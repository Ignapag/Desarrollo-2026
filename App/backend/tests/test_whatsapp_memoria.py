"""Memoria semántica del pedido y recuperación de fallos técnicos sin aplicar cambios."""

import json

import pytest

from app.modules.whatsapp.presentation.dependencias import construir_servicio
from tests.test_whatsapp_regresiones import (
    TELEFONO,
    borrador,
    cliente,
    empleado,
    enviar,
    nuevo_pedido,
    worker,
)

__all__ = ["worker"]


async def actuar(s, identificador, texto, accion):
    await s.recibir(identificador, TELEFONO, texto)
    return await s.procesar(identificador, accion)


async def test_contexto_contiene_pregunta_y_turnos_previos_del_mismo_pedido(uow, worker):
    s = construir_servicio(uow)
    _, pid = await nuevo_pedido(uow, worker, s, "memoria")
    respuesta = await actuar(s, "memoria-direccion", "Quiero cambiar la dirección", {
        "accion": "preguntar", "argumentos": {"campo": "direccion"},
    })
    assert "dirección" in respuesta and "calle" in respuesta
    await s.recibir("memoria-respuesta", TELEFONO, "Calle 7")
    contexto = (await s.preparar("memoria-respuesta"))["contexto"]
    assert contexto["conversacion"]["solicitud_pendiente"] == "direccion"
    assert contexto["conversacion"]["ultimos_turnos"]
    assert "dirección" in json.dumps(contexto, ensure_ascii=False)
    assert await uow.valor("SELECT direccion_id FROM pedido WHERE id=%s", (pid,)) is None


async def test_direccion_en_partes_conserva_datos_locales_sin_exportarlos(uow, worker):
    s = construir_servicio(uow)
    _, pid = await nuevo_pedido(uow, worker, s, "partes")
    await actuar(s, "partes-pregunta", "quiero cambiar la dir", {
        "accion": "preguntar", "argumentos": {"campo": "direccion"},
    })
    respuesta = await actuar(s, "partes-calle", "Calle Privada", {
        "accion": "datos", "argumentos": {"direccion": "Calle Privada"},
    })
    assert "número" in respuesta
    await s.recibir("partes-altura", TELEFONO, "123")
    contexto = (await s.preparar("partes-altura"))["contexto"]
    assert contexto["conversacion"]["solicitud_pendiente"] == "numero"
    assert "direccion" in contexto["conversacion"]["datos_presentes"]
    assert "Calle Privada" not in json.dumps(contexto, ensure_ascii=False)
    respuesta = await s.procesar("partes-altura", {
        "accion": "datos", "argumentos": {"numero": "123"},
    })
    assert "localidad" in respuesta
    respuesta = await actuar(s, "partes-localidad", "Ensenada", {
        "accion": "datos", "argumentos": {"localidad": "Ensenada"},
    })
    assert "Cambio guardado" in respuesta
    b = await uow.uno("SELECT contexto_chat FROM whatsapp_borrador WHERE pedido_id=%s", (pid,))
    assert not b["contexto_chat"].get("datos")
    direccion = await uow.uno(
        "SELECT d.calle,d.numero,d.localidad FROM pedido p JOIN direccion d ON d.id=p.direccion_id "
        "WHERE p.id=%s", (pid,),
    )
    assert direccion == {"calle": "Calle Privada", "numero": "123", "localidad": "Ensenada"}


async def test_caida_del_proveedor_no_deriva_ni_borra_el_contexto(uow, worker):
    s = construir_servicio(uow)
    _, pid = await nuevo_pedido(uow, worker, s, "caida")
    respuesta = await actuar(s, "caida-tecnica", "Quiero cambiar la dirección", {
        "accion": "humano", "argumentos": {}, "motivo": "PROVEEDOR",
    })
    assert "disponible" in respuesta and "entender" not in respuesta
    assert await uow.valor("SELECT count(*) FROM whatsapp_atencion") == 0
    assert await uow.valor(
        "SELECT estado FROM whatsapp_borrador WHERE pedido_id=%s", (pid,)
    ) == "CREADO"
    respuesta = await actuar(s, "caida-retomar", "Quiero cambiar la dirección", {
        "accion": "preguntar", "argumentos": {"campo": "direccion"},
    })
    assert "calle" in respuesta


