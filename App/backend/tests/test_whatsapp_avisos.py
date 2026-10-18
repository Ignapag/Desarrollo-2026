"""Resumen privado de tareas humanas: sin conversaciones ni adjuntos."""

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.dependencias import obtener_uow
from app.core.seguridad import crear_token
from app.modules.whatsapp.infrastructure.cola import ColaWhatsAppSQL
from tests.test_whatsapp_http import aplicacion


@pytest.mark.parametrize("rol", [None, "CLIENTE", "REPARTIDOR"])
@pytest.mark.parametrize("ruta", ["/avisos", "/atenciones/1/archivo"])
def test_avisos_rechazan_antes_de_conectar(rol, ruta):
    app = aplicacion()

    async def no_conectar():
        pytest.fail("Un visitante no puede consultar tareas internas")

    app.dependency_overrides[obtener_uow] = no_conectar
    with TestClient(app) as cliente:
        if rol:
            cliente.cookies.set(settings.cookie_sesion, crear_token(
                usuario_id=1, rol=rol, username="prueba"
            ))
        assert cliente.get("/api/whatsapp" + ruta).status_code == (403 if rol else 401)


@pytest.mark.parametrize("rol", ["EMPLEADO", "ADMINISTRADOR", "DUENIO"])
def test_avisos_solo_cantidades_y_sin_cache(rol):
    app = aplicacion()

    class Resumen:
        async def uno(self, sql):
            assert "whatsapp_comprobante" in sql and "whatsapp_atencion" in sql
            assert sql.count("estado='PENDIENTE'") == 3
            return {"comprobantes_pendientes": 2, "atenciones_pendientes": 3}

    async def uow():
        return Resumen()

    app.dependency_overrides[obtener_uow] = uow
    with TestClient(app) as cliente:
        cliente.cookies.set(settings.cookie_sesion, crear_token(
            usuario_id=1, rol=rol, username="prueba"
        ))
        result = cliente.get("/api/whatsapp/avisos")
        assert result.status_code == 200
        assert result.json() == {"comprobantes_pendientes": 2, "atenciones_pendientes": 3}
        assert "no-store" in result.headers["cache-control"]


@pytest.mark.asyncio
async def test_avisos_reflejan_atencion_persistente_y_resolucion(uow):
    from app.modules.whatsapp.presentation.dependencias import construir_servicio
    from tests.test_whatsapp_regresiones import derivar_borrador, empleado

    cola = ColaWhatsAppSQL(uow)
    antes = await cola.avisos()
    servicio = construir_servicio(uow)
    _, identificador = await derivar_borrador(uow, servicio)
    pendientes = await cola.avisos()
    assert pendientes["atenciones_pendientes"] == antes["atenciones_pendientes"] + 1
    await servicio.resolver_atencion(identificador, await empleado(uow), "Atendido en persona")
    assert await cola.avisos() == antes


@pytest.mark.asyncio
async def test_avisos_comprobante_repetido_rechazado_y_aprobado(uow):
    from tests.test_whatsapp_bd import crear_pedido_bot
    from tests.test_whatsapp_regresiones import empleado

    cola = ColaWhatsAppSQL(uow)
    antes = await cola.avisos()
    servicio, pedido_id = await crear_pedido_bot(uow, metodo="TRANSFERENCIA")
    for identificador, aprobar in (("rechazado", False), ("aprobado", True)):
        for _ in range(2):
            await servicio.recibir(identificador, "5492215550000", "", "foto-prueba")
            await servicio.procesar(identificador, {"accion": "consulta", "argumentos": {}})
        pendientes = await cola.avisos()
        assert pendientes["comprobantes_pendientes"] == antes["comprobantes_pendientes"] + 1
        comprobante_id = await uow.valor(
            "SELECT id FROM whatsapp_comprobante WHERE entrada_id=%s", (identificador,)
        )
        total = await uow.valor("SELECT total FROM pedido WHERE id=%s", (pedido_id,))
        await servicio.revisar_comprobante(
            comprobante_id, aprobar, await empleado(uow), "Verificado por el empleado",
            total_verificado=total if aprobar else None,
        )
        assert await cola.avisos() == antes


