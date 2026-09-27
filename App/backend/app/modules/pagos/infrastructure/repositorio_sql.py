"""Repositorio del módulo de pagos con SQL directo y consultas parametrizadas."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from app.core.db import UnidadDeTrabajo
from app.modules.pagos.domain.entidades import (
    EstadoPago,
    MetodoPago,
    Pago,
    TipoPago,
)


def _mapear_pago(fila: dict) -> Pago:
    """Convierte un registro de PostgreSQL en una entidad de dominio Pago."""
    return Pago(
        id=fila["id"],
        pedido_id=fila["pedido_id"],
        cierre_caja_id=fila.get("cierre_caja_id"),
        tipo=TipoPago(fila["tipo"]),
        metodo_pago=MetodoPago(fila["metodo_pago"]),
        monto=Decimal(str(fila["monto"])),
        propina=Decimal(str(fila["propina"])),
        estado=EstadoPago(fila["estado"]),
        referencia_externa=fila.get("referencia_externa"),
        registrado_por=fila.get("registrado_por"),
        registrado_en=fila["registrado_en"],
        conciliado_en=fila.get("conciliado_en"),
        motivo=fila.get("motivo"),
    )


class RepositorioPagosSQL:
    def __init__(self, uow: UnidadDeTrabajo) -> None:
        self.uow = uow

    async def obtener_pedido(self, pedido_id: int) -> dict | None:
        """Obtiene datos esenciales del pedido para lectura (sin bloqueo)."""
        sql = """
            SELECT id, numero, cliente_id, tipo_entrega, canal, estado, total
            FROM pedido
            WHERE id = %s
        """
        return await self.uow.uno(sql, (pedido_id,))

    async def obtener_pedido_para_actualizar(self, pedido_id: int) -> dict | None:
        """Obtiene el pedido adquiriendo un bloqueo pesimista de fila (FOR UPDATE).

        Garantiza que dos pagos o cancelaciones concurrentes sobre el mismo pedido
        se ejecuten en serie, evitando doble cobro o carreras de estado.
        """
        sql = """
            SELECT id, numero, cliente_id, tipo_entrega, canal, estado, total
            FROM pedido
            WHERE id = %s
            FOR UPDATE
        """
        return await self.uow.uno(sql, (pedido_id,))

    async def total_pagado_por_pedido(self, pedido_id: int) -> Decimal:
        """Calcula el monto neto ya imputado al pedido (cobros menos devoluciones)."""
        sql = """
            SELECT COALESCE(SUM(
                CASE WHEN tipo = 'COBRO' THEN monto ELSE -monto END
            ), 0) AS total_pagado
            FROM pago
            WHERE pedido_id = %s AND estado <> 'ANULADO'
        """
        valor = await self.uow.valor(sql, (pedido_id,))
        return Decimal(str(valor)) if valor is not None else Decimal("0.00")

    async def existe_pago_con_referencia(self, referencia_externa: str) -> bool:
        """Verifica si ya existe un cobro registrado con la misma referencia externa."""
        sql = """
            SELECT EXISTS (
                SELECT 1 FROM pago
                WHERE referencia_externa = %s AND estado <> 'ANULADO'
            )
        """
        return bool(await self.uow.valor(sql, (referencia_externa,)))

    async def registrar_pago(
        self,
        pedido_id: int,
        tipo: TipoPago,
        metodo_pago: MetodoPago,
        monto: Decimal,
        propina: Decimal,
        estado: EstadoPago,
        referencia_externa: str | None = None,
        registrado_por: int | None = None,
        conciliado_en: datetime | None = None,
        motivo: str | None = None,
    ) -> Pago:
        """Inserta un pago de forma parametrizada y retorna la entidad creada."""
        sql = """
            INSERT INTO pago (
                pedido_id, tipo, metodo_pago, monto, propina,
                estado, referencia_externa, registrado_por, registrado_en,
                conciliado_en, motivo
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, now(), %s, %s)
            RETURNING id, pedido_id, cierre_caja_id, tipo, metodo_pago,
                      monto, propina, estado, referencia_externa,
                      registrado_por, registrado_en, conciliado_en, motivo
        """
        fila = await self.uow.uno(
            sql,
            (
                pedido_id,
                tipo.value,
                metodo_pago.value,
                monto,
                propina,
                estado.value,
                referencia_externa,
                registrado_por,
                conciliado_en,
                motivo,
            ),
        )
        if fila is None:
            raise RuntimeError("No se pudo registrar el pago en la base de datos")
        return _mapear_pago(fila)

    async def cambiar_estado_pedido(
        self,
        pedido_id: int,
        estado: str,
        *,
        usuario_id: int | None = None,
        observacion: str | None = None,
    ) -> None:
        """Cambia el estado del pedido y registra el historial en pedido_estado_historial (RF-01)."""
        anterior = await self.uow.valor("SELECT estado FROM pedido WHERE id = %s", (pedido_id,))

        marca = {
            "CONFIRMADO": ", confirmado_en = now()",
            "ENTREGADO": ", entregado_en = now()",
        }.get(estado, "")
        await self.uow.ejecutar(
            f"UPDATE pedido SET estado = %s {marca} WHERE id = %s", (estado, pedido_id)
        )
        await self.uow.ejecutar(
            """
            INSERT INTO pedido_estado_historial
                (pedido_id, estado_anterior, estado_nuevo, usuario_id, observacion)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (pedido_id, anterior, estado, usuario_id, observacion),
        )

    async def obtener_pago_por_id(self, pago_id: int) -> Pago | None:
        """Busca un pago por su identificador primario."""
        sql = """
            SELECT id, pedido_id, cierre_caja_id, tipo, metodo_pago,
                   monto, propina, estado, referencia_externa,
                   registrado_por, registrado_en, conciliado_en, motivo
            FROM pago
            WHERE id = %s
        """
        fila = await self.uow.uno(sql, (pago_id,))
        return _mapear_pago(fila) if fila else None

    async def listar_pagos_por_pedido(self, pedido_id: int) -> list[Pago]:
        """Obtiene la lista de pagos y movimientos asociados a un pedido."""
        sql = """
            SELECT id, pedido_id, cierre_caja_id, tipo, metodo_pago,
                   monto, propina, estado, referencia_externa,
                   registrado_por, registrado_en, conciliado_en, motivo
            FROM pago
            WHERE pedido_id = %s
            ORDER BY registrado_en ASC
        """
        filas = await self.uow.todos(sql, (pedido_id,))
        return [_mapear_pago(f) for f in filas]
