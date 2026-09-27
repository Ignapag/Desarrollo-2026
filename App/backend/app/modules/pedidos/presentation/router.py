"""Endpoints para crear, consultar y avanzar pedidos."""

from fastapi import APIRouter, status

from app.errores import DatosInvalidos
from app.modules.pedidos.application.servicio_pedidos import ItemNuevoPedido
from app.modules.pedidos.presentation.dependencias import ServicioPedidosDep
from app.modules.pedidos.presentation.esquemas import (
    CambiarEstadoEntrada,
    PedidoCrear,
    PedidoSalida,
)
from app.modules.usuarios.domain.entidades import Rol
from app.modules.usuarios.presentation.dependencias import PersonalInterno, Sesion

router = APIRouter(prefix="/api/pedidos", tags=["pedidos"])


@router.post("", response_model=PedidoSalida, status_code=status.HTTP_201_CREATED)
async def crear_pedido(
    datos: PedidoCrear, sesion: Sesion, servicio: ServicioPedidosDep
) -> PedidoSalida:
    cliente_id = sesion.usuario_id if sesion.rol == Rol.CLIENTE else datos.cliente_id
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
    )
    return PedidoSalida(**fila)


@router.get("", response_model=list[PedidoSalida])
async def listar_pedidos(sesion: Sesion, servicio: ServicioPedidosDep) -> list[PedidoSalida]:
    cliente_id = sesion.usuario_id if sesion.rol == Rol.CLIENTE else None
    return [PedidoSalida(**fila) for fila in await servicio.listar(cliente_id=cliente_id)]


@router.patch("/{pedido_id}/estado", response_model=PedidoSalida)
async def cambiar_estado(
    pedido_id: int,
    datos: CambiarEstadoEntrada,
    sesion: PersonalInterno,
    servicio: ServicioPedidosDep,
) -> PedidoSalida:
    fila = await servicio.cambiar_estado(
        pedido_id, datos.estado, usuario_id=sesion.usuario_id
    )
    return PedidoSalida(**fila)
