from datetime import date

import pytest

from contrato_vivo.gerador.extenso import data_longa, percentual, por_extenso, reais, reais_por_extenso


@pytest.mark.parametrize(
    "n, esperado",
    [
        (0, "zero"),
        (16, "dezesseis"),
        (21, "vinte e um"),
        (100, "cem"),
        (101, "cento e um"),
        (120, "cento e vinte"),
        (1000, "mil"),
        (1500, "mil e quinhentos"),
        (12500, "doze mil e quinhentos"),
        (2023, "dois mil e vinte e três"),
        (1234, "mil duzentos e trinta e quatro"),
        (1_000_000, "um milhão"),
        (2_500_000, "dois milhões e quinhentos mil"),
    ],
)
def test_por_extenso(n, esperado):
    assert por_extenso(n) == esperado


def test_valores_em_reais():
    assert reais(12500) == "R$ 12.500,00"
    assert reais(1234567.8) == "R$ 1.234.567,80"
    assert reais_por_extenso(12500) == "doze mil e quinhentos reais"
    assert reais_por_extenso(110.5) == "cento e dez reais e cinquenta centavos"
    assert reais_por_extenso(1) == "um real"


def test_percentual_e_datas():
    assert percentual(15) == "15%"
    assert percentual(7.5) == "7,5%"
    assert data_longa(date(2024, 3, 1)) == "1º de março de 2024"
    assert data_longa(date(2025, 12, 31)) == "31 de dezembro de 2025"
