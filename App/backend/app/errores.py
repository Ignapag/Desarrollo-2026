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
        """Guarda el mensaje legible y los detalles estructurados que viajan al cliente."""
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.detalles = detalles or {}


class NoEncontrado(ErrorDominio):
    """El recurso pedido (pedido, producto, usuario, etc.) no existe: responde 404."""

    codigo_http = 404
    codigo = "no_encontrado"


class ReglaDeNegocio(ErrorDominio):
    """La operación viola una regla de negocio o el estado actual lo impide: 409."""

    codigo_http = 409
    codigo = "regla_de_negocio"


class DatosInvalidos(ErrorDominio):
    """Los datos recibidos no cumplen las validaciones del dominio: responde 422."""

    codigo_http = 422
    codigo = "datos_invalidos"


class NoAutenticado(ErrorDominio):
    """No hay sesión válida (cookie ausente, token vencido o inválido): 401."""

    codigo_http = 401
    codigo = "no_autenticado"


class SinPermiso(ErrorDominio):
    """El usuario autenticado no tiene el permiso o rol requerido: responde 403."""

    codigo_http = 403
    codigo = "sin_permiso"
