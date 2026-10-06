"""Gera os contratos em PDF e o gabarito a partir do billing do Ledger.

No Databricks (job do bundle), lê as tabelas Silver do Ledger com Spark:
    contrato-vivo-gerar --ledger-catalog workspace --ledger-schema <schema_silver_do_ledger> \\
        --saida /Volumes/.../contratos --gabarito /Volumes/.../gabarito

Saída:
    contratos/<ano>/<documento_id>.pdf
    gabarito/documentos.jsonl   valor correto de cada campo de cada documento e páginas onde aparece
    gabarito/vazamentos.csv     vazamento mensal esperado por contrato e tipo
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import shutil
import time
from dataclasses import asdict
from datetime import date
from pathlib import Path

from pypdf import PdfReader

from contrato_vivo.gerador.digitalizar import digitalizar, sortear_nivel
from contrato_vivo.gerador.extenso import data_curta, data_longa, percentual, reais
from contrato_vivo.gerador.pdf import renderizar
from contrato_vivo.gerador.termos import Documento, Resultado, gerar


def paginas_dos_campos(doc: Documento, pdf: bytes) -> dict[str, list[int]]:
    """Páginas (a partir de 1) em que o valor de cada campo aparece escrito; usado para avaliar citações."""
    paginas = [p.extract_text().replace("\n", " ") for p in PdfReader(io.BytesIO(pdf)).pages]
    procurar = {
        "preco_usuario": [reais(doc.preco_usuario)],
        "multa_percentual": [f"multa de {percentual(doc.multa_percentual)}"] if doc.multa_percentual else [],
        "fim_vigencia": [data_curta(doc.fim_vigencia), data_longa(doc.fim_vigencia)] if doc.fim_vigencia else [],
        "desconto_promocional_percentual": ["desconto promocional"] if doc.desconto_promocional_percentual else [],
        "reajuste_tipo": ["reajustado anualmente", "tabela vigente"],
        "minimo_usuarios": ["faturamento mínimo"] if doc.minimo_usuarios else [],
    }
    return {
        campo: sorted({i for i, texto in enumerate(paginas, 1) for termo in termos if termo in texto})
        for campo, termos in procurar.items()
        if termos
    }


def escrever(resultado: Resultado, saida: Path, gabarito: Path) -> dict[str, int]:
    for pasta in (saida, gabarito):
        shutil.rmtree(pasta / "_tmp", ignore_errors=True)
    for ano_dir in saida.glob("[0-9][0-9][0-9][0-9]"):
        shutil.rmtree(ano_dir, ignore_errors=True)  # geração anterior
    shutil.rmtree(saida / "reprocessar", ignore_errors=True)  # cópias de reprocessamento da geração anterior
    gabarito.mkdir(parents=True, exist_ok=True)

    paginas_total = digitalizados = 0
    with open(gabarito / "documentos.jsonl", "w", encoding="utf-8") as fh:
        for doc in resultado.documentos:
            pdf = renderizar(doc)
            paginas = paginas_dos_campos(doc, pdf)  # antes de digitalizar: o PDF escaneado não tem texto
            nivel = sortear_nivel(doc.documento_id)
            if nivel:
                pdf = digitalizar(pdf, nivel, doc.documento_id)
                digitalizados += 1
            destino = saida / str(doc.data_assinatura.year) / f"{doc.documento_id}.pdf"
            destino.parent.mkdir(parents=True, exist_ok=True)
            destino.write_bytes(pdf)
            registro = {
                **doc.campos_esperados(),
                "arquivo": f"{doc.data_assinatura.year}/{doc.documento_id}.pdf",
                "modelo": doc.modelo,
                "digitalizado": nivel,
                "vazamento_plantado": doc.vazamento_plantado,
                "paginas": paginas,
            }
            paginas_total += len(PdfReader(io.BytesIO(pdf)).pages)
            fh.write(json.dumps(registro, ensure_ascii=False) + "\n")

    with open(gabarito / "vazamentos.csv", "w", encoding="utf-8", newline="") as fh:
        campos = list(asdict(resultado.vazamentos[0])) if resultado.vazamentos else []
        writer = csv.DictWriter(fh, fieldnames=campos)
        writer.writeheader()
        for v in resultado.vazamentos:
            linha = asdict(v)
            linha["mes"] = v.mes.isoformat()
            writer.writerow(linha)
    return {
        "documentos": len(resultado.documentos),
        "digitalizados": digitalizados,
        "paginas": paginas_total,
        "linhas_de_vazamento": len(resultado.vazamentos),
    }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Gera contratos em PDF e o gabarito a partir do billing do Ledger.")
    parser.add_argument("--ledger-catalog", default="workspace")
    parser.add_argument("--ledger-schema", required=True, help="Schema Silver do Ledger (contas e assinaturas).")
    parser.add_argument("--saida", type=Path, required=True, help="Destino dos PDFs.")
    parser.add_argument("--gabarito", type=Path, required=True, help="Destino do gabarito.")
    parser.add_argument("--ultimo-mes", type=date.fromisoformat, default=date(2026, 9, 1),
                        help="Último mês fechado do billing.")  # fmt: skip
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--limite",
        type=lambda v: int(v) if v else None,  # vazio = todas as contas (parâmetro opcional do job)
        default=None,
        help="Gera só para as N primeiras contas.",
    )
    args = parser.parse_args(argv)

    from pyspark.sql import SparkSession

    from contrato_vivo.gerador.fontes import de_tabelas

    t0 = time.perf_counter()
    contas, versoes = de_tabelas(SparkSession.builder.getOrCreate(), args.ledger_catalog, args.ledger_schema)
    resultado = gerar(contas, versoes, args.ultimo_mes, seed=args.seed, limite=args.limite)
    resumo = escrever(resultado, args.saida, args.gabarito)
    plantados = sum(1 for d in resultado.documentos if d.vazamento_plantado)
    print(
        f"{resumo['documentos']} documentos ({resumo['digitalizados']} digitalizados, {resumo['paginas']} páginas), "
        f"{plantados} contratos com vazamento "
        f"plantado, {resumo['linhas_de_vazamento']} meses com vazamento. {time.perf_counter() - t0:.0f} s"
    )


if __name__ == "__main__":
    main()
