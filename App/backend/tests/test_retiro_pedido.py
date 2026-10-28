"""Reglas de retiro con prueba de pago leída bajo el bloqueo del pedido."""

from copy import deepcopy

import pytest
from pydantic import ValidationError

from app.errores import ReglaDeNegocio
from app.modules.pedidos.application.servicio_pedidos import ServicioPedidos
from app.modules.pedidos.domain.entidades import EstadoPedido as E
from app.modules.pedidos.presentation.esquemas import CambiarEstadoEntrada


class RepoRetiro:
    def __init__(self, metodo="TRANSFERENCIA", aprobado=False, **datos):
        self.pedido = {
            "id": 7, "estado": "LISTO", "tipo_entrega": "RETIRO", "version": 3,
            "metodo_pago_acordado": metodo, "puede_preparar": aprobado,
            "pagos": [{"id": 9, "estado": "CONCILIADO" if aprobado else "PENDIENTE"}],
            **datos,
        }
        self.escrituras = 0
        self.bloqueado = False

    async def obtener(self, pedido_id, *, bloquear=False):
        assert pedido_id == 7 and bloquear
        self.bloqueado = True
        return deepcopy(self.pedido)

    async def cambiar_estado(self, pedido_id, nuevo, usuario_id, **kwargs):
        assert self.bloqueado
        self.escrituras += 1
        self.pedido.update(estado=nuevo.value, version=self.pedido["version"] + 1)
        return deepcopy(self.pedido)


class StockSinCambios:
    async def procesar(self, *args):
        pytest.fail("Retirar no debe volver a consumir stock")


async def retirar(repo):
    return await ServicioPedidos(repo, StockSinCambios()).cambiar_estado(
        7, E.ENTREGADO, usuario_id=1, version_esperada=3, estado_esperado="LISTO",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("metodo,aprobado", [
    ("TRANSFERENCIA", True), ("EFECTIVO", False), ("EFECTIVO", True),
])
async def test_retiro_pagado_o_en_efectivo_no_crea_cobros_ni_duplica_stock(metodo, aprobado):
    repo = RepoRetiro(metodo, aprobado)
    pagos = deepcopy(repo.pedido["pagos"])
    result = await retirar(repo)
    assert result["estado"] == "ENTREGADO"
    assert result["version"] == 4
    assert repo.escrituras == 1
    assert repo.pedido["pagos"] == pagos
    # Repetir el comando con la versión previa no entrega ni cobra por segunda vez.
    with pytest.raises(ReglaDeNegocio, match="pedido cambio"):
        await retirar(repo)
    assert repo.escrituras == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("aprobado", [False, None])
async def test_transferencia_sin_prueba_de_cobertura_no_permite_retirar(aprobado):
    repo = RepoRetiro("TRANSFERENCIA", aprobado)
    with pytest.raises(ReglaDeNegocio, match="retiro requiere pago completo"):
        await retirar(repo)
    assert repo.pedido["estado"] == "LISTO"
    assert repo.escrituras == 0


@pytest.mark.asyncio
async def test_pago_no_salta_cocina_y_efectivo_no_salta_el_viaje_delivery():
    for datos in [{"estado": "PENDIENTE"}, {"tipo_entrega": "DELIVERY"}]:
        repo = RepoRetiro("EFECTIVO", True, **datos)
        with pytest.raises(ReglaDeNegocio):
            await ServicioPedidos(repo, StockSinCambios()).cambiar_estado(
                7, E.ENTREGADO, usuario_id=1,
            )
        assert repo.escrituras == 0


def test_el_cliente_no_puede_enviar_su_propia_prueba_de_pago():
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        CambiarEstadoEntrada.model_validate({
            "estado": "ENTREGADO", "version_esperada": 3, "puede_preparar": True,
        })
