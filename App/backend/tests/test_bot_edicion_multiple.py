"""Planes de varios cambios conservan intención, confirmación y atomicidad."""

import pytest

from app.modules.whatsapp.presentation.dependencias import construir_servicio
from tests.test_bot_edicion_completa import enviar
from tests.test_whatsapp_bd import crear_pedido_bot


def plan(*operaciones):
    return {"operaciones": [
        {"accion": accion, "argumentos": args} for accion, args in operaciones
    ]}


CRISPY = ("agregar_producto", {
    "producto": "Crispy", "cantidad": 1, "aclaraciones": "Sin bacon",
})
DELIVERY = ("datos", {
    "tipo_entrega": "delivery", "direccion": "Calle 52", "numero": "32",
    "localidad": "Ensenada", "metodo_pago": "efectivo",
})


async def test_crispy_y_entrega_se_aclaran_y_confirman_juntas_sin_duplicar(uow):
    s, pid = await crear_pedido_bot(uow)
    anterior = await s.repo.pedido(pid)
    respuesta = await enviar(s, "multiple", "agregar crispy sin bacon y delivery a Ensenada",
        "editar_pedido", plan(CRISPY, DELIVERY))
    assert "variante" in respuesta.lower()
    assert await s.repo.pedido(pid) == anterior
    s = construir_servicio(uow)
    respuesta = await enviar(s, "doble-multiple", "variante Doble")
    assert all(t in respuesta for t in ("Crispy", "Delivery", "Calle 52", "32", "confirmar"))
    assert await s.repo.pedido(pid) == anterior
    respuesta = await enviar(s, "confirmar-multiple", "confirmar")
    assert "Cambios guardados" in respuesta
    assert await s.procesar("confirmar-multiple", {}) == respuesta
    actual = await s.repo.pedido(pid)
    assert len(actual["items"]) == 2 and actual["items"][0] == anterior["items"][0]
    assert actual["items"][-1]["aclaraciones"] == "Sin Panceta"
    assert actual["tipo_entrega"] == "DELIVERY"
    assert actual["version"] == anterior["version"] + 1
    assert (await s.repo.direccion_pedido(actual))["calle"] == "Calle 52"
    assert await uow.valor("SELECT count(*) FROM pedido") == 1


async def test_falta_numero_conserva_producto_variante_y_localidad(uow):
    s, pid = await crear_pedido_bot(uow)
    crispy = (CRISPY[0], {**CRISPY[1], "variante": "Simple"})
    datos = ("datos", {"tipo_entrega": "delivery", "direccion": "Calle 52",
        "localidad": "Ensenada"})
    respuesta = await enviar(s, "numero-faltante", "crispy simple y delivery calle 52 Ensenada",
        "editar_pedido", plan(crispy, datos))
    assert "número" in respuesta
    assert len((await s.repo.pedido(pid))["items"]) == 1
    s = construir_servicio(uow)
    respuesta = await enviar(s, "completar-numero", "32", "completar_edicion", {"numero": "32"})
    assert "Crispy" in respuesta and "confirmar" in respuesta
    await enviar(s, "confirmar-numero", "confirmar")
    actual = await s.repo.pedido(pid)
    assert len(actual["items"]) == 2
    assert (await s.repo.direccion_pedido(actual))["numero"] == "32"


async def test_indices_referencian_productos_originales_al_quitar_otro(uow):
    s, pid = await crear_pedido_bot(uow, dos=True)
    original = (await s.repo.pedido(pid))["items"]
    respuesta = await enviar(s, "indices-originales", "quitar el primero y dos del segundo",
        "editar_pedido", plan(("quitar_producto", {"item_indice": 1}),
            ("cantidad", {"item_indice": 2, "cantidad": 2})))
    assert "confirmar" in respuesta
    await enviar(s, "confirmar-indices", "confirmar")
    actual = (await s.repo.pedido(pid))["items"]
    assert len(actual) == 1 and actual[0]["id"] == original[1]["id"]
    assert actual[0]["cantidad"] == 2


@pytest.mark.parametrize("operacion", [
    {"accion": "confirmar", "argumentos": {}},
    {"accion": "datos", "argumentos": {"precio": 1}},
    {"accion": "cantidad", "argumentos": {"cantidad": True}},
])
async def test_plan_invalido_no_aplica_su_parte_valida(uow, operacion):
    s, pid = await crear_pedido_bot(uow)
    anterior = await s.repo.pedido(pid)
    args = plan(("cantidad", {"cantidad": 2, "item_indice": 1}))
    args["operaciones"].append(operacion)
    respuesta = await enviar(s, "plan-invalido", "dos cambios", "editar_pedido", args)
    assert "guardad" not in respuesta.lower()
    assert await s.repo.pedido(pid) == anterior


