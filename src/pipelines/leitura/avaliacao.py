"""Avaliação da extração contra o gabarito do gerador.

Existe porque os contratos são simulados e o valor certo de cada campo é conhecido. Numa empresa, o papel
do gabarito seria de uma amostra revisada por pessoas; a estrutura da avaliação seria a mesma.
"""

from comum import CATALOG, GABARITO, RAW, _normalizado, silver, spark
from esquema import CAMPOS
from pyspark import pipelines as dp
from pyspark.sql import functions as F

# O gabarito chama de "tipo" o que a extração chama de "tipo_documento".
_NOME_NO_GABARITO = {"tipo_documento": "tipo"}


@dp.materialized_view(
    name=silver("avaliacao_campos"),
    comment="Cada campo extraído comparado com o valor correto do gabarito. Só existe no ambiente simulado.",
)
def avaliacao_campos():
    gabarito = spark.read.json(f"{GABARITO}/documentos.jsonl")
    esperados = None
    for campo, (_, tipo) in CAMPOS.items():
        coluna = _NOME_NO_GABARITO.get(campo, campo)
        df = gabarito.select(
            "documento_id",
            "modelo",
            F.coalesce("digitalizado", F.lit("digital")).alias("digitalizacao"),
            F.lit(campo).alias("campo"),
            F.expr(_normalizado(f"`{coluna}`", tipo)).alias("esperado"),
        )
        esperados = df if esperados is None else esperados.unionByName(df)

    extraidos = spark.read.table(silver("campos"))
    # Documentos usados para ajustar prompt e regras: o acerto neles não vale como medida final.
    desenvolvimento = spark.read.table(f"{CATALOG}.{RAW}.conjunto_desenvolvimento").withColumn("_dev", F.lit(True))
    return (
        esperados.withColumnRenamed("modelo", "modelo_do_pdf")
        .join(extraidos, ["documento_id", "campo"])
        .join(desenvolvimento, "documento_id", "left")
        .withColumn("conjunto", F.when(F.col("_dev"), "desenvolvimento").otherwise("controle"))
        .drop("_dev")
        .withColumn("correto", F.expr("valor <=> esperado"))
    )
