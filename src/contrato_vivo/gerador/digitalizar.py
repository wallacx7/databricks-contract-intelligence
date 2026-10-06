"""Transforma um PDF digital num PDF "digitalizado": imagem com ruído e sem camada de texto.

Simula o contrato que chega escaneado: a página vira imagem, ganha uma pequena rotação, ruído, desfoque,
manchas e compressão JPEG, e volta a ser PDF. Sem camada de texto, o `ai_parse_document` precisa fazer OCR,
o que torna a extração mais difícil e a fila de revisão humana mais realista.
"""

from __future__ import annotations

import io
import random
import time

import pypdfium2 as pdfium
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

NIVEIS = ("leve", "medio", "forte")
PROBABILIDADE = 0.15

# nível -> (rotação máx. em graus, intensidade do ruído, raio do desfoque, qualidade JPEG, contraste, manchas)
_PARAMETROS = {
    "leve": (0.6, 18, 0.0, 70, 1.00, 0),
    "medio": (1.2, 32, 0.6, 50, 0.90, 1),
    "forte": (2.0, 48, 0.9, 38, 0.78, 3),
}
DPI = 150
_DATA_FIXA = time.gmtime(1767225600)  # 01/01/2026 00:00 UTC


def sortear_nivel(documento_id: str, seed: int = 42) -> str | None:
    """Decide, de forma estável por documento, se ele será digitalizado e com qual nível."""
    rng = random.Random(f"digitalizacao-{seed}-{documento_id}")
    if rng.random() >= PROBABILIDADE:
        return None
    return rng.choices(NIVEIS, weights=[0.5, 0.35, 0.15])[0]


def _degradar(pagina: Image.Image, nivel: str, rng: random.Random) -> Image.Image:
    rotacao, ruido, desfoque, _, contraste, manchas = _PARAMETROS[nivel]
    img = pagina.convert("L")
    img = img.rotate(rng.uniform(-rotacao, rotacao), resample=Image.BICUBIC, expand=False, fillcolor=255)
    # Ruído gerado pela semente do documento (Image.effect_noise usa um gerador próprio, sem semente).
    granulado = Image.frombytes("L", img.size, rng.randbytes(img.width * img.height))
    img = Image.blend(img, granulado, ruido / 400)
    if desfoque:
        img = img.filter(ImageFilter.GaussianBlur(desfoque))
    img = ImageEnhance.Contrast(img).enhance(contraste)
    desenho = ImageDraw.Draw(img)
    for _ in range(manchas):
        x, y = rng.randrange(img.width), rng.randrange(img.height)
        r = rng.randrange(30, 90)
        desenho.ellipse((x - r, y - r // 2, x + r, y + r // 2), fill=rng.randrange(170, 215))
    return img


def digitalizar(pdf: bytes, nivel: str, semente: str) -> bytes:
    if nivel not in _PARAMETROS:
        raise ValueError(f"nível desconhecido: {nivel}")
    rng = random.Random(semente)
    documento = pdfium.PdfDocument(pdf)
    paginas = []
    for i in range(len(documento)):
        imagem = documento[i].render(scale=DPI / 72).to_pil()
        paginas.append(_degradar(imagem, nivel, rng))
    documento.close()

    qualidade = _PARAMETROS[nivel][3]
    comprimidas = []
    for pagina in paginas:  # passa por JPEG para ter os artefatos de compressão de um scanner
        buffer = io.BytesIO()
        pagina.save(buffer, format="JPEG", quality=qualidade)
        comprimidas.append(Image.open(io.BytesIO(buffer.getvalue())))

    saida = io.BytesIO()
    comprimidas[0].save(
        saida,
        format="PDF",
        save_all=True,
        append_images=comprimidas[1:],
        resolution=DPI,
        creationDate=_DATA_FIXA,  # sem data do momento da geração: o mesmo documento gera os mesmos bytes
        modDate=_DATA_FIXA,
    )
    return saida.getvalue()
