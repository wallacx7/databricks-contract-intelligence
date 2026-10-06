"""Renderização dos contratos e aditivos em PDF, com modelos de redação diferentes.

A variedade é proposital: a extração não pode depender de um layout. Os modelos mudam a ordem das
cláusulas, a forma de escrever valores e datas e onde ficam as condições comerciais (cláusula, quadro
resumo, texto corrido ou anexo). Também há iscas, como o total mensal estimado ao lado do preço por
usuário e o desconto permanente de pagamento anual, parecido com o desconto promocional.
"""

from __future__ import annotations

import io
import random

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from contrato_vivo.gerador.extenso import (
    data_curta,
    data_longa,
    percentual,
    por_extenso,
    reais,
    reais_por_extenso,
)
from contrato_vivo.gerador.termos import Documento

CONTRATADA = "NIMBUS TECNOLOGIA S.A., com sede em São Paulo/SP"

CLAUSULAS_GERAIS = [
    ("CONFIDENCIALIDADE", "As partes manterão sigilo sobre as informações a que tiverem acesso em razão deste "
     "instrumento, inclusive após o seu término, pelo prazo de 5 (cinco) anos."),
    ("PROTEÇÃO DE DADOS PESSOAIS", "A CONTRATADA tratará dados pessoais exclusivamente para a execução deste contrato, "
     "na condição de operadora, observando a Lei nº 13.709/2018 (LGPD) e as instruções da CONTRATANTE."),
    ("NÍVEL DE SERVIÇO", "A CONTRATADA garante disponibilidade mensal da plataforma de 99,5% (noventa e nove "
     "inteiros e cinco décimos por cento), excluídas as janelas de manutenção comunicadas com 48 horas de "
     "antecedência."),
    ("SUPORTE", "O suporte técnico será prestado em dias úteis, das 8h às 18h, pelos canais indicados pela "
     "CONTRATADA, com primeiro atendimento em até 4 (quatro) horas úteis para incidentes críticos."),
    ("PROPRIEDADE INTELECTUAL", "A plataforma, seus códigos e materiais permanecem de propriedade exclusiva da "
     "CONTRATADA. Os dados inseridos pela CONTRATANTE permanecem de sua propriedade."),
    ("RESPONSABILIDADE", "A responsabilidade total de cada parte fica limitada ao valor pago nos 12 (doze) meses "
     "anteriores ao evento que a originou, salvo dolo ou culpa grave."),
    ("COMUNICAÇÕES", "As comunicações entre as partes serão feitas por escrito, para os endereços eletrônicos "
     "indicados pelos representantes legais."),
    ("FORO", "Fica eleito o foro da Comarca de São Paulo/SP para dirimir quaisquer controvérsias oriundas deste "
     "contrato, com renúncia a qualquer outro, por mais privilegiado que seja."),
]  # fmt: skip


def _estilos(fonte: str) -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    corpo = ParagraphStyle("corpo", parent=base["BodyText"], fontName=fonte, fontSize=10.5, leading=15,
                           spaceAfter=7, alignment=4)  # fmt: skip
    negrito = fonte + "-Bold" if fonte == "Helvetica" else "Times-Bold"
    return {
        "titulo": ParagraphStyle("titulo", parent=base["Title"], fontName=negrito, fontSize=14, leading=18),
        "secao": ParagraphStyle("secao", parent=corpo, fontName=negrito, spaceBefore=10, alignment=0),
        "corpo": corpo,
        "pequeno": ParagraphStyle("pequeno", parent=corpo, fontSize=9, textColor=colors.HexColor("#444444")),
    }


def _valor(v: float, extenso_primeiro: bool = False) -> str:
    if extenso_primeiro:
        return f"{reais_por_extenso(v)} ({reais(v)})"
    return f"{reais(v)} ({reais_por_extenso(v)})"


def _usuarios(n: int) -> str:
    return f"{n} ({por_extenso(n)}) usuário" + ("" if n == 1 else "s")


def _data(d, longa: bool) -> str:
    return data_longa(d) if longa else data_curta(d)