async def test_modalidad_y_pago_se_conservan_mientras_completa_direccion(uow, worker):
    s = construir_servicio(uow)
    b = await borrador(uow, s, completo=False)
    await enviar(uow, worker, s, "modalidad-inicio", b["mensaje"])
    await actuar(s, "modalidad-calle", "Delivery en Calle 7, por transferencia", {
        "accion": "datos", "argumentos": {
            "tipo_entrega": "delivery", "metodo_pago": "transferencia", "direccion": "Calle 7",
        },
    })
    await actuar(s, "modalidad-numero", "123", {
        "accion": "datos", "argumentos": {"numero": "123"},
    })
    await actuar(s, "modalidad-ciudad", "Ensenada", {
        "accion": "datos", "argumentos": {"localidad": "Ensenada"},
    })
    fila = await uow.uno(
        "SELECT b.tipo_entrega,b.metodo_pago,p.tipo_entrega AS entrega_pedido "
        "FROM whatsapp_borrador b JOIN pedido p ON p.id=b.pedido_id WHERE b.cliente_id=%s",
        (await cliente(uow),),
    )
    assert fila == {
        "tipo_entrega": "DELIVERY", "metodo_pago": "TRANSFERENCIA", "entrega_pedido": "DELIVERY",
    }


@pytest.mark.parametrize("intervencion", [None, "SOLICITUD", "RESPUESTA"])
async def test_recupera_solo_incidente_tecnico_sin_intervencion_humana(uow, worker, intervencion):
    s = construir_servicio(uow)
    _, pid = await nuevo_pedido(uow, worker, s, "legacy")
    b = await uow.uno("SELECT * FROM whatsapp_borrador WHERE pedido_id=%s", (pid,))
    await s.recibir("legacy-fallo", TELEFONO, "necesito ayuda")
    motivo = "SOLICITUD" if intervencion == "SOLICITUD" else "PROVEEDOR"
    await s.repo.derivar(b["referencia_hash"], "legacy-fallo", motivo)
    await uow.ejecutar("UPDATE whatsapp_borrador SET estado='HUMANO' WHERE pedido_id=%s", (pid,))
    atencion = await uow.uno("SELECT * FROM whatsapp_atencion WHERE estado='PENDIENTE'")
    if intervencion == "RESPUESTA":
        await s.responder_atencion(
            atencion["id"], await empleado(uow), "Ya estoy atendiendo tu consulta.",
            "4d11edbe-27de-4aa3-acda-c733f02598f2",
        )
    respuesta = await actuar(s, "legacy-retomar", "quiero cambiar la dirección", {
        "accion": "preguntar", "argumentos": {"campo": "direccion"},
    })
    actual = await uow.uno("SELECT * FROM whatsapp_atencion WHERE id=%s", (atencion["id"],))
    if intervencion is None:
        assert actual["estado"] == "RESUELTA" and actual["resuelta_por"] is None
        assert "calle" in respuesta
    else:
        assert actual["estado"] == "PENDIENTE" and "empleado está atendiendo" in respuesta


async def test_personal_recibe_datos_fuera_de_los_ultimos_turnos(uow, worker):
    from app.modules.whatsapp.infrastructure.cola import ColaWhatsAppSQL

    s = construir_servicio(uow)
    _, pid = await nuevo_pedido(uow, worker, s, "detalle")
    # La asignación exige coordinación humana y mantiene los datos para la bandeja.
    await uow.ejecutar("INSERT INTO envio(pedido_id,estado) VALUES (%s,'ASIGNADO')", (pid,))
    await actuar(s, "detalle-pregunta", "quiero cambiar la dirección", {
        "accion": "preguntar", "argumentos": {"campo": "direccion"},
    })
    await actuar(s, "detalle-calle", "Calle Privada", {
        "accion": "datos", "argumentos": {"direccion": "Calle Privada"},
    })
    for n in range(6):
        await enviar(uow, worker, s, f"detalle-gracias-{n}", "gracias")
    await actuar(s, "detalle-numero", "123", {"accion": "datos", "argumentos": {"numero": "123"}})
    await actuar(s, "detalle-localidad", "Ensenada", {
        "accion": "datos", "argumentos": {"localidad": "Ensenada"},
    })
    bandeja = await ColaWhatsAppSQL(uow).bandeja()
    a = next(a for a in bandeja["atenciones"] if a["pedido_id"] == pid)
    assert "Calle Privada" in a["mensaje"] and "123" in a["mensaje"]
    assert "sin aplicar" in a["mensaje"]
    memoria = await s.repo.memoria(TELEFONO, await uow.valor(
        "SELECT referencia_hash FROM whatsapp_borrador WHERE pedido_id=%s", (pid,),
    ))
    assert "Calle Privada" not in json.dumps(memoria, ensure_ascii=False)


