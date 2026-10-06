"""Contrato Vivo: revisão humana dos campos extraídos, publicada como Databricks App.

Configuração por variáveis de ambiente (definidas no recurso da app no bundle):
CONTRATO_VIVO_CATALOG, CONTRATO_VIVO_SILVER, DATABRICKS_WAREHOUSE_ID e as variáveis PG* do recurso de banco.
"""

from __future__ import annotations

import io
import os

import pandas as pd
import pypdfium2 as pdfium
import streamlit as st
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.sql import StatementState

from contrato_vivo.revisao import banco

ROTULOS = {
    "tipo_documento": "Tipo de documento",
    "contrato_id": "Número do contrato",
    "numero_aditivo": "Número do aditivo",
    "codigo_cliente": "Código do cliente",
    "cliente": "Cliente",
    "data_assinatura": "Data de assinatura",
    "inicio_vigencia": "Início da vigência",
    "fim_vigencia": "Fim da vigência",
    "plano": "Plano",
    "preco_usuario": "Preço por usuário (R$)",
    "usuarios_contratados": "Usuários contratados",
    "periodicidade": "Periodicidade de pagamento",
    "desconto_anual_percentual": "Desconto por pagamento anual (%)",
    "desconto_promocional_percentual": "Desconto promocional (%)",
    "desconto_promocional_meses": "Prazo do desconto promocional (meses)",
    "reajuste_tipo": "Tipo de reajuste",
    "reajuste_percentual": "Reajuste anual (%)",
    "minimo_usuarios": "Compromisso mínimo de usuários",
    "multa_percentual": "Multa de rescisão (%)",
    "multa_limite_mensalidades": "Limite da multa (mensalidades)",
}
MOTIVOS = {"confianca_baixa": "Confiança baixa", "auditoria": "Auditoria por amostragem"}

st.set_page_config(page_title="Contrato Vivo", page_icon="📄", layout="wide")
w = WorkspaceClient()
TABELA_FILA = f"{os.environ['CONTRATO_VIVO_CATALOG']}.{os.environ['CONTRATO_VIVO_SILVER']}.fila_revisao"


def consultar(sql: str) -> pd.DataFrame:
    r = w.statement_execution.execute_statement(
        statement=sql, warehouse_id=os.environ["DATABRICKS_WAREHOUSE_ID"], wait_timeout="30s"
    )
    while r.status.state in (StatementState.PENDING, StatementState.RUNNING):
        r = w.statement_execution.get_statement(r.statement_id)
    if r.status.state != StatementState.SUCCEEDED:
        raise RuntimeError(r.status.error.message if r.status.error else r.status.state.value)
    colunas = [c.name for c in r.manifest.schema.columns]
    return pd.DataFrame((r.result.data_array if r.result else None) or [], columns=colunas)


@st.cache_data(ttl=300)
def fila() -> pd.DataFrame:
    return consultar(
        f"SELECT item_id, documento_id, campo, tipo, valor, valor_segundo_modelo, pagina, concordam, ancorado, "
        f"valido, motivo, path FROM {TABELA_FILA} ORDER BY motivo DESC, documento_id, campo"
    )


@st.cache_data(ttl=3600)
def pagina_do_pdf(path: str, pagina: int) -> bytes:
    conteudo = w.files.download(path.removeprefix("dbfs:")).contents.read()
    doc = pdfium.PdfDocument(conteudo)
    indice = max(0, min(pagina - 1, len(doc) - 1))
    imagem = doc[indice].render(scale=1.6).to_pil()
    saida = io.BytesIO()
    imagem.save(saida, format="PNG")
    return saida.getvalue()


def sinal(nome: str, valor) -> str:
    if valor in (None, "", "None"):
        return f"⚪ {nome}: não se aplica"
    return f"{'🟢' if str(valor).lower() == 'true' else '🔴'} {nome}"