def _partes(doc: Documento, s: dict) -> list:
    return [
        Paragraph(f"<b>CONTRATADA:</b> {CONTRATADA}.", s["corpo"]),
        Paragraph(
            f"<b>CONTRATANTE:</b> {doc.cliente.upper()}, com sede no estado de {doc.uf}, "
            f"código de cliente <b>{doc.codigo_cliente}</b>.",
            s["corpo"],
        ),  # fmt: skip
    ]


def _termos_comerciais(doc: Documento, longa: bool, extenso_primeiro: bool) -> list[str]:
    """Parágrafos com as condições comerciais, na ordem em que entram no texto."""
    total = doc.preco_usuario * doc.usuarios_contratados
    p = [
        f"A CONTRATANTE contrata o plano <b>{doc.plano}</b> para {_usuarios(doc.usuarios_contratados)}, ao preço de "
        f"{_valor(doc.preco_usuario, extenso_primeiro)} por usuário por mês.",
        f"Para fins de referência, o valor mensal estimado na data de assinatura é de {reais(total)}, "
        f"calculado sobre a quantidade de usuários indicada acima.",
    ]
    if doc.periodicidade == "anual":
        p.append(
            f"O pagamento será anual e antecipado, com desconto de {percentual(doc.desconto_anual_percentual)} "
            f"sobre o preço por usuário durante toda a vigência, enquanto mantida essa modalidade de pagamento."
        )
    else:
        p.append(
            "O pagamento será mensal, por boleto ou cartão corporativo, com vencimento em 10 (dez) dias "
            "da emissão da fatura."
        )
    if doc.desconto_promocional_percentual:
        meses_txt = f"{doc.desconto_promocional_meses} ({por_extenso(doc.desconto_promocional_meses)}) meses"
        p.append(
            f"Nos primeiros {meses_txt} de vigência, será concedido desconto promocional de "
            f"{percentual(doc.desconto_promocional_percentual)} sobre o preço por usuário. Encerrado esse "
            f"prazo, passa a ser devido o preço integral previsto neste contrato."
        )
    if doc.minimo_usuarios:
        p.append(
            f"A CONTRATANTE se compromete com o faturamento mínimo equivalente a "
            f"{_usuarios(doc.minimo_usuarios)} por mês, ainda que utilize quantidade inferior."
        )
    if doc.reajuste_tipo == "fixo":
        pct = percentual(doc.reajuste_percentual)
        p.append(
            f"O preço por usuário será reajustado anualmente, na data de aniversário do contrato, em {pct} "
            f"({por_extenso(int(doc.reajuste_percentual))}{' e meio' if doc.reajuste_percentual % 1 else ''} "
            f"por cento)."
        )
    else:
        p.append(
            "Os preços serão atualizados conforme a tabela vigente da CONTRATADA, mediante aviso prévio de "
            "30 (trinta) dias à CONTRATANTE."
        )
    return p


def _vigencia(doc: Documento, longa: bool) -> list[str]:
    return [
        f"Este contrato vigora de {_data(doc.inicio_vigencia, longa)} a {_data(doc.fim_vigencia, longa)}, "
        f"renovando-se automaticamente por períodos sucessivos de 12 (doze) meses, salvo manifestação contrária "
        f"de qualquer das partes com 60 (sessenta) dias de antecedência.",
        f"Em caso de rescisão antecipada imotivada pela CONTRATANTE, será devida multa de "
        f"{percentual(doc.multa_percentual)} sobre as mensalidades remanescentes, limitada a "
        f"{doc.multa_limite_mensalidades} ({por_extenso(doc.multa_limite_mensalidades)}) mensalidades.",
    ]


_ROMANOS = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII", "XIII", "XIV"]


