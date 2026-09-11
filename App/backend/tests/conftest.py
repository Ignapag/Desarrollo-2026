"""Configuracion comun de las pruebas.

Importar app.core.db ajusta el event loop de Windows, necesario para que
psycopg funcione en modo async (ver configurar_event_loop).
"""

from __future__ import annotations

from app.core.db import configurar_event_loop

configurar_event_loop()
