"""Avaliação do agente de contratos contra o gabarito do gerador.

Cada pergunta é conferida em duas dimensões:
- valor: o número ou a data esperada aparece na resposta;
- citação: a resposta cita o documento certo e uma página onde o valor está de fato escrito.

Uso:
    contrato-vivo-avaliar-agente --gold <schema> --silver <schema> --warehouse-id <id> --indice <nome>
"""

from __future__ import annotations

import argparse
import json
import random
import re
import statistics
import sys
from dataclasses import asdict, dataclass, field
from datetime import date

from contrato_vivo.agente.nucleo import RECUSA, Resposta

_MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro",
          "novembro", "dezembro"]  # fmt: skip
_NUMERO = re.compile(r"(\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+(?:,\d+)?)")


def numeros(texto: str) -> list[float]:
    return [float(n.replace(".", "").replace(",", ".")) for n in _NUMERO.findall(texto)]


def formatos_de_data(d: date) -> list[str]:
    dia = "1º" if d.day == 1 else str(d.day)
    return [d.strftime("%d/%m/%Y"), f"{dia} de {_MESES[d.month - 1]} de {d.year}", f"{d.day} de {_MESES[d.month - 1]}"]


@dataclass
class Caso:
    id: str
    categoria: str
    pergunta: str
    valores: list[float] = field(default_factory=list)  # todos precisam aparecer
    textos: list[str] = field(default_factory=list)  # pelo menos um precisa aparecer
    documento: str | None = None  # documento que precisa ser citado
    paginas: list[int] = field(default_factory=list)  # páginas aceitas na citação
    recusa: bool = False


@dataclass
class Resultado:
    id: str
    categoria: str
    pergunta: str
    valor_ok: bool
    citacao_ok: bool | None
    resposta: str
    ferramentas: list[str]
    segundos: float
    tokens: int

    @property
    def acertou(self) -> bool:
        return self.valor_ok and self.citacao_ok is not False


def conferir(caso: Caso, r: Resposta) -> Resultado:
    texto = r.texto
    if caso.recusa:
        valor_ok, citacao_ok = RECUSA.lower() in texto.lower(), None
    else:
        achados = numeros(texto)
        valor_ok = all(any(abs(n - v) < 0.011 for n in achados) for v in caso.valores)
        if caso.textos:
            valor_ok = valor_ok and any(t.lower() in texto.lower() for t in caso.textos)
        citacao_ok = None
        if caso.documento:
            citadas = {int(p) for doc, p in re.findall(r"(CT-\d{4}-\d{6}(?:-A\d+)?)[^)]*?p\.\s*(\d+)", texto)
                       if doc == caso.documento}  # fmt: skip
            citacao_ok = bool(citadas & set(caso.paginas)) if caso.paginas else caso.documento in texto
    return Resultado(caso.id, caso.categoria, caso.pergunta, valor_ok, citacao_ok, texto,
                     [p.ferramenta for p in r.passos], r.segundos, r.tokens)  # fmt: skip


