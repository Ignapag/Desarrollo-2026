"""Punto de entrada del servidor de desarrollo.

Usar esto en lugar de `uvicorn app.main:app` directamente:

    python run.py

Motivo: en Windows, psycopg en modo async necesita SelectorEventLoop, y
Python usa ProactorEventLoop por defecto. Ajustarlo dentro de la aplicacion
no alcanza, porque para cuando uvicorn importa `app.main` el event loop ya
esta creado. Hay que fijar la politica ANTES de que uvicorn arranque, y eso
solo se puede hacer desde un entrypoint propio.

Sin esto, la API levanta pero ninguna consulta a PostgreSQL funciona: el
pool no consigue abrir conexiones y todos los endpoints responden 503.
"""

from __future__ import annotations

import asyncio
import sys

# En Windows psycopg async requiere SelectorEventLoop: se fija antes de importar uvicorn.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import uvicorn  # noqa: E402  - despues de fijar la politica del event loop

from app.core.config import settings  # noqa: E402

# Levanta la API local en 127.0.0.1:8000, con recarga automatica si debug esta activo.
if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=8000,
        reload=settings.debug,
    )
