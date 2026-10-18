"""Cambios operativos reales, memoria de solicitudes y contexto canónico vigente."""

import pytest

from app.errores import ReglaDeNegocio
from app.modules.whatsapp.application.servicio_bot import InterpretacionDesactualizada
from app.modules.whatsapp.infrastructure.cola import ColaWhatsAppSQL
from tests.test_whatsapp_bd import crear_pedido_bot
from tests.test_whatsapp_regresiones import TELEFONO, empleado


async def actuar(s, identificador, argumentos, texto="cambiar datos"):
    await s.recibir(identificador, TELEFONO, texto)
    return await s.procesar(identificador, {"accion": "datos", "argumentos": argumentos})


async def confirmar(s, identificador="confirmacion"):
    await s.recibir(identificador, TELEFONO, "confirmar")
    return await s.procesar(identificador, {"accion": "confirmar", "argumentos": {}})


@pytest.mark.parametrize("estado", ["PENDIENTE", "CONFIRMADO", "EN_PREPARACION", "LISTO"])
async def test_metodo_cambia_mismo_pedido_sin_inferir_estado(uow, estado):
    s, pid = await crear_pedido_bot(uow)
    await uow.ejecutar("UPDATE pedido SET estado=%s WHERE id=%s", (estado, pid))
    anterior = await s.repo.pedido(pid)
    respuesta = await actuar(s, "metodo", {"metodo_pago": "transferencia"})
    actual = await s.repo.pedido(pid)
    assert "Cambio guardado" in respuesta
    assert (actual["id"], actual["numero"], actual["estado"]) == (
        pid, anterior["numero"], estado,
    )
    assert actual["metodo_pago_acordado"] == "TRANSFERENCIA"
    assert actual["version"] == anterior["version"] + 1
    assert await uow.valor("SELECT count(*) FROM pago WHERE pedido_id=%s", (pid,)) == 0
    b = await uow.uno("SELECT * FROM whatsapp_borrador WHERE pedido_id=%s", (pid,))
    assert b["metodo_pago"] == "TRANSFERENCIA"
    assert not b["contexto_chat"].get("datos")


async def test_delivery_recalcula_y_confirma_importe_sin_crear_otro_pedido(uow):
    await uow.ejecutar("UPDATE zona_cobertura SET costo_envio=1000 WHERE nombre='Ensenada'")
    s, pid = await crear_pedido_bot(uow)
    anterior = await s.repo.pedido(pid)
    respuesta = await actuar(s, "delivery", {
        "tipo_entrega": "delivery", "direccion": "Calle 7", "numero": "123",
        "localidad": "Ensenada",
    })
    assert "nuevo total" in respuesta and "confirmar" in respuesta
    assert "Respondé *confirmar*" in respuesta and str(anterior["numero"]) not in respuesta
    assert (await s.repo.pedido(pid))["tipo_entrega"] == "RETIRO"
    assert "Cambio guardado" in await confirmar(s)
    actual = await s.repo.pedido(pid)
    assert actual["numero"] == anterior["numero"] and actual["tipo_entrega"] == "DELIVERY"
    assert actual["total"] == anterior["total"] + actual["costo_envio"]
    assert actual["costo_envio"] > 0
    assert await uow.valor("SELECT count(*) FROM pedido") == 1
    b = await uow.uno("SELECT * FROM whatsapp_borrador WHERE pedido_id=%s", (pid,))
    assert b["tipo_entrega"] == "DELIVERY" and b["direccion"]["calle"] == "Calle 7"
    assert not b["contexto_chat"].get("datos")
    # Retiro disminuye el total: también requiere aceptación explícita.
    assert "nuevo total" in await actuar(s, "retiro", {"tipo_entrega": "retiro"})
    assert "Cambio guardado" in await confirmar(s, "conf-retiro")
    assert (await s.repo.pedido(pid))["total"] == anterior["total"]


