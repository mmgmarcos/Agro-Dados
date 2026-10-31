import csv
from datetime import date
from decimal import Decimal
from pathlib import Path

import duckdb
import pytest

from pipeline import db, ingestao, transformacao
from pipeline.comum import PipelineError, executar_cli
from pipeline.contrato import TABELAS
from pipeline.ingestao import ingerir, numerar_amostras
from pipeline.transformacao import transformar


def retrato(con: duckdb.DuckDBPyConnection, schema: str) -> dict[str, list]:
    return {
        t.nome: con.execute(f"SELECT * FROM {schema}.{t.nome} ORDER BY ALL").fetchall()
        for t in TABELAS
    }


def test_ingestao_preserva_textos_nulos_tipos_e_amostras(
    con: duckdb.DuckDBPyConnection, csvs: Path, capsys: pytest.CaptureFixture
) -> None:
    ingerir(con, csvs)
    assert con.execute(
        "SELECT DISTINCT data_type FROM information_schema.columns "
        "WHERE table_schema='raw'"
    ).fetchall() == [("VARCHAR",)]
    assert con.execute(
        'SELECT codigo_ibge, name, "2004" FROM raw.produtividade_soja '
        "ORDER BY codigo_ibge"
    ).fetchall() == [("000", "  Abatiá", None), ("001", "NULL", None)]
    assert con.execute("SELECT * FROM raw.y1 ORDER BY amostra_id").fetchall() == [
        ("1", "1.25"),
        ("2", "1.25"),
    ]
    antes = retrato(con, "raw")
    saida = capsys.readouterr().out
    ingerir(con, csvs)
    assert retrato(con, "raw") == antes
    assert capsys.readouterr().out == saida


def test_transformacao_preserva_dados_e_reexecucao(
    con: duckdb.DuckDBPyConnection, csvs: Path, capsys: pytest.CaptureFixture
) -> None:
    ingerir(con, csvs)
    con.execute(
        "CREATE OR REPLACE TABLE raw.agroclimatology AS "
        "SELECT * FROM raw.agroclimatology UNION ALL "
        "SELECT * FROM raw.agroclimatology"
    )
    antes = retrato(con, "raw")
    capsys.readouterr()
    transformar(con)
    saida = capsys.readouterr().out
    assert "refined.agroclimatology 4 -> 2 linhas (2 duplicatas)" in saida
    assert "nulos mantidos: indice_uv_superficie 1" in saida
    assert "nulos mantidos: produtividade_2004 2" in saida
    assert "TOTAL: 8 linhas" in saida
    assert con.execute(
        "SELECT data_medicao, latitude, indice_uv_superficie "
        "FROM refined.agroclimatology WHERE codigo_ibge='000'"
    ).fetchone() == (date(2004, 2, 29), Decimal("-23.304900000000001"), Decimal("-999"))
    assert con.execute("SELECT sum(chuva_media) FROM refined.x1").fetchone()[0] == (
        Decimal("125.06666666666668")
    )
    assert (
        con.execute(
            "SELECT sum(produtividade_2004) FROM refined.produtividade_soja"
        ).fetchone()[0]
        is None
    )
    assert con.execute("SELECT count(*) FROM refined.y1").fetchone()[0] == 2
    tipos = dict(
        con.execute(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_schema='refined' AND table_name='x1'"
        ).fetchall()
    )
    assert tipos["amostra_id"] == "VARCHAR"
    assert tipos["chuva_media"] == "DECIMAL(22,16)"
    refined = retrato(con, "refined")
    transformar(con)
    assert capsys.readouterr().out == saida
    assert retrato(con, "refined") == refined
    assert retrato(con, "raw") == antes
    ingerir(con, csvs)
    assert retrato(con, "refined") == refined


@pytest.mark.parametrize(
    ("coluna", "valor"),
    [
        ("T2M", "invalido"),
        ("T2M", "1.235"),
        ("T2M", "1e-3"),
        ("T2M", "100000000"),
        ("T2M", "NaN"),
        ("T2M", "Infinity"),
        ("data", "20030229"),
        ("data", "2003-01-01"),
        ("data", "2003011"),
    ],
)
def test_conversao_invalida_diagnostica_e_preserva_refined(
    con: duckdb.DuckDBPyConnection, csvs: Path, coluna: str, valor: str
) -> None:
    ingerir(con, csvs)
    transformar(con)
    antes = retrato(con, "refined")
    con.execute(
        f"UPDATE raw.agroclimatology SET \"{coluna}\"=? WHERE codigo_ibge='001'",
        [valor],
    )
    with pytest.raises(PipelineError) as erro:
        transformar(con)
    assert "raw.agroclimatology" in str(erro.value)
    assert coluna in str(erro.value)
    assert repr(valor) in str(erro.value)
    assert retrato(con, "refined") == antes


def test_numeros_equivalentes_e_data_nula(
    con: duckdb.DuckDBPyConnection, csvs: Path
) -> None:
    ingerir(con, csvs)
    con.execute("UPDATE raw.agroclimatology SET T2M='1.2300', data=NULL")
    transformar(con)
    assert con.execute(
        "SELECT DISTINCT data_medicao, temperatura_media_2m "
        "FROM refined.agroclimatology"
    ).fetchall() == [(None, Decimal("1.23"))]


