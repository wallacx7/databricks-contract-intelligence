from datetime import datetime

from contrato_vivo.reprocessar import MAX_TENTATIVAS, pendentes_sql, reenviar


def test_reenvia_copiando_para_pasta_com_carimbo(tmp_path):
    origem = tmp_path / "contratos" / "2021" / "CT-2021-000903.pdf"
    origem.parent.mkdir(parents=True)
    origem.write_bytes(b"%PDF-1.4 teste")

    destinos = reenviar([("CT-2021-000903", f"dbfs:{origem}")], tmp_path / "contratos", datetime(2026, 10, 6, 14, 0))

    assert destinos == [tmp_path / "contratos" / "reprocessar" / "20261006T140000" / "CT-2021-000903.pdf"]
    assert destinos[0].read_bytes() == origem.read_bytes()
    assert origem.exists()  # o original fica onde estava


def test_so_reenvia_quem_nunca_teve_sucesso_e_respeita_o_limite():
    sql = pendentes_sql("workspace", "lc_bronze")
    assert "count_if(erro_leitura IS NULL) = 0" in sql
    assert f"count(*) < {MAX_TENTATIVAS}" in sql
