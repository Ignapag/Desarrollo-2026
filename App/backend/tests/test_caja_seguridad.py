"""Cortes contables y autoría de caja con PostgreSQL y conexiones independientes."""

import asyncio
from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio

from app.core.db import UnidadDeTrabajo
from app.core.dependencias import obtener_uow
from app.errores import ReglaDeNegocio
from app.modules.pagos.application import servicio_caja as modulo_caja
from app.modules.pagos.application.servicio_caja import ServicioCaja
from app.modules.pagos.application.servicio_conciliacion import ServicioConciliacion
from app.modules.pagos.domain.entidades import TurnoCierre
from app.modules.pagos.infrastructure.repositorio_caja_sql import RepositorioCajaSQL
from app.modules.pagos.infrastructure.repositorio_sql import RepositorioPagosSQL
from app.modules.pagos.presentation.router_caja import router
from tests.soporte_bd import conectar_o_omitir
from tests.test_pagos_privacidad import aplicacion, sesion


@pytest_asyncio.fixture
async def datos_caja():
    conn = await conectar_o_omitir()
    uow = UnidadDeTrabajo(conn)
    cliente = await uow.valor(
        "INSERT INTO cliente (nombre,telefono_whatsapp) VALUES ('Corte caja',%s) RETURNING id",
        (uuid4().hex,),
    )
    pedido = await uow.valor(
        "INSERT INTO pedido (cliente_id,tipo_entrega,subtotal,total) "
        "VALUES (%s,'RETIRO',100,100) RETURNING id",
        (cliente,),
    )
    pago = await uow.valor(
        "INSERT INTO pago (pedido_id,metodo_pago,monto,estado) "
        "VALUES (%s,'TRANSFERENCIA',100,'PENDIENTE') RETURNING id",
        (pedido,),
    )
    actor = await uow.valor("SELECT id FROM usuario WHERE rol='DUENIO' LIMIT 1")
    fecha = date(2080, 1, 1) + timedelta(days=uuid4().int % 10000)
    await conn.commit()
    try:
        yield pedido, pago, actor, fecha
    finally:
        await conn.rollback()
        await uow.ejecutar(
            "DELETE FROM auditoria WHERE (entidad='pago' AND entidad_id IN "
            "(SELECT id::text FROM pago WHERE pedido_id=%s)) OR "
            "(entidad='cierre_caja' AND entidad_id IN "
            "(SELECT id::text FROM cierre_caja WHERE fecha BETWEEN %s AND %s))",
            (pedido, fecha, fecha + timedelta(days=1)),
        )
        await uow.ejecutar("DELETE FROM pago WHERE pedido_id=%s", (pedido,))
        await uow.ejecutar("DELETE FROM pedido WHERE id=%s", (pedido,))
        await uow.ejecutar("DELETE FROM cliente WHERE id=%s", (cliente,))
        await uow.ejecutar(
            "DELETE FROM cierre_caja WHERE fecha BETWEEN %s AND %s",
            (fecha, fecha + timedelta(days=1)),
        )
        await conn.commit()
        await conn.close()


async def acreditar_pago(pago, actor):
    conn = await conectar_o_omitir()
    try:
        uow = UnidadDeTrabajo(conn)
        await ServicioConciliacion(uow, RepositorioPagosSQL(uow)).conciliar_pago(
            pago,
            conciliar_por=actor,
        )
        await conn.commit()
    finally:
        await conn.close()


