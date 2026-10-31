"""Aplica o contrato aprovado de raw para refined."""

import re
from decimal import Decimal, InvalidOperation

import duckdb

from pipeline.comum import PipelineError, executar_cli, quantidade
from pipeline.contrato import TABELAS, Coluna, Tabela
from pipeline.db import conectar, criar_schema, identificador


def expressao(coluna: Coluna, origem: str | None = None) -> str:
    campo = origem or identificador(coluna.origem)
    if coluna.tipo == "DATE":
        return f"CAST(STRPTIME({campo}, '%Y%m%d') AS DATE)"
    return f"CAST({campo} AS {coluna.tipo})"


def verificar_estrutura(con: duckdb.DuckDBPyConnection) -> None:
    existentes = {
        linha[0]
        for linha in con.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'raw'"
        ).fetchall()
    }
    ausentes = [t.nome for t in TABELAS if t.nome not in existentes]
    if ausentes:
        raise PipelineError(
            "Tabelas ausentes: "
            + ", ".join(f"raw.{n}" for n in ausentes)
            + ". Execute: uv run python -m pipeline.ingestao"
        )
    for tabela in TABELAS:
        atuais = {
            linha[0]
            for linha in con.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema='raw' AND table_name=?",
                [tabela.nome],
            ).fetchall()
        }
        esperadas = {c.origem for c in tabela.colunas}
        if atuais != esperadas:
            raise PipelineError(
                f"raw.{tabela.nome}: colunas ausentes {sorted(esperadas - atuais)}; "
                f"colunas não previstas {sorted(atuais - esperadas)}."
            )


def erro_valor(
    tabela: Tabela, coluna: Coluna, valor: str, motivo: str
) -> PipelineError:
    return PipelineError(
        f"raw.{tabela.nome}, coluna {coluna.origem} -> {coluna.destino}: "
        f"valor inválido {valor!r}; {motivo}"
    )


def converter_valores(tabela: Tabela, coluna: Coluna, valores: list[str]) -> list:
    # Conexão isolada: erro de CAST aborta uma transação DuckDB ativa e impediria
    # localizar o exemplo inválido na conexão que publica refined.
    with duckdb.connect() as validador:
        try:
            return validador.execute(
                f"SELECT valor, {expressao(coluna, 'valor')} "
                "FROM unnest(?) AS entrada(valor)",
                [valores],
            ).fetchall()
        except duckdb.Error as erro:
            for valor in valores:
                try:
                    validador.execute(
                        f"SELECT {expressao(coluna, '?')}", [valor]
                    ).fetchone()
                except duckdb.Error as detalhe:
                    raise erro_valor(tabela, coluna, valor, str(detalhe)) from detalhe
            raise PipelineError(f"raw.{tabela.nome}.{coluna.origem}: {erro}") from erro


def validar_conversoes(con: duckdb.DuckDBPyConnection, tabela: Tabela) -> None:
    """Valida valores distintos, incluindo a exatidão decimal antes de gravar."""
    for coluna in tabela.colunas:
        if coluna.tipo == "VARCHAR":
            continue
        campo = identificador(coluna.origem)
        valores = [
            linha[0]
            for linha in con.execute(
                f"SELECT DISTINCT {campo} FROM raw.{identificador(tabela.nome)} "
                f"WHERE {campo} IS NOT NULL ORDER BY {campo}"
            ).fetchall()
        ]
        if not valores:
            continue
        if coluna.tipo == "DATE":
            for valor in valores:
                if re.fullmatch(r"[0-9]{8}", valor) is None:
                    raise erro_valor(tabela, coluna, valor, "esperado YYYYMMDD")
        convertidos = converter_valores(tabela, coluna, valores)
        if coluna.tipo.startswith("DECIMAL"):
            for valor, convertido in convertidos:
                try:
                    original = Decimal(valor)
                    exato = original.is_finite() and original == convertido
                except InvalidOperation:
                    exato = False
                if not exato:
                    raise erro_valor(
                        tabela,
                        coluna,
                        valor,
                        f"conversão para {coluna.tipo} não preserva o valor exato",
                    )


