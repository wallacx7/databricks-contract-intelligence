"""Implementações reais das interfaces do agente, usando o Databricks (adaptadas do Ledger).

A autenticação segue a cadeia padrão do SDK: perfil do Databricks CLI na máquina local,
service principal dentro de uma Databricks App.
"""

from __future__ import annotations

import time
from decimal import Decimal
from typing import Any

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.sql import StatementParameterListItem, StatementState

from contrato_vivo.agente.nucleo import LlmReply, ToolCall

_TYPES = {int: "INT", float: "DOUBLE", str: "STRING"}


def _convert(value: str | None, type_name: str) -> Any:
    if value is None:
        return None
    if type_name in ("DECIMAL",):
        return float(Decimal(value))
    if type_name in ("INT", "LONG", "SHORT", "BYTE"):
        return int(value)
    if type_name in ("DOUBLE", "FLOAT"):
        return float(value)
    return value


class WarehouseRunner:
    """Executa SQL parametrizado num SQL warehouse pela Statement Execution API."""

    def __init__(self, warehouse_id: str, client: WorkspaceClient | None = None, max_rows: int = 200) -> None:
        self.w = client or WorkspaceClient()
        self.warehouse_id = warehouse_id
        self.max_rows = max_rows

    def run(self, sql: str, params: dict[str, Any]) -> list[dict]:
        parameters = [
            StatementParameterListItem(name=k, value=None if v is None else str(v), type=_TYPES.get(type(v), "STRING"))
            for k, v in params.items()
        ]
        resp = self.w.statement_execution.execute_statement(
            statement=sql,
            warehouse_id=self.warehouse_id,
            parameters=parameters,
            wait_timeout="30s",
            row_limit=self.max_rows,
        )
        while resp.status.state in (StatementState.PENDING, StatementState.RUNNING):
            time.sleep(1)
            resp = self.w.statement_execution.get_statement(resp.statement_id)
        if resp.status.state != StatementState.SUCCEEDED:
            message = resp.status.error.message if resp.status.error else resp.status.state.value
            raise RuntimeError(message)
        columns = resp.manifest.schema.columns
        rows = (resp.result.data_array if resp.result else None) or []
        return [
            {
                c.name: _convert(v, c.type_name.value if c.type_name else "STRING")
                for c, v in zip(columns, row, strict=True)
            }
            for row in rows
        ]


class DatabricksChatModel:
    """Modelo servido no workspace, pela API compatível com OpenAI (ADR 003)."""

    def __init__(self, endpoint: str = "databricks-gpt-oss-120b", max_tokens: int = 2000) -> None:
        from databricks_openai import DatabricksOpenAI

        self.client = DatabricksOpenAI()
        self.endpoint = endpoint
        self.max_tokens = max_tokens

    @staticmethod
    def _text(content: Any) -> str | None:
        # Alguns modelos devolvem uma lista de partes (raciocínio + texto); só o texto vai para a resposta.
        if content is None or isinstance(content, str):
            return content
        parts = [p.get("text", "") for p in content if isinstance(p, dict) and p.get("type") == "text"]
        return "".join(parts) or None

    def complete(self, messages: list[dict], tools: list[dict], allow_tools: bool = True) -> LlmReply:
        kwargs: dict[str, Any] = {
            "model": self.endpoint,
            "messages": messages,
            "max_tokens": self.max_tokens,
            "temperature": 0,
        }
        if allow_tools:
            kwargs["tools"] = tools
        resp = self.client.chat.completions.create(**kwargs)
        msg = resp.choices[0].message
        calls = [ToolCall(id=c.id, name=c.function.name, arguments=c.function.arguments) for c in msg.tool_calls or []]
        return LlmReply(
            text=self._text(msg.content), tool_calls=calls, tokens=resp.usage.total_tokens if resp.usage else 0
        )


class BuscaVetorial:
    """Busca híbrida (semântica + palavras) no índice de trechos, filtrada por contrato."""

    COLUNAS = ["documento_id", "contrato_id", "cliente", "tipo_documento", "pagina", "texto"]

    def __init__(
        self, indice: str, client: WorkspaceClient | None = None, modelo_embedding: str = "databricks-gte-large-en"
    ) -> None:
        self.w = client or WorkspaceClient()
        self.indice = indice
        self.modelo_embedding = modelo_embedding

    def _vetor(self, texto: str) -> list[float]:
        """Embedding da consulta, com o mesmo modelo usado nos trechos."""
        r = self.w.serving_endpoints.query(name=self.modelo_embedding, input=[texto])
        return list(r.data[0].embedding)

    def buscar(self, consulta: str, contrato_id: str | None, limite: int = 5) -> list[dict]:
        import json

        filtros = json.dumps({"contrato_id": contrato_id}) if contrato_id else None
        r = self.w.vector_search_indexes.query_index(
            index_name=self.indice,
            columns=self.COLUNAS,
            query_text=consulta,  # busca por palavras; junto com o vetor forma a busca híbrida
            query_vector=self._vetor(consulta),
            filters_json=filtros,
            num_results=limite,
            query_type="HYBRID",
        )
        colunas = [c.name for c in r.manifest.columns]
        return [dict(zip(colunas, linha, strict=False)) for linha in (r.result.data_array or [])]