async def test_cierre_no_vincula_acreditacion_que_llega_despues_de_su_snapshot(
    datos_caja, monkeypatch
):
    _, pago, actor, fecha = datos_caja
    ahora = datetime.now(UTC)
    monkeypatch.setattr(
        modulo_caja,
        "ventana_para_turno",
        lambda *_: (
            ahora - timedelta(minutes=1),
            ahora + timedelta(minutes=1),
        ),
    )
    conn = await conectar_o_omitir()
    try:
        uow = UnidadDeTrabajo(conn)
        repo = RepositorioCajaSQL(uow)
        persistir = repo.crear_o_actualizar_cierre

        async def acreditar_entre_total_y_vinculo(**kwargs):
            await asyncio.wait_for(acreditar_pago(pago, actor), timeout=10)
            return await persistir(**kwargs)

        monkeypatch.setattr(repo, "crear_o_actualizar_cierre", acreditar_entre_total_y_vinculo)
        cierre = await ServicioCaja(uow, repo).generar_resumen_cierre(
            fecha,
            TurnoCierre.MEDIODIA,
            generado_por=actor,
        )
        neto = await uow.valor(
            "SELECT COALESCE(SUM(monto),0) FROM pago WHERE cierre_caja_id=%s",
            (cierre.id,),
        )
        assert cierre.total_general == neto == 0
        assert await uow.valor("SELECT cierre_caja_id FROM pago WHERE id=%s", (pago,)) is None
        await conn.commit()
    finally:
        await conn.close()


async def test_http_caja_autoria_siempre_proviene_de_la_sesion(uow):
    actor = await uow.valor("SELECT id FROM usuario WHERE rol='DUENIO' LIMIT 1")
    otro = await uow.valor("SELECT id FROM usuario WHERE rol='EMPLEADO' LIMIT 1")
    fecha = (date(2100, 1, 1) + timedelta(days=uuid4().int % 10000)).isoformat()
    app = aplicacion()
    app.include_router(router)
    app.dependency_overrides[obtener_uow] = lambda: uow
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app),
        base_url="http://test",
        cookies=sesion(actor, "DUENIO"),
    ) as client:
        respuesta = await client.post(
            "/api/caja/cierres/generar",
            json={
                "fecha": fecha,
                "turno": "MEDIODIA",
                "generado_por": otro,
            },
        )
        assert respuesta.status_code == 201, respuesta.text
        cierre = respuesta.json()
        aprobacion = await client.post(
            f"/api/caja/cierres/{cierre['id']}/aprobar",
            json={
                "aprobado_por": otro,
            },
        )
        assert aprobacion.status_code == 200, aprobacion.text
        assert cierre["generado_por"] == actor
        assert aprobacion.json()["aprobado_por"] == actor
    autores = await uow.todos(
        "SELECT usuario_id FROM auditoria WHERE entidad='cierre_caja' AND entidad_id=%s",
        (str(cierre["id"]),),
    )
    assert len(autores) == 2 and all(a["usuario_id"] == actor for a in autores)


async def test_aprobado_no_cambia_y_acreditacion_tardia_arrastra_a_proximo_cierre(datos_caja):
    _, pago, actor, fecha = datos_caja
    conn = await conectar_o_omitir()
    try:
        uow = UnidadDeTrabajo(conn)
        servicio = ServicioCaja(uow, RepositorioCajaSQL(uow))
        original = await servicio.generar_resumen_cierre(fecha, TurnoCierre.MEDIODIA)
        await servicio.aprobar_y_bloquear_cierre(original.id, actor)
        await conn.commit()
        await acreditar_pago(pago, actor)
        siguiente = await servicio.generar_resumen_cierre(
            fecha + timedelta(days=1), TurnoCierre.MEDIODIA
        )
        assert siguiente.total_general == 100
        assert (
            await uow.valor("SELECT cierre_caja_id FROM pago WHERE id=%s", (pago,)) == siguiente.id
        )
        assert (await servicio.obtener_cierre(original.id)).total_general == 0
        with pytest.raises(ReglaDeNegocio, match="aprobado"):
            await servicio.generar_resumen_cierre(fecha, TurnoCierre.MEDIODIA)
        await conn.commit()
    finally:
        await conn.close()