async def test_plan_desde_cocina_deriva_solicitud_completa(uow):
    s, pid = await crear_pedido_bot(uow)
    await uow.ejecutar("UPDATE pedido SET estado='EN_PREPARACION',preparacion_en=now() WHERE id=%s",
        (pid,))
    anterior = await s.repo.pedido(pid)
    respuesta = await enviar(s, "plan-cocina", "crispy y delivery", "editar_pedido",
        plan(CRISPY, DELIVERY))
    assert "empleado" in respuesta
    assert await s.repo.pedido(pid) == anterior
    assert await uow.valor("SELECT count(*) FROM whatsapp_atencion WHERE estado='PENDIENTE'") == 1


async def test_tarifa_cambia_despues_de_propuesta_no_aplica_nada(uow):
    s, pid = await crear_pedido_bot(uow)
    anterior = await s.repo.pedido(pid)
    crispy = (CRISPY[0], {**CRISPY[1], "variante": "Simple"})
    respuesta = await enviar(s, "plan-tarifa", "crispy simple y delivery", "editar_pedido",
        plan(crispy, DELIVERY))
    assert "confirmar" in respuesta
    await uow.ejecutar("UPDATE zona_cobertura SET costo_envio=costo_envio+1000 WHERE activa=true")
    respuesta = await enviar(s, "tarifa-nueva", "confirmar")
    assert "guardad" not in respuesta.lower()
    assert await s.repo.pedido(pid) == anterior


async def test_reemplazo_y_cantidad_referencian_la_misma_linea_original(uow):
    s, pid = await crear_pedido_bot(uow)
    respuesta = await enviar(s, "reemplazar-cantidad", "cambiar el primero por crispy y llevar dos",
        "editar_pedido", plan(("reemplazar_producto", {"item_indice": 1,
            "producto": "Crispy", "variante": "Simple", "cantidad": 1}),
            ("cantidad", {"item_indice": 1, "cantidad": 2})))
    assert "confirmar" in respuesta
    await enviar(s, "confirmar-reemplazar-cantidad", "confirmar")
    actual = (await s.repo.pedido(pid))["items"]
    assert len(actual) == 1 and "Crispy" in actual[0]["nombre_producto"]
    assert actual[0]["cantidad"] == 2


async def test_plan_invalido_invalida_confirmacion_anterior(uow):
    s, pid = await crear_pedido_bot(uow)
    anterior = await s.repo.pedido(pid)
    assert "confirmar" in await enviar(s, "propuesta-anterior", "dos unidades",
        "editar_pedido", plan(("cantidad", {"item_indice": 1, "cantidad": 2})))
    await enviar(s, "plan-nuevo-invalido", "otra solicitud", "editar_pedido",
        plan(("cantidad", {"item_indice": 1, "precio": 1})))
    respuesta = await enviar(s, "confirmacion-vieja", "confirmar")
    assert "guardad" not in respuesta.lower()
    assert await s.repo.pedido(pid) == anterior


async def test_varias_aclaraciones_y_confirmacion_prematura_conservan_plan(uow):
    s, pid = await crear_pedido_bot(uow)
    anterior = await s.repo.pedido(pid)
    respuesta = await enviar(s, "aclaraciones", "crispy y delivery", "editar_pedido",
        plan(("agregar_producto", {"producto": "Crispy", "aclaraciones": "Sin bacon"}),
            ("datos", {"tipo_entrega": "delivery", "direccion": "Calle 52",
                "localidad": "Ensenada"})))
    assert "variante" in respuesta
    assert "dato pendiente" in await enviar(s, "prematuro", "confirmar")
    assert "unidades" in await enviar(s, "simple-aclaraciones", "variante Simple")
    assert "número" in await enviar(s, "cantidad-aclaraciones", "cantidad 2")
    s = construir_servicio(uow)
    respuesta = await enviar(s, "numero-aclaraciones", "32", "completar_edicion", {"numero": "32"})
    assert "confirmar" in respuesta and "2 × Crispy" in respuesta
    assert await s.repo.pedido(pid) == anterior
    await enviar(s, "confirmar-aclaraciones", "confirmar")
    actual = await s.repo.pedido(pid)
    assert actual["items"][-1]["cantidad"] == 2 and actual["tipo_entrega"] == "DELIVERY"


async def test_variante_y_personalizacion_conservan_identidad_virtual(uow):
    s, pid = await crear_pedido_bot(uow)
    item = (await s.repo.pedido(pid))["items"][0]
    respuesta = await enviar(s, "variante-personalizacion", "simple y sin tomate",
        "editar_pedido", plan(("cambiar_variante", {"item_indice": 1, "variante": "Simple"}),
            ("personalizar", {"item_indice": 1, "aclaraciones": "Sin Tomate"})))
    assert "confirmar" in respuesta
    await enviar(s, "confirmar-variante-personalizacion", "confirmar")
    actual = (await s.repo.pedido(pid))["items"][0]
    assert actual["producto_id"] == item["producto_id"] and actual["variante"] == "Simple"
    assert actual["aclaraciones"] == "Sin Tomate"


