"""Regresiones de la revisión del bot sobre PostgreSQL descartable.

Cubren selección por referencia con dos pedidos activos, cambios que devuelven
insumos con stock agotado, derivaciones humanas y mensajes que superan el límite
de interpretación. El worker usa la conexión de la prueba, que siempre se revierte.
"""

from contextlib import asynccontextmanager

import pytest

from app.errores import DatosInvalidos, ReglaDeNegocio
from app.modules.pedidos.domain.entidades import EstadoPedido
from app.modules.whatsapp.domain.mensajes import hash_referencia
from app.modules.whatsapp.infrastructure import proveedores
from app.modules.whatsapp.infrastructure.cola import ColaWhatsAppSQL
from app.modules.whatsapp.infrastructure.proveedores import (
    GeminiInterpretador,
    SimuladoInterpretador,
)
from app.modules.whatsapp.presentation import procesamiento
from app.modules.whatsapp.presentation.dependencias import construir_servicio

TELEFONO = "5492215550000"


@pytest.fixture
def worker(uow, monkeypatch):
    """Worker real sobre la transacción revertida de la prueba."""

    @asynccontextmanager
    async def conexion():
        yield uow.conn

    monkeypatch.setattr(procesamiento, "conexion", conexion)
    monkeypatch.setattr(procesamiento, "interpretador", SimuladoInterpretador)
    return procesamiento


async def item_con_tomate(uow, cantidad=1):
    producto = await uow.uno(
        "SELECT p.id,p.variantes FROM producto p JOIN producto_ingrediente pi "
        "ON pi.producto_id=p.id JOIN ingrediente i ON i.id=pi.ingrediente_id "
        "WHERE p.activo AND lower(i.nombre)='tomate' ORDER BY p.id LIMIT 1"
    )
    variante = (producto["variantes"] or [{}])[0].get("nombre")
    return {"producto_id": producto["id"], "cantidad": cantidad, "variante": variante}


async def cliente(uow):
    return await uow.valor("SELECT usuario_id FROM cliente ORDER BY usuario_id LIMIT 1")


async def empleado(uow):
    return await uow.valor("SELECT id FROM usuario WHERE rol='ADMINISTRADOR' LIMIT 1")


async def borrador(uow, s, completo=True, metodo="EFECTIVO", cantidad=1):
    datos = {"telefono": TELEFONO, "items": [await item_con_tomate(uow, cantidad)]}
    if completo:
        datos |= {"tipo_entrega": "RETIRO", "metodo_pago": metodo}
    return await s.crear_borrador(await cliente(uow), datos)


async def pedido_de(uow, b):
    return await uow.valor(
        "SELECT pedido_id FROM whatsapp_borrador WHERE referencia_hash=%s",
        (hash_referencia(b["referencia"][3:]),),
    )


async def nuevo_pedido(uow, worker, s, sufijo, **opciones):
    b = await borrador(uow, s, **opciones)
    await enviar(uow, worker, s, f"inicio-{sufijo}", b["mensaje"])
    pid = await pedido_de(uow, b)
    assert pid is not None
    return b["referencia"], pid


async def enviar(uow, worker, s, identificador, texto, media_id=None):
    await s.recibir(identificador, TELEFONO, texto, media_id)
    await worker.procesar_entrada(identificador)
    return await uow.valor("SELECT respuesta FROM whatsapp_entrada WHERE id=%s", (identificador,))


async def notas(uow, pid):
    return await uow.valor("SELECT aclaraciones FROM pedido_item WHERE pedido_id=%s", (pid,))


async def cantidad(uow, pid):
    return await uow.valor("SELECT cantidad FROM pedido_item WHERE pedido_id=%s", (pid,))


# --- Hallazgo 2: dos pedidos activos y selección por referencia -------------------


async def test_referencia_en_el_mensaje_modifica_solo_ese_pedido(uow, worker):
    s = construir_servicio(uow)
    ref_a, pid_a = await nuevo_pedido(uow, worker, s, "a")
    _, pid_b = await nuevo_pedido(uow, worker, s, "b")

    respuesta = await enviar(uow, worker, s, "sin-ref", "sin tomate")
    assert "referencia" in respuesta.lower()
    assert await notas(uow, pid_a) is None and await notas(uow, pid_b) is None

    respuesta = await enviar(uow, worker, s, "con-ref", f"sin tomate {ref_a}")
    assert "Cambio guardado" in respuesta
    assert await notas(uow, pid_a) == "Sin Tomate"
    assert await notas(uow, pid_b) is None
    respuesta_guardada = await uow.valor(
        "SELECT referencia_hash FROM whatsapp_entrada WHERE id='con-ref'"
    )
    assert respuesta_guardada == hash_referencia(ref_a[3:])


