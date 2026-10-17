"""Recorrido real sobre PostgreSQL descartable, sin proveedores externos."""

import pytest

from app.errores import DatosInvalidos, ReglaDeNegocio
from app.modules.whatsapp.domain.mensajes import hash_referencia
from app.modules.whatsapp.presentation.dependencias import construir_servicio


async def pedido_borrador(uow, b):
    return await uow.valor(
        "SELECT pedido_id FROM whatsapp_borrador WHERE referencia_hash=%s",
        (hash_referencia(b["referencia"][3:]),),
    )


async def datos_prueba(uow):
    cliente = await uow.valor("SELECT usuario_id FROM cliente ORDER BY usuario_id LIMIT 1")
    producto = await uow.uno(
        "SELECT id, variantes FROM producto WHERE activo AND nombre ILIKE '%MONU%' "
        "ORDER BY id LIMIT 1"
    )
    if producto is None:
        producto = await uow.uno("SELECT id, variantes FROM producto WHERE activo LIMIT 1")
    variante = (producto["variantes"] or [{}])[0].get("nombre")
    return cliente, {"producto_id": producto["id"], "cantidad": 1, "variante": variante}


@pytest.mark.asyncio
async def test_borrador_no_crea_pedido_y_recepcion_es_unica(uow):
    cliente, item = await datos_prueba(uow)
    servicio = construir_servicio(uow)
    antes = await uow.valor("SELECT count(*) FROM pedido")
    borrador = await servicio.crear_borrador(
        cliente,
        {
            "telefono": "5492215550000",
            "tipo_entrega": "RETIRO",
            "metodo_pago": "EFECTIVO",
            "items": [item],
        },
    )
    assert await uow.valor("SELECT count(*) FROM pedido") == antes
    for identificador in ("test-inicio", "test-inicio", "test-otro-inicio"):
        await servicio.recibir(identificador, "5492215550000", borrador["mensaje"])
        await servicio.procesar(identificador, {"accion": "consulta", "argumentos": {}})
    assert await uow.valor("SELECT count(*) FROM pedido") == antes + 1
    pid = await pedido_borrador(uow, borrador)
    assert await uow.valor("SELECT count(*) FROM movimiento_stock WHERE pedido_id=%s", (pid,)) == 0
    respuesta = await uow.valor("SELECT respuesta FROM whatsapp_entrada WHERE id='test-inicio'")
    assert "Total" in respuesta and "Pedido #" in respuesta


@pytest.mark.asyncio
async def test_referencia_no_puede_usarse_desde_otro_telefono(uow):
    cliente, item = await datos_prueba(uow)
    servicio = construir_servicio(uow)
    b = await servicio.crear_borrador(cliente, {"telefono": "5492215550000", "items": [item]})
    await servicio.recibir("test-ajeno", "5492215559999", b["mensaje"])
    respuesta = await servicio.procesar("test-ajeno", {"accion": "consulta", "argumentos": {}})
    assert "referencia" in respuesta.lower()
    assert await pedido_borrador(uow, b) is None


@pytest.mark.asyncio
async def test_transferencia_requiere_revision_aun_con_comprobante(uow):
    from app.modules.pedidos.domain.entidades import EstadoPedido
    from app.modules.pedidos.presentation.dependencias import obtener_servicio_pedidos

    cliente, item = await datos_prueba(uow)
    s = construir_servicio(uow)
    b = await s.crear_borrador(
        cliente,
        {
            "telefono": "5492215550000",
            "tipo_entrega": "RETIRO",
            "metodo_pago": "TRANSFERENCIA",
            "items": [item],
        },
    )
    await s.recibir("test-transfer", "5492215550000", b["mensaje"])
    await s.procesar("test-transfer", {"accion": "consulta", "argumentos": {}})
    pedido_id = await pedido_borrador(uow, b)
    await s.recibir("test-foto", "5492215550000", "", media_id="imagen-prueba")
    assert "revisión" in await s.procesar("test-foto", {})
    pedidos = obtener_servicio_pedidos(uow)
    with pytest.raises(ReglaDeNegocio):
        await pedidos.cambiar_estado(pedido_id, EstadoPedido.EN_PREPARACION, usuario_id=None)
    assert await uow.valor("SELECT count(*) FROM pago WHERE pedido_id=%s", (pedido_id,)) == 0


