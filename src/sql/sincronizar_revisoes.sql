-- Traz as decisões dos revisores do Lakebase (Postgres, lido pelo catálogo do Unity Catalog) para o Delta.
-- O pipeline usa a tabela Delta para calcular os campos finais. Parâmetros: :catalog, :silver_schema, :catalogo_revisao

CREATE TABLE IF NOT EXISTS IDENTIFIER(:catalog || '.' || :silver_schema || '.revisoes') (
  item_id STRING,
  documento_id STRING,
  campo STRING,
  motivo STRING,
  valor_sugerido STRING,
  decisao STRING,
  valor_corrigido STRING,
  revisor STRING,
  decidido_em TIMESTAMP
)
COMMENT 'Decisões da revisão humana, copiadas do Lakebase. Uma linha por item revisado.';

MERGE INTO IDENTIFIER(:catalog || '.' || :silver_schema || '.revisoes') AS destino
USING IDENTIFIER(:catalogo_revisao || '.revisao.decisoes') AS origem
ON destino.item_id = origem.item_id
WHEN MATCHED AND origem.decidido_em > destino.decidido_em THEN UPDATE SET *
WHEN NOT MATCHED THEN INSERT *;
