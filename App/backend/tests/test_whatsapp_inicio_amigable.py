"""Inicio sin códigos: remitente verificado, intención legible y reenvío idempotente."""

from datetime import UTC, datetime, timedelta

import pytest

from app.modules.whatsapp.application import servicio_bot as modulo
from app.modules.whatsapp.domain.mensajes import hash_referencia
from app.modules.whatsapp.presentation.dependencias import construir_servicio
from tests.test_whatsapp_bd import datos_prueba

TELEFONO = "5492215550181"
OTRO = "5492215550182"


@pytest.fixture
def momento(monkeypatch):
    ahora = datetime.now(UTC)
    monkeypatch.setattr(modulo, "momento_preparacion", lambda: ahora, raising=False)
    return ahora


async def preparar(uow, telefono=TELEFONO, tipo="RETIRO"):
    _, item = await datos_prueba(uow)
    datos = {
        "items": [item], "tipo_entrega": tipo, "metodo_pago": "EFECTIVO",
        "contacto": {"nombre": "Ana", "apellido": "Pérez", "telefono": telefono},
    }
    if tipo == "DELIVERY":
        datos["direccion_nueva"] = {
            "calle": "Calle 43", "numero": "123", "localidad": "Ensenada",
        }
    return await construir_servicio(uow).crear_borrador(None, datos)


async def fila(uow, b):
    return await uow.uno(
        "SELECT * FROM whatsapp_borrador WHERE referencia_hash=%s",
        (hash_referencia(b["referencia"][3:]),),
    )


async def enviar(uow, identificador, telefono, texto):
    s = construir_servicio(uow)
    await s.recibir(identificador, telefono, texto)
    return await s.procesar(identificador, {"accion": "consulta"})


async def test_inicio_legible_sin_token_y_reenvio_crea_un_solo_pedido(uow, momento):
    antes = await uow.valor("SELECT count(*) FROM pedido")
    b = await preparar(uow)
    assert "MB-" not in b["mensaje"]
    assert "Ana Pérez" in b["mensaje"] and "efectivo" in b["mensaje"].lower()
    s = construir_servicio(uow)
    await s.recibir("inicio-legible", TELEFONO, b["mensaje"])
    assert not (await s.preparar("inicio-legible"))["interpretar"]
    await s.procesar("inicio-legible", {})
    await enviar(uow, "inicio-legible-reenvio", TELEFONO, "  " + b["mensaje"].upper() + "\n")
    actual = await fila(uow, b)
    assert actual["telefono"] == TELEFONO and actual["pedido_id"]
    assert await uow.valor("SELECT count(*) FROM pedido") == antes + 1


async def test_otro_remitente_no_reclama_con_resumen_ni_referencia_interna(uow, momento):
    b = await preparar(uow)
    await enviar(uow, "inicio-ajeno", OTRO, b["mensaje"])
    await enviar(uow, "inicio-ajeno-ref", OTRO, "Confirmar " + b["referencia"])
    actual = await fila(uow, b)
    assert actual["cliente_id"] is None and actual["pedido_id"] is None
    await enviar(uow, "inicio-dueno", TELEFONO, b["mensaje"])
    assert (await fila(uow, b))["telefono"] == TELEFONO


async def test_resumen_editado_no_se_registra_automaticamente(uow, momento):
    b = await preparar(uow)
    await enviar(uow, "inicio-editado", TELEFONO, b["mensaje"] + " sin pagar")
    assert (await fila(uow, b))["cliente_id"] is None


async def test_resumen_editado_no_se_aplica_a_otra_compra_activa(uow, momento, monkeypatch):
    a = await preparar(uow)
    await enviar(uow, "anterior-activa", TELEFONO, a["mensaje"])
    monkeypatch.setattr(modulo, "momento_preparacion", lambda: momento + timedelta(seconds=1))
    b = await preparar(uow)
    texto = b["mensaje"].replace("¡Hola, Monu Burger! 🍔", "Buenas") + " sin tomate"
    s = construir_servicio(uow)
    await s.recibir("nuevo-editado", TELEFONO, texto)
    assert not (await s.preparar("nuevo-editado"))["interpretar"]
    await s.procesar("nuevo-editado", {
        "accion": "cantidad", "argumentos": {"cantidad": 2},
    })
    assert (await fila(uow, b))["pedido_id"] is None
    assert (await fila(uow, a))["propuesta"] is None


async def test_resumen_vencido_no_crea_cliente_ni_pedido(uow, momento):
    b = await preparar(uow)
    await uow.ejecutar(
        "UPDATE whatsapp_borrador SET expira_en=now()-interval '1 minute' "
        "WHERE referencia_hash=%s", (hash_referencia(b["referencia"][3:]),),
    )
    respuesta = await enviar(uow, "resumen-vencido", TELEFONO, b["mensaje"])
    assert "venció" in respuesta
    actual = await fila(uow, b)
    assert actual["cliente_id"] is None and actual["pedido_id"] is None


async def test_doble_click_preparar_reutiliza_el_mismo_resumen(uow, momento):
    b = await preparar(uow)
    repetido = await preparar(uow)
    assert b == repetido


async def test_dos_clientes_con_resumen_igual_solo_reclaman_su_propio_pedido(uow, momento):
    a, b = await preparar(uow), await preparar(uow, OTRO)
    assert a["mensaje"] == b["mensaje"]
    await enviar(uow, "inicio-cliente-a", TELEFONO, a["mensaje"])
    assert (await fila(uow, b))["cliente_id"] is None
    await enviar(uow, "inicio-cliente-b", OTRO, b["mensaje"])
    assert (await fila(uow, a))["cliente_id"] != (await fila(uow, b))["cliente_id"]