async def test_memoria_se_acota_al_pedido_y_al_telefono(uow, worker):
    s = construir_servicio(uow)
    ref_a, a = await nuevo_pedido(uow, worker, s, "aislado-a")
    ref_b, b = await nuevo_pedido(uow, worker, s, "aislado-b")
    await actuar(s, "aislado-cantidad-a", f"cantidad 2 {ref_a}", {
        "accion": "cantidad", "argumentos": {"cantidad": 2},
    })
    await actuar(s, "aislado-cantidad-b", f"cantidad 3 {ref_b}", {
        "accion": "cantidad", "argumentos": {"cantidad": 3},
    })
    await s.recibir("aislado-contexto", TELEFONO, "¿Cuánto sería?")
    preparado = await s.preparar("aislado-contexto")
    turnos = preparado["contexto"]["conversacion"]["ultimos_turnos"]
    assert any("cantidad a 3" in t["cliente"] for t in turnos)
    assert not any("cantidad a 2" in t["cliente"] for t in turnos)
    referencia = await uow.valor(
        "SELECT referencia_hash FROM whatsapp_borrador WHERE pedido_id=%s", (b,),
    )
    assert await s.repo.memoria("5492215550999", referencia) == []
    assert preparado["vinculo"]["pedido_id"] == b and a != b


async def test_memoria_guarda_cuatro_turnos_en_orden_de_recepcion(uow, worker):
    s = construir_servicio(uow)
    _, pid = await nuevo_pedido(uow, worker, s, "orden")
    for cantidad in range(1, 7):
        # IDs en orden inverso para no depender del orden léxico del proveedor.
        await actuar(s, f"orden-{100-cantidad}", f"cantidad {cantidad}", {
            "accion": "cantidad", "argumentos": {"cantidad": cantidad},
        })
    ref = await uow.valor(
        "SELECT referencia_hash FROM whatsapp_borrador WHERE pedido_id=%s", (pid,),
    )
    turnos = await s.repo.memoria(TELEFONO, ref)
    assert [t["cliente"] for t in turnos] == [
        f"Pidió cambiar la cantidad a {n}." for n in (3, 4, 5, 6)
    ]


async def test_respuesta_a_pregunta_pendiente_no_se_confunde_con_otro_pedido(uow, worker):
    s = construir_servicio(uow)
    ref_a, a = await nuevo_pedido(uow, worker, s, "contexto-a")
    _, b = await nuevo_pedido(uow, worker, s, "contexto-b")
    await enviar(uow, worker, s, "contexto-elegir", f"estado {ref_a}")
    await actuar(s, "contexto-pregunta", "Quiero cambiar la dirección", {
        "accion": "preguntar", "argumentos": {"campo": "direccion"},
    })
    await s.recibir("contexto-segundo", TELEFONO, "el segundo")
    preparado = await s.preparar("contexto-segundo")
    assert preparado["vinculo"]["pedido_id"] == a
    assert preparado["contexto"]["conversacion"]["solicitud_pendiente"] == "direccion"
    assert a != b


def test_resumen_semantico_no_copia_datos_privados_ni_argumentos_extra():
    from app.modules.whatsapp.domain.memoria import resumir_turno

    memoria = resumir_turno({"accion": "datos", "argumentos": {
        "direccion": "Calle Privada 777", "telefono": "5492215550000", "nombre": "Cliente Privado",
    }}, {"estado": "CREADO", "propuesta": None, "contexto_chat": {}}, set())
    texto = json.dumps(memoria)
    assert all(
        valor not in texto for valor in ("Calle Privada", "5492215550000", "Cliente Privado")
    )
