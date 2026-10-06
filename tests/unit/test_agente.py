from __future__ import annotations

import json

import pytest

from contrato_vivo.agente.ferramentas import ErroDeFerramenta, apresentar, consulta, contrato_valido
from contrato_vivo.agente.nucleo import AgenteDeContratos, Configuracao, LlmReply, ToolCall

CONFIG = Configuracao(gold_schema="w.gold", silver_schema="w.silver", max_passos=3)


class SqlFalso:
    def __init__(self, linhas):
        self.linhas, self.chamadas = linhas, []

    def run(self, sql, params):
        self.chamadas.append((sql, params))
        return self.linhas


class BuscaFalsa:
    def __init__(self):
        self.chamadas = []

    def buscar(self, consulta, contrato_id, limite=5):
        self.chamadas.append((consulta, contrato_id))
        return [{"documento_id": contrato_id, "pagina": 2, "texto": "multa de 30% ..."}]


class ModeloRoteirizado:
    def __init__(self, respostas):
        self.respostas, self.vistas = respostas, []

    def complete(self, messages, tools, allow_tools=True):
        self.vistas.append([dict(m) for m in messages])
        return self.respostas.pop(0)


def chamar(nome, **argumentos):
    return ToolCall(id=f"c_{nome}", name=nome, arguments=json.dumps(argumentos))


def test_valida_numero_de_contrato():
    assert contrato_valido(" ct-2024-000123 ") == "CT-2024-000123"
    for invalido in ("CT-2024-123", "Alfa Logística", "CT-2024-000123'; DROP TABLE x; --"):
        with pytest.raises(ErroDeFerramenta):
            contrato_valido(invalido)


def test_consultas_sao_parametrizadas():
    sql, params = consulta("localizar_contrato", {"cliente": "Alfa"}, "w.gold", "w.silver")
    assert ":cliente" in sql and params == {"cliente": "Alfa"} and "Alfa" not in sql
    sql, params = consulta("vazamento_do_contrato", {"contrato_id": "ct-2024-000123"}, "w.gold", "w.silver")
    assert params == {"contrato_id": "CT-2024-000123"} and "CT-2024" not in sql


def test_apresenta_valores_formatados():
    assert apresentar({"campo": "preco_usuario", "valor": "1234.5", "pagina": 2}) == {
        "campo": "preco_usuario",
        "valor": "R$ 1.234,50",
        "pagina": 2,
    }
    assert apresentar({"campo": "multa_percentual", "valor": "30.0"})["valor"] == "30%"
    assert apresentar({"vazamento_acumulado": 98400.0})["vazamento_acumulado"] == "R$ 98.400,00"


def test_agente_localiza_busca_e_responde():
    sql = SqlFalso([{"contrato_id": "CT-2024-000123", "cliente": "alfa logística ltda"}])
    busca = BuscaFalsa()
    modelo = ModeloRoteirizado(
        [
            LlmReply(None, [chamar("localizar_contrato", cliente="Alfa")]),
            LlmReply(None, [chamar("buscar_clausulas", contrato_id="CT-2024-000123", assunto="multa rescisão")]),
            LlmReply("A multa é de 30% (CT-2024-000123, p. 2).", []),
        ]
    )
    r = AgenteDeContratos(modelo, sql, busca, CONFIG).perguntar("Qual a multa da Alfa?")
    assert r.texto.startswith("A multa é de 30%")
    assert [p.ferramenta for p in r.passos] == ["localizar_contrato", "buscar_clausulas"]
    assert busca.chamadas == [("multa rescisão", "CT-2024-000123")]


def test_erro_de_argumento_volta_ao_modelo():
    modelo = ModeloRoteirizado(
        [LlmReply(None, [chamar("termos_do_contrato", contrato_id="Alfa")]), LlmReply("Corrigido.", [])]
    )
    r = AgenteDeContratos(modelo, SqlFalso([]), BuscaFalsa(), CONFIG).perguntar("Termos da Alfa?")
    assert r.passos[0].erro and "localizar_contrato" in r.passos[0].erro
    assert "erro" in json.loads(modelo.vistas[1][-1]["content"])


def test_avaliacao_confere_valor_e_pagina_citada():
    from contrato_vivo.agente.avaliacao import Caso, conferir
    from contrato_vivo.agente.nucleo import Resposta

    caso = Caso("multa_01", "multa", "?", valores=[30.0, 6], documento="CT-2024-000123", paginas=[2])
    certo = conferir(caso, Resposta("?", "A multa é de 30%, limitada a 6 mensalidades (CT-2024-000123, p. 2)."))
    assert certo.valor_ok and certo.citacao_ok and certo.acertou
    pagina_errada = conferir(caso, Resposta("?", "A multa é de 30%, até 6 mensalidades (CT-2024-000123, p. 1)."))
    assert pagina_errada.valor_ok and pagina_errada.citacao_ok is False and not pagina_errada.acertou
    recusa = Caso("x", "fora_do_escopo", "?", recusa=True)
    assert conferir(recusa, Resposta("?", "Não encontrei essa informação nos contratos.")).acertou


def test_hifen_tipografico_e_datas_formatadas():
    from contrato_vivo.agente.avaliacao import Caso, conferir
    from contrato_vivo.agente.nucleo import Resposta

    caso = Caso("v", "vigencia", "?", textos=["09/02/2023"], documento="CT-2021-000310", paginas=[2])
    r = conferir(caso, Resposta("?", "Termina em 09/02/2023 (CT‑2021‑000310, p. 2)."))
    assert r.valor_ok and r.citacao_ok
    assert apresentar({"campo": "fim_vigencia", "valor": "2023-02-09"})["valor"] == "09/02/2023"
