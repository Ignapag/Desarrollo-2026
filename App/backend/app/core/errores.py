"""Errores de dominio y su traduccion a respuestas HTTP.

Las capas de dominio y aplicacion nunca importan FastAPI: lanzan estas
excepciones y la capa de presentacion las mapea a codigos HTTP.
"""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse


class ErrorDominio(Exception):
    """Error de negocio previsible."""

    codigo_http = 400
    codigo = "error_dominio"

    def __init__(self, mensaje: str, detalles: dict | None = None) -> None:
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.detalles = detalles or {}


class NoEncontrado(ErrorDominio):
    codigo_http = 404
    codigo = "no_encontrado"


class ReglaDeNegocio(ErrorDominio):
    codigo_http = 409
    codigo = "regla_de_negocio"


class DatosInvalidos(ErrorDominio):
    codigo_http = 422
    codigo = "datos_invalidos"


class NoAutenticado(ErrorDominio):
    codigo_http = 401
    codigo = "no_autenticado"


class SinPermiso(ErrorDominio):
    codigo_http = 403
    codigo = "sin_permiso"


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
