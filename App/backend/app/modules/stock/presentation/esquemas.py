"""Esquemas de stock; se expondran cuando exista la guarda real de roles."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Unidad = Literal["KG", "GR", "LT", "ML", "UNIDAD"]
Nivel = Literal["NORMAL", "BAJO_UMBRAL", "SIN_STOCK"]
TipoMovimiento = Literal["CONSUMO", "REPOSICION", "AJUSTE", "DEVOLUCION", "MERMA"]


class IngredienteCrear(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nombre: str = Field(min_length=1)
    unidad_medida: Unidad
    cantidad_actual: Decimal = Field(ge=0, max_digits=12, decimal_places=3)
    umbral_minimo: Decimal = Field(gt=0, max_digits=12, decimal_places=3)
    costo_unitario: Decimal = Field(default=Decimal("0"), ge=0, max_digits=12, decimal_places=2)
    dias_reposicion: list[str] = Field(default_factory=list)
    responsable_id: int | None = Field(default=None, gt=0)
    activo: bool = True


class IngredienteModificar(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nombre: str | None = Field(default=None, min_length=1)
    unidad_medida: Unidad | None = None
    umbral_minimo: Decimal | None = Field(default=None, gt=0)
    costo_unitario: Decimal | None = Field(default=None, ge=0)
    dias_reposicion: list[str] | None = None
    responsable_id: int | None = Field(default=None, gt=0)
    activo: bool | None = None


class FiltrosIngredientes(BaseModel):
    nombre: str | None = None
    responsable_id: int | None = Field(default=None, gt=0)
    activo: bool | None = None
    nivel: Nivel | None = None


class ReposicionCrear(BaseModel):
    cantidad: Decimal = Field(gt=0, max_digits=12, decimal_places=3)
    origen: str = Field(default="REPOSICION_MANUAL", min_length=1)


class FiltrosHistorial(BaseModel):
    ingrediente_id: int | None = Field(default=None, gt=0)
    desde: date | None = None
    hasta: date | None = None
    tipo: TipoMovimiento | None = None


class IngredienteSalida(BaseModel):
    id: int
    nombre: str
    unidad_medida: Unidad
    cantidad_actual: Decimal
    umbral_minimo: Decimal
    indicador_alerta: bool
    responsable_id: int | None
    responsable: str | None
    fecha_ultima_reposicion: datetime | None
    activo: bool
    nivel: Nivel


class MovimientoSalida(BaseModel):
    id: int
    ingrediente_id: int
    creado_en: datetime
    tipo: TipoMovimiento
    cantidad: Decimal
    saldo_anterior: Decimal
    saldo_resultante: Decimal
    usuario_id: int | None
    usuario_origen: str | None
    pedido_id: int | None


class ReposicionSalida(BaseModel):
    ingrediente_id: int
    saldo_anterior: Decimal
    cantidad: Decimal
    saldo_resultante: Decimal
    fecha_ultima_reposicion: datetime
    movimiento_id: int
    creado_en: datetime
