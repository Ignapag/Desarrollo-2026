"""Pruebas de dominio del modulo de Usuarios y Seguridad.

Logica pura (politica de contrasenia) y las dos primitivas de
app/core/seguridad.py (hash bcrypt y JWT). No necesitan base de datos.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.core.config import settings
from app.core.seguridad import (
    ALGORITMO_JWT,
    TokenInvalido,
    crear_token,
    decodificar_token,
    hashear_password,
    verificar_password,
)
from app.modules.usuarios.domain.entidades import PasswordInvalida, validar_password

# ------------------------------------------------------------------ password


def test_password_valida_no_lanza():
    validar_password("unaClaveOk1")


@pytest.mark.parametrize(
    "password",
    [
        "corta1",  # menos de 8 caracteres
        "12345678",  # solo numeros
        " conEspacios ",  # espacios en los bordes
    ],
)
def test_password_invalida_por_regla_basica(password: str):
    with pytest.raises(PasswordInvalida):
        validar_password(password)


def test_password_no_puede_ser_igual_al_username():
    with pytest.raises(PasswordInvalida):
        validar_password("miusuario123", username="miusuario123")
    with pytest.raises(PasswordInvalida):
        # Case-insensitive: username en la base es CITEXT.
        validar_password("MiUsuario123", username="miusuario123")


# ------------------------------------------------------------------- hash


def test_hashear_y_verificar_password_correcta():
    hash_ = hashear_password("unaClaveOk1")
    assert hash_ != "unaClaveOk1"
    assert verificar_password("unaClaveOk1", hash_)


def test_verificar_password_incorrecta_es_false():
    hash_ = hashear_password("unaClaveOk1")
    assert not verificar_password("otraClave1", hash_)


def test_verificar_password_con_hash_corrupto_es_false():
    """No debe reventar con un hash invalido: solo decir que no coincide."""
    assert not verificar_password("cualquiera", "esto-no-es-un-hash-bcrypt")


def test_hash_compatible_con_el_formato_bcrypt_de_pgcrypto():
    """seed.sql hashea con crypt(password, gen_salt('bf')): mismo formato $2b$/$2a$."""
    hash_ = hashear_password("unaClaveOk1")
    assert hash_.startswith(("$2a$", "$2b$"))


# --------------------------------------------------------------------- jwt


def test_crear_y_decodificar_token_roundtrip():
    token = crear_token(usuario_id=42, rol="ADMINISTRADOR", username="admin")
    payload = decodificar_token(token)
    assert payload["sub"] == "42"
    assert payload["rol"] == "ADMINISTRADOR"
    assert payload["username"] == "admin"


def test_decodificar_token_vencido_lanza_token_invalido():
    ahora = datetime.now(UTC)
    payload = {
        "sub": "1",
        "rol": "CLIENTE",
        "username": "x",
        "iat": ahora - timedelta(hours=2),
        "exp": ahora - timedelta(hours=1),  # vencio hace una hora
    }
    token_vencido = jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITMO_JWT)

    with pytest.raises(TokenInvalido):
        decodificar_token(token_vencido)


def test_decodificar_token_con_firma_invalida_lanza_token_invalido():
    token = crear_token(usuario_id=1, rol="CLIENTE", username="x")
    encabezado, cuerpo, firma = token.split(".")
    # Se toca el primer caracter de la firma, no el ultimo: en base64url el
    # ultimo caracter de un bloque puede compartir bits de relleno y, por
    # coincidencia, decodificar al mismo byte (asi fallo esta prueba antes).
    firma_alterada = ("a" if firma[0] != "a" else "b") + firma[1:]
    token_alterado = f"{encabezado}.{cuerpo}.{firma_alterada}"

    with pytest.raises(TokenInvalido):
        decodificar_token(token_alterado)


def test_decodificar_token_basura_lanza_token_invalido():
    with pytest.raises(TokenInvalido):
        decodificar_token("no-soy-un-jwt")
