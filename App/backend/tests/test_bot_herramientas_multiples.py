"""Planes del proveedor: todas las operaciones se validan antes de ejecutarlas."""

import json

import pytest

from app.modules.whatsapp.infrastructure import proveedores as p


def _respuesta(accion, argumentos):
    return {"candidates": [{"finishReason": "STOP", "content": {"parts": [
        {"functionCall": {"name": accion, "args": argumentos}},
    ]}}]}


async def test_gemini_conserva_producto_y_direccion_en_una_herramienta(monkeypatch):
    operaciones = [
        {"accion": "agregar_producto", "argumentos": {
            "producto": "Crispy", "cantidad": 1, "aclaraciones": "Sin bacon",
        }},
        {"accion": "datos", "argumentos": {
            "tipo_entrega": "delivery", "direccion": "calle 52", "numero": "32",
            "localidad": "Ensenada",
        }},
    ]

    def responder(solicitud, timeout):
        datos = json.loads(solicitud.data)
        herramientas = {f["name"]: f for f in datos["tools"][0]["functionDeclarations"]}
        assert "editar_pedido" in herramientas
        instrucciones = datos["systemInstruction"]["parts"][0]["text"]
        assert "pedido original" in instrucciones
        assert "Ensenada" in instrucciones
        assert "varias operaciones independientes, usá humano" not in instrucciones
        assert 256 < datos["generationConfig"]["maxOutputTokens"] <= 768
        return _respuesta("editar_pedido", {"operaciones": operaciones})

    monkeypatch.setattr(p, "_leer_json", responder)
    resultado = await p.GeminiInterpretador("ficticia", "gemini-3.5-flash-lite").interpretar(
        "quiero agregar una crispy sin bacon y que me lo envien a ensenada calle 52 n 32", {},
    )
    assert resultado == {"accion": "editar_pedido", "argumentos": {"operaciones": operaciones}}


@pytest.mark.parametrize("operaciones", [
    [], [{"accion": "cantidad", "argumentos": {"cantidad": 1}}] * 9,
    [{"accion": "confirmar", "argumentos": {}}],
    [{"accion": "humano", "argumentos": {}}],
    [{"accion": "cancelar", "argumentos": {}}],
    [{"accion": "editar_pedido", "argumentos": {"operaciones": []}}],
    [{"accion": "completar_edicion", "argumentos": {"variante": "Doble"}}],
    [{"accion": "cantidad", "argumentos": {"cantidad": True}}],
    [{"accion": "quitar_producto", "argumentos": {"item_indice": True}}],
    [{"accion": "datos", "argumentos": {}}],
    [{"accion": "agregar_producto", "argumentos": {"producto": "Crispy", "precio": 1}}],
    [{"accion": "cantidad", "argumentos": {"cantidad": 2}, "extra": 1}],
    [{"accion": "cantidad", "argumentos": {"cantidad": 2}},
     {"accion": "datos", "argumentos": {"metodo_pago": "tarjeta"}}],
    [{"accion": "cantidad"}],
    [{"accion": [], "argumentos": {}}],
    [None], "no es una lista",
])
async def test_plan_invalido_rechaza_todo_sin_devolver_una_parte(monkeypatch, operaciones):
    monkeypatch.setattr(p, "_leer_json", lambda *_: _respuesta(
        "editar_pedido", {"operaciones": operaciones},
    ))
    resultado = await p.GeminiInterpretador("ficticia", "gemini-3.5-flash-lite").interpretar(
        "dos cambios", {},
    )
    assert resultado["accion"] == "humano"
    assert resultado["causa_proveedor"] == "ARGUMENTOS"


@pytest.mark.parametrize("accion,argumentos", [
    ("agregar_producto", {"producto": "Crispy"}),
    ("quitar_producto", {"item_indice": 2}),
    ("reemplazar_producto", {"producto": "Cheese", "item_indice": 1}),
    ("cambiar_variante", {"item_indice": 1, "variante": "Doble"}),
    ("personalizar", {"item_indice": 1, "aclaraciones": ""}),
    ("cantidad", {"item_indice": 1, "cantidad": 2}),
    ("quitar_ingrediente", {"item_indice": 1, "ingrediente": "tomate"}),
    ("datos", {"tipo_entrega": "retiro"}),
])
def test_plan_admite_acciones_existentes_sin_exigir_datos_que_cliente_no_dio(accion, argumentos):
    assert p._argumentos_validos("editar_pedido", {
        "operaciones": [{"accion": accion, "argumentos": argumentos}],
    })
    assert p._argumentos_validos("accion_inexistente", {}) is False
    assert p._argumentos_validos("editar_pedido", {"operaciones": [], "precio": 1}) is False


async def test_completar_edicion_admite_datos_sin_perder_producto_pendiente(monkeypatch):
    argumentos = {"direccion": "calle 52", "numero": "32", "localidad": "Ensenada",
                  "referencias": "timbre", "tipo_entrega": "delivery", "metodo_pago": "efectivo"}
    monkeypatch.setattr(p, "_leer_json", lambda *_: _respuesta("completar_edicion", argumentos))
    resultado = await p.GeminiInterpretador("ficticia", "gemini-3.5-flash-lite").interpretar(
        "Ensenada calle 52 número 32", {"edicion_pendiente": {
            "accion": "datos", "argumentos": {},
        }},
    )
    assert resultado == {"accion": "completar_edicion", "argumentos": argumentos}


def test_contexto_pendiente_expone_solo_nombres_datos_y_opcion_activa():
    seguro = p._contexto_acotado({"edicion_pendiente": {
        "accion": "datos", "argumentos": {"direccion": "privado", "numero": "32"},
        "datos_presentes": ["direccion", "numero", "telefono", "direccion", None],
        "operaciones": [{"accion": "datos", "argumentos": {"localidad": "privado"}}],
    }})
    assert seguro["edicion_pendiente"] == {
        "accion": "datos", "argumentos": {}, "datos_presentes": ["direccion", "numero"],
    }
    assert "privado" not in json.dumps(seguro)


def test_plan_admite_hasta_ocho_operaciones_y_rechaza_campos_globales():
    operaciones = [{"accion": "cantidad", "argumentos": {
        "cantidad": 2, "item_indice": indice,
    }} for indice in range(1, 9)]
    assert p._argumentos_validos("editar_pedido", {"operaciones": operaciones})
    assert not p._argumentos_validos("editar_pedido", {
        "operaciones": operaciones, "confirmar": True,
    })
