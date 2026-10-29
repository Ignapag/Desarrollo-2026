"""Hash de contrasenias y JWT de sesion (EDT 1.8 - Usuarios y Seguridad).

Aisla las dos primitivas criptograficas del modulo para que el resto de la
app (dependencias de FastAPI, casos de uso de otros modulos) no importe
bcrypt ni PyJWT directamente: solo conocen `hashear_password`,
`verificar_password`, `crear_token` y `decodificar_token`.

El hash es compatible con el que genera `seed.sql` via pgcrypto
(`crypt(password, gen_salt('bf'))`): ambos producen un hash bcrypt estandar
($2b$/$2a$), asi que `verificar_password` funciona igual sobre una cuenta
creada por la API que sobre una de los datos de desarrollo.

bcrypt tarda cientos de milisegundos a proposito: desde codigo async se usa
`verificar_password_sin_bloquear`, que lo corre en un hilo para no frenar el
event loop y que tambien paga ese costo cuando la cuenta no existe.
"""

from __future__ import annotations

import asyncio
import secrets
from datetime import UTC, datetime, timedelta
from functools import cache
from typing import Any

import bcrypt
import jwt

from app.core.config import settings

ALGORITMO_JWT = "HS256"


def hashear_password(password: str) -> str:
    """Genera un hash bcrypt con sal aleatoria para guardar la contraseña."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verificar_password(password: str, password_hash: str) -> bool:
    """Compara la contraseña ingresada con el hash bcrypt almacenado."""
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        # Hash vacio, corrupto o en un formato que bcrypt no reconoce.
        return False


@cache
def _hash_ficticio() -> str:
    """Hash de una clave aleatoria descartada, con el mismo costo que `hashear_password`."""
    return hashear_password(secrets.token_urlsafe(32))


def _costo(password_hash: str) -> int | None:
    """Rondas de un hash bcrypt (`$2b$12$...` -> 12), o None si no tiene ese formato."""
    partes = password_hash.split("$")
    return int(partes[2]) if len(partes) > 3 and partes[2].isdigit() else None


def _verificar_o_simular(password: str, password_hash: str | None) -> bool:
    # Sin cuenta, o con un hash mas barato que el estandar (seed.sql usa costo
    # 6 de pgcrypto) o ilegible, se paga ademas la verificacion ficticia: asi
    # la demora no revela si el username existe. Lo ficticio nunca autentica.
    costo = _costo(password_hash) if password_hash is not None else None
    if costo is None or costo < _costo(_hash_ficticio()):
        verificar_password(password, _hash_ficticio())
    if password_hash is None:
        return False
    return verificar_password(password, password_hash)


async def verificar_password_sin_bloquear(password: str, password_hash: str | None) -> bool:
    """Verifica la contraseña en un hilo aparte, sin bloquear el event loop.

    ``password_hash=None`` indica que la cuenta no existe: se ejecuta una
    verificación de costo equivalente y el resultado es siempre ``False``.
    Todo intento paga al menos una verificación del costo de `hashear_password`.
    """
    return await asyncio.to_thread(_verificar_o_simular, password, password_hash)


class TokenInvalido(Exception):
    """El token no vino, esta mal firmado, o vencio."""


def crear_token(*, usuario_id: int, rol: str, username: str) -> str:
    """Emite el JWT de sesión con id, rol y username, válido por ``jwt_exp_minutos``."""
    ahora = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": str(usuario_id),
        "rol": rol,
        "username": username,
        "iat": ahora,
        "exp": ahora + timedelta(minutes=settings.jwt_exp_minutos),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITMO_JWT)


def decodificar_token(token: str) -> dict[str, Any]:
    """Valida firma y vencimiento del JWT; lanza ``TokenInvalido`` si no es válido."""
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITMO_JWT])
    except jwt.PyJWTError as exc:
        raise TokenInvalido(str(exc)) from exc
