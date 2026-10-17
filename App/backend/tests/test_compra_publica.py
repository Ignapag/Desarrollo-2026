"""Compra sin cuenta: la identidad nace del remitente, nunca del formulario."""

import hashlib
import hmac
import json
from contextlib import asynccontextmanager

import httpx
import pytest

from app.core.config import settings
from app.core.dependencias import obtener_uow
from app.modules.whatsapp.domain.mensajes import hash_referencia
from app.modules.whatsapp.presentation.dependencias import construir_servicio
from tests.test_whatsapp_bd import datos_prueba
from tests.test_whatsapp_http import aplicacion

TELEFONO = "5492215550123"
OTRO = "5492215550124"


async def datos(uow):
    _, item = await datos_prueba(uow)
    return {"items": [item], "tipo_entrega": "RETIRO", "metodo_pago": "EFECTIVO"}


async def fila(uow, borrador):
    return await uow.uno(
        "SELECT * FROM whatsapp_borrador WHERE referencia_hash=%s",
        (hash_referencia(borrador["referencia"][3:]),),
    )


async def enviar(servicio, identificador, telefono, mensaje):
    await servicio.recibir(identificador, telefono, mensaje)
    return await servicio.procesar(identificador, {"accion": "consulta"})


async def test_checkout_publico_y_webhook_firmado_asocian_remitente_sin_usuario(uow, monkeypatch):
    from app.modules.whatsapp.presentation import router as modulo

    @asynccontextmanager
    async def conexion_prueba():
        yield uow.conn

    app = aplicacion()
    app.dependency_overrides[obtener_uow] = lambda: uow
    monkeypatch.setattr(modulo, "conexion", conexion_prueba)
    monkeypatch.setattr(settings, "whatsapp_modo", "real")
    monkeypatch.setattr(settings, "whatsapp_app_secret", "secret-prueba")
    monkeypatch.setattr(settings, "whatsapp_phone_number_id", "numero-prueba")
    antes = await uow.valor("SELECT count(*) FROM usuario")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://prueba"
    ) as visitante:
        respuesta = await visitante.post("/api/whatsapp/borradores", json=await datos(uow))
        assert respuesta.status_code == 201
        b = respuesta.json()
        assert (await fila(uow, b))["cliente_id"] is None
        assert (await fila(uow, b))["pedido_id"] is None
        cuerpo = json.dumps({
            "object": "whatsapp_business_account",
            "entry": [{"changes": [{"value": {
                "metadata": {"phone_number_id": "numero-prueba"},
                "contacts": [{"wa_id": TELEFONO, "profile": {"name": "Juana"}}],
                "messages": [{"id": "publico-firmado", "from": TELEFONO,
                              "type": "text", "text": {"body": b["mensaje"]}}],
            }}]}],
        }).encode()
        firma = "sha256=" + hmac.new(b"secret-prueba", cuerpo, hashlib.sha256).hexdigest()
        for _ in range(2):
            respuesta = await visitante.post(
                "/api/whatsapp/webhook", content=cuerpo,
                headers={"x-hub-signature-256": firma},
            )
            assert respuesta.status_code == 200
    servicio = construir_servicio(uow)
    await servicio.procesar("publico-firmado", {"accion": "consulta"})
    primera = await fila(uow, b)
    cliente = await uow.uno("SELECT * FROM cliente WHERE id=%s", (primera["cliente_id"],))
    assert cliente["usuario_id"] is None
    assert cliente["whatsapp_verificado"] == TELEFONO
    assert cliente["nombre"] == "Juana"
    assert primera["telefono"] == TELEFONO and primera["pedido_id"]
    await servicio.procesar("publico-firmado", {})
    await enviar(servicio, "publico-repetido", TELEFONO, b["mensaje"])
    assert (await fila(uow, b))["pedido_id"] == primera["pedido_id"]
    assert await uow.valor("SELECT count(*) FROM usuario") == antes
    pedidos = await servicio.pedidos.listar(cliente_id=cliente["id"])
    assert len(pedidos) == 1 and pedidos[0]["cliente"] == "Juana"


async def test_recompra_dos_activos_y_ajeno_no_reclama_ni_modifica(uow):
    servicio = construir_servicio(uow)
    primero = await servicio.crear_borrador(None, await datos(uow))
    await enviar(servicio, "publico-1", TELEFONO, primero["mensaje"])
    a = await fila(uow, primero)
    segundo = await servicio.crear_borrador(None, await datos(uow))
    await enviar(servicio, "publico-2", TELEFONO, segundo["mensaje"])
    b = await fila(uow, segundo)
    assert a["cliente_id"] == b["cliente_id"]
    assert a["pedido_id"] != b["pedido_id"]
    respuesta = await enviar(servicio, "publico-ambiguo", TELEFONO, "estado")
    assert "referencia" in respuesta.lower()
    respuesta = await enviar(servicio, "publico-ajeno", OTRO, primero["mensaje"])
    assert "referencia" in respuesta.lower()
    assert (await fila(uow, primero))["telefono"] == TELEFONO
    assert await uow.valor(
        "SELECT count(*) FROM whatsapp_cambio WHERE pedido_id=%s", (a["pedido_id"],)
    ) == 0


