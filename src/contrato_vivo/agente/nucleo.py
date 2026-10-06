"""Agente de perguntas sobre contratos: decide as ferramentas, consulta e responde com citação.

Mesma arquitetura do agente do Ledger: o laço depende de interfaces (modelo, executor SQL, busca), o que
permite testá-lo com implementações falsas, sem rede.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Protocol

from contrato_vivo.agente.ferramentas import ESPECIFICACOES, ErroDeFerramenta, apresentar, consulta, texto_valido

RECUSA = "Não encontrei essa informação nos contratos."

INSTRUCOES = f"""\
Você responde perguntas sobre os contratos de clientes da Nimbus Tecnologia (contratos de assinatura de software
e seus aditivos), usando apenas as ferramentas.

Regras
1. Se a pergunta citar o cliente e não o número do contrato, use localizar_contrato primeiro. Se houver mais de um
   contrato possível, diga quais são e pergunte qual.
2. Todo fato da resposta precisa de citação no formato (documento, p. N), com o documento e a página que vieram das
   ferramentas. Ex.: "A multa é de 30% (CT-2024-000123, p. 2)."
3. Aditivos alteram o contrato: o preço e o plano vigentes são os do documento mais recente.
4. Valores já vêm formatados (R$ 1.234,56 e 30%); copie exatamente.
5. Se as ferramentas não trouxerem a informação, responda exatamente: "{RECUSA}"
6. Não dê opinião jurídica nem recomende ações; descreva o que o contrato diz.

Responda em português, começando pela resposta direta, em até cinco frases.
"""


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: str


@dataclass
class LlmReply:
    text: str | None
    tool_calls: list[ToolCall]
    tokens: int = 0


class ChatModel(Protocol):
    def complete(self, messages: list[dict], tools: list[dict], allow_tools: bool = True) -> LlmReply: ...


class SqlRunner(Protocol):
    def run(self, sql: str, params: dict[str, Any]) -> list[dict]: ...


class Busca(Protocol):
    def buscar(self, consulta: str, contrato_id: str | None, limite: int = 5) -> list[dict]: ...


@dataclass
class Passo:
    ferramenta: str
    argumentos: dict
    linhas: list[dict] | None = None
    erro: str | None = None
    segundos: float = 0.0


@dataclass
class Resposta:
    pergunta: str
    texto: str
    passos: list[Passo] = field(default_factory=list)
    tokens: int = 0
    segundos: float = 0.0

    @property
    def recusou(self) -> bool:
        return RECUSA in self.texto


@dataclass
class Configuracao:
    gold_schema: str  # catalogo.schema
    silver_schema: str
    max_passos: int = 8
    max_linhas: int = 60


class AgenteDeContratos:
    def __init__(self, modelo: ChatModel, sql: SqlRunner, busca: Busca, config: Configuracao) -> None:
        self.modelo, self.sql, self.busca, self.config = modelo, sql, busca, config

    def _executar(self, nome: str, argumentos: dict) -> Passo:
        passo = Passo(nome, argumentos)
        t0 = time.perf_counter()
        try:
            if nome == "buscar_clausulas":
                from contrato_vivo.agente.ferramentas import contrato_valido

                contrato = contrato_valido(argumentos.get("contrato_id"))
                assunto = texto_valido(argumentos.get("assunto"), "O assunto", maximo=200)
                passo.linhas = self.busca.buscar(assunto, contrato, limite=5)
            else:
                sql, parametros = consulta(nome, argumentos, self.config.gold_schema, self.config.silver_schema)
                passo.linhas = self.sql.run(sql, parametros)
        except ErroDeFerramenta as exc:
            passo.erro = str(exc)
        except Exception as exc:  # falha de execução volta ao modelo em vez de derrubar a conversa
            passo.erro = f"Falha ao executar {nome}: {exc}"
        passo.segundos = time.perf_counter() - t0
        return passo

    def _mensagem(self, call_id: str, passo: Passo) -> dict:
        if passo.erro:
            conteudo = {"erro": passo.erro}
        else:
            linhas = passo.linhas or []
            conteudo = {"linhas": [apresentar(x) for x in linhas[: self.config.max_linhas]], "total": len(linhas)}
        return {
            "role": "tool",
            "tool_call_id": call_id,
            "content": json.dumps(conteudo, ensure_ascii=False, default=str),
        }

    def perguntar(self, pergunta: str, historico: list[dict] | None = None) -> Resposta:
        t0 = time.perf_counter()
        resposta = Resposta(pergunta, "")
        mensagens = [
            {"role": "system", "content": INSTRUCOES},
            *(historico or []),
            {"role": "user", "content": pergunta},
        ]
        for rodada in range(self.config.max_passos + 1):
            r = self.modelo.complete(mensagens, ESPECIFICACOES, allow_tools=rodada < self.config.max_passos)
            resposta.tokens += r.tokens
            if not r.tool_calls:
                resposta.texto = (r.text or "").strip()
                break
            mensagens.append(
                {
                    "role": "assistant",
                    "content": r.text or "",
                    "tool_calls": [
                        {"id": c.id, "type": "function", "function": {"name": c.name, "arguments": c.arguments}}
                        for c in r.tool_calls
                    ],
                }
            )
            for chamada in r.tool_calls:
                try:
                    argumentos = json.loads(chamada.arguments or "{}")
                except json.JSONDecodeError:
                    argumentos = {}
                passo = self._executar(chamada.name, argumentos)
                resposta.passos.append(passo)
                mensagens.append(self._mensagem(chamada.id, passo))
        resposta.segundos = time.perf_counter() - t0
        return resposta
