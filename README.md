# Clima Paraná

Pipeline local em Python 3.14, uv e DuckDB. O contrato está em [SPEC.md](SPEC.md).

## Executar

Na raiz do projeto, com os quatro CSVs na pasta `raw/`:

```shell
uv sync
uv run python -m pipeline.ingestao
uv run python -m pipeline.transformacao
```

O banco `agro.duckdb` fica na raiz do projeto. A ingestão recria as quatro tabelas raw, mantendo as colunas originais como VARCHAR e convertendo campos vazios em NULL. A transformação recria as quatro tabelas refined, aplica os mapas aprovados e verifica contagens, nulos e somas.

X1/y1 recebem `amostra_id` pela posição do registro no CSV. Valores iguais em amostras diferentes permanecem presentes. Os arquivos devem ter a mesma quantidade de registros e manter sua correspondência posicional.

Conversões inválidas, arredondamento decimal, estruturas inesperadas e conflitos de chave interrompem o comando com código 1. Cada etapa grava em uma transação: uma falha desfaz as alterações daquela execução. Os comandos mostram mensagens de sucesso somente após a confirmação da carga.

Reexecutar com as mesmas entradas substitui as tabelas e produz o mesmo resultado. A transformação não modifica raw; a ingestão não modifica refined nem os CSVs.

## Interface local

```shell
uv run python ui.py
```

A interface oferece gráficos de clima diário, produtividade anual da soja e amostras de arroz; consulta paginada das tabelas raw/refined, com filtros e download da página; e execução da ingestão, transformação ou das duas etapas. As consultas fecham a conexão após a leitura, permitindo executar o pipeline pelos botões.

Os gráficos mantêm as unidades originais da fonte, sem inferir unidades ainda não documentadas. O ano selecionado filtra somente o clima; o gráfico da soja mostra sua série histórica completa. Dados nulos não são preenchidos. A consulta de tabelas e o CSV preservam a representação decimal exata.

Em **Consultas SQL**, escreva uma consulta e clique em **Executar consulta**. O editor aceita SELECT, WITH, SHOW e DESCRIBE, incluindo JOINs e agregações, em uma conexão somente leitura. O catálogo de tabelas e colunas fica disponível abaixo do editor. O limite de exibição é configurável até 10.000 linhas e o download contém somente o resultado exibido, preservando os decimais.

```sql
SELECT codigo_ibge, COUNT(*) AS medicoes
FROM refined.agroclimatology
GROUP BY codigo_ibge
ORDER BY medicoes DESC;
```

## Verificar

```shell
uv run ruff check .
uv run ruff format --check .
uv run python -m pytest --cov=pipeline --cov=ui --cov-report=term-missing --cov-fail-under=50
```

Os testes usam CSVs pequenos e bancos temporários ou em memória; não alteram o banco de produção. Cobrem preservação de precisão, nulos, duplicatas, falhas, identidade das amostras e reexecução.