async def test_confirmacion_de_importe_con_referencia_aplica_al_pedido_correcto(uow, worker):
    s = construir_servicio(uow)
    _, pid_a = await nuevo_pedido(uow, worker, s, "a")
    ref_b, pid_b = await nuevo_pedido(uow, worker, s, "b")

    respuesta = await enviar(uow, worker, s, "cantidad-b", f"cantidad 2 {ref_b}")
    assert "nuevo total" in respuesta
    assert await cantidad(uow, pid_b) == 1

    respuesta = await enviar(uow, worker, s, "confirmar-sin-ref", "confirmar")
    assert "referencia" in respuesta.lower()
    assert await cantidad(uow, pid_b) == 1

    respuesta = await enviar(uow, worker, s, "confirmar-a", f"confirmar {ref_b[:-1]}x")
    assert await cantidad(uow, pid_a) == 1 and await cantidad(uow, pid_b) == 1

    respuesta = await enviar(uow, worker, s, "confirmar-b", f"confirmar {ref_b}")
    assert "Cambio guardado" in respuesta
    assert await cantidad(uow, pid_b) == 2
    assert await cantidad(uow, pid_a) == 1


async def test_comprobante_con_referencia_se_asocia_al_pedido_correcto(uow, worker):
    s = construir_servicio(uow)
    _, pid_a = await nuevo_pedido(uow, worker, s, "a", metodo="TRANSFERENCIA")
    ref_b, pid_b = await nuevo_pedido(uow, worker, s, "b", metodo="TRANSFERENCIA")

    respuesta = await enviar(uow, worker, s, "foto-sin-ref", "", "media-sin-ref")
    assert "referencia" in respuesta.lower()
    assert (
        await uow.valor(
            "SELECT count(*) FROM whatsapp_comprobante WHERE pedido_id = ANY(%s)", ([pid_a, pid_b],)
        )
        == 0
    )

    respuesta = await enviar(uow, worker, s, "foto-b", f"Comprobante {ref_b}", "media-b")
    assert "revisión humana" in respuesta
    assert (
        await uow.valor("SELECT pedido_id FROM whatsapp_comprobante WHERE entrada_id='foto-b'")
        == pid_b
    )
    pagos = await uow.valor(
        "SELECT count(*) FROM pago WHERE pedido_id = ANY(%s)", ([pid_a, pid_b],)
    )
    assert pagos == 0


async def test_dos_referencias_distintas_no_eligen_pedido(uow, worker):
    s = construir_servicio(uow)
    ref_a, pid_a = await nuevo_pedido(uow, worker, s, "a")
    ref_b, pid_b = await nuevo_pedido(uow, worker, s, "b")
    respuesta = await enviar(uow, worker, s, "dos-ref", f"sin tomate {ref_a} {ref_b}")
    assert "una sola referencia" in respuesta
    assert await notas(uow, pid_a) is None and await notas(uow, pid_b) is None


# --- Hallazgo 3: stock agotado y cambios que devuelven insumos -------------------


async def agotar_pan_al_confirmar(uow, s, pid, unidades):
    """Deja el pan exacto para el pedido: confirmar consume la última unidad."""
    pan = await uow.valor(
        "SELECT i.id FROM ingrediente i JOIN producto_ingrediente pi ON pi.ingrediente_id=i.id "
        "JOIN pedido_item it ON it.producto_id=pi.producto_id "
        "WHERE it.pedido_id=%s AND pi.es_base AND lower(i.nombre) <> 'tomate' "
        "ORDER BY i.id LIMIT 1",
        (pid,),
    )
    await uow.ejecutar("UPDATE ingrediente SET cantidad_actual=%s WHERE id=%s", (unidades, pan))
    await s.pedidos.cambiar_estado(pid, EstadoPedido.CONFIRMADO, usuario_id=None)
    producto = await uow.valor("SELECT producto_id FROM pedido_item WHERE pedido_id=%s", (pid,))
    assert (
        await uow.valor(
            "SELECT disponible FROM producto_disponible WHERE producto_id=%s", (producto,)
        )
        is False
    )
    return pan


