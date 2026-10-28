"""Esquemas Pydantic del modulo de Notificaciones."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class PlantillaEntrada(BaseModel):
    """Datos para registrar una plantilla de notificación para un evento."""

    clave: str
    nombre: str = Field(min_length=1)
    cuerpo: str = Field(min_length=1)
    activa: bool = True


class ModificarPlantillaEntrada(BaseModel):
    """Datos editables de una plantilla existente."""

    nombre: str = Field(min_length=1)
    cuerpo: str = Field(min_length=1)
    activa: bool = True


class PlantillaSalida(BaseModel):
    """Plantilla de notificación tal como se devuelve al panel."""

    id: int
    clave: str
    nombre: str
    cuerpo: str
    activa: bool
    actualizado_por: int | None
    actualizado_en: datetime


class NotificacionSalida(BaseModel):
    """Notificación encolada con su estado de envío e intentos."""

    id: int
    clave: str
    destinatario: str
    cliente_id: int | None
    pedido_id: int | None
    estado: str
    intentos: int
    error: str | None
    creada_en: datetime
    enviada_en: datetime | None


class ResultadoProcesamiento(BaseModel):
    """Resumen de una corrida de envío de notificaciones pendientes."""

    procesadas: int
    enviadas: int
    fallidas: int
