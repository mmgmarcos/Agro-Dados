"""Mapas de nomes, tipos e chaves definidos em SPEC.md."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Coluna:
    origem: str
    destino: str
    tipo: str


@dataclass(frozen=True)
class Tabela:
    nome: str
    arquivo: str
    chave: tuple[str, ...]
    colunas: tuple[Coluna, ...]


TABELAS = (
    Tabela(
        "agroclimatology",
        "agroclimatology.csv",
        ("codigo_ibge", "data_medicao"),
        (
            Coluna("data", "data_medicao", "TIMESTAMP"),
            Coluna("codigo_ibge", "codigo_ibge", "VARCHAR"),
            Coluna("latitude", "latitude", "DECIMAL(18,15)"),
            Coluna("longitude", "longitude", "DECIMAL(18,15)"),
            Coluna("T2M_RANGE", "amplitude_temperatura_2m", "DECIMAL(10,2)"),
            Coluna("TS", "temperatura_superficie", "DECIMAL(10,2)"),
            Coluna("T2MDEW", "temperatura_ponto_orvalho_2m", "DECIMAL(10,2)"),
            Coluna("T2MWET", "temperatura_bulbo_umido_2m", "DECIMAL(10,2)"),
            Coluna("T2M_MAX", "temperatura_maxima_2m", "DECIMAL(10,2)"),
            Coluna("T2M_MIN", "temperatura_minima_2m", "DECIMAL(10,2)"),
            Coluna("T2M", "temperatura_media_2m", "DECIMAL(10,2)"),
            Coluna("QV2M", "umidade_especifica_2m", "DECIMAL(10,2)"),
            Coluna("RH2M", "umidade_relativa_2m", "DECIMAL(10,2)"),
            Coluna("PRECTOTCORR", "precipitacao_corrigida", "DECIMAL(10,2)"),
            Coluna("PS", "pressao_superficie", "DECIMAL(10,2)"),
            Coluna("WS2M", "velocidade_vento_2m", "DECIMAL(10,2)"),
            Coluna("WS2M_MAX", "velocidade_maxima_vento_2m", "DECIMAL(10,2)"),
            Coluna("WS2M_MIN", "velocidade_minima_vento_2m", "DECIMAL(10,2)"),
            Coluna("WS2M_RANGE", "amplitude_velocidade_vento_2m", "DECIMAL(10,2)"),
            Coluna("WS10M", "velocidade_vento_10m", "DECIMAL(10,2)"),
            Coluna("WS10M_MAX", "velocidade_maxima_vento_10m", "DECIMAL(10,2)"),
            Coluna("WS10M_MIN", "velocidade_minima_vento_10m", "DECIMAL(10,2)"),
            Coluna("WS10M_RANGE", "amplitude_velocidade_vento_10m", "DECIMAL(10,2)"),
            Coluna("WS50M", "velocidade_vento_50m", "DECIMAL(10,2)"),
            Coluna("WS50M_MAX", "velocidade_maxima_vento_50m", "DECIMAL(10,2)"),
            Coluna("WS50M_MIN", "velocidade_minima_vento_50m", "DECIMAL(10,2)"),
            Coluna("WS50M_RANGE", "amplitude_velocidade_vento_50m", "DECIMAL(10,2)"),
            Coluna("GWETTOP", "umidade_solo_superficial", "DECIMAL(10,2)"),
            Coluna("GWETROOT", "umidade_solo_zona_radicular", "DECIMAL(10,2)"),
            Coluna("GWETPROF", "umidade_solo_perfil", "DECIMAL(10,2)"),
            Coluna(
                "ALLSKY_SFC_SW_DWN", "radiacao_ondas_curtas_superficie", "DECIMAL(10,2)"
            ),
            Coluna(
                "CLRSKY_SFC_SW_DWN",
                "radiacao_ondas_curtas_superficie_ceu_claro",
                "DECIMAL(10,2)",
            ),
            Coluna(
                "TOA_SW_DWN", "radiacao_ondas_curtas_topo_atmosfera", "DECIMAL(10,2)"
            ),
            Coluna(
                "ALLSKY_SFC_PAR_TOT",
                "radiacao_fotossintetica_superficie",
                "DECIMAL(10,2)",
            ),
            Coluna(
                "CLRSKY_SFC_PAR_TOT",
                "radiacao_fotossintetica_superficie_ceu_claro",
                "DECIMAL(10,2)",
            ),
            Coluna("ALLSKY_SFC_UVA", "radiacao_uva_superficie", "DECIMAL(10,2)"),
            Coluna("ALLSKY_SFC_UVB", "radiacao_uvb_superficie", "DECIMAL(10,2)"),
            Coluna("ALLSKY_SFC_UV_INDEX", "indice_uv_superficie", "DECIMAL(10,2)"),
        ),
    ),
    Tabela(
        "produtividade_soja",
        "produtividade_soja.csv",
        ("nivel", "codigo_ibge"),
        (
            Coluna("nivel", "nivel", "VARCHAR"),
            Coluna("codigo_ibge", "codigo_ibge", "VARCHAR"),
            Coluna("name", "nome", "VARCHAR"),
            Coluna("2004", "produtividade_2004", "DECIMAL(10,2)"),
            Coluna("2005", "produtividade_2005", "DECIMAL(10,2)"),
            Coluna("2006", "produtividade_2006", "DECIMAL(10,2)"),
            Coluna("2007", "produtividade_2007", "DECIMAL(10,2)"),
            Coluna("2008", "produtividade_2008", "DECIMAL(10,2)"),
            Coluna("2009", "produtividade_2009", "DECIMAL(10,2)"),
            Coluna("2010", "produtividade_2010", "DECIMAL(10,2)"),
            Coluna("2011", "produtividade_2011", "DECIMAL(10,2)"),
            Coluna("2012", "produtividade_2012", "DECIMAL(10,2)"),
            Coluna("2013", "produtividade_2013", "DECIMAL(10,2)"),
            Coluna("2014", "produtividade_2014", "DECIMAL(10,2)"),
            Coluna("2015", "produtividade_2015", "DECIMAL(10,2)"),
            Coluna("2016", "produtividade_2016", "DECIMAL(10,2)"),
            Coluna("2017", "produtividade_2017", "DECIMAL(10,2)"),
        ),
    ),
    Tabela(
        "x1",
        "X1.csv",
        ("amostra_id",),
        (
            Coluna("amostra_id", "amostra_id", "VARCHAR"),
            Coluna("ANNUAL", "valor_anual", "DECIMAL(10,2)"),
            Coluna("avg_rain", "chuva_media", "DECIMAL(22,16)"),
            Coluna("Nitrogen", "nitrogenio", "DECIMAL(14,2)"),
            Coluna("POTASH", "potassa", "DECIMAL(14,2)"),
            Coluna("PHOSPHATE", "fosfato", "DECIMAL(14,2)"),
            Coluna("DYSTROPEPTS", "solo_dystropepts", "DECIMAL(10,2)"),
            Coluna("FLUVENTS", "solo_fluvents", "DECIMAL(10,2)"),
            Coluna("INCEPTISOLS", "solo_inceptisols", "DECIMAL(10,2)"),
            Coluna("LOAMY_ALFISOL", "solo_alfisol_franco", "DECIMAL(10,2)"),
            Coluna("ORTHENTS", "solo_orthents", "DECIMAL(10,2)"),
            Coluna("ORTHIDS", "solo_orthids", "DECIMAL(10,2)"),
            Coluna("PSAMMENTS", "solo_psamments", "DECIMAL(10,2)"),
            Coluna("SANDY_ALFISOL", "solo_alfisol_arenoso", "DECIMAL(10,2)"),
            Coluna("UDALFS", "solo_udalfs", "DECIMAL(10,2)"),
            Coluna("UDOLLS_UDALFS", "solo_udolls_udalfs", "DECIMAL(10,2)"),
            Coluna("UDUPTS_UDALFS", "solo_udupts_udalfs", "DECIMAL(10,2)"),
            Coluna("USTALF_USTOLLS", "solo_ustalf_ustolls", "DECIMAL(10,2)"),
            Coluna("USTALFS", "solo_ustalfs", "DECIMAL(10,2)"),
            Coluna("VERTIC_SOILS", "solos_verticos", "DECIMAL(10,2)"),
            Coluna("VERTISOLS", "solo_vertisols", "DECIMAL(10,2)"),
            Coluna("RICE_PRODUCTION", "producao_arroz", "DECIMAL(14,2)"),
        ),
    ),
    Tabela(
        "y1",
        "y1.csv",
        ("amostra_id",),
        (
            Coluna("amostra_id", "amostra_id", "VARCHAR"),
            Coluna("RICE_YIELD", "produtividade_arroz", "DECIMAL(10,2)"),
        ),
    ),
)