@pytest.mark.asyncio
async def test_no_se_aceptan_precios_ni_cantidades_del_modelo(uow):
    cliente, item = await datos_prueba(uow)
    s = construir_servicio(uow)
    with pytest.raises(DatosInvalidos):
        await s.crear_borrador(
            cliente, {"telefono": "5492215550000", "items": [{**item, "cantidad": -1}]}
        )


async def crear_pedido_bot(uow, metodo="EFECTIVO", dos=False):
    cliente, _ = await datos_prueba(uow)
    producto = await uow.uno(
        "SELECT p.id,p.variantes FROM producto p JOIN producto_ingrediente pi "
        "ON pi.producto_id=p.id JOIN ingrediente i ON i.id=pi.ingrediente_id "
        "WHERE p.activo AND lower(i.nombre)='tomate' ORDER BY p.id LIMIT 1"
    )
    variante = next(
        (v["nombre"] for v in producto["variantes"] if v["nombre"] == "Doble"),
        producto["variantes"][0]["nombre"],
    )
    item = {"producto_id": producto["id"], "cantidad": 1, "variante": variante}
    s = construir_servicio(uow)
    b = await s.crear_borrador(
        cliente,
        {
            "telefono": "5492215550000",
            "tipo_entrega": "RETIRO",
            "metodo_pago": metodo,
            "items": [item, {**item, "aclaraciones": "Sin Lechuga"}] if dos else [item],
        },
    )
    await s.recibir("inicio", "5492215550000", b["mensaje"])
    await s.procesar("inicio", {"accion": "consulta", "argumentos": {}})
    pid = await pedido_borrador(uow, b)
    return s, pid


@pytest.mark.asyncio
async def test_sin_tomate_se_persiste_y_cocina_lee_la_version_actual(uow):
    s, pid = await crear_pedido_bot(uow)
    await s.recibir("cambio", "5492215550000", "¿Le podés sacar el tomate?")
    respuesta = await s.procesar(
        "cambio", {"accion": "quitar_ingrediente", "argumentos": {"ingrediente": "tomate"}}
    )
    assert "Cambio guardado" in respuesta
    assert (
        await uow.valor("SELECT aclaraciones FROM pedido_item WHERE pedido_id=%s", (pid,))
        == "Sin Tomate"
    )
    pedido = (await s.pedidos.listar(cliente_id=None))[0]
    assert pedido["items"][0]["aclaraciones"] == "Sin Tomate"
    assert (
        await uow.valor(
            "SELECT count(*) FROM whatsapp_cambio WHERE pedido_id=%s " "AND estado='APLICADO'",
            (pid,),
        )
        == 1
    )


@pytest.mark.asyncio
async def test_ambiguo_pregunta_y_no_modifica(uow):
    s, pid = await crear_pedido_bot(uow, dos=True)
    await s.recibir("ambiguo", "5492215550000", "sin tomate")
    respuesta = await s.procesar(
        "ambiguo", {"accion": "quitar_ingrediente", "argumentos": {"ingrediente": "tomate"}}
    )
    assert "¿Cuál producto" in respuesta
    assert await uow.valor("SELECT count(*) FROM whatsapp_cambio WHERE pedido_id=%s", (pid,)) == 0
    assert await uow.valor("SELECT count(*) FROM pedido_item WHERE pedido_id=%s", (pid,)) == 2
    await s.recibir("aclarar", "5492215550000", "producto 2")
    respuesta = await s.procesar("aclarar", {"accion": "humano", "argumentos": {}})
    assert "Cambio guardado" in respuesta
    notas = await uow.todos(
        "SELECT aclaraciones FROM pedido_item WHERE pedido_id=%s ORDER BY id", (pid,)
    )
    assert notas[0]["aclaraciones"] is None
    assert "Sin Tomate" in notas[1]["aclaraciones"]


