"""Testes do gerador de termos com o billing real do simulador do Ledger."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, timedelta

import pytest
from ledger.simulator import SimulationConfig, simulate

from contrato_vivo.gerador.fontes import de_simulador
from contrato_vivo.gerador.termos import (
    TOLERANCIA_CENTAVOS,
    aniversarios,
    fim_do_mes,
    gerar,
    meses,
    meses_completos,
    preco_devido,
    versao_em,
)

ULTIMO_MES = date(2026, 9, 1)


@pytest.fixture(scope="module")
def billing():
    # Mesmo período do Ledger, com escala menor para o teste ser rápido.
    return de_simulador(simulate(SimulationConfig(start=date(2023, 1, 1), end=date(2026, 9, 30), seed=11, scale=0.6)))


@pytest.fixture(scope="module")
def resultado(billing):
    contas, versoes = billing
    return gerar(contas, versoes, ULTIMO_MES)


@pytest.fixture(scope="module")
def versoes_por_conta(billing):
    por_conta = defaultdict(list)
    for v in billing[1]:
        por_conta[v.account_id].append(v)
    return {k: sorted(v, key=lambda x: x.inicio) for k, v in por_conta.items()}


def test_calendario():
    assert aniversarios(date(2024, 3, 1), datetime(2025, 3, 1)) == 0
    assert aniversarios(date(2024, 3, 1), datetime(2025, 3, 2)) == 1
    assert meses_completos(date(2024, 3, 10), datetime(2025, 3, 10)) == 11
    assert meses_completos(date(2024, 3, 10), datetime(2025, 3, 11)) == 12
    assert fim_do_mes(date(2025, 12, 1)) == datetime(2026, 1, 1)
    assert meses(date(2025, 11, 15), date(2026, 1, 1)) == [date(2025, 11, 1), date(2025, 12, 1), date(2026, 1, 1)]


def test_so_mid_market_e_enterprise_tem_contrato(billing, resultado):
    segmento = {c.account_id: c.segmento for c in billing[0]}
    assert {segmento[d.account_id] for d in resultado.documentos} == {"mid_market", "enterprise"}


def test_um_aditivo_por_mudanca_de_plano(resultado, versoes_por_conta):
    aditivos = Counter(d.contrato_id for d in resultado.documentos if d.tipo == "aditivo")
    for doc in (d for d in resultado.documentos if d.tipo == "contrato"):
        versoes = [v for v in versoes_por_conta[doc.account_id] if v.status == "active"]
        mudancas = sum(1 for a, b in zip(versoes, versoes[1:], strict=False) if a.plan_id != b.plan_id)
        assert aditivos[doc.contrato_id] == mudancas


def test_contrato_sem_vazamento_plantado_cobra_exatamente_o_devido(resultado, versoes_por_conta):
    """A regra de preço precisa reproduzir o billing em todo mês; se não, o 'vazamento' seria erro do gerador."""
    por_contrato = defaultdict(list)
    for d in resultado.documentos:
        por_contrato[d.contrato_id].append(d)
    verificados = 0
    for docs in por_contrato.values():
        base = docs[0]
        if base.vazamento_plantado:
            continue
        versoes = versoes_por_conta[base.account_id]
        for mes in meses(base.inicio_vigencia, ULTIMO_MES):
            momento = fim_do_mes(mes)
            v = versao_em(versoes, momento)
            if v is None or v.status != "active":
                continue
            vigente = [d for d in docs if datetime.combine(d.inicio_vigencia, datetime.min.time()) < momento][-1]
            assert abs(preco_devido(base, vigente, v.plan_id, momento) - v.unit_price) <= TOLERANCIA_CENTAVOS
            verificados += 1
    assert verificados > 1000


def test_vazamentos_plantados_aparecem_e_so_onde_deveriam(resultado):
    plantados = {d.contrato_id: d.vazamento_plantado for d in resultado.documentos if d.tipo == "contrato"}
    com_minimo = {d.contrato_id for d in resultado.documentos if d.tipo == "contrato" and d.minimo_usuarios}
    tipos = Counter(v.tipo for v in resultado.vazamentos)
    assert set(tipos) == {"desconto_vencido", "preco_abaixo", "reajuste_nao_aplicado", "minimo_nao_cobrado"}
    for v in resultado.vazamentos:
        assert v.vazamento > 0
        if v.tipo == "minimo_nao_cobrado":
            assert v.contrato_id in com_minimo and v.usuarios_ativos < v.usuarios_devidos
        else:
            assert plantados[v.contrato_id] == v.tipo


def test_desconto_vencido_so_vaza_depois_do_prazo(resultado):
    inicio = {d.contrato_id: d.inicio_vigencia for d in resultado.documentos if d.tipo == "contrato"}
    for v in resultado.vazamentos:
        if v.tipo == "desconto_vencido":
            fim_desconto = date(inicio[v.contrato_id].year + 1, inicio[v.contrato_id].month, 1)
            assert v.mes >= fim_desconto


def test_geracao_estavel_por_conta(billing):
    """Gerar um subconjunto não muda os termos das contas incluídas."""
    contas, versoes = billing
    todos = {d.documento_id: d for d in gerar(contas, versoes, ULTIMO_MES).documentos}
    parte = gerar(contas, versoes, ULTIMO_MES, limite=20).documentos
    assert parte and all(todos[d.documento_id] == d for d in parte)


def test_fim_de_vigencia_e_a_vespera_do_aniversario(resultado):
    from contrato_vivo.gerador.termos import adicionar_meses

    assert adicionar_meses(date(2024, 1, 31), 1) == date(2024, 2, 29)
    for d in (d for d in resultado.documentos if d.tipo == "contrato"):
        duracao = 36 if d.fim_vigencia.year - d.inicio_vigencia.year >= 3 else 24
        assert d.fim_vigencia == adicionar_meses(d.inicio_vigencia, duracao) - timedelta(days=1)


def test_gabarito_do_aditivo_so_tem_o_que_esta_escrito_nele(resultado):
    aditivo = next(d for d in resultado.documentos if d.tipo == "aditivo")
    campos = aditivo.campos_esperados()
    assert campos["preco_usuario"] == aditivo.preco_usuario and campos["plano"] == aditivo.plano
    assert all(campos[c] is None for c in aditivo.CAMPOS_FORA_DO_ADITIVO)