@pytest.mark.parametrize("chave_nula", [False, True])
def test_conflito_de_chave_mostra_linhas(
    con: duckdb.DuckDBPyConnection, csvs: Path, chave_nula: bool
) -> None:
    ingerir(con, csvs)
    con.execute(
        "UPDATE raw.produtividade_soja SET codigo_ibge=?",
        [None if chave_nula else "000"],
    )
    with pytest.raises(PipelineError) as erro:
        transformar(con)
    mensagem = str(erro.value)
    assert "chave repetida" in mensagem
    assert "linhas conflitantes" in mensagem
    assert "  Abatiá" in mensagem and "NULL" in mensagem
    assert (
        con.execute(
            "SELECT count(*) FROM information_schema.tables "
            "WHERE table_schema='refined'"
        ).fetchone()[0]
        == 0
    )


def test_amostras_desalinhadas(con: duckdb.DuckDBPyConnection, csvs: Path) -> None:
    ingerir(con, csvs)
    con.execute("UPDATE raw.y1 SET amostra_id='3' WHERE amostra_id='2'")
    with pytest.raises(PipelineError, match="não correspondem"):
        transformar(con)


def test_tabelas_ausentes_e_saida_de_erro(
    con: duckdb.DuckDBPyConnection, capsys: pytest.CaptureFixture
) -> None:
    with pytest.raises(SystemExit) as erro:
        executar_cli(lambda: transformar(con))
    assert erro.value.code == 1
    mensagem = capsys.readouterr().err
    for nome in ("agroclimatology", "produtividade_soja", "x1", "y1"):
        assert f"raw.{nome}" in mensagem
    assert "uv run python -m pipeline.ingestao" in mensagem


@pytest.mark.parametrize("mudanca", ["DROP COLUMN T2M", "ADD COLUMN extra VARCHAR"])
def test_colunas_fora_do_contrato(
    con: duckdb.DuckDBPyConnection, csvs: Path, mudanca: str
) -> None:
    ingerir(con, csvs)
    con.execute(f"ALTER TABLE raw.agroclimatology {mudanca}")
    with pytest.raises(PipelineError, match="colunas"):
        transformar(con)


def test_arquivos_ausentes(con: duckdb.DuckDBPyConnection, tmp_path: Path) -> None:
    with pytest.raises(PipelineError) as erro:
        ingerir(con, tmp_path)
    for tabela in TABELAS:
        assert tabela.arquivo in str(erro.value)


def test_quantidades_diferentes(con: duckdb.DuckDBPyConnection, csvs: Path) -> None:
    (csvs / "y1.csv").write_text("RICE_YIELD\n1.25\n", encoding="utf-8")
    with pytest.raises(PipelineError, match="x1 2, y1 1"):
        ingerir(con, csvs)


@pytest.mark.parametrize("vazio", ["", '""'])
def test_alvo_vazio_preserva_amostra(
    con: duckdb.DuckDBPyConnection, csvs: Path, vazio: str
) -> None:
    (csvs / "y1.csv").write_text(
        f"RICE_YIELD\n1.25\n{vazio}\n", encoding="utf-8", newline=""
    )
    ingerir(con, csvs)
    transformar(con)
    assert con.execute("SELECT * FROM refined.y1 ORDER BY amostra_id").fetchall() == [
        ("1", Decimal("1.25")),
        ("2", None),
    ]


def test_numeracao_conta_registros_csv(tmp_path: Path) -> None:
    origem = tmp_path / "origem.csv"
    destino = tmp_path / "destino.csv"
    origem.write_text(
        'campo\n"texto\nmultilinha"\n"com,virgula"\n', encoding="utf-8", newline=""
    )
    assert numerar_amostras(origem, destino) == 2
    with destino.open(encoding="utf-8", newline="") as arquivo:
        assert list(csv.reader(arquivo)) == [
            ["amostra_id", "campo"],
            ["1", "texto\nmultilinha"],
            ["2", "com,virgula"],
        ]


@pytest.mark.parametrize("conteudo", ["", "a,a\n1,2\n", "a\n1,2\n", 'a\n"aberto'])
def test_csv_invalido(tmp_path: Path, conteudo: str) -> None:
    origem = tmp_path / "origem.csv"
    origem.write_text(conteudo, encoding="utf-8")
    with pytest.raises(PipelineError):
        numerar_amostras(origem, tmp_path / "destino.csv")


def test_falha_ingestao_preserva_raw(
    con: duckdb.DuckDBPyConnection, csvs: Path
) -> None:
    ingerir(con, csvs)
    antes = retrato(con, "raw")
    (csvs / "produtividade_soja.csv").write_text(
        'nivel,codigo_ibge,name\n"campo sem fechamento', encoding="utf-8"
    )
    with pytest.raises(PipelineError, match="raw.produtividade_soja"):
        ingerir(con, csvs)
    assert retrato(con, "raw") == antes


def test_entrypoints_usam_banco_do_projeto(
    csvs: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    banco = tmp_path / "teste.duckdb"
    pasta_raw = tmp_path / "raw"
    pasta_raw.mkdir()
    for tabela in TABELAS:
        (csvs / tabela.arquivo).rename(pasta_raw / tabela.arquivo)
    monkeypatch.setattr(db, "BANCO", banco)
    monkeypatch.setattr(ingestao, "RAIZ", tmp_path)
    ingestao.main()
    transformacao.main()
    with duckdb.connect(str(banco), read_only=True) as con:
        assert con.execute("SELECT count(*) FROM refined.y1").fetchone()[0] == 2
