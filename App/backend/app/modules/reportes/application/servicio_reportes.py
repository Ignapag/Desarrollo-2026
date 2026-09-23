"""Compone reportes por rol sin exponer datos financieros al Administrador."""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal
from typing import Protocol

from app.modules.reportes.domain.reglas import validar_agrupacion, validar_periodo, validar_rol
from app.modules.stock.application.servicio_stock import ServicioStock


class RepositorioReportes(Protocol):
    async def resumen_pedidos(self) -> dict: ...
    async def ventas(
        self,
        desde: date,
        hasta: date,
        agrupacion_sql: str,
        categoria_id: int | None,
        producto_id: int | None,
        *,
        incluir_montos: bool,
    ) -> list[dict]: ...
    async def pagos_por_metodo(self, desde: date, hasta: date) -> list[dict]: ...
    async def rentabilidad(
        self, desde: date, hasta: date, categoria_id: int | None, producto_id: int | None
    ) -> list[dict]: ...


class ServicioReportes:
    def __init__(self, repositorio: RepositorioReportes, stock: ServicioStock) -> None:
        self.repo = repositorio
        self.stock = stock

    async def dashboard(self, *, rol: str, fecha_desde: date, fecha_hasta: date) -> dict:
        validar_rol(rol)
        validar_periodo(fecha_desde, fecha_hasta)
        resumen = await self.repo.resumen_pedidos()
        ventas = await self.ventas(
            rol="ADMINISTRADOR",
            fecha_desde=fecha_desde,
            fecha_hasta=fecha_hasta,
            agrupacion="DIA",
        )
        # Stock ya define los niveles y el indicador de alerta activa.
        criticos = [
            *(await self.stock.listar(nivel="SIN_STOCK", activo=True)),
            *(await self.stock.listar(nivel="BAJO_UMBRAL", activo=True)),
        ]
        ingredientes = [
            {
                "id": fila["id"],
                "nombre": fila["nombre"],
                "unidad_medida": fila["unidad_medida"],
                "cantidad_actual": fila["cantidad_actual"],
                "umbral_minimo": fila["umbral_minimo"],
                "nivel": fila["nivel"],
                "indicador_alerta": fila["indicador_alerta"],
            }
            for fila in criticos
        ]
        # El ranking del dashboard agrega las cantidades de todos los dias del rango.
        cantidades: dict[int, dict] = {}
        for fila in ventas:
            item = cantidades.setdefault(
                fila["producto_id"],
                {
                    "producto_id": fila["producto_id"],
                    "producto": fila["producto"],
                    "cantidad_vendida": 0,
                },
            )
            item["cantidad_vendida"] += fila["cantidad_vendida"]
        ranking = sorted(
            cantidades.values(), key=lambda f: (-f["cantidad_vendida"], f["producto_id"])
        )
        for posicion, fila in enumerate(ranking, start=1):
            fila["ranking"] = posicion

        resultado = {
            "fecha_desde": fecha_desde,
            "fecha_hasta": fecha_hasta,
            "pedidos_dia": resumen["pedidos_dia"],
            "pedidos_semana": resumen["pedidos_semana"],
            "pedidos_mes": resumen["pedidos_mes"],
            "ranking_productos": ranking,
            "ingredientes_criticos": ingredientes,
            "alertas_stock": [fila for fila in ingredientes if fila["indicador_alerta"]],
            "actualizado_en": resumen["actualizado_en"],
        }
        if rol == "DUENIO":
            metodos = await self.repo.pagos_por_metodo(fecha_desde, fecha_hasta)
            resultado["ingreso_neto_confirmado"] = sum(
                (fila["ingreso_neto"] for fila in metodos), Decimal("0")
            )
            resultado["ingresos_por_metodo"] = metodos
        return resultado

    async def ventas(
        self,
        *,
        rol: str,
        fecha_desde: date,
        fecha_hasta: date,
        agrupacion: str,
        categoria_id: int | None = None,
        producto_id: int | None = None,
    ) -> list[dict]:
        validar_rol(rol)
        validar_periodo(fecha_desde, fecha_hasta)
        grupo_sql = validar_agrupacion(agrupacion)
        filas = await self.repo.ventas(
            fecha_desde,
            fecha_hasta,
            grupo_sql,
            categoria_id,
            producto_id,
            incluir_montos=rol == "DUENIO",
        )
        totales: dict[date, Decimal] = defaultdict(lambda: Decimal("0"))
        if rol == "DUENIO":
            for fila in filas:
                totales[fila["periodo"]] += fila["monto_total"]
        ordenadas = sorted(
            filas, key=lambda f: (f["periodo"], -f["cantidad_vendida"], f["producto_id"])
        )
        posiciones: dict[date, int] = defaultdict(int)
        salida = []
        for fila in ordenadas:
            periodo = fila["periodo"]
            posiciones[periodo] += 1
            item = {
                "periodo": periodo,
                "producto_id": fila["producto_id"],
                "producto": fila["producto"],
                "categoria": fila["categoria"],
                "cantidad_vendida": fila["cantidad_vendida"],
                "ranking": posiciones[periodo],
            }
            if rol == "DUENIO":
                total = totales[periodo]
                item["monto_total"] = fila["monto_total"]
                item["participacion"] = fila["monto_total"] * 100 / total if total else Decimal("0")
            else:
                item["cantidad_pedidos"] = fila["cantidad_pedidos"]
            salida.append(item)
        return salida

    async def rentabilidad_estimada(
        self,
        *,
        rol: str,
        fecha_desde: date,
        fecha_hasta: date,
        categoria_id: int | None = None,
        producto_id: int | None = None,
    ) -> list[dict]:
        """Usa precios historicos y costos actuales: no es rentabilidad historica exacta.

        costo_unitario=0 se respeta como dato almacenado; el esquema no distingue
        un costo genuinamente cero de uno aun no cargado.
        """
        validar_rol(rol, financiero=True)
        validar_periodo(fecha_desde, fecha_hasta)
        filas = await self.repo.rentabilidad(fecha_desde, fecha_hasta, categoria_id, producto_id)
        resultado = []
        for fila in filas:
            ingreso = fila["ingreso_estimado"]
            costo = fila["costo_estimado"]
            margen = ingreso - costo
            resultado.append(
                {
                    "tipo": "RENTABILIDAD_ESTIMADA",
                    "producto_id": fila["producto_id"],
                    "producto": fila["producto"],
                    "unidades_vendidas": fila["unidades_vendidas"],
                    "ingreso_estimado": ingreso,
                    "costo_estimado": costo,
                    "margen_estimado": margen,
                    "porcentaje_margen": margen * 100 / ingreso if ingreso else Decimal("0"),
                }
            )
        return resultado
