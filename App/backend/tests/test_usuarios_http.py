"""Pruebas de control de acceso contra la API real, via ASGI.

Complementan test_control_acceso.py (que prueba la guarda en aislamiento):
aca se golpea la aplicacion real -login incluido- para confirmar que cada
endpoint tiene declarado el alias correcto, no solo que el alias en si
funcione.

Usan los usuarios de App/db/seed.sql (contrasenia Monu2026! para todos) y
solo pegan a endpoints de lectura: no dejan escritos nuevos en la base.
Si no hay base accesible, se saltean -igual que el resto de las pruebas
contra la base real.

    pytest tests/test_usuarios_http.py -v
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest
import pytest_asyncio

from app.core.db import abrir_pool, cerrar_pool, verificar_conexion
from app.main import app

CONTRASENIA_SEED = "Monu2026!"

ADMIN = "admin"  # ADMINISTRADOR
EMPLEADO = "taramburu"  # EMPLEADO
DUENIO = "ipagotto"  # DUENIO
CLIENTE = "acliente"  # CLIENTE


@pytest_asyncio.fixture
async def _pool_de_pruebas() -> AsyncIterator[None]:
    """Abre el pool para la prueba: los endpoints lo necesitan y ASGITransport
    no dispara el lifespan de FastAPI por si solo.

    Se abre y cierra por prueba (no una vez por archivo) para no mezclar
    scopes con el event_loop de pytest-asyncio, que en este proyecto es
    function-scoped (ver pyproject.toml). El costo de reabrirlo es bajo:
    son pocas pruebas y el pool no hace trabajo pesado al abrir.
    """
    await abrir_pool()
    try:
        await verificar_conexion()
    except Exception as exc:  # pragma: no cover
        await cerrar_pool()
        pytest.skip(f"Base no accesible: {exc.__class__.__name__}")
    yield
    await cerrar_pool()


@pytest_asyncio.fixture
async def api(_pool_de_pruebas: None) -> AsyncIterator[httpx.AsyncClient]:
    """Cliente nuevo (cookie jar limpio) por prueba, sobre el mismo pool."""
    transporte = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transporte, base_url="http://test") as client:
        yield client


async def iniciar_sesion(api: httpx.AsyncClient, username: str) -> httpx.Response:
    return await api.post(
        "/api/auth/login", json={"username": username, "password": CONTRASENIA_SEED}
    )


# --------------------------------------------------------------- CU_USR_01


@pytest.mark.asyncio
async def test_login_con_password_incorrecta_devuelve_401(api: httpx.AsyncClient):
    resp = await api.post("/api/auth/login", json={"username": ADMIN, "password": "incorrecta"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_login_exitoso_devuelve_200_y_cookie_de_sesion(api: httpx.AsyncClient):
    resp = await iniciar_sesion(api, ADMIN)
    assert resp.status_code == 200
    assert resp.json()["rol"] == "ADMINISTRADOR"
    assert any(c == "monu_session" for c in api.cookies)


@pytest.mark.asyncio
async def test_me_sin_sesion_devuelve_401(api: httpx.AsyncClient):
    resp = await api.get("/api/auth/me")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_me_con_sesion_devuelve_el_usuario(api: httpx.AsyncClient):
    await iniciar_sesion(api, EMPLEADO)
    resp = await api.get("/api/auth/me")
    assert resp.status_code == 200
    assert resp.json()["username"] == EMPLEADO


# ------------------------------------------------------- /api/usuarios (SoloAdministrador)


@pytest.mark.asyncio
async def test_buscar_usuarios_sin_sesion_devuelve_401(api: httpx.AsyncClient):
    resp = await api.get("/api/usuarios")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_buscar_usuarios_con_empleado_devuelve_403(api: httpx.AsyncClient):
    await iniciar_sesion(api, EMPLEADO)
    resp = await api.get("/api/usuarios")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_buscar_usuarios_con_duenio_devuelve_403(api: httpx.AsyncClient):
    """CU_USR_02: el actor es Administrador. Dueno/Supervisor no gestiona cuentas."""
    await iniciar_sesion(api, DUENIO)
    resp = await api.get("/api/usuarios")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_buscar_usuarios_con_administrador_devuelve_200(api: httpx.AsyncClient):
    await iniciar_sesion(api, ADMIN)
    resp = await api.get("/api/usuarios")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
    assert any(u["username"] == ADMIN for u in resp.json())


# ------------------------------------------------------- /api/auditoria (AdministradorODuenio)


@pytest.mark.asyncio
async def test_auditoria_con_cliente_devuelve_403(api: httpx.AsyncClient):
    await iniciar_sesion(api, CLIENTE)
    resp = await api.get("/api/auditoria")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_auditoria_con_duenio_devuelve_200(api: httpx.AsyncClient):
    await iniciar_sesion(api, DUENIO)
    resp = await api.get("/api/auditoria")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_auditoria_con_administrador_devuelve_200(api: httpx.AsyncClient):
    await iniciar_sesion(api, ADMIN)
    resp = await api.get("/api/auditoria")
    assert resp.status_code == 200


# ------------------------------------------------------- /api/notificaciones


@pytest.mark.asyncio
async def test_listar_notificaciones_con_cliente_devuelve_403(api: httpx.AsyncClient):
    """PersonalInterno: el Cliente no opera el panel interno."""
    await iniciar_sesion(api, CLIENTE)
    resp = await api.get("/api/notificaciones")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_listar_notificaciones_con_empleado_devuelve_200(api: httpx.AsyncClient):
    await iniciar_sesion(api, EMPLEADO)
    resp = await api.get("/api/notificaciones")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_plantillas_de_notificacion_con_empleado_devuelve_403(api: httpx.AsyncClient):
    """AdministradorODuenio: el Empleado no gestiona plantillas (CU_BOT_04)."""
    await iniciar_sesion(api, EMPLEADO)
    resp = await api.get("/api/notificaciones/plantillas")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_plantillas_de_notificacion_con_duenio_devuelve_200(api: httpx.AsyncClient):
    await iniciar_sesion(api, DUENIO)
    resp = await api.get("/api/notificaciones/plantillas")
    assert resp.status_code == 200


# --------------------------------------------------------------- logout


@pytest.mark.asyncio
async def test_logout_borra_la_sesion(api: httpx.AsyncClient):
    await iniciar_sesion(api, ADMIN)
    assert (await api.get("/api/usuarios")).status_code == 200

    await api.post("/api/auth/logout")

    assert (await api.get("/api/usuarios")).status_code == 401
