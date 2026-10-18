"""Endpoints para crear, consultar y avanzar pedidos."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.errores import DatosInvalidos, SinPermiso
from app.modules.pedidos.application.servicio_pedidos import ItemNuevoPedido
from app.modules.pedidos.presentation.dependencias import ServicioPedidosDep
from app.modules.pedidos.presentation.esquemas import (
    CambiarEstadoEntrada,
    EditarOperacionEntrada,
    PedidoCrear,
    PedidoSalida,
)
from app.modules.usuarios.domain.entidades import ClaimsSesion, Rol
from app.modules.usuarios.presentation.dependencias import Sesion, requiere_rol

router = APIRouter(prefix="/api/pedidos", tags=["pedidos"])
SesionPedidos = Annotated[
    ClaimsSesion,
    Depends(requiere_rol(Rol.ADMINISTRADOR, Rol.DUENIO, Rol.EMPLEADO, Rol.CLIENTE)),
]
GestionPedidos = Annotated[
    ClaimsSesion,
    Depends(requiere_rol(Rol.ADMINISTRADOR, Rol.DUENIO, Rol.EMPLEADO)),
]


@router.post("", response_model=PedidoSalida, status_code=status.HTTP_201_CREATED)
async def crear_pedido(
    datos: PedidoCrear, sesion: SesionPedidos, servicio: ServicioPedidosDep
) -> PedidoSalida:
    cliente_id = (
        await servicio.cliente_para_usuario(sesion.usuario_id)
        if sesion.rol == Rol.CLIENTE
        else datos.cliente_id
    )
    if cliente_id is None:
        raise DatosInvalidos("El personal interno debe indicar cliente_id")
    fila = await servicio.crear(
        cliente_id=cliente_id,
        tipo_entrega=datos.tipo_entrega,
        direccion_id=datos.direccion_id,
        direccion_nueva=(
            datos.direccion_nueva.model_dump() if datos.direccion_nueva is not None else None
        ),
        observaciones=datos.observaciones,
        items=[ItemNuevoPedido(**item.model_dump()) for item in datos.items],
        metodo_pago_acordado=datos.metodo_pago_acordado,
    )
    return PedidoSalida(**fila)


@router.get("", response_model=list[PedidoSalida])
async def listar_pedidos(
    sesion: Sesion,
    servicio: ServicioPedidosDep,
    q: str | None = None,
    estado: str | None = None,
    activos: bool | None = None,
    cliente_id: int | None = Query(default=None, gt=0),
) -> list[PedidoSalida]:
    if sesion.rol == Rol.CLIENTE:
        identidad = await servicio.cliente_para_usuario(sesion.usuario_id)
        if cliente_id is not None and cliente_id != identidad:
            raise SinPermiso("No puede consultar pedidos de otro cliente")
        cliente_id = identidad
    elif sesion.rol == Rol.REPARTIDOR and cliente_id is not None:
        raise SinPermiso("El repartidor sólo puede consultar sus viajes")
    repartidor_id = sesion.usuario_id if sesion.rol == Rol.REPARTIDOR else None
    filas = await servicio.listar(
        cliente_id=cliente_id, repartidor_id=repartidor_id, q=q, estado=estado, activos=activos
    )
    return [PedidoSalida(**fila) for fila in filas]


@router.get("/{pedido_id}", response_model=PedidoSalida)
async def detalle_pedido(
    pedido_id: int, sesion: Sesion, servicio: ServicioPedidosDep
) -> PedidoSalida:
    cliente_id = (
        await servicio.cliente_para_usuario(sesion.usuario_id)
        if sesion.rol == Rol.CLIENTE
        else None
    )
    fila = await servicio.detalle(
        pedido_id,
        cliente_id=cliente_id,
        repartidor_id=sesion.usuario_id if sesion.rol == Rol.REPARTIDOR else None,
    )
    return PedidoSalida(**fila)


@router.patch("/{pedido_id}/operacion", response_model=PedidoSalida)
async def editar_operacion(
    pedido_id: int,
    datos: EditarOperacionEntrada,
    sesion: GestionPedidos,
    servicio: ServicioPedidosDep,
) -> PedidoSalida:
    cambios = datos.model_dump(exclude_unset=True, exclude={"motivo", "version_esperada"})
    if any(
        cambios.get(campo) is None
        for campo in {"tipo_entrega", "metodo_pago_acordado"} & cambios.keys()
    ):
        raise DatosInvalidos("La modalidad y el metodo no pueden estar vacios")
    fila = await servicio.editar_operacion(
        pedido_id,
        cambios=cambios,
        usuario_id=sesion.usuario_id,
        motivo=datos.motivo,
        version_esperada=datos.version_esperada,
        rol=sesion.rol,
    )
    return PedidoSalida(**fila)


@router.patch("/{pedido_id}/estado", response_model=PedidoSalida)
async def cambiar_estado(
    pedido_id: int,
    datos: CambiarEstadoEntrada,
    sesion: GestionPedidos,
    servicio: ServicioPedidosDep,
) -> PedidoSalida:
    fila = await servicio.cambiar_estado(
        pedido_id,
        datos.estado,
        usuario_id=sesion.usuario_id,
        motivo=datos.motivo,
        version_esperada=datos.version_esperada,
        estado_esperado=datos.estado_esperado,
        correccion=datos.correccion,
        tratamiento_stock=datos.tratamiento_stock,
        rol=sesion.rol,
    )
    return PedidoSalida(**fila)
