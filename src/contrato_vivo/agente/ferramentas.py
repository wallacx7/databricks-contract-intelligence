"""Ferramentas do agente de contratos.

Argumentos são validados antes de virar consulta; o texto do modelo nunca vira SQL. Valores em reais e
percentuais saem formatados, para o modelo copiar em vez de converter (lição do Ledger, ADR 005 de lá).
"""

from __future__ import annotations

import re
from typing import Any


class ErroDeFerramenta(ValueError):
    """Argumento inválido. A mensagem volta para o modelo corrigir a chamada."""


_CONTRATO = re.compile(r"^CT-\d{4}-\d{6}$")


def contrato_valido(valor: Any) -> str:
    texto = str(valor or "").strip().upper()
    if not _CONTRATO.match(texto):
        raise ErroDeFerramenta(
            f"Número de contrato inválido: {valor!r}. Use o formato CT-AAAA-NNNNNN; se só tiver o nome do cliente, "
            "use localizar_contrato antes."
        )
    return texto


def texto_valido(valor: Any, nome: str, minimo: int = 2, maximo: int = 200) -> str:
    texto = str(valor or "").strip()
    if not minimo <= len(texto) <= maximo:
        raise ErroDeFerramenta(f"{nome} precisa ter entre {minimo} e {maximo} caracteres.")
    return texto


def brl(valor: float) -> str:
    return "R$ " + f"{valor:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


_DINHEIRO = {"preco_usuario", "vazamento_acumulado", "vazamento_mes_atual", "recuperavel_12_meses"}
_DATA = {"data_assinatura", "inicio_vigencia", "fim_vigencia", "primeiro_mes", "ultimo_mes"}
_PERCENTUAL = {"desconto_anual_percentual", "desconto_promocional_percentual", "reajuste_percentual",
               "multa_percentual"}  # fmt: skip


def apresentar(linha: dict) -> dict:
    """Formata dinheiro e percentuais; nos campos por linha (campo/valor), usa o nome do campo."""
    out = dict(linha)
    campo = linha.get("campo")
    for chave, valor in linha.items():
        nome = campo if chave == "valor" and campo else chave
        if nome in _DATA and isinstance(valor, str) and re.match(r"^\d{4}-\d{2}-\d{2}", valor):
            out[chave] = f"{valor[8:10]}/{valor[5:7]}/{valor[0:4]}"
            continue
        try:
            numero = float(valor)
        except (TypeError, ValueError):
            continue
        if nome in _DINHEIRO:
            out[chave] = brl(numero)
        elif nome in _PERCENTUAL:
            out[chave] = f"{numero:g}%".replace(".", ",")
    return out


def _funcao(nome: str, descricao: str, propriedades: dict, obrigatorios: list[str]) -> dict:
    return {
        "type": "function",
        "function": {
            "name": nome,
            "description": descricao,
            "parameters": {"type": "object", "properties": propriedades, "required": obrigatorios},
        },
    }


_ID = {"type": "string", "description": "Número do contrato, formato CT-AAAA-NNNNNN."}

ESPECIFICACOES = [
    _funcao(
        "localizar_contrato",
        "Encontra contratos pelo nome (ou parte do nome) do cliente. Use quando a pergunta citar o cliente e não "
        "o número do contrato.",
        {"cliente": {"type": "string", "description": "Nome ou parte do nome do cliente."}},
        ["cliente"],
    ),
    _funcao(
        "termos_do_contrato",
        "Termos comerciais de cada documento do contrato (contrato original e aditivos, em ordem), um campo por "
        "linha, com a página de onde o valor foi lido. O preço vigente é o do documento mais recente.",
        {"contrato_id": _ID},
        ["contrato_id"],
    ),
    _funcao(
        "buscar_clausulas",
        "Busca trechos do texto do contrato e dos aditivos sobre um assunto (ex.: multa, rescisão, reajuste, "
        "confidencialidade, LGPD, SLA). Devolve documento, página e texto.",
        {"contrato_id": _ID, "assunto": {"type": "string", "description": "O que procurar, em poucas palavras."}},
        ["contrato_id", "assunto"],
    ),
    _funcao(
        "vazamento_do_contrato",
        "Receita que o contrato dá direito de cobrar e o billing não cobrou: tipo, período, valor acumulado, "
        "valor no último mês e o recuperável em 12 meses.",
        {"contrato_id": _ID},
        ["contrato_id"],
    ),
]


def consulta(nome: str, argumentos: dict, gold: str, silver: str) -> tuple[str, dict]:
    """SQL parametrizado de cada ferramenta de tabela (buscar_clausulas usa o índice, não SQL)."""
    if nome == "localizar_contrato":
        cliente = texto_valido(argumentos.get("cliente"), "O nome do cliente", maximo=80)
        return (
            f"SELECT DISTINCT contrato_id, cliente FROM {gold}.stg_documentos "
            f"WHERE lower(cliente) LIKE lower(concat('%', :cliente, '%')) ORDER BY contrato_id LIMIT 10",
            {"cliente": cliente},
        )
    if nome == "termos_do_contrato":
        contrato = contrato_valido(argumentos.get("contrato_id"))
        return (
            f"SELECT d.documento_id, d.tipo_documento, d.inicio_vigencia, c.campo, c.valor_final AS valor, c.pagina "
            f"FROM {gold}.stg_documentos d JOIN {silver}.campos_finais c USING (documento_id) "
            f"WHERE d.contrato_id = :contrato_id AND c.valor_final IS NOT NULL "
            f"AND c.campo NOT IN ('contrato_id', 'codigo_cliente', 'tipo_documento') "
            f"ORDER BY d.inicio_vigencia, d.documento_id, c.campo",
            {"contrato_id": contrato},
        )
    if nome == "vazamento_do_contrato":
        contrato = contrato_valido(argumentos.get("contrato_id"))
        return (
            f"SELECT tipo, primeiro_mes, ultimo_mes, meses, vazamento_acumulado, vazamento_mes_atual, "
            f"recuperavel_12_meses FROM {gold}.vazamento_por_contrato WHERE contrato_id = :contrato_id",
            {"contrato_id": contrato},
        )
    raise ErroDeFerramenta(f"Ferramenta desconhecida: {nome}.")
