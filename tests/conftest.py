import csv
from collections.abc import Iterator
from pathlib import Path

import duckdb
import pytest

from pipeline.contrato import TABELAS


@pytest.fixture
def con() -> Iterator[duckdb.DuckDBPyConnection]:
    with duckdb.connect() as conexao:
        yield conexao


@pytest.fixture
def csvs(tmp_path: Path) -> Path:
    for tabela in TABELAS:
        colunas = [c for c in tabela.colunas if c.origem != "amostra_id"]
        with (tmp_path / tabela.arquivo).open(
            "w", encoding="utf-8", newline=""
        ) as arquivo:
            escritor = csv.DictWriter(arquivo, [c.origem for c in colunas])
            escritor.writeheader()
            for indice in range(2):
                linha = {
                    c.origem: (
                        "20040229"
                        if c.tipo == "DATE"
                        else "1.25"
                        if c.tipo.startswith("DECIMAL")
                        else "texto"
                    )
                    for c in colunas
                }
                if "codigo_ibge" in linha:
                    linha["codigo_ibge"] = f"00{indice}"
                if "name" in linha:
                    linha["name"] = "  Abatiá" if indice == 0 else "NULL"
                if "avg_rain" in linha:
                    linha["avg_rain"] = "62.53333333333334"
                if "latitude" in linha:
                    linha["latitude"] = "-23.304900000000001"
                if "ALLSKY_SFC_UV_INDEX" in linha:
                    linha["ALLSKY_SFC_UV_INDEX"] = "-999.0" if indice == 0 else ""
                if "2004" in linha:
                    linha["2004"] = ""
                escritor.writerow(linha)
    return tmp_path
