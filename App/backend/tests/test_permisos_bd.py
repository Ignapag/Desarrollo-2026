"""Roles persistentes y revocaciones sobre cookies ya emitidas, en BD descartable."""

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI

from app.core.config import settings
from app.core.dependencias import obtener_uow
from app.core.errores import manejador_error_dominio
from app.core.seguridad import crear_token
from app.errores import DatosInvalidos, ErrorDominio, ReglaDeNegocio, SinPermiso
from app.modules.stock.presentation.router import router as stock
from app.modules.usuarios.application.servicio_acceso import ServicioAcceso
from app.modules.usuarios.domain.permisos import PERMISOS_INICIALES
from app.modules.usuarios.infrastructure.acceso_sql import RepositorioAccesoSQL
from app.modules.usuarios.presentation.router import router as usuarios
from app.modules.usuarios.presentation.router_acceso import router as acceso


@pytest.fixture
def servicio(uow):
    return ServicioAcceso(RepositorioAccesoSQL(uow))


@pytest_asyncio.fixture
async def identidades(uow):
    filas = await uow.todos(
        "SELECT id, rol, username FROM usuario WHERE username IN ('admin','taramburu')"
    )
    return {fila["rol"]: fila for fila in filas}


@pytest_asyncio.fixture
async def api(uow):
    app = FastAPI()
    for router in (usuarios, acceso, stock):
        app.include_router(router)
    app.add_exception_handler(ErrorDominio, manejador_error_dominio)
    app.dependency_overrides[obtener_uow] = lambda: uow
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://prueba"
    ) as cliente:
        yield cliente


def autenticar(api, identidad):
    api.cookies.set(settings.cookie_sesion, crear_token(
        usuario_id=identidad["id"], rol=identidad["rol"], username=identidad["username"],
    ))


async def test_migracion_conserva_permisos_iniciales_y_catalogo(servicio):
    estado = await servicio.consultar()
    for rol in estado["roles"]:
        assert set(rol["permisos"]) == PERMISOS_INICIALES[rol["rol"]]
    assert {modulo["clave"] for modulo in estado["modulos"]} >= {"pedidos", "stock", "usuarios"}


async def test_guardado_versionado_y_auditoria_sin_sobrescritura(servicio, uow, identidades):
    admin_id = identidades["ADMINISTRADOR"]["id"]
    estado = await servicio.consultar()
    actual = next(rol for rol in estado["roles"] if rol["rol"] == "EMPLEADO")
    permisos = [p for p in actual["permisos"] if p != "stock.ver"]
    actualizado = await servicio.guardar("EMPLEADO", permisos, actual["version"], admin_id)
    assert actualizado["version"] == actual["version"] + 1
    assert "stock.ver" not in actualizado["permisos"]
    with pytest.raises(ReglaDeNegocio):
        await servicio.guardar("EMPLEADO", actual["permisos"], actual["version"], admin_id)
    assert await uow.valor(
        "SELECT count(*) FROM auditoria "
        "WHERE accion='PERMISOS_MODIFICADOS' AND entidad_id='EMPLEADO'"
    ) == 1


@pytest.mark.parametrize("rol,permisos,error", [
    ("ADMINISTRADOR", [], SinPermiso), ("CLIENTE", ["stock.ver"], SinPermiso),
    ("EMPLEADO", ["inventado.borrar"], DatosInvalidos),
    ("EMPLEADO", ["usuarios.administrar_permisos"], SinPermiso),
])
async def test_no_se_delegan_privilegios_de_administracion(servicio, rol, permisos, error):
    with pytest.raises(error):
        await servicio.guardar(rol, permisos, 1, None)


async def test_misma_cookie_pierde_y_recupera_permiso(api, identidades):
    empleado = identidades["EMPLEADO"]
    autenticar(api, empleado)
    cookie = api.cookies.get(settings.cookie_sesion)
    assert (await api.get("/api/stock/ingredientes")).status_code == 200
    assert (await api.get("/api/acceso")).status_code == 403
    autenticar(api, identidades["ADMINISTRADOR"])
    estado = (await api.get("/api/acceso")).json()
    rol = next(rol for rol in estado["roles"] if rol["rol"] == "EMPLEADO")
    permisos = [p for p in rol["permisos"] if p != "stock.ver"]
    guardado = await api.put("/api/acceso/roles/EMPLEADO", json={
        "permisos": permisos, "version": rol["version"],
    })
    assert guardado.status_code == 200, guardado.text
    api.cookies.set(settings.cookie_sesion, cookie)
    assert (await api.get("/api/stock/ingredientes")).status_code == 403
    assert "stock.ver" not in (await api.get("/api/auth/me")).json()["permisos"]
    autenticar(api, identidades["ADMINISTRADOR"])
    assert (await api.put("/api/acceso/roles/EMPLEADO", json={
        "permisos": rol["permisos"], "version": guardado.json()["version"],
    })).status_code == 200
    api.cookies.set(settings.cookie_sesion, cookie)
    assert (await api.get("/api/stock/ingredientes")).status_code == 200


async def test_cambio_de_rol_y_desactivacion_invalidan_autoridad_vieja(api, identidades):
    empleado = identidades["EMPLEADO"]
    autenticar(api, empleado)
    cookie = api.cookies.get(settings.cookie_sesion)
    autenticar(api, identidades["ADMINISTRADOR"])
    assert (await api.post(f'/api/usuarios/{empleado["id"]}/rol', json={
        "rol": "CLIENTE",
    })).status_code == 200
    api.cookies.set(settings.cookie_sesion, cookie)
    assert (await api.get("/api/auth/me")).json()["rol"] == "CLIENTE"
    assert (await api.get("/api/stock/ingredientes")).status_code == 403
    autenticar(api, identidades["ADMINISTRADOR"])
    assert (await api.post(f'/api/usuarios/{empleado["id"]}/desactivar')).status_code == 200
    api.cookies.set(settings.cookie_sesion, cookie)
    assert (await api.get("/api/auth/me")).status_code == 401


