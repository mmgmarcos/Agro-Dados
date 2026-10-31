# Pipeline agrícola — spec aprovada

Status: aprovada pelo usuário em 29/10/2026, incluindo os mapas, tipos e a identidade posicional de X1/y1.

Esta spec substitui os mapas das oito tabelas operacionais pelo contrato dos quatro CSVs presentes no projeto. Mantém a filosofia: refined torna os dados consistentes para consumo, sem corrigir fatos nem tomar decisões de negócio.

## 1. Decisões já confirmadas

- Python 3.14, dependências gerenciadas com uv e DuckDB.
- Banco `agro.duckdb` na raiz do projeto.
- Execução pela linha de comando, sem orquestrador.
- Implementar também a conexão e a ingestão, pois esses componentes ainda não existem.
- Processar somente `agroclimatology`, `produtividade_soja`, `x1` e `y1`.
- Comparar nulos e somas com a origem após a remoção das duplicatas exatas aplicáveis. Esta é a interpretação adotada para a resposta ao item 4.
- Não processar `imagens_satelite` nem criar marts.

## 2. Evidência dos arquivos atuais

Inspeção local em 29/10/2026. Estas contagens documentam a entrada atual; não são limites fixos para futuras cargas.

| Arquivo | Linhas | Colunas originais | Repetições exatas além da primeira |
| --- | ---: | ---: | ---: |
| `raw/agroclimatology.csv` | 2.294.675 | 38 | 0 |
| `raw/produtividade_soja.csv` | 349 | 17 | 0 |
| `raw/X1.csv` | 2.536 | 21 | 0 |
| `raw/y1.csv` | 2.536 | 1 | 51 |

Não foram encontrados campos nulos na leitura atual. A combinação `(codigo_ibge, data)` é única em agroclimatology; `(nivel, codigo_ibge)` é única em produtividade_soja.

`avg_rain` tem até 16 casas decimais; latitude tem até 15 e longitude até 14. Reduzi-las a duas casas mudaria os valores. Há valores como `-999.0` no índice UV e valores negativos em X1; eles serão preservados como números, sem interpretação automática como ausência de informação.

## 3. Identidade de X1 e y1

Os dois arquivos têm a mesma quantidade de registros e não contêm identificadores. O usuário aprovou a correspondência da linha N de X1 com a linha N de y1.

**Identidade posicional aprovada:**

- Na ingestão, acrescentar `amostra_id VARCHAR` a raw.x1 e raw.y1.
- O valor será a posição do registro no CSV, a partir de `1`, sem contar o cabeçalho. Contar registros CSV, não linhas físicas de texto.
- Atribuir o identificador durante a leitura ordenada do arquivo, antes de operações SQL que possam alterar a ordem.
- Preservar o mesmo identificador em refined. Ele é uma identidade técnica dentro da versão dos arquivos, não um identificador estável entre arquivos reordenados.
- Verificar que X1 e y1 tenham a mesma quantidade de registros; caso contrário, mostrar as duas contagens e encerrar com código 1.
- Não juntar os arquivos na ingestão ou transformação. A correspondência ficará disponível por `amostra_id`.
- Valores de produtividade iguais em amostras diferentes são registros distintos. As 51 repetições de valores em y1 não serão removidas.

Esta é uma alteração explícita em relação à spec original: adiciona uma coluna técnica a cada uma dessas duas tabelas. Todas as colunas originais continuam presentes. A deduplicação considera a linha completa, incluindo `amostra_id`.

Essa correspondência faz parte do contrato dos arquivos. Não inferir relações adicionais com os dados de municípios ou de soja.

## 4. Artefatos e execução

Arquivos de implementação:

- `pipeline/__init__.py`
- `pipeline/db.py`, expondo `conectar()` e `criar_schema(con, nome)`.
- `pipeline/ingestao.py`.
- `pipeline/transformacao.py`.
- `pipeline/contrato.py`, centralizando os mapas aprovados.
- `pipeline/comum.py`, compartilhando erros e apresentação da CLI.

`conectar()` abre o arquivo da raiz do projeto. As duas etapas reutilizam esse módulo.

```shell
uv run python -m pipeline.ingestao
uv run python -m pipeline.transformacao
```

Os comandos são executados na raiz do projeto. A transformação não executa a ingestão automaticamente.

## 5. Contrato da ingestão

