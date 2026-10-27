"""Fecha contable y cortes de Caja independientes de la zona del servidor y SQL."""

from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

import pytest

from app.modules.pagos.application.servicio_caja import ServicioCaja
from app.modules.pagos.domain import entidades
from app.modules.pagos.domain.entidades import TurnoCierre, determinar_turno_y_ventana
from app.modules.pagos.infrastructure.repositorio_caja_sql import RepositorioCajaSQL


def test_madrugada_utc_conserva_fecha_contable_noche_argentina():
    turno, fecha, desde, hasta = determinar_turno_y_ventana(
        datetime(2026, 10, 28, 6, 30, tzinfo=UTC)
    )
    assert turno == TurnoCierre.NOCHE
    assert fecha == date(2026, 10, 27)
    assert desde.isoformat() == "2026-10-27T17:00:00-03:00"
    assert hasta.isoformat() == "2026-10-28T04:59:59-03:00"


def test_turno_actual_convierte_reloj_utc_a_zona_del_negocio(monkeypatch):
    class RelojUTC(datetime):
        @classmethod
        def now(cls, tz=None):
            instante = cls(2026, 10, 28, 6, 30, tzinfo=UTC)
            return instante.astimezone(tz) if tz else instante.replace(tzinfo=None)

    monkeypatch.setattr(entidades, "datetime", RelojUTC)
    turno, fecha, desde, _ = determinar_turno_y_ventana()
    assert turno == TurnoCierre.NOCHE
    assert fecha == date(2026, 10, 27)
    assert desde.utcoffset() == timedelta(hours=-3)


@pytest.mark.parametrize("zona_sql", ["UTC", "Asia/Tokyo", "America/Argentina/Buenos_Aires"])
async def test_consolidado_y_cierre_respetan_hora_argentina_con_cualquier_zona_sql(uow, zona_sql):
    await uow.valor("SELECT set_config('TimeZone', %s, true)", (zona_sql,))
    cliente = await uow.valor(
        "INSERT INTO cliente (nombre,telefono_whatsapp) VALUES ('Zona caja',%s) RETURNING id",
        (uuid4().hex,),
    )
    pedido = await uow.valor(
        "INSERT INTO pedido (cliente_id,tipo_entrega,subtotal,total) "
        "VALUES (%s,'RETIRO',300,300) RETURNING id", (cliente,),
    )
    pago_mediodia = await uow.valor(
        "INSERT INTO pago (pedido_id,metodo_pago,monto,estado,registrado_en,conciliado_en) "
        "VALUES (%s,'EFECTIVO',100,'CONCILIADO',"
        "'2199-10-27 16:00:00-03','2199-10-27 16:00:00-03') RETURNING id", (pedido,),
    )
    pago_noche = await uow.valor(
        "INSERT INTO pago (pedido_id,metodo_pago,monto,estado,registrado_en,conciliado_en) "
        "VALUES (%s,'EFECTIVO',200,'CONCILIADO',"
        "'2199-10-28 03:30:00-03','2199-10-28 03:30:00-03') RETURNING id", (pedido,),
    )
    servicio = ServicioCaja(uow, RepositorioCajaSQL(uow))
    mediodia = await servicio.consolidar_turno(date(2199, 10, 27), TurnoCierre.MEDIODIA)
    noche = await servicio.consolidar_turno(date(2199, 10, 27), TurnoCierre.NOCHE)
    assert mediodia.total_general == 100
    assert noche.total_general == 200
    assert mediodia.desde.isoformat() == "2199-10-27T10:00:00-03:00"
    assert noche.hasta.isoformat() == "2199-10-28T04:59:59-03:00"
    cierre = await servicio.generar_resumen_cierre(date(2199, 10, 27), TurnoCierre.MEDIODIA)
    assert (
        await uow.valor("SELECT cierre_caja_id FROM pago WHERE id=%s", (pago_mediodia,))
        == cierre.id
    )
    assert await uow.valor("SELECT cierre_caja_id FROM pago WHERE id=%s", (pago_noche,)) is None
