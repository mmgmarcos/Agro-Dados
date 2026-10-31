"""Interface local: uv run python ui.py."""

import math
import os
import subprocess
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

import altair as alt
import duckdb
import pandas as pd
import streamlit as st
from streamlit.runtime.scriptrunner import get_script_run_ctx
from streamlit.web import cli

from pipeline.comum import quantidade
from pipeline.contrato import TABELAS
from pipeline.db import BANCO, RAIZ, identificador

CONTRATOS = {t.nome: t for t in TABELAS}
KG_POR_SACA = 60


def formatar_sacas(valor: float | int | None) -> str:
    """Formata sacas em escala legível, preservando a unidade no rótulo."""
    if valor is None or pd.isna(valor):
        return "—"
    valor = float(valor)
    sinal = "-" if valor < 0 else ""
    absoluto = abs(valor)
    if absoluto >= 1_000_000:
        return f"{sinal}{absoluto / 1_000_000:.1f} milhões de sacas"
    if absoluto >= 1_000:
        return f"{sinal}{absoluto / 1_000:.1f} mil sacas"
    return f"{sinal}{absoluto:.1f} sacas"


def toneladas_para_sacas(valor: pd.Series) -> pd.Series:
    """Converte toneladas em sacas de 60 kg para exibição no dashboard."""
    return valor * 1_000 / KG_POR_SACA


def kg_para_sacas(valor: pd.Series) -> pd.Series:
    """Converte kg em sacas de 60 kg para exibição no dashboard."""
    return valor / KG_POR_SACA


def consultar(sql: str, parametros: list | None = None) -> pd.DataFrame:
    """Abre uma conexão curta, sem deixar o banco bloqueado para o pipeline."""
    if not BANCO.is_file():
        raise FileNotFoundError("Banco ausente. Execute a ingestão e a transformação.")
    with duckdb.connect(str(BANCO), read_only=True) as con:
        return con.execute(sql, parametros or []).fetchdf()


def tabelas_disponiveis(schema: str) -> list[str]:
    dados = consultar(
        "SELECT table_name FROM information_schema.tables WHERE table_schema=?",
        [schema],
    )
    return [nome for nome in CONTRATOS if nome in set(dados["table_name"])]


def consultar_sql(sql: str, limite: int) -> tuple[pd.DataFrame, bool]:
    """Executa uma consulta de leitura e limita apenas as linhas retornadas à UI."""
    if not 1 <= limite <= 10000:
        raise ValueError("O limite deve estar entre 1 e 10.000 linhas.")
    if not BANCO.is_file():
        raise FileNotFoundError("Banco ausente. Execute a ingestão e a transformação.")
    with duckdb.connect(str(BANCO), read_only=True) as con:
        comandos = con.extract_statements(sql)
        if len(comandos) != 1:
            raise ValueError("Informe uma única consulta SQL por execução.")
        if comandos[0].type != duckdb.StatementType.SELECT:
            raise ValueError(
                "Use somente consultas: SELECT, WITH, SHOW ou DESCRIBE. "
                "Alterações no banco não são permitidas neste editor."
            )
        resultado = con.sql(comandos[0].query).limit(limite + 1)
        registros = resultado.fetchall()
        # Aliases repetidos são válidos em SQL, mas não nas tabelas do Streamlit.
        nomes: list[str] = []
        for original in resultado.columns:
            nome = original
            sufixo = 2
            while nome in nomes:
                nome = f"{original}_{sufixo}"
                sufixo += 1
            nomes.append(nome)
    linhas = [
        [format(valor, "f") if isinstance(valor, Decimal) else valor for valor in linha]
        for linha in registros[:limite]
    ]
    return pd.DataFrame(linhas, columns=nomes, dtype=object), len(registros) > limite


