"""Entidades y reglas del modulo de Usuarios y Seguridad (EDT 1.8).

Logica pura: no toca la base ni FastAPI, y por eso se puede probar sin
infraestructura. Cubre las tareas del cronograma:
  - Rol, ClaimsSesion   : quien es el usuario autenticado y que puede hacer
  - validar_password()  : politica de contrasenia (CU_USR_03)
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Rol(StrEnum):
    """Coincide con el CHECK usuario_rol_chk de la migracion 001."""

    ADMINISTRADOR = "ADMINISTRADOR"
    DUENIO = "DUENIO"
    EMPLEADO = "EMPLEADO"
    REPARTIDOR = "REPARTIDOR"
    CLIENTE = "CLIENTE"


#: Roles que operan el panel interno: todos menos el Cliente. Es el guard
#: `PersonalInterno` que el resto de los modulos (Delivery, Pedidos, etc.)
#: esperan encontrar en app.core.dependencias.
ROLES_PERSONAL_INTERNO = frozenset(
    {Rol.ADMINISTRADOR, Rol.DUENIO, Rol.EMPLEADO, Rol.REPARTIDOR}
)

LONGITUD_MINIMA_PASSWORD = 8


class PasswordInvalida(ValueError):
    """La contrasenia no cumple la politica minima (CU_USR_03)."""


def validar_password(password: str, *, username: str | None = None) -> None:
    """Politica minima de contrasenia.

    No pretende ser exhaustiva (no exige simbolos ni mayusculas), pero
    rechaza los casos mas obvios: corta, solo numeros, con espacios en los
    bordes, o igual al nombre de usuario.
    """
    if len(password) < LONGITUD_MINIMA_PASSWORD:
        raise PasswordInvalida(
            f"La contrasenia debe tener al menos {LONGITUD_MINIMA_PASSWORD} caracteres"
        )
    if password.strip() != password:
        raise PasswordInvalida("La contrasenia no puede empezar ni terminar con espacios")
    if password.isdigit():
        raise PasswordInvalida("La contrasenia no puede ser solo numeros")
    if username and password.lower() == username.lower():
        raise PasswordInvalida("La contrasenia no puede ser igual al nombre de usuario")


@dataclass(slots=True, frozen=True)
class ClaimsSesion:
    """Lo que viaja adentro del JWT: lo minimo para autorizar sin ir a la base.

    Se arma al decodificar la cookie de sesion (ver app/core/dependencias.py)
    y no se vuelve a consultar la base en cada request: el token ya
    certifica identidad y rol al momento de emitirse, con una vigencia de
    `settings.jwt_exp_minutos`.
    """

    usuario_id: int
    rol: Rol
    username: str


class AccionesAuditoria:
    """Valores de `accion` que este modulo registra en la tabla auditoria."""

    SESION_INICIADA = "SESION_INICIADA"
    SESION_FALLIDA = "SESION_LOGIN_FALLIDA"
    USUARIO_REGISTRADO = "USUARIO_REGISTRADO"
    USUARIO_MODIFICADO = "USUARIO_MODIFICADO"
    USUARIO_DESACTIVADO = "USUARIO_DESACTIVADO"
    ROL_ASIGNADO = "ROL_ASIGNADO"