class Corpo:
    """Monta as seções numeradas em sequência, num único estilo por documento."""

    def __init__(self, s: dict, rng: random.Random, estilo: str = "clausula") -> None:
        self.s, self.estilo, self.n = s, estilo, 0
        self._restantes = CLAUSULAS_GERAIS[:]
        rng.shuffle(self._restantes)  # uma vez por documento: nenhuma cláusula se repete

    def secao(self, titulo: str, paragrafos: list[str], corrido: bool = False) -> list:
        self.n += 1
        if self.estilo == "secao":
            rotulo = f"SEÇÃO {_ROMANOS[self.n - 1]} – {titulo}"
        else:
            rotulo = f"CLÁUSULA {self.n} – {titulo}"
        out = [Paragraph(rotulo, self.s["secao"])]
        if corrido:
            out.append(Paragraph(" ".join(paragrafos), self.s["corpo"]))
        else:
            out += [Paragraph(f"{self.n}.{i} {t}", self.s["corpo"]) for i, t in enumerate(paragrafos, 1)]
        return out

    def gerais(self, quantidade: int) -> list:
        out = []
        for _ in range(min(quantidade, len(self._restantes))):
            titulo, texto = self._restantes.pop(0)
            out += self.secao(titulo, [texto])
        return out


def _assinatura(doc: Documento, s: dict, longa: bool) -> list:
    return [
        Spacer(1, 18),
        Paragraph(f"São Paulo, {_data(doc.data_assinatura, longa)}.", s["corpo"]),
        Spacer(1, 30),
        Paragraph("_______________________________<br/>NIMBUS TECNOLOGIA S.A.", s["corpo"]),
        Spacer(1, 16),
        Paragraph(f"_______________________________<br/>{doc.cliente.upper()}", s["corpo"]),
    ]


# --------------------------------------------------------------------------- modelos de contrato


def _modelo_clausulas(doc: Documento, s: dict, rng: random.Random) -> list:
    """Modelo 0: cláusulas numeradas, valores em número seguido de extenso, datas curtas."""
    c = Corpo(s, rng)
    story = [Paragraph(f"CONTRATO DE ASSINATURA DE SOFTWARE Nº {doc.contrato_id}", s["titulo"]), *_partes(doc, s)]
    story += c.secao("OBJETO", ["Licença de uso, na modalidade de assinatura, da plataforma de gestão da CONTRATADA, "
                                "incluindo atualizações e suporte técnico."])  # fmt: skip
    story += c.gerais(3) + [PageBreak()]
    story += c.secao("PREÇO E PAGAMENTO", _termos_comerciais(doc, False, False))
    story += c.secao("VIGÊNCIA E RESCISÃO", _vigencia(doc, False))
    story += c.gerais(5) + _assinatura(doc, s, False)
    return story


def _modelo_quadro(doc: Documento, s: dict, rng: random.Random) -> list:
    """Modelo 1: quadro resumo na primeira página, cláusulas remetendo ao quadro."""
    linhas = [
        ["Contrato", doc.contrato_id],
        ["Código do cliente", doc.codigo_cliente],
        ["Plano", doc.plano],
        ["Usuários contratados", str(doc.usuarios_contratados)],
        ["Preço por usuário/mês", reais(doc.preco_usuario)],
        ["Pagamento", "Anual antecipado" if doc.periodicidade == "anual" else "Mensal"],
        ["Início da vigência", data_curta(doc.inicio_vigencia)],
        ["Término da vigência", data_curta(doc.fim_vigencia)],
    ]
    tabela = Table(linhas, colWidths=[6 * cm, 9 * cm])
    tabela.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#EEEEEE")),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
    ]))  # fmt: skip
    c = Corpo(s, rng)
    story = [Paragraph("CONTRATO DE LICENCIAMENTO DE SOFTWARE COMO SERVIÇO", s["titulo"]), *_partes(doc, s),
             Paragraph("QUADRO RESUMO", s["secao"]), tabela, Spacer(1, 10),
             Paragraph("As condições do Quadro Resumo integram este contrato. Em caso de divergência, prevalecem "
                       "as cláusulas a seguir.", s["pequeno"]), PageBreak()]  # fmt: skip
    story += c.gerais(2)
    story += c.secao("CONDIÇÕES COMERCIAIS", _termos_comerciais(doc, False, False))
    story += c.secao("PRAZO", _vigencia(doc, False))
    story += c.gerais(6) + _assinatura(doc, s, False)
    return story


