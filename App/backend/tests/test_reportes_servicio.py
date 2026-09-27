"""Reglas, proyecciones por rol y contratos sin base de datos."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.core.errores import DatosInvalidos, SinPermiso
from app.modules.reportes.application.servicio_reportes import ServicioReportes
from app.modules.reportes.presentation.esquemas import (
    DashboardAdministrador,
    DashboardDuenio,
    FiltrosVentas,
    RentabilidadEstimada,
    VentaAdministrador,
    VentaDuenio,
)

DESDE = date(2026, 9, 1)
HASTA = date(2026, 9, 30)


class RepositorioFalso:
    def __init__(self) -> None:
        self.filas_ventas: list[dict] = []
        self.filas_pagos: list[dict] = []
        self.filas_rentabilidad: list[dict] = []
        self.consulta_ventas: dict | None = None
        self.consultas_pagos = 0

    async def resumen_pedidos(self):
        return {
            "pedidos_dia": 2,
            "pedidos_semana": 3,
            "pedidos_mes": 4,
            "actualizado_en": datetime(2026, 9, 23, 12, tzinfo=UTC),
        }

    async def ventas(
        self, desde, hasta, agrupacion_sql, categoria_id, producto_id, *, incluir_montos
    ):
        self.consulta_ventas = {
            "desde": desde,
            "hasta": hasta,
            "agrupacion": agrupacion_sql,
            "categoria_id": categoria_id,
            "producto_id": producto_id,
            "incluir_montos": incluir_montos,
        }
        if incluir_montos:
            return self.filas_ventas
        return [{k: v for k, v in fila.items() if k != "monto_total"} for fila in self.filas_ventas]

    async def pagos_por_metodo(self, desde, hasta):
        self.consultas_pagos += 1
        return self.filas_pagos

    async def rentabilidad(self, desde, hasta, categoria_id, producto_id):
        return self.filas_rentabilidad


class StockFalso:
    def __init__(self) -> None:
        self.consultas: list[str] = []

    async def listar(self, *, nivel, activo):
        self.consultas.append(nivel)
        if nivel == "SIN_STOCK":
            return [
                {
                    "id": 1,
                    "nombre": "Pan",
                    "unidad_medida": "UNIDAD",
                    "cantidad_actual": Decimal("0"),
                    "umbral_minimo": Decimal("5"),
                    "nivel": nivel,
                    "indicador_alerta": True,
                }
            ]
        return []


@pytest.fixture
def servicio():
    repo = RepositorioFalso()
    stock = StockFalso()
    return ServicioReportes(repo, stock)


def venta(
    *,
    producto_id=1,
    producto="Monu",
    cantidad=2,
    monto="100",
    periodo=DESDE,
    categoria="Hamburguesas",
    pedidos=1,
):
    return {
        "periodo": periodo,
        "producto_id": producto_id,
        "producto": producto,
        "categoria": categoria,
        "cantidad_vendida": cantidad,
        "cantidad_pedidos": pedidos,
        "monto_total": Decimal(monto),
    }


@pytest.mark.asyncio
async def test_rechaza_rango_invalido_y_temporada(servicio):
    with pytest.raises(DatosInvalidos):
        await servicio.ventas(rol="DUENIO", fecha_desde=HASTA, fecha_hasta=DESDE, agrupacion="DIA")
    with pytest.raises(DatosInvalidos):
        await servicio.ventas(
            rol="DUENIO",
            fecha_desde=DESDE,
            fecha_hasta=HASTA,
            agrupacion="TEMPORADA",
        )
    with pytest.raises(ValidationError):
        FiltrosVentas(fecha_desde=HASTA, fecha_hasta=DESDE, agrupacion="DIA")


@pytest.mark.asyncio
async def test_ventas_sin_datos(servicio):
    assert (
        await servicio.ventas(rol="DUENIO", fecha_desde=DESDE, fecha_hasta=HASTA, agrupacion="DIA")
        == []
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "agrupacion,sql",
    [
        ("DIA", "day"),
        ("SEMANA", "week"),
        ("MES", "month"),
    ],
)
async def test_agrupaciones_y_filtros(servicio, agrupacion, sql):
    await servicio.ventas(
        rol="DUENIO",
        fecha_desde=DESDE,
        fecha_hasta=HASTA,
        agrupacion=agrupacion,
        categoria_id=4,
        producto_id=8,
    )
    assert servicio.repo.consulta_ventas == {
        "desde": DESDE,
        "hasta": HASTA,
        "agrupacion": sql,
        "categoria_id": 4,
        "producto_id": 8,
        "incluir_montos": True,
    }


@pytest.mark.asyncio
async def test_ranking_y_participacion_por_periodo(servicio):
    servicio.repo.filas_ventas = [
        venta(producto_id=1, cantidad=1, monto="25"),
        venta(producto_id=2, cantidad=3, monto="75"),
        venta(producto_id=1, cantidad=2, monto="40", periodo=date(2026, 9, 2)),
    ]
    salida = await servicio.ventas(
        rol="DUENIO", fecha_desde=DESDE, fecha_hasta=HASTA, agrupacion="DIA"
    )
    assert [x["producto_id"] for x in salida] == [2, 1, 1]
    assert [x["ranking"] for x in salida] == [1, 2, 1]
    assert [x["participacion"] for x in salida] == [75, 25, 100]
    assert all(VentaDuenio.model_validate(x) for x in salida)


@pytest.mark.asyncio
async def test_administrador_no_recibe_montos_ni_consulta_pagos(servicio):
    servicio.repo.filas_ventas = [venta()]
    ventas = await servicio.ventas(
        rol="ADMINISTRADOR",
        fecha_desde=DESDE,
        fecha_hasta=HASTA,
        agrupacion="DIA",
    )
    assert "monto_total" not in ventas[0]
    assert "participacion" not in ventas[0]
    assert ventas[0]["cantidad_pedidos"] == 1
    assert servicio.repo.consulta_ventas["incluir_montos"] is False
    VentaAdministrador.model_validate(ventas[0])
    with pytest.raises(ValidationError):
        VentaAdministrador.model_validate({**ventas[0], "monto_total": Decimal("100")})

    dashboard = await servicio.dashboard(rol="ADMINISTRADOR", fecha_desde=DESDE, fecha_hasta=HASTA)
    assert "ingreso_neto_confirmado" not in dashboard
    assert "ingresos_por_metodo" not in dashboard
    assert servicio.repo.consultas_pagos == 0
    assert servicio.stock.consultas == ["SIN_STOCK", "BAJO_UMBRAL"]
    assert dashboard["alertas_stock"] == dashboard["ingredientes_criticos"]
    DashboardAdministrador.model_validate(dashboard)
    with pytest.raises(ValidationError):
        DashboardAdministrador.model_validate({**dashboard, "ingreso_neto_confirmado": 0})


@pytest.mark.asyncio
async def test_duenio_recibe_ingreso_neto_sin_propina(servicio):
    servicio.repo.filas_pagos = [
        {"metodo_pago": "EFECTIVO", "ingreso_neto": Decimal("70")},
        {"metodo_pago": "TRANSFERENCIA", "ingreso_neto": Decimal("50")},
    ]
    dashboard = await servicio.dashboard(rol="DUENIO", fecha_desde=DESDE, fecha_hasta=HASTA)
    assert dashboard["ingreso_neto_confirmado"] == 120
    assert servicio.repo.consultas_pagos == 1
    DashboardDuenio.model_validate(dashboard)


@pytest.mark.asyncio
async def test_rentabilidad_solo_duenio_y_estimada(servicio):
    with pytest.raises(SinPermiso):
        await servicio.rentabilidad_estimada(
            rol="ADMINISTRADOR", fecha_desde=DESDE, fecha_hasta=HASTA
        )
    servicio.repo.filas_rentabilidad = [
        {
            "producto_id": 1,
            "producto": "Monu",
            "unidades_vendidas": 2,
            "ingreso_estimado": Decimal("100"),
            "costo_estimado": Decimal("40"),
        }
    ]
    salida = await servicio.rentabilidad_estimada(
        rol="DUENIO", fecha_desde=DESDE, fecha_hasta=HASTA
    )
    assert salida[0]["margen_estimado"] == 60
    assert salida[0]["porcentaje_margen"] == 60
    RentabilidadEstimada.model_validate(salida[0])
