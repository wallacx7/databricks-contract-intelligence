"""Leitura do billing do Ledger: pelas tabelas Silver no workspace ou pelo simulador local (testes)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from contrato_vivo.gerador.termos import Conta, Versao


def de_tabelas(spark: Any, catalog: str, schema: str) -> tuple[list[Conta], list[Versao]]:
    """Lê silver.accounts (versão vigente) e silver.subscriptions (todas as versões) do Ledger."""
    contas = [
        Conta(r.account_id, r.company_name, r.segment, r.state, r.industry)
        for r in spark.sql(
            f"SELECT account_id, company_name, segment, state, industry "
            f"FROM {catalog}.{schema}.accounts WHERE __END_AT IS NULL"
        ).collect()
    ]
    versoes = [
        Versao(
            subscription_id=r.subscription_id,
            account_id=r.account_id,
            plan_id=r.plan_id,
            seats=int(r.seats),
            unit_price=float(r.unit_price),
            billing_period=r.billing_period,
            status=r.status,
            inicio=r.inicio,
            fim=r.fim,
        )
        for r in spark.sql(
            f"SELECT subscription_id, account_id, plan_id, seats, unit_price, billing_period, status, "
            f"__START_AT.effective_at AS inicio, __END_AT.effective_at AS fim "
            f"FROM {catalog}.{schema}.subscriptions"
        ).collect()
    ]
    return contas, versoes


def de_simulador(result: Any) -> tuple[list[Conta], list[Versao]]:
    """Reconstrói contas e versões SCD2 a partir da saída do simulador do Ledger, como a Silver faria."""
    contas: dict[str, Conta] = {}
    for r in result.account_records:  # o último registro de cada conta é a versão vigente
        contas[r["account_id"]] = Conta(r["account_id"], r["company_name"], r["segment"], r["state"], r["industry"])

    eventos: dict[str, dict[str, dict]] = {}
    for e in result.subscription_events:
        if e["subscription_id"].startswith("sub_test_"):
            continue  # registros de teste do billing vão para a quarentena no Ledger
        eventos.setdefault(e["subscription_id"], {})[e["event_id"]] = e

    versoes: list[Versao] = []
    for por_id in eventos.values():
        ordenados = sorted(por_id.values(), key=lambda e: (e["effective_at"], e["sequence"]))
        for atual, seguinte in zip(ordenados, [*ordenados[1:], None], strict=True):
            versoes.append(
                Versao(
                    subscription_id=atual["subscription_id"],
                    account_id=atual["account_id"],
                    plan_id=atual["plan_id"],
                    seats=atual["seats"],
                    unit_price=atual["unit_price"],
                    billing_period=atual["billing_period"],
                    status=atual["status"],
                    inicio=datetime.fromisoformat(atual["effective_at"]),
                    fim=datetime.fromisoformat(seguinte["effective_at"]) if seguinte else None,
                )
            )
    return list(contas.values()), versoes
