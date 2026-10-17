"""Arranque de Render: python -m scripts.serve [--migrar] [--sin-worker].

Conserva la única API y su pool. En modo WhatsApp real ejecuta el worker en
el mismo servicio; en simulado no procesa colas automáticamente. En Windows
el desarrollo habitual sigue usando run.py.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import os
from contextlib import asynccontextmanager, suppress
from functools import partial

import psycopg
import uvicorn

from app.core.config import settings
from app.main import app
from app.main import ciclo_de_vida as ciclo_api
from scripts.migrate import _aplicadas, _migraciones, aplicar
from scripts.whatsapp_worker import procesar_continuamente


def checksum_compatible(archivo, registrado: str) -> bool:
    """Conserva hashes históricos de Windows/Linux sin aceptar SQL alterado."""
    original = archivo.read_bytes()
    lf = original.replace(b"\r\n", b"\n")
    return registrado in {
        hashlib.sha256(datos).hexdigest()[:16]
        for datos in (original, lf, lf.replace(b"\n", b"\r\n"))
    }


def migrar() -> None:
    """Solo pendientes, con bloqueo entre despliegues; nunca seed ni reset."""
    with psycopg.connect(settings.database_url, connect_timeout=15) as conn:
        # El bloqueo es de sesión: aplicar() confirma cada migración por separado.
        conn.execute("SELECT pg_advisory_lock(7019262026)")
        if conn.execute("SELECT to_regclass('schema_migrations')").fetchone()[0]:
            aplicadas = _aplicadas(conn)
            modificadas = [
                archivo.stem for archivo in _migraciones()
                if archivo.stem in aplicadas
                and not checksum_compatible(archivo, aplicadas[archivo.stem])
            ]
            if modificadas:
                raise RuntimeError(
                    "Migraciones aplicadas con checksum distinto: " + ", ".join(modificadas)
                )
        aplicar(conn)


@asynccontextmanager
async def ciclo_servicio(api, *, con_worker: bool):
    async with ciclo_api(api):
        tarea = asyncio.create_task(procesar_continuamente()) if con_worker else None
        try:
            yield
        finally:
            if tarea is not None:
                tarea.cancel()
                with suppress(asyncio.CancelledError):
                    await tarea


def iniciar_servidor(*, con_worker: bool) -> None:
    if settings.whatsapp_modo == "real":
        campos = (
            "whatsapp_token", "whatsapp_phone_number_id", "whatsapp_numero_negocio",
            "whatsapp_app_secret", "whatsapp_verify_token",
        )
        faltantes = [campo.upper() for campo in campos if not getattr(settings, campo).strip()]
        if settings.gemini_modo == "real" and not settings.gemini_api_key.strip():
            faltantes.append("GEMINI_API_KEY")
        if faltantes:
            raise RuntimeError("Falta configurar: " + ", ".join(faltantes))
    app.router.lifespan_context = partial(
        ciclo_servicio, con_worker=con_worker and settings.whatsapp_modo == "real"
    )
    uvicorn.run(
        app, host="0.0.0.0", port=int(os.environ.get("PORT", "8000")),
        reload=False, access_log=False,
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--migrar", action="store_true", help="aplicar solo migraciones pendientes")
    parser.add_argument("--sin-worker", action="store_true", help="usar un worker externo")
    args = parser.parse_args(argv)
    if args.migrar:
        migrar()
    iniciar_servidor(con_worker=not args.sin_worker)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
