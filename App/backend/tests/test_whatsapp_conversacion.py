"""Continuidad de chat entre compras, sin elegir otro pedido por accidente."""

import pytest

from app.modules.whatsapp.presentation.dependencias import construir_servicio
from tests.test_whatsapp_regresiones import (
    TELEFONO,
    cantidad,
    enviar,
    notas,
    nuevo_pedido,
    worker,
)

__all__ = ["worker"]


async def sin_foco(uow):
    await uow.ejecutar("DELETE FROM whatsapp_sesion WHERE telefono=%s", (TELEFONO,))


async def test_sigue_el_pedido_recien_enviado_sin_pedir_numero(uow, worker):
    s = construir_servicio(uow)
    _, a = await nuevo_pedido(uow, worker, s, "charla-a")
    _, b = await nuevo_pedido(uow, worker, s, "charla-b")
    respuesta = await enviar(uow, worker, s, "charla-cambio", "sin tomate")
    assert "Cambio guardado" in respuesta
    assert await notas(uow, a) is None
    assert await notas(uow, b) == "Sin Tomate"


async def test_elegir_un_pedido_mantiene_el_contexto_en_los_mensajes_siguientes(uow, worker):
    s = construir_servicio(uow)
    ref, a = await nuevo_pedido(uow, worker, s, "foco-a")
    _, b = await nuevo_pedido(uow, worker, s, "foco-b")
    await enviar(uow, worker, s, "foco-elegir", f"estado {ref}")
    respuesta = await enviar(uow, worker, s, "foco-cantidad", "cantidad 2")
    assert "nuevo total" in respuesta
    respuesta = await enviar(uow, worker, s, "foco-confirmar", "confirmar")
    assert "Cambio guardado" in respuesta
    assert await cantidad(uow, a) == 2 and await cantidad(uow, b) == 1


async def test_datos_no_soportados_no_responden_solo_con_un_resumen(uow, worker):
    s = construir_servicio(uow)
    _, pid = await nuevo_pedido(uow, worker, s, "direccion")
    antes = await uow.valor("SELECT direccion_id FROM pedido WHERE id=%s", (pid,))
    await s.recibir(
        "direccion-nueva", TELEFONO, "dirección: Calle 7; número: 123; localidad: Ensenada"
    )
    await worker.procesar_entrada("direccion-nueva")
    respuesta = await uow.valor("SELECT respuesta FROM whatsapp_entrada WHERE id='direccion-nueva'")
    assert "empleado" in respuesta
    assert await uow.valor("SELECT direccion_id FROM pedido WHERE id=%s", (pid,)) == antes
    assert await uow.valor(
        "SELECT count(*) FROM whatsapp_atencion WHERE entrada_id='direccion-nueva'"
    ) == 1


@pytest.mark.parametrize("eleccion", ["el último", "1", "el primero"])
async def test_pregunta_y_retoma_la_solicitud_sin_hacerla_repetir(uow, worker, eleccion):
    s = construir_servicio(uow)
    _, a = await nuevo_pedido(uow, worker, s, "menu-a")
    _, b = await nuevo_pedido(uow, worker, s, "menu-b")
    await sin_foco(uow)
    pregunta = await enviar(uow, worker, s, "consulta-ambigua", "sin tomate")
    assert "cuál" in pregunta and "Armá tu carrito" not in pregunta
    assert await notas(uow, a) is None and await notas(uow, b) is None
    respuesta = await enviar(uow, worker, s, "eleccion-natural", eleccion)
    assert "Cambio guardado" in respuesta
    assert await notas(uow, a) is None and await notas(uow, b) == "Sin Tomate"
    assert await enviar(uow, worker, s, "eleccion-natural", eleccion) == respuesta


async def test_eleccion_ambigua_no_pierde_la_solicitud_ni_elige_un_producto_igual(uow, worker):
    s = construir_servicio(uow)
    _, a = await nuevo_pedido(uow, worker, s, "igual-a")
    _, b = await nuevo_pedido(uow, worker, s, "igual-b")
    await sin_foco(uow)
    await enviar(uow, worker, s, "ambigua-cantidad", "cantidad 2")
    nombre = await uow.valor("SELECT nombre_producto FROM pedido_item WHERE pedido_id=%s", (a,))
    pregunta = await enviar(uow, worker, s, "igual-nombre", "el de " + nombre)
    assert "cuál" in pregunta
    respuesta = await enviar(uow, worker, s, "igual-segundo", "el segundo")
    assert "nuevo total" in respuesta
    assert await cantidad(uow, a) == 1 and await cantidad(uow, b) == 1
    await enviar(uow, worker, s, "igual-confirmar", "confirmar")
    assert await cantidad(uow, a) == 2 and await cantidad(uow, b) == 1


