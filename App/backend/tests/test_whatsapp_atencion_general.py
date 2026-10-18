"""Atención por remitente sin asignar una compra ni acreditar dinero."""

from uuid import uuid4

import pytest

from app.errores import DatosInvalidos, ReglaDeNegocio
from app.modules.whatsapp.presentation.dependencias import construir_servicio
from tests.test_whatsapp_bd import crear_pedido_bot, datos_prueba

TELEFONO = "5492215550000"
AJENO = "5492215550999"


@pytest.mark.parametrize("texto", [
    "Quiero una hamburguesa para una persona",
    "Hola Monu Burger, quiero confirmar mi pedido. Nombre: Persona",
])
def test_persona_en_contexto_de_compra_no_solicita_empleado(texto):
    from app.modules.whatsapp.application.servicio_bot import ServicioBot

    assert not ServicioBot._solicita_personal(texto)


async def enviar(s, identificador, texto="", media=None, telefono=TELEFONO):
    await s.recibir(identificador, telefono, texto, media)
    preparado = await s.preparar(identificador)
    if preparado:
        assert not preparado["interpretar"]
    return await s.procesar(identificador, {"accion": "consulta"})


async def general(uow, motivo):
    return await uow.uno("SELECT * FROM whatsapp_atencion WHERE motivo=%s", (motivo,))


@pytest.mark.parametrize("texto", ["quiero hablar con un empleado", "atención humana", "empleado"])
async def test_primer_contacto_solicita_personal_sin_crear_compra(uow, texto):
    s = construir_servicio(uow)
    antes = await uow.uno(
        "SELECT (SELECT count(*) FROM pedido) pedidos,"
        "(SELECT count(*) FROM cliente) clientes,"
        "(SELECT count(*) FROM whatsapp_borrador) borradores"
    )
    respuesta = await enviar(s, "personal-primer-contacto", texto)
    atencion = await general(uow, "SOLICITUD")
    assert atencion is not None
    assert atencion["referencia_hash"] is None and atencion["telefono"] == TELEFONO
    assert atencion["entrada_id"] == "personal-primer-contacto"
    assert "empleado" in respuesta and "por acá" in respuesta
    assert await uow.uno(
        "SELECT (SELECT count(*) FROM pedido) pedidos,"
        "(SELECT count(*) FROM cliente) clientes,"
        "(SELECT count(*) FROM whatsapp_borrador) borradores"
    ) == antes


@pytest.mark.parametrize("cerrado", ["ENTREGADO", "CANCELADO"])
async def test_personal_tras_pedido_cerrado_no_asocia_ni_reabre_compra(uow, cerrado):
    s, pid = await crear_pedido_bot(uow)
    await uow.ejecutar("UPDATE pedido SET estado=%s WHERE id=%s", (cerrado, pid))
    antes = await uow.uno("SELECT * FROM pedido WHERE id=%s", (pid,))
    respuesta = await enviar(s, "personal-despues-cierre", "necesito un empleado")
    atencion = await general(uow, "SOLICITUD")
    assert atencion is not None and atencion["referencia_hash"] is None
    assert str(antes["numero"]) not in respuesta and "Pedido #" not in respuesta
    assert await uow.uno("SELECT * FROM pedido WHERE id=%s", (pid,)) == antes


async def test_remitente_ajeno_solicita_personal_sin_ver_compras(uow):
    s, pid = await crear_pedido_bot(uow)
    numero = (await s.repo.pedido(pid))["numero"]
    respuesta = await enviar(s, "personal-ajeno", "hablar con una persona", telefono=AJENO)
    atencion = await general(uow, "SOLICITUD")
    assert atencion is not None and atencion["telefono"] == AJENO
    assert atencion["referencia_hash"] is None
    assert str(numero) not in respuesta and "Total" not in respuesta


async def test_solicitudes_repetidas_no_duplican_atencion_pendiente(uow):
    s = construir_servicio(uow)
    primera = await enviar(s, "personal-unico", "quiero hablar con un empleado")
    assert await enviar(s, "personal-unico", "quiero hablar con un empleado") == primera
    await enviar(s, "personal-otro-mensaje", "necesito un empleado")
    assert await uow.valor("SELECT count(*) FROM whatsapp_atencion") == 1