async def test_quitar_ingrediente_con_ultima_unidad_consumida_devuelve_una_vez(uow, worker):
    s = construir_servicio(uow)
    _, pid = await nuevo_pedido(uow, worker, s, "a")
    pan = await agotar_pan_al_confirmar(uow, s, pid, 1)
    tomate = await uow.valor("SELECT id FROM ingrediente WHERE lower(nombre)='tomate'")
    stock_tomate = await uow.valor("SELECT cantidad_actual FROM ingrediente WHERE id=%s", (tomate,))

    for identificador in ("sin-tomate", "sin-tomate-repetido"):
        respuesta = await enviar(uow, worker, s, identificador, "sin tomate")
    assert await notas(uow, pid) == "Sin Tomate"
    assert (
        await uow.valor(
            "SELECT count(*) FROM movimiento_stock WHERE pedido_id=%s AND tipo='DEVOLUCION' "
            "AND ingrediente_id=%s",
            (pid, tomate),
        )
        == 1
    )
    assert (
        await uow.valor("SELECT cantidad_actual FROM ingrediente WHERE id=%s", (tomate,))
        == stock_tomate + 1
    )
    assert "ya está guardado sin ese ingrediente" in respuesta

    # Un aumento sí requiere insumos: sigue rechazado con el pan agotado.
    await enviar(uow, worker, s, "aumentar", "cantidad 2")
    await enviar(uow, worker, s, "confirmar-aumento", "confirmar")
    assert await cantidad(uow, pid) == 1
    assert await uow.valor("SELECT cantidad_actual FROM ingrediente WHERE id=%s", (pan,)) == 0


async def test_reducir_cantidad_con_stock_agotado_devuelve_insumos(uow, worker):
    s = construir_servicio(uow)
    _, pid = await nuevo_pedido(uow, worker, s, "a", cantidad=2)
    pan = await agotar_pan_al_confirmar(uow, s, pid, 2)
    respuesta = await enviar(uow, worker, s, "reducir", "cantidad 1")
    assert "nuevo total" in respuesta
    respuesta = await enviar(uow, worker, s, "confirmar-reduccion", "confirmar")
    assert "Cambio guardado" in respuesta
    assert await cantidad(uow, pid) == 1
    assert await uow.valor("SELECT cantidad_actual FROM ingrediente WHERE id=%s", (pan,)) == 1


# --- Hallazgo 4: derivación humana en borradores ---------------------------------


async def atencion(uow, b):
    return await uow.uno(
        "SELECT * FROM whatsapp_atencion WHERE referencia_hash=%s",
        (hash_referencia(b["referencia"][3:]),),
    )


async def estado_borrador(uow, b):
    return await uow.uno(
        "SELECT estado,tipo_entrega,metodo_pago,items,pedido_id FROM whatsapp_borrador "
        "WHERE referencia_hash=%s",
        (hash_referencia(b["referencia"][3:]),),
    )


async def test_derivacion_en_borrador_completo_no_crea_pedido(uow):
    s = construir_servicio(uow)
    b = await borrador(uow, s)
    pedidos = await uow.valor("SELECT count(*) FROM pedido")
    await s.recibir("humano-completo", TELEFONO, f"{b['referencia']} quiero hablar con alguien")
    respuesta = await s.procesar("humano-completo", {"accion": "humano", "argumentos": {}})
    assert "empleado" in respuesta
    assert await uow.valor("SELECT count(*) FROM pedido") == pedidos
    fila = await estado_borrador(uow, b)
    assert fila["estado"] == "HUMANO" and fila["pedido_id"] is None
    assert fila["tipo_entrega"] == "RETIRO" and fila["metodo_pago"] == "EFECTIVO"
    pendiente = await atencion(uow, b)
    assert pendiente["estado"] == "PENDIENTE"
    assert pendiente["motivo"] == "SOLICITUD"
    assert pendiente["entrada_id"] == "humano-completo"


