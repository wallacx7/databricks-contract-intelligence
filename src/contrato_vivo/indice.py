"""Cria (se preciso) e sincroniza o índice do Vector Search sobre os trechos dos contratos.

Uso (tarefa do job diário):
    contrato-vivo-indice --tabela workspace.<gold>.trechos_indice --endpoint contrato-vivo
"""

from __future__ import annotations

import argparse
import time

MODELO_DE_EMBEDDING = "databricks-gte-large-en"
DIMENSAO = 1024


def nome_do_indice(tabela: str) -> str:
    return f"{tabela}_vs"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--tabela", required=True, help="Tabela Delta de origem (com Change Data Feed).")
    parser.add_argument("--endpoint", default="contrato-vivo")
    args = parser.parse_args(argv)

    from databricks.sdk import WorkspaceClient
    from databricks.sdk.service.vectorsearch import (
        DeltaSyncVectorIndexSpecRequest,
        EmbeddingVectorColumn,
        PipelineType,
        VectorIndexType,
    )

    w = WorkspaceClient()
    indice = nome_do_indice(args.tabela)
    existentes = {i.name for i in w.vector_search_indexes.list_indexes(args.endpoint)}
    if indice not in existentes:
        w.vector_search_indexes.create_index(
            name=indice,
            endpoint_name=args.endpoint,
            primary_key="trecho_id",
            index_type=VectorIndexType.DELTA_SYNC,
            delta_sync_index_spec=DeltaSyncVectorIndexSpecRequest(
                source_table=args.tabela,
                pipeline_type=PipelineType.TRIGGERED,
                # Vetores calculados em lote na tabela de origem (atualizar_trechos.sql); o índice só armazena.
                embedding_vector_columns=[EmbeddingVectorColumn(name="embedding", embedding_dimension=DIMENSAO)],
                columns_to_sync=[
                    "trecho_id",
                    "documento_id",
                    "contrato_id",
                    "cliente",
                    "tipo_documento",
                    "pagina",
                    "texto",
                    "embedding",
                ],  # fmt: skip
            ),
        )
        print(f"Índice criado: {indice}")
    else:
        estado = w.vector_search_indexes.get_index(indice).status
        if estado and estado.ready:
            try:
                w.vector_search_indexes.sync_index(indice)
                print(f"Sincronização disparada: {indice}")
            except Exception as exc:  # uma sincronização anterior ainda em andamento: só espera ela terminar
                if "not ready to sync" not in str(exc):
                    raise
                print(f"Sincronização anterior em andamento: {indice}")
        else:
            print(f"Índice ainda inicializando, aguardando: {indice}")

    for _ in range(90):  # espera ficar pronto (até 15 minutos)
        estado = w.vector_search_indexes.get_index(indice).status
        if estado and estado.ready:
            print(f"Pronto: {estado.indexed_row_count} trechos indexados.")
            return
        time.sleep(10)
    raise TimeoutError(f"O índice {indice} não ficou pronto a tempo.")


if __name__ == "__main__":
    main()