def _modelo_prosa(doc: Documento, s: dict, rng: random.Random) -> list:
    """Modelo 2: seções em texto corrido, valores por extenso primeiro, datas longas."""
    c = Corpo(s, rng, estilo="secao")
    story = [Paragraph("INSTRUMENTO PARTICULAR DE PRESTAÇÃO DE SERVIÇOS DE SOFTWARE", s["titulo"]),
             Paragraph(f"Registro interno {doc.contrato_id}", s["pequeno"]), *_partes(doc, s)]  # fmt: skip
    story += c.gerais(4) + [PageBreak()]
    story += c.secao("DA REMUNERAÇÃO", _termos_comerciais(doc, True, True), corrido=True)
    story += c.secao("DO PRAZO E DA EXTINÇÃO", _vigencia(doc, True), corrido=True)
    story += c.gerais(4) + _assinatura(doc, s, True)
    return story


def _modelo_anexo(doc: Documento, s: dict, rng: random.Random) -> list:
    """Modelo 3: corpo genérico e condições comerciais no Anexo I, na última página."""
    c = Corpo(s, rng)
    story = [Paragraph(f"CONTRATO Nº {doc.contrato_id}", s["titulo"]), *_partes(doc, s)]
    story += c.secao("OBJETO", ["Assinatura da plataforma da CONTRATADA nas condições comerciais do Anexo I, que "
                                "integra este contrato."])  # fmt: skip
    story += c.gerais(8)
    story += c.secao("VIGÊNCIA", _vigencia(doc, True))
    story += _assinatura(doc, s, True) + [PageBreak(), Paragraph("ANEXO I – CONDIÇÕES COMERCIAIS", s["titulo"])]
    story += [Paragraph(f"({chr(97 + i)}) {t}", s["corpo"]) for i, t in enumerate(_termos_comerciais(doc, True, False))]
    return story


# --------------------------------------------------------------------------- aditivos


def _aditivo(doc: Documento, s: dict, longa: bool) -> list:
    total = doc.preco_usuario * doc.usuarios_contratados
    return [
        Paragraph(f"{doc.numero_aditivo}º TERMO ADITIVO AO CONTRATO Nº {doc.contrato_id}", s["titulo"]),
        *_partes(doc, s),
        Paragraph("CLÁUSULA PRIMEIRA – DO OBJETO", s["secao"]),
        Paragraph(f"1.1 A partir de {_data(doc.inicio_vigencia, longa)}, a CONTRATANTE passa a utilizar o plano "
                  f"<b>{doc.plano}</b>, ao preço de {_valor(doc.preco_usuario)} por usuário por mês, para "
                  f"{_usuarios(doc.usuarios_contratados)}.", s["corpo"]),
        Paragraph(f"1.2 O valor mensal estimado passa a ser de {reais(total)}.", s["corpo"]),
        Paragraph("CLÁUSULA SEGUNDA – DA RATIFICAÇÃO", s["secao"]),
        Paragraph("2.1 Permanecem inalteradas as demais cláusulas e condições do contrato original e de seus "
                  "aditivos anteriores, que não conflitem com o presente termo.", s["corpo"]),
        *_assinatura(doc, s, longa),
    ]  # fmt: skip


MODELOS_CONTRATO = [_modelo_clausulas, _modelo_quadro, _modelo_prosa, _modelo_anexo]


def renderizar(doc: Documento) -> bytes:
    rng = random.Random(doc.documento_id)
    s = _estilos("Times-Roman" if doc.modelo in (2, 3) else "Helvetica")
    if doc.tipo == "aditivo":
        story = _aditivo(doc, s, longa=doc.modelo == 1)
    else:
        story = MODELOS_CONTRATO[doc.modelo](doc, s, rng)
    buffer = io.BytesIO()
    SimpleDocTemplate(
        buffer, pagesize=A4, title=doc.documento_id, author="Nimbus Tecnologia S.A.",
        leftMargin=2.5 * cm, rightMargin=2.5 * cm, topMargin=2.5 * cm, bottomMargin=2.5 * cm,
    ).build(story)  # fmt: skip
    return buffer.getvalue()