def painel_sql() -> None:
    st.header("Consultas SQL")
    st.caption(
        "DuckDB · agro.duckdb · somente leitura. "
        "Use nomes completos, como raw.x1 ou refined.produtividade_soja."
    )
    with st.form("consulta_sql", enter_to_submit=False):
        sql = st.text_area(
            "SQL",
            value="SELECT *\nFROM refined.produtividade_soja\nLIMIT 10;",
            height=220,
            key="sql_editor",
            persist_state="session",
        )
        limite = int(
            st.number_input(
                "Máximo de linhas exibidas",
                min_value=1,
                max_value=10000,
                value=1000,
                step=100,
            )
        )
        executar = st.form_submit_button("Executar consulta", type="primary")
    if executar:
        st.session_state.pop("resultado_sql", None)
        st.session_state.pop("erro_sql", None)
        try:
            with st.spinner("Consultando o DuckDB..."):
                dados, truncado = consultar_sql(sql, limite)
            st.session_state["resultado_sql"] = (sql, dados, truncado)
        except (duckdb.Error, OSError, ValueError) as erro:
            st.session_state["erro_sql"] = str(erro)
    if "erro_sql" in st.session_state:
        st.error(st.session_state["erro_sql"])
    if "resultado_sql" in st.session_state:
        executado, dados, truncado = st.session_state["resultado_sql"]
        st.subheader("Resultado da última consulta executada")
        if truncado:
            st.caption(
                f"Exibindo as primeiras {quantidade(len(dados))} linhas. "
                "Há mais registros; refine o SQL ou aumente o limite de exibição."
            )
        elif dados.empty:
            st.info("A consulta não retornou registros.")
        else:
            st.caption(f"{quantidade(len(dados))} linhas retornadas.")
        st.dataframe(dados, hide_index=True, width="stretch", alt="Resultado SQL")
        st.download_button(
            "Baixar resultado exibido em CSV",
            dados.to_csv(index=False).encode("utf-8-sig"),
            file_name="consulta_sql.csv",
            mime="text/csv",
        )
        with st.expander("SQL executado"):
            st.code(executado, language="sql")
    with st.expander("Tabelas e colunas disponíveis"):
        catalogo = consultar(
            "SELECT table_schema AS camada, table_name AS tabela, "
            "column_name AS coluna, data_type AS tipo "
            "FROM information_schema.columns WHERE table_schema IN ('raw', 'refined') "
            "ORDER BY table_schema, table_name, ordinal_position"
        )
        st.dataframe(
            catalogo, hide_index=True, width="stretch", alt="Catálogo do banco"
        )
    with st.expander("Exemplo: consultar X1 e y1 juntos"):
        st.code(
            "SELECT x.amostra_id, x.producao_arroz, y.produtividade_arroz\n"
            "FROM refined.x1 AS x\n"
            "JOIN refined.y1 AS y USING (amostra_id)\n"
            "ORDER BY x.amostra_id\nLIMIT 100;",
            language="sql",
        )


def painel_consulta() -> None:
    st.header("Consultar tabelas")
    esquerda, direita = st.columns(2)
    schema = esquerda.selectbox("Camada", ["refined", "raw"])
    disponiveis = tabelas_disponiveis(schema)
    if not disponiveis:
        st.info(f"Nenhuma tabela em {schema}. Use a página Executar pipeline.")
        return
    nome = direita.selectbox("Tabela", disponiveis)
    tabela = CONTRATOS[nome]
    alvo = f"{identificador(schema)}.{identificador(nome)}"
    estrutura = consultar(
        "SELECT column_name AS coluna, data_type AS tipo "
        "FROM information_schema.columns WHERE table_schema=? AND table_name=? "
        "ORDER BY ordinal_position",
        [schema, nome],
    )
    coluna = st.selectbox("Coluna para filtrar", ["Sem filtro", *estrutura["coluna"]])
    filtro = ""
    parametros = []
    if coluna != "Sem filtro":
        esquerda, direita = st.columns(2)
        operacao = esquerda.selectbox("Condição", ["Contém", "Igual a", "É nulo"])
        campo = identificador(coluna)
        if operacao == "É nulo":
            filtro = f" WHERE {campo} IS NULL"
        else:
            valor = direita.text_input("Valor do filtro (texto)")
            if valor:
                filtro = (
                    f" WHERE contains(lower(CAST({campo} AS VARCHAR)), lower(?))"
                    if operacao == "Contém"
                    else f" WHERE CAST({campo} AS VARCHAR) = ?"
                )
                parametros.append(valor)

    total = int(
        consultar(f"SELECT count(*) AS n FROM {alvo}{filtro}", parametros).iat[0, 0]
    )
    esquerda, direita = st.columns(2)
    tamanho = esquerda.selectbox("Linhas por página", [100, 500, 1000])
    paginas = max(1, math.ceil(total / tamanho))
    pagina = int(
        direita.number_input(
            "Página",
            min_value=1,
            max_value=paginas,
            value=1,
            step=1,
            key=f"pagina_{schema}_{nome}_{coluna}_{filtro}_{parametros}_{tamanho}",
        )
    )
    # Evita a conversão implícita de DECIMAL para float na prévia e no CSV.
    selecao = ", ".join(
        f"CAST({identificador(c)} AS VARCHAR) AS {identificador(c)}"
        if tipo.startswith("DECIMAL")
        else identificador(c)
        for c, tipo in estrutura.itertuples(index=False, name=None)
    )
    chaves = [
        c.origem if schema == "raw" else c.destino
        for c in tabela.colunas
        if c.destino in tabela.chave
    ]
    ordem = ", ".join(identificador(c) for c in chaves)
    dados = consultar(
        f"SELECT {selecao} FROM {alvo}{filtro} ORDER BY {ordem} LIMIT ? OFFSET ?",
        [*parametros, tamanho, (pagina - 1) * tamanho],
    )
    st.caption(
        f"{schema}.{nome} · {quantidade(total)} registros no filtro · "
        f"página {quantidade(pagina)} de {quantidade(paginas)}"
    )
    if dados.empty:
        st.info("Nenhum registro corresponde ao filtro.")
    st.dataframe(dados, hide_index=True, width="stretch")
    st.download_button(
        "Baixar esta página em CSV",
        dados.to_csv(index=False).encode("utf-8-sig"),
        file_name=f"{schema}_{nome}_pagina_{pagina}.csv",
        mime="text/csv",
    )
    with st.expander("Colunas e tipos"):
        st.dataframe(estrutura, hide_index=True, width="stretch")


