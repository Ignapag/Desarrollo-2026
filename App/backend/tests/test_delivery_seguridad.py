"""Regresiones de entrega, autoria y concurrencia contra PostgreSQL descartable."""

from __future__ import annotations

import asyncio
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio

from app.core.config import settings
from app.core.db import UnidadDeTrabajo
from app.core.dependencias import obtener_uow
from app.core.seguridad import crear_token
from app.errores import ReglaDeNegocio
from app.main import app
from app.modules.delivery.presentation.dependencias import obtener_servicio_delivery
from app.modules.usuarios.presentation.dependencias import sesion_vigente, usuario_actual
from tests.soporte_bd import conectar_o_omitir
from tests.test_delivery_bd import ENSENADA_CENTRO, crear_pedido_listo


async def crear_repartidor(uow, sufijo):
    usuario_id = await uow.valor(
        """INSERT INTO usuario(nombre,apellido,username,password_hash,rol)
           VALUES ('Rider','Prueba',%s,'x','REPARTIDOR') RETURNING id""",
        (f"rider_{sufijo}",),
    )
    await uow.ejecutar("INSERT INTO repartidor(usuario_id) VALUES (%s)", (usuario_id,))
    return usuario_id


async def crear_viaje_propio(uow, *, cantidad=1):
    sufijo = uuid4().hex[:12]
    rider = await crear_repartidor(uow, sufijo)
    servicio = obtener_servicio_delivery(uow)
    viaje = await servicio.repo.crear_viaje(rider, asignado_por=rider, automatica=False)
    pedidos, envios = [], []
    for indice in range(cantidad):
        pedido = await crear_pedido_listo(uow, f"{sufijo}_{indice}", ENSENADA_CENTRO)
        envio = await servicio.repo.asignar_envio(
            pedido_id=pedido, viaje_id=viaje, zona_id=None, orden=indice + 1, distancia_km=None
        )
        pedidos.append(pedido)
        envios.append(envio)
    await servicio.repo.cambiar_estado_repartidor(rider, "EN_RUTA")
    return servicio, rider, viaje, pedidos, envios


def autenticar(api, usuario_id, rol):
    api.cookies.set(
        settings.cookie_sesion,
        crear_token(usuario_id=usuario_id, rol=rol, username="prueba_delivery"),
    )


@pytest_asyncio.fixture
async def api(uow):
    async def unidad_prueba():
        yield uow

    app.dependency_overrides[obtener_uow] = unidad_prueba
    # Las pruebas inyectan actores de distintos roles para aislar las reglas logisticas.
    app.dependency_overrides[sesion_vigente] = usuario_actual
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as cliente:
            yield cliente
    finally:
        app.dependency_overrides.pop(obtener_uow, None)
        app.dependency_overrides.pop(sesion_vigente, None)


@pytest.mark.asyncio
async def test_http_repartidor_solo_ve_y_opera_su_viaje(uow, api):
    _, rider, viaje, pedidos, envios = await crear_viaje_propio(uow)
    otro = await crear_repartidor(uow, uuid4().hex[:12])
    autenticar(api, otro, "REPARTIDOR")
    for ruta in (f"/viajes/{viaje}", f"/repartidores/{rider}/viaje"):
        assert (await api.get(f"/api/delivery{ruta}")).status_code == 403
    for ruta in (f"/viajes/{viaje}/iniciar", f"/envios/{envios[0]}/entregar"):
        assert (await api.post(f"/api/delivery{ruta}")).status_code == 403
    assert (await api.post("/api/delivery/planificacion")).status_code == 403
    assert (await api.get("/api/delivery/viajes")).json() == []

    autenticar(api, rider, "REPARTIDOR")
    detalle = (await api.get(f"/api/delivery/viajes/{viaje}")).json()
    envio = detalle["envios"][0]
    assert envio["envio_id"] == envios[0]
    assert envio["viaje_id"] == viaje
    assert envio["pedido_id"] == pedidos[0]
    assert envio["numero"] > 0 and envio["telefono_cliente"] and envio["calle"]
    assert "saldo_pendiente" in envio
    assert (await api.post(f"/api/delivery/viajes/{viaje}/iniciar")).status_code == 200
    assert (await api.post(f"/api/delivery/envios/{envios[0]}/entregar")).status_code == 200
    historia = await uow.todos(
        "SELECT usuario_id FROM pedido_estado_historial WHERE pedido_id=%s", (pedidos[0],)
    )
    assert len(historia) == 2 and all(f["usuario_id"] == rider for f in historia)
    assert (
        await uow.valor(
            "SELECT usuario_id FROM auditoria WHERE accion='ENVIO_ENTREGADO' AND entidad_id=%s",
            (str(envios[0]),),
        )
        == rider
    )