async def test_delivery_pide_direccion_en_varios_turnos(uow):
    await uow.ejecutar("UPDATE zona_cobertura SET costo_envio=1000 WHERE nombre='Ensenada'")
    s, pid = await crear_pedido_bot(uow)
    assert "dirección" in await actuar(s, "modo", {"tipo_entrega": "delivery"})
    assert "número" in await actuar(s, "calle", {"direccion": "Calle 7"})
    assert "localidad" in await actuar(s, "altura", {"numero": "123"})
    assert "nuevo total" in await actuar(s, "localidad", {"localidad": "Ensenada"})
    assert "Cambio guardado" in await confirmar(s)
    assert (await s.repo.pedido(pid))["tipo_entrega"] == "DELIVERY"


async def test_atencion_resuelta_limpia_intencion_y_nueva_solicitud_tiene_origen_propio(uow):
    s, pid = await crear_pedido_bot(uow, "TRANSFERENCIA")
    await uow.ejecutar("UPDATE pedido SET estado='CANCELADO',version=version+1 WHERE id=%s", (pid,))
    assert "empleado" in await actuar(s, "efectivo-rechazado", {"metodo_pago": "efectivo"},
        texto=f"efectivo pedido #{(await s.repo.pedido(pid))['numero']}")
    atencion = await uow.uno("SELECT * FROM whatsapp_atencion WHERE estado='PENDIENTE'")
    await s.resolver_atencion(atencion["id"], await empleado(uow), "No se acepta el cambio")
    await actuar(s, "nuevo-delivery", {
        "tipo_entrega": "delivery", "direccion": "Calle Nueva", "numero": "44",
        "localidad": "Ensenada",
    }, texto=f"delivery pedido #{(await s.repo.pedido(pid))['numero']}")
    nueva = await uow.uno("SELECT * FROM whatsapp_atencion WHERE estado='PENDIENTE'")
    assert nueva["id"] != atencion["id"] and nueva["entrada_id"] == "nuevo-delivery"
    b = await uow.uno("SELECT * FROM whatsapp_borrador WHERE pedido_id=%s", (pid,))
    assert "metodo_pago" not in b["contexto_chat"]["datos"]
    assert b["metodo_pago"] == "TRANSFERENCIA"
    bandeja = await ColaWhatsAppSQL(uow).bandeja()
    mensaje = next(a["mensaje"] for a in bandeja["atenciones"] if a["id"] == nueva["id"])
    assert "Calle Nueva" in mensaje and "efectivo" not in mensaje.lower()


@pytest.mark.parametrize("cambio", ["version", "fondos", "metodo"])
async def test_interpretacion_revalida_version_y_finanzas_canonicas(uow, cambio):
    s, pid = await crear_pedido_bot(uow)
    await s.recibir("demorado", TELEFONO, "pasar a transferencia")
    preparado = await s.preparar("demorado")
    if cambio == "version":
        await uow.ejecutar("UPDATE pedido SET version=version+1 WHERE id=%s", (pid,))
    elif cambio == "metodo":
        await uow.ejecutar(
            "UPDATE pedido SET metodo_pago_acordado='TRANSFERENCIA' WHERE id=%s", (pid,),
        )
    else:
        await uow.ejecutar(
            "INSERT INTO pago(pedido_id,tipo,metodo_pago,monto,estado) "
            "VALUES (%s,'COBRO','EFECTIVO',100,'CONCILIADO')", (pid,),
        )
    with pytest.raises(InterpretacionDesactualizada):
        await s.procesar("demorado", {"accion": "datos", "argumentos": {
            "metodo_pago": "transferencia",
        }}, preparado["vinculo"], reintentar=True)


async def test_edicion_de_item_incrementa_version_y_deja_historia_canonica(uow):
    s, pid = await crear_pedido_bot(uow)
    anterior = (await s.repo.pedido(pid))["version"]
    await s.recibir("cantidad", TELEFONO, "cantidad 2")
    await s.procesar("cantidad", {"accion": "cantidad", "argumentos": {"cantidad": 2}})
    await confirmar(s)
    actual = await s.repo.pedido(pid)
    assert actual["version"] == anterior + 1
    historia = await uow.uno(
        "SELECT * FROM pedido_estado_historial WHERE pedido_id=%s ORDER BY id DESC LIMIT 1", (pid,),
    )
    assert historia["version"] == actual["version"] and historia["origen"] == "WHATSAPP"
    assert historia["cambios"]


