from contrato_vivo.revisao.banco import DDL
from contrato_vivo.revisao.simulado import decidir_item


def test_revisor_simulado_aprova_o_certo_e_corrige_o_errado():
    assert decidir_item({"valor": "99.00", "esperado": "99.00"}) == ("aprovado", None)
    assert decidir_item({"valor": "m-002362", "esperado": "nim-002362"}) == ("corrigido", "nim-002362")
    assert decidir_item({"valor": "1", "esperado": None}) == ("corrigido", "(vazio)")


def test_banco_exige_valor_na_correcao_e_motivo_conhecido():
    assert "CHECK (decisao = 'aprovado' OR valor_corrigido IS NOT NULL)" in DDL
    assert "CHECK (motivo IN ('confianca_baixa', 'auditoria'))" in DDL
