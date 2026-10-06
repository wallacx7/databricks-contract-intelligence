"""Reenvia para leitura os documentos cuja leitura falhou e nunca teve sucesso.

O `ai_parse_document` às vezes falha de forma transitória (ex.: "TimeoutException during page parsing").
Como a leitura é uma streaming table, cada arquivo é lido uma única vez: um documento que falhou ficaria
sem leitura para sempre. Esta tarefa copia o PDF para `reprocessar/<data>/`, o Auto Loader trata a cópia como
arquivo novo, e as etapas seguintes usam só a leitura bem-sucedida mais recente de cada documento.

Uso (tarefa do job diário):
    contrato-vivo-reprocessar --catalog workspace --bronze-schema <schema> --contratos /Volumes/.../contratos
"""

from __future__ import annotations

import argparse
import shutil
from datetime import datetime
from pathlib import Path

MAX_TENTATIVAS = 3


def pendentes_sql(catalog: str, bronze: str) -> str:
    return f"""
SELECT documento_id, first(path) AS path, count(*) AS tentativas
FROM {catalog}.{bronze}.documentos_lidos
GROUP BY documento_id
HAVING count_if(erro_leitura IS NULL) = 0 AND count(*) < {MAX_TENTATIVAS}
"""


def reenviar(pendentes: list[tuple[str, str]], contratos: Path, agora: datetime | None = None) -> list[Path]:
    """Copia cada PDF pendente para contratos/reprocessar/<carimbo>/; devolve os destinos."""
    pasta = contratos / "reprocessar" / (agora or datetime.now()).strftime("%Y%m%dT%H%M%S")
    destinos = []
    for documento_id, origem in pendentes:
        origem_local = Path(origem.removeprefix("dbfs:"))
        destino = pasta / f"{documento_id}.pdf"
        destino.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(origem_local, destino)
        destinos.append(destino)
    return destinos


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Reenvia documentos com leitura falha.")
    parser.add_argument("--catalog", required=True)
    parser.add_argument("--bronze-schema", required=True)
    parser.add_argument("--contratos", type=Path, required=True)
    args = parser.parse_args(argv)

    from pyspark.sql import SparkSession

    spark = SparkSession.builder.getOrCreate()
    linhas = spark.sql(pendentes_sql(args.catalog, args.bronze_schema)).collect()
    destinos = reenviar([(r.documento_id, r.path) for r in linhas], args.contratos)
    print(f"{len(destinos)} documentos reenviados para leitura." if destinos else "Nenhuma leitura pendente.")


if __name__ == "__main__":
    main()