@pytest.mark.asyncio
async def test_total_nuevo_requiere_confirmacion_y_revalida_preparacion(uow):
    from app.modules.pedidos.domain.entidades import EstadoPedido

    s, pid = await crear_pedido_bot(uow)
    await s.recibir("cantidad", "5492215550000", "cantidad 2")
    respuesta = await s.procesar("cantidad", {"accion": "cantidad", "argumentos": {"cantidad": 2}})
    assert "nuevo total" in respuesta
    assert await uow.valor("SELECT cantidad FROM pedido_item WHERE pedido_id=%s", (pid,)) == 1
    await s.pedidos.cambiar_estado(pid, EstadoPedido.EN_PREPARACION, usuario_id=None)
    await s.recibir("confirma", "5492215550000", "confirmar")
    respuesta = await s.procesar("confirma", {"accion": "confirmar", "argumentos": {}})
    assert "aprobación de un empleado" in respuesta
    assert await uow.valor("SELECT cantidad FROM pedido_item WHERE pedido_id=%s", (pid,)) == 1


@pytest.mark.asyncio
async def test_empleado_aprueba_sin_tomate_durante_preparacion(uow):
    from app.modules.pedidos.domain.entidades import EstadoPedido

    s, pid = await crear_pedido_bot(uow)
    await s.pedidos.cambiar_estado(pid, EstadoPedido.EN_PREPARACION, usuario_id=None)
    await s.recibir("cambio", "5492215550000", "sin tomate")
    respuesta = await s.procesar(
        "cambio", {"accion": "quitar_ingrediente", "argumentos": {"ingrediente": "tomate"}}
    )
    assert "aprobación de un empleado" in respuesta
    cambio = await uow.valor("SELECT id FROM whatsapp_cambio WHERE pedido_id=%s", (pid,))
    empleado = await uow.valor("SELECT id FROM usuario WHERE rol='ADMINISTRADOR' LIMIT 1")
    await s.revisar_cambio(cambio, True, empleado, "Cocina avisada, todavía puede retirarlo")
    assert (
        await uow.valor("SELECT aclaraciones FROM pedido_item WHERE pedido_id=%s", (pid,))
        == "Sin Tomate"
    )


@pytest.mark.asyncio
async def test_comprobante_aprobado_una_sola_vez_y_notificacion_estado(uow):
    from app.modules.pedidos.domain.entidades import EstadoPedido

    s, pid = await crear_pedido_bot(uow, "TRANSFERENCIA")
    await s.recibir("foto", "5492215550000", "", "imagen-prueba")
    await s.procesar("foto", {})
    comprobante = await uow.valor("SELECT id FROM whatsapp_comprobante WHERE pedido_id=%s", (pid,))
    empleado = await uow.valor("SELECT id FROM usuario WHERE rol='ADMINISTRADOR' LIMIT 1")
    for _ in range(2):
        total = await uow.valor("SELECT total FROM pedido WHERE id=%s", (pid,))
        await s.revisar_comprobante(
            comprobante, True, empleado, "Verificado importe y cuenta", total_verificado=total
        )
    assert await uow.valor("SELECT count(*) FROM pago WHERE pedido_id=%s", (pid,)) == 1
    await s.pedidos.cambiar_estado(pid, EstadoPedido.EN_PREPARACION, usuario_id=empleado)
    assert (
        await uow.valor(
            "SELECT count(*) FROM whatsapp_salida WHERE clave=%s", (f"estado:{pid}:EN_PREPARACION",)
        )
        == 1
    )


@pytest.mark.asyncio
async def test_cantidad_confirmada_actualiza_total_servidor(uow):
    s, pid = await crear_pedido_bot(uow)
    total = await uow.valor("SELECT total FROM pedido WHERE id=%s", (pid,))
    await s.recibir("cantidad", "5492215550000", "cantidad 2")
    await s.procesar("cantidad", {"accion": "cantidad", "argumentos": {"cantidad": 2}})
    await s.recibir("confirmacion", "5492215550000", "confirmar")
    respuesta = await s.procesar("confirmacion", {"accion": "confirmar", "argumentos": {}})
    assert "Cambio guardado" in respuesta
    assert await uow.valor("SELECT total FROM pedido WHERE id=%s", (pid,)) == total * 2