async def test_derivacion_en_borrador_incompleto_conserva_datos(uow, worker):
    s = construir_servicio(uow)
    b = await borrador(uow, s, completo=False)
    respuesta = await enviar(uow, worker, s, "inicio", b["mensaje"])
    assert "Retiro o delivery" in respuesta
    await s.recibir("pedir-persona", TELEFONO, "necesito que me atienda una persona")
    respuesta = await s.procesar("pedir-persona", {"accion": "humano", "argumentos": {}})
    assert "empleado" in respuesta and "Retiro o delivery" not in respuesta
    fila = await estado_borrador(uow, b)
    assert fila["estado"] == "HUMANO" and fila["pedido_id"] is None
    assert len(fila["items"]) == 1
    assert (await atencion(uow, b))["motivo"] == "SOLICITUD"
    # Una segunda derivación no duplica la atención pendiente.
    await s.recibir("pedir-persona-2", TELEFONO, "por favor una persona")
    await s.procesar("pedir-persona-2", {"accion": "humano", "argumentos": {}})
    assert (
        await uow.valor(
            "SELECT count(*) FROM whatsapp_atencion WHERE referencia_hash=%s",
            (hash_referencia(b["referencia"][3:]),),
        )
        == 1
    )


@pytest.fixture
def gemini_caido(worker, monkeypatch):
    def fallar(*_args, **_kwargs):
        raise OSError("cuota agotada")

    monkeypatch.setattr(proveedores, "_leer_json", fallar)
    monkeypatch.setattr(
        procesamiento, "interpretador", lambda: GeminiInterpretador("clave-prueba", "modelo-x")
    )
    return worker


async def test_fallo_de_gemini_en_borrador_incompleto_registra_atencion(uow, gemini_caido):
    s = construir_servicio(uow)
    b = await borrador(uow, s, completo=False)
    await enviar(uow, gemini_caido, s, "inicio", b["mensaje"])
    respuesta = await enviar(uow, gemini_caido, s, "retiro", "retiro")
    assert "empleado" in respuesta
    fila = await estado_borrador(uow, b)
    assert fila["pedido_id"] is None and fila["tipo_entrega"] is None
    assert (await atencion(uow, b))["motivo"] == "PROVEEDOR"


async def test_fallo_de_gemini_en_borrador_completo_no_crea_pedido(uow, gemini_caido):
    s = construir_servicio(uow)
    b = await borrador(uow, s)
    respuesta = await enviar(
        uow, gemini_caido, s, "inicio-con-texto", f"{b['referencia']} y agregale una gaseosa"
    )
    assert "empleado" in respuesta
    assert await pedido_de(uow, b) is None
    assert (await atencion(uow, b))["motivo"] == "PROVEEDOR"


async def test_derivacion_en_pedido_registra_atencion(uow, worker):
    s = construir_servicio(uow)
    ref, pid = await nuevo_pedido(uow, worker, s, "a")
    await s.recibir("humano-pedido", TELEFONO, "quiero hablar con alguien")
    respuesta = await s.procesar("humano-pedido", {"accion": "humano", "argumentos": {}})
    assert "empleado" in respuesta
    fila = await uow.uno(
        "SELECT * FROM whatsapp_atencion WHERE referencia_hash=%s", (hash_referencia(ref[3:]),)
    )
    assert fila["estado"] == "PENDIENTE" and fila["entrada_id"] == "humano-pedido"
    assert await notas(uow, pid) is None


# --- Hallazgo 5: atender derivaciones desde la bandeja ---------------------------


async def derivar_borrador(uow, s):
    b = await borrador(uow, s, completo=False)
    await s.recibir("derivar", TELEFONO, f"{b['referencia']} necesito ayuda con la dirección")
    await s.procesar("derivar", {"accion": "humano", "argumentos": {}})
    return b, (await atencion(uow, b))["id"]


async def test_bandeja_identifica_conversacion_sin_pedido_y_su_solicitud(uow):
    s = construir_servicio(uow)
    b, atencion_id = await derivar_borrador(uow, s)
    bandeja = await ColaWhatsAppSQL(uow).bandeja()
    fila = next(a for a in bandeja["atenciones"] if a["id"] == atencion_id)
    assert fila["telefono"] == TELEFONO
    assert fila["motivo"] == "SOLICITUD"
    assert fila["pedido_id"] is None and fila["numero"] is None
    assert "necesito ayuda con la dirección" in fila["mensaje"]
    assert "MB-" not in fila["mensaje"]
    assert fila["cliente"]
    assert fila["productos"] and fila["productos"][0]["cantidad"] == 1
    assert fila["respuestas"] == []
    assert all("MB-" not in m["texto"] for m in fila["mensajes"])


