"""Endpoints protegidos de pagos, cobro digital, conciliacion y webhooks."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.core.dependencias import IpCliente
from app.errores import SinPermiso
from app.modules.pagos.presentation.dependencias import ServicioConciliacionDep, ServicioPagosDep
from app.modules.pagos.presentation.esquemas import (
    AnularPagoEntrada,
    ConciliarLoteEntrada,
    ConciliarPagoEntrada,
    EstadoFinancieroPedidoSalida,
    PagoOperacionSalida,
    PagoSalida,
    RegistrarDevolucionEntrada,
    RegistrarPagoEfectivoEntrada,
    RegistrarTransferenciaEntrada,
    ResultadoCobroEfectivoSalida,
    ResultadoConciliacionLoteSalida,
)
from app.modules.pedidos.presentation.dependencias import ServicioPedidosDep
from app.modules.pedidos.presentation.esquemas import PedidoSalida
from app.modules.usuarios.domain.entidades import ClaimsSesion, Rol
from app.modules.usuarios.presentation.dependencias import requiere_permiso

PermisoPagosRegistrar = Annotated[ClaimsSesion, Depends(requiere_permiso("pagos", "registrar"))]
PermisoPagosVer = Annotated[ClaimsSesion, Depends(requiere_permiso("pagos", "ver", cliente=True))]
PermisoPagosConciliar = Annotated[ClaimsSesion, Depends(requiere_permiso("pagos", "conciliar"))]
PermisoPagosCorregir = Annotated[ClaimsSesion, Depends(requiere_permiso("pagos", "corregir"))]

router = APIRouter(prefix="/api/pagos", tags=["pagos"])


@router.post(
    "/efectivo",
    response_model=ResultadoCobroEfectivoSalida,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar cobro en efectivo",
)
async def registrar_pago_efectivo(
    datos: RegistrarPagoEfectivoEntrada,
    sesion: PermisoPagosRegistrar,
    servicio: ServicioPagosDep,
    pedidos: ServicioPedidosDep,
    incluir_pedido: bool = False,
    ip: IpCliente = None,
) -> ResultadoCobroEfectivoSalida:
    """Registra el cobro en efectivo de un pedido de forma concurrente-segura.

    - Bloqueo pesimista sobre el pedido (FOR UPDATE) para prevenir dobles cobros simultáneos.
    - Si `conciliar_inmediato` es True, el pago queda en estado `CONCILIADO` inmediatamente.
    - Registra dinero sin cambiar el estado físico del pedido.
    - Registra el evento en auditoría con la IP del cliente.
    """
    if datos.conciliar_inmediato and not sesion.puede("pagos.conciliar"):
        raise SinPermiso("Conciliar el cobro requiere permiso de conciliacion")
    resultado = await servicio.registrar_pago_efectivo(
        pedido_id=datos.pedido_id,
        monto_recibido=datos.monto_recibido,
        monto_a_pagar=datos.monto_a_pagar,
        propina=datos.propina,
        conciliar_inmediato=datos.conciliar_inmediato,
        registrado_por=sesion.usuario_id,
        clave_operacion=str(datos.clave_operacion),
        ip_cliente=ip,
    )
    salida = ResultadoCobroEfectivoSalida.desde_dominio(resultado)
    if incluir_pedido:
        salida.pedido = PedidoSalida.para_sesion(await pedidos.detalle(datos.pedido_id), sesion)
    return salida


@router.post(
    "/transferencia",
    response_model=PagoOperacionSalida,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar transferencia para revisión humana",
)
async def registrar_transferencia(
    datos: RegistrarTransferenciaEntrada,
    sesion: PermisoPagosRegistrar,
    servicio: ServicioPagosDep,
    conciliacion: ServicioConciliacionDep,
    pedidos: ServicioPedidosDep,
    incluir_pedido: bool = False,
    confirmar_ingreso: bool = False,
    ip: IpCliente = None,
) -> PagoOperacionSalida:
    if confirmar_ingreso and not sesion.puede("pagos.conciliar"):
        raise SinPermiso("Confirmar el ingreso requiere permiso de conciliacion")
    pago = await servicio.registrar_transferencia(
        pedido_id=datos.pedido_id,
        monto=datos.monto,
        comprobante=datos.comprobante,
        registrado_por=sesion.usuario_id,
        ip_cliente=ip,
        clave_operacion=str(datos.clave_operacion),
    )
    if confirmar_ingreso:
        # Sólo personal autorizado; registrar y acreditar comparten transacción.
        # El valor por defecto conserva el circuito pendiente del comprobante.
        pago = await conciliacion.conciliar_pago(
            pago.id,
            conciliar_por=sesion.usuario_id,
            ip_cliente=ip,
        )
    salida = PagoOperacionSalida.desde_dominio(pago)
    if incluir_pedido:
        salida.pedido = PedidoSalida.para_sesion(await pedidos.detalle(pago.pedido_id), sesion)
    return salida


@router.get(
    "/pedido/{pedido_id}/estado",
    response_model=EstadoFinancieroPedidoSalida,
    summary="Consultar balance y estado financiero de un pedido",
)
async def estado_financiero_pedido(
    pedido_id: int,
    sesion: PermisoPagosVer,
    servicio: ServicioPagosDep,
) -> EstadoFinancieroPedidoSalida:
    """Retorna el balance de pagos, saldo pendiente, detalle de pagos y si el pedido \