@pytest.mark.asyncio
async def test_opcion_obligatoria_faltante_se_pregunta_antes_de_crear(uow):
    cliente, item = await datos_prueba(uow)
    item["variante"] = None
    s = construir_servicio(uow)
    b = await s.crear_borrador(
        cliente,
        {
            "telefono": "5492215550000",
            "tipo_entrega": "RETIRO",
            "metodo_pago": "EFECTIVO",
            "items": [item],
        },
    )
    await s.recibir("incompleto", "5492215550000", b["mensaje"])
    respuesta = await s.procesar("incompleto", {"accion": "consulta", "argumentos": {}})
    assert "variante:" in respuesta
    assert await pedido_borrador(uow, b) is None
    producto = await uow.uno("SELECT variantes FROM producto WHERE id=%s", (item["producto_id"],))
    variante = producto["variantes"][0]["nombre"]
    await s.recibir("opcion", "5492215550000", f"producto 1; variante: {variante}")
    respuesta = await s.procesar("opcion", {"accion": "humano", "argumentos": {}})
    assert "Pedido #" in respuesta


@pytest.mark.asyncio
async def test_rechazar_otro_adjunto_no_revoca_pago_aprobado(uow):
    s, pid = await crear_pedido_bot(uow, "TRANSFERENCIA")
    empleado = await uow.valor("SELECT id FROM usuario WHERE rol='ADMINISTRADOR' LIMIT 1")
    ids = []
    for n in (1, 2):
        await s.recibir(f"foto{n}", "5492215550000", "", f"imagen{n}")
        await s.procesar(f"foto{n}", {})
        ids.append(
            await uow.valor(
                "SELECT id FROM whatsapp_comprobante WHERE entrada_id=%s", (f"foto{n}",)
            )
        )
    total = await uow.valor("SELECT total FROM pedido WHERE id=%s", (pid,))
    with pytest.raises(ReglaDeNegocio):
        await s.revisar_comprobante(
            ids[0], True, empleado, "importe incorrecto", total_verificado=total + 1
        )
    await s.revisar_comprobante(ids[0], True, empleado, "verificado", total_verificado=total)
    await s.revisar_comprobante(ids[1], False, empleado, "adjunto duplicado")
    assert (
        await uow.valor("SELECT estado_pago FROM whatsapp_borrador WHERE pedido_id=%s", (pid,))
        == "APROBADO"
    )


@pytest.mark.asyncio
async def test_reintento_despues_de_preparar_no_repite_stock(uow):
    from app.modules.pedidos.domain.entidades import EstadoPedido

    s, pid = await crear_pedido_bot(uow)
    texto = await uow.valor("SELECT texto FROM whatsapp_entrada WHERE id='inicio'")
    await s.pedidos.cambiar_estado(pid, EstadoPedido.EN_PREPARACION, usuario_id=None)
    antes = await uow.todos(
        "SELECT ingrediente_id,cantidad FROM movimiento_stock WHERE pedido_id=%s", (pid,)
    )
    for identificador in ("inicio", "otro-inicio"):
        await s.recibir(identificador, "5492215550000", texto)
        await s.procesar(identificador, {"accion": "consulta", "argumentos": {}})
    assert antes == await uow.todos(
        "SELECT ingrediente_id,cantidad FROM movimiento_stock WHERE pedido_id=%s", (pid,)
    )


