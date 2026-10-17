"""python -m scripts.whatsapp_worker [--una-vez]. Sin Redis ni servicio nuevo."""

import argparse
import asyncio
import logging

from app.core.db import abrir_pool, cerrar_pool
from app.modules.whatsapp.presentation.procesamiento import procesar_lote

log = logging.getLogger("monuburger.whatsapp.worker")
pausar = asyncio.sleep


async def procesar_continuamente():
    """Usa el pool del llamador; un fallo transitorio conserva inbox y outbox."""
    while True:
        try:
            await procesar_lote()
        except Exception as exc:
            # No imprimir texto de mensajes, tokens ni detalles del proveedor/DSN.
            log.warning("Worker WhatsApp reintentará el ciclo (%s)", type(exc).__name__)
        await pausar(2)


async def ejecutar(una_vez=False):
    await abrir_pool()
    try:
        if una_vez:
            await procesar_lote()
        else:
            await procesar_continuamente()
    finally:
        await cerrar_pool()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--una-vez", action="store_true")
    asyncio.run(ejecutar(parser.parse_args().una_vez))