async def test_solicitud_explicita_con_compra_activa_no_depende_del_proveedor(uow):
    s, pid = await crear_pedido_bot(uow)
    antes = await uow.uno("SELECT * FROM pedido WHERE id=%s", (pid,))
    await s.recibir("personal-con-compra", TELEFONO, "quiero hablar con un empleado")
    preparado = await s.preparar("personal-con-compra")
    assert not preparado["interpretar"]
    respuesta = await s.procesar(
        "personal-con-compra", {"accion": "humano", "motivo": "PROVEEDOR"}, preparado["vinculo"]
    )
    atencion = await general(uow, "SOLICITUD")
    assert atencion is not None and atencion["referencia_hash"] is not None
    assert atencion["telefono"] is None
    assert "empleado" in respuesta
    assert await uow.valor("SELECT count(*) FROM whatsapp_atencion WHERE motivo='PROVEEDOR'") == 0
    assert await uow.uno("SELECT * FROM pedido WHERE id=%s", (pid,)) == antes


@pytest.mark.parametrize("con_pedido", [False, True])
async def test_comprobante_general_sin_pedido_transferencia_no_acredita(uow, con_pedido):
    if con_pedido:
        s, pid = await crear_pedido_bot(uow)
        antes = await s.repo.pedido(pid)
    else:
        s = construir_servicio(uow)
    respuesta = await enviar(s, "recibo-general", media="adjunto-general")
    assert await enviar(s, "recibo-general", media="adjunto-general") == respuesta
    await enviar(s, "recibo-general-repetido", media="otro-adjunto-general")
    atenciones = await uow.todos("SELECT * FROM whatsapp_atencion ORDER BY id")
    assert len(atenciones) == 2
    assert [a["entrada_id"] for a in atenciones] == ["recibo-general", "recibo-general-repetido"]
    assert all(a["referencia_hash"] is None and a["telefono"] == TELEFONO for a in atenciones)
    assert "recibido" in respuesta and "empleado" in respuesta
    assert "pago todavía no está confirmado" in respuesta and "Pedido #" not in respuesta
    assert await uow.valor("SELECT count(*) FROM whatsapp_atencion") == 2
    assert await uow.valor("SELECT count(*) FROM whatsapp_comprobante") == 0
    assert await uow.valor("SELECT count(*) FROM pago") == 0
    if con_pedido:
        assert await s.repo.pedido(pid) == antes


async def test_recibo_y_solicitud_son_atenciones_generales_independientes(uow):
    s = construir_servicio(uow)
    await enviar(s, "personal-antes-recibo", "empleado")
    await enviar(s, "recibo-con-personal", media="adjunto")
    filas = await uow.todos("SELECT motivo FROM whatsapp_atencion ORDER BY motivo")
    assert filas == [{"motivo": "COMPROBANTE"}, {"motivo": "SOLICITUD"}]


async def test_recibo_sin_foco_no_se_asocia_por_eleccion_posterior(uow):
    s, _ = await crear_pedido_bot(uow, metodo="TRANSFERENCIA")
    cliente, item = await datos_prueba(uow)
    b = await s.crear_borrador(cliente, {
        "telefono": TELEFONO, "tipo_entrega": "RETIRO", "metodo_pago": "TRANSFERENCIA",
        "items": [{**item, "cantidad": 2}],
    })
    await enviar(s, "segunda-compra", b["mensaje"])
    await uow.ejecutar("DELETE FROM whatsapp_sesion WHERE telefono=%s", (TELEFONO,))
    respuesta = await enviar(s, "recibo-ambiguo", media="adjunto-sin-compra")
    assert "recibido" in respuesta
    assert await uow.valor(
        "SELECT count(*) FROM whatsapp_sesion WHERE telefono=%s", (TELEFONO,)
    ) == 0
    assert await uow.valor(
        "SELECT referencia_hash FROM whatsapp_entrada WHERE id='recibo-ambiguo'"
    ) is None
    await enviar(s, "compra-elegida-despues", "el segundo")
    assert await uow.valor("SELECT count(*) FROM whatsapp_comprobante") == 0
    assert await uow.valor("SELECT count(*) FROM pago") == 0
    assert (await general(uow, "COMPROBANTE"))["entrada_id"] == "recibo-ambiguo"