@pytest.mark.asyncio
async def test_entrega_rechazada_por_pedido_revierte_envio_y_viaje(uow):
    servicio, rider, viaje, pedidos, envios = await crear_viaje_propio(uow)
    await servicio.iniciar_viaje(viaje, usuario_id=rider, rol="REPARTIDOR")
    await uow.ejecutar("UPDATE pedido SET estado='CANCELADO' WHERE id=%s", (pedidos[0],))
    with pytest.raises(ReglaDeNegocio):
        async with uow.conn.transaction():
            await servicio.registrar_entrega(envios[0], usuario_id=rider, rol="REPARTIDOR")
    assert await uow.valor("SELECT estado FROM envio WHERE id=%s", (envios[0],)) == "EN_CAMINO"
    assert await uow.valor("SELECT estado FROM viaje WHERE id=%s", (viaje,)) == "EN_RUTA"
    assert await uow.valor("SELECT estado FROM pedido WHERE id=%s", (pedidos[0],)) == "CANCELADO"


@pytest.mark.asyncio
async def test_fallo_y_regreso_permiten_corregir_y_reasignar_sin_recrear(uow):
    servicio, rider, viaje, pedidos, envios = await crear_viaje_propio(uow)
    await servicio.iniciar_viaje(viaje, usuario_id=rider, rol="REPARTIDOR")
    await servicio.registrar_fallo(
        envios[0], motivo="No hay nadie", usuario_id=rider, rol="REPARTIDOR"
    )
    assert await uow.valor("SELECT estado FROM viaje WHERE id=%s", (viaje,)) == "EN_RUTA"
    assert await uow.valor("SELECT estado FROM pedido WHERE id=%s", (pedidos[0],)) == "EN_CAMINO"
    version = await uow.valor("SELECT version FROM pedido WHERE id=%s", (pedidos[0],))
    await servicio.confirmar_regreso(
        envios[0],
        motivo="Pedido recibido en local",
        version_esperada=version,
        usuario_id=rider,
        rol="EMPLEADO",
    )
    assert await uow.valor("SELECT estado FROM pedido WHERE id=%s", (pedidos[0],)) == "LISTO"
    assert await uow.valor("SELECT estado FROM viaje WHERE id=%s", (viaje,)) == "FINALIZADO"
    nueva = await servicio.asignar_pedido(
        pedidos[0], rider, motivo="Reintentar entrega", usuario_id=rider, rol="EMPLEADO"
    )
    assert nueva["envio_id"] == envios[0] and nueva["viaje_id"] != viaje


