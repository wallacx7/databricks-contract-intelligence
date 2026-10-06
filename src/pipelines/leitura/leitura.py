"""Pipeline de leitura: PDF → texto por página → extração com dois modelos → campos com confiança.

Tudo que chama modelo é streaming table: cada documento novo é lido e extraído uma única vez, e o
reprocessamento não gasta tokens de novo. A comparação entre os modelos é uma materialized view, barata.
"""

from comum import MODELOS, ORIGEM, _no_texto, _normalizado, _pagina, bronze, silver, spark
from esquema import CAMPOS, FORMATOS, INSTRUCOES, json_schema, struct_ddl
from pyspark import pipelines as dp
from pyspark.sql import functions as F

# --------------------------------------------------------------------------------- bronze


@dp.table(name=bronze("documentos"), comment="PDFs dos contratos e aditivos, como chegaram.")
def documentos():
    return (
        spark.readStream.format("cloudFiles")
        .option("cloudFiles.format", "binaryFile")
        .option("pathGlobFilter", "*.pdf")
        .option("recursiveFileLookup", "true")
        .load(ORIGEM)
        .where(~F.col("path").contains("/_"))  # pastas de teste, como _viabilidade
        .select(
            F.regexp_extract("path", r"([^/]+)\.pdf$", 1).alias("documento_id"),
            "path",
            "length",
            "modificationTime",
            "content",
            F.current_timestamp().alias("_ingested_at"),
        )
    )


@dp.table(
    name=bronze("documentos_lidos"),
    comment="Texto de cada documento, com marcação de página, extraído por ai_parse_document.",
)
@dp.expect("leitura_sem_erro", "erro_leitura IS NULL")
@dp.expect("tem_paginas", "paginas > 0")
def documentos_lidos():
    elementos = "CAST(parsed:document:elements AS ARRAY<VARIANT>)"
    texto = (
        f"concat_ws('\\n', transform({elementos}, "
        "e -> concat('[página ', CAST(e:bbox[0]:page_id AS INT) + 1, '] ', CAST(e:content AS STRING))))"
    )
    return (
        spark.readStream.table(bronze("documentos"))
        .select("documento_id", "path", F.expr("ai_parse_document(content)").alias("parsed"))
        .select(
            "documento_id",
            "path",
            F.expr("size(CAST(parsed:document:pages AS ARRAY<VARIANT>))").alias("paginas"),
            F.expr(texto).alias("texto"),
            F.expr("CAST(parsed:error_status AS STRING)").alias("erro_leitura"),
            F.current_timestamp().alias("lido_em"),
        )
    )


# --------------------------------------------------------------------------------- silver

dp.create_streaming_table(
    name=silver("extracoes"),
    comment="Resposta de cada modelo para cada documento: os campos extraídos e eventuais erros.",
)

_SCHEMA = json_schema().replace("'", "\\'")
_PROMPT = INSTRUCOES.replace("'", "\\'")


def _fluxo_de_extracao(modelo: str) -> None:
    @dp.append_flow(target=silver("extracoes"), name=f"extracao_{modelo.replace('-', '_')}")
    def _extrair():
        chamada = (
            f"ai_query('{modelo}', concat('{_PROMPT}', texto), responseFormat => '{_SCHEMA}', failOnError => false)"
        )
        return (
            spark.readStream.table(bronze("documentos_lidos"))
            .where("erro_leitura IS NULL")
            .select("documento_id", F.lit(modelo).alias("modelo"), F.expr(chamada).alias("r"))
            .select(
                "documento_id",
                "modelo",
                F.col("r.result").alias("resposta"),
                F.col("r.errorMessage").alias("erro"),
                F.from_json("r.result", struct_ddl()).alias("campos"),
                F.current_timestamp().alias("extraido_em"),
            )
        )


for _modelo in MODELOS:
    _fluxo_de_extracao(_modelo)


@dp.materialized_view(
    name=silver("campos"),
    comment=(
        "Um registro por documento e campo, com o valor de cada modelo, concordância, ancoragem no texto e "
        "confiança. Confiança alta: os modelos concordam, números aparecem escritos no documento e identificadores "
        "têm formato válido e coerente entre si."
    ),
)
def campos():
    principal, segundo = MODELOS[0], MODELOS[1]
    ext = (
        spark.read.table(silver("extracoes"))
        .where("erro IS NULL")
        .withColumn("_n", F.expr("row_number() OVER (PARTITION BY documento_id, modelo ORDER BY extraido_em DESC)"))
        .where("_n = 1")
    )
    a = ext.where(F.col("modelo") == principal).alias("a")
    b = ext.where(F.col("modelo") == segundo).alias("b")
    # Um documento reprocessado tem mais de uma leitura; vale a bem-sucedida mais recente.
    lidos = (
        spark.read.table(bronze("documentos_lidos"))
        .where("erro_leitura IS NULL")
        .withColumn("_n", F.expr("row_number() OVER (PARTITION BY documento_id ORDER BY lido_em DESC)"))
        .where("_n = 1")
        .select("documento_id", "texto")
        .alias("t")
    )
    base = (
        a.join(b, "documento_id", "left")
        .join(lidos, "documento_id")
        # Convenção do sistema de contratos: o número do contrato termina com os dígitos do código do cliente.
        .withColumn(
            "ids_coerentes",
            F.expr(
                "regexp_extract(lower(a.campos.contrato_id), '([0-9]{6})$', 1) "
                "<=> regexp_extract(lower(a.campos.codigo_cliente), '([0-9]{6})$', 1)"
            ),
        )
    )

    linhas = []
    for campo, (_, tipo) in CAMPOS.items():
        va, vb = f"a.campos.{campo}", f"b.campos.{campo}"
        linhas.append(
            base.select(
                "documento_id",
                F.lit(campo).alias("campo"),
                F.lit(tipo).alias("tipo"),
                F.expr(_normalizado(va, tipo)).alias("valor"),
                F.expr(_normalizado(vb, tipo)).alias("valor_segundo_modelo"),
                F.expr(f"{_no_texto(va, tipo)}").alias("ancorado"),
                F.expr(_valido(campo, va)).alias("valido"),
                F.expr(_pagina(va, tipo)).alias("pagina"),
            )
        )
    todos = linhas[0]
    for df in linhas[1:]:
        todos = todos.unionByName(df)
    concordam = F.expr("valor <=> valor_segundo_modelo")
    ancorado_ok = F.col("ancorado").isNull() | F.col("ancorado") | F.col("valor").isNull()
    valido_ok = F.col("valido").isNull() | F.col("valido")
    return todos.withColumn("concordam", concordam).withColumn(
        "confianca", F.when(concordam & ancorado_ok & valido_ok, "alta").otherwise("baixa")
    )


def _valido(campo: str, coluna: str) -> str:
    """Formato e coerência de identificadores; NULL para campos sem regra.

    Os dois modelos leem o mesmo texto do OCR: se a leitura perde um caractere, eles concordam no erro.
    A validação não depende da leitura e pega esse caso.
    """
    if campo not in FORMATOS:
        return "NULL"
    return f"(lower({coluna}) RLIKE '{FORMATOS[campo]}' AND ids_coerentes)"
