"""Campos extraídos de cada documento: JSON Schema enviado ao modelo e tipo de cada campo na comparação.

Mantido num só lugar para que o pipeline, a avaliação e os testes usem exatamente a mesma lista.
"""

from __future__ import annotations

import json

# campo -> (tipo JSON, tipo para comparar/ancorar)
#   dinheiro, inteiro e percentual são ancorados no texto; data e texto dependem só da concordância.
CAMPOS: dict[str, tuple[str, str]] = {
    "tipo_documento": ("string", "texto"),
    "contrato_id": ("string", "texto"),
    "numero_aditivo": ("integer", "inteiro"),
    "codigo_cliente": ("string", "texto"),
    "cliente": ("string", "texto"),
    "data_assinatura": ("string", "data"),
    "inicio_vigencia": ("string", "data"),
    "fim_vigencia": ("string", "data"),
    "plano": ("string", "texto"),
    "preco_usuario": ("number", "dinheiro"),
    "usuarios_contratados": ("integer", "inteiro"),
    "periodicidade": ("string", "texto"),
    "desconto_anual_percentual": ("number", "percentual"),
    "desconto_promocional_percentual": ("number", "percentual"),
    "desconto_promocional_meses": ("integer", "inteiro"),
    "reajuste_tipo": ("string", "texto"),
    "reajuste_percentual": ("number", "percentual"),
    "minimo_usuarios": ("integer", "inteiro"),
    "multa_percentual": ("number", "percentual"),
    "multa_limite_mensalidades": ("integer", "inteiro"),
}

# Formato esperado de identificadores (valores normalizados em minúsculas). Um OCR que perde ou troca caracteres
# produz um valor fora do formato mesmo quando os dois modelos concordam, porque ambos leem o mesmo texto.
FORMATOS = {
    "contrato_id": r"^ct-[0-9]{4}-[0-9]{6}$",
    "codigo_cliente": r"^nim-[0-9]{6}$",
}

_ENUMS = {
    "tipo_documento": ["contrato", "aditivo"],
    "periodicidade": ["mensal", "anual"],
    "reajuste_tipo": ["tabela", "fixo"],
}

INSTRUCOES = """\
Você extrai os termos comerciais de contratos e aditivos de assinatura de software da Nimbus Tecnologia.
Regras:
- preco_usuario é o preço por usuário por mês. Não confunda com o "valor mensal estimado", que é um total.
- desconto_promocional_* é o desconto temporário, com prazo em meses. desconto_anual_percentual é o desconto
  permanente por pagamento anual antecipado. Use null no que não existir.
- reajuste_tipo é "fixo" quando há percentual anual definido (informe reajuste_percentual) e "tabela" quando
  os preços seguem a tabela vigente da Nimbus.
- minimo_usuarios só existe quando há compromisso de faturamento mínimo.
- multa_* refere-se à rescisão antecipada.
- numero_aditivo é o número do termo aditivo como inteiro ("1º TERMO ADITIVO" = 1); null em contratos.
- periodicidade é a forma de pagamento escrita no documento: "anual" quando há pagamento anual antecipado,
  "mensal" quando o pagamento mensal está descrito. "Por usuário por mês" é a unidade do preço, não a forma de
  pagamento. Em aditivos, que não tratam de pagamento, use null.
- Datas no formato AAAA-MM-DD. Percentuais como número (15 para 15%).
- Em aditivos, preencha apenas o que está escrito no aditivo; o restante é null.
- Nunca invente: se o campo não estiver no texto, use null.

Documento:
"""


def json_schema() -> str:
    props = {}
    for campo, (tipo, _) in CAMPOS.items():
        prop: dict = {"type": [tipo, "null"]}
        if campo in _ENUMS:
            prop["enum"] = [*_ENUMS[campo], None]
        props[campo] = prop
    schema = {
        "type": "json_schema",
        "json_schema": {
            "name": "termos_do_contrato",
            "strict": True,
            "schema": {"type": "object", "properties": props, "required": list(CAMPOS), "additionalProperties": False},
        },
    }
    return json.dumps(schema, ensure_ascii=False)


def struct_ddl() -> str:
    """Tipo Spark para ler a resposta JSON com from_json."""
    tipos = {"string": "STRING", "integer": "INT", "number": "DOUBLE"}
    return ", ".join(f"{c} {tipos[t]}" for c, (t, _) in CAMPOS.items())
