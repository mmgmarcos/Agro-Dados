"""Carrega os quatro CSVs em raw, sem conversões de domínio."""

import csv
from pathlib import Path
from tempfile import TemporaryDirectory

import duckdb

from pipeline.comum import PipelineError, executar_cli, quantidade
from pipeline.contrato import TABELAS
from pipeline.db import RAIZ, conectar, criar_schema, identificador


def numerar_amostras(origem: Path, destino: Path) -> int:
    """Registra a posição do registro CSV antes de qualquer operação SQL."""
    with (
        origem.open(encoding="utf-8", newline="") as entrada,
        destino.open("w", encoding="utf-8", newline="") as saida,
    ):
        leitor = csv.reader(entrada, strict=True)
        escritor = csv.writer(saida)
        try:
            cabecalho = next(leitor)
            if "amostra_id" in cabecalho or len(set(cabecalho)) != len(cabecalho):
                raise PipelineError(f"{origem.name}: cabeçalho duplicado ou reservado.")
            escritor.writerow(["amostra_id", *cabecalho])
            total = 0
            for total, registro in enumerate(leitor, start=1):
                # No CSV de uma coluna, um registro vazio é um campo vazio.
                if not registro and len(cabecalho) == 1:
                    registro = [""]
                if len(registro) != len(cabecalho):
                    raise PipelineError(
                        f"{origem.name}: registro {total} com quantidade de "
                        "campos diferente do cabeçalho."
                    )
                escritor.writerow([str(total), *registro])
        except (StopIteration, csv.Error) as erro:
            raise PipelineError(f"{origem.name}: CSV inválido: {erro}") from erro
    return total


def ingerir(con: duckdb.DuckDBPyConnection, pasta: Path) -> None:
    ausentes = [t.arquivo for t in TABELAS if not (pasta / t.arquivo).is_file()]
    if ausentes:
        raise PipelineError("Arquivos ausentes: " + ", ".join(ausentes))

    with TemporaryDirectory(prefix="agro_amostras_") as temporario:
        caminhos = {t.nome: pasta / t.arquivo for t in TABELAS}
        totais = {}
        for nome in ("x1", "y1"):
            destino = Path(temporario) / f"{nome}.csv"
            totais[nome] = numerar_amostras(caminhos[nome], destino)
            caminhos[nome] = destino
        if totais["x1"] != totais["y1"]:
            raise PipelineError(
                f"Quantidades de amostras diferentes: x1 {totais['x1']}, "
                f"y1 {totais['y1']}."
            )

        mensagens = []
        con.execute("BEGIN TRANSACTION")
        try:
            criar_schema(con, "raw")
            for tabela in TABELAS:
                alvo = f"raw.{identificador(tabela.nome)}"
                try:
                    con.execute(
                        f"CREATE OR REPLACE TABLE {alvo} AS "
                        "SELECT * FROM read_csv(?, header=true, all_varchar=true, "
                        "delim=',', quote='\"', escape='\"', nullstr='', "
                        "allow_quoted_nulls=true, strict_mode=true, encoding='utf-8')",
                        [str(caminhos[tabela.nome])],
                    )
                except duckdb.Error as erro:
                    raise PipelineError(f"raw.{tabela.nome}: {erro}") from erro
                total = con.execute(f"SELECT count(*) FROM {alvo}").fetchone()[0]
                mensagens.append(f"raw.{tabela.nome} {quantidade(total)} linhas")
            con.execute("COMMIT")
        except Exception:
            con.execute("ROLLBACK")
            raise
    print("\n".join(mensagens))


def main() -> None:
    with conectar() as con:
        ingerir(con, RAIZ / "raw")


if __name__ == "__main__":
    executar_cli(main)
