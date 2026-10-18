"""Regresiones de revisión: snapshot viejo y corrección logística coordinada."""

from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest

from app.core.db import UnidadDeTrabajo
from app.errores import ReglaDeNegocio
from app.modules.delivery.presentation.dependencias import obtener_servicio_delivery
from tests.soporte_bd import conectar_o_omitir
from tests.test_delivery_bd import ENSENADA_CENTRO, crear_pedido_listo
from tests.test_delivery_seguridad import api as api_delivery
from tests.test_delivery_seguridad import (
    autenticar,
    crear_repartidor,
    crear_viaje_propio,
)

api = api_delivery


@pytest.mark.asyncio
async def test_snapshot_planificador_anterior_a_commit_manual_no_roba_envio(monkeypatch):
    manual, plan = await conectar_o_omitir(), await conectar_o_omitir()
    um, up = UnidadDeTrabajo(manual), UnidadDeTrabajo(plan)
    pedido = cliente = usuario = None
    riders = []
    tarea = None
    clave = 871994
    try:
        sufijo = uuid4().hex[:12]
        pedido = await crear_pedido_listo(um, sufijo, ENSENADA_CENTRO)
        riders = [await crear_repartidor(um, f"{sufijo}_{i}") for i in range(2)]
        cliente = await um.valor("SELECT cliente_id FROM pedido WHERE id=%s", (pedido,))
        usuario = await um.valor("SELECT usuario_id FROM cliente WHERE id=%s", (cliente,))
        await manual.commit()
        await um.valor("SELECT pg_advisory_lock(%s)", (clave,))
        pid = await up.valor("SELECT pg_backend_pid()")
        original = up.todos
        pausada = False

        async def con_barrera(sql, parametros=None):
            nonlocal pausada
            if "SELECT p.id AS pedido_id" in sql and not pausada:
                pausada = True
                sql = (
                    f"WITH barrera AS MATERIALIZED (SELECT pg_advisory_xact_lock({clave})) "
                    + sql.replace("FROM pedido p", "FROM pedido p CROSS JOIN barrera").replace(
                        "WHERE p.estado", f"WHERE p.id={pedido} AND p.estado"
                    )
                )
            if "FROM repartidor r" in sql:
                sql = sql.replace("WHERE r.estado", f"WHERE r.usuario_id={riders[1]} AND r.estado")
            return await original(sql, parametros)

        monkeypatch.setattr(up, "todos", con_barrera)
        tarea = asyncio.create_task(
            obtener_servicio_delivery(up).planificar_y_asignar(usuario_id=riders[1], rol="EMPLEADO")
        )
        async with asyncio.timeout(5):
            while not await um.valor(
                "SELECT EXISTS(SELECT 1 FROM pg_locks WHERE pid=%s AND NOT granted)", (pid,)
            ):
                await asyncio.sleep(0.01)
        asignado = await obtener_servicio_delivery(um).asignar_pedido(
            pedido,
            riders[0],
            motivo="Asignacion manual concurrente",
            usuario_id=riders[0],
            rol="EMPLEADO",
        )
        await manual.commit()
        await um.valor("SELECT pg_advisory_unlock(%s)", (clave,))
        resultado = await asyncio.wait_for(tarea, timeout=5)
        await plan.commit()
        assert resultado.viajes == [], "El planificador uso un candidato anterior al commit manual"
        assert (
            await um.valor("SELECT viaje_id FROM envio WHERE pedido_id=%s", (pedido,))
            == asignado["viaje_id"]
        )
        assert (
            await um.valor("SELECT count(*) FROM viaje WHERE repartidor_id=ANY(%s)", (riders,)) == 1
        )
        assert (
            await um.valor("SELECT estado FROM repartidor WHERE usuario_id=%s", (riders[1],))
            == "DISPONIBLE"
        )
    finally:
        if tarea and not tarea.done():
            tarea.cancel()
            await asyncio.gather(tarea, return_exceptions=True)
        await plan.rollback()
        await manual.rollback()
        await um.valor("SELECT pg_advisory_unlock(%s)", (clave,))
        if riders:
            await um.ejecutar("DELETE FROM auditoria WHERE usuario_id=ANY(%s)", (riders,))
            await um.ejecutar("DELETE FROM pedido WHERE id=%s", (pedido,))
            await um.ejecutar("DELETE FROM viaje WHERE repartidor_id=ANY(%s)", (riders,))
            await um.ejecutar("DELETE FROM direccion WHERE cliente_id=%s", (cliente,))
            await um.ejecutar("DELETE FROM cliente WHERE id=%s", (cliente,))
            await um.ejecutar("DELETE FROM repartidor WHERE usuario_id=ANY(%s)", (riders,))
            await um.ejecutar("DELETE FROM usuario WHERE id=ANY(%s)", ([*riders, usuario],))
            await manual.commit()
        await manual.close()
        await plan.close()


