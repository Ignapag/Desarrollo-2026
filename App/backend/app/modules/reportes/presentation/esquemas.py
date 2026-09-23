"""Contratos distintos por rol; los financieros no existen en los de Administrador."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class FiltrosPeriodo(BaseModel):
    fecha_desde: date
    fecha_hasta: date

    @model_validator(mode="after")
    def validar_rango(self) -> FiltrosPeriodo:
        if self.fecha_desde > self.fecha_hasta:
            raise ValueError("La fecha desde debe ser anterior o igual a la fecha hasta")
        return self


class FiltrosVentas(FiltrosPeriodo):
    agrupacion: Literal["DIA", "SEMANA", "MES"]
    categoria_id: int | None = Field(default=None, gt=0)
    producto_id: int | None = Field(default=None, gt=0)


class FiltrosRentabilidad(FiltrosPeriodo):
    categoria_id: int | None = Field(default=None, gt=0)
    producto_id: int | None = Field(default=None, gt=0)


class RankingProducto(BaseModel):
    producto_id: int
    producto: str
    cantidad_vendida: int
    ranking: int


class IngredienteCritico(BaseModel):
    id: int
    nombre: str
    unidad_medida: str
    cantidad_actual: Decimal
    umbral_minimo: Decimal
    nivel: Literal["BAJO_UMBRAL", "SIN_STOCK"]
    indicador_alerta: bool


class DashboardAdministrador(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fecha_desde: date
    fecha_hasta: date
    pedidos_dia: int
    pedidos_semana: int
    pedidos_mes: int
    ranking_productos: list[RankingProducto]
    ingredientes_criticos: list[IngredienteCritico]
    alertas_stock: list[IngredienteCritico]
    actualizado_en: datetime


class IngresoPorMetodo(BaseModel):
    metodo_pago: str
    ingreso_neto: Decimal


class DashboardDuenio(DashboardAdministrador):
    ingreso_neto_confirmado: Decimal
    ingresos_por_metodo: list[IngresoPorMetodo]


class VentaAdministrador(BaseModel):
    model_config = ConfigDict(extra="forbid")

    periodo: date
    producto_id: int
    producto: str
    categoria: str
    cantidad_vendida: int
    cantidad_pedidos: int
    ranking: int


class VentaDuenio(BaseModel):
    model_config = ConfigDict(extra="forbid")

    periodo: date
    producto_id: int
    producto: str
    categoria: str
    cantidad_vendida: int
    monto_total: Decimal
    participacion: Decimal
    ranking: int


class RentabilidadEstimada(BaseModel):
    """Combina precios historicos con costos actuales: no es un resultado historico exacto."""

    model_config = ConfigDict(extra="forbid")

    tipo: Literal["RENTABILIDAD_ESTIMADA"]
    producto_id: int
    producto: str
    unidades_vendidas: int
    ingreso_estimado: Decimal
    costo_estimado: Decimal
    margen_estimado: Decimal
    porcentaje_margen: Decimal