async def test_referencia_vencida_no_crea_cliente_ni_pedido(uow):
    servicio = construir_servicio(uow)
    b = await servicio.crear_borrador(None, await datos(uow))
    await uow.ejecutar(
        "UPDATE whatsapp_borrador SET expira_en=now()-interval '1 second' "
        "WHERE referencia_hash=%s", (hash_referencia(b["referencia"][3:]),),
    )
    respuesta = await enviar(servicio, "publico-vencido", TELEFONO, b["mensaje"])
    assert "venció" in respuesta
    actual = await fila(uow, b)
    assert actual["cliente_id"] is None and actual["pedido_id"] is None


async def test_telefono_declarado_no_fusiona_historial_y_api_no_lo_admite(uow):
    servicio = construir_servicio(uow)
    historico = await uow.valor("SELECT usuario_id FROM cliente ORDER BY usuario_id LIMIT 1")
    await uow.ejecutar(
        "UPDATE cliente SET telefono_whatsapp=%s WHERE usuario_id=%s", (TELEFONO, historico)
    )
    app = aplicacion()
    app.dependency_overrides[obtener_uow] = lambda: uow
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://prueba"
    ) as visitante:
        respuesta = await visitante.post(
            "/api/whatsapp/borradores", json={**await datos(uow), "telefono": TELEFONO}
        )
        assert respuesta.status_code == 422
    b = await servicio.crear_borrador(None, await datos(uow))
    await enviar(servicio, "publico-no-fusion", TELEFONO, b["mensaje"])
    cliente_id = (await fila(uow, b))["cliente_id"]
    assert await uow.valor("SELECT usuario_id FROM cliente WHERE id=%s", (cliente_id,)) is None


@pytest.mark.parametrize("campo", ["cliente_id", "precio", "pedido_id"])
async def test_borrador_publico_rechaza_atributos_de_autoridad(uow, campo):
    app = aplicacion()
    app.dependency_overrides[obtener_uow] = lambda: uow
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://prueba"
    ) as visitante:
        r = await visitante.post(
            "/api/whatsapp/borradores", json={**await datos(uow), campo: 1}
        )
        assert r.status_code == 422


async def test_worker_completa_datos_y_cambio_invitado_llega_a_cocina_y_stock(uow, monkeypatch):
    from app.modules.pedidos.domain.entidades import EstadoPedido
    from app.modules.whatsapp.infrastructure.proveedores import SimuladoInterpretador
    from app.modules.whatsapp.presentation import procesamiento
    from tests.test_whatsapp_regresiones import item_con_tomate

    @asynccontextmanager
    async def conexion_prueba():
        yield uow.conn

    monkeypatch.setattr(procesamiento, "conexion", conexion_prueba)
    monkeypatch.setattr(procesamiento, "interpretador", SimuladoInterpretador)
    servicio = construir_servicio(uow)
    b = await servicio.crear_borrador(None, {"items": [await item_con_tomate(uow)]})
    for indice, texto in enumerate((b["mensaje"], "retiro", "efectivo")):
        identificador = f"publico-datos-{indice}"
        await servicio.recibir(identificador, TELEFONO, texto)
        await procesamiento.procesar_entrada(identificador)
        if indice < 2:
            assert (await fila(uow, b))["pedido_id"] is None
    pedido_id = (await fila(uow, b))["pedido_id"]
    assert pedido_id
    await servicio.pedidos.cambiar_estado(pedido_id, EstadoPedido.CONFIRMADO, usuario_id=None)
    await servicio.recibir("publico-sin-tomate", TELEFONO, "sin tomate")
    await procesamiento.procesar_entrada("publico-sin-tomate")
    pedido = next(p for p in await servicio.pedidos.listar(cliente_id=None) if p["id"] == pedido_id)
    assert pedido["items"][0]["aclaraciones"] == "Sin Tomate"
    assert await uow.valor(
        "SELECT count(*) FROM whatsapp_cambio WHERE pedido_id=%s AND estado='APLICADO'",
        (pedido_id,),
    ) == 1
    assert await uow.valor(
        "SELECT count(*) FROM movimiento_stock m JOIN ingrediente i ON i.id=m.ingrediente_id "
        "WHERE m.pedido_id=%s AND lower(i.nombre)='tomate' AND m.tipo='DEVOLUCION'",
        (pedido_id,),
    ) == 1
