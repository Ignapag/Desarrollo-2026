"""Pruebas del modulo de Usuarios y Seguridad contra la base real.

Ejercitan servicio + repositorio directamente (sin HTTP), igual que
test_delivery_bd.py. Cada prueba corre en una transaccion que se revierte al
terminar, asi que **no ensucian la base compartida del grupo**. Si no hay
base accesible, se saltean.

    pytest tests/test_usuarios_bd.py -v
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import psycopg
import pytest
import pytest_asyncio

from app.core.config import settings
from app.core.db import UnidadDeTrabajo
from app.core.errores import NoAutenticado, NoEncontrado, ReglaDeNegocio
from app.core.seguridad import hashear_password
from app.modules.usuarios.application.servicio_auth import ServicioAuth
from app.modules.usuarios.application.servicio_usuarios import (
    DatosNuevoUsuario,
    DatosUsuario,
    ServicioUsuarios,
)
from app.modules.usuarios.infrastructure.repositorio_sql import RepositorioUsuariosSQL

CONTRASENIA_PRUEBA = "Prueba1234"


@pytest_asyncio.fixture
async def uow() -> AsyncIterator[UnidadDeTrabajo]:
    """Unidad de trabajo sobre una transaccion que siempre se revierte."""
    try:
        conn = await psycopg.AsyncConnection.connect(
            settings.database_url, row_factory=psycopg.rows.dict_row, connect_timeout=10
        )
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"Base no accesible: {exc.__class__.__name__}")

    await conn.set_autocommit(False)
    try:
        yield UnidadDeTrabajo(conn)
    finally:
        await conn.rollback()
        await conn.close()


@pytest_asyncio.fixture
async def servicio_usuarios(uow: UnidadDeTrabajo) -> ServicioUsuarios:
    return ServicioUsuarios(uow, RepositorioUsuariosSQL(uow))


@pytest_asyncio.fixture
async def servicio_auth(uow: UnidadDeTrabajo) -> ServicioAuth:
    return ServicioAuth(uow, RepositorioUsuariosSQL(uow))


def username_de_prueba() -> str:
    # Un sufijo unico por corrida evita choques si dos pruebas insertan en
    # la misma transaccion (comparten conexion dentro de una prueba).
    return f"usr_{uuid.uuid4().hex[:10]}"


async def crear_usuario_activo(
    uow: UnidadDeTrabajo, *, rol: str = "EMPLEADO", estado: str = "ACTIVO"
) -> tuple[int, str]:
    username = username_de_prueba()
    fila = await uow.uno(
        """
        INSERT INTO usuario (nombre, apellido, username, password_hash, rol, estado)
        VALUES ('Prueba', 'DeAcceso', %s, %s, %s, %s) RETURNING id
        """,
        (username, hashear_password(CONTRASENIA_PRUEBA), rol, estado),
    )
    return fila["id"], username  # type: ignore[index]


# --------------------------------------------------------------- CU_USR_01


@pytest.mark.asyncio
async def test_login_con_credenciales_correctas(uow, servicio_auth):
    _id, username = await crear_usuario_activo(uow)

    sesion = await servicio_auth.iniciar_sesion(username=username, password=CONTRASENIA_PRUEBA)

    assert sesion.username == username
    assert sesion.token


@pytest.mark.asyncio
async def test_login_con_password_incorrecta_rechaza(uow, servicio_auth):
    _id, username = await crear_usuario_activo(uow)

    with pytest.raises(NoAutenticado):
        await servicio_auth.iniciar_sesion(username=username, password="incorrecta")


@pytest.mark.asyncio
async def test_login_con_usuario_inexistente_rechaza(uow, servicio_auth):
    with pytest.raises(NoAutenticado):
        await servicio_auth.iniciar_sesion(username="no_existe_" + uuid.uuid4().hex, password="x")


@pytest.mark.asyncio
async def test_login_de_cuenta_inactiva_rechaza(uow, servicio_auth):
    _id, username = await crear_usuario_activo(uow, estado="INACTIVO")

    with pytest.raises(NoAutenticado):
        await servicio_auth.iniciar_sesion(username=username, password=CONTRASENIA_PRUEBA)


# --------------------------------------------------------------- CU_USR_03


@pytest.mark.asyncio
async def test_registrar_usuario_crea_la_cuenta(uow, servicio_usuarios):
    username = username_de_prueba()
    creado = await servicio_usuarios.registrar(
        DatosNuevoUsuario(
            nombre="Nueva",
            apellido="Cuenta",
            username=username,
            password=CONTRASENIA_PRUEBA,
            rol="EMPLEADO",
        ),
        ejecutor_id=None,
    )
    assert creado["username"] == username
    assert creado["rol"] == "EMPLEADO"
    assert creado["estado"] == "ACTIVO"


@pytest.mark.asyncio
async def test_registrar_usuario_con_username_repetido_falla(uow, servicio_usuarios):
    _id, username = await crear_usuario_activo(uow)

    with pytest.raises(ReglaDeNegocio):
        await servicio_usuarios.registrar(
            DatosNuevoUsuario(
                nombre="Otra",
                apellido="Persona",
                username=username,
                password=CONTRASENIA_PRUEBA,
                rol="EMPLEADO",
            ),
            ejecutor_id=None,
        )


# --------------------------------------------------------------- CU_USR_04


@pytest.mark.asyncio
async def test_desactivar_usuario_cambia_el_estado(uow, servicio_usuarios):
    usuario_id, _username = await crear_usuario_activo(uow)

    resultado = await servicio_usuarios.desactivar(usuario_id, ejecutor_id=None)

    assert resultado["estado"] == "INACTIVO"


@pytest.mark.asyncio
async def test_desactivar_dos_veces_falla(uow, servicio_usuarios):
    usuario_id, _username = await crear_usuario_activo(uow)
    await servicio_usuarios.desactivar(usuario_id, ejecutor_id=None)

    with pytest.raises(ReglaDeNegocio):
        await servicio_usuarios.desactivar(usuario_id, ejecutor_id=None)


@pytest.mark.asyncio
async def test_desactivar_repartidor_con_viaje_abierto_falla(uow, servicio_usuarios):
    usuario_id, _username = await crear_usuario_activo(uow, rol="REPARTIDOR")
    await uow.ejecutar(
        "INSERT INTO repartidor (usuario_id, estado) VALUES (%s, 'EN_RUTA')", (usuario_id,)
    )
    await uow.ejecutar(
        "INSERT INTO viaje (repartidor_id, estado) VALUES (%s, 'EN_RUTA')", (usuario_id,)
    )

    with pytest.raises(ReglaDeNegocio):
        await servicio_usuarios.desactivar(usuario_id, ejecutor_id=None)


# --------------------------------------------------------------- CU_USR_05


@pytest.mark.asyncio
async def test_modificar_usuario_actualiza_los_campos(uow, servicio_usuarios):
    usuario_id, _username = await crear_usuario_activo(uow)
    nuevo_username = username_de_prueba()

    resultado = await servicio_usuarios.modificar(
        usuario_id,
        DatosUsuario(
            nombre="Cambiado", apellido="Apellido", username=nuevo_username, estado="ACTIVO"
        ),
        ejecutor_id=None,
    )

    assert resultado["nombre"] == "Cambiado"
    assert resultado["username"] == nuevo_username


@pytest.mark.asyncio
async def test_modificar_a_un_username_ya_usado_falla(uow, servicio_usuarios):
    _id1, username1 = await crear_usuario_activo(uow)
    id2, _username2 = await crear_usuario_activo(uow)

    with pytest.raises(ReglaDeNegocio):
        await servicio_usuarios.modificar(
            id2,
            DatosUsuario(nombre="X", apellido="Y", username=username1, estado="ACTIVO"),
            ejecutor_id=None,
        )


@pytest.mark.asyncio
async def test_modificar_usuario_inexistente_falla(uow, servicio_usuarios):
    with pytest.raises(NoEncontrado):
        await servicio_usuarios.modificar(
            -1,
            DatosUsuario(nombre="X", apellido="Y", username="no_existe", estado="ACTIVO"),
            ejecutor_id=None,
        )


# --------------------------------------------------------------- CU_USR_06


@pytest.mark.asyncio
async def test_asignar_rol_lo_cambia(uow, servicio_usuarios):
    usuario_id, _username = await crear_usuario_activo(uow, rol="EMPLEADO")

    resultado = await servicio_usuarios.asignar_rol(usuario_id, "DUENIO", ejecutor_id=None)

    assert resultado["rol"] == "DUENIO"


@pytest.mark.asyncio
async def test_asignar_rol_invalido_falla(uow, servicio_usuarios):
    usuario_id, _username = await crear_usuario_activo(uow)

    with pytest.raises(ReglaDeNegocio):
        await servicio_usuarios.asignar_rol(usuario_id, "SUPERADMIN", ejecutor_id=None)


# --------------------------------------------------------------- CU_USR_02


@pytest.mark.asyncio
async def test_buscar_usuarios_filtra_por_username(uow, servicio_usuarios):
    from app.modules.usuarios.application.servicio_usuarios import FiltrosUsuario

    _id, username = await crear_usuario_activo(uow)

    resultados = await servicio_usuarios.buscar(FiltrosUsuario(username=username))

    assert len(resultados) == 1
    assert resultados[0]["username"] == username


# --------------------------------------------------------------- auditoria


@pytest.mark.asyncio
async def test_login_exitoso_deja_rastro_en_auditoria(uow, servicio_auth):
    _id, username = await crear_usuario_activo(uow)
    await servicio_auth.iniciar_sesion(username=username, password=CONTRASENIA_PRUEBA)

    from app.core import auditoria

    eventos = await auditoria.listar(uow, accion="SESION_INICIADA", limite=50)
    assert any(e["username"] == username for e in eventos)


@pytest.mark.asyncio
async def test_registrar_usuario_deja_rastro_en_auditoria(uow, servicio_usuarios):
    username = username_de_prueba()
    creado = await servicio_usuarios.registrar(
        DatosNuevoUsuario(
            nombre="Auditada",
            apellido="Cuenta",
            username=username,
            password=CONTRASENIA_PRUEBA,
            rol="EMPLEADO",
        ),
        ejecutor_id=None,
    )

    from app.core import auditoria

    eventos = await auditoria.listar(
        uow, accion="USUARIO_REGISTRADO", entidad="usuario", limite=50
    )
    assert any(e["entidad_id"] == str(creado["id"]) for e in eventos)
