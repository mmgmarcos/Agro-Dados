"""Conexão compartilhada com o banco do projeto."""

from pathlib import Path

import duckdb

RAIZ = Path(__file__).resolve().parents[1]
BANCO = RAIZ / "agro.duckdb"


def conectar() -> duckdb.DuckDBPyConnection:
    return duckdb.connect(str(BANCO))


def identificador(nome: str) -> str:
    return '"' + nome.replace('"', '""') + '"'


def criar_schema(con: duckdb.DuckDBPyConnection, nome: str) -> None:
    con.execute(f"CREATE SCHEMA IF NOT EXISTS {identificador(nome)}")