def gerar_casos(
    documentos: list[dict], vazamentos: dict[str, float], n_contratos: int = 12, seed: int = 7
) -> list[Caso]:
    """Perguntas a partir do gabarito; só clientes de nome único, para a pergunta não ser ambígua."""
    por_contrato: dict[str, list[dict]] = {}
    for d in documentos:
        por_contrato.setdefault(d["contrato_id"], []).append(d)
    nomes = [d["cliente"] for d in documentos if d["tipo"] == "contrato"]
    unicos = {n for n in nomes if nomes.count(n) == 1}
    candidatos = sorted(c for c, docs in por_contrato.items() if docs[0]["cliente"] in unicos)
    rng = random.Random(seed)
    com_aditivo = [c for c in candidatos if len(por_contrato[c]) > 1]
    com_vazamento = [c for c in candidatos if c in vazamentos]
    escolhidos = sorted(set(rng.sample(candidatos, n_contratos) + rng.sample(com_aditivo, 4)
                            + rng.sample(com_vazamento, 4)))  # fmt: skip

    casos: list[Caso] = []

    def add(categoria: str, **kw) -> None:
        casos.append(Caso(id=f"{categoria}_{len(casos) + 1:02d}", categoria=categoria, **kw))

    for cid in escolhidos:
        docs = sorted(por_contrato[cid], key=lambda d: d["inicio_vigencia"])
        base, vigente = docs[0], docs[-1]
        cliente = base["cliente"]
        add("multa", pergunta=f"Qual é a multa por rescisão antecipada do contrato {cid}?",
            valores=[base["multa_percentual"], base["multa_limite_mensalidades"]],
            documento=base["documento_id"], paginas=base["paginas"].get("multa_percentual", []))  # fmt: skip
        add("preco_vigente", pergunta=f"Qual é o preço por usuário em vigor hoje no contrato da {cliente}?",
            valores=[vigente["preco_usuario"]], documento=vigente["documento_id"],
            paginas=vigente["paginas"].get("preco_usuario", []))  # fmt: skip
        if base["fim_vigencia"]:
            fim = date.fromisoformat(base["fim_vigencia"])
            add("vigencia", pergunta=f"Até quando vai a vigência do contrato {cid}?", textos=formatos_de_data(fim),
                documento=base["documento_id"], paginas=base["paginas"].get("fim_vigencia", []))  # fmt: skip
        if base["minimo_usuarios"]:
            add("minimo", pergunta=f"O contrato {cid} tem compromisso mínimo de usuários?",
                valores=[base["minimo_usuarios"]], documento=base["documento_id"],
                paginas=base["paginas"].get("minimo_usuarios", []))  # fmt: skip
        if cid in vazamentos:
            add("vazamento", pergunta=f"Quanto o contrato {cid} deixou de faturar até agora?",
                valores=[round(vazamentos[cid], 2)])  # fmt: skip

    for pergunta in [
        "Qual é o telefone do responsável financeiro da Nimbus?",
        "Qual contrato da Nimbus é com a Microsoft?",
        "Quais clientes devemos processar judicialmente?",
        "Qual será o faturamento da Nimbus em 2030?",
    ]:
        add("fora_do_escopo", pergunta=pergunta, recusa=True)
    return casos


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Avalia o agente de contratos contra o gabarito.")
    parser.add_argument("--catalog", default="workspace")
    parser.add_argument("--gold", required=True)
    parser.add_argument("--silver", required=True)
    parser.add_argument("--raw", required=True)
    parser.add_argument("--warehouse-id", required=True)
    parser.add_argument("--indice", required=True)
    parser.add_argument("--modelo", default="databricks-gpt-oss-120b")
    parser.add_argument("--experimento", default=None)
    parser.add_argument("--saida", default="avaliacao_agente.json")
    args = parser.parse_args(argv)

    from databricks.sdk import WorkspaceClient

    from contrato_vivo.agente.backends import BuscaVetorial, DatabricksChatModel, WarehouseRunner
    from contrato_vivo.agente.nucleo import AgenteDeContratos, Configuracao

    w = WorkspaceClient()
    gabarito = f"/Volumes/{args.catalog}/{args.raw}/gabarito"
    conteudo = w.files.download(f"{gabarito}/documentos.jsonl").contents.read().decode("utf-8")
    documentos = [json.loads(linha) for linha in conteudo.splitlines()]
    sql = WarehouseRunner(args.warehouse_id, w)
    ultimo = sql.run(f"SELECT max(mes) AS m FROM {args.catalog}.{args.gold}.termos_mensais", {})[0]["m"]
    vaz = sql.run(
        f"SELECT contrato_id, sum(CAST(vazamento AS DOUBLE)) AS total FROM read_files('{gabarito}/vazamentos.csv', "
        f"format => 'csv', header => true) WHERE CAST(mes AS DATE) <= DATE'{ultimo}' GROUP BY contrato_id",
        {},
    )
    casos = gerar_casos(documentos, {v["contrato_id"]: v["total"] for v in vaz})
    agente = AgenteDeContratos(
        DatabricksChatModel(args.modelo),
        sql,
        BuscaVetorial(args.indice, w),
        Configuracao(f"{args.catalog}.{args.gold}", f"{args.catalog}.{args.silver}"),
    )

    resultados = []
    for caso in casos:
        r = conferir(caso, agente.perguntar(caso.pergunta))
        resultados.append(r)
        marca = "ok  " if r.acertou else "ERRO"
        cit = {True: "citação ok", False: "citação errada", None: ""}[r.citacao_ok]
        print(f"[{marca}] {r.id:<18} {r.segundos:5.1f}s {cit:<15} {r.pergunta}")

    por_categoria: dict[str, list[Resultado]] = {}
    for r in resultados:
        por_categoria.setdefault(r.categoria, []).append(r)
    com_citacao = [r for r in resultados if r.citacao_ok is not None]
    resumo = {
        "acerto": sum(r.acertou for r in resultados) / len(resultados),
        "acertos": sum(r.acertou for r in resultados),
        "perguntas": len(resultados),
        "citacao_correta": sum(r.citacao_ok for r in com_citacao) / max(1, len(com_citacao)),
        "latencia_p50_s": statistics.median(r.segundos for r in resultados),
        **{f"acerto_{c}": sum(r.acertou for r in rs) / len(rs) for c, rs in por_categoria.items()},
    }
    print(f"\nAcerto: {resumo['acertos']}/{resumo['perguntas']} ({resumo['acerto']:.1%})")
    for chave, valor in resumo.items():
        if chave.startswith("acerto_"):
            print(f"  {chave.removeprefix('acerto_'):<16} {valor:.0%}")
    print(f"Citação na página certa: {resumo['citacao_correta']:.0%} · latência p50 {resumo['latencia_p50_s']:.1f} s")

    with open(args.saida, "w", encoding="utf-8") as fh:
        json.dump({"resumo": resumo, "resultados": [asdict(r) for r in resultados]}, fh, ensure_ascii=False, indent=2)
    if args.experimento:
        import mlflow

        mlflow.set_tracking_uri("databricks")
        mlflow.set_experiment(args.experimento)
        with mlflow.start_run(run_name=f"agente_{args.modelo}"):
            mlflow.log_metrics({k: float(v) for k, v in resumo.items()})
            mlflow.log_artifact(args.saida)
    if resumo["acerto"] < 0.0:
        sys.exit(1)


if __name__ == "__main__":
    main()
