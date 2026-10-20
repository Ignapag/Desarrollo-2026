"""Perfil público persistido, compartido por el arranque de API y workers."""

import json

import psycopg

from app.core.config import settings


def cargar_demo_publica() -> bool:
    """Sin parámetro válido conserva la configuración privada del entorno."""
    try:
        with psycopg.connect(settings.database_url, connect_timeout=5) as conn:
            fila = conn.execute(
                "SELECT valor FROM parametro WHERE clave=%s", ("chat_demo_publico",),
            ).fetchone()
        datos = json.loads(fila[0]) if fila else {}
    except (psycopg.Error, ValueError, TypeError):
        return False
    if not isinstance(datos, dict) or datos.get("habilitado") is not True:
        return False
    modo = datos.get("gemini_modo", "real")
    if not isinstance(modo, str) or modo not in {"real", "simulado"}:
        return False
    settings.chat_demo_habilitado = True
    settings.chat_demo_bd_compartida_autorizada = True
    settings.chat_demo_gemini_modo = modo
    return True
