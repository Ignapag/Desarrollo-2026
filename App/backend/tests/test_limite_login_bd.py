"""Limitación de intentos de login contra PostgreSQL descartable: SQL y HTTP.

Las reservas se confirman en su propia transacción (deben sobrevivir al 401),
así que estas pruebas confirman datos y limpian al terminar: `intento_login`,
la auditoría que agregaron y `usuario.ultimo_acceso`. Usan umbrales chicos
para no pagar decenas de verificaciones bcrypt.

    pytest tests/test_limite_login_bd.py -v
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from uuid import uuid4

import bcrypt
import httpx
import psycopg
import pytest
import pytest_asyncio
from psycopg.rows import dict_row

from app.core.config import settings
from app.core.db import UnidadDeTrabajo, abrir_pool, cerrar_pool, conexion, verificar_conexion
from app.main import app
from app.modules.usuarios.domain.entidades import AccionesAuditoria
from app.modules.usuarios.domain.limite_login import MENSAJE_DEMASIADOS_INTENTOS
from app.modules.usuarios.infrastructure.intentos_login_sql import RepositorioIntentosLoginSQL
from tests.soporte_bd import exigir_base_descartable, mantenimiento_pruebas

CONTRASENIA_SEED = "Monu2026!"
EMPLEADO = "taramburu"
SECRETO = "secreto-de-prueba"
MAX_USUARIO = 3
MAX_IP = 5


# ------------------------------------------------------------------ SQL


async def _conectar() -> psycopg.AsyncConnection:
    return await psycopg.AsyncConnection.connect(
        settings.database_url, row_factory=dict_row, connect_timeout=10
    )


async def test_reserva_hasta_el_maximo_y_normaliza_el_username(uow):
    repo = RepositorioIntentosLoginSQL(uow)
    username = f"Prueba_{uuid4().hex[:8]}"

    resultados = [await repo.reservar_usuario(username, 3, 900) for _ in range(3)]
    resultados.append(await repo.reservar_usuario(username.upper(), 3, 900))

    assert resultados == [True, True, True, False]
    fila = await uow.uno(
        "SELECT fallos FROM intento_login WHERE clave = %s", (f"usuario:{username.lower()}",)
    )
    assert fila["fallos"] == 3


async def test_ventana_vencida_reinicia_el_contador_y_la_purga_la_elimina(uow):
    repo = RepositorioIntentosLoginSQL(uow)
    vieja, activa = f"vieja_{uuid4().hex[:8]}", f"activa_{uuid4().hex[:8]}"
    for username in (vieja, activa):
        for _ in range(3):
            await repo.reservar_usuario(username, 3, 900)
    await uow.ejecutar(
        "UPDATE intento_login SET vence_en = now() - interval '1 second' WHERE clave = %s",
        (f"usuario:{vieja}",),
    )

    assert await repo.reservar_usuario(vieja, 3, 900) is True
    fila = await uow.uno("SELECT fallos, vence_en > now() AS vigente FROM intento_login "
                         "WHERE clave = %s", (f"usuario:{vieja}",))
    assert fila == {"fallos": 1, "vigente": True}

    await uow.ejecutar(
        "UPDATE intento_login SET vence_en = now() - interval '1 second' WHERE clave = %s",
        (f"usuario:{activa}",),
    )
    await repo.purgar_vencidos()
    assert await uow.valor(
        "SELECT count(*) FROM intento_login WHERE clave = %s", (f"usuario:{activa}",)
    ) == 0


async def test_exito_borra_username_y_devuelve_cupo_sin_bajar_de_cero(uow):
    repo = RepositorioIntentosLoginSQL(uow)
    username, origen = f"exito_{uuid4().hex[:8]}", "198.51.100.20"
    await repo.reservar_usuario(username, 3, 900)
    await repo.reservar_origen(origen, 3, 900)

    await repo.reiniciar_usuario(username.upper())
    await repo.devolver_origen(origen)
    await repo.devolver_origen(origen)

    assert await uow.valor(
        "SELECT count(*) FROM intento_login WHERE clave = %s", (f"usuario:{username}",)
    ) == 0
    assert await uow.valor(
        "SELECT fallos FROM intento_login WHERE clave = %s", (f"ip:{origen}",)
    ) == 0


async def test_reservas_concurrentes_no_superan_el_umbral():
    """Cada reserva usa su propia conexión y transacción, como en la API."""
    exigir_base_descartable()
    username = f"concurrente_{uuid4().hex[:8]}"
    try:
        conexiones = [await _conectar() for _ in range(25)]
    except psycopg.OperationalError as exc:
        pytest.skip(f"Base no accesible: {exc.__class__.__name__}")
    inicio = asyncio.Event()

    async def reservar(conn: psycopg.AsyncConnection) -> bool:
        await inicio.wait()
        aceptada = await RepositorioIntentosLoginSQL(UnidadDeTrabajo(conn)).reservar_usuario(
            username, 10, 900
        )
        await conn.commit()
        return aceptada

    try:
        tareas = [asyncio.create_task(reservar(conn)) for conn in conexiones]
        inicio.set()
        resultados = await asyncio.gather(*tareas)
        assert sum(resultados) == 10
        fila = await conexiones[0].execute(
            "SELECT fallos FROM intento_login WHERE clave = %s", (f"usuario:{username}",)
        )
        assert (await fila.fetchone())["fallos"] == 10
    finally:
        await conexiones[0].execute(
            "DELETE FROM intento_login WHERE clave = %s", (f"usuario:{username}",)
        )
        await conexiones[0].commit()
        for conn in conexiones:
            await conn.close()


# ------------------------------------------------------------------ HTTP


@pytest_asyncio.fixture
async def api(monkeypatch) -> AsyncIterator[httpx.AsyncClient]:
    """API real con umbrales chicos y limpieza de lo que confirman los logins."""
    exigir_base_descartable()
    monkeypatch.setattr(settings, "login_max_fallos_usuario", MAX_USUARIO)
    monkeypatch.setattr(settings, "login_max_fallos_ip", MAX_IP)
    monkeypatch.setattr(settings, "proxy_ip_secreto", "")
    await abrir_pool()
    try:
        await verificar_conexion()
    except Exception as exc:  # pragma: no cover
        await cerrar_pool()
        pytest.skip(f"Base no accesible: {exc.__class__.__name__}")
    async with conexion() as conn:
        uow = UnidadDeTrabajo(conn)
        ultimo_id_auditoria = await uow.valor("SELECT COALESCE(max(id), 0) FROM auditoria")
        accesos = await uow.todos("SELECT id, ultimo_acceso FROM usuario")
        await uow.ejecutar("DELETE FROM intento_login")
    transporte = httpx.ASGITransport(app=app)
    try:
        async with httpx.AsyncClient(transport=transporte, base_url="http://test") as client:
            yield client
    finally:
        async with conexion() as conn:
            uow = UnidadDeTrabajo(conn)
            await uow.ejecutar("DELETE FROM intento_login")
            for fila in accesos:
                await uow.ejecutar(
                    "UPDATE usuario SET ultimo_acceso = %s WHERE id = %s",
                    (fila["ultimo_acceso"], fila["id"]),
                )
            async with mantenimiento_pruebas(uow):
                await uow.ejecutar("DELETE FROM auditoria WHERE id > %s", (ultimo_id_auditoria,))
        await cerrar_pool()


@pytest.fixture
def verificaciones_bcrypt(monkeypatch) -> list[bytes]:
    """Espía sobre bcrypt.checkpw que conserva la verificación real."""
    vistas: list[bytes] = []
    original = bcrypt.checkpw

    def espia(password: bytes, password_hash: bytes) -> bool:
        vistas.append(password_hash)
        return original(password, password_hash)

    monkeypatch.setattr(bcrypt, "checkpw", espia)
    return vistas


async def login(api, username: str, password: str = "incorrecta", headers=None):
    return await api.post(
        "/api/auth/login", json={"username": username, "password": password}, headers=headers
    )


def proxy(ip: str, secreto: str = SECRETO) -> dict[str, str]:
    return {"X-Monu-IP-Cliente": ip, "X-Monu-Proxy-Secreto": secreto}


async def test_bloqueo_responde_429_con_password_correcta_y_sin_bcrypt(api, verificaciones_bcrypt):
    for _ in range(MAX_USUARIO):
        assert (await login(api, EMPLEADO)).status_code == 401
    verificaciones_bcrypt.clear()

    resp = await login(api, EMPLEADO.upper(), CONTRASENIA_SEED)

    assert resp.status_code == 429
    assert resp.json() == {
        "codigo": "demasiados_intentos", "mensaje": MENSAJE_DEMASIADOS_INTENTOS, "detalles": {},
    }
    assert verificaciones_bcrypt == []
    assert "monu_session" not in api.cookies


async def test_usuario_inexistente_recibe_la_misma_respuesta(api):
    username = f"no_existe_{uuid4().hex[:8]}"
    for _ in range(MAX_USUARIO):
        assert (await login(api, username)).status_code == 401

    resp = await login(api, username)

    assert resp.status_code == 429
    assert resp.json()["mensaje"] == MENSAJE_DEMASIADOS_INTENTOS


async def test_ventana_vencida_vuelve_a_permitir_el_login(api):
    for _ in range(MAX_USUARIO):
        await login(api, EMPLEADO)
    async with conexion() as conn:
        await UnidadDeTrabajo(conn).ejecutar(
            "UPDATE intento_login SET vence_en = now() - interval '1 second'"
        )

    assert (await login(api, EMPLEADO, CONTRASENIA_SEED)).status_code == 200


async def test_login_exitoso_reinicia_el_contador_del_username(api):
    for _ in range(MAX_USUARIO - 1):
        await login(api, EMPLEADO)
    assert (await login(api, EMPLEADO, CONTRASENIA_SEED)).status_code == 200

    for _ in range(MAX_USUARIO):
        assert (await login(api, EMPLEADO)).status_code == 401
    assert (await login(api, EMPLEADO)).status_code == 429


async def test_login_fallido_queda_auditado_aunque_responda_401(api):
    await login(api, EMPLEADO)

    async with conexion() as conn:
        eventos = await UnidadDeTrabajo(conn).todos(
            "SELECT datos FROM auditoria WHERE accion = %s ORDER BY id DESC LIMIT 1",
            (AccionesAuditoria.SESION_FALLIDA,),
        )
    assert eventos and eventos[0]["datos"] == {"username": EMPLEADO}


async def test_limite_por_ip_con_proxy_autenticado(api, monkeypatch):
    monkeypatch.setattr(settings, "proxy_ip_secreto", SECRETO)
    ip = "198.51.100.30"
    for numero in range(MAX_IP):
        assert (await login(api, f"spray{numero}_{uuid4().hex[:6]}",
                            headers=proxy(ip))).status_code == 401

    # Otro username y un X-Forwarded-For falso no dan cupo nuevo a la misma IP.
    bloqueada = await login(api, EMPLEADO, CONTRASENIA_SEED,
                            headers={**proxy(ip), "X-Forwarded-For": "203.0.113.50"})
    assert bloqueada.status_code == 429
    assert (await login(api, EMPLEADO, CONTRASENIA_SEED,
                        headers=proxy("198.51.100.31"))).status_code == 200


async def test_cabeceras_falsificadas_comparten_el_origen_sin_proxy(api, monkeypatch):
    monkeypatch.setattr(settings, "proxy_ip_secreto", SECRETO)
    for numero in range(MAX_IP):
        falsas = {**proxy(f"203.0.113.{numero}", secreto="adivinado"),
                  "X-Forwarded-For": f"192.0.2.{numero}"}
        assert (await login(api, f"falso{numero}_{uuid4().hex[:6]}",
                            headers=falsas)).status_code == 401

    resp = await login(api, EMPLEADO, CONTRASENIA_SEED,
                       headers={"X-Monu-IP-Cliente": "203.0.113.99"})
    assert resp.status_code == 429


async def test_ip_bloqueada_no_consume_cupo_del_username(api, monkeypatch):
    monkeypatch.setattr(settings, "proxy_ip_secreto", SECRETO)
    ip = "198.51.100.40"
    for numero in range(MAX_IP):
        await login(api, f"cupo{numero}_{uuid4().hex[:6]}", headers=proxy(ip))

    for _ in range(MAX_USUARIO + 1):
        assert (await login(api, EMPLEADO, headers=proxy(ip))).status_code == 429
    assert (await login(api, EMPLEADO, CONTRASENIA_SEED,
                        headers=proxy("198.51.100.41"))).status_code == 200


async def test_intentos_simultaneos_no_superan_el_umbral(api, verificaciones_bcrypt):
    respuestas = await asyncio.gather(*(login(api, EMPLEADO) for _ in range(20)))

    estados = sorted(r.status_code for r in respuestas)
    assert estados == [401] * MAX_USUARIO + [429] * (20 - MAX_USUARIO)
    assert len(verificaciones_bcrypt) <= MAX_USUARIO * 2  # cuenta real + hash ficticio
    async with conexion() as conn:
        fallos = await UnidadDeTrabajo(conn).valor(
            "SELECT fallos FROM intento_login WHERE clave = %s", (f"usuario:{EMPLEADO}",)
        )
    assert fallos == MAX_USUARIO
