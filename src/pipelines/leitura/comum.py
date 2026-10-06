"""Configuração e expressões compartilhadas pelos arquivos do pipeline (sem definir tabelas).

Arquivos do pipeline não devem importar uns aos outros: importar um arquivo que define tabelas faria
o pipeline registrá-las duas vezes.
"""

from pyspark.sql import SparkSession

spark = SparkSession.getActiveSession()

CATALOG = spark.conf.get("contrato_vivo.catalog")
RAW = spark.conf.get("contrato_vivo.raw_schema")
BRONZE = spark.conf.get("contrato_vivo.bronze_schema")
SILVER = spark.conf.get("contrato_vivo.silver_schema")
ORIGEM = spark.conf.get("contrato_vivo.contratos_path")
GABARITO = spark.conf.get("contrato_vivo.gabarito_path")
MODELOS = [m.strip() for m in spark.conf.get("contrato_vivo.modelos").split(",")]


def bronze(nome: str) -> str:
    return f"{CATALOG}.{BRONZE}.{nome}"


def silver(nome: str) -> str:
    return f"{CATALOG}.{SILVER}.{nome}"


def _normalizado(coluna: str, tipo: str) -> str:
    """Expressão SQL que transforma o valor num texto comparável entre modelos e com o gabarito."""
    if tipo == "dinheiro":
        return f"format_number(round({coluna}, 2), '0.00')"
    if tipo == "percentual":
        return f"CAST(round({coluna}, 2) AS STRING)"
    if tipo == "inteiro":
        return f"CAST(CAST({coluna} AS INT) AS STRING)"
    if tipo == "data":
        return f"CAST(try_to_date({coluna}) AS STRING)"
    return f"lower(trim({coluna}))"


# A leitura do PDF pode quebrar a linha no meio de um valor ("R$" numa linha, "49,00" na seguinte);
# a busca compara o texto com espaços e quebras de linha reduzidos a um espaço.
_TEXTO = "regexp_replace(texto, '\\\\s+', ' ')"


def _no_texto(coluna: str, tipo: str) -> str:
    """O valor aparece escrito no documento do jeito que contratos escrevem?"""
    if tipo == "dinheiro":
        brl = f"concat('R$ ', translate(format_number({coluna}, 2), ',.', '.,'))"
        return f"instr({_TEXTO}, {brl}) > 0"
    if tipo == "percentual":
        pct = (
            f"concat(regexp_replace(regexp_replace(translate(format_number({coluna}, 2), ',.', '.,'), "
            f"'0+$', ''), ',$', ''), '%')"
        )
        return f"instr({_TEXTO}, {pct}) > 0"
    if tipo == "inteiro":
        return (
            f"(instr({_TEXTO}, concat(CAST({coluna} AS INT), ' (')) > 0 OR instr({_TEXTO}, CAST({coluna} AS INT)) > 0)"
        )
    return "NULL"
