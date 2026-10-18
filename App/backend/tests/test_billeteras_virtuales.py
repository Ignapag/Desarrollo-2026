"""Mercado Pago permanece deshabilitado, incluso si existen credenciales históricas.

Sustituye los antiguos tests de simulación aprobada: ya no es un medio operativo.
"""

from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from app.errores import ReglaDeNegocio
from app.modules.pagos.application.servicio_pagos import ServicioPagos
from app.modules.pagos.infrastructure.cliente_billetera import ClienteMercadoPago


@pytest.mark.parametrize("token", [None, "", "credencial-historica"])
async def test_adapter_no_crea_preferencias_ni_aprueba_con_ninguna_configuracion(token):
    cliente = ClienteMercadoPago(access_token=token)
    assert not cliente.esta_configurado
    with pytest.raises(ReglaDeNegocio, match="deshabilitada"):
        await cliente.crear_preferencia(pedido_id=1, numero_pedido=1001, monto=Decimal(100))
    with pytest.raises(ReglaDeNegocio, match="deshabilitada"):
        await cliente.consultar_pago("sim_123")


async def test_servicio_no_acepta_inicio_ni_webhook_aunque_adapter_diga_aprobado():
    repo = AsyncMock()
    proveedor = AsyncMock()
    servicio = ServicioPagos(AsyncMock(), repo, cliente_mp=proveedor)
    with pytest.raises(ReglaDeNegocio, match="deshabilitada"):
        await servicio.iniciar_cobro_digital(1)
    with pytest.raises(ReglaDeNegocio, match="deshabilitada"):
        await servicio.procesar_webhook_mercadopago("falso")
    assert not repo.mock_calls
    assert not proveedor.mock_calls
