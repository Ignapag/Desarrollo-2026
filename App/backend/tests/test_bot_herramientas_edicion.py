"""El contrato real del proveedor puede expresar altas sin alterar otro ítem."""

import json

from app.modules.whatsapp.infrastructure import proveedores as p


async def test_herramienta_agregar_es_real_y_conserva_personalizacion(monkeypatch):
    def responder(solicitud, timeout):
        datos = json.loads(solicitud.data)
        nombres = {f["name"] for f in datos["tools"][0]["functionDeclarations"]}
        assert {
            "agregar_producto",
            "quitar_producto",
            "reemplazar_producto",
            "personalizar",
            "cancelar",
            "completar_edicion",
        } <= nombres
        return {
            "candidates": [
                {
                    "finishReason": "STOP",
                    "content": {
                        "parts": [
                            {
                                "functionCall": {
                                    "name": "agregar_producto",
                                    "args": {
                                        "producto": "Crispy",
                                        "cantidad": 1,
                                        "aclaraciones": "Sin bacon",
                                    },
                                }
                            }
                        ]
                    },
                }
            ]
        }

    monkeypatch.setattr(p, "_leer_json", responder)
    accion = await p.GeminiInterpretador("ficticia", "gemini-3.5-flash-lite").interpretar(
        "quiero agregar una crispy sin bacon", {}
    )
    assert accion["accion"] == "agregar_producto"
    assert accion["argumentos"]["aclaraciones"] == "Sin bacon"


def test_restaurar_receta_admite_aclaracion_vacia_sin_extras():
    assert p._argumentos_validos("personalizar", {"aclaraciones": "", "item_indice": 1})
    assert not p._argumentos_validos("agregar_producto", {"producto": "Crispy", "precio": 1})