está saldado."""
    estado = await servicio.obtener_estado_financiero(
        pedido_id,
        cliente_usuario_id=sesion.usuario_id if sesion.rol == Rol.CLIENTE else None,
    )
    return EstadoFinancieroPedidoSalida.desde_dominio(estado)


@router.get(
    "/pedido/{pedido_id}",
    response_model=list[PagoSalida],
    summary="Listar pagos de un pedido",
)
async def listar_pagos_pedido(
    pedido_id: int,
    sesion: PermisoPagosVer,
    servicio: ServicioPagosDep,
) -> list[PagoSalida]:
    """Retorna el historial completo de pagos y egresos/devoluciones asociados a un pedido."""
    pagos = await servicio.listar_pagos_por_pedido(
        pedido_id,
        cliente_usuario_id=sesion.usuario_id if sesion.rol == Rol.CLIENTE else None,
    )
    return [PagoSalida.desde_dominio(p) for p in pagos]


@router.get(
    "/pendientes-conciliacion",
    response_model=list[PagoSalida],
    summary="Listar pagos pendientes de conciliación",
)
async def listar_pendientes_conciliacion(
    _sesion: PermisoPagosConciliar,
    servicio: ServicioConciliacionDep,
) -> list[PagoSalida]:
    """Recupera la lista de cobros que aún se encuentran pendientes de acreditación o arqueo."""
    pagos = await servicio.listar_pendientes_conciliacion()
    return [PagoSalida.desde_dominio(p) for p in pagos]


@router.post(
    "/conciliar-lote",
    response_model=ResultadoConciliacionLoteSalida,
    summary="Conciliar múltiples pagos en lote",
)
async def conciliar_lote(
    datos: ConciliarLoteEntrada,
    sesion: PermisoPagosConciliar,
    servicio: ServicioConciliacionDep,
    ip: IpCliente = None,
) -> ResultadoConciliacionLoteSalida:
    """Concilia de forma masiva una lista de pagos pendientes (ej. arqueo diario o extracto)."""
    resultado = await servicio.conciliar_lote(
        pago_ids=datos.pago_ids,
        conciliar_por=sesion.usuario_id,
        ip_cliente=ip,
    )
    return ResultadoConciliacionLoteSalida(**resultado)


@router.post(
    "/devolucion",
    response_model=PagoOperacionSalida,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar egreso o devolución sobre un pedido",
)
async def registrar_devolucion(
    datos: RegistrarDevolucionEntrada,
    sesion: PermisoPagosCorregir,
    servicio: ServicioConciliacionDep,
    pedidos: ServicioPedidosDep,
    incluir_pedido: bool = False,
    ip: IpCliente = None,
) -> PagoOperacionSalida:
    """Registra una devolución o reintegro (C-11).

    - Valida que el motivo esté explicitado.
    - Verifica que el monto a devolver no supere el total neto abonado en el pedido.
    - Asienta el pago con tipo DEVOLUCION y estado CONCILIADO.
    - Registra el evento en auditoría.
    """
    devolucion = await servicio.registrar_devolucion(
        pedido_id=datos.pedido_id,
        monto=datos.monto,
        motivo=datos.motivo,
        metodo_pago=datos.metodo_pago,
        registrado_por=sesion.usuario_id,
        clave_operacion=str(datos.clave_operacion),
        ip_cliente=ip,
    )
    salida = PagoOperacionSalida.desde_dominio(devolucion)
    if incluir_pedido:
        salida.pedido = PedidoSalida.para_sesion(
            await pedidos.detalle(devolucion.pedido_id), sesion
        )
    return salida


@router.get(
    "/{pago_id}",
    response_model=PagoSalida,
    summary="Obtener detalle de un pago",
)
async def obtener_pago(
    pago_id: int,
    sesion: PermisoPagosVer,
    servicio: ServicioPagosDep,
) -> PagoSalida:
    """Obtiene los datos de un pago registrado por su identificador primario."""
    pago = await servicio.obtener_pago(
        pago_id,
        cliente_usuario_id=sesion.usuario_id if sesion.rol == Rol.CLIENTE else None,
    )
    return PagoSalida.desde_dominio(pago)


@router.post(
    "/{pago_id}/conciliar",
    response_model=PagoOperacionSalida,
    summary="Conciliar un pago individual",
)
async def conciliar_pago(
    pago_id: int,
    sesion: PermisoPagosConciliar,
    servicio: ServicioConciliacionDep,
    pedidos: ServicioPedidosDep,
    incluir_pedido: bool = False,
    datos: ConciliarPagoEntrada | None = None,
    ip: IpCliente = None,
) -> PagoOperacionSalida:
    """Marca un pago individual como CONCILIADO.

    La acreditación humana no cambia el estado físico del pedido.
    """
    conciliar_por = sesion.usuario_id
    comprobante = datos.comprobante if datos else None
    pago = await servicio.conciliar_pago(
        pago_id=pago_id,
        conciliar_por=conciliar_por,
        comprobante=comprobante,
        ip_cliente=ip,
    )
    salida = PagoOperacionSalida.desde_dominio(pago)
    if incluir_pedido:
        salida.pedido = PedidoSalida.para_sesion(await pedidos.detalle(pago.pedido_id), sesion)
    return salida


@router.post(
    "/{pago_id}/anular",
    response_model=PagoSalida,
    summary="Anular un pago pendiente",
)
async def anular_pago(
    pago_id: int,
    datos: AnularPagoEntrada,
    sesion: PermisoPagosCorregir,
    servicio: ServicioConciliacionDep,
    ip: IpCliente = None,
) -> PagoSalida:
    """Anula un pago pendiente registrando el motivo de anulación y auditoría.

    Los pagos ya conciliados no pueden anularse; debe registrarse una devolución.
    """
    pago = await servicio.anular_pago(
        pago_id=pago_id,
        motivo=datos.motivo,
        anulado_por=sesion.usuario_id,
        ip_cliente=ip,
    )
    return PagoSalida.desde_dominio(pago)
