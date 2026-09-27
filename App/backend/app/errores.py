"""Excepciones compartidas por las reglas y casos de uso.

Este modulo no depende de FastAPI ni de infraestructura. La traduccion a
respuestas HTTP vive en ``app.core.errores``.
"""

from __future__ import annotations


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
