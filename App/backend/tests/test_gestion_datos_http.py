"""Las consultas ordinarias excluyen bajas y gestión las pide explícitamente."""

from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI

from app.core.config import settings
from app.core.dependencias import obtener_uow
from app.core.errores import manejador_error_dominio
from app.core.seguridad import crear_token
from app.errores import ErrorDominio
from app.modules.notificaciones.presentation.router import router as notificaciones
from app.modules.reportes.presentation.router import router as reportes
from app.modules.stock.presentation.router import router as stock
from app.modules.usuarios.presentation.router import router as usuarios


@pytest_asyncio.fixture
async def gestion(uow):
    app = FastAPI()
    app.include_router(usuarios)
    app.include_router(stock)
    app.include_router(notificaciones)
    app.include_router(reportes)
    app.add_exception_handler(ErrorDominio, manejador_error_dominio)
    app.dependency_overrides[obtener_uow] = lambda: uow
    admin = await uow.uno("SELECT id, rol, username FROM usuario WHERE username='admin'")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://prueba"
    ) as client:
        client.cookies.set(settings.cookie_sesion, crear_token(
            usuario_id=admin["id"], rol=admin["rol"], username=admin["username"]
        ))
        yield client


@pytest.mark.asyncio
@pytest.mark.parametrize("entidad", ["usuario", "ingrediente", "plantilla"])
async def test_listado_ordinario_excluye_baja_y_gestion_puede_incluirla(gestion, uow, entidad):
    nombre = f"baja_{uuid4().hex}"
    if entidad == "usuario":
        registro = await uow.valor(
            "INSERT INTO usuario(nombre,apellido,username,password_hash,rol,estado) "
            "VALUES(%s,'Prueba',%s,'no-utilizable','EMPLEADO','INACTIVO') RETURNING id",
            (nombre, nombre),
        )
        ruta = "/api/usuarios"
    elif entidad == "ingrediente":
        registro = await uow.valor(
            "INSERT INTO ingrediente(nombre,unidad_medida,umbral_minimo,activo) "
            "VALUES(%s,'UNIDAD',1,FALSE) RETURNING id", (nombre,),
        )
        ruta = "/api/stock/ingredientes"
    else:
        registro = await uow.valor("SELECT min(id) FROM notificacion_plantilla")
        await uow.ejecutar(
            "UPDATE notificacion_plantilla SET activa=FALSE WHERE id=%s", (registro,)
        )
        ruta = "/api/notificaciones/plantillas"
    ordinario = await gestion.get(ruta)
    assert ordinario.status_code == 200, ordinario.text
    assert registro not in {fila["id"] for fila in ordinario.json()}
    historico = await gestion.get(ruta, params={"incluir_inactivos": "true"})
    assert historico.status_code == 200, historico.text
    assert registro in {fila["id"] for fila in historico.json()}


@pytest.mark.asyncio
async def test_directorio_excluye_cliente_inactivo_salvo_consulta_explicita(gestion, uow):
    nombre = f"baja_{uuid4().hex}"
    cliente = await uow.valor(
        "INSERT INTO cliente(nombre,telefono_whatsapp,estado) "
        "VALUES(%s,'5492210999000','INACTIVO') RETURNING id", (nombre,),
    )
    ruta = "/api/reportes/clientes"
    ordinario = await gestion.get(ruta, params={"q": nombre})
    assert ordinario.status_code == 200, ordinario.text
    assert ordinario.json()["total"] == 0
    historico = await gestion.get(ruta, params={"q": nombre, "incluir_inactivos": "true"})
    assert historico.status_code == 200, historico.text
    assert [fila["id"] for fila in historico.json()["clientes"]] == [cliente]