async def test_cambiar_a_retiro_descarta_direccion_parcial_anterior(uow):
    s, pid = await crear_pedido_bot(uow)
    await actuar(s, "dir-parcial", {"tipo_entrega": "delivery", "direccion": "Calle 7"})
    respuesta = await actuar(s, "cambio-intencion", {"tipo_entrega": "retiro"})
    assert "Cambio guardado" in respuesta
    assert (await s.repo.pedido(pid))["tipo_entrega"] == "RETIRO"
    b = await uow.uno("SELECT contexto_chat FROM whatsapp_borrador WHERE pedido_id=%s", (pid,))
    assert not b["contexto_chat"].get("datos")


async def test_propuesta_de_items_no_aplica_sobre_version_canonica_nueva(uow):
    s, pid = await crear_pedido_bot(uow)
    await s.recibir("cantidad-obsoleta", TELEFONO, "cantidad 2")
    await s.procesar("cantidad-obsoleta", {"accion": "cantidad", "argumentos": {"cantidad": 2}})
    await uow.ejecutar("UPDATE pedido SET version=version+1 WHERE id=%s", (pid,))
    respuesta = await confirmar(s)
    assert "cambió" in respuesta
    assert (await s.repo.pedido(pid))["items"][0]["cantidad"] == 1


@pytest.mark.parametrize("estado", ["ASIGNADO", "EN_CAMINO", "FALLIDO"])
async def test_asignacion_durante_interpretacion_rechaza_ia_y_deriva_nuevo_intento(uow, estado):
    s, pid = await crear_pedido_bot(uow)
    await s.recibir("antes-asignacion", TELEFONO, "pagar por transferencia")
    preparado = await s.preparar("antes-asignacion")
    await uow.ejecutar("INSERT INTO envio(pedido_id,estado) VALUES (%s,%s)", (pid, estado))
    with pytest.raises(InterpretacionDesactualizada):
        await s.procesar("antes-asignacion", {"accion": "datos", "argumentos": {
            "metodo_pago": "transferencia",
        }}, preparado["vinculo"], reintentar=True)
    respuesta = await actuar(s, "despues-asignacion", {"metodo_pago": "transferencia"})
    assert "empleado" in respuesta
    assert (await s.repo.pedido(pid))["metodo_pago_acordado"] == "EFECTIVO"
    assert await uow.valor("SELECT count(*) FROM whatsapp_atencion WHERE estado='PENDIENTE'") == 1


async def test_revision_humana_de_item_rechaza_version_canonica_desactualizada(uow):
    s, pid = await crear_pedido_bot(uow)
    await uow.ejecutar("UPDATE pedido SET estado='EN_PREPARACION' WHERE id=%s", (pid,))
    await s.recibir("sin-tomate", TELEFONO, "sin tomate")
    await s.procesar("sin-tomate", {
        "accion": "quitar_ingrediente", "argumentos": {"ingrediente": "tomate"},
    })
    cambio = await uow.valor("SELECT id FROM whatsapp_cambio WHERE pedido_id=%s", (pid,))
    await uow.ejecutar("UPDATE pedido SET version=version+1 WHERE id=%s", (pid,))
    with pytest.raises(ReglaDeNegocio, match="versión"):
        await s.revisar_cambio(cambio, True, await empleado(uow), "Cocina avisada")
    assert (await s.repo.pedido(pid))["items"][0]["aclaraciones"] is None


async def test_bandeja_identifica_bloqueo_y_accion_del_personal(uow):
    s, pid = await crear_pedido_bot(uow)
    await uow.ejecutar("INSERT INTO envio(pedido_id,estado) VALUES (%s,'ASIGNADO')", (pid,))
    await actuar(s, "direccion-asignada", {
        "tipo_entrega": "delivery", "direccion": "Calle 7", "numero": "123",
        "localidad": "Ensenada",
    })
    a = (await ColaWhatsAppSQL(uow).bandeja())["atenciones"][0]
    assert "desasignación" in a["mensaje"] and "Calle 7" in a["mensaje"]


