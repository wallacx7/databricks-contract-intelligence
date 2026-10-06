"""Números, valores e datas escritos como em contratos brasileiros."""

from __future__ import annotations

from datetime import date

_UNIDADES = ["zero", "um", "dois", "três", "quatro", "cinco", "seis", "sete", "oito", "nove", "dez", "onze", "doze",
             "treze", "quatorze", "quinze", "dezesseis", "dezessete", "dezoito", "dezenove"]  # fmt: skip
_DEZENAS = ["", "", "vinte", "trinta", "quarenta", "cinquenta", "sessenta", "setenta", "oitenta", "noventa"]
_CENTENAS = ["", "cento", "duzentos", "trezentos", "quatrocentos", "quinhentos", "seiscentos", "setecentos",
             "oitocentos", "novecentos"]  # fmt: skip
MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro",
         "novembro", "dezembro"]  # fmt: skip


def _ate_mil(n: int) -> str:
    if n < 20:
        return _UNIDADES[n]
    if n < 100:
        d, u = divmod(n, 10)
        return _DEZENAS[d] + (f" e {_UNIDADES[u]}" if u else "")
    if n == 100:
        return "cem"
    c, resto = divmod(n, 100)
    return _CENTENAS[c] + (f" e {_ate_mil(resto)}" if resto else "")


def por_extenso(n: int) -> str:
    """Inteiro de 0 a 999.999.999 por extenso."""
    if not 0 <= n < 1_000_000_000:
        raise ValueError(n)
    if n < 1000:
        return _ate_mil(n)
    grupos: list[tuple[int, str]] = []
    milhoes, resto = divmod(n, 1_000_000)
    milhares, unidades = divmod(resto, 1000)
    if milhoes:
        grupos.append((milhoes, _ate_mil(milhoes) + (" milhão" if milhoes == 1 else " milhões")))
    if milhares:
        grupos.append((milhares, "mil" if milhares == 1 else _ate_mil(milhares) + " mil"))
    if unidades:
        grupos.append((unidades, _ate_mil(unidades)))
    if len(grupos) == 1:
        return grupos[0][1]
    # "e" antes do último grupo quando ele é menor que cem ou é centena redonda
    valor_ultimo, texto_ultimo = grupos[-1]
    ligacao = " e " if valor_ultimo < 100 or valor_ultimo % 100 == 0 else " "
    return " ".join(t for _, t in grupos[:-1]) + ligacao + texto_ultimo


def reais(valor: float) -> str:
    """R$ 12.500,00"""
    texto = f"{valor:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return f"R$ {texto}"


def reais_por_extenso(valor: float) -> str:
    """doze mil e quinhentos reais e trinta centavos"""
    centavos_total = round(valor * 100)
    inteiro, centavos = divmod(centavos_total, 100)
    partes = []
    if inteiro:
        sufixo = "real" if inteiro == 1 else "reais"
        if inteiro >= 1_000_000 and inteiro % 1_000_000 == 0:
            sufixo = "de reais"
        partes.append(f"{por_extenso(inteiro)} {sufixo}")
    if centavos:
        partes.append(f"{por_extenso(centavos)} {'centavo' if centavos == 1 else 'centavos'}")
    return " e ".join(partes) if partes else "zero reais"


def percentual(valor: float) -> str:
    """15% ou 7,5%"""
    texto = f"{valor:.2f}".rstrip("0").rstrip(".").replace(".", ",")
    return f"{texto}%"


def data_curta(d: date) -> str:
    return d.strftime("%d/%m/%Y")


def data_longa(d: date) -> str:
    dia = "1º" if d.day == 1 else str(d.day)
    return f"{dia} de {MESES[d.month - 1]} de {d.year}"
