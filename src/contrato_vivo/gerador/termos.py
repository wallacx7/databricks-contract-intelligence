"""Contratos, aditivos e vazamento esperado a partir do histórico de billing (ADR 001).

Entrada: contas e versões SCD2 das assinaturas do Ledger. Saída: um documento por contrato e por aditivo,
com os termos que serão escritos no PDF, e o vazamento mensal que a reconciliação precisa encontrar.

Regra geral do valor devido por usuário num mês:
    preço do documento vigente
    × desconto promocional, se dentro do prazo
    × desconto de pagamento anual, se houver
    × reajuste: tabela vigente (acompanha os reajustes de tabela da Nimbus) ou percentual fixo por aniversário
Contratos sem vazamento plantado produzem, por construção, valor devido igual ao cobrado (há teste para isso).
"""

from __future__ import annotations

import random
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta

PLANOS = {"starter": "Starter", "pro": "Pro", "business": "Business"}
DESCONTO_ANUAL = 0.15
DESCONTO_PROMOCIONAL = 0.15
MESES_PROMOCIONAIS = 12
# Reajuste de tabela aplicado pelo billing do Ledger em julho de 2026 (planos Starter e Pro).
REAJUSTES_DE_TABELA = [(date(2026, 7, 1), {"starter": 0.12, "pro": 0.12})]
# Diferenças de arredondamento (centavos por usuário) não são vazamento.
TOLERANCIA_CENTAVOS = 0.05

TIPOS_VAZAMENTO = ("desconto_vencido", "preco_abaixo", "reajuste_nao_aplicado", "minimo_nao_cobrado")


@dataclass(frozen=True)
class Conta:
    account_id: str
    empresa: str
    segmento: str
    uf: str
    setor: str


@dataclass(frozen=True)
class Versao:
    """Uma versão SCD2 de silver.subscriptions do Ledger."""

    subscription_id: str
    account_id: str
    plan_id: str
    seats: int
    unit_price: float
    billing_period: str
    status: str
    inicio: datetime
    fim: datetime | None


@dataclass
class Documento:
    documento_id: str
    tipo: str  # contrato | aditivo
    contrato_id: str
    numero_aditivo: int | None
    account_id: str
    codigo_cliente: str
    cliente: str
    uf: str
    setor: str
    data_assinatura: date
    inicio_vigencia: date
    fim_vigencia: date | None
    plano: str
    preco_usuario: float
    usuarios_contratados: int
    periodicidade: str  # mensal | anual
    desconto_anual_percentual: float | None
    desconto_promocional_percentual: float | None
    desconto_promocional_meses: int | None
    reajuste_tipo: str  # tabela | fixo
    reajuste_percentual: float | None
    minimo_usuarios: int | None
    multa_percentual: float | None
    multa_limite_mensalidades: int | None
    modelo: int  # qual dos modelos de redação o PDF usa
    vazamento_plantado: str | None = None  # só para o gabarito; não aparece no texto

    # O aditivo só escreve plano, preço, usuários e data; o resto continua valendo pelo contrato original.
    CAMPOS_FORA_DO_ADITIVO = (
        "fim_vigencia", "periodicidade", "desconto_anual_percentual", "desconto_promocional_percentual",
        "desconto_promocional_meses", "reajuste_tipo", "reajuste_percentual", "minimo_usuarios",
        "multa_percentual", "multa_limite_mensalidades",
    )  # fmt: skip

    def campos_esperados(self) -> dict:
        """Valores que a extração precisa encontrar no texto deste documento."""
        campos = asdict(self)
        for interno in ("modelo", "vazamento_plantado", "account_id", "uf", "setor"):
            campos.pop(interno)
        if self.tipo == "aditivo":
            for campo in self.CAMPOS_FORA_DO_ADITIVO:
                campos[campo] = None
        for k, v in campos.items():
            if isinstance(v, date):
                campos[k] = v.isoformat()
        return campos


@dataclass
class VazamentoMensal:
    contrato_id: str
    account_id: str
    mes: date
    tipo: str
    usuarios_ativos: int
    usuarios_devidos: int
    preco_devido: float
    preco_cobrado: float
    valor_devido: float
    valor_cobrado: float
    vazamento: float


@dataclass
class Resultado:
    documentos: list[Documento] = field(default_factory=list)
    vazamentos: list[VazamentoMensal] = field(default_factory=list)


# ------------------------------------------------------------------------- utilidades