@pytest.mark.asyncio
async def test_avisos_generales_y_cupo_independiente_por_categoria(uow):
    from app.modules.whatsapp.presentation.dependencias import construir_servicio
    from tests.test_whatsapp_regresiones import empleado

    # Una cola de consultas antiguas no debe ocultar un comprobante nuevo.
    await uow.ejecutar(
        """INSERT INTO whatsapp_entrada (id,telefono,texto)
        SELECT 'consulta-masiva-'||n, '54922155'||lpad(n::text,5,'0'), 'Empleado'
        FROM generate_series(1,101) n"""
    )
    await uow.ejecutar(
        """INSERT INTO whatsapp_atencion (telefono,entrada_id,motivo)
        SELECT telefono,id,'SOLICITUD' FROM whatsapp_entrada WHERE id LIKE 'consulta-masiva-%'"""
    )
    servicio = construir_servicio(uow)
    await servicio.recibir("recibo-sin-compra", "5492215550999", "", "adjunto-sin-compra")
    await servicio.procesar("recibo-sin-compra", {"accion": "consulta"})
    cola = ColaWhatsAppSQL(uow)
    assert await cola.avisos() == {"comprobantes_pendientes": 1, "atenciones_pendientes": 101}
    bandeja = await cola.bandeja()
    recibo = next(a for a in bandeja["atenciones"] if a["motivo"] == "COMPROBANTE")
    assert recibo["telefono"] == "5492215550999" and recibo["tiene_archivo"]
    assert recibo["pedido_id"] is None and recibo["productos"] == []
    assert recibo["mensajes"] == []
    assert len(bandeja["atenciones"]) == 101
    await servicio.resolver_atencion(recibo["id"], await empleado(uow), "Consulta atendida")
    assert await cola.avisos() == {"comprobantes_pendientes": 0, "atenciones_pendientes": 101}


@pytest.mark.asyncio
async def test_archivo_general_autenticado_no_expone_url_del_proveedor(uow, monkeypatch):
    from contextlib import asynccontextmanager
    from types import SimpleNamespace

    import httpx

    from app.modules.whatsapp.presentation import router as modulo
    from app.modules.whatsapp.presentation.dependencias import construir_servicio

    servicio = construir_servicio(uow)
    await servicio.recibir("archivo-general", "5492215550999", "", "media-prueba")
    await servicio.procesar("archivo-general", {"accion": "consulta"})
    identificador = await uow.valor("SELECT id FROM whatsapp_atencion WHERE motivo='COMPROBANTE'")

    @asynccontextmanager
    async def conexion_prueba():
        yield uow.conn

    async def bajar(media):
        assert media == "media-prueba"
        return b"%PDF-prueba", "application/pdf"

    monkeypatch.setattr(modulo, "conexion", conexion_prueba)
    monkeypatch.setattr(settings, "whatsapp_modo", "real")
    monkeypatch.setattr(modulo, "transporte", lambda: SimpleNamespace(bajar_comprobante=bajar))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=aplicacion()), base_url="http://prueba",
        cookies={settings.cookie_sesion: crear_token(
            usuario_id=1, rol="EMPLEADO", username="prueba"
        )},
    ) as cliente:
        respuesta = await cliente.get(f"/api/whatsapp/atenciones/{identificador}/archivo")
        assert respuesta.status_code == 200
        assert respuesta.content == b"%PDF-prueba"
        assert respuesta.headers["content-type"] == "application/pdf"
        assert respuesta.headers["x-content-type-options"] == "nosniff"
        assert respuesta.headers["cache-control"] == "no-store"
        assert "attachment" in respuesta.headers["content-disposition"]
        assert (await cliente.get("/api/whatsapp/atenciones/999999/archivo")).status_code == 404
