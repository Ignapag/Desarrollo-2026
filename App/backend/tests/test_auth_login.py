"""Verificacion de contrasenia del login sin base: hilo aparte y costo sin cuenta.

No miden tiempos: un `checkpw` bloqueante solo se libera desde el event loop, y
un espia confirma que bcrypt corre tambien contra el hash ficticio.
"""

from __future__ import annotations

import asyncio
import threading

import bcrypt
import pytest

from app.core import auditoria
from app.core.seguridad import hashear_password
from app.errores import NoAutenticado
from app.modules.usuarios.application.servicio_auth import (
    MENSAJE_CREDENCIALES_INVALIDAS,
    ServicioAuth,
)
from app.modules.usuarios.domain.entidades import AccionesAuditoria

HASH_GUARDADO = hashear_password("unaClaveOk1")
# Formato de seed.sql: crypt(password, gen_salt('bf')) de pgcrypto, costo 6.
HASH_SEED = bcrypt.hashpw(b"unaClaveOk1", bcrypt.gensalt(rounds=6, prefix=b"2a")).decode()


class RepositorioFalso:
    def __init__(self, fila: dict | None) -> None:
        self.fila = fila

    async def por_username(self, username: str) -> dict | None:
        return self.fila

    async def actualizar_ultimo_acceso(self, usuario_id: int) -> None:
        pass


class UowFalsa:
    async def atribuir_actor(self, usuario_id: int) -> None:
        pass


def fila_usuario(estado: str = "ACTIVO", password_hash: str = HASH_GUARDADO) -> dict:
    return {
        "id": 7, "nombre": "Ana", "apellido": "Prueba", "username": "ana",
        "password_hash": password_hash, "rol": "EMPLEADO", "estado": estado,
    }


@pytest.fixture
def eventos(monkeypatch) -> list[dict]:
    registrados: list[dict] = []

    async def registrar(uow, **datos) -> None:
        registrados.append(datos)

    monkeypatch.setattr(auditoria, "registrar", registrar)
    return registrados


@pytest.fixture
def hashes_verificados(monkeypatch) -> list[bytes]:
    """Espia sobre bcrypt.checkpw que conserva la verificacion real."""
    vistos: list[bytes] = []
    original = bcrypt.checkpw

    def espia(password: bytes, password_hash: bytes) -> bool:
        vistos.append(password_hash)
        return original(password, password_hash)

    monkeypatch.setattr(bcrypt, "checkpw", espia)
    return vistos


def servicio(fila: dict | None) -> ServicioAuth:
    return ServicioAuth(UowFalsa(), RepositorioFalso(fila))


def costo(password_hash: bytes | str) -> str:
    texto = password_hash.decode() if isinstance(password_hash, bytes) else password_hash
    return texto.split("$")[2]


async def test_usuario_inexistente_verifica_contra_hash_ficticio_y_rechaza(
    eventos, hashes_verificados
):
    with pytest.raises(NoAutenticado) as error:
        await servicio(None).iniciar_sesion(username="no_existe", password="x", ip="10.0.0.1")

    assert str(error.value) == MENSAJE_CREDENCIALES_INVALIDAS
    assert len(hashes_verificados) == 1
    ficticio = hashes_verificados[0]
    assert ficticio != HASH_GUARDADO.encode()
    assert ficticio.startswith((b"$2a$", b"$2b$"))
    assert costo(ficticio) == costo(HASH_GUARDADO)
    assert eventos == [{
        "accion": AccionesAuditoria.SESION_FALLIDA, "entidad": "usuario", "entidad_id": None,
        "datos": {"username": "no_existe"}, "ip": "10.0.0.1",
    }]


async def test_hash_ficticio_nunca_autentica_aunque_coincida(monkeypatch, eventos):
    monkeypatch.setattr(bcrypt, "checkpw", lambda password, password_hash: True)
    with pytest.raises(NoAutenticado, match=MENSAJE_CREDENCIALES_INVALIDAS):
        await servicio(None).iniciar_sesion(username="no_existe", password="x")
    assert [e["accion"] for e in eventos] == [AccionesAuditoria.SESION_FALLIDA]


async def test_usuario_existente_con_password_incorrecta_usa_su_hash(eventos, hashes_verificados):
    with pytest.raises(NoAutenticado, match=MENSAJE_CREDENCIALES_INVALIDAS):
        await servicio(fila_usuario()).iniciar_sesion(username="ana", password="otraClave1")
    assert hashes_verificados == [HASH_GUARDADO.encode()]
    assert eventos[0]["entidad_id"] == 7


async def test_hash_del_seed_mas_barato_paga_tambien_el_costo_estandar(eventos, hashes_verificados):
    """Sin esto, una cuenta del seed (costo 6) responderia mucho antes que una inexistente."""
    sesion = await servicio(fila_usuario(password_hash=HASH_SEED)).iniciar_sesion(
        username="ana", password="unaClaveOk1"
    )
    assert sesion.usuario_id == 7
    assert [costo(h) for h in hashes_verificados] == [costo(HASH_GUARDADO), "06"]
    assert hashes_verificados[1] == HASH_SEED.encode()


async def test_hash_ilegible_rechaza_pagando_el_costo_estandar(eventos, hashes_verificados):
    with pytest.raises(NoAutenticado, match=MENSAJE_CREDENCIALES_INVALIDAS):
        await servicio(fila_usuario(password_hash="no-es-bcrypt")).iniciar_sesion(
            username="ana", password="unaClaveOk1"
        )
    assert costo(hashes_verificados[0]) == costo(HASH_GUARDADO)
    assert hashes_verificados[1:] == [b"no-es-bcrypt"]
    assert eventos[0]["accion"] == AccionesAuditoria.SESION_FALLIDA


@pytest.mark.parametrize("fila", [fila_usuario(), None], ids=["existente", "inexistente"])
async def test_bcrypt_corre_fuera_del_event_loop(monkeypatch, eventos, fila):
    """Si bcrypt corriera en el loop, este nunca podria liberar el `checkpw` bloqueado."""
    entro = threading.Event()
    liberar = threading.Event()
    hilos: list[int] = []

    def checkpw_bloqueante(password: bytes, password_hash: bytes) -> bool:
        hilos.append(threading.get_ident())
        entro.set()
        assert liberar.wait(timeout=5), "el event loop quedo bloqueado durante bcrypt"
        return True

    monkeypatch.setattr(bcrypt, "checkpw", checkpw_bloqueante)
    login = asyncio.create_task(
        servicio(fila).iniciar_sesion(username="ana", password="unaClaveOk1")
    )
    # Otra "request" sigue avanzando en el loop mientras bcrypt esta en curso.
    for _ in range(500):
        if entro.is_set():
            break
        await asyncio.sleep(0.01)
    assert entro.is_set() and not login.done()
    liberar.set()

    if fila is None:
        with pytest.raises(NoAutenticado, match=MENSAJE_CREDENCIALES_INVALIDAS):
            await login
    else:
        assert (await login).usuario_id == 7
    assert hilos and hilos[0] != threading.get_ident()
