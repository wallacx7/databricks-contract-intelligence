"""Fila de revisão humana e campos finais (extração + decisões dos revisores)."""

from comum import CATALOG, SILVER, bronze, silver, spark
from pyspark import pipelines as dp
from pyspark.sql import functions as F

# Fração dos campos de confiança alta sorteada para auditoria: mede o acerto real sem gabarito.
AUDITORIA_PERCENTUAL = 2


@dp.materialized_view(
    name=silver("fila_revisao"),
    comment=(
        "Campos que precisam de olho humano: todos os de confiança baixa e uma amostra de auditoria de "
        f"{AUDITORIA_PERCENTUAL}% dos de confiança alta, sorteada de forma estável por documento e campo."
    ),
)
def fila_revisao():
    campos = spark.read.table(silver("campos"))
    arquivos = (
        spark.read.table(bronze("documentos_lidos"))
        .where("erro_leitura IS NULL")
        .withColumn("_n", F.expr("row_number() OVER (PARTITION BY documento_id ORDER BY lido_em DESC)"))
        .where("_n = 1")
        .select("documento_id", "path")
    )
    auditoria = F.expr(f"valor IS NOT NULL AND pmod(xxhash64(documento_id, campo), 100) < {AUDITORIA_PERCENTUAL}")
    return (
        campos.where((F.col("confianca") == "baixa") | auditoria)
        .join(arquivos, "documento_id")
        .select(
            F.sha2(F.concat_ws("|", "documento_id", "campo"), 256).alias("item_id"),
            "documento_id",
            "campo",
            "tipo",
            "valor",
            "valor_segundo_modelo",
            "pagina",
            "concordam",
            "ancorado",
            "valido",
            F.when(F.col("confianca") == "baixa", "confianca_baixa").otherwise("auditoria").alias("motivo"),
            "path",
        )
    )


@dp.materialized_view(
    name=silver("campos_finais"),
    comment="Valor final de cada campo: a decisão do revisor quando existe, senão o valor extraído.",
)
def campos_finais():
    campos = spark.read.table(silver("campos"))
    revisoes = spark.read.table(f"{CATALOG}.{SILVER}.revisoes").select(
        "documento_id", "campo", "decisao", "valor_corrigido", "revisor", "decidido_em"
    )
    return (
        campos.join(revisoes, ["documento_id", "campo"], "left")
        .withColumn(
            "valor_final", F.when(F.col("decisao") == "corrigido", F.col("valor_corrigido")).otherwise(F.col("valor"))
        )
        .withColumn(
            "origem",
            F.when(F.col("decisao").isNotNull(), "revisado")
            .when(F.col("confianca") == "alta", "automatico")
            .otherwise("pendente"),
        )
    )