def painel_clima() -> None:
    municipios = consultar(
        "SELECT DISTINCT a.codigo_ibge, coalesce(trim(s.nome), a.codigo_ibge) AS nome "
        "FROM refined.agroclimatology a LEFT JOIN refined.produtividade_soja s "
        "ON a.codigo_ibge=s.codigo_ibge AND s.nivel='MU' "
        "WHERE a.codigo_ibge IS NOT NULL ORDER BY nome, codigo_ibge"
    )
    if municipios.empty:
        st.info("Não há municípios disponíveis para os gráficos.")
        return
    rotulos = dict(zip(municipios["codigo_ibge"], municipios["nome"], strict=True))
    codigo = st.selectbox(
        "Município", list(rotulos), format_func=lambda c: f"{rotulos[c]} · {c}"
    )
    anos = consultar(
        "SELECT DISTINCT year(data_medicao) AS ano FROM refined.agroclimatology "
        "WHERE codigo_ibge=? AND data_medicao IS NOT NULL ORDER BY ano",
        [codigo],
    )["ano"].tolist()
    st.subheader("Clima diário")
    if anos:
        esquerda, direita = st.columns([1, 3])
        ano = esquerda.selectbox("Ano do clima", anos, index=len(anos) - 1)
        medidas = [
            c.destino
            for c in CONTRATOS["agroclimatology"].colunas
            if c.tipo.startswith("DECIMAL")
            and c.destino not in ("latitude", "longitude")
        ]
        medida = direita.selectbox(
            "Medida climática",
            medidas,
            index=medidas.index("temperatura_media_2m"),
            format_func=lambda c: c.replace("_", " ").capitalize(),
        )
        dados = consultar(
            f"SELECT data_medicao, {identificador(medida)} AS valor "
            "FROM refined.agroclimatology WHERE codigo_ibge=? "
            "AND data_medicao >= ? AND data_medicao < ? ORDER BY data_medicao",
            [codigo, date(int(ano), 1, 1), date(int(ano) + 1, 1, 1)],
        )
        st.caption(
            f"refined.agroclimatology · {rotulos[codigo]} · {ano} · "
            f"{quantidade(len(dados))} registros · unidade da fonte"
        )
        # Datas ausentes e valores nulos permanecem lacunas, sem interpolação.
        calendario = pd.date_range(f"{ano}-01-01", f"{ano}-12-31", name="data_medicao")
        serie = dados.set_index("data_medicao").reindex(calendario).reset_index()
        if serie["valor"].notna().any():
            grafico = (
                alt.Chart(serie)
                .mark_line()
                .encode(
                    x=alt.X(
                        "data_medicao:T",
                        title="Data",
                        axis=alt.Axis(format="%b %Y", tickCount=12),
                    ),
                    y=alt.Y(
                        "valor:Q",
                        title=medida.replace("_", " ").capitalize(),
                    ),
                    tooltip=[
                        alt.Tooltip("data_medicao:T", title="Data", format="%d/%m/%Y"),
                        alt.Tooltip("valor:Q", title="Valor"),
                    ],
                )
            )
            st.altair_chart(
                grafico,
                width="stretch",
                theme=None,
                alt="Série diária da medida climática com eixo temporal mensal",
            )
        else:
            st.info("Não há valores preenchidos para esta medida no período.")
        if serie["valor"].isna().any():
            st.caption(
                f"Dias sem valor: {quantidade(int(serie['valor'].isna().sum()))}."
            )
        if dados["valor"].eq(-999).any():
            st.caption(
                "A fonte contém -999 nesta seleção; esses valores estão preservados."
            )
        with st.expander("Dados do gráfico de clima"):
            st.dataframe(dados, hide_index=True, width="stretch")
    else:
        st.info("Não há medições com data para este município.")



