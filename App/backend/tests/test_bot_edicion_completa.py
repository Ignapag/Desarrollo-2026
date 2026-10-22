"""Edición conversacional real, persistencia e intervención humana sin proveedores."""

import pytest

from app.modules.whatsapp.presentation.dependencias import construir_servicio
from tests.test_whatsapp_bd import crear_pedido_bot

TELEFONO = "5492215550000"


async def enviar(s, identificador, texto, accion="consulta", argumentos=None, vinculo=None):
    await s.recibir(identificador, TELEFONO, texto)
    return await s.procesar(
        identificador, {"accion": accion, "argumentos": argumentos or {}}, vinculo
    )


async def test_agregar_crispy_sin_bacon_aclara_variante_y_confirma_sin_duplicar(uow):
    s, pid = await crear_pedido_bot(uow)
    original = (await s.repo.pedido(pid))["items"][0]
    respuesta = await enviar(
        s,
        "agregar",
        "quiero agregar una crispy sin bacon",
        "agregar_producto",
        {"producto": "Crispy", "cantidad": 1, "aclaraciones": "Sin bacon"},
    )
    assert "variante" in respuesta.lower()
    assert len((await s.repo.pedido(pid))["items"]) == 1
    # Nueva instancia, igual que después de recargar o atender en otro worker.
    s = construir_servicio(uow)
    respuesta = await enviar(s, "variante", "variante Doble")
    assert "confirmar" in respuesta and "Crispy" in respuesta and "Total" in respuesta
    assert len((await s.repo.pedido(pid))["items"]) == 1
    respuesta = await enviar(s, "aceptar", "confirmar")
    assert "Cambio guardado" in respuesta
    assert await s.procesar("aceptar", {}) == respuesta
    actual = await s.repo.pedido(pid)
    assert len(actual["items"]) == 2
    assert actual["items"][0] == original
    agregado = actual["items"][1]
    assert "Crispy" in agregado["nombre_producto"] and agregado["cantidad"] == 1
    assert agregado["aclaraciones"].lower() in {"sin panceta", "sin bacon en cubos", "sin bacon"}
    assert await uow.valor("SELECT count(*) FROM pedido") == 1


@pytest.mark.parametrize(
    "estado,fecha", [("EN_PREPARACION", False), ("LISTO", False), ("PENDIENTE", True)]
)
@pytest.mark.parametrize(
    "accion,args",
    [
        ("datos", {"metodo_pago": "transferencia"}),
        ("datos", {"referencias": "timbre azul"}),
        ("preguntar", {"campo": "direccion"}),
        ("agregar_producto", {"producto": "Crispy", "cantidad": 1}),
    ],
)
async def test_toda_modificacion_desde_cocina_deriva_solicitud_completa(
    uow, estado, fecha, accion, args
):
    s, pid = await crear_pedido_bot(uow)
    await uow.ejecutar(
        "UPDATE pedido SET estado=%s,"
        "preparacion_en=CASE WHEN %s THEN now() ELSE NULL END WHERE id=%s",
        (estado, fecha, pid),
    )
    anterior = await s.repo.pedido(pid)
    texto = "quiero cambiar mi pedido y conservar este mensaje completo"
    respuesta = await enviar(s, "cocina", texto, accion, args)
    assert "empleado" in respuesta
    assert (await s.repo.pedido(pid))["version"] == anterior["version"]
    atencion = await uow.uno(
        "SELECT e.texto FROM whatsapp_atencion a "
        "JOIN whatsapp_entrada e ON e.id=a.entrada_id WHERE a.estado='PENDIENTE'"
    )
    assert atencion["texto"] == texto


async def test_cocina_entre_interpretacion_y_aplicacion_deriva(uow):
    s, pid = await crear_pedido_bot(uow)
    await s.recibir("demora", TELEFONO, "agregar una Crispy")
    preparado = await s.preparar("demora")
    await uow.ejecutar(
        "UPDATE pedido SET estado='EN_PREPARACION',"
        "preparacion_en=now(),version=version+1 WHERE id=%s",
        (pid,),
    )
    respuesta = await s.procesar(
        "demora",
        {"accion": "agregar_producto", "argumentos": {"producto": "Crispy"}},
        preparado["vinculo"],
    )
    assert "empleado" in respuesta
    assert await uow.valor("SELECT count(*) FROM whatsapp_atencion WHERE estado='PENDIENTE'") == 1


async def test_fallo_ia_persiste_derivacion_y_ofrece_comandos_ejecutables(uow):
    s, pid = await crear_pedido_bot(uow)
    await s.recibir("sin-ia", TELEFONO, "agregar crispy")
    respuesta = await s.procesar(
        "sin-ia",
        {"accion": "humano", "argumentos": {}, "motivo": "PROVEEDOR", "causa_proveedor": "CUOTA"},
    )
    assert "ayuda" in respuesta.lower()
    assert (
        await uow.valor(
            "SELECT count(*) FROM whatsapp_atencion WHERE motivo='PROVEEDOR' AND estado='PENDIENTE'"
        )
        == 1
    )
    ayuda = await enviar(s, "guiado", "ayuda")
    assert "agregar" in ayuda.lower() and "producto" in ayuda.lower()
    assert "Total" in await enviar(s, "resumen", "resumen")
    assert "Crispy" in await enviar(s, "catalogo", "agregar")
    assert (await s.repo.pedido(pid))["items"][0]["cantidad"] == 1


