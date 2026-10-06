"""Banco operacional da revisão humana (Lakebase, Postgres).

Duas tabelas:
- `reservas`: o item que cada revisor está olhando agora. Evita que duas pessoas revisem o mesmo campo;
  a reserva expira em 15 minutos para não travar itens abandonados.
- `decisoes`: o resultado de cada revisão (aprovado ou corrigido). É a fonte que volta para o lakehouse.

A conexão usa um token OAuth do Databricks como senha: localmente o do usuário do CLI, na App o do
service principal da própria App.
"""

from __future__ import annotations

import os
import uuid
from contextlib import contextmanager
from dataclasses import dataclass

ESQUEMA = "revisao"
MINUTOS_DE_RESERVA = 15

DDL = f"""
CREATE SCHEMA IF NOT EXISTS {ESQUEMA};

CREATE TABLE IF NOT EXISTS {ESQUEMA}.decisoes (
    item_id         text PRIMARY KEY,
    documento_id    text NOT NULL,
    campo           text NOT NULL,
    motivo          text NOT NULL CHECK (motivo IN ('confianca_baixa', 'auditoria')),
    valor_sugerido  text,
    decisao         text NOT NULL CHECK (decisao IN ('aprovado', 'corrigido')),
    valor_corrigido text,
    revisor         text NOT NULL,
    decidido_em     timestamptz NOT NULL DEFAULT now(),
    CHECK (decisao = 'aprovado' OR valor_corrigido IS NOT NULL)
);

CREATE TABLE IF NOT EXISTS {ESQUEMA}.reservas (
    item_id      text PRIMARY KEY,
    revisor      text NOT NULL,
    reservado_em timestamptz NOT NULL DEFAULT now()
);
"""


@dataclass(frozen=True)
class Conexao:
    host: str
    usuario: str
    banco: str = "revisao"


def conexao_padrao(instancia: str = "contrato-vivo") -> Conexao:
    """Na App, usa as variáveis injetadas pelo recurso de banco; fora dela, consulta a instância pela API."""
    if os.environ.get("PGHOST"):
        return Conexao(os.environ["PGHOST"], os.environ["PGUSER"], os.environ.get("PGDATABASE", "revisao"))
    from databricks.sdk import WorkspaceClient

    w = WorkspaceClient()
    host = w.database.get_database_instance(instancia).read_write_dns
    return Conexao(host, w.current_user.me().user_name)


def _token(instancia: str) -> str:
    from databricks.sdk import WorkspaceClient

    w = WorkspaceClient()
    if os.environ.get("PGHOST"):  # dentro da App: token do service principal
        return w.config.oauth_token().access_token
    return w.database.generate_database_credential(request_id=str(uuid.uuid4()), instance_names=[instancia]).token


@contextmanager
def conectar(conexao: Conexao | None = None, instancia: str = "contrato-vivo"):
    import psycopg

    conexao = conexao or conexao_padrao(instancia)
    with psycopg.connect(
        host=conexao.host,
        user=conexao.usuario,
        dbname=conexao.banco,
        password=_token(instancia),
        sslmode="require",
        autocommit=False,
    ) as conn:
        yield conn


def criar_tabelas(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(DDL)
    conn.commit()


def reservar(conn, item_ids: list[str], revisor: str) -> str | None:
    """Reserva o primeiro item livre da lista para o revisor; devolve o item reservado ou None."""
    with conn.cursor() as cur:
        cur.execute(
            f"DELETE FROM {ESQUEMA}.reservas WHERE reservado_em < now() - interval '{MINUTOS_DE_RESERVA} minutes'"
        )
        cur.execute(f"SELECT item_id FROM {ESQUEMA}.reservas WHERE revisor = %s", (revisor,))
        atual = cur.fetchone()
        if atual and atual[0] in item_ids:
            conn.commit()
            return atual[0]
        for item_id in item_ids:
            cur.execute(
                f"INSERT INTO {ESQUEMA}.reservas (item_id, revisor) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                (item_id, revisor),
            )
            if cur.rowcount == 1:
                cur.execute(f"DELETE FROM {ESQUEMA}.reservas WHERE revisor = %s AND item_id <> %s", (revisor, item_id))
                conn.commit()
                return item_id
    conn.commit()
    return None


def decidir(conn, item: dict, decisao: str, revisor: str, valor_corrigido: str | None = None) -> None:
    """Grava a decisão e libera a reserva, na mesma transação."""
    if decisao not in ("aprovado", "corrigido"):
        raise ValueError(decisao)
    if decisao == "corrigido" and not valor_corrigido:
        raise ValueError("Uma correção precisa do valor correto.")
    with conn.cursor() as cur:
        cur.execute(
            f"""
            INSERT INTO {ESQUEMA}.decisoes
                (item_id, documento_id, campo, motivo, valor_sugerido, decisao, valor_corrigido, revisor)
            VALUES (%(item_id)s, %(documento_id)s, %(campo)s, %(motivo)s, %(valor)s, %(decisao)s, %(corrigido)s,
                    %(revisor)s)
            ON CONFLICT (item_id) DO UPDATE SET
                decisao = EXCLUDED.decisao, valor_corrigido = EXCLUDED.valor_corrigido,
                revisor = EXCLUDED.revisor, decidido_em = now()
            """,
            {**item, "decisao": decisao, "corrigido": valor_corrigido, "revisor": revisor},
        )
        cur.execute(f"DELETE FROM {ESQUEMA}.reservas WHERE item_id = %s", (item["item_id"],))
    conn.commit()


def pular(conn, item_id: str, revisor: str) -> None:
    """Devolve o item à fila marcado como pulado, para o mesmo revisor não recebê-lo de novo em seguida."""
    with conn.cursor() as cur:
        cur.execute(f"DELETE FROM {ESQUEMA}.reservas WHERE item_id = %s", (item_id,))
        cur.execute(
            f"INSERT INTO {ESQUEMA}.reservas (item_id, revisor) VALUES (%s, %s) ON CONFLICT DO NOTHING",
            (item_id, f"pulado:{revisor}"),
        )
    conn.commit()


def decididos(conn) -> set[str]:
    with conn.cursor() as cur:
        cur.execute(f"SELECT item_id FROM {ESQUEMA}.decisoes")
        return {r[0] for r in cur.fetchall()}
