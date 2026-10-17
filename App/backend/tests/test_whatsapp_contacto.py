"""Datos declarados del checkout separados de la identidad firmada de WhatsApp."""

from uuid import uuid4

import httpx
import pytest
from pydantic import ValidationError

from app.errores import DatosInvalidos
from app.modules.whatsapp.application.servicio_bot import ServicioBot
from app.modules.whatsapp.domain.mensajes import hash_referencia
from app.modules.whatsapp.infrastructure.repositorio_sql import RepositorioBotSQL
from app.modules.whatsapp.presentation.dependencias import construir_servicio
from app.modules.whatsapp.presentation.esquemas import BorradorEntrada
from tests.test_whatsapp_bd import datos_prueba
from tests.test_whatsapp_http import aplicacion


def datos_contacto():
    return {"nombre": "Ana", "apellido": "Pérez", "telefono": "542215550000"}


def test_checkout_acepta_contacto_y_recorta_nombres():
    datos = BorradorEntrada(
        contacto={**datos_contacto(), "nombre": "  Ana  "},
        items=[{"producto_id": 1, "cantidad": 1}],
    )
    assert datos.model_dump()["contacto"] == datos_contacto()


@pytest.mark.parametrize(
    "campo,valor",
    [("nombre", "   "), ("apellido", ""), ("nombre", "a" * 81), ("telefono", "123")],
)
def test_checkout_rechaza_contacto_incompleto_o_invalido(campo, valor):
    with pytest.raises(ValidationError):
        BorradorEntrada(
            contacto={**datos_contacto(), campo: valor},
            items=[{"producto_id": 1, "cantidad": 1}],
        )


@pytest.mark.parametrize(
    "contacto",
    [
        {}, [], {**datos_contacto(), "nombre": "   "},
        {**datos_contacto(), "telefono": 542215550000},
        {**datos_contacto(), "whatsapp_verificado": "5492215550001"},
    ],
)
async def test_servicio_rechaza_contacto_invalido_antes_de_persistir(contacto):
    with pytest.raises(DatosInvalidos):
        await ServicioBot(None, None).crear_borrador(None, {"contacto": contacto})


async def test_checkout_publico_con_contacto_registra_un_solo_pedido_por_whatsapp(uow):
    _, item = await datos_prueba(uow)
    servicio = construir_servicio(uow)
    app = aplicacion()
    app.dependency_overrides[construir_servicio] = lambda: servicio
    clientes_antes = await uow.valor("SELECT count(*) FROM cliente")
    pedidos_antes = await uow.valor("SELECT count(*) FROM pedido")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as navegador:
        respuesta = await navegador.post("/api/whatsapp/borradores", json={
            "items": [item], "contacto": datos_contacto(),
            "tipo_entrega": "RETIRO", "metodo_pago": "EFECTIVO",
        })
    assert respuesta.status_code == 201
    assert await uow.valor("SELECT count(*) FROM cliente") == clientes_antes
    assert await uow.valor("SELECT count(*) FROM pedido") == pedidos_antes
    borrador = respuesta.json()
    for identificador in ("checkout-primero", "checkout-repetido"):
        await servicio.recibir(identificador, "5492215550000", borrador["mensaje"])
        await servicio.procesar(identificador, {"accion": "consulta", "argumentos": {}})
    assert await uow.valor("SELECT count(*) FROM pedido") == pedidos_antes + 1
    fila = await uow.uno(
        "SELECT b.contacto,c.nombre,c.telefono_contacto,c.whatsapp_verificado,c.usuario_id "
        "FROM whatsapp_borrador b JOIN cliente c ON c.id=b.cliente_id "
        "WHERE b.referencia_hash=%s", (hash_referencia(borrador["referencia"][3:]),),
    )
    assert fila == {
        "contacto": datos_contacto(), "nombre": "Ana Pérez",
        "telefono_contacto": "542215550000", "whatsapp_verificado": "5492215550000",
        "usuario_id": None,
    }


async def test_contacto_no_verifica_identidad_hasta_recibir_whatsapp(uow):
    repo = RepositorioBotSQL(uow)
    referencia = uuid4().hex
    b = await repo.crear_borrador(
        referencia, None, {"items": [], "contacto": datos_contacto()}
    )
    assert b["cliente_id"] is None and b["telefono"] is None
    assert b["contacto"] == datos_contacto()

    vinculado = await repo.conversacion(
        "5492215550001", referencia, bloquear=True, nombre_remitente="Perfil de WhatsApp"
    )
    cliente = await uow.uno("SELECT * FROM cliente WHERE id=%s", (vinculado["cliente_id"],))
    assert cliente["nombre"] == "Ana Pérez"
    assert cliente["telefono_contacto"] == "542215550000"
    assert cliente["telefono_whatsapp"] == "5492215550001"
    assert cliente["whatsapp_verificado"] == "5492215550001"
    assert cliente["usuario_id"] is None
    assert await repo.conversacion("542215550000", referencia, bloquear=True) is None


async def test_nuevo_contacto_actualiza_solo_al_cliente_del_remitente_real(uow):
    repo = RepositorioBotSQL(uow)
    otro_cliente_id = await uow.valor(
        "INSERT INTO cliente (nombre,telefono_whatsapp,whatsapp_verificado) "
        "VALUES ('Otra persona','542215550000','542215550000') RETURNING id"
    )
    cliente_id = await uow.valor(
        "INSERT INTO cliente (nombre,telefono_whatsapp,whatsapp_verificado) "
        "VALUES ('Anterior','5492215550001','5492215550001') RETURNING id"
    )
    referencia = uuid4().hex
    await repo.crear_borrador(referencia, None, {"items": [], "contacto": datos_contacto()})
    vinculado = await repo.conversacion("5492215550001", referencia, bloquear=True)
    assert vinculado["cliente_id"] == cliente_id
    assert await uow.valor("SELECT nombre FROM cliente WHERE id=%s", (cliente_id,)) == "Ana Pérez"
    assert await uow.valor(
        "SELECT nombre FROM cliente WHERE id=%s", (otro_cliente_id,)
    ) == "Otra persona"
