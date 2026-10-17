"""Traduccion de errores a respuestas HTTP.

Las clases de error viven en ``app.errores``, sin frameworks: dominio,
aplicacion y adaptadores las importan desde alli. Este modulo solo contiene
los manejadores que ``app.main`` registra.
"""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse

from app.errores import ErrorDominio


async def manejador_error_dominio(_: Request, exc: ErrorDominio) -> JSONResponse:
    return JSONResponse(
        status_code=exc.codigo_http,
        content={"codigo": exc.codigo, "mensaje": exc.mensaje, "detalles": exc.detalles},
    )


async def manejador_base_no_disponible(_: Request, exc: Exception) -> JSONResponse:
    """La base no responde: 503, no 500.

    Un 500 sugiere un bug del sistema; esto es indisponibilidad de
    infraestructura y el cliente puede reintentar.
    """
    return JSONResponse(
        status_code=503,
        content={
            "codigo": "base_no_disponible",
            "mensaje": "La base de datos no esta disponible. Reintenta en unos segundos.",
            "detalles": {"tipo": exc.__class__.__name__},
        },
    )