async def test_nueva_intencion_de_producto_descarta_solicitud_operativa_incompleta(uow):
    s, pid = await crear_pedido_bot(uow)
    await actuar(s, "delivery-incompleto", {"tipo_entrega": "delivery", "direccion": "Calle 7"})
    await s.recibir("otra-intencion", TELEFONO, "sin tomate")
    await s.procesar("otra-intencion", {
        "accion": "quitar_ingrediente", "argumentos": {"ingrediente": "tomate"},
    })
    respuesta = await actuar(s, "metodo-nuevo", {"metodo_pago": "transferencia"})
    assert "Cambio guardado" in respuesta
    actual = await s.repo.pedido(pid)
    assert actual["tipo_entrega"] == "RETIRO" and actual["metodo_pago_acordado"] == "TRANSFERENCIA"


async def test_retiro_con_importe_menor_a_cobrado_deriva_a_caja_sin_perder_fondos(uow):
    s, pid = await crear_pedido_bot(uow)
    await uow.ejecutar("UPDATE zona_cobertura SET costo_envio=1000 WHERE nombre='Ensenada'")
    await actuar(s, "delivery-pago", {
        "tipo_entrega": "delivery", "direccion": "Calle 7",
        "numero": "123", "localidad": "Ensenada",
    })
    await confirmar(s)
    pedido = await s.repo.pedido(pid)
    await uow.ejecutar(
        "INSERT INTO pago(pedido_id,tipo,metodo_pago,monto,estado) "
        "VALUES (%s,'COBRO','EFECTIVO',%s,'CONCILIADO')", (pid, pedido["total"]),
    )
    respuesta = await actuar(s, "retiro-cobrado", {"tipo_entrega": "retiro"})
    assert "empleado" in respuesta
    actual = await s.repo.pedido(pid)
    assert actual["tipo_entrega"] == "DELIVERY" and actual["pagado"] == pedido["total"]
    a = (await ColaWhatsAppSQL(uow).bandeja())["atenciones"][0]
    assert "devolución en caja" in a["mensaje"] and "retiro" in a["mensaje"]


async def test_cambio_de_tarifa_invalida_importe_antes_de_confirmar(uow):
    s, pid = await crear_pedido_bot(uow)
    await uow.ejecutar("UPDATE zona_cobertura SET costo_envio=1000 WHERE nombre='Ensenada'")
    await actuar(s, "tarifa-previa", {
        "tipo_entrega": "delivery", "direccion": "Calle 7",
        "numero": "123", "localidad": "Ensenada",
    })
    await uow.ejecutar("UPDATE zona_cobertura SET costo_envio=2000 WHERE nombre='Ensenada'")
    assert "total cambió" in await confirmar(s)
    assert (await s.repo.pedido(pid))["tipo_entrega"] == "RETIRO"


@pytest.mark.parametrize("accion", ["quitar_ingrediente", "cantidad"])
async def test_pedido_que_paso_por_cocina_requiere_personal_aunque_se_reabra(uow, accion):
    s, pid = await crear_pedido_bot(uow)
    await uow.ejecutar(
        "UPDATE pedido SET preparacion_en=now(),estado='PENDIENTE',version=version+1 WHERE id=%s",
        (pid,),
    )
    await s.recibir("receta-reabierta", TELEFONO, "corregir producto")
    args = {"ingrediente": "tomate"} if accion == "quitar_ingrediente" else {"cantidad": 2}
    respuesta = await s.procesar("receta-reabierta", {"accion": accion, "argumentos": args})
    if accion == "cantidad":
        assert "nuevo total" in respuesta
        respuesta = await confirmar(s)
    assert "aprobación de un empleado" in respuesta
    item = (await s.repo.pedido(pid))["items"][0]
    assert item["cantidad"] == 1 and item["aclaraciones"] is None