@pytest.mark.asyncio
async def test_escritura_envio_no_sustituye_asignacion_vigente(uow):
    servicio, rider, viaje, pedidos, envios = await crear_viaje_propio(uow)
    otro = await crear_repartidor(uow, uuid4().hex[:12])
    destino = await servicio.repo.crear_viaje(otro, asignado_por=rider, automatica=False)
    with pytest.raises(ReglaDeNegocio):
        await servicio.repo.asignar_envio(
            pedido_id=pedidos[0], viaje_id=destino, zona_id=None, orden=1, distancia_km=None
        )
    assert await uow.valor("SELECT viaje_id FROM envio WHERE id=%s", (envios[0],)) == viaje


@pytest.mark.asyncio
@pytest.mark.parametrize("cantidad", [1, 2])
async def test_http_corregir_entrega_confirma_regreso_y_preserva_resto(uow, api, cantidad):
    servicio, rider, viaje, pedidos, envios = await crear_viaje_propio(uow, cantidad=cantidad)
    await servicio.iniciar_viaje(viaje, usuario_id=rider, rol="REPARTIDOR")
    await servicio.registrar_entrega(envios[0], usuario_id=rider, rol="REPARTIDOR")
    version = await uow.valor("SELECT version FROM pedido WHERE id=%s", (pedidos[0],))
    autenticar(api, rider, "ADMINISTRADOR")
    respuesta = await api.post(
        f"/api/delivery/envios/{envios[0]}/corregir-entrega",
        json={
            "motivo": "Click de entrega erroneo; paquete recibido en local",
            "version_esperada": version,
            "regreso_confirmado": True,
        },
    )
    assert respuesta.status_code == 200
    assert respuesta.json()["envio_id"] == envios[0]
    assert await uow.valor("SELECT estado FROM pedido WHERE id=%s", (pedidos[0],)) == "LISTO"
    assert await uow.valor("SELECT viaje_id FROM envio WHERE id=%s", (envios[0],)) is None
    assert await uow.valor("SELECT estado FROM viaje WHERE id=%s", (viaje,)) == (
        "EN_RUTA" if cantidad == 2 else "FINALIZADO"
    )
    assert await uow.valor("SELECT estado FROM repartidor WHERE usuario_id=%s", (rider,)) == (
        "EN_RUTA" if cantidad == 2 else "DISPONIBLE"
    )
    if cantidad == 2:
        assert await uow.valor("SELECT estado FROM envio WHERE id=%s", (envios[1],)) == "EN_CAMINO"
        assert (
            await uow.valor("SELECT estado FROM pedido WHERE id=%s", (pedidos[1],)) == "EN_CAMINO"
        )
    historia = await uow.uno(
        "SELECT datos FROM auditoria WHERE accion='ENVIO_ENTREGA_CORREGIDA' AND entidad_id=%s",
        (str(envios[0]),),
    )
    assert historia["datos"]["envio_anterior"]["viaje_id"] == viaje
    assert historia["datos"]["envio_anterior"]["entregado_en"]
    nuevo = await crear_repartidor(uow, uuid4().hex[:12])
    reasignado = await servicio.asignar_pedido(
        pedidos[0],
        nuevo,
        motivo="Reintentar tras regreso confirmado",
        usuario_id=rider,
        rol="EMPLEADO",
    )
    assert reasignado["envio_id"] == envios[0] and reasignado["viaje_id"] != viaje
    if cantidad == 2:
        assert await uow.valor("SELECT viaje_id FROM envio WHERE id=%s", (envios[1],)) == viaje


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "rol,confirmado,esperado",
    [("EMPLEADO", True, 403), ("REPARTIDOR", True, 403), ("ADMINISTRADOR", False, 422)],
)
async def test_correccion_entrega_requiere_privilegio_y_regreso(
    uow, api, rol, confirmado, esperado
):
    servicio, rider, viaje, pedidos, envios = await crear_viaje_propio(uow, cantidad=2)
    await servicio.iniciar_viaje(viaje, usuario_id=rider, rol="REPARTIDOR")
    await servicio.registrar_entrega(envios[0], usuario_id=rider, rol="REPARTIDOR")
    version = await uow.valor("SELECT version FROM pedido WHERE id=%s", (pedidos[0],))
    autenticar(api, rider, rol)
    respuesta = await api.post(
        f"/api/delivery/envios/{envios[0]}/corregir-entrega",
        json={
            "motivo": "Correccion de entrega",
            "version_esperada": version,
            "regreso_confirmado": confirmado,
        },
    )
    assert respuesta.status_code == esperado
    assert await uow.valor("SELECT estado FROM pedido WHERE id=%s", (pedidos[0],)) == "ENTREGADO"
    assert await uow.valor("SELECT viaje_id FROM envio WHERE id=%s", (envios[0],)) == viaje


