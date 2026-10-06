-- Copia os trechos para a tabela de origem do índice do Vector Search.
-- O índice exige uma tabela Delta comum com Change Data Feed; o MERGE mantém a tabela (recriá-la quebraria
-- a sincronização). Parâmetros: :catalog, :silver_schema, :gold_schema

CREATE TABLE IF NOT EXISTS IDENTIFIER(:catalog || '.' || :gold_schema || '.trechos_indice') (
  trecho_id STRING NOT NULL,
  documento_id STRING,
  contrato_id STRING,
  cliente STRING,
  tipo_documento STRING,
  pagina INT,
  ordem INT,
  texto STRING
)
TBLPROPERTIES (delta.enableChangeDataFeed = true)
COMMENT 'Trechos dos contratos indexados no Vector Search para as perguntas com citação.';

MERGE INTO IDENTIFIER(:catalog || '.' || :gold_schema || '.trechos_indice') AS destino
USING IDENTIFIER(:catalog || '.' || :silver_schema || '.trechos') AS origem
ON destino.trecho_id = origem.trecho_id
WHEN MATCHED AND destino.texto <> origem.texto THEN UPDATE SET *
WHEN NOT MATCHED THEN INSERT *
WHEN NOT MATCHED BY SOURCE THEN DELETE;