async def test_admin_no_puede_quitarse_su_propio_acceso(api, identidades):
    admin = identidades["ADMINISTRADOR"]
    autenticar(api, admin)
    assert (await api.post(f'/api/usuarios/{admin["id"]}/rol', json={
        "rol": "EMPLEADO",
    })).status_code == 409
    assert (await api.post(f'/api/usuarios/{admin["id"]}/desactivar')).status_code == 409
    assert (await api.get("/api/acceso")).status_code == 200


async def test_ultimo_administrador_no_puede_perder_rol_ni_estado(uow, identidades):
    from app.modules.usuarios.application.servicio_usuarios import DatosUsuario, ServicioUsuarios
    from app.modules.usuarios.infrastructure.repositorio_sql import RepositorioUsuariosSQL

    admin = identidades["ADMINISTRADOR"]
    servicio = ServicioUsuarios(uow, RepositorioUsuariosSQL(uow))
    await uow.ejecutar(
        "UPDATE usuario SET estado='INACTIVO' WHERE rol='ADMINISTRADOR' AND id<>%s",
        (admin["id"],),
    )
    with pytest.raises(ReglaDeNegocio):
        await servicio.asignar_rol(admin["id"], "EMPLEADO", ejecutor_id=None)
    with pytest.raises(ReglaDeNegocio):
        await servicio.modificar(admin["id"], DatosUsuario(
            nombre="Admin", apellido="Prueba", username=admin["username"], estado="INACTIVO",
        ), ejecutor_id=None)


async def test_asignar_rol_crea_perfiles_operativos_y_conserva_identidad(uow, identidades):
    from app.modules.usuarios.application.servicio_usuarios import ServicioUsuarios
    from app.modules.usuarios.infrastructure.repositorio_sql import RepositorioUsuariosSQL

    servicio = ServicioUsuarios(uow, RepositorioUsuariosSQL(uow))
    empleado_id = identidades["EMPLEADO"]["id"]
    await servicio.asignar_rol(empleado_id, "REPARTIDOR", ejecutor_id=None)
    assert await uow.valor(
        "SELECT estado FROM repartidor WHERE usuario_id=%s", (empleado_id,),
    ) == "DISPONIBLE"
    await servicio.asignar_rol(empleado_id, "CLIENTE", ejecutor_id=None)
    cliente_id = await uow.valor("SELECT id FROM cliente WHERE usuario_id=%s", (empleado_id,))
    assert cliente_id is not None
    assert await uow.valor(
        "SELECT estado FROM repartidor WHERE usuario_id=%s", (empleado_id,),
    ) == "FUERA_DE_SERVICIO"
    await servicio.asignar_rol(empleado_id, "EMPLEADO", ejecutor_id=None)
    await servicio.asignar_rol(empleado_id, "CLIENTE", ejecutor_id=None)
    assert await uow.valor(
        "SELECT id FROM cliente WHERE usuario_id=%s", (empleado_id,),
    ) == cliente_id


@pytest.mark.parametrize("ruta", ["/api/acceso", "/api/auth/me"])
async def test_sin_cookie_se_rechaza_antes_de_pedir_conexion(ruta):
    app = FastAPI()
    app.include_router(acceso)
    app.include_router(usuarios)
    app.add_exception_handler(ErrorDominio, manejador_error_dominio)

    async def no_conectar():
        raise AssertionError("Un anónimo no debe pedir conexión")

    app.dependency_overrides[obtener_uow] = no_conectar
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://prueba"
    ) as cliente:
        assert (await cliente.get(ruta)).status_code == 401


async def test_admin_crea_cuenta_independiente_con_rol_y_login_propio(api, identidades):
    from uuid import uuid4

    username = "cuenta-" + uuid4().hex[:12]
    autenticar(api, identidades["EMPLEADO"])
    datos = {"nombre": "Cuenta", "apellido": "Nueva", "username": username,
             "password": "MonuCuenta2026!", "rol": "REPARTIDOR"}
    assert (await api.post("/api/usuarios", json=datos)).status_code == 403
    autenticar(api, identidades["ADMINISTRADOR"])
    creada = await api.post("/api/usuarios", json=datos)
    assert creada.status_code == 201, creada.text
    assert creada.json()["rol"] == "REPARTIDOR"
    assert "password" not in creada.json() and "password_hash" not in creada.json()
    assert (await api.post("/api/usuarios", json=datos)).status_code == 409
    login = await api.post("/api/auth/login", json={
        "username": username, "password": "MonuCuenta2026!",
    })
    assert login.status_code == 200, login.text
    assert login.json()["id"] == creada.json()["id"]
    assert login.json()["permisos"] and login.json()["rol"] == "REPARTIDOR"
    assert (await api.get("/api/acceso")).status_code == 403


async def test_password_de_alta_invalida_devuelve_error_corregible(api, identidades):
    autenticar(api, identidades["ADMINISTRADOR"])
    respuesta = await api.post("/api/usuarios", json={
        "nombre": "Cuenta", "apellido": "Prueba", "username": "usuario-prueba",
        "password": "12345678", "rol": "EMPLEADO",
    })
    assert respuesta.status_code == 422
    assert "solo numeros" in respuesta.json()["mensaje"]