async def test_quitar_ultimo_producto_propone_cancelacion_y_no_deja_vacio(uow):
    s, pid = await crear_pedido_bot(uow)
    respuesta = await enviar(
        s, "quitar", "quitar producto 1", "quitar_producto", {"item_indice": 1}
    )
    assert "cancel" in respuesta.lower() and "confirmar" in respuesta
    assert (await s.repo.pedido(pid))["estado"] == "PENDIENTE"
    assert "cancelado" in (await enviar(s, "cancelar", "confirmar")).lower()
    assert (await s.repo.pedido(pid))["estado"] == "CANCELADO"
    assert len((await s.repo.pedido(pid))["items"]) == 1


async def test_nueva_solicitud_rechazada_invalida_propuesta_anterior(uow):
    s, pid = await crear_pedido_bot(uow)
    assert "confirmar" in await enviar(s, "propuesta-a", "cantidad 2")
    respuesta = await enviar(s, "propuesta-b", "quitar ingrediente inexistente", "personalizar",
        {"item_indice": 1, "aclaraciones": "Sin ingrediente inexistente"})
    assert "No pude proponer" in respuesta
    respuesta = await enviar(s, "confirmacion-invalida", "confirmar")
    assert "No hay" in respuesta
    assert (await s.repo.pedido(pid))["items"][0]["cantidad"] == 1


async def test_argumentos_compuestos_no_se_descartan_ni_aplican_parcialmente(uow):
    s, pid = await crear_pedido_bot(uow)
    antes = await s.repo.pedido(pid)
    respuesta = await enviar(s, "compuesta", "sin tomate y quiero dos", "personalizar",
        {"item_indice": 1, "cantidad": 2, "aclaraciones": "Sin Tomate"})
    assert "empleado" in respuesta
    assert (await s.repo.pedido(pid))["items"] == antes["items"]


async def test_recorrido_guiado_quita_reemplaza_variante_y_restaura_receta(uow):
    s, pid = await crear_pedido_bot(uow, dos=True)
    respuesta = await enviar(s, "quitar-linea", "quitar producto 1")
    assert "confirmar" in respuesta
    await enviar(s, "conf-quitar", "confirmar")
    assert len((await s.repo.pedido(pid))["items"]) == 1
    respuesta = await enviar(s, "reemplazar", "reemplazar producto 1")
    assert "catálogo" in respuesta
    b = await uow.uno("SELECT contexto_chat FROM whatsapp_borrador WHERE pedido_id=%s", (pid,))
    crispy = await uow.valor("SELECT id FROM producto WHERE nombre='Crispy'")
    elegido = b["contexto_chat"]["catalogo_opciones"].index(crispy) + 1
    assert "variante" in (await enviar(s, "elegir-crispy", f"catálogo {elegido}")).lower()
    respuesta = await enviar(s, "doble", "variante Doble")
    assert "confirmar" in respuesta
    await enviar(s, "conf-reemplazo", "confirmar")
    assert "Crispy" in (await s.repo.pedido(pid))["items"][0]["nombre_producto"]
    respuesta = await enviar(s, "variante-simple", "variante Simple producto 1")
    assert "confirmar" in respuesta
    await enviar(s, "conf-simple", "confirmar")
    assert (await s.repo.pedido(pid))["items"][0]["variante"] == "Simple"
    await enviar(s, "personalizar", "personalizar producto 1")
    assert "Cambio guardado" in await enviar(s, "sin-bacon", "Sin bacon")
    await enviar(s, "editar-notas", "personalizar producto 1")
    assert "Cambio guardado" in await enviar(s, "restaurar", "receta original")
    assert (await s.repo.pedido(pid))["items"][0]["aclaraciones"] is None


async def test_referencias_de_delivery_sin_repedir_direccion(uow):
    s, pid = await crear_pedido_bot(uow)
    respuesta = await enviar(s, "direccion-completa",
        "direccion: Calle 7; numero: 123; localidad: Ensenada")
    if "confirmar" in respuesta:
        await enviar(s, "confirmar-entrega", "confirmar")
    assert "Cambio guardado" in await enviar(s, "nueva-referencia", "referencias: timbre azul")
    pedido = await s.repo.pedido(pid)
    assert (await s.repo.direccion_pedido(pedido))["referencia"] == "timbre azul"


async def test_argumentos_irrelevantes_herramienta_no_son_validos():
    from app.modules.whatsapp.infrastructure.proveedores import _argumentos_validos

    assert not _argumentos_validos("personalizar", {"cantidad": 2, "aclaraciones": "Sin Tomate"})
    assert not _argumentos_validos("quitar_producto", {"cantidad": 1, "item_indice": 1})


