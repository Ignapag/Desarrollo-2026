"""Limitación de intentos de login sin base: política, servicio e IP confiable.

Las pruebas con PostgreSQL (atomicidad, concurrencia y HTTP) están en
``test_limite_login_bd.py``.
"""

from __future__ import annotations

import pytest
from starlette.requests import Request

from app.core import dependencias
from app.core.config import settings
from app.errores import DemasiadosIntentos
from app.modules.usuarios.application.servicio_limite_login import ServicioLimiteLogin
from app.modules.usuarios.domain.limite_login import (
    MENSAJE_DEMASIADOS_INTENTOS,
    IntentoReservado,
    PoliticaIntentosLogin,
)

POLITICA = PoliticaIntentosLogin(max_fallos_usuario=2, max_fallos_origen=3, ventana_segundos=60)


class RegistroFalso:
    """Contadores en memoria con la misma semántica que el repositorio SQL."""

    def __init__(self) -> None:
        self.contadores: dict[str, int] = {}
        self.purgas = 0

    def _reservar(self, clave: str, maximo: int) -> bool:
        if self.contadores.get(clave, 0) >= maximo:
            return False
        self.contadores[clave] = self.contadores.get(clave, 0) + 1
        return True

    async def reservar_usuario(self, username: str, maximo: int, ventana_segundos: int) -> bool:
        return self._reservar(f"usuario:{username.lower()}", maximo)

    async def reservar_origen(self, origen: str, maximo: int, ventana_segundos: int) -> bool:
        return self._reservar(f"ip:{origen}", maximo)

    async def purgar_vencidos(self) -> None:
        self.purgas += 1

    async def reiniciar_usuario(self, username: str) -> None:
        self.contadores.pop(f"usuario:{username.lower()}", None)

    async def devolver_origen(self, origen: str) -> None:
        clave = f"ip:{origen}"
        if self.contadores.get(clave, 0) > 0:
            self.contadores[clave] -= 1


@pytest.fixture
def registro() -> RegistroFalso:
    return RegistroFalso()


@pytest.fixture
def limite(registro: RegistroFalso) -> ServicioLimiteLogin:
    return ServicioLimiteLogin(registro, POLITICA)


# ------------------------------------------------------------------ política


@pytest.mark.parametrize(
    "usuario,origen,ventana", [(0, 5, 60), (5, 0, 60), (5, 5, 0)],
)
def test_politica_rechaza_valores_que_desactivan_el_limite(usuario, origen, ventana):
    with pytest.raises(ValueError):
        PoliticaIntentosLogin(usuario, origen, ventana)


# ------------------------------------------------------------------ servicio


async def test_bloquea_el_username_al_alcanzar_el_umbral(limite, registro):
    for _ in range(POLITICA.max_fallos_usuario):
        await limite.reservar("ana", None)

    with pytest.raises(DemasiadosIntentos) as error:
        await limite.reservar("ANA", None)

    assert error.value.codigo_http == 429
    assert error.value.mensaje == MENSAJE_DEMASIADOS_INTENTOS
    assert error.value.detalles == {}


async def test_bloquea_el_origen_aunque_cambie_el_username(limite):
    for numero in range(POLITICA.max_fallos_origen):
        await limite.reservar(f"usuario{numero}", "198.51.100.7")

    with pytest.raises(DemasiadosIntentos) as error:
        await limite.reservar("otro", "198.51.100.7")
    assert error.value.mensaje == MENSAJE_DEMASIADOS_INTENTOS


async def test_sin_origen_confiable_solo_limita_el_username(limite, registro):
    intento = await limite.reservar("ana", None)

    assert intento == IntentoReservado(username="ana", origen=None)
    assert not any(clave.startswith("ip:") for clave in registro.contadores)
    assert registro.purgas == 1


async def test_exito_reinicia_username_y_devuelve_cupo_del_origen(limite, registro):
    await limite.reservar("ana", "198.51.100.7")
    intento = await limite.reservar("ana", "198.51.100.7")

    await limite.confirmar_exito(intento)

    assert "usuario:ana" not in registro.contadores
    assert registro.contadores["ip:198.51.100.7"] == 1


# ------------------------------------------------------------------ IP confiable


def request(headers: dict[str, str], cliente: str = "10.0.0.5") -> Request:
    return Request({
        "type": "http",
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
        "client": (cliente, 1234),
    })


def proxy(ip: str, secreto: str = "secreto-de-prueba") -> dict[str, str]:
    return {"X-Monu-IP-Cliente": ip, "X-Monu-Proxy-Secreto": secreto}


@pytest.fixture
def con_secreto(monkeypatch):
    monkeypatch.setattr(settings, "proxy_ip_secreto", "secreto-de-prueba")


@pytest.fixture
def sin_secreto(monkeypatch):
    monkeypatch.setattr(settings, "proxy_ip_secreto", "")


def test_sin_secreto_no_hay_origen_para_limite_aunque_vengan_cabeceras(sin_secreto):
    falsas = {**proxy("198.51.100.7"), "X-Forwarded-For": "198.51.100.8"}

    assert dependencias.origen_para_limite(request(falsas)) is None
    assert dependencias.ip_de_proxy_confiable(request(falsas)) is None


def test_proxy_autenticado_define_el_origen_y_la_ip_de_auditoria(con_secreto):
    pedido = request({**proxy("198.51.100.7"), "X-Forwarded-For": "203.0.113.9"})

    assert dependencias.origen_para_limite(pedido) == "198.51.100.7"
    assert dependencias.ip_cliente(pedido) == "198.51.100.7"


def test_ipv6_cuenta_por_red_64_y_audita_la_direccion_exacta(con_secreto):
    pedidos = [request(proxy(ip)) for ip in ("2001:DB8:0:0:abcd::1", "2001:db8::ffff:2")]

    assert {dependencias.origen_para_limite(p) for p in pedidos} == {"2001:db8::/64"}
    assert dependencias.ip_cliente(pedidos[0]) == "2001:db8::abcd:0:0:1"
    assert dependencias.origen_para_limite(request(proxy("2001:db8:0:1::1"))) == "2001:db8:0:1::/64"


def test_ip_con_zona_ipv6_se_descarta(con_secreto):
    # Como cualquier X-Forwarded-For inválido: sin IP, en lugar de un 500 al guardar inet.
    assert dependencias.ip_cliente(request({"X-Forwarded-For": "fe80::1%eth0"})) is None
    assert dependencias.origen_para_limite(request(proxy("fe80::1%eth0"))) == (
        dependencias.ORIGEN_SIN_PROXY
    )


@pytest.mark.parametrize("headers", [
    {"X-Forwarded-For": "198.51.100.8"},
    proxy("198.51.100.7", secreto="otro-secreto"),
    proxy("no-es-ip"),
    {"X-Monu-IP-Cliente": "198.51.100.7"},
])
def test_peticiones_sin_proxy_autenticado_comparten_un_origen(con_secreto, headers):
    assert dependencias.origen_para_limite(request(headers)) == dependencias.ORIGEN_SIN_PROXY


def test_auditoria_conserva_x_forwarded_for_informativo_sin_proxy(con_secreto):
    pedido = request({"X-Forwarded-For": " 192.0.2.41 , 10.0.0.1"})

    assert dependencias.ip_cliente(pedido) == "192.0.2.41"
    assert dependencias.ip_cliente(request({"X-Forwarded-For": "basura"})) is None
    assert dependencias.ip_cliente(request({})) == "10.0.0.5"
