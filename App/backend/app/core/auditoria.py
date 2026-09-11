"""Registro de acciones criticas en la tabla auditoria (RNF-09).

Helper compartido: cualquier modulo lo usa para dejar rastro de quien hizo
que y cuando. El modulo de Usuarios y Seguridad (EDT 1.8) agregara despues
la consulta del log desde el panel.
"""

from __future__ import annotations

import json
from typing import Any

from app.core.db import UnidadDeTrabajo


async def registrar(
    uow: UnidadDeTrabajo,
    *,
    accion: str,
    entidad: str,
    entidad_id: str | int | None = None,
    usuario_id: int | None = None,
    datos: dict[str, Any] | None = None,
    ip: str | None = None,
) -> None:
    await uow.ejecutar(
        """
        INSERT INTO auditoria (usuario_id, accion, entidad, entidad_id, datos, ip)
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (
            usuario_id,
            accion,
            entidad,
            str(entidad_id) if entidad_id is not None else None,
            json.dumps(datos, default=str) if datos else None,
            ip,
        ),
    )