async def test_respuesta_del_empleado_usa_la_outbox_y_muestra_su_estado_real(uow):
    s = construir_servicio(uow)
    _, atencion_id = await derivar_borrador(uow, s)
    persona = await empleado(uow)
    solicitud = "0f8e1c1e-6b65-4d2e-8f39-5b1a1d2c3e4f"
    primera = await s.responder_atencion(atencion_id, persona, "Hola, te ayudo.", solicitud)
    repetida = await s.responder_atencion(atencion_id, persona, "Hola, te ayudo.", solicitud)
    assert primera == repetida
    assert primera["estado"] == "PENDIENTE"
    salida = await uow.uno("SELECT * FROM whatsapp_salida WHERE id=%s", (primera["id"],))
    assert salida["atencion_id"] == atencion_id and salida["enviado_por"] == persona
    assert salida["telefono"] == TELEFONO
    bandeja = await ColaWhatsAppSQL(uow).bandeja()
    fila = next(a for a in bandeja["atenciones"] if a["id"] == atencion_id)
    assert [(r["id"], r["estado"]) for r in fila["respuestas"]] == [(primera["id"], "PENDIENTE")]
    with pytest.raises(DatosInvalidos):
        await s.responder_atencion(
            atencion_id, persona, "   ", "1f8e1c1e-6b65-4d2e-8f39-5b1a1d2c3e4f"
        )


async def test_resolver_atencion_registra_responsable_y_es_idempotente(uow):
    s = construir_servicio(uow)
    b, atencion_id = await derivar_borrador(uow, s)
    persona = await empleado(uow)
    with pytest.raises(DatosInvalidos):
        await s.resolver_atencion(atencion_id, persona, " ")
    resultado = await s.resolver_atencion(atencion_id, persona, "Llamé y completamos la dirección")
    assert resultado["estado"] == "RESUELTA"
    assert (await s.resolver_atencion(atencion_id, persona, "otra"))["estado"] == "RESUELTA"
    fila = await atencion(uow, b)
    assert fila["resuelta_por"] == persona
    assert fila["resolucion"] == "Llamé y completamos la dirección"
    assert (await estado_borrador(uow, b))["estado"] == "VINCULADO"
    bandeja = await ColaWhatsAppSQL(uow).bandeja()
    assert atencion_id not in {a["id"] for a in bandeja["atenciones"]}
    with pytest.raises(ReglaDeNegocio):
        await s.responder_atencion(
            atencion_id, persona, "¿Seguís ahí?", "2f8e1c1e-6b65-4d2e-8f39-5b1a1d2c3e4f"
        )


# --- Hallazgo 6: mensajes que superan el límite de interpretación ----------------


class InterpretadorDePrefijo:
    """Modela un proveedor que acata lo que lee: actúa sobre cualquier 'sin tomate'."""

    def __init__(self):
        self.textos = []

    async def interpretar(self, texto, contexto):
        self.textos.append(texto)
        if texto.startswith("sin tomate"):
            return {"accion": "quitar_ingrediente", "argumentos": {"ingrediente": "tomate"}}
        return {"accion": "humano", "argumentos": {}}


async def test_mensaje_largo_no_ejecuta_el_prefijo(uow, worker, monkeypatch):
    s = construir_servicio(uow)
    _, pid = await nuevo_pedido(uow, worker, s, "a")
    interpretador = InterpretadorDePrefijo()
    monkeypatch.setattr(procesamiento, "interpretador", lambda: interpretador)
    texto = "sin tomate" + " detalle" * 300 + " Aclaración final: no, dejale el tomate."
    assert len(texto) > 2000 and texto.index("Aclaración final") > 2000
    respuesta = await enviar(uow, worker, s, "largo", texto)
    assert await notas(uow, pid) is None
    # Ni el prefijo ni el mensaje completo llegan al intérprete.
    assert interpretador.textos == []
    assert "2000" in respuesta and "no apliqué" in respuesta.lower()
    assert "Reformulalo" in respuesta
    # Pedir reformulación no bloquea la conversación con una atención.
    assert await uow.valor("SELECT count(*) FROM whatsapp_atencion WHERE entrada_id='largo'") == 0
    respuesta = await enviar(uow, worker, s, "corto", "sin tomate")
    assert "Cambio guardado" in respuesta