def painel_soja() -> None:
    municipios = consultar(
        "SELECT DISTINCT codigo_ibge, trim(nome) AS nome "
        "FROM refined.produtividade_soja WHERE nivel='MU' "
        "ORDER BY nome, codigo_ibge"
    )
    if municipios.empty:
        st.info("Não há municípios disponíveis para a série da soja.")
        return
    rotulos = dict(zip(municipios["codigo_ibge"], municipios["nome"], strict=True))
    codigo = st.selectbox(
        "Município", list(rotulos), format_func=lambda c: f"{rotulos[c]} · {c}"
    )
    soja = consultar(
        "SELECT * FROM refined.produtividade_soja WHERE codigo_ibge=? AND nivel='MU'",
        [codigo],
    )
    colunas = [
        c.destino
        for c in CONTRATOS["produtividade_soja"].colunas
        if c.destino.startswith("produtividade_")
    ]
    serie_soja = pd.DataFrame(
        {
            "ano": [int(c.rsplit("_", 1)[1]) for c in colunas],
            "produtividade_fonte": [soja.iloc[0][c] for c in colunas],
        }
    )
    serie_soja["sacas_por_hectare"] = kg_para_sacas(
        serie_soja["produtividade_fonte"]
    )
    ultimo = serie_soja.dropna(subset=["sacas_por_hectare"]).tail(1)
    st.caption(
        f"refined.produtividade_soja · {rotulos[codigo]} · "
        f"{serie_soja['ano'].min()}–{serie_soja['ano'].max()}. "
        "A série da fonte foi interpretada como kg/ha e convertida por 60 kg/saca."
    )
    if not ultimo.empty:
        st.metric(
            f"Produção equivalente em {int(ultimo.iloc[0]['ano'])}",
            f"{ultimo.iloc[0]['sacas_por_hectare']:.1f} sacas/ha",
            border=True,
        )
    if serie_soja["sacas_por_hectare"].notna().any():
        st.line_chart(
            serie_soja,
            x="ano",
            y="sacas_por_hectare",
            x_label="Ano",
            y_label="Sacas por hectare",
            height=300,
        )
    else:
        st.info("A série de produtividade está inteiramente nula.")
    with st.expander("Dados do gráfico de soja"):
        st.dataframe(
            serie_soja,
            hide_index=True,
            width="stretch",
            column_config={
                "produtividade_fonte": st.column_config.NumberColumn(
                    "Valor da fonte"
                ),
                "sacas_por_hectare": st.column_config.NumberColumn(
                    "Sacas por hectare", format="%.1f"
                ),
            },
            alt="Série histórica da produção equivalente de soja em sacas por hectare",
        )


def painel_arroz() -> None:
    dados = consultar(
        "SELECT x.amostra_id, x.producao_arroz, y.produtividade_arroz "
        "FROM refined.x1 x JOIN refined.y1 y USING (amostra_id) ORDER BY x.amostra_id"
    )
    dados["producao_sacas"] = toneladas_para_sacas(dados["producao_arroz"])
    total_sacas = dados["producao_sacas"].sum()
    st.subheader("Produção de arroz")
    st.caption(
        "refined.x1 + refined.y1 · correspondência por amostra_id · "
        "RICE_PRODUCTION interpretado como toneladas e convertido em sacas de 60 kg."
    )
    with st.container(horizontal=True):
        st.metric("Produção total", formatar_sacas(total_sacas), border=True)
        st.metric("Amostras", quantidade(len(dados)), border=True)
    validos = dados.dropna(subset=["producao_arroz", "produtividade_arroz"])
    st.caption(
        f"{quantidade(len(validos))} amostras com produção e produtividade "
        "preenchidas."
    )
    if validos.empty:
        st.info("Não há pares preenchidos para o gráfico.")
    else:
        st.scatter_chart(
            validos,
            x="producao_sacas",
            y="produtividade_arroz",
            x_label="Produção de arroz (sacas)",
            y_label="Produtividade do arroz",
            height=420,
        )
    with st.expander("Amostras do gráfico"):
        st.dataframe(
            dados,
            hide_index=True,
            width="stretch",
            column_config={
                "producao_arroz": st.column_config.NumberColumn(
                    "Produção na fonte"
                ),
                "producao_sacas": st.column_config.NumberColumn(
                    "Produção (sacas)", format="%.1f"
                ),
            },
            alt="Amostras de produção de arroz convertidas para sacas",
        )


