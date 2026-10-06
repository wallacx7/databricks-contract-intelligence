-- Copia os trechos para a tabela de origem do índice do Vector Search, com o embedding de cada trecho.
--
-- Os embeddings são calculados aqui, em lote, com ai_query, e só para trechos novos ou com texto alterado.
-- No modo gerenciado o índice calcularia um a um pelo endpoint (cerca de 30 por minuto no Free Edition);
-- em lote são cerca de 500 a cada 10 segundos. Parâmetros: :catalog, :silver_schema, :gold_schema, :modelo_embedding

CREATE TABLE IF NOT EXISTS IDENTIFIER(:catalog || '.' || :gold_schema || '.trechos_indice') (
  trecho_id STRING NOT NULL,
  documento_id STRING,
  contrato_id STRING,
  cliente STRING,
  tipo_documento STRING,
  pagina INT,
  ordem INT,
  texto STRING,
  embedding ARRAY<FLOAT>
)
TBLPROPERTIES (delta.enableChangeDataFeed = true)
COMMENT 'Trechos dos contratos com embeddings, origem do índice do Vector Search para as perguntas com citação.';

MERGE INTO IDENTIFIER(:catalog || '.' || :gold_schema || '.trechos_indice') AS destino
USING (
  SELECT
    o.trecho_id, o.documento_id, o.contrato_id, o.cliente, o.tipo_documento, o.pagina, o.ordem, o.texto,
    CAST(ai_query(:modelo_embedding, o.texto) AS ARRAY<FLOAT>) AS embedding
  FROM IDENTIFIER(:catalog || '.' || :silver_schema || '.trechos') AS o
  LEFT JOIN IDENTIFIER(:catalog || '.' || :gold_schema || '.trechos_indice') AS atual
    ON atual.trecho_id = o.trecho_id AND atual.texto = o.texto
  WHERE atual.trecho_id IS NULL
) AS origem
ON destino.trecho_id = origem.trecho_id
WHEN MATCHED THEN UPDATE SET *
WHEN NOT MATCHED THEN INSERT *;

DELETE FROM IDENTIFIER(:catalog || '.' || :gold_schema || '.trechos_indice')
WHERE trecho_id NOT IN (SELECT trecho_id FROM IDENTIFIER(:catalog || '.' || :silver_schema || '.trechos'));