async def test_servicio_rechaza_mutacion_interpretada_de_mensaje_largo(uow, worker):
    s = construir_servicio(uow)
    _, pid = await nuevo_pedido(uow, worker, s, "a")
    await s.recibir("largo-directo", TELEFONO, "sin tomate " + "x" * 2100)
    await s.procesar(
        "largo-directo", {"accion": "quitar_ingrediente", "argumentos": {"ingrediente": "tomate"}}
    )
    assert await notas(uow, pid) is None


# --- Revisión independiente: atención en curso, remitentes y referencias ---------


async def test_atencion_pendiente_impide_crear_o_modificar_hasta_resolver(uow, worker):
    s = construir_servicio(uow)
    b = await borrador(uow, s, completo=False)
    await enviar(uow, worker, s, "inicio", b["mensaje"])
    await s.recibir("persona", TELEFONO, "quiero hablar con una persona")
    await s.procesar("persona", {"accion": "humano", "argumentos": {}})

    respuesta = await enviar(uow, worker, s, "datos", "retiro y efectivo")
    assert "empleado está atendiendo" in respuesta
    fila = await estado_borrador(uow, b)
    assert fila["pedido_id"] is None and fila["tipo_entrega"] is None
    assert fila["estado"] == "HUMANO"

    persona = await empleado(uow)
    await s.resolver_atencion((await atencion(uow, b))["id"], persona, "Atendido por teléfono")
    assert (await estado_borrador(uow, b))["estado"] == "VINCULADO"
    respuesta = await enviar(uow, worker, s, "datos-2", "retiro y efectivo")
    assert "Pedido #" in respuesta
    assert await pedido_de(uow, b) is not None


async def test_derivar_descarta_la_propuesta_de_importe(uow, worker):
    s = construir_servicio(uow)
    ref, pid = await nuevo_pedido(uow, worker, s, "a")
    assert "nuevo total" in await enviar(uow, worker, s, "doble", "cantidad 2")
    await s.recibir("persona", TELEFONO, "mejor hablo con alguien")
    await s.procesar("persona", {"accion": "humano", "argumentos": {}})
    assert (
        await uow.valor(
            "SELECT propuesta FROM whatsapp_borrador WHERE referencia_hash=%s",
            (hash_referencia(ref[3:]),),
        )
        is None
    )
    respuesta = await enviar(uow, worker, s, "ok", "confirmar")
    assert "empleado está atendiendo" in respuesta
    assert await cantidad(uow, pid) == 1


async def test_remitente_sin_conversacion_no_se_envia_al_proveedor(uow, worker, monkeypatch):
    s = construir_servicio(uow)
    interpretador = InterpretadorDePrefijo()
    monkeypatch.setattr(procesamiento, "interpretador", lambda: interpretador)
    await s.recibir("desconocido", "5492215559876", "hola, mi DNI es 30111222")
    await worker.procesar_entrada("desconocido")
    assert interpretador.textos == []
    respuesta = await uow.valor("SELECT respuesta FROM whatsapp_entrada WHERE id='desconocido'")
    assert "referencia" in respuesta.lower()


@pytest.mark.parametrize("variante", ["mb-{t}", "pedidoMB-{t}", "MB\u2011{t}", "MB {t}", "MB-{t}"])
def test_variantes_de_referencia_no_salen_al_proveedor_ni_a_la_bandeja(variante):
    from app.modules.whatsapp.domain.mensajes import ocultar_referencias, sin_referencias

    token = "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8S9t0U1v"
    texto = "sin tomate " + variante.format(t=token) + " gracias"
    assert token not in sin_referencias(texto)
    assert sin_referencias(texto) in {"sin tomate gracias", "sin tomate pedido gracias"}
    assert token not in ocultar_referencias(texto)
    # Palabras comunes que contienen "mb" no se alteran.
    assert sin_referencias("hamburguesa sin tomate") == "hamburguesa sin tomate"


async def test_confirmacion_con_puntuacion_aplica_el_cambio(uow, worker):
    s = construir_servicio(uow)
    _, pid = await nuevo_pedido(uow, worker, s, "a")
    await enviar(uow, worker, s, "doble", "cantidad 2")
    await s.recibir("ok", TELEFONO, "Confirmar.")
    respuesta = await s.procesar("ok", {"accion": "confirmar", "argumentos": {}})
    assert "Cambio guardado" in respuesta
    assert await cantidad(uow, pid) == 2