def painel_dashboard() -> None:
    st.header("Dashboards por tema")
    visao = st.segmented_control(
        "Visão",
        ["Clima", "Arroz", "Soja"],
        default="Clima",
        key="dashboard_visao",
    )
    disponiveis = tabelas_disponiveis("refined")
    exigidas = {
        "Clima": ["agroclimatology"],
        "Arroz": ["x1", "y1"],
        "Soja": ["produtividade_soja"],
    }[visao or "Clima"]
    ausentes = [nome for nome in exigidas if nome not in disponiveis]
    if ausentes:
        st.info("Execute o pipeline para disponibilizar: " + ", ".join(ausentes))
        return
    if visao == "Clima":
        painel_clima()
    elif visao == "Arroz":
        painel_arroz()
    else:
        painel_soja()


def executar_etapas(etapas: list[str]) -> tuple[bool, str]:
    saidas = []
    for etapa in etapas:
        if etapa not in ("ingestao", "transformacao"):
            raise ValueError("Etapa desconhecida.")
        resultado = subprocess.run(
            [sys.executable, "-m", f"pipeline.{etapa}"],
            cwd=RAIZ,
            capture_output=True,
            text=True,
            encoding="utf-8",
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            check=False,
        )
        saidas.append(
            f"$ python -m pipeline.{etapa}\n{resultado.stdout}{resultado.stderr}"
        )
        if resultado.returncode != 0:
            return False, "\n".join(saidas)
    return True, "\n".join(saidas)


def painel_pipeline() -> None:
    st.header("Executar pipeline")
    st.write(
        "A ingestão substitui raw a partir dos CSVs. A transformação substitui refined."
    )
    opcoes = {
        "Pipeline completo": ["ingestao", "transformacao"],
        "Somente ingestão": ["ingestao"],
        "Somente transformação": ["transformacao"],
    }
    escolha = st.selectbox("Etapas", list(opcoes))
    if st.button("Executar", type="primary"):
        with st.spinner("Executando; aguarde a conclusão das etapas..."):
            st.session_state["ultima_execucao"] = executar_etapas(opcoes[escolha])
    if "ultima_execucao" in st.session_state:
        sucesso, saida = st.session_state["ultima_execucao"]
        if sucesso:
            st.success("Execução concluída.")
        else:
            st.error("A execução falhou. Veja o diagnóstico abaixo.")
        st.code(saida, language="text")


def main() -> None:
    st.set_page_config(
        page_title="Agro dados", page_icon=":material/agriculture:", layout="wide"
    )
    st.title("Agro dados")
    pagina = st.sidebar.radio(
        "Navegação",
        ["Dashboard", "Consultar tabelas", "Consultas SQL", "Executar pipeline"],
    )
    st.sidebar.caption("Fonte: agro.duckdb · dados locais")
    st.sidebar.button("Atualizar dados")
    try:
        if pagina == "Executar pipeline":
            painel_pipeline()
        elif pagina == "Consultar tabelas":
            painel_consulta()
        elif pagina == "Consultas SQL":
            painel_sql()
        else:
            painel_dashboard()
    except FileNotFoundError as erro:
        st.info(str(erro))
    except (duckdb.Error, OSError) as erro:
        st.error(f"Não foi possível concluir a operação: {erro}")
        st.caption("Se o banco estiver em uso por outra execução, aguarde e atualize.")


if __name__ == "__main__":
    if get_script_run_ctx(suppress_warning=True) is None:
        cli.main(
            args=["run", str(Path(__file__).resolve()), *sys.argv[1:]],
            prog_name="streamlit",
        )
    else:
        main()