@pytest.mark.asyncio
async def test_aumento_pagado_requiere_empleado_y_no_acredita_diferencia(uow):
    s, pid = await crear_pedido_bot(uow, "TRANSFERENCIA")
    empleado = await uow.valor("SELECT id FROM usuario WHERE rol='ADMINISTRADOR' LIMIT 1")
    total = await uow.valor("SELECT total FROM pedido WHERE id=%s", (pid,))
    await uow.ejecutar(
        "INSERT INTO pago (pedido_id,metodo_pago,monto,estado) "
        "VALUES (%s,'TRANSFERENCIA',%s,'CONCILIADO')",
        (pid, total),
    )
    await uow.ejecutar(
        "UPDATE whatsapp_borrador SET estado_pago='APROBADO' WHERE pedido_id=%s", (pid,)
    )
    await s.recibir("aumento", "5492215550000", "cantidad 2")
    respuesta = await s.procesar("aumento", {"accion": "cantidad", "argumentos": {"cantidad": 2}})
    assert "aprobación de un empleado" in respuesta
    cambio = await uow.valor("SELECT id FROM whatsapp_cambio WHERE pedido_id=%s", (pid,))
    await s.revisar_cambio(
        cambio,
        True,
        empleado,
        "Coordino cobro adicional",
        total_verificado=total * 2,
        resolucion_financiera="COBRO_PENDIENTE",
    )
    assert await uow.valor("SELECT total FROM pedido WHERE id=%s", (pid,)) == total * 2
    assert await uow.valor("SELECT sum(monto) FROM pago WHERE pedido_id=%s", (pid,)) == total
    assert (
        await uow.valor("SELECT estado_pago FROM whatsapp_borrador WHERE pedido_id=%s", (pid,))
        == "PENDIENTE"
    )
    await s.revisar_cambio(
        cambio,
        True,
        empleado,
        "reintento",
        total_verificado=total * 2,
        resolucion_financiera="COBRO_PENDIENTE",
    )
    assert await uow.valor("SELECT cantidad FROM pedido_item WHERE pedido_id=%s", (pid,)) == 2


@pytest.mark.asyncio
async def test_cantidad_en_preparacion_confirma_importe_y_empleado_ajusta_stock(uow):
    from app.modules.pedidos.domain.entidades import EstadoPedido

    s, pid = await crear_pedido_bot(uow)
    await s.pedidos.cambiar_estado(pid, EstadoPedido.EN_PREPARACION, usuario_id=None)
    consumo = await uow.valor(
        "SELECT sum(cantidad) FROM movimiento_stock WHERE pedido_id=%s", (pid,)
    )
    total = await uow.valor("SELECT total FROM pedido WHERE id=%s", (pid,))
    await s.recibir("cantidad-prep", "5492215550000", "cantidad 2")
    respuesta = await s.procesar(
        "cantidad-prep", {"accion": "cantidad", "argumentos": {"cantidad": 2}}
    )
    assert "nuevo total" in respuesta
    assert await uow.valor("SELECT count(*) FROM whatsapp_cambio WHERE pedido_id=%s", (pid,)) == 0
    await s.recibir("confirmar-prep", "5492215550000", "confirmar")
    respuesta = await s.procesar("confirmar-prep", {"accion": "confirmar", "argumentos": {}})
    assert "aprobación de un empleado" in respuesta
    cid = await uow.valor("SELECT id FROM whatsapp_cambio WHERE pedido_id=%s", (pid,))
    empleado = await uow.valor("SELECT id FROM usuario WHERE rol='ADMINISTRADOR' LIMIT 1")
    for _ in range(2):
        await s.revisar_cambio(
            cid,
            True,
            empleado,
            "Cocina acepta y caja cobra adicional",
            total_verificado=total * 2,
            resolucion_financiera="COBRO_PENDIENTE",
        )
    assert (
        await uow.valor("SELECT sum(cantidad) FROM movimiento_stock WHERE pedido_id=%s", (pid,))
        == consumo * 2
    )
    assert await uow.valor("SELECT cantidad FROM pedido_item WHERE pedido_id=%s", (pid,)) == 2