def verificar_chaves(con: duckdb.DuckDBPyConnection, tabela: Tabela) -> None:
    chaves = ", ".join(identificador(c) for c in tabela.chave)
    alvo = f"refined.{identificador(tabela.nome)}"
    conflito = con.execute(
        f"SELECT {chaves} FROM {alvo} GROUP BY {chaves} HAVING count(*) > 1 "
        f"ORDER BY {chaves} LIMIT 1"
    ).fetchone()
    if conflito is not None:
        filtro = " AND ".join(
            f"{identificador(c)} IS NOT DISTINCT FROM ?" for c in tabela.chave
        )
        linhas = con.execute(
            f"SELECT * FROM {alvo} WHERE {filtro}", conflito
        ).fetchall()
        nomes = [c.destino for c in tabela.colunas]
        detalhes = "\n".join(
            repr(dict(zip(nomes, linha, strict=True))) for linha in linhas
        )
        chave = dict(zip(tabela.chave, conflito, strict=True))
        raise PipelineError(
            f"{alvo}: chave repetida {chave}; linhas conflitantes:\n{detalhes}"
        )


def estatisticas(con: duckdb.DuckDBPyConnection, tabela: Tabela, origem: bool) -> tuple:
    fonte = (
        f"(SELECT DISTINCT * FROM raw.{identificador(tabela.nome)})"
        if origem
        else f"refined.{identificador(tabela.nome)}"
    )
    campos = ["count(*)"]
    for coluna in tabela.colunas:
        campo = identificador(coluna.origem if origem else coluna.destino)
        campos.append(f"count(*) FILTER (WHERE {campo} IS NULL)")
    for coluna in tabela.colunas:
        if coluna.tipo.startswith("DECIMAL"):
            campo = expressao(coluna) if origem else identificador(coluna.destino)
            campos.append(f"sum({campo})")
    return con.execute(f"SELECT {', '.join(campos)} FROM {fonte}").fetchone()


def transformar(con: duckdb.DuckDBPyConnection) -> None:
    verificar_estrutura(con)
    mensagens = []
    total = 0
    # Uma falha não deixa parte da nova carga publicada em refined.
    con.execute("BEGIN TRANSACTION")
    try:
        criar_schema(con, "refined")
        for tabela in TABELAS:
            validar_conversoes(con, tabela)
            selecao = ", ".join(
                f"{expressao(c)} AS {identificador(c.destino)}" for c in tabela.colunas
            )
            alvo = f"refined.{identificador(tabela.nome)}"
            fonte = f"raw.{identificador(tabela.nome)}"
            con.execute(
                f"CREATE OR REPLACE TABLE {alvo} AS SELECT {selecao} "
                f"FROM (SELECT DISTINCT * FROM {fonte})"
            )
            verificar_chaves(con, tabela)
            antes = estatisticas(con, tabela, origem=True)
            depois = estatisticas(con, tabela, origem=False)
            if antes != depois:
                raise PipelineError(
                    f"{alvo}: contagem, nulos ou somas divergem da origem deduplicada."
                )
            entrada = con.execute(f"SELECT count(*) FROM {fonte}").fetchone()[0]
            saida = depois[0]
            total += saida
            mensagens.append(
                f"refined.{tabela.nome} {quantidade(entrada)} -> "
                f"{quantidade(saida)} linhas ({quantidade(entrada - saida)} duplicatas)"
            )
            nulos = [
                f"{coluna.destino} {quantidade(n)}"
                for coluna, n in zip(
                    tabela.colunas, depois[1 : 1 + len(tabela.colunas)], strict=True
                )
                if n
            ]
            mensagens.append("nulos mantidos: " + (", ".join(nulos) or "nenhum"))
        diferencas = con.execute(
            "SELECT count(*) FROM ("
            "(SELECT amostra_id FROM refined.x1 "
            "EXCEPT SELECT amostra_id FROM refined.y1)"
            " UNION ALL "
            "(SELECT amostra_id FROM refined.y1 "
            "EXCEPT SELECT amostra_id FROM refined.x1)"
            ")"
        ).fetchone()[0]
        if diferencas:
            raise PipelineError("Amostras de refined.x1 e refined.y1 não correspondem.")
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    print("\n".join([*mensagens, f"TOTAL: {quantidade(total)} linhas"]))


def main() -> None:
    with conectar() as con:
        transformar(con)


if __name__ == "__main__":
    executar_cli(main)
