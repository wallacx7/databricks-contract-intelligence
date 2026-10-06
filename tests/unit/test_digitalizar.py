from __future__ import annotations

import io
from collections import Counter
from datetime import date

import pytest
from ledger.simulator import SimulationConfig, simulate
from pypdf import PdfReader

from contrato_vivo.gerador.digitalizar import PROBABILIDADE, digitalizar, sortear_nivel
from contrato_vivo.gerador.fontes import de_simulador
from contrato_vivo.gerador.pdf import renderizar
from contrato_vivo.gerador.termos import gerar


@pytest.fixture(scope="module")
def documento():
    contas, versoes = de_simulador(simulate(SimulationConfig(start=date(2025, 1, 1), end=date(2026, 9, 30), seed=2)))
    return next(d for d in gerar(contas, versoes, date(2026, 9, 1)).documentos if d.tipo == "contrato")


@pytest.mark.parametrize("nivel", ["leve", "medio", "forte"])
def test_digitalizado_mantem_paginas_e_perde_a_camada_de_texto(documento, nivel):
    original = renderizar(documento)
    escaneado = digitalizar(original, nivel, documento.documento_id)
    paginas_original = PdfReader(io.BytesIO(original)).pages
    paginas_escaneado = PdfReader(io.BytesIO(escaneado)).pages
    assert len(paginas_escaneado) == len(paginas_original)
    assert all(not (p.extract_text() or "").strip() for p in paginas_escaneado)


def test_digitalizacao_e_deterministica(documento):
    original = renderizar(documento)
    assert digitalizar(original, "medio", "x") == digitalizar(original, "medio", "x")


def test_sorteio_estavel_e_na_proporcao_esperada():
    ids = [f"CT-2024-{n:06d}" for n in range(4000)]
    niveis = [sortear_nivel(i) for i in ids]
    assert niveis == [sortear_nivel(i) for i in ids]
    proporcao = sum(n is not None for n in niveis) / len(ids)
    assert abs(proporcao - PROBABILIDADE) < 0.02
    contagem = Counter(n for n in niveis if n)
    assert contagem["leve"] > contagem["medio"] > contagem["forte"] > 0