@pytest.mark.parametrize("texto", ["hola", "el empleado me recomendó una hamburguesa",
                                  "no necesito un empleado"])
async def test_mencion_sin_solicitud_explicita_no_crea_atencion_general(uow, texto):
    s = construir_servicio(uow)
    await enviar(s, "mencion-personal", texto)
    assert await uow.valor("SELECT count(*) FROM whatsapp_atencion") == 0


@pytest.mark.parametrize("media", [None, "adjunto-vencido"])
@pytest.mark.parametrize("con_selector", [False, True])
async def test_borrador_vencido_deriva_sin_reclamar_cliente_ni_crear_pedido(
    uow, media, con_selector
):
    s = construir_servicio(uow)
    _, item = await datos_prueba(uow)
    b = await s.crear_borrador(None, {
        "items": [item], "tipo_entrega": "RETIRO", "metodo_pago": "EFECTIVO",
        "contacto": {"nombre": "Ana", "apellido": "Pérez", "telefono": TELEFONO},
    })
    await uow.ejecutar("UPDATE whatsapp_borrador SET expira_en=now()-interval '1 minute'")
    texto = (
        "necesito un empleado " + b["referencia"] if con_selector
        else b["mensaje"] + " necesito un empleado"
    )
    respuesta = await enviar(s, "vencido-general", texto, media)
    motivo = "COMPROBANTE" if media else "SOLICITUD"
    assert await general(uow, motivo) is not None
    borrador = await uow.uno("SELECT * FROM whatsapp_borrador")
    assert borrador["cliente_id"] is None and borrador["pedido_id"] is None
    assert "empleado" in respuesta


async def test_responder_y_resolver_general_son_idempotentes_sin_mutar_pedidos(uow):
    s, pid = await crear_pedido_bot(uow)
    await enviar(s, "general-adjunto", media="recibo-no-asociable")
    atencion = await general(uow, "COMPROBANTE")
    assert atencion is not None
    antes_pedido = await uow.uno("SELECT * FROM pedido WHERE id=%s", (pid,))
    antes_borrador = await uow.uno("SELECT * FROM whatsapp_borrador WHERE pedido_id=%s", (pid,))
    empleado = await uow.valor("SELECT id FROM usuario WHERE rol='ADMINISTRADOR' LIMIT 1")
    with pytest.raises(DatosInvalidos, match="solicitud"):
        await s.responder_atencion(atencion["id"], empleado, "Lo revisamos", "invalido")
    solicitud = str(uuid4())
    salida = await s.responder_atencion(atencion["id"], empleado, "Lo revisamos", solicitud)
    assert await s.responder_atencion(
        atencion["id"], empleado, "Lo revisamos", solicitud
    ) == salida
    assert await uow.valor(
        "SELECT telefono FROM whatsapp_salida WHERE id=%s", (salida["id"],)
    ) == TELEFONO
    for _ in range(2):
        await s.resolver_atencion(atencion["id"], empleado, "Revisión manual completada")
    assert (await s.repo.atencion(atencion["id"]))["estado"] == "RESUELTA"
    await s.repo.derivar_general("general-adjunto", "COMPROBANTE")
    assert await uow.valor("SELECT count(*) FROM whatsapp_atencion") == 1
    with pytest.raises(ReglaDeNegocio, match="resuelta"):
        await s.responder_atencion(atencion["id"], empleado, "Otro mensaje", str(uuid4()))
    assert await uow.uno("SELECT * FROM pedido WHERE id=%s", (pid,)) == antes_pedido
    assert await uow.uno(
        "SELECT * FROM whatsapp_borrador WHERE pedido_id=%s", (pid,)
    ) == antes_borrador