| Arquivo | Destino |
| --- | --- |
| `raw/agroclimatology.csv` | `raw.agroclimatology` |
| `raw/produtividade_soja.csv` | `raw.produtividade_soja` |
| `raw/X1.csv` | `raw.x1` |
| `raw/y1.csv` | `raw.y1` |

- Verificar a existência dos quatro arquivos antes de começar; listar os ausentes e encerrar com código 1.
- Ler CSV com cabeçalho, separador vírgula e codificação UTF-8, respeitando aspas de campos CSV.
- Criar o schema raw se necessário.
- Preservar os nomes originais e carregar todas as colunas como VARCHAR.
- Converter somente campos de conteúdo vazio em NULL. Espaços, textos como `NULL` e números sentinela não serão reinterpretados.
- Preservar espaços nos valores textuais, inclusive nos nomes de municípios.
- Não remover duplicatas, corrigir valores nem renomear colunas nesta etapa.
- Adicionar `amostra_id` conforme a seção 3.
- Recriar cada tabela com `CREATE OR REPLACE TABLE`; não usar INSERT, APPEND ou MERGE.
- Escrever somente no schema raw; não modificar refined nem os CSVs.
- Informar a tabela e a quantidade carregada, com separador de milhar por ponto.

## 6. Contrato da transformação

- Ler somente as quatro tabelas do schema raw e escrever somente suas correspondentes no schema refined.
- Manter os nomes das tabelas: `refined.agroclimatology`, `refined.produtividade_soja`, `refined.x1` e `refined.y1`.
- Criar refined se necessário.
- Antes de transformar, verificar a existência das quatro tabelas raw. Listar todas as ausentes, orientar `uv run python -m pipeline.ingestao` e encerrar com `sys.exit(1)`.
- Verificar os nomes das colunas contra os mapas abaixo, incluindo `amostra_id`. Listar colunas ausentes ou não previstas e encerrar com código 1, sem descartá-las silenciosamente.
- Renomear todas as colunas conforme os mapas; nomes que já estejam adequados podem permanecer iguais.
- Recriar tabelas com `CREATE OR REPLACE TABLE`; não usar INSERT, APPEND ou MERGE.
- Não preencher nulos, remover linhas por nulos, normalizar textos, converter unidades, calcular indicadores ou alterar o formato largo da produtividade da soja.

## 7. Mapas de nomes e tipos aprovados

Os tipos decimais abaixo preservam a precisão textual observada. Não atribuir unidades como kg, hectares ou milímetros aos campos cuja unidade não está documentada no projeto.