async def test_consolidado_usa_un_solo_snapshot_para_importes_y_desglose(datos_caja, monkeypatch):
    _, pago, actor, _ = datos_caja
    conn = await conectar_o_omitir()
    try:
        uow = UnidadDeTrabajo(conn)
        original_uno, original_todos = uow.uno, uow.todos
        acreditado = False

        async def despues_de_lectura(lector, sql, parametros=None):
            nonlocal acreditado
            resultado = await lector(sql, parametros)
            if "FROM pago" in sql and not acreditado:
                acreditado = True
                await acreditar_pago(pago, actor)
            return resultado

        monkeypatch.setattr(
            uow, "uno", lambda sql, p=None: despues_de_lectura(original_uno, sql, p)
        )
        monkeypatch.setattr(
            uow, "todos", lambda sql, p=None: despues_de_lectura(original_todos, sql, p)
        )
        ahora = datetime.now(UTC)
        monkeypatch.setattr(
            modulo_caja,
            "ventana_para_turno",
            lambda *_: (
                ahora - timedelta(minutes=1),
                ahora + timedelta(minutes=1),
            ),
        )
        corte = await ServicioCaja(uow, RepositorioCajaSQL(uow)).consolidar_turno(
            date.today(),
            TurnoCierre.MEDIODIA,
        )
        assert acreditado
        assert corte.total_general == 0
        assert corte.desglose_metodos == []
        assert corte.pagos_pendientes_conciliacion == 1
    finally:
        await conn.close()


async def test_generacion_y_aprobacion_concurrentes_publican_el_mismo_corte(
    datos_caja, monkeypatch
):
    _, pago, actor, fecha = datos_caja
    a, b = await conectar_o_omitir(), await conectar_o_omitir()
    capturado, continuar = asyncio.Event(), asyncio.Event()
    tareas = []
    try:
        uow_a, uow_b = UnidadDeTrabajo(a), UnidadDeTrabajo(b)
        repo_a = RepositorioCajaSQL(uow_a)
        servicio_a = ServicioCaja(uow_a, repo_a)
        cierre = await servicio_a.generar_resumen_cierre(fecha, TurnoCierre.MEDIODIA)
        await a.commit()
        await acreditar_pago(pago, actor)
        persistir = repo_a.crear_o_actualizar_cierre

        async def pausar_despues_de_captura(**kwargs):
            capturado.set()
            await continuar.wait()
            return await persistir(**kwargs)

        monkeypatch.setattr(repo_a, "crear_o_actualizar_cierre", pausar_despues_de_captura)

        async def generar():
            try:
                resultado = await servicio_a.generar_resumen_cierre(fecha, TurnoCierre.MEDIODIA)
                await a.commit()
                return resultado
            except BaseException:
                await a.rollback()
                raise

        async def aprobar():
            try:
                resultado = await ServicioCaja(
                    uow_b, RepositorioCajaSQL(uow_b)
                ).aprobar_y_bloquear_cierre(
                    cierre.id,
                    actor,
                )
                await b.commit()
                return resultado
            except BaseException:
                await b.rollback()
                raise

        pid_b = await uow_b.valor("SELECT pg_backend_pid()")
        tarea_a = asyncio.create_task(generar())
        tareas.append(tarea_a)
        await asyncio.wait_for(capturado.wait(), timeout=10)
        tarea_b = asyncio.create_task(aprobar())
        tareas.append(tarea_b)
        bloqueada = False
        for _ in range(300):
            bloqueada = bool(
                await uow_a.valor("SELECT cardinality(pg_blocking_pids(%s))", (pid_b,))
            )
            if bloqueada or tarea_b.done():
                break
            await asyncio.sleep(0.01)
        assert bloqueada, "Aprobación debe esperar el snapshot y los vínculos de generación"
        continuar.set()
        generado, aprobado = await asyncio.wait_for(asyncio.gather(*tareas), timeout=10)
        assert generado.total_general == aprobado.total_general == 100
        assert (
            await uow_b.valor("SELECT SUM(monto) FROM pago WHERE cierre_caja_id=%s", (cierre.id,))
            == 100
        )
    finally:
        continuar.set()
        if tareas:
            await asyncio.wait_for(asyncio.gather(*tareas, return_exceptions=True), timeout=10)
        await a.close()
        await b.close()


