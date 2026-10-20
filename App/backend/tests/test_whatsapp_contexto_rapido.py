"""Menos consultas por turno sin cachear la autorización ni el pedido vigente."""

from decimal import Decimal

import pytest

from tests.test_whatsapp_bd import crear_pedido_bot


async def test_resumen_guiado_no_carga_catalogo_ni_memoria_ia(uow, monkeypatch):
    s, pid = await crear_pedido_bot(uow)

    async def no_corresponde(*args, **kwargs):
        pytest.fail("Un comando guiado no necesita construir el contexto de Gemini")

    monkeypatch.setattr(s.productos, "listar", no_corresponde)
    monkeypatch.setattr(s.repo, "memoria", no_corresponde)
    await s.recibir("resumen-rapido", "5492215550000", "resumen")
    preparado = await s.preparar("resumen-rapido")
    assert not preparado["interpretar"]
    respuesta = await s.procesar("resumen-rapido", {"accion": "consulta"}, preparado["vinculo"])
    assert "Total" in respuesta
    assert (await s.repo.pedido(pid))["items"][0]["cantidad"] == 1


async def test_contexto_no_agrega_consultas_por_cada_linea_del_pedido(uow, monkeypatch):
    s, pid = await crear_pedido_bot(uow)
    b = await uow.uno("SELECT * FROM whatsapp_borrador WHERE pedido_id=%s", (pid,))
    consultas = []
    uno, todos = uow.uno, uow.todos

    async def contar_uno(sql, parametros=None):
        consultas.append(sql)
        return await uno(sql, parametros)

    async def contar_todos(sql, parametros=None):
        consultas.append(sql)
        return await todos(sql, parametros)

    monkeypatch.setattr(uow, "uno", contar_uno)
    monkeypatch.setattr(uow, "todos", contar_todos)
    contexto_uno = await s._contexto(b)
    cantidad_uno = len(consultas)
    await uow.ejecutar(
        "INSERT INTO pedido_item(pedido_id,producto_id,nombre_producto,cantidad,precio_unitario,"
        "costo_opciones,subtotal,aclaraciones,variante,receta_snapshot) "
        "SELECT pedido_id,producto_id,nombre_producto,cantidad,precio_unitario,"
        "costo_opciones,subtotal,aclaraciones,variante,receta_snapshot "
        "FROM pedido_item CROSS JOIN generate_series(1,9) WHERE pedido_id=%s", (pid,),
    )
    consultas.clear()
    contexto_diez = await s._contexto(b)
    assert len(contexto_diez["items"]) == 10
    assert all(i["ingredientes"] == contexto_uno["items"][0]["ingredientes"]
        for i in contexto_diez["items"])
    assert len(consultas) <= cantidad_uno + 1


async def test_lectura_pedido_conserva_neto_decimal_y_fondos_pendientes(uow):
    s, pid = await crear_pedido_bot(uow)
    for tipo, monto, estado in [
        ("COBRO", "100.10", "CONCILIADO"),
        ("COBRO", "0.20", "CONCILIADO"),
        ("DEVOLUCION", "0.05", "CONCILIADO"),
        ("COBRO", "500.00", "PENDIENTE"),
    ]:
        await uow.ejecutar(
            "INSERT INTO pago(pedido_id,tipo,metodo_pago,monto,estado) "
            "VALUES (%s,%s,'EFECTIVO',%s,%s)", (pid, tipo, Decimal(monto), estado),
        )
    pedido = await s.repo.pedido(pid)
    assert pedido["pagado"] == Decimal("100.25")
    assert len(pedido["fondos"]) == 4
    assert all(isinstance(p["monto"], Decimal) for p in pedido["fondos"])


async def test_recetas_agrupadas_conservan_snapshot_vacio_fallback_y_repetidos(uow):
    s, pid = await crear_pedido_bot(uow)
    item = (await s.repo.pedido(pid))["items"][0]
    repetida = [*item["receta_snapshot"], item["receta_snapshot"][0]]
    items = [item, {**item, "receta_snapshot": []}, {**item, "receta_snapshot": None},
        {**item, "receta_snapshot": repetida}]
    originales = [await s._ingredientes_item(i) for i in items]
    agrupadas = await s.repo.ingredientes_items(items)
    assert agrupadas == originales
    assert agrupadas[1] == []


@pytest.mark.parametrize("cambio", ["fondos", "asignacion", "composicion"])
async def test_vinculo_guiado_relee_fondos_reparto_y_composicion(uow, cambio):
    from app.modules.whatsapp.application.servicio_bot import InterpretacionDesactualizada

    s, pid = await crear_pedido_bot(uow)
    await s.recibir("guiado-obsoleto", "5492215550000", "cantidad 2")
    preparado = await s.preparar("guiado-obsoleto")
    assert not preparado["interpretar"]
    if cambio == "fondos":
        await uow.ejecutar("INSERT INTO pago(pedido_id,tipo,metodo_pago,monto,estado) "
            "VALUES (%s,'COBRO','EFECTIVO',100,'CONCILIADO')", (pid,))
    elif cambio == "asignacion":
        await uow.ejecutar("INSERT INTO envio(pedido_id,estado) VALUES (%s,'ASIGNADO')", (pid,))
    else:
        await uow.ejecutar("UPDATE pedido_item SET aclaraciones='Sin Tomate' WHERE pedido_id=%s",
            (pid,))
    with pytest.raises(InterpretacionDesactualizada):
        await s.procesar("guiado-obsoleto", {"accion": "consulta"}, preparado["vinculo"],
            reintentar=True)
    assert (await s.repo.pedido(pid))["items"][0]["cantidad"] == 1
