"""Esquemas Pydantic del modulo de Notificaciones."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class PlantillaEntrada(BaseModel):
    clave: str
    nombre: str = Field(min_length=1)
    cuerpo: str = Field(min_length=1)
    activa: bool = True


class ModificarPlantillaEntrada(BaseModel):
    nombre: str = Field(min_length=1)
    cuerpo: str = Field(min_length=1)
    activa: bool = True


class PlantillaSalida(BaseModel):
    id: int
    clave: str
    nombre: str
    cuerpo: str
    activa: bool
    actualizado_por: int | None
    actualizado_en: datetime


class NotificacionSalida(BaseModel):
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
    procesadas: int
    enviadas: int
    fallidas: int
