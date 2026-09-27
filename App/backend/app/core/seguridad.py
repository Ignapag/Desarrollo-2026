"""Hash de contrasenias y JWT de sesion (EDT 1.8 - Usuarios y Seguridad).

Aisla las dos primitivas criptograficas del modulo para que el resto de la
app (dependencias de FastAPI, casos de uso de otros modulos) no importe
bcrypt ni PyJWT directamente: solo conocen `hashear_password`,
`verificar_password`, `crear_token` y `decodificar_token`.

El hash es compatible con el que genera `seed.sql` via pgcrypto
(`crypt(password, gen_salt('bf'))`): ambos producen un hash bcrypt estandar
($2b$/$2a$), asi que `verificar_password` funciona igual sobre una cuenta
creada por la API que sobre una de los datos de desarrollo.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
import jwt

from app.core.config import settings

ALGORITMO_JWT = "HS256"


def hashear_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verificar_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        # Hash vacio, corrupto o en un formato que bcrypt no reconoce.
        return False


class TokenInvalido(Exception):
    """El token no vino, esta mal firmado, o vencio."""


def crear_token(*, usuario_id: int, rol: str, username: str) -> str:
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
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITMO_JWT])
    except jwt.PyJWTError as exc:
        raise TokenInvalido(str(exc)) from exc
