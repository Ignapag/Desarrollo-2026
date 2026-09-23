"""Registro y consulta de acciones criticas en la tabla auditoria (RNF-09).

Helper compartido: cualquier modulo usa `registrar()` para dejar rastro de
quien hizo que y cuando. `listar()` y `obtener()` implementan la consulta
del log (CU_USR_07 del modulo de Usuarios y Seguridad, EDT 1.8); viven aca
y no en ese modulo porque la tabla es unica y compartida por todos.
"""

from __future__ import annotations

import json
from datetime import datetime
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


_CAMPOS_EVENTO = """
    a.id, a.usuario_id, u.username, a.accion, a.entidad, a.entidad_id,
    a.datos, a.ip::text AS ip, a.creado_en
"""


async def listar(
    uow: UnidadDeTrabajo,
    *,
    desde: datetime | None = None,
    hasta: datetime | None = None,
    usuario_id: int | None = None,
    accion: str | None = None,
    entidad: str | None = None,
    limite: int = 200,
) -> list[dict[str, Any]]:
    """Consulta el log de auditoria (CU_USR_07), del mas reciente al mas viejo.

    Sin filtros devuelve las ultimas `limite` acciones registradas por
    cualquier modulo del sistema.
    """
    condiciones: list[str] = []
    parametros: list[Any] = []

    if desde is not None:
        condiciones.append("a.creado_en >= %s")
        parametros.append(desde)
    if hasta is not None:
        condiciones.append("a.creado_en <= %s")
        parametros.append(hasta)
    if usuario_id is not None:
        condiciones.append("a.usuario_id = %s")
        parametros.append(usuario_id)
    if accion is not None:
        condiciones.append("a.accion = %s")
        parametros.append(accion)
    if entidad is not None:
        condiciones.append("a.entidad = %s")
        parametros.append(entidad)

    where = f"WHERE {' AND '.join(condiciones)}" if condiciones else ""
    parametros.append(limite)

    return await uow.todos(
        f"""
        SELECT {_CAMPOS_EVENTO}
        FROM auditoria a
        LEFT JOIN usuario u ON u.id = a.usuario_id
        {where}
        ORDER BY a.creado_en DESC
        LIMIT %s
        """,
        parametros,
    )


async def obtener(uow: UnidadDeTrabajo, evento_id: int) -> dict[str, Any] | None:
    return await uow.uno(
        f"""
        SELECT {_CAMPOS_EVENTO}
        FROM auditoria a
        LEFT JOIN usuario u ON u.id = a.usuario_id
        WHERE a.id = %s
        """,
        (evento_id,),
    )
