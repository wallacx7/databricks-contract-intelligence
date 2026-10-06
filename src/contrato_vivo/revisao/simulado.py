"""Revisor simulado: decide itens da fila usando o gabarito, para demonstrar o fluxo de ponta a ponta.

Existe só porque o ambiente é simulado. Aprova o que está certo e corrige o que está errado, gravando as
decisões no Lakebase como `revisor-simulado`. Deixa alguns itens pendentes para revisão na App.

Uso:
    contrato-vivo-revisor-simulado --catalog workspace --silver-schema <schema> --warehouse-id <id> --deixar 10
"""

from __future__ import annotations

import argparse
from collections import Counter

from contrato_vivo.revisao import banco

REVISOR = "revisor-simulado"


def decidir_item(item: dict) -> tuple[str, str | None]:
    """aprovado quando o valor extraído é o esperado; senão, corrigido com o valor esperado."""
    if item["valor"] == item["esperado"]:
        return "aprovado", None
    return "corrigido", item["esperado"] if item["esperado"] is not None else "(vazio)"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--catalog", default="workspace")
    parser.add_argument("--silver-schema", required=True)
    parser.add_argument("--warehouse-id", required=True)
    parser.add_argument("--deixar", type=int, default=10, help="Quantos itens deixar pendentes para a App.")
    args = parser.parse_args(argv)

    from databricks.sdk import WorkspaceClient

    w = WorkspaceClient()
    s = f"{args.catalog}.{args.silver_schema}"
    sql = (
        f"SELECT f.item_id, f.documento_id, f.campo, f.motivo, f.valor, a.esperado "
        f"FROM {s}.fila_revisao f JOIN {s}.avaliacao_campos a USING (documento_id, campo) "
        f"ORDER BY f.motivo, f.documento_id, f.campo"
    )
    r = w.statement_execution.execute_statement(statement=sql, warehouse_id=args.warehouse_id, wait_timeout="50s")
    colunas = [c.name for c in r.manifest.schema.columns]
    itens = [dict(zip(colunas, linha, strict=True)) for linha in (r.result.data_array or [])]

    with banco.conectar() as conn:
        feitos = banco.decididos(conn)
        pendentes = [i for i in itens if i["item_id"] not in feitos]
        a_decidir = pendentes[: max(0, len(pendentes) - args.deixar)]
        resultado = Counter()
        for item in a_decidir:
            decisao, valor = decidir_item(item)
            banco.decidir(conn, item, decisao, REVISOR, valor)
            resultado[(item["motivo"], decisao)] += 1
    for (motivo, decisao), n in sorted(resultado.items()):
        print(f"{motivo:16} {decisao:10} {n}")
    print(f"{len(pendentes) - len(a_decidir)} itens deixados pendentes para a App.")


if __name__ == "__main__":
    main()