async def test_se_puede_cambiar_el_foco_sin_escribir_un_comando(uow, worker):
    s = construir_servicio(uow)
    ref, a = await nuevo_pedido(uow, worker, s, "otro-a")
    _, b = await nuevo_pedido(uow, worker, s, "otro-b")
    await enviar(uow, worker, s, "otro-seleccion-a", f"estado {ref}")
    await enviar(uow, worker, s, "otro-ultimo", "el último")
    await enviar(uow, worker, s, "otro-cambio", "sin tomate")
    assert await notas(uow, a) is None and await notas(uow, b) == "Sin Tomate"


async def test_pedido_cerrado_no_redirige_un_cambio_a_la_compra_anterior(uow, worker):
    s = construir_servicio(uow)
    _, a = await nuevo_pedido(uow, worker, s, "cerrado-a")
    _, b = await nuevo_pedido(uow, worker, s, "cerrado-b")
    await uow.ejecutar("UPDATE pedido SET estado='CANCELADO' WHERE id=%s", (b,))
    respuesta = await enviar(uow, worker, s, "cerrado-cambio", "sin tomate")
    assert "anterior ya no está activo" in respuesta
    assert await notas(uow, a) is None


async def test_lista_modificada_no_reinterpreta_la_opcion_que_ya_mostramos(uow, worker):
    s = construir_servicio(uow)
    _, a = await nuevo_pedido(uow, worker, s, "lista-a")
    _, b = await nuevo_pedido(uow, worker, s, "lista-b")
    await sin_foco(uow)
    await enviar(uow, worker, s, "lista-pregunta", "sin tomate")
    await uow.ejecutar("UPDATE pedido SET estado='CANCELADO' WHERE id=%s", (b,))
    respuesta = await enviar(uow, worker, s, "lista-cambio", "1")
    assert "anterior ya no está activo" in respuesta
    assert await notas(uow, a) is None
    await enviar(uow, worker, s, "lista-confirmada", "1")
    assert await notas(uow, a) == "Sin Tomate"


async def test_otro_telefono_no_ve_las_opciones_ni_puede_elegir_un_pedido(uow, worker):
    s = construir_servicio(uow)
    _, pid = await nuevo_pedido(uow, worker, s, "privado")
    numero = await uow.valor("SELECT numero FROM pedido WHERE id=%s", (pid,))
    await s.recibir("privado-ajeno", "5492215550999", "el último")
    respuesta = await s.procesar("privado-ajeno", {"accion": "consulta"})
    assert f"Pedido #{numero}" not in respuesta
    assert await notas(uow, pid) is None


async def test_comprobante_sin_foco_se_asocia_solo_tras_elegir_y_no_acredita_pago(uow, worker):
    s = construir_servicio(uow)
    _, a = await nuevo_pedido(uow, worker, s, "recibo-a", metodo="TRANSFERENCIA")
    _, b = await nuevo_pedido(uow, worker, s, "recibo-b", metodo="TRANSFERENCIA")
    await sin_foco(uow)
    await enviar(uow, worker, s, "recibo-original", "", "imagen-ficticia")
    assert await uow.valor("SELECT count(*) FROM whatsapp_comprobante") == 0
    respuesta = await enviar(uow, worker, s, "recibo-elegido", "el último")
    assert "Comprobante recibido" in respuesta
    assert await uow.valor(
        "SELECT pedido_id FROM whatsapp_comprobante WHERE entrada_id='recibo-original'"
    ) == b
    assert await uow.valor(
        "SELECT count(*) FROM pago WHERE pedido_id=ANY(%s)", ([a, b],)
    ) == 0


