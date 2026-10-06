import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2] / "src" / "pipelines" / "leitura"))

from esquema import CAMPOS, json_schema, struct_ddl  # noqa: E402

from contrato_vivo.gerador.termos import Documento  # noqa: E402


def test_esquema_cobre_todos_os_campos_do_gabarito():
    gabarito = {f for f in Documento.__dataclass_fields__} - {
        "documento_id",
        "modelo",
        "vazamento_plantado",
        "account_id",
        "uf",
        "setor",
    }
    gabarito = {"tipo_documento" if f == "tipo" else f for f in gabarito}
    assert gabarito == set(CAMPOS)


def test_json_schema_e_estrito_e_aceita_nulos():
    schema = json.loads(json_schema())["json_schema"]
    assert schema["strict"] is True
    props = schema["schema"]["properties"]
    assert set(schema["schema"]["required"]) == set(CAMPOS)
    assert all("null" in p["type"] for p in props.values())
    assert props["reajuste_tipo"]["enum"] == ["tabela", "fixo", None]


def test_struct_ddl_tem_um_tipo_por_campo():
    assert struct_ddl().count(",") == len(CAMPOS) - 1
    assert "preco_usuario DOUBLE" in struct_ddl() and "usuarios_contratados INT" in struct_ddl()


def test_formatos_de_identificadores():
    import re

    from esquema import FORMATOS

    assert re.match(FORMATOS["codigo_cliente"], "nim-002362")
    assert not re.match(FORMATOS["codigo_cliente"], "m-002362")  # o caso real do OCR
    assert re.match(FORMATOS["contrato_id"], "ct-2022-002362")
    assert not re.match(FORMATOS["contrato_id"], "ct-2022-00236")
