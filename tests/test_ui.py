import subprocess
from pathlib import Path

import duckdb
import pytest
from streamlit.testing.v1 import AppTest

import ui
from pipeline import db
from pipeline.ingestao import ingerir
from pipeline.transformacao import transformar


@pytest.fixture
def banco_ui(csvs: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    caminho = csvs / "interface.duckdb"
    with duckdb.connect(str(caminho)) as con:
        ingerir(con, csvs)
        con.execute("UPDATE raw.produtividade_soja SET nivel='MU'")
        transformar(con)
    monkeypatch.setattr(db, "BANCO", caminho)
    monkeypatch.setattr(ui, "BANCO", caminho)
    return caminho


def test_dashboard_e_consulta_com_filtro(banco_ui: Path) -> None:
    app = AppTest.from_file(str(db.RAIZ / "ui.py"), default_timeout=30).run()
    assert not app.exception
    assert app.selectbox[0].value == "000"
    assert len(app.get("vega_lite_chart")) == 2
    app.radio[0].set_value("Arroz").run()
    assert not app.exception
    assert len(app.get("vega_lite_chart")) == 1
    app.sidebar.radio[0].set_value("Consultar tabelas").run()
    assert not app.exception
    app.selectbox[1].set_value("x1").run()
    app.selectbox[2].set_value("amostra_id").run()
    next(w for w in app.selectbox if w.label == "Condição").set_value("Igual a").run()
    app.text_input[0].set_value("1").run()
    assert not app.exception
    exibido = app.dataframe[0].value
    assert len(exibido) == 1
    assert exibido.iloc[0]["amostra_id"] == "1"
    assert exibido.iloc[0]["chuva_media"] == "62.5333333333333400"
    app.text_input[0].set_value("' OR 1=1 --").run()
    assert not app.exception
    assert app.dataframe[0].value.empty
    assert any("Nenhum registro" in item.value for item in app.info)


def test_banco_ausente_permite_executar_pipeline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    banco = tmp_path / "ausente.duckdb"
    monkeypatch.setattr(db, "BANCO", banco)
    app = AppTest.from_file(str(db.RAIZ / "ui.py"), default_timeout=30).run()
    assert not app.exception
    assert any("Banco ausente" in item.value for item in app.info)
    assert not banco.exists()
    app.sidebar.radio[0].set_value("Executar pipeline").run()
    assert not app.exception
    assert app.selectbox[0].value == "Pipeline completo"


@pytest.mark.parametrize("codigo_saida", [0, 1])
def test_botao_executa_modulos_e_interrompe_falha(
    banco_ui: Path, monkeypatch: pytest.MonkeyPatch, codigo_saida: int
) -> None:
    chamadas = []

    def executar_mock(args: list[str], **kwargs: object) -> subprocess.CompletedProcess:
        chamadas.append(args)
        assert kwargs["cwd"] == db.RAIZ
        assert kwargs["encoding"] == "utf-8"
        return subprocess.CompletedProcess(
            args,
            codigo_saida,
            stdout="Carga concluída\n" if codigo_saida == 0 else "",
            stderr="Valor inválido\n" if codigo_saida else "",
        )

    monkeypatch.setattr(subprocess, "run", executar_mock)
    app = AppTest.from_file(str(db.RAIZ / "ui.py"), default_timeout=30).run()
    app.sidebar.radio[0].set_value("Executar pipeline").run()
    assert chamadas == []
    next(b for b in app.button if b.label == "Executar").click().run()
    assert not app.exception
    assert [args[-1] for args in chamadas] == (
        ["pipeline.ingestao", "pipeline.transformacao"]
        if codigo_saida == 0
        else ["pipeline.ingestao"]
    )
    if codigo_saida:
        assert app.error and "Valor inválido" in app.code[0].value
    else:
        assert app.success and "Carga concluída" in app.code[0].value


def test_refined_ausente(banco_ui: Path) -> None:
    with duckdb.connect(str(banco_ui)) as con:
        con.execute("DROP SCHEMA refined CASCADE")
    app = AppTest.from_file(str(db.RAIZ / "ui.py"), default_timeout=30).run()
    assert not app.exception
    assert any("Execute o pipeline" in item.value for item in app.info)


def test_sql_cte_join_precisao_e_limite(banco_ui: Path) -> None:
    dados, truncado = ui.consultar_sql(
        "-- consulta com CTE\nWITH amostras AS (SELECT * FROM refined.x1) "
        "SELECT x.amostra_id, x.chuva_media, y.produtividade_arroz "
        "FROM amostras x JOIN refined.y1 y USING(amostra_id) "
        "ORDER BY x.amostra_id;",
        1,
    )
    assert truncado
    assert dados.to_dict("records") == [
        {
            "amostra_id": "1",
            "chuva_media": "62.5333333333333400",
            "produtividade_arroz": "1.25",
        }
    ]
    agregado, truncado = ui.consultar_sql(
        "SELECT count(*) AS n, sum(chuva_media) AS soma FROM refined.x1", 1
    )
    assert not truncado
    assert agregado.iloc[0]["n"] == 2
    assert agregado.iloc[0]["soma"] == "125.0666666666666800"
    vazio, truncado = ui.consultar_sql("SELECT * FROM refined.x1 WHERE false", 10)
    assert vazio.empty and not truncado
    assert "chuva_media" in vazio.columns
    texto, _ = ui.consultar_sql("SELECT 'a;b' AS texto, NULL AS ausente", 1)
    assert texto.iloc[0]["texto"] == "a;b"
    assert texto.iloc[0]["ausente"] is None
    descricao, _ = ui.consultar_sql("DESCRIBE refined.x1", 100)
    assert "chuva_media" in descricao["column_name"].tolist()


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM refined.x1",
        "CREATE TABLE refined.nova AS SELECT 1",
        "COPY refined.x1 TO 'nao_criar.csv'",
        "SELECT 1; DELETE FROM refined.x1",
        "",
        "-- apenas comentario",
    ],
)
def test_sql_rejeita_escrita_e_multiplos_comandos(banco_ui: Path, sql: str) -> None:
    with pytest.raises(ValueError):
        ui.consultar_sql(sql, 100)
    with duckdb.connect(str(banco_ui), read_only=True) as con:
        assert con.execute("SELECT count(*) FROM refined.x1").fetchone()[0] == 2
        assert not con.execute(
            "SELECT * FROM information_schema.tables WHERE table_name='nova'"
        ).fetchall()


def test_editor_sql_resultado_erro_e_sem_execucao_automatica(banco_ui: Path) -> None:
    app = AppTest.from_file(str(db.RAIZ / "ui.py"), default_timeout=30).run()
    app.sidebar.radio[0].set_value("Consultas SQL").run()
    assert not app.exception
    assert "resultado_sql" not in app.session_state
    app.text_area[0].set_value("SELECT count(*) AS total FROM refined.x1;")
    next(b for b in app.button if b.label == "Executar consulta").click().run()
    assert not app.exception
    assert app.dataframe[0].value.iloc[0]["total"] == 2
    app.text_area[0].set_value("SELECT coluna_inexistente FROM refined.x1")
    next(b for b in app.button if b.label == "Executar consulta").click().run()
    assert not app.exception
    assert app.error and "coluna_inexistente" in app.error[0].value
    assert "resultado_sql" not in app.session_state
    app.text_area[0].set_value("SELECT * FROM refined.x1 WHERE false")
    next(b for b in app.button if b.label == "Executar consulta").click().run()
    assert not app.exception and not app.error
    assert any("não retornou registros" in item.value for item in app.info)