@pytest.mark.asyncio
async def test_entrega_corregida_puede_tener_nueva_asignacion_real(uow):
    servicio, rider, viaje, pedidos, envios = await crear_viaje_propio(uow)
    await servicio.iniciar_viaje(viaje, usuario_id=rider, rol="REPARTIDOR")
    await servicio.registrar_entrega(envios[0], usuario_id=rider, rol="REPARTIDOR")
    version = await uow.valor("SELECT version FROM pedido WHERE id=%s", (pedidos[0],))
    await servicio.corregir_entrega(
        envios[0],
        usuario_id=rider,
        rol="ADMINISTRADOR",
        motivo="Click erroneo; paquete recibido en local",
        version_esperada=version,
        regreso_confirmado=True,
    )
    nueva = await servicio.asignar_pedido(
        pedidos[0], rider, motivo="Entrega corregida", usuario_id=rider, rol="EMPLEADO"
    )
    assert nueva["viaje_id"] != viaje and nueva["envio_id"] == envios[0]
    assert await uow.valor("SELECT estado FROM pedido WHERE id=%s", (pedidos[0],)) == "LISTO"
    assert await uow.valor("SELECT estado FROM envio WHERE id=%s", (envios[0],)) == "ASIGNADO"
    anterior = await uow.uno(
        "SELECT datos FROM auditoria WHERE accion='ENVIO_ENTREGA_CORREGIDA' AND entidad_id=%s",
        (str(envios[0]),),
    )
    assert anterior["datos"]["envio_anterior"]["viaje_id"] == viaje
    assert anterior["datos"]["regreso_confirmado"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize("estado,tipo", [("LISTO", "RETIRO"), ("EN_PREPARACION", "DELIVERY")])
async def test_asignacion_manual_no_despacha_retiro_ni_pedido_no_listo(uow, estado, tipo):
    servicio, rider, _, pedidos, envios = await crear_viaje_propio(uow)
    await servicio.desasignar_envio(envios[0], motivo="Corregir", rol="EMPLEADO")
    await uow.ejecutar(
        "UPDATE pedido SET estado=%s,tipo_entrega=%s WHERE id=%s", (estado, tipo, pedidos[0])
    )
    with pytest.raises(ReglaDeNegocio):
        await servicio.asignar_pedido(pedidos[0], rider, motivo="Nueva asignacion", rol="EMPLEADO")
    assert await uow.valor("SELECT viaje_id FROM envio WHERE id=%s", (envios[0],)) is None


@pytest.mark.asyncio
async def test_regreso_con_version_obsoleta_revierte_desasignacion(uow):
    servicio, rider, viaje, pedidos, envios = await crear_viaje_propio(uow)
    await servicio.iniciar_viaje(viaje, usuario_id=rider, rol="REPARTIDOR")
    await servicio.registrar_fallo(envios[0], motivo="Domicilio cerrado", rol="EMPLEADO")
    with pytest.raises(ReglaDeNegocio):
        async with uow.conn.transaction():
            await servicio.confirmar_regreso(
                envios[0], motivo="Regreso", version_esperada=0, rol="EMPLEADO"
            )
    assert await uow.valor("SELECT viaje_id FROM envio WHERE id=%s", (envios[0],)) == viaje
    assert await uow.valor("SELECT estado FROM envio WHERE id=%s", (envios[0],)) == "FALLIDO"


@pytest.mark.asyncio
async def test_reasignacion_atomica_fallida_conserva_viaje_original(uow):
    servicio, _, viaje, _, envios = await crear_viaje_propio(uow)
    _, ocupado, _, _, _ = await crear_viaje_propio(uow)
    with pytest.raises(ReglaDeNegocio):
        async with uow.conn.transaction():
            await servicio.reasignar_envio(
                envios[0], ocupado, motivo="Cambiar repartidor", rol="EMPLEADO"
            )
    assert await uow.valor("SELECT viaje_id FROM envio WHERE id=%s", (envios[0],)) == viaje
    assert await uow.valor("SELECT estado FROM viaje WHERE id=%s", (viaje,)) == "PLANIFICADO"


@pytest.mark.asyncio
async def test_http_reasignacion_persiste_viaje_real_y_actor(uow, api):
    _, rider, viaje, pedidos, envios = await crear_viaje_propio(uow)
    nuevo = await crear_repartidor(uow, uuid4().hex[:12])
    autenticar(api, rider, "EMPLEADO")
    respuesta = await api.post(
        f"/api/delivery/envios/{envios[0]}/reasignar",
        json={"repartidor_id": nuevo, "motivo": "Relevo en el local"},
    )
    assert respuesta.status_code == 200
    resultado = respuesta.json()
    assert resultado["viaje_id"] != viaje
    assert resultado["envio_id"] == envios[0] and resultado["pedido_id"] == pedidos[0]
    assert await uow.valor("SELECT estado FROM viaje WHERE id=%s", (viaje,)) == "CANCELADO"
    assert (
        await uow.valor("SELECT asignado_por FROM viaje WHERE id=%s", (resultado["viaje_id"],))
        == rider
    )
    assert (
        await uow.valor("SELECT repartidor_id FROM viaje WHERE id=%s", (resultado["viaje_id"],))
        == nuevo
    )


@pytest.mark.asyncio
async def test_dos_entregas_concurrentes_serializan_cierre_del_mismo_viaje():
    uno, dos = await conectar_o_omitir(), await conectar_o_omitir()
    uow1, uow2 = UnidadDeTrabajo(uno), UnidadDeTrabajo(dos)
    pedidos, envios, cliente_ids, usuarios = [], [], [], []
    viaje = rider = None
    tarea = None
    try:
        servicio, rider, viaje, pedidos, envios = await crear_viaje_propio(uow1, cantidad=2)
        cliente_ids = [
            f["cliente_id"]
            for f in await uow1.todos("SELECT cliente_id FROM pedido WHERE id=ANY(%s)", (pedidos,))
        ]
        usuarios = [
            f["usuario_id"]
            for f in await uow1.todos(
                "SELECT usuario_id FROM cliente WHERE id=ANY(%s)", (cliente_ids,)
            )
        ]
        await servicio.iniciar_viaje(viaje, usuario_id=rider, rol="REPARTIDOR")
        await uno.commit()
        primera = await servicio.registrar_entrega(envios[0], usuario_id=rider, rol="REPARTIDOR")
        assert primera["viaje_finalizado"] is False
        otro = obtener_servicio_delivery(uow2)
        tarea = asyncio.create_task(
            otro.registrar_entrega(envios[1], usuario_id=rider, rol="REPARTIDOR")
        )
        # La primera entrega sigue sin commit: la segunda debe esperar el viaje.
        terminadas, _ = await asyncio.wait({tarea}, timeout=0.15)
        assert not terminadas, "La segunda entrega avanzo sin serializar el viaje"
        await uno.commit()
        segunda = await asyncio.wait_for(tarea, timeout=5)
        await dos.commit()
        assert segunda["viaje_finalizado"] is True
        assert await uow1.valor("SELECT estado FROM viaje WHERE id=%s", (viaje,)) == "FINALIZADO"
        assert (
            await uow1.valor("SELECT estado FROM repartidor WHERE usuario_id=%s", (rider,))
            == "DISPONIBLE"
        )
        assert (
            await uow1.valor(
                "SELECT count(*) FROM pedido WHERE id=ANY(%s) AND estado='ENTREGADO'", (pedidos,)
            )
            == 2
        )
    finally:
        if tarea and not tarea.done():
            tarea.cancel()
            await asyncio.gather(tarea, return_exceptions=True)
        await dos.rollback()
        await uno.rollback()
        if rider:
            await uow1.ejecutar("DELETE FROM auditoria WHERE usuario_id=%s", (rider,))
            await uow1.ejecutar("DELETE FROM pedido WHERE id=ANY(%s)", (pedidos,))
            await uow1.ejecutar("DELETE FROM viaje WHERE id=%s", (viaje,))
            await uow1.ejecutar("DELETE FROM direccion WHERE cliente_id=ANY(%s)", (cliente_ids,))
            await uow1.ejecutar("DELETE FROM cliente WHERE id=ANY(%s)", (cliente_ids,))
            await uow1.ejecutar("DELETE FROM repartidor WHERE usuario_id=%s", (rider,))
            await uow1.ejecutar("DELETE FROM usuario WHERE id=ANY(%s)", ([rider, *usuarios],))
            await uno.commit()
        await uno.close()
        await dos.close()


@pytest.mark.asyncio
async def test_edicion_modalidad_gana_carrera_a_asignacion_sin_envio_huerfano():
    from app.modules.pedidos.presentation.dependencias import obtener_servicio_pedidos

    uno, dos = await conectar_o_omitir(), await conectar_o_omitir()
    uow1, uow2 = UnidadDeTrabajo(uno), UnidadDeTrabajo(dos)
    pedido = rider = cliente = usuario = None
    tarea = None
    try:
        sufijo = uuid4().hex[:12]
        pedido = await crear_pedido_listo(uow1, sufijo, ENSENADA_CENTRO)
        rider = await crear_repartidor(uow1, sufijo)
        cliente = await uow1.valor("SELECT cliente_id FROM pedido WHERE id=%s", (pedido,))
        usuario = await uow1.valor("SELECT usuario_id FROM cliente WHERE id=%s", (cliente,))
        await uno.commit()
        version = await uow1.valor("SELECT version FROM pedido WHERE id=%s", (pedido,))
        await obtener_servicio_pedidos(uow1).editar_operacion(
            pedido,
            cambios={"tipo_entrega": "RETIRO"},
            motivo="Retira en local",
            version_esperada=version,
            usuario_id=rider,
            rol="EMPLEADO",
        )
        tarea = asyncio.create_task(
            obtener_servicio_delivery(uow2).asignar_pedido(
                pedido, rider, motivo="Asignar al reparto", usuario_id=rider, rol="EMPLEADO"
            )
        )
        terminadas, _ = await asyncio.wait({tarea}, timeout=0.15)
        assert not terminadas, "La asignacion no espero el bloqueo del pedido"
        await uno.commit()
        with pytest.raises(ReglaDeNegocio):
            await asyncio.wait_for(tarea, timeout=5)
        await dos.rollback()
        assert (
            await uow1.valor("SELECT tipo_entrega FROM pedido WHERE id=%s", (pedido,)) == "RETIRO"
        )
        assert await uow1.valor("SELECT count(*) FROM envio WHERE pedido_id=%s", (pedido,)) == 0
        assert await uow1.valor("SELECT count(*) FROM viaje WHERE repartidor_id=%s", (rider,)) == 0
    finally:
        if tarea and not tarea.done():
            tarea.cancel()
            await asyncio.gather(tarea, return_exceptions=True)
        await dos.rollback()
        await uno.rollback()
        if rider:
            await uow1.ejecutar("DELETE FROM auditoria WHERE usuario_id=%s", (rider,))
            await uow1.ejecutar("DELETE FROM pedido WHERE id=%s", (pedido,))
            await uow1.ejecutar("DELETE FROM direccion WHERE cliente_id=%s", (cliente,))
            await uow1.ejecutar("DELETE FROM cliente WHERE id=%s", (cliente,))
            await uow1.ejecutar("DELETE FROM repartidor WHERE usuario_id=%s", (rider,))
            await uow1.ejecutar("DELETE FROM usuario WHERE id=ANY(%s)", ([rider, usuario],))
            await uno.commit()
        await uno.close()
        await dos.close()