async def test_eleccion_revalidada_no_aplica_otra_solicitud_mientras_gemini_responde(uow, worker):
    s = construir_servicio(uow)
    _, a = await nuevo_pedido(uow, worker, s, "version-a")
    ref_b, b = await nuevo_pedido(uow, worker, s, "version-b")
    await sin_foco(uow)
    await enviar(uow, worker, s, "version-original", "sin tomate")
    await s.recibir("version-eleccion", TELEFONO, "el último")
    preparado = await s.preparar("version-eleccion")
    assert preparado["texto"] == "sin tomate" and preparado["interpretar"]
    await enviar(uow, worker, s, "version-otro-contexto", f"estado {ref_b}")
    respuesta = await s.procesar(
        "version-eleccion",
        {"accion": "quitar_ingrediente", "argumentos": {"ingrediente": "tomate"}},
        preparado["vinculo"],
    )
    assert "no apliqué" in respuesta
    assert await notas(uow, a) is None and await notas(uow, b) is None


async def test_numero_publico_como_eleccion_retoma_la_solicitud(uow, worker):
    s = construir_servicio(uow)
    _, a = await nuevo_pedido(uow, worker, s, "numero-a")
    _, b = await nuevo_pedido(uow, worker, s, "numero-b")
    await sin_foco(uow)
    await enviar(uow, worker, s, "numero-pregunta", "sin tomate")
    numero = await uow.valor("SELECT numero FROM pedido WHERE id=%s", (a,))
    respuesta = await enviar(uow, worker, s, "numero-respuesta", f"el pedido #{numero}")
    assert "Cambio guardado" in respuesta
    assert await notas(uow, a) == "Sin Tomate" and await notas(uow, b) is None


async def test_saludar_y_agradecer_no_pierden_la_solicitud_pendiente(uow, worker):
    s = construir_servicio(uow)
    _, a = await nuevo_pedido(uow, worker, s, "gracias-a")
    _, b = await nuevo_pedido(uow, worker, s, "gracias-b")
    await sin_foco(uow)
    await enviar(uow, worker, s, "gracias-pregunta", "sin tomate")
    assert "En qué te ayudo" in await enviar(uow, worker, s, "gracias-hola", "hola")
    assert "De nada" in await enviar(uow, worker, s, "gracias-respuesta", "gracias")
    respuesta = await enviar(uow, worker, s, "gracias-elegir", "el último")
    assert "Cambio guardado" in respuesta
    assert await notas(uow, a) is None and await notas(uow, b) == "Sin Tomate"


def test_indice_de_lista_no_se_confunde_con_numero_publico():
    from app.modules.whatsapp.domain.conversacion import elegir_conversacion

    opciones = [{"numero": 2, "descripcion": "Cheese"}, {"numero": 1, "descripcion": "Bacon"}]
    assert elegir_conversacion("1", opciones) is opciones[0]
    assert elegir_conversacion("pedido 1", opciones) is opciones[1]
    assert elegir_conversacion("#1", opciones) is opciones[1]
    assert elegir_conversacion("el de Bacon", opciones) is opciones[1]
    assert elegir_conversacion("el último y sacale tomate", opciones) is None


async def test_comprobante_determinista_no_cambia_de_pedido_entre_etapas(uow, worker, monkeypatch):
    from app.modules.whatsapp.presentation import procesamiento

    s = construir_servicio(uow)
    ref_a, a = await nuevo_pedido(uow, worker, s, "race-recibo-a", metodo="TRANSFERENCIA")
    _, b = await nuevo_pedido(uow, worker, s, "race-recibo-b", metodo="TRANSFERENCIA")
    await enviar(uow, worker, s, "race-foco-a", f"estado {ref_a}")
    await s.recibir("race-recibo", TELEFONO, "", "adjunto-ficticio")
    preparar = type(s).preparar
    cambio_foco = False

    async def preparar_y_cambiar_foco(self, identificador):
        nonlocal cambio_foco
        preparado = await preparar(self, identificador)
        if identificador == "race-recibo" and not cambio_foco:
            cambio_foco = True
            assert not preparado["interpretar"]
            await enviar(uow, worker, s, "race-foco-b", "el último")
        return preparado

    monkeypatch.setattr(type(s), "preparar", preparar_y_cambiar_foco)
    await procesamiento.procesar_entrada("race-recibo")
    assert cambio_foco
    assert await uow.valor(
        "SELECT count(*) FROM whatsapp_comprobante WHERE pedido_id=ANY(%s)", ([a, b],)
    ) == 0
    respuesta = await uow.valor("SELECT respuesta FROM whatsapp_entrada WHERE id='race-recibo'")
    assert "no apliqué" in respuesta
