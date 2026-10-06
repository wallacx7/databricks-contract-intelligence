"""Trechos dos documentos para busca semântica: um registro por elemento lido do PDF (cláusula, título, linha).

Cada trecho leva documento, página e os identificadores do contrato, para a busca poder filtrar por contrato
e a resposta do agente poder citar documento e página.
"""

from comum import bronze, silver, spark
from pyspark import pipelines as dp
from pyspark.sql import functions as F


@dp.materialized_view(
    name=silver("trechos"),
    comment="Trechos dos documentos com página e identificadores do contrato, origem do índice de busca.",
)
def trechos():
    lidos = (
        spark.read.table(bronze("documentos_lidos"))
        .where("erro_leitura IS NULL")
        .withColumn("_n", F.expr("row_number() OVER (PARTITION BY documento_id ORDER BY lido_em DESC)"))
        .where("_n = 1")
    )
    # O texto tem "[página N] " antes de cada elemento; funções literais evitam escapar colchetes em regex.
    elementos = lidos.select(
        "documento_id",
        F.posexplode(F.expr("split(replace(texto, '[página ', '§§'), '§§')")).alias("ordem", "bruto"),
    ).where("length(trim(bruto)) > 0")
    trechos = elementos.select(
        "documento_id",
        "ordem",
        F.expr("try_cast(substring_index(bruto, ']', 1) AS INT)").alias("pagina"),
        F.expr("trim(substr(bruto, instr(bruto, ']') + 1))").alias("texto"),
    ).where("length(texto) >= 20")  # títulos soltos e linhas de assinatura não ajudam a busca

    ids = (
        spark.read.table(silver("campos"))
        .groupBy("documento_id")
        .agg(
            F.max(F.when(F.col("campo") == "contrato_id", F.upper("valor"))).alias("contrato_id"),
            F.max(F.when(F.col("campo") == "cliente", F.col("valor"))).alias("cliente"),
            F.max(F.when(F.col("campo") == "tipo_documento", F.col("valor"))).alias("tipo_documento"),
        )
    )
    return trechos.join(ids, "documento_id").select(
        F.sha2(F.concat_ws("|", "documento_id", "ordem"), 256).alias("trecho_id"),
        "documento_id",
        "contrato_id",
        "cliente",
        "tipo_documento",
        "pagina",
        "ordem",
        "texto",
    )