async def test_dos_turnos_concurrentes_no_cuentan_dos_veces_el_arrastre(datos_caja):
    _, pago, actor, fecha = datos_caja
    await acreditar_pago(pago, actor)

    async def generar_cierre(fecha_caja):
        conn = await conectar_o_omitir()
        try:
            uow = UnidadDeTrabajo(conn)
            resultado = await ServicioCaja(uow, RepositorioCajaSQL(uow)).generar_resumen_cierre(
                fecha_caja,
                TurnoCierre.MEDIODIA,
            )
            await conn.commit()
            return resultado
        finally:
            await conn.close()

    cierres = await asyncio.wait_for(
        asyncio.gather(
            generar_cierre(fecha),
            generar_cierre(fecha + timedelta(days=1)),
        ),
        timeout=10,
    )
    assert sorted(c.total_general for c in cierres) == [0, 100]


async def test_aprobacion_rechaza_cierre_historico_con_suma_inconsistente(uow):
    cierre_id = await uow.valor(
        "INSERT INTO cierre_caja (fecha,turno,total_general,estado) "
        "VALUES (%s,'MEDIODIA',100,'PENDIENTE_APROBACION') RETURNING id",
        (date(2200, 1, 1) + timedelta(days=uuid4().int % 10000),),
    )
    actor = await uow.valor("SELECT id FROM usuario WHERE rol='DUENIO' LIMIT 1")
    with pytest.raises(ReglaDeNegocio, match="no coinciden"):
        await ServicioCaja(uow, RepositorioCajaSQL(uow)).aprobar_y_bloquear_cierre(cierre_id, actor)


async def test_aprobacion_que_gana_la_carrera_impide_regeneracion(datos_caja, monkeypatch):
    _, pago, actor, fecha = datos_caja
    await acreditar_pago(pago, actor)
    a, b = await conectar_o_omitir(), await conectar_o_omitir()
    capturado, continuar = asyncio.Event(), asyncio.Event()
    tareas = []
    try:
        uow_a, uow_b = UnidadDeTrabajo(a), UnidadDeTrabajo(b)
        repo_a = RepositorioCajaSQL(uow_a)
        servicio_a = ServicioCaja(uow_a, repo_a)
        cierre = await servicio_a.generar_resumen_cierre(fecha, TurnoCierre.MEDIODIA)
        await a.commit()
        aprobar_original = repo_a.aprobar_cierre

        async def pausar_aprobacion(**kwargs):
            capturado.set()
            await continuar.wait()
            return await aprobar_original(**kwargs)

        monkeypatch.setattr(repo_a, "aprobar_cierre", pausar_aprobacion)

        async def aprobar():
            try:
                resultado = await servicio_a.aprobar_y_bloquear_cierre(cierre.id, actor)
                await a.commit()
                return resultado
            except BaseException:
                await a.rollback()
                raise

        async def generar():
            try:
                return await ServicioCaja(uow_b, RepositorioCajaSQL(uow_b)).generar_resumen_cierre(
                    fecha,
                    TurnoCierre.MEDIODIA,
                )
            finally:
                await b.rollback()

        pid_b = await uow_b.valor("SELECT pg_backend_pid()")
        tarea_a = asyncio.create_task(aprobar())
        tareas.append(tarea_a)
        await asyncio.wait_for(capturado.wait(), timeout=10)
        tarea_b = asyncio.create_task(generar())
        tareas.append(tarea_b)
        bloqueada = False
        for _ in range(300):
            bloqueada = bool(
                await uow_a.valor("SELECT cardinality(pg_blocking_pids(%s))", (pid_b,))
            )
            if bloqueada or tarea_b.done():
                break
            await asyncio.sleep(0.01)
        assert bloqueada
        continuar.set()
        aprobado, error = await asyncio.wait_for(
            asyncio.gather(*tareas, return_exceptions=True),
            timeout=10,
        )
        assert aprobado.total_general == 100 and aprobado.es_aprobado
        assert isinstance(error, ReglaDeNegocio)
        assert "aprobado" in str(error)
    finally:
        continuar.set()
        if tareas:
            await asyncio.wait_for(asyncio.gather(*tareas, return_exceptions=True), timeout=10)
        await a.close()
        await b.close()