Os nomes climáticos são propostas de tradução das siglas NASA POWER, não uma confirmação da procedência ou das unidades deste CSV. A documentação oficial disponibiliza um [dicionário de parâmetros](https://power.larc.nasa.gov/docs/tutorials/parameters/); as descrições de [meteorologia](https://gis.earthdata.nasa.gov/portal/home/item.html?id=c1673c398f044392b2f4d6a52a201a38) e [radiação](https://gis.earthdata.nasa.gov/portal/home/item.html?id=f85d4fc5eb0740ac8cffb3803e7b0d7a) orientam a nomenclatura proposta.

### 7.1 agroclimatology

Chave: `(codigo_ibge, data_medicao)`.

| Origem | Destino | Tipo |
| --- | --- | --- |
| data | data_medicao | DATE |
| codigo_ibge | codigo_ibge | VARCHAR |
| latitude | latitude | DECIMAL(18,15) |
| longitude | longitude | DECIMAL(18,15) |
| T2M_RANGE | amplitude_temperatura_2m | DECIMAL(10,2) |
| TS | temperatura_superficie | DECIMAL(10,2) |
| T2MDEW | temperatura_ponto_orvalho_2m | DECIMAL(10,2) |
| T2MWET | temperatura_bulbo_umido_2m | DECIMAL(10,2) |
| T2M_MAX | temperatura_maxima_2m | DECIMAL(10,2) |
| T2M_MIN | temperatura_minima_2m | DECIMAL(10,2) |
| T2M | temperatura_media_2m | DECIMAL(10,2) |
| QV2M | umidade_especifica_2m | DECIMAL(10,2) |
| RH2M | umidade_relativa_2m | DECIMAL(10,2) |
| PRECTOTCORR | precipitacao_corrigida | DECIMAL(10,2) |
| PS | pressao_superficie | DECIMAL(10,2) |
| WS2M | velocidade_vento_2m | DECIMAL(10,2) |
| WS2M_MAX | velocidade_maxima_vento_2m | DECIMAL(10,2) |
| WS2M_MIN | velocidade_minima_vento_2m | DECIMAL(10,2) |
| WS2M_RANGE | amplitude_velocidade_vento_2m | DECIMAL(10,2) |
| WS10M | velocidade_vento_10m | DECIMAL(10,2) |
| WS10M_MAX | velocidade_maxima_vento_10m | DECIMAL(10,2) |
| WS10M_MIN | velocidade_minima_vento_10m | DECIMAL(10,2) |
| WS10M_RANGE | amplitude_velocidade_vento_10m | DECIMAL(10,2) |
| WS50M | velocidade_vento_50m | DECIMAL(10,2) |
| WS50M_MAX | velocidade_maxima_vento_50m | DECIMAL(10,2) |
| WS50M_MIN | velocidade_minima_vento_50m | DECIMAL(10,2) |
| WS50M_RANGE | amplitude_velocidade_vento_50m | DECIMAL(10,2) |
| GWETTOP | umidade_solo_superficial | DECIMAL(10,2) |
| GWETROOT | umidade_solo_zona_radicular | DECIMAL(10,2) |
| GWETPROF | umidade_solo_perfil | DECIMAL(10,2) |
| ALLSKY_SFC_SW_DWN | radiacao_ondas_curtas_superficie | DECIMAL(10,2) |
| CLRSKY_SFC_SW_DWN | radiacao_ondas_curtas_superficie_ceu_claro | DECIMAL(10,2) |
| TOA_SW_DWN | radiacao_ondas_curtas_topo_atmosfera | DECIMAL(10,2) |
| ALLSKY_SFC_PAR_TOT | radiacao_fotossintetica_superficie | DECIMAL(10,2) |
| CLRSKY_SFC_PAR_TOT | radiacao_fotossintetica_superficie_ceu_claro | DECIMAL(10,2) |
| ALLSKY_SFC_UVA | radiacao_uva_superficie | DECIMAL(10,2) |
| ALLSKY_SFC_UVB | radiacao_uvb_superficie | DECIMAL(10,2) |
| ALLSKY_SFC_UV_INDEX | indice_uv_superficie | DECIMAL(10,2) |

`data` usa o formato `YYYYMMDD`, por exemplo `20030101`. Validar oito dígitos e converter com `STRPTIME(valor, '%Y%m%d')`, seguido de CAST para DATE. Datas inexistentes são erros; NULL continua NULL.

Nos nomes de radiação sem o sufixo `ceu_claro`, o campo de origem é ALLSKY: todas as condições de céu. Os campos de ondas curtas representam radiação descendente, e os campos de radiação fotossintética representam o total.

### 7.2 produtividade_soja

Chave: `(nivel, codigo_ibge)`. Manter uma linha por unidade geográfica e as colunas anuais; não realizar UNPIVOT nesta fase.

| Origem | Destino | Tipo |
| --- | --- | --- |
| nivel | nivel | VARCHAR |
| codigo_ibge | codigo_ibge | VARCHAR |
| name | nome | VARCHAR |
| 2004 | produtividade_2004 | DECIMAL(10,2) |
| 2005 | produtividade_2005 | DECIMAL(10,2) |
| 2006 | produtividade_2006 | DECIMAL(10,2) |
| 2007 | produtividade_2007 | DECIMAL(10,2) |
| 2008 | produtividade_2008 | DECIMAL(10,2) |
| 2009 | produtividade_2009 | DECIMAL(10,2) |
| 2010 | produtividade_2010 | DECIMAL(10,2) |
| 2011 | produtividade_2011 | DECIMAL(10,2) |
| 2012 | produtividade_2012 | DECIMAL(10,2) |
| 2013 | produtividade_2013 | DECIMAL(10,2) |
| 2014 | produtividade_2014 | DECIMAL(10,2) |
| 2015 | produtividade_2015 | DECIMAL(10,2) |
| 2016 | produtividade_2016 | DECIMAL(10,2) |
| 2017 | produtividade_2017 | DECIMAL(10,2) |

### 7.3 x1

Chave: `amostra_id`. Os termos taxonômicos dos solos permanecem identificáveis; o prefixo `solo_` e os qualificadores usam português. Não converter classificações de solo para outro sistema taxonômico.

| Origem | Destino | Tipo |
| --- | --- | --- |
| amostra_id (técnica) | amostra_id | VARCHAR |
| ANNUAL | valor_anual | DECIMAL(10,2) |
| avg_rain | chuva_media | DECIMAL(22,16) |
| Nitrogen | nitrogenio | DECIMAL(14,2) |
| POTASH | potassa | DECIMAL(14,2) |
| PHOSPHATE | fosfato | DECIMAL(14,2) |
| DYSTROPEPTS | solo_dystropepts | DECIMAL(10,2) |
| FLUVENTS | solo_fluvents | DECIMAL(10,2) |
| INCEPTISOLS | solo_inceptisols | DECIMAL(10,2) |
| LOAMY_ALFISOL | solo_alfisol_franco | DECIMAL(10,2) |
| ORTHENTS | solo_orthents | DECIMAL(10,2) |
| ORTHIDS | solo_orthids | DECIMAL(10,2) |
| PSAMMENTS | solo_psamments | DECIMAL(10,2) |
| SANDY_ALFISOL | solo_alfisol_arenoso | DECIMAL(10,2) |
| UDALFS | solo_udalfs | DECIMAL(10,2) |
| UDOLLS_UDALFS | solo_udolls_udalfs | DECIMAL(10,2) |
| UDUPTS_UDALFS | solo_udupts_udalfs | DECIMAL(10,2) |
| USTALF_USTOLLS | solo_ustalf_ustolls | DECIMAL(10,2) |
| USTALFS | solo_ustalfs | DECIMAL(10,2) |
| VERTIC_SOILS | solos_verticos | DECIMAL(10,2) |
| VERTISOLS | solo_vertisols | DECIMAL(10,2) |
| RICE_PRODUCTION | producao_arroz | DECIMAL(14,2) |

`ANNUAL` não tem significado suficientemente documentado no projeto. Propõe-se `valor_anual`, sem afirmar que se trata de chuva acumulada. Os campos de solo são preservados numericamente; não se assume que sejam porcentagens ou proporções para aplicar validações de negócio.

### 7.4 y1

Chave: `amostra_id`.

| Origem | Destino | Tipo |
| --- | --- | --- |
| amostra_id (técnica) | amostra_id | VARCHAR |
| RICE_YIELD | produtividade_arroz | DECIMAL(10,2) |

## 8. Conversões e erros

- Converter tipos com CAST ou STRPTIME; nunca usar TRY_CAST, TRY_STRPTIME ou `errors="coerce"`.
- Identificadores permanecem VARCHAR, preservando sua representação.
- NULL de origem deve continuar NULL após conversão.
- Em erro de conversão, mostrar tabela, coluna de origem/destino e pelo menos um valor inválido; encerrar com `sys.exit(1)`.
- A preservação das somas exige que a conversão não arredonde valores. Se uma nova entrada não puder ser representada exatamente no tipo declarado, tratá-la como erro com o mesmo diagnóstico, em vez de aceitar o arredondamento que um CAST decimal poderia realizar.
- Não converter `-999`, valores negativos ou qualquer outro valor preenchido em NULL.

## 9. Duplicatas, conflitos e nulos

1. Determinar duplicatas exatas comparando todas as colunas da origem, antes das conversões; NULLs na mesma posição contam como iguais para essa finalidade.
2. Manter uma ocorrência de cada linha exatamente repetida e contabilizar as removidas.
3. Converter e renomear conforme o mapa.
4. Detectar mais de uma linha restante para a mesma chave definida nesta proposta. Mostrar tabela, chave e linhas conflitantes, e encerrar com `sys.exit(1)`.

Representações textuais distintas que resultem na mesma chave após conversão não serão descartadas silenciosamente. Devem ser reportadas como conflito de chave.

Em x1 e y1, `amostra_id` faz parte da linha completa: duas amostras com medidas iguais continuam sendo duas linhas. Não deduplicar o alvo isoladamente.

Nenhuma linha é apagada por ter nulos e nenhum nulo é preenchido. Na verificação de conflitos, NULLs na mesma posição da chave são agrupados; não criar uma regra adicional que proíba chaves nulas.

## 10. Comparações e critérios de aceite

Definir `origem_base` como o conjunto de linhas raw após a deduplicação exata da seção 9, incluindo os identificadores técnicos quando aplicáveis.

- Existem quatro tabelas refined, com todas as colunas e tipos previstos.
- Quantidade de linhas refined = quantidade de linhas de `origem_base`.
- Linhas raw menos linhas refined = duplicatas exatas removidas.
- Para cada coluna, nulos em refined = nulos em `origem_base`.
- Para cada medida numérica, soma em refined = soma numérica exata dos textos não nulos de `origem_base`, sem arredondar a referência previamente ao tipo de destino.
- A mesma preservação numérica vale para coordenadas e campos de solo, embora somá-los não tenha significado de indicador agrícola.
- Colunas totalmente nulas continuam com soma NULL; não substituir NULL por zero para validar.
- Valores numéricos individuais devem ser preservados, evitando que perdas se compensem na soma.
- Os IDs permanecem VARCHAR.
- Os conjuntos de `amostra_id` de x1 e y1 coincidem; nenhuma associação depende da ordem de retorno de um SELECT sem ORDER BY.
- Executar a transformação duas vezes sobre a mesma raw produz o mesmo conteúdo e as mesmas mensagens. Não exigir ordem física de armazenamento das linhas.
- Reexecutar a ingestão dos mesmos arquivos produz o mesmo conteúdo raw e os mesmos IDs técnicos.
- A transformação não escreve em raw; a ingestão não escreve em refined.
- Erros de conversão e conflitos de chave interrompem o comando com código 1.

## 11. Saída da transformação

Usar stdout em UTF-8 e contagens com ponto como separador de milhar. Processar e imprimir na ordem: agroclimatology, produtividade_soja, x1, y1.

Uma linha por tabela, seguida pelas contagens de nulos de suas colunas com nulos, na ordem do mapa. Se não houver nulos, escrever `nulos mantidos: nenhum`.

Com os arquivos atuais, o resultado esperado é:

```text
refined.agroclimatology 2.294.675 -> 2.294.675 linhas (0 duplicatas)
nulos mantidos: nenhum
refined.produtividade_soja 349 -> 349 linhas (0 duplicatas)
nulos mantidos: nenhum
refined.x1 2.536 -> 2.536 linhas (0 duplicatas)
nulos mantidos: nenhum
refined.y1 2.536 -> 2.536 linhas (0 duplicatas)
nulos mantidos: nenhum
TOTAL: 2.300.096 linhas
```

As contagens devem ser calculadas na execução, nunca fixadas no código. TOTAL soma as linhas finais das quatro tabelas.

## 12. Registro da aprovação

- Aprovada a correspondência da linha N de X1 com a linha N de y1 e o uso de `amostra_id`, preservando as 2.536 amostras atuais de cada arquivo.
- Aprovados os mapas e tipos, inclusive o nome conservador `valor_anual` e a manutenção das unidades originais sem sufixos não documentados.

Esta revisão não introduz orquestração, integração externa, conversão de unidades, enriquecimento, marts, imputação ou regras agronômicas de correção.

## 13. Interface local aprovada

Em extensão ao escopo, o usuário solicitou `ui.py` na raiz e aprovou as três funções: consulta das tabelas com filtros, execução do pipeline por botões e dashboard de clima e produtividade.

- Usar Streamlit, já declarado como dependência, iniciando o servidor automaticamente com `uv run python ui.py`.
- Consultar as quatro tabelas raw/refined com filtros textuais ou de nulos, paginação e download da página exibida. Preservar a precisão decimal na consulta e no CSV.
- Executar os módulos existentes de ingestão e transformação, separadamente ou em sequência, exibindo a saída e interrompendo a sequência quando uma etapa falhar.
- Exibir clima diário por município, ano e medida; série anual da produtividade da soja do município; e produção versus produtividade de arroz por `amostra_id`.
- Manter as unidades da fonte e as lacunas de dados; não escrever resultados de gráficos no banco nem inferir relações geográficas ou temporais para X1/y1.
- Mostrar estados de banco ausente, tabelas ausentes, filtros sem registros e medidas sem valores.

### Editor SQL

Por solicitação do usuário, a interface inclui consultas SQL diretamente ao DuckDB. O editor aceita uma consulta de leitura por execução (SELECT, WITH, SHOW ou DESCRIBE), permite JOINs e agregações e mostra erros do banco. A conexão é somente leitura. A interface limita o resultado exibido a um máximo configurável de 10.000 linhas, informa quando há mais registros e permite baixar o resultado exibido em CSV com precisão decimal preservada. O editor disponibiliza os nomes e tipos das colunas de raw/refined.
