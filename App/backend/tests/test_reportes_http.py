"""Contratos y permisos vigentes de analítica contra PostgreSQL descartable."""

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI

from app.core.config import settings
from app.core.dependencias import obtener_uow
from app.core.errores import manejador_error_dominio
from app.core.seguridad import crear_token
from app.errores import ErrorDominio
from app.modules.reportes.presentation.router import router
from tests.test_reportes_bd import escenario, pedido_con_item


@pytest_asyncio.fixture
async def api(uow):
    app = FastAPI()
    app.include_router(router)
    app.add_exception_handler(ErrorDominio, manejador_error_dominio)
    app.dependency_overrides[obtener_uow] = lambda: uow
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://prueba"
    ) as client:
        yield client


async def permisos(api, uow, autorizados):
    identidad = await uow.uno("SELECT id, rol, username FROM usuario WHERE username='taramburu'")
    assert identidad["rol"] == "EMPLEADO"
    await uow.ejecutar("DELETE FROM rol_permiso WHERE rol='EMPLEADO'")
    for permiso in autorizados:
        await uow.ejecutar(
            "INSERT INTO rol_permiso (rol, permiso) VALUES ('EMPLEADO', %s)", (permiso,)
        )
    api.cookies.set(settings.cookie_sesion, crear_token(
        usuario_id=identidad["id"], rol=identidad["rol"], username=identidad["username"]
    ))


QUERY = "?fecha_desde=2026-09-01&fecha_hasta=2026-09-01"


@pytest.mark.parametrize("endpoint", ["dashboard", "ventas", "rentabilidad"])
async def test_sin_sesion_no_accede(api, endpoint):
    assert (await api.get(f"/api/reportes/{endpoint}{QUERY}&agrupacion=DIA")).status_code == 401


@pytest.mark.parametrize("autorizados", [[], ["reportes.financieros"]])
@pytest.mark.parametrize("endpoint", ["dashboard", "ventas", "rentabilidad"])
async def test_sin_lectura_no_accede_a_reportes(api, uow, autorizados, endpoint):
    await permisos(api, uow, autorizados)
    assert (await api.get(f"/api/reportes/{endpoint}{QUERY}&agrupacion=DIA")).status_code == 403


async def test_contratos_filtros_y_revocacion_misma_cookie(api, uow):
    from datetime import UTC, datetime

    cliente, _, productos = await escenario(uow)
    await pedido_con_item(
        uow, cliente, productos[0], "CONFIRMADO", datetime(2026, 9, 1, 15, tzinfo=UTC), cantidad=3
    )
    await permisos(api, uow, ["reportes.ver"])
    ruta = f"/api/reportes/ventas{QUERY}&agrupacion=DIA&producto_id={productos[0]}"
    basico = await api.get(ruta)
    assert basico.status_code == 200, basico.text
    assert basico.json()[0]["cantidad_vendida"] == 3
    assert basico.json()[0]["cantidad_pedidos"] == 1
    assert "monto_total" not in basico.json()[0]
    dashboard = (await api.get(f"/api/reportes/dashboard{QUERY}")).json()
    assert "ingreso_neto_confirmado" not in dashboard
    assert (await api.get(f"/api/reportes/rentabilidad{QUERY}")).status_code == 403
    invertido = ruta.replace("2026-09-01&fecha_hasta", "2026-09-02&fecha_hasta")
    assert (await api.get(invertido)).status_code == 422
    assert (await api.get(ruta.replace("2026-09-01", "2026-08-01"))).json() == []
    await uow.ejecutar(
        "INSERT INTO rol_permiso (rol, permiso) VALUES ('EMPLEADO', 'reportes.financieros')"
    )
    financiero = (await api.get(ruta)).json()[0]
    assert financiero["monto_total"] == "300.00"
    assert "cantidad_pedidos" not in financiero
    rentabilidad = await api.get(f"/api/reportes/rentabilidad{QUERY}&producto_id={productos[0]}")
    assert rentabilidad.status_code == 200, rentabilidad.text
    assert rentabilidad.json()[0]["tipo"] == "RENTABILIDAD_ESTIMADA"
    await uow.ejecutar("DELETE FROM rol_permiso WHERE rol='EMPLEADO'")
    assert (await api.get(ruta)).status_code == 403