async def test_quitar_primero_y_aclarar_reemplazo_del_segundo(uow):
    s, pid = await crear_pedido_bot(uow, dos=True)
    respuesta = await enviar(s, "quitar-aclarar", "quitar primero y segundo por crispy",
        "editar_pedido", plan(("quitar_producto", {"item_indice": 1}),
            ("reemplazar_producto", {"item_indice": 2, "producto": "Crispy"}),
            ("cantidad", {"item_indice": 2, "cantidad": 2})))
    assert "variante" in respuesta
    respuesta = await enviar(s, "doble-quitar", "variante Doble")
    assert "confirmar" in respuesta
    await enviar(s, "confirmar-quitar-aclarar", "confirmar")
    actual = (await s.repo.pedido(pid))["items"]
    assert len(actual) == 1 and "Crispy" in actual[0]["nombre_producto"]
    assert actual[0]["cantidad"] == 2


async def test_fondos_cambian_antes_de_confirmar_conserva_todo_el_pedido(uow):
    s, pid = await crear_pedido_bot(uow)
    anterior = await s.repo.pedido(pid)
    assert "confirmar" in await enviar(s, "fondos-plan", "dos unidades y delivery",
        "editar_pedido", plan(("cantidad", {"item_indice": 1, "cantidad": 2}), DELIVERY))
    await uow.ejecutar("INSERT INTO pago(pedido_id,tipo,metodo_pago,monto,estado) "
        "VALUES(%s,'COBRO','EFECTIVO',10,'CONCILIADO')", (pid,))
    respuesta = await enviar(s, "fondos-confirmar", "confirmar")
    assert "guardad" not in respuesta.lower()
    actual = await s.repo.pedido(pid)
    assert actual["items"] == anterior["items"]
    assert actual["tipo_entrega"] == anterior["tipo_entrega"]
    assert actual["pagado"] == 10


async def test_worker_revierte_todo_si_falla_despues_de_guardar_el_conjunto(uow, monkeypatch):
    from contextlib import asynccontextmanager

    from app.modules.pedidos.infrastructure.repositorio_sql import RepositorioPedidosSQL
    from app.modules.whatsapp.presentation import procesamiento
    from tests.test_bot_edicion_completa import TELEFONO

    s, pid = await crear_pedido_bot(uow)
    anterior = await s.repo.pedido(pid)
    crispy = (CRISPY[0], {**CRISPY[1], "variante": "Simple"})
    assert "confirmar" in await enviar(s, "plan-rollback", "crispy y delivery",
        "editar_pedido", plan(crispy, DELIVERY))
    direcciones = await uow.valor("SELECT count(*) FROM direccion")
    await s.recibir("confirmar-rollback", TELEFONO, "confirmar")
    guardar = RepositorioPedidosSQL.guardar_edicion

    @asynccontextmanager
    async def conexion_local():
        async with uow.conn.transaction():
            yield uow.conn

    async def guardar_y_fallar(self, *args, **kwargs):
        await guardar(self, *args, **kwargs)
        raise RuntimeError("Fallo ficticio posterior a todas las escrituras")

    monkeypatch.setattr(procesamiento, "conexion", conexion_local)
    monkeypatch.setattr(RepositorioPedidosSQL, "guardar_edicion", guardar_y_fallar)
    await procesamiento.procesar_entrada("confirmar-rollback")
    assert await s.repo.pedido(pid) == anterior
    assert await uow.valor("SELECT count(*) FROM direccion") == direcciones
    entrada = await s.repo.entrada("confirmar-rollback")
    assert entrada["estado"] == "PROCESADO" and "No pude aplicar" in entrada["respuesta"]


async def test_derivacion_por_catalogo_no_disponible_persiste_estado_humano(uow, monkeypatch):
    from app.modules.whatsapp.application import edicion_conversacional

    s, pid = await crear_pedido_bot(uow)

    async def sin_catalogo(_bot):
        return []

    monkeypatch.setattr(edicion_conversacional, "catalogo", sin_catalogo)
    respuesta = await enviar(s, "sin-catalogo-plan", "crispy y delivery",
        "editar_pedido", plan(CRISPY, DELIVERY))
    assert "empleado" in respuesta
    estado = await uow.valor("SELECT estado FROM whatsapp_borrador WHERE pedido_id=%s", (pid,))
    assert estado == "HUMANO"