@pytest.mark.asyncio
async def test_reduccion_pagada_requiere_devolucion_real_y_no_reintegra_insumos_de_cocina(uow):
    from app.modules.pagos.presentation.dependencias import obtener_servicio_conciliacion
    from app.modules.pedidos.domain.entidades import EstadoPedido

    s, pid = await crear_pedido_bot(uow)
    await s.recibir("duplicar", "5492215550000", "cantidad 2")
    await s.procesar("duplicar", {"accion": "cantidad", "argumentos": {"cantidad": 2}})
    await s.recibir("aceptar", "5492215550000", "confirmar")
    await s.procesar("aceptar", {"accion": "confirmar", "argumentos": {}})
    total = await uow.valor("SELECT total FROM pedido WHERE id=%s", (pid,))
    await uow.ejecutar(
        "INSERT INTO pago(pedido_id,metodo_pago,monto,estado) "
        "VALUES(%s,'EFECTIVO',%s,'CONCILIADO')",
        (pid, total),
    )
    await s.pedidos.cambiar_estado(pid, EstadoPedido.EN_PREPARACION, usuario_id=None)
    saldo = await uow.valor("SELECT sum(cantidad) FROM movimiento_stock WHERE pedido_id=%s", (pid,))
    await s.recibir("reducir", "5492215550000", "cantidad 1")
    await s.procesar("reducir", {"accion": "cantidad", "argumentos": {"cantidad": 1}})
    cid = await uow.valor(
        "SELECT id FROM whatsapp_cambio WHERE pedido_id=%s " "AND estado='PENDIENTE_EMPLEADO'",
        (pid,),
    )
    empleado = await uow.valor("SELECT id FROM usuario WHERE rol='ADMINISTRADOR' LIMIT 1")
    with pytest.raises(ReglaDeNegocio, match="devolución"):
        await s.revisar_cambio(
            cid,
            True,
            empleado,
            "Reducir con cocina",
            total_verificado=total / 2,
            resolucion_financiera="COBRO_PENDIENTE",
        )
    await obtener_servicio_conciliacion(uow).registrar_devolucion(
        pedido_id=pid, monto=total / 2, motivo="Unidad anulada con cocina", registrado_por=empleado
    )
    await s.revisar_cambio(
        cid,
        True,
        empleado,
        "Devolución registrada y cocina avisada",
        total_verificado=total / 2,
        resolucion_financiera="COBRO_PENDIENTE",
    )
    assert await uow.valor("SELECT total FROM pedido WHERE id=%s", (pid,)) == total / 2
    assert (
        await uow.valor("SELECT sum(cantidad) FROM movimiento_stock WHERE pedido_id=%s", (pid,))
        == saldo
    )


@pytest.mark.asyncio
async def test_devolucion_total_invalida_aprobacion_y_nuevo_total_requiere_revision(uow):
    from app.modules.pagos.presentation.dependencias import obtener_servicio_conciliacion
    from app.modules.pedidos.domain.entidades import EstadoPedido

    s, pid = await crear_pedido_bot(uow, "TRANSFERENCIA")
    empleado = await uow.valor("SELECT id FROM usuario WHERE rol='ADMINISTRADOR' LIMIT 1")
    total = await uow.valor("SELECT total FROM pedido WHERE id=%s", (pid,))
    await s.recibir("comprobante", "5492215550000", "", "imagen-prueba")
    await s.procesar("comprobante", {})
    cid = await uow.valor("SELECT id FROM whatsapp_comprobante WHERE pedido_id=%s", (pid,))
    await s.revisar_comprobante(cid, True, empleado, "verificado", total_verificado=total)
    await obtener_servicio_conciliacion(uow).registrar_devolucion(
        pedido_id=pid, monto=total, motivo="Devolución total", registrado_por=empleado
    )
    with pytest.raises(ReglaDeNegocio):
        await s.pedidos.cambiar_estado(pid, EstadoPedido.EN_PREPARACION, usuario_id=empleado)
    await s.recibir("mas", "5492215550000", "cantidad 2")
    await s.procesar("mas", {"accion": "cantidad", "argumentos": {"cantidad": 2}})
    await s.recibir("acepto", "5492215550000", "confirmar")
    await s.procesar("acepto", {"accion": "confirmar", "argumentos": {}})
    assert (
        await uow.valor("SELECT estado_pago FROM whatsapp_borrador WHERE pedido_id=%s", (pid,))
        == "PENDIENTE"
    )
    with pytest.raises(ReglaDeNegocio):
        await s.pedidos.cambiar_estado(pid, EstadoPedido.EN_PREPARACION, usuario_id=empleado)