async def test_recompra_y_seleccion_por_numero_habitual_no_permiten_acceso_ajeno(
    uow, momento, monkeypatch
):
    a = await preparar(uow)
    await enviar(uow, "inicio-compra-a", TELEFONO, a["mensaje"])
    monkeypatch.setattr(modulo, "momento_preparacion", lambda: momento + timedelta(seconds=1))
    b = await preparar(uow)
    await enviar(uow, "inicio-compra-b", TELEFONO, b["mensaje"])
    primera, segunda = await fila(uow, a), await fila(uow, b)
    assert primera["pedido_id"] != segunda["pedido_id"]
    numero = await uow.valor("SELECT numero FROM pedido WHERE id=%s", (primera["pedido_id"],))
    respuesta = await enviar(uow, "consulta-numero", TELEFONO, f"Estado del pedido #{numero}")
    assert respuesta.count(f"Pedido #{numero}") == 1
    ajena = await enviar(uow, "consulta-numero-ajeno", OTRO, f"Estado del pedido #{numero}")
    assert f"Pedido #{numero}" not in ajena


async def test_variante_en_lenguaje_simple_se_resuelve_sin_ia(uow, momento):
    _, item = await datos_prueba(uow)
    item["variante"] = None
    s = construir_servicio(uow)
    b = await s.crear_borrador(None, {
        "items": [item], "tipo_entrega": "RETIRO", "metodo_pago": "EFECTIVO",
        "contacto": {"nombre": "Ana", "apellido": "Pérez", "telefono": TELEFONO},
    })
    pregunta = await enviar(uow, "pregunta-variante", TELEFONO, b["mensaje"])
    assert "Doble" in pregunta
    await s.recibir("respuesta-variante", TELEFONO, "Doble")
    assert not (await s.preparar("respuesta-variante"))["interpretar"]
    respuesta = await s.procesar("respuesta-variante", {"accion": "consulta"})
    assert "Pedido #" in respuesta and "(Doble)" in respuesta
    assert (await fila(uow, b))["pedido_id"]


async def test_cambio_y_confirmacion_por_numero_afectan_solo_a_esa_compra(
    uow, momento, monkeypatch
):
    a = await preparar(uow)
    await enviar(uow, "seleccion-compra-a", TELEFONO, a["mensaje"])
    monkeypatch.setattr(modulo, "momento_preparacion", lambda: momento + timedelta(seconds=1))
    b = await preparar(uow)
    await enviar(uow, "seleccion-compra-b", TELEFONO, b["mensaje"])
    primera, segunda = await fila(uow, a), await fila(uow, b)
    numero = await uow.valor("SELECT numero FROM pedido WHERE id=%s", (primera["pedido_id"],))
    s = construir_servicio(uow)
    await s.recibir("cambio-por-numero", TELEFONO, f"cantidad 2 para el pedido #{numero}")
    respuesta = await s.procesar("cambio-por-numero", {
        "accion": "cantidad", "argumentos": {"cantidad": 2},
    })
    assert f"confirmar para el pedido #{numero}" in respuesta
    await s.recibir("confirmar-por-numero", TELEFONO, f"confirmar para el pedido #{numero}")
    assert (await s.preparar("confirmar-por-numero"))["texto"] == "confirmar"
    await s.procesar("confirmar-por-numero", {"accion": "confirmar"})
    assert await uow.valor(
        "SELECT cantidad FROM pedido_item WHERE pedido_id=%s", (primera["pedido_id"],)
    ) == 2
    assert await uow.valor(
        "SELECT cantidad FROM pedido_item WHERE pedido_id=%s", (segunda["pedido_id"],)
    ) == 1


@pytest.mark.parametrize("tipo", ["RETIRO", "DELIVERY"])
async def test_aviso_estado_es_amigable_y_sigue_siendo_unico(uow, momento, tipo):
    b = await preparar(uow, tipo=tipo)
    await enviar(uow, "estado-inicio", TELEFONO, b["mensaje"])
    pedido_id = (await fila(uow, b))["pedido_id"]
    # La prueba aísla las notificaciones del trigger para una compra válida.
    for estado, emoji in [("EN_PREPARACION", "👨‍🍳"), ("LISTO", "🍔"), ("EN_CAMINO", "🛵")]:
        await uow.ejecutar(
            "UPDATE pedido SET estado=%s,version=version+1 WHERE id=%s", (estado, pedido_id)
        )
        # Repetir la misma escritura no crea un nuevo evento.
        await uow.ejecutar("UPDATE pedido SET estado=%s WHERE id=%s", (estado, pedido_id))
        version = await uow.valor("SELECT version FROM pedido WHERE id=%s", (pedido_id,))
        salidas = await uow.todos(
            "SELECT texto FROM whatsapp_salida WHERE clave=%s",
            (f"estado:{pedido_id}:v{version}",),
        )
        assert len(salidas) == 1
        assert estado not in salidas[0]["texto"]
        if tipo == "DELIVERY" or estado == "EN_PREPARACION":
            assert emoji in salidas[0]["texto"]
        if tipo == "RETIRO" and estado == "EN_CAMINO":
            assert "retirar" in salidas[0]["texto"] and "en camino" not in salidas[0]["texto"]
