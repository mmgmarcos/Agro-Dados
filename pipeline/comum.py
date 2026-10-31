"""Erros e apresentação dos comandos."""

import sys
from collections.abc import Callable

import duckdb


class PipelineError(Exception):
    """Violação do contrato de entrada ou de transformação."""


def quantidade(valor: int) -> str:
    return f"{valor:,}".replace(",", ".")


def executar_cli(acao: Callable[[], None]) -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    try:
        acao()
    except (PipelineError, duckdb.Error, OSError, UnicodeError) as erro:
        print(f"ERRO: {erro}", file=sys.stderr)
        sys.exit(1)
