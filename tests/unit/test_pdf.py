from __future__ import annotations

import io
import re
from collections import Counter
from datetime import date

import pytest
from ledger.simulator import SimulationConfig, simulate
from pypdf import PdfReader

from contrato_vivo.gerador.extenso import reais
from contrato_vivo.gerador.fontes import de_simulador
from contrato_vivo.gerador.pdf import renderizar
from contrato_vivo.gerador.termos import gerar


@pytest.fixture(scope="module")
def documentos():
    contas, versoes = de_simulador(simulate(SimulationConfig(start=date(2024, 1, 1), end=date(2026, 9, 30), seed=5)))
    return gerar(contas, versoes, date(2026, 9, 1)).documentos


def _texto(doc) -> str:
    return "\n".join(p.extract_text() for p in PdfReader(io.BytesIO(renderizar(doc))).pages).replace("\n", " ")


@pytest.mark.parametrize("modelo", [0, 1, 2, 3])
def test_modelo_de_contrato_tem_os_termos_e_numeracao_sequencial(documentos, modelo):
    doc = next(d for d in documentos if d.tipo == "contrato" and d.modelo == modelo)
    texto = _texto(doc)
    for esperado in (doc.contrato_id, doc.codigo_cliente, reais(doc.preco_usuario), doc.plano):
        assert esperado in texto, esperado
    rotulos = re.findall(r"(?:CLÁUSULA (\d+)|SEÇÃO ([IVX]+)) – ([^\d]+?)(?= \d+\.\d| [A-Z][a-z])", texto)
    numeros = [a or b for a, b, _ in rotulos]
    assert numeros[:3] in (["1", "2", "3"], ["I", "II", "III"])
    titulos = Counter(re.findall(r"(?:CLÁUSULA \d+|SEÇÃO [IVX]+) – ([A-ZÁÉÍÓÚÇÃÕ ]+)", texto))
    assert all(n == 1 for n in titulos.values()), titulos


def test_clausulas_de_vazamento_aparecem_no_texto(documentos):
    contratos = [d for d in documentos if d.tipo == "contrato"]
    promo = next(d for d in contratos if d.desconto_promocional_percentual)
    assert "desconto promocional" in _texto(promo)
    fixo = next(d for d in contratos if d.reajuste_tipo == "fixo")
    assert "reajustado anualmente" in _texto(fixo)
    minimo = next(d for d in contratos if d.minimo_usuarios)
    assert "faturamento mínimo" in _texto(minimo)
    anual = next(d for d in contratos if d.periodicidade == "anual")
    assert "pagamento será anual" in _texto(anual)


def test_aditivo_referencia_o_contrato_e_traz_o_novo_preco(documentos):
    aditivo = next(d for d in documentos if d.tipo == "aditivo")
    texto = _texto(aditivo)
    assert f"ADITIVO AO CONTRATO Nº {aditivo.contrato_id}" in texto
    assert reais(aditivo.preco_usuario) in texto and aditivo.plano in texto