def pagina_revisao() -> None:
    revisor = st.context.headers.get("X-Forwarded-Email") or os.environ.get("USER", "revisor")
    st.title("Revisão de contratos")

    itens = fila()
    with banco.conectar() as conn:
        feitos = banco.decididos(conn)
        pendentes = itens[~itens["item_id"].isin(feitos)]

        total, auditoria = len(itens), (itens["motivo"] == "auditoria").sum()
        c1, c2, c3 = st.columns(3)
        c1.metric("Na fila", len(pendentes), help="Campos ainda sem decisão")
        c2.metric("Revisados", len(feitos & set(itens["item_id"])))
        c3.metric("Da auditoria", f"{auditoria} de {total}", help="Amostra de campos de confiança alta")

        if pendentes.empty:
            st.success("Não há campos para revisar. Bom trabalho.")
            st.stop()

        item_id = banco.reservar(conn, pendentes["item_id"].tolist(), revisor)
        if item_id is None:
            st.info("Todos os campos pendentes estão sendo revisados por outras pessoas agora.")
            st.stop()
        item = pendentes[pendentes["item_id"] == item_id].iloc[0].to_dict()

        esquerda, direita = st.columns([1.3, 1])
        pagina = int(item["pagina"]) if item["pagina"] not in (None, "", "None") else 1
        with esquerda:
            st.caption(f"{item['documento_id']} · página {pagina}")
            st.image(pagina_do_pdf(item["path"], pagina), use_container_width=True)
        with direita:
            st.caption(MOTIVOS[item["motivo"]])
            st.subheader(ROTULOS.get(item["campo"], item["campo"]))
            st.markdown(f"**Valor extraído:** `{item['valor']}`")
            st.markdown(f"Segundo modelo: `{item['valor_segundo_modelo']}`")
            st.markdown(
                "  \n".join(
                    [
                        sinal("Os dois modelos concordam", item["concordam"]),
                        sinal("Valor escrito no documento", item["ancorado"]),
                        sinal("Formato válido", item["valido"]),
                    ]
                )
            )
            registro = {k: item[k] for k in ("item_id", "documento_id", "campo", "motivo", "valor")}
            if st.button("Aprovar", type="primary", use_container_width=True):
                banco.decidir(conn, registro, "aprovado", revisor)
                st.rerun()
            with st.form("corrigir", clear_on_submit=True):
                correto = st.text_input("Valor correto", placeholder="Como está no contrato")
                if st.form_submit_button("Corrigir", use_container_width=True):
                    if correto.strip():
                        banco.decidir(conn, registro, "corrigido", revisor, correto.strip())
                        st.rerun()
                    else:
                        st.warning("Informe o valor correto para registrar a correção.")
            if st.button("Pular", use_container_width=True):
                banco.pular(conn, item_id, revisor)
                st.rerun()


@st.cache_resource
def agente():
    from contrato_vivo.agente.backends import BuscaVetorial, DatabricksChatModel, WarehouseRunner
    from contrato_vivo.agente.nucleo import AgenteDeContratos, Configuracao

    catalogo = os.environ["CONTRATO_VIVO_CATALOG"]
    return AgenteDeContratos(
        DatabricksChatModel(os.environ.get("CONTRATO_VIVO_MODELO", "databricks-gpt-oss-120b")),
        WarehouseRunner(os.environ["DATABRICKS_WAREHOUSE_ID"], w),
        BuscaVetorial(os.environ["CONTRATO_VIVO_INDICE"], w),
        Configuracao(
            f"{catalogo}.{os.environ['CONTRATO_VIVO_GOLD']}", f"{catalogo}.{os.environ['CONTRATO_VIVO_SILVER']}"
        ),
    )


EXEMPLOS = [
    "Qual é a multa por rescisão antecipada do contrato da Foco Engenharia S.A.?",
    "Qual o preço por usuário em vigor hoje no contrato CT-2021-000308?",
    "Quanto o contrato CT-2021-000036 deixou de faturar e por quê?",
]


def pagina_perguntas() -> None:
    st.title("Pergunte aos contratos")
    st.caption("Cada resposta cita o documento e a página de onde a informação veio.")
    if "conversa" not in st.session_state:
        st.session_state.conversa = []
    with st.sidebar:
        st.caption("Experimente")
        for exemplo in EXEMPLOS:
            if st.button(exemplo, use_container_width=True):
                st.session_state.pendente = exemplo
        if st.button("Nova conversa", use_container_width=True):
            st.session_state.conversa = []
    for msg in st.session_state.conversa:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if msg.get("passos"):
                with st.expander(f"Como cheguei nisso · {len(msg['passos'])} consultas"):
                    for i, passo in enumerate(msg["passos"], 1):
                        st.markdown(f"**{i}. {passo['ferramenta']}** `{passo['argumentos']}`")
                        if passo["erro"]:
                            st.warning(passo["erro"])
                        elif passo["linhas"]:
                            st.dataframe(pd.DataFrame(passo["linhas"]), hide_index=True, use_container_width=True)
    pergunta = st.chat_input("Pergunte sobre multas, preços, vigência, reajuste ou vazamento")
    pergunta = pergunta or st.session_state.pop("pendente", None)
    if not pergunta:
        return
    st.session_state.conversa.append({"role": "user", "content": pergunta})
    historico = [{"role": m["role"], "content": m["content"]} for m in st.session_state.conversa[:-1]][-6:]
    with st.spinner("Lendo os contratos..."):
        r = agente().perguntar(pergunta, historico)
    passos = [
        {"ferramenta": p.ferramenta, "argumentos": p.argumentos, "erro": p.erro, "linhas": (p.linhas or [])[:20]}
        for p in r.passos
    ]
    st.session_state.conversa.append({"role": "assistant", "content": r.texto, "passos": passos})
    st.rerun()


st.navigation(
    [
        st.Page(pagina_revisao, title="Revisão", icon="✅", url_path="revisao"),
        st.Page(pagina_perguntas, title="Perguntas", icon="💬", url_path="perguntas"),
    ]
).run()