async def test_regenerar_historico_conserva_vinculado_acreditado_despues_del_corte(uow):
    fecha = date(1900, 1, 1)
    cliente = await uow.valor(
        "INSERT INTO cliente (nombre,telefono_whatsapp) VALUES ('Historico caja',%s) RETURNING id",
        (uuid4().hex,),
    )
    pedido = await uow.valor(
        "INSERT INTO pedido (cliente_id,tipo_entrega,subtotal,total) "
        "VALUES (%s,'RETIRO',200,200) RETURNING id",
        (cliente,),
    )
    cierre_id = await uow.valor(
        "INSERT INTO cierre_caja "
        "(fecha,turno,total_billeteras,total_general,cantidad_pedidos,estado) "
        "VALUES (%s,'MEDIODIA',100,100,1,'PENDIENTE_APROBACION') RETURNING id",
        (fecha,),
    )
    pago_historico = await uow.valor(
        "INSERT INTO pago (pedido_id,cierre_caja_id,metodo_pago,monto,estado,registrado_en,"
        "conciliado_en,referencia_externa) VALUES (%s,%s,'TRANSFERENCIA',100,'CONCILIADO',"
        "'1900-01-01 12:00:00+00','1900-01-02 12:00:00+00','HISTORICO') RETURNING id",
        (pedido, cierre_id),
    )
    pago_tardio = await uow.valor(
        "INSERT INTO pago (pedido_id,metodo_pago,monto,estado,registrado_en,conciliado_en) "
        "VALUES (%s,'TRANSFERENCIA',30,'CONCILIADO','1900-01-01 13:00:00+00',"
        "'1900-01-02 13:00:00+00') RETURNING id",
        (pedido,),
    )
    historico_antes = await RepositorioPagosSQL(uow).obtener_pago_por_id(pago_historico)
    servicio = ServicioCaja(uow, RepositorioCajaSQL(uow))
    regenerado = await servicio.generar_resumen_cierre(fecha, TurnoCierre.MEDIODIA)
    assert regenerado.id == cierre_id and regenerado.total_general == 100
    assert (
        await uow.valor(
            "SELECT SUM(monto) FROM pago WHERE cierre_caja_id=%s",
            (cierre_id,),
        )
        == 100
    )
    assert await uow.valor("SELECT cierre_caja_id FROM pago WHERE id=%s", (pago_tardio,)) is None
    assert await RepositorioPagosSQL(uow).obtener_pago_por_id(pago_historico) == historico_antes
    actor = await uow.valor("SELECT id FROM usuario WHERE rol='DUENIO' LIMIT 1")
    aprobado = await servicio.aprobar_y_bloquear_cierre(cierre_id, actor)
    assert aprobado.es_aprobado and aprobado.total_general == 100
    siguiente = await servicio.generar_resumen_cierre(
        fecha + timedelta(days=1), TurnoCierre.MEDIODIA
    )
    assert siguiente.total_general == 30
    assert (
        await uow.valor("SELECT cierre_caja_id FROM pago WHERE id=%s", (pago_tardio,))
        == siguiente.id
    )
    assert (
        await uow.valor("SELECT cierre_caja_id FROM pago WHERE id=%s", (pago_historico,))
        == cierre_id
    )
    assert await servicio.obtener_cierre(cierre_id) == aprobado
    with pytest.raises(ReglaDeNegocio, match="aprobado"):
        await servicio.generar_resumen_cierre(fecha, TurnoCierre.MEDIODIA)