@pytest.mark.asyncio
async def test_http_personal_consulta_repartidores_disponibles_sin_exponer_datos_privados(uow, api):
    _, rider, _, _, _ = await crear_viaje_propio(uow)
    disponible = await crear_repartidor(uow, uuid4().hex[:12])
    autenticar(api, rider, "EMPLEADO")
    respuesta = await api.get("/api/delivery/repartidores")
    assert respuesta.status_code == 200
    filas = respuesta.json()
    elegido = next(f for f in filas if f["id"] == disponible)
    assert elegido == {"id": disponible, "nombre": "Rider Prueba", "estado": "DISPONIBLE"}
    assert all(f["id"] != rider for f in filas)
    autenticar(api, rider, "REPARTIDOR")
    assert (await api.get("/api/delivery/repartidores")).status_code == 403


@pytest.mark.asyncio
async def test_correccion_entrega_obsoleta_revierte_desvinculacion(uow):
    servicio, rider, viaje, pedidos, envios = await crear_viaje_propio(uow, cantidad=2)
    await servicio.iniciar_viaje(viaje, usuario_id=rider, rol="REPARTIDOR")
    await servicio.registrar_entrega(envios[0], usuario_id=rider, rol="REPARTIDOR")
    with pytest.raises(ReglaDeNegocio):
        async with uow.conn.transaction():
            await servicio.corregir_entrega(
                envios[0],
                motivo="Paquete recibido en local",
                version_esperada=0,
                regreso_confirmado=True,
                usuario_id=rider,
                rol="ADMINISTRADOR",
            )
    assert await uow.valor("SELECT estado FROM pedido WHERE id=%s", (pedidos[0],)) == "ENTREGADO"
    assert await uow.valor("SELECT viaje_id FROM envio WHERE id=%s", (envios[0],)) == viaje
    assert await uow.valor("SELECT estado FROM envio WHERE id=%s", (envios[0],)) == "ENTREGADO"


@pytest.mark.asyncio
async def test_pedido_fallido_no_omite_regreso_por_autoridad_general(uow):
    from app.modules.pedidos.domain.entidades import EstadoPedido
    from app.modules.pedidos.presentation.dependencias import obtener_servicio_pedidos

    servicio, rider, viaje, pedidos, envios = await crear_viaje_propio(uow)
    await servicio.iniciar_viaje(viaje, usuario_id=rider, rol="REPARTIDOR")
    await servicio.registrar_fallo(
        envios[0], motivo="Cliente ausente", rol="REPARTIDOR", usuario_id=rider
    )
    version = await uow.valor("SELECT version FROM pedido WHERE id=%s", (pedidos[0],))
    with pytest.raises(ReglaDeNegocio):
        await obtener_servicio_pedidos(uow).cambiar_estado(
            pedidos[0],
            EstadoPedido.LISTO,
            usuario_id=rider,
            rol="EMPLEADO",
            correccion=True,
            motivo="Omitir regreso",
            version_esperada=version,
        )
    assert await uow.valor("SELECT estado FROM pedido WHERE id=%s", (pedidos[0],)) == "EN_CAMINO"