async def test_error_inesperado_no_deja_entrada_pendiente(uow, monkeypatch):
    from contextlib import asynccontextmanager

    from app.modules.pedidos.application.servicio_pedidos import ServicioPedidos
    from app.modules.whatsapp.presentation import procesamiento

    s, pid = await crear_pedido_bot(uow)
    await enviar(s, "proponer-error", "cantidad 2")
    await s.recibir("aplicar-error", TELEFONO, "confirmar")

    @asynccontextmanager
    async def conexion_local():
        yield uow.conn

    async def falla_al_aplicar(*args, **kwargs):
        raise RuntimeError("falla ficticia antes de escribir")

    monkeypatch.setattr(procesamiento, "conexion", conexion_local)
    monkeypatch.setattr(ServicioPedidos, "editar_items", falla_al_aplicar)
    await procesamiento.procesar_entrada("aplicar-error")
    entrada = await s.repo.entrada("aplicar-error")
    assert entrada["estado"] == "PROCESADO" and "No pude aplicar" in entrada["respuesta"]
    assert (await s.repo.pedido(pid))["items"][0]["cantidad"] == 1
    assert await uow.valor("SELECT count(*) FROM whatsapp_atencion WHERE estado='PENDIENTE'") == 1


async def test_producto_ambiguo_conserva_eleccion_al_aclarar_variante(uow):
    s, pid = await crear_pedido_bot(uow)
    crispy = await uow.uno("SELECT id,categoria_id FROM producto WHERE nombre='Crispy'")
    otro = await uow.valor("SELECT id FROM producto WHERE categoria_id<>%s LIMIT 1",
        (crispy["categoria_id"],))
    await uow.ejecutar("UPDATE producto SET nombre='Crispy' WHERE id=%s", (otro,))
    respuesta = await enviar(s, "ambigua-alta", "agregar una Crispy", "agregar_producto",
        {"producto": "Crispy", "cantidad": 1})
    assert "catálogo N" in respuesta
    b = await uow.uno("SELECT contexto_chat FROM whatsapp_borrador WHERE pedido_id=%s", (pid,))
    elegido = b["contexto_chat"]["catalogo_opciones"].index(crispy["id"]) + 1
    assert "variante" in await enviar(s, "elegir-producto", f"catálogo {elegido}")
    assert "confirmar" in await enviar(s, "variante-ambigua", "variante Doble")
    await enviar(s, "confirmar-ambigua", "confirmar")
    assert (await s.repo.pedido(pid))["items"][-1]["producto_id"] == crispy["id"]


async def test_referencia_comercial_propone_y_confirma_alta_sin_perder_personalizacion(uow):
    s, pid = await crear_pedido_bot(uow)
    anterior = await s.repo.pedido(pid)
    original = anterior['items'][0]
    await uow.ejecutar(
        "UPDATE producto SET nombre='Nagui burger',descripcion='Triple tasty de Nagi' WHERE id=%s",
        (original['producto_id'],),
    )
    movimientos = await uow.valor('SELECT count(*) FROM movimiento_stock')
    respuesta = await enviar(
        s, 'alias-comercial', 'quiero agregar una triple tasty sin tomate', 'agregar_producto',
        {'producto': 'triple tasty', 'cantidad': 1, 'variante': original['variante'],
         'aclaraciones': 'Sin tomate'},
    )
    assert 'Nagui burger' in respuesta and 'confirmar' in respuesta
    assert await s.repo.pedido(pid) == anterior
    assert await uow.valor('SELECT count(*) FROM movimiento_stock') == movimientos
    guardado = await enviar(s, 'alias-confirmar', 'confirmar')
    assert 'Cambio guardado' in guardado
    actual = await s.repo.pedido(pid)
    assert len(actual['items']) == 2
    assert actual['items'][0] == original
    assert actual['items'][1]['producto_id'] == original['producto_id']
    assert actual['items'][1]['cantidad'] == 1
    assert actual['items'][1]['aclaraciones'].casefold() == 'sin tomate'
    assert actual['total'] > anterior['total']
    assert await s.procesar('alias-confirmar', {}) == guardado
    assert len((await s.repo.pedido(pid))['items']) == 2


async def test_elegir_variante_ya_vigente_conserva_precio_y_snapshot(uow):
    s, pid = await crear_pedido_bot(uow)
    original = (await s.repo.pedido(pid))["items"][0]
    await uow.ejecutar(
        "UPDATE producto SET variantes=(SELECT jsonb_agg(v || jsonb_build_object('precio',"
        "(v->>'precio')::numeric+1000)) FROM jsonb_array_elements(variantes) v) WHERE id=%s",
        (original["producto_id"],),
    )
    respuesta = await enviar(s, "misma-variante", f"variante {original['variante']} producto 1")
    assert "ya está guardado" in respuesta
    assert (await s.repo.pedido(pid))["items"][0] == original