def fim_do_mes(mes: date) -> datetime:
    proximo = date(mes.year + mes.month // 12, mes.month % 12 + 1, 1)
    return datetime.combine(proximo, datetime.min.time())


def adicionar_meses(d: date, n: int) -> date:
    """Mesmo dia n meses depois, recuando para o último dia do mês quando ele não existe (31/01 + 1 = 28/02)."""
    ano, mes = divmod(d.month - 1 + n, 12)
    ano, mes = d.year + ano, mes + 1
    ultimo = (date(ano + mes // 12, mes % 12 + 1, 1) - timedelta(days=1)).day
    return date(ano, mes, min(d.day, ultimo))


def meses(inicio: date, fim: date) -> list[date]:
    out, m = [], date(inicio.year, inicio.month, 1)
    while m <= fim:
        out.append(m)
        m = date(m.year + m.month // 12, m.month % 12 + 1, 1)
    return out


def aniversarios(inicio: date, ate: datetime) -> int:
    """Quantos aniversários de `inicio` aconteceram até `ate` (exclusivo)."""
    n = ate.year - inicio.year
    if (ate.month, ate.day) <= (inicio.month, inicio.day):
        n -= 1
    return max(0, n)


def meses_completos(inicio: date, ate: datetime) -> int:
    n = (ate.year - inicio.year) * 12 + ate.month - inicio.month
    if ate.day <= inicio.day:
        n -= 1
    return max(0, n)


def fator_tabela(plano: str, desde: date, ate: datetime) -> float:
    fator = 1.0
    for quando, reajustes in REAJUSTES_DE_TABELA:
        # `ate` é o fim do mês (00:00 do dia 1º seguinte); um reajuste nesse instante já é do mês seguinte.
        if desde < quando and datetime.combine(quando, datetime.min.time()) < ate and plano in reajustes:
            fator *= 1 + reajustes[plano]
    return fator


def versao_em(versoes: list[Versao], momento: datetime) -> Versao | None:
    """Versão vigente imediatamente antes de `momento` (fim do mês)."""
    for v in versoes:
        if v.inicio < momento and (v.fim is None or v.fim >= momento):
            return v
    return None


# ------------------------------------------------------------------------- geração


def _numero(account_id: str) -> int:
    return int(account_id.split("_")[1])


def documentos_da_conta(conta: Conta, versoes: list[Versao], rng: random.Random) -> list[Documento]:
    versoes = sorted(versoes, key=lambda v: v.inicio)
    primeira = versoes[0]
    inicio = primeira.inicio.date()
    numero = _numero(conta.account_id)
    contrato_id = f"CT-{inicio.year}-{numero:06d}"
    anual = primeira.billing_period == "annual"
    preco_tabela = round(primeira.unit_price / (1 - DESCONTO_ANUAL), 2) if anual else primeira.unit_price

    vazamento = None
    if not anual:
        sorteio = rng.random()
        if sorteio < 0.10:
            vazamento = "desconto_vencido"
        elif sorteio < 0.14:
            vazamento = "preco_abaixo"
        elif sorteio < 0.22:
            vazamento = "reajuste_nao_aplicado"

    preco = preco_tabela
    desconto_promo = meses_promo = reajuste_pct = None
    if vazamento == "desconto_vencido":
        preco = round(primeira.unit_price / (1 - DESCONTO_PROMOCIONAL), 2)
        desconto_promo, meses_promo = DESCONTO_PROMOCIONAL * 100, MESES_PROMOCIONAIS
    elif vazamento == "preco_abaixo":
        preco = round(primeira.unit_price * rng.uniform(1.08, 1.20), 2)
    elif vazamento == "reajuste_nao_aplicado":
        reajuste_pct = rng.choice([4.0, 4.5, 5.0, 6.0, 7.5, 8.0])
    minimo = primeira.seats if rng.random() < 0.15 else None

    duracao = 36 if conta.segmento == "enterprise" else 24
    fim_vigencia = adicionar_meses(inicio, duracao) - timedelta(days=1)
    base = Documento(
        documento_id=contrato_id,
        tipo="contrato",
        contrato_id=contrato_id,
        numero_aditivo=None,
        account_id=conta.account_id,
        codigo_cliente=f"NIM-{numero:06d}",
        cliente=conta.empresa,
        uf=conta.uf,
        setor=conta.setor,
        data_assinatura=inicio,
        inicio_vigencia=inicio,
        fim_vigencia=fim_vigencia,
        plano=PLANOS[primeira.plan_id],
        preco_usuario=preco,
        usuarios_contratados=primeira.seats,
        periodicidade="anual" if anual else "mensal",
        desconto_anual_percentual=DESCONTO_ANUAL * 100 if anual else None,
        desconto_promocional_percentual=desconto_promo,
        desconto_promocional_meses=meses_promo,
        reajuste_tipo="fixo" if reajuste_pct else "tabela",
        reajuste_percentual=reajuste_pct,
        minimo_usuarios=minimo,
        multa_percentual=rng.choice([20.0, 25.0, 30.0, 40.0]),
        multa_limite_mensalidades=rng.choice([3, 4, 6]),
        modelo=rng.randrange(4),
        vazamento_plantado=vazamento,
    )
    docs = [base]

    # Um aditivo por mudança de plano, com o preço que o billing passou a cobrar.
    anterior = primeira
    for v in versoes[1:]:
        if v.plan_id != anterior.plan_id and v.status == "active":
            n = len(docs)
            preco_aditivo = round(v.unit_price / (1 - DESCONTO_ANUAL), 2) if anual else v.unit_price
            docs.append(
                Documento(
                    **{
                        **asdict(base),
                        "documento_id": f"{contrato_id}-A{n}",
                        "tipo": "aditivo",
                        "numero_aditivo": n,
                        "data_assinatura": v.inicio.date(),
                        "inicio_vigencia": v.inicio.date(),
                        "fim_vigencia": None,
                        "plano": PLANOS[v.plan_id],
                        "preco_usuario": preco_aditivo,
                        "usuarios_contratados": v.seats,
                        "desconto_promocional_percentual": None,
                        "desconto_promocional_meses": None,
                        "modelo": rng.randrange(2),
                    }
                )
            )
        anterior = v
    return docs


def preco_devido(base: Documento, vigente: Documento, plano: str, momento: datetime) -> float:
    preco = vigente.preco_usuario
    if (
        vigente.tipo == "contrato"
        and base.desconto_promocional_meses
        and meses_completos(base.inicio_vigencia, momento) < base.desconto_promocional_meses
    ):
        preco *= 1 - base.desconto_promocional_percentual / 100
    if base.desconto_anual_percentual:
        preco *= 1 - base.desconto_anual_percentual / 100
    if base.reajuste_tipo == "fixo":
        anos = aniversarios(base.inicio_vigencia, momento) - aniversarios(
            base.inicio_vigencia, datetime.combine(vigente.inicio_vigencia, datetime.min.time())
        )
        preco *= (1 + base.reajuste_percentual / 100) ** anos
    else:
        preco *= fator_tabela(plano, vigente.inicio_vigencia, momento)
    return round(preco, 2)


def vazamentos_do_contrato(docs: list[Documento], versoes: list[Versao], ultimo_mes: date) -> list[VazamentoMensal]:
    base = docs[0]
    versoes = sorted(versoes, key=lambda v: v.inicio)
    out = []
    for mes in meses(base.inicio_vigencia, ultimo_mes):
        momento = fim_do_mes(mes)
        v = versao_em(versoes, momento)
        if v is None or v.status != "active":
            continue
        vigente = [d for d in docs if datetime.combine(d.inicio_vigencia, datetime.min.time()) < momento][-1]
        devido = preco_devido(base, vigente, v.plan_id, momento)
        usuarios_devidos = max(v.seats, base.minimo_usuarios or 0)
        diferenca_preco = devido - v.unit_price
        partes = []
        if diferenca_preco > TOLERANCIA_CENTAVOS and base.vazamento_plantado:
            partes.append((base.vazamento_plantado, round(v.seats * diferenca_preco, 2)))
        if usuarios_devidos > v.seats:
            partes.append(("minimo_nao_cobrado", round((usuarios_devidos - v.seats) * devido, 2)))
        for tipo, valor in partes:
            out.append(
                VazamentoMensal(
                    contrato_id=base.contrato_id,
                    account_id=base.account_id,
                    mes=mes,
                    tipo=tipo,
                    usuarios_ativos=v.seats,
                    usuarios_devidos=usuarios_devidos,
                    preco_devido=devido,
                    preco_cobrado=v.unit_price,
                    valor_devido=round(usuarios_devidos * devido, 2),
                    valor_cobrado=round(v.seats * v.unit_price, 2),
                    vazamento=valor,
                )
            )
    return out


def gerar(
    contas: list[Conta],
    versoes: list[Versao],
    ultimo_mes: date,
    seed: int = 42,
    limite: int | None = None,
) -> Resultado:
    """Gera documentos e vazamentos para as contas Mid-Market e Enterprise."""
    por_conta: dict[str, list[Versao]] = {}
    for v in versoes:
        por_conta.setdefault(v.account_id, []).append(v)
    elegiveis = sorted(
        (c for c in contas if c.segmento in ("mid_market", "enterprise") and c.account_id in por_conta),
        key=lambda c: c.account_id,
    )
    if limite:
        elegiveis = elegiveis[:limite]
    resultado = Resultado()
    for conta in elegiveis:
        rng = random.Random(f"{seed}-{conta.account_id}")  # estável por conta, independente do limite
        docs = documentos_da_conta(conta, por_conta[conta.account_id], rng)
        resultado.documentos.extend(docs)
        resultado.vazamentos.extend(vazamentos_do_contrato(docs, por_conta[conta.account_id], ultimo_mes))
    return resultado
