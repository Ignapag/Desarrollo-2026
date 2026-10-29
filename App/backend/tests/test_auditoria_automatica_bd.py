"""Auditoría de escrituras SQL y conservación, en PostgreSQL descartable."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql


async def _categoria(uow):
    return await uow.valor(
        "INSERT INTO categoria(nombre) VALUES (%s) RETURNING id",
        (f"auditoria-{uuid4().hex}",),
    )


async def _ultimo(uow, entidad, entidad_id):
    return await uow.uno(
        "SELECT * FROM auditoria WHERE entidad=%s AND entidad_id=%s "
        "AND accion LIKE 'DATOS_%%' ORDER BY id DESC LIMIT 1",
        (entidad, str(entidad_id)),
    )


@pytest.mark.asyncio
async def test_sql_directo_registra_alta_y_cambio_antes_despues(uow):
    categoria_id = await _categoria(uow)
    alta = await _ultimo(uow, "categoria", categoria_id)
    assert alta is not None
    assert alta["accion"] == "DATOS_INSERTADOS"
    assert alta["datos"]["antes"] is None
    assert alta["datos"]["clave"] == {"id": categoria_id}
    assert alta["usuario_id"] is None
    assert alta["origen"].startswith("SQL:")
    assert alta["identificador_operacion"].startswith("sql:")
    assert alta["creado_en"].tzinfo is not None

    await uow.ejecutar("UPDATE categoria SET orden=42 WHERE id=%s", (categoria_id,))
    cambio = await _ultimo(uow, "categoria", categoria_id)
    assert cambio["accion"] == "DATOS_MODIFICADOS"
    assert cambio["datos"]["antes"]["orden"] == 0
    assert cambio["datos"]["despues"]["orden"] == 42
    assert cambio["datos"]["campos_modificados"] == ["orden"]


@pytest.mark.asyncio
async def test_actor_ip_origen_y_operacion_provienen_de_la_transaccion(uow):
    actor = await uow.valor("SELECT id FROM usuario ORDER BY id LIMIT 1")
    identificador = uuid4().hex
    await uow.ejecutar(
        "SELECT set_config('monu.usuario_id',%s,true), "
        "set_config('monu.ip','127.0.0.8',true), "
        "set_config('monu.origen','HTTP:PATCH /api/productos',true), "
        "set_config('monu.identificador_operacion',%s,true)",
        (str(actor), identificador),
    )
    categoria_id = await _categoria(uow)
    evento = await _ultimo(uow, "categoria", categoria_id)
    assert evento["usuario_id"] == actor
    assert str(evento["ip"]) == "127.0.0.8"
    assert evento["origen"] == "HTTP:PATCH /api/productos"
    assert evento["identificador_operacion"] == identificador


@pytest.mark.asyncio
async def test_update_sin_cambios_no_duplica_auditoria(uow):
    categoria_id = await _categoria(uow)
    anterior = await _ultimo(uow, "categoria", categoria_id)
    await uow.ejecutar("UPDATE categoria SET orden=orden WHERE id=%s", (categoria_id,))
    assert (await _ultimo(uow, "categoria", categoria_id))["id"] == anterior["id"]


@pytest.mark.asyncio
async def test_timestamp_de_actualizacion_solo_no_genera_falso_cambio(uow):
    producto_id = await uow.valor("SELECT id FROM producto ORDER BY id LIMIT 1")
    antes = await uow.valor(
        "SELECT count(*) FROM auditoria WHERE entidad='producto' AND entidad_id=%s",
        (str(producto_id),),
    )
    await uow.ejecutar(
        "UPDATE producto SET actualizado_en=clock_timestamp() WHERE id=%s", (producto_id,)
    )
    assert await uow.valor(
        "SELECT count(*) FROM auditoria WHERE entidad='producto' AND entidad_id=%s",
        (str(producto_id),),
    ) == antes


@pytest.mark.asyncio
async def test_baja_y_reactivacion_preservan_ambas_imagenes(uow):
    categoria_id = await _categoria(uow)
    await uow.ejecutar("UPDATE categoria SET activa=false WHERE id=%s", (categoria_id,))
    baja = await _ultimo(uow, "categoria", categoria_id)
    assert baja["datos"]["antes"]["activa"] is True
    assert baja["datos"]["despues"]["activa"] is False
    await uow.ejecutar("UPDATE categoria SET activa=true WHERE id=%s", (categoria_id,))
    alta = await _ultimo(uow, "categoria", categoria_id)
    assert alta["datos"]["antes"]["activa"] is False
    assert alta["datos"]["despues"]["activa"] is True


@pytest.mark.asyncio
async def test_clave_compuesta_y_baja_logica_de_permiso(uow):
    fila = await uow.uno(
        "SELECT rol,permiso FROM rol_permiso WHERE eliminado_en IS NULL LIMIT 1"
    )
    await uow.ejecutar(
        "UPDATE rol_permiso SET eliminado_en=now() WHERE rol=%s AND permiso=%s",
        (fila["rol"], fila["permiso"]),
    )
    evento = await uow.uno(
        "SELECT datos FROM auditoria WHERE entidad='rol_permiso' "
        "AND accion='DATOS_MODIFICADOS' ORDER BY id DESC LIMIT 1"
    )
    assert evento["datos"]["clave"] == fila
    assert evento["datos"]["antes"]["eliminado_en"] is None
    assert evento["datos"]["despues"]["eliminado_en"] is not None


@pytest.mark.asyncio
async def test_credenciales_se_auditan_sin_copiar_sus_valores(uow):
    usuario_id = await uow.valor(
        "INSERT INTO usuario(nombre,apellido,username,password_hash,rol) "
        "VALUES ('Auditoria','Prueba',%s,'valor-credencial-anterior','EMPLEADO') RETURNING id",
        (f"auditoria-{uuid4().hex}",),
    )
    await uow.ejecutar(
        "UPDATE usuario SET password_hash='valor-credencial-nuevo' WHERE id=%s", (usuario_id,)
    )
    evento = await _ultimo(uow, "usuario", usuario_id)
    datos = evento["datos"]
    assert "password_hash" in datos["campos_modificados"]
    assert "password_hash" not in datos["antes"]
    assert "password_hash" not in datos["despues"]
    assert "valor-credencial" not in json.dumps(datos)


@pytest.mark.asyncio
async def test_json_libre_no_filtra_secretos_al_log(uow):
    clave = f"auditoria-{uuid4().hex}"
    await uow.ejecutar(
        "INSERT INTO parametro(clave,valor) VALUES (%s,%s)",
        (clave, '{"token":"marcador-no-debe-aparecer"}'),
    )
    evento = await _ultimo(uow, "parametro", clave)
    assert evento is not None
    assert "valor" not in evento["datos"]["despues"]
    assert "marcador-no-debe-aparecer" not in json.dumps(evento["datos"])


@pytest.mark.asyncio
async def test_parametro_de_negocio_conocido_guarda_valor_anterior_y_nuevo(uow):
    clave = "pedido.minutos_cancelacion"
    anterior = await uow.valor("SELECT valor FROM parametro WHERE clave=%s", (clave,))
    await uow.ejecutar("UPDATE parametro SET valor='6' WHERE clave=%s", (clave,))
    evento = await _ultimo(uow, "parametro", clave)
    assert evento["datos"]["antes"]["valor"] == anterior
    assert evento["datos"]["despues"]["valor"] == "6"


@pytest.mark.asyncio
async def test_texto_de_plantilla_es_dato_de_negocio_auditable(uow):
    plantilla_id = await uow.valor("SELECT id FROM notificacion_plantilla ORDER BY id LIMIT 1")
    anterior = await uow.valor(
        "SELECT cuerpo FROM notificacion_plantilla WHERE id=%s", (plantilla_id,)
    )
    await uow.ejecutar(
        "UPDATE notificacion_plantilla SET cuerpo='Su pedido esta listo' WHERE id=%s",
        (plantilla_id,),
    )
    evento = await _ultimo(uow, "notificacion_plantilla", plantilla_id)
    assert evento["datos"]["antes"]["cuerpo"] == anterior
    assert evento["datos"]["despues"]["cuerpo"] == "Su pedido esta listo"


@pytest.mark.asyncio
async def test_imagen_embebida_no_se_copia_al_log(uow):
    producto_id = await uow.valor("SELECT id FROM producto ORDER BY id LIMIT 1")
    await uow.ejecutar(
        "UPDATE producto SET imagen_url='data:image/png;base64,contenido-binario' WHERE id=%s",
        (producto_id,),
    )
    evento = await _ultimo(uow, "producto", producto_id)
    assert "imagen_url" in evento["datos"]["campos_modificados"]
    assert "contenido-binario" not in json.dumps(evento["datos"])


@pytest.mark.asyncio
async def test_json_de_variantes_solo_proyecta_campos_de_negocio(uow):
    producto_id = await uow.valor("SELECT id FROM producto ORDER BY id LIMIT 1")
    variantes = [{
        "nombre": "Prueba", "precio": 17000, "token": "secreto-en-json",
        "ingredientes": [{"ingrediente_id": 1, "cantidad_requerida": "1", "api_key": "oculta"}],
    }]
    await uow.ejecutar(
        "UPDATE producto SET variantes=%s::jsonb WHERE id=%s",
        (json.dumps(variantes), producto_id),
    )
    evento = await _ultimo(uow, "producto", producto_id)
    despues = evento["datos"]["despues"]["variantes"]
    assert despues == [{
        "nombre": "Prueba", "precio": 17000,
        "ingredientes": [{"ingrediente_id": 1, "cantidad_requerida": "1"}],
    }]
    assert "secreto-en-json" not in json.dumps(evento["datos"])
    assert "oculta" not in json.dumps(evento["datos"])


@pytest.mark.asyncio
async def test_referencia_de_borrador_se_pseudonimiza_en_clave_y_no_se_copia(uow):
    referencia = uuid4().hex
    await uow.ejecutar(
        "INSERT INTO whatsapp_borrador(referencia_hash,items) VALUES (%s,'[]')", (referencia,)
    )
    evento = await uow.uno(
        "SELECT * FROM auditoria WHERE entidad='whatsapp_borrador' "
        "AND accion='DATOS_INSERTADOS' ORDER BY id DESC LIMIT 1"
    )
    assert evento["entidad_id"].startswith("sha256:")
    assert evento["datos"]["clave"]["referencia_hash"] == evento["entidad_id"]
    assert referencia not in json.dumps(evento["datos"])
    assert "referencia_hash" not in evento["datos"]["despues"]


@pytest.mark.asyncio
async def test_poligono_conserva_coordenadas_sin_propiedades_libres(uow):
    zona_id = await uow.valor("SELECT id FROM zona_cobertura ORDER BY id LIMIT 1")
    anterior = await uow.valor("SELECT poligono FROM zona_cobertura WHERE id=%s", (zona_id,))
    poligono = {
        "type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]],
        "token": "no-exportar-geometria",
    }
    await uow.ejecutar(
        "UPDATE zona_cobertura SET poligono=%s::jsonb WHERE id=%s",
        (json.dumps(poligono), zona_id),
    )
    evento = await _ultimo(uow, "zona_cobertura", zona_id)
    assert evento["datos"]["antes"]["poligono"] == anterior
    assert evento["datos"]["despues"]["poligono"] == {
        "type": "Polygon", "coordinates": poligono["coordinates"],
    }
    assert "no-exportar-geometria" not in json.dumps(evento["datos"])


@pytest.mark.asyncio
async def test_poligono_con_coordenada_no_numerica_no_filtra_contenido(uow):
    zona_id = await uow.valor("SELECT id FROM zona_cobertura ORDER BY id LIMIT 1")
    poligono = {"type": "Polygon", "coordinates": [[["secreto-en-coordenada", 0]] ]}
    await uow.ejecutar(
        "UPDATE zona_cobertura SET poligono=%s::jsonb WHERE id=%s",
        (json.dumps(poligono), zona_id),
    )
    evento = await _ultimo(uow, "zona_cobertura", zona_id)
    assert "poligono" in evento["datos"]["campos_modificados"]
    assert "secreto-en-coordenada" not in json.dumps(evento["datos"])


@pytest.mark.asyncio
async def test_borrador_audita_contacto_direccion_y_propuesta_tipados(uow):
    referencia = uuid4().hex
    contacto = {"nombre": "Ana", "apellido": "Perez", "telefono": "5492211234567",
                "token": "no-exportar-contacto"}
    direccion = {"calle": "Uno", "numero": "12", "localidad": "Centro",
                 "referencia": "Esquina", "password": "no-exportar-direccion"}
    propuesta = {"tipo": "TOTAL", "version": 1, "total": "12000",
                 "accion": {"accion": "cantidad", "argumentos": {"cantidad": 2}},
                 "cambios": {"tipo_entrega": "RETIRO"}, "token": "no-exportar-propuesta"}
    await uow.ejecutar(
        "INSERT INTO whatsapp_borrador(referencia_hash,items,contacto,direccion,propuesta) "
        "VALUES (%s,'[]',%s::jsonb,%s::jsonb,%s::jsonb)",
        (referencia, json.dumps(contacto), json.dumps(direccion), json.dumps(propuesta)),
    )
    evento = await uow.uno(
        "SELECT datos FROM auditoria WHERE entidad='whatsapp_borrador' "
        "AND accion='DATOS_INSERTADOS' ORDER BY id DESC LIMIT 1"
    )
    despues = evento["datos"]["despues"]
    assert despues["contacto"] == {k: v for k, v in contacto.items() if k != "token"}
    assert despues["direccion"] == {k: v for k, v in direccion.items() if k != "password"}
    assert despues["propuesta"] == {k: v for k, v in propuesta.items() if k != "token"}
    assert "no-exportar" not in json.dumps(evento["datos"])


@pytest.mark.asyncio
async def test_historial_whatsapp_audita_accion_y_fotos_sin_campos_tecnicos(uow):
    cliente_id = await uow.valor("SELECT id FROM cliente ORDER BY id LIMIT 1")
    pedido_id = await uow.valor(
        "INSERT INTO pedido(cliente_id,tipo_entrega) VALUES (%s,'RETIRO') RETURNING id",
        (cliente_id,),
    )
    accion = {"accion": "cantidad", "argumentos": {"cantidad": 2, "item_id": 7,
              "token": "no-exportar-argumento"}, "revision_motivo": "Cambio confirmado"}
    anterior = {"item_id": 7, "cantidad": 1, "total": "10000", "password_hash": "reservado"}
    posterior = {"cantidad": 2, "total": "20000", "token": "no-exportar-posterior"}
    cambio_id = await uow.valor(
        "INSERT INTO whatsapp_cambio(pedido_id,version,accion,anterior,posterior,estado) "
        "VALUES (%s,1,%s::jsonb,%s::jsonb,%s::jsonb,'APLICADO') RETURNING id",
        (pedido_id, json.dumps(accion), json.dumps(anterior), json.dumps(posterior)),
    )
    evento = await _ultimo(uow, "whatsapp_cambio", cambio_id)
    despues = evento["datos"]["despues"]
    assert despues["accion"] == {"accion": "cantidad", "argumentos": {"cantidad": 2,
                                  "item_id": 7}, "revision_motivo": "Cambio confirmado"}
    assert despues["anterior"] == {"item_id": 7, "cantidad": 1, "total": "10000"}
    assert despues["posterior"] == {"cantidad": 2, "total": "20000"}
    assert "no-exportar" not in json.dumps(evento["datos"])
    assert "reservado" not in json.dumps(evento["datos"])


@pytest.mark.asyncio
async def test_cambios_de_historial_conservan_deltas_tipados_y_excluyen_desconocidos(uow):
    cliente_id = await uow.valor("SELECT id FROM cliente ORDER BY id LIMIT 1")
    pedido_id = await uow.valor(
        "INSERT INTO pedido(cliente_id,tipo_entrega) VALUES (%s,'RETIRO') RETURNING id",
        (cliente_id,),
    )
    cambios = {
        "tipo_entrega": {"anterior": "DELIVERY", "nuevo": "RETIRO"},
        "items": {"anterior": [{"id": 7, "cantidad": 1}],
                  "nuevo": [{"id": 7, "cantidad": 2, "token": "no-exportar-item"}]},
        "token": {"anterior": "no-exportar-antes", "nuevo": "no-exportar-despues"},
    }
    historial_id = await uow.valor(
        "INSERT INTO pedido_estado_historial(pedido_id,estado_nuevo,cambios) "
        "VALUES (%s,'PENDIENTE',%s::jsonb) RETURNING id", (pedido_id, json.dumps(cambios)),
    )
    evento = await _ultimo(uow, "pedido_estado_historial", historial_id)
    assert evento["datos"]["despues"]["cambios"] == {
        "tipo_entrega": {"anterior": "DELIVERY", "nuevo": "RETIRO"},
        "items": {"anterior": [{"id": 7, "cantidad": 1}],
                  "nuevo": [{"id": 7, "cantidad": 2}]},
    }
    assert "no-exportar" not in json.dumps(evento["datos"])


@pytest.mark.asyncio
async def test_campos_json_con_tipo_incorrecto_no_exportan_objetos_arbitrarios(uow):
    referencia = uuid4().hex
    await uow.ejecutar(
        "INSERT INTO whatsapp_borrador(referencia_hash,items,contacto) VALUES (%s,'[]',%s::jsonb)",
        (referencia, json.dumps({"nombre": {"token": "no-exportar-tipo-invalido"},
                                "telefono": ["no-exportar-array"]})),
    )
    evento = await uow.uno(
        "SELECT datos FROM auditoria WHERE entidad='whatsapp_borrador' "
        "AND accion='DATOS_INSERTADOS' ORDER BY id DESC LIMIT 1"
    )
    assert evento["datos"]["despues"]["contacto"] == {}
    assert "no-exportar" not in json.dumps(evento["datos"])


@pytest.mark.asyncio
@pytest.mark.parametrize("tabla", ["whatsapp_atencion", "whatsapp_comprobante"])
async def test_entrada_demo_se_pseudonimiza_en_columnas_de_auditoria(uow, tabla):
    entrada_id = f"web:{uuid4().hex}:{uuid4().hex}"
    await uow.ejecutar(
        "INSERT INTO whatsapp_entrada(id,telefono,texto) VALUES(%s,'5492211234567','Prueba')",
        (entrada_id,),
    )
    if tabla == "whatsapp_atencion":
        entidad_id = await uow.valor(
            "INSERT INTO whatsapp_atencion(entrada_id,telefono,motivo) "
            "VALUES(%s,'5492211234567','SOLICITUD') RETURNING id", (entrada_id,),
        )
    else:
        cliente_id = await uow.valor("SELECT id FROM cliente ORDER BY id LIMIT 1")
        pedido_id = await uow.valor(
            "INSERT INTO pedido(cliente_id,tipo_entrega) VALUES(%s,'RETIRO') RETURNING id",
            (cliente_id,),
        )
        entidad_id = await uow.valor(
            "INSERT INTO whatsapp_comprobante(entrada_id,pedido_id,media_id) "
            "VALUES(%s,%s,'archivo-prueba') RETURNING id", (entrada_id, pedido_id),
        )
    evento = await _ultimo(uow, tabla, entidad_id)
    entrada_auditada = evento["datos"]["despues"]["entrada_id"]
    assert entrada_auditada.startswith("sha256:")
    assert entrada_id not in json.dumps(evento["datos"])
    assert entrada_id.split(":")[1] not in json.dumps(evento["datos"])


@pytest.mark.asyncio
@pytest.mark.parametrize("demo", [False, True])
async def test_entrada_demo_en_json_se_pseudonimiza_sin_ocultar_ids_meta(uow, demo):
    entrada_id = f"web:{uuid4().hex}:{uuid4().hex}" if demo else f"wamid.{uuid4().hex}"
    cliente_id = await uow.valor("SELECT id FROM cliente ORDER BY id LIMIT 1")
    pedido_id = await uow.valor(
        "INSERT INTO pedido(cliente_id,tipo_entrega) VALUES(%s,'RETIRO') RETURNING id",
        (cliente_id,),
    )
    cambio_id = await uow.valor(
        "INSERT INTO whatsapp_cambio(pedido_id,version,accion,anterior,posterior,estado) "
        "VALUES(%s,1,%s::jsonb,'{}','{}','APLICADO') RETURNING id",
        (pedido_id, json.dumps({"accion": "cantidad", "entrada_id": entrada_id})),
    )
    evento = await _ultimo(uow, "whatsapp_cambio", cambio_id)
    entrada_auditada = evento["datos"]["despues"]["accion"]["entrada_id"]
    if demo:
        assert entrada_auditada.startswith("sha256:")
        assert entrada_id.split(":")[1] not in json.dumps(evento["datos"])
    else:
        assert entrada_auditada == entrada_id


@pytest.mark.asyncio
async def test_rollback_revierte_cambio_y_evento(uow):
    categoria_id = await _categoria(uow)
    anterior = await _ultimo(uow, "categoria", categoria_id)
    await uow.ejecutar("SAVEPOINT cambio_auditado")
    await uow.ejecutar("UPDATE categoria SET orden=99 WHERE id=%s", (categoria_id,))
    assert (await _ultimo(uow, "categoria", categoria_id))["id"] != anterior["id"]
    await uow.ejecutar("ROLLBACK TO SAVEPOINT cambio_auditado")
    assert (await _ultimo(uow, "categoria", categoria_id))["id"] == anterior["id"]
    assert await uow.valor("SELECT orden FROM categoria WHERE id=%s", (categoria_id,)) == 0


@pytest.mark.asyncio
async def test_delete_operativo_rechazado_y_registro_conservado(uow):
    categoria_id = await _categoria(uow)
    async with uow.conn.transaction():
        with pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState):
            async with uow.conn.transaction():
                await uow.ejecutar("DELETE FROM categoria WHERE id=%s", (categoria_id,))
    assert await uow.valor("SELECT id FROM categoria WHERE id=%s", (categoria_id,)) == categoria_id


@pytest.mark.asyncio
async def test_truncate_operativo_rechazado_incluso_sin_filas(uow):
    with pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState):
        async with uow.conn.transaction():
            await uow.ejecutar("TRUNCATE rol_permiso")


@pytest.mark.asyncio
@pytest.mark.parametrize("operacion", [
    "UPDATE auditoria SET accion='alterada' WHERE id=%s",
    "DELETE FROM auditoria WHERE id=%s",
])
async def test_log_no_puede_alterarse_ni_borrarse(uow, operacion):
    categoria_id = await _categoria(uow)
    evento = await _ultimo(uow, "categoria", categoria_id)
    with pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState):
        async with uow.conn.transaction():
            await uow.ejecutar(operacion, (evento["id"],))


@pytest.mark.asyncio
async def test_contexto_local_no_sobrevive_al_rollback_de_savepoint(uow):
    await uow.ejecutar("SAVEPOINT contexto_temporal")
    await uow.ejecutar("SELECT set_config('monu.origen','PRUEBA_TEMPORAL',true)")
    await uow.ejecutar("ROLLBACK TO SAVEPOINT contexto_temporal")
    categoria_id = await _categoria(uow)
    assert (await _ultimo(uow, "categoria", categoria_id))["origen"] != "PRUEBA_TEMPORAL"


@pytest.mark.asyncio
async def test_migracion_y_triggers_respetan_esquema_aislado_y_search_path(uow):
    esquema = f"auditoria_{uuid4().hex}"
    eventos_publicos = await uow.valor("SELECT count(*) FROM public.auditoria")
    await uow.conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(esquema)))
    await uow.conn.execute(
        sql.SQL("SET LOCAL search_path TO {},public").format(sql.Identifier(esquema))
    )
    migraciones = Path(__file__).resolve().parents[2] / "db" / "migrations"
    for archivo in sorted(migraciones.glob("*.sql")):
        await uow.conn.execute(archivo.read_text(encoding="utf-8"))
    categoria_id = await _categoria(uow)
    evento = await _ultimo(uow, "categoria", categoria_id)
    assert evento["datos"]["clave"] == {"id": categoria_id}
    assert await uow.valor("SELECT count(*) FROM public.auditoria") == eventos_publicos

    # El llamador puede cambiar search_path; el trigger debe conservar el suyo.
    await uow.conn.execute("SET LOCAL search_path TO public")
    await uow.conn.execute(
        sql.SQL("UPDATE {}.categoria SET orden=87 WHERE id=%s").format(sql.Identifier(esquema)),
        (categoria_id,),
    )
    cursor = await uow.conn.execute(
        sql.SQL("SELECT datos FROM {}.auditoria WHERE entidad='categoria' "
                "ORDER BY id DESC LIMIT 1").format(sql.Identifier(esquema))
    )
    evento = await cursor.fetchone()
    assert evento["datos"]["despues"]["orden"] == 87
    assert await uow.valor("SELECT count(*) FROM public.auditoria") == eventos_publicos
