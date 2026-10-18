"""Identidad comercial independiente del acceso autenticado y sus permisos."""

from pathlib import Path
from uuid import uuid4

import httpx
import psycopg
import pytest
from psycopg import sql

from app.errores import DatosInvalidos
from app.main import app
from app.modules.delivery.infrastructure.repositorio_sql import RepositorioDeliverySQL
from app.modules.pedidos.application.servicio_pedidos import ServicioPedidos
from app.modules.pedidos.infrastructure.repositorio_sql import RepositorioPedidosSQL
from app.modules.pedidos.presentation.dependencias import obtener_servicio_pedidos
from app.modules.usuarios.domain.entidades import ClaimsSesion, Rol
from app.modules.usuarios.presentation.dependencias import usuario_actual
from app.modules.whatsapp.infrastructure.cola import ColaWhatsAppSQL


@pytest.mark.asyncio
async def test_cliente_huesped_activo_y_detalle_sin_usuario(uow):
    cliente_id = await uow.valor(
        "INSERT INTO cliente (nombre, telefono_whatsapp, whatsapp_verificado) "
        "VALUES ('Invitada', '5492211234567', '5492211234567') RETURNING id"
    )
    repo = RepositorioPedidosSQL(uow)
    assert await repo.cliente_valido(cliente_id)
    pedido_id = await uow.valor(
        "INSERT INTO pedido (cliente_id, tipo_entrega) VALUES (%s, 'RETIRO') RETURNING id",
        (cliente_id,),
    )
    assert (await repo.detalle(pedido_id))["cliente"] == "Invitada"
    assert pedido_id in [p["id"] for p in await repo.listar(cliente_id=cliente_id)]
    await uow.ejecutar("UPDATE cliente SET estado='INACTIVO' WHERE id=%s", (cliente_id,))
    assert not await repo.cliente_valido(cliente_id)


@pytest.mark.asyncio
async def test_usuario_y_cliente_con_ids_distintos_se_resuelven_explicitamente(uow):
    usuario_id = await uow.valor(
        "INSERT INTO usuario (nombre, apellido, username, password_hash, rol) "
        "VALUES ('Cuenta', 'Anterior', %s, 'x', 'CLIENTE') RETURNING id",
        (uuid4().hex,),
    )
    cliente_id = await uow.valor(
        "INSERT INTO cliente (id, usuario_id, nombre, telefono_whatsapp) "
        "VALUES (%s, %s, 'Nombre comercial', '5492211234567') RETURNING id",
        (usuario_id + 1000000, usuario_id),
    )
    repo = RepositorioPedidosSQL(uow)
    servicio = ServicioPedidos(repo, None)
    assert await servicio.cliente_para_usuario(usuario_id) == cliente_id
    assert await repo.cliente_valido(cliente_id)
    pedido_id = await uow.valor(
        "INSERT INTO pedido (cliente_id, tipo_entrega) VALUES (%s, 'RETIRO') RETURNING id",
        (cliente_id,),
    )
    app.dependency_overrides[usuario_actual] = lambda: ClaimsSesion(
        usuario_id, Rol.CLIENTE, "cuenta"
    )
    app.dependency_overrides[obtener_servicio_pedidos] = lambda: servicio
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as navegador:
            respuesta = await navegador.get("/api/pedidos")
        assert respuesta.status_code == 200
        assert [pedido["id"] for pedido in respuesta.json()] == [pedido_id]
    finally:
        app.dependency_overrides.pop(usuario_actual, None)
        app.dependency_overrides.pop(obtener_servicio_pedidos, None)
    await uow.ejecutar("UPDATE usuario SET estado='INACTIVO' WHERE id=%s", (usuario_id,))
    assert not await repo.cliente_valido(cliente_id)
    with pytest.raises(DatosInvalidos):
        await servicio.cliente_para_usuario(usuario_id)


@pytest.mark.asyncio
async def test_usuario_sin_cliente_comercial_no_se_convierte_en_historial_global(uow):
    with pytest.raises(DatosInvalidos):
        await ServicioPedidos(RepositorioPedidosSQL(uow), None).cliente_para_usuario(999999999)


@pytest.mark.asyncio
async def test_repartidor_no_crea_pedido_ni_cambia_estado_manualmente():
    app.dependency_overrides[usuario_actual] = lambda: ClaimsSesion(1, Rol.REPARTIDOR, "reparto")
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as cliente:
            respuesta = await cliente.post(
                "/api/pedidos", json={"tipo_entrega": "RETIRO", "items": []}
            )
            assert respuesta.status_code == 403
            respuesta = await cliente.patch(
                "/api/pedidos/1/estado", json={"estado": "CANCELADO"}
            )
            assert respuesta.status_code == 403
    finally:
        app.dependency_overrides.pop(usuario_actual, None)


@pytest.mark.asyncio
async def test_borrador_anonimo_no_requiere_usuario_ni_telefono(uow):
    referencia = uuid4().hex
    await uow.ejecutar(
        "INSERT INTO whatsapp_borrador (referencia_hash, items) VALUES (%s, '[]')",
        (referencia,),
    )
    borrador = await uow.uno(
        "SELECT cliente_id, telefono FROM whatsapp_borrador WHERE referencia_hash=%s",
        (referencia,),
    )
    assert borrador == {"cliente_id": None, "telefono": None}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "datos",
    [
        {"estado": "INVALIDO"},
        {"whatsapp_verificado": "12345"},
        {"whatsapp_verificado": "+5492211234567"},
    ],
)
async def test_cliente_rechaza_estado_o_numero_verificado_invalido(uow, datos):
    with pytest.raises(psycopg.errors.CheckViolation):
        await uow.conn.execute(
            sql.SQL(
                "INSERT INTO cliente (nombre, telefono_whatsapp, {}) "
                "VALUES ('Invitada', '5492211234567', %s)"
            ).format(sql.Identifier(next(iter(datos)))),
            (next(iter(datos.values())),),
        )


@pytest.mark.asyncio
async def test_cliente_no_comparte_whatsapp_verificado_con_otro_cliente(uow):
    await uow.ejecutar(
        "INSERT INTO cliente (nombre, telefono_whatsapp, whatsapp_verificado) "
        "VALUES ('Primera', '5492211234567', '5492211234567')"
    )
    with pytest.raises(psycopg.errors.UniqueViolation):
        await uow.ejecutar(
            "INSERT INTO cliente (nombre, telefono_whatsapp, whatsapp_verificado) "
            "VALUES ('Segunda', '5492211234567', '5492211234567')"
        )


@pytest.mark.asyncio
async def test_borrador_no_admite_identidad_parcial(uow):
    with pytest.raises(psycopg.errors.CheckViolation):
        await uow.ejecutar(
            "INSERT INTO whatsapp_borrador (referencia_hash, telefono, items) "
            "VALUES (%s, '5492211234567', '[]')",
            (uuid4().hex,),
        )


@pytest.mark.asyncio
async def test_migracion_preserva_identidad_y_referencias_historicas(uow):
    """Verifica identidad en 015 y lectura actual tras migrar el esquema aislado."""
    esquema = sql.Identifier("identidad_" + uuid4().hex)
    await uow.conn.execute(sql.SQL("CREATE SCHEMA {}").format(esquema))
    await uow.conn.execute(sql.SQL("SET LOCAL search_path TO {}, public").format(esquema))
    migraciones = Path(__file__).resolve().parents[2] / "db" / "migrations"
    for archivo in sorted(migraciones.glob("*.sql")):
        if archivo.name.startswith("015_"):
            break
        await uow.conn.execute(archivo.read_text(encoding="utf-8"))
    usuario_id = await uow.valor(
        "INSERT INTO usuario (nombre, apellido, username, password_hash, rol, estado) "
        "VALUES ('Ana', 'Histórica', 'historica', 'x', 'CLIENTE', 'INACTIVO') RETURNING id"
    )
    await uow.ejecutar(
        "INSERT INTO cliente (usuario_id, telefono_whatsapp, notas, acepta_notif_wsp) "
        "VALUES (%s, '5492211234567', 'Conservar', false)",
        (usuario_id,),
    )
    await uow.ejecutar(
        "INSERT INTO direccion (cliente_id, calle, numero) VALUES (%s, 'Histórica', '123')",
        (usuario_id,),
    )
    pedido_id = await uow.valor(
        "INSERT INTO pedido (cliente_id, tipo_entrega) VALUES (%s, 'RETIRO') RETURNING id",
        (usuario_id,),
    )
    await uow.ejecutar(
        "INSERT INTO notificacion (cliente_id, clave, destinatario, cuerpo_renderizado) "
        "VALUES (%s, 'BIENVENIDA', '5492211234567', 'Histórica')",
        (usuario_id,),
    )
    await uow.ejecutar(
        "INSERT INTO whatsapp_borrador "
        "(referencia_hash, cliente_id, telefono, items, pedido_id) "
        "VALUES ('historica', %s, '5492211234567', '[]', %s)",
        (usuario_id, pedido_id),
    )
    await uow.conn.execute(
        (migraciones / "015_clientes_sin_cuenta.sql").read_text(encoding="utf-8")
    )
    cliente = await uow.uno("SELECT * FROM cliente WHERE id=%s", (usuario_id,))
    assert cliente["usuario_id"] == usuario_id
    assert cliente["nombre"] == "Ana Histórica"
    assert cliente["estado"] == "INACTIVO"
    assert cliente["telefono_whatsapp"] == "5492211234567"
    assert cliente["whatsapp_verificado"] is None
    assert cliente["notas"] == "Conservar"
    assert cliente["acepta_notif_wsp"] is False
    for tabla in ("pedido", "direccion", "notificacion", "whatsapp_borrador"):
        async with uow.conn.cursor() as cursor:
            await cursor.execute(sql.SQL("SELECT cliente_id FROM {}").format(sql.Identifier(tabla)))
            assert (await cursor.fetchone())["cliente_id"] == usuario_id
    nuevo = await uow.valor(
        "INSERT INTO cliente (nombre, telefono_whatsapp) "
        "VALUES ('Huésped', '5492211234567') RETURNING id"
    )
    assert nuevo > usuario_id
    for archivo in sorted(migraciones.glob("*.sql")):
        if int(archivo.name.split("_", 1)[0]) > 15:
            await uow.conn.execute(archivo.read_text(encoding="utf-8"))
    pedido = await RepositorioPedidosSQL(uow).detalle(pedido_id)
    assert pedido["id"] == pedido_id
    assert pedido["cliente_id"] == usuario_id
    assert pedido["cliente"] == "Ana Histórica"


@pytest.mark.asyncio
async def test_delivery_incluye_cliente_huesped_sin_cuenta(uow):
    cliente_id = await uow.valor(
        "INSERT INTO cliente (nombre, telefono_whatsapp) "
        "VALUES ('Invitada delivery', '5492211234567') RETURNING id"
    )
    pedido_id = await uow.valor(
        "INSERT INTO pedido (cliente_id, tipo_entrega) VALUES (%s, 'RETIRO') RETURNING id",
        (cliente_id,),
    )
    repartidor_id = await uow.valor("SELECT usuario_id FROM repartidor LIMIT 1")
    viaje_id = await uow.valor(
        "INSERT INTO viaje (repartidor_id) VALUES (%s) RETURNING id", (repartidor_id,)
    )
    await uow.ejecutar(
        "INSERT INTO envio (pedido_id, viaje_id, orden_en_viaje) VALUES (%s, %s, 1)",
        (pedido_id, viaje_id),
    )
    envios = await RepositorioDeliverySQL(uow).envios_del_viaje(viaje_id)
    assert len(envios) == 1
    assert envios[0]["cliente_nombre"] == "Invitada delivery"
    assert envios[0]["telefono_cliente"] == "5492211234567"


@pytest.mark.asyncio
async def test_bandeja_interna_incluye_atencion_de_cliente_sin_cuenta(uow):
    cliente_id = await uow.valor(
        "INSERT INTO cliente (nombre, telefono_whatsapp) "
        "VALUES ('Invitada atención', '5492211234567') RETURNING id"
    )
    referencia = uuid4().hex
    entrada = uuid4().hex
    await uow.ejecutar(
        "INSERT INTO whatsapp_borrador (referencia_hash, cliente_id, telefono, items) "
        "VALUES (%s, %s, '5492211234567', '[]')",
        (referencia, cliente_id),
    )
    await uow.ejecutar(
        "INSERT INTO whatsapp_entrada (id, telefono, texto, referencia_hash) "
        "VALUES (%s, '5492211234567', 'Necesito ayuda', %s)",
        (entrada, referencia),
    )
    atencion_id = await uow.valor(
        "INSERT INTO whatsapp_atencion (referencia_hash, entrada_id, motivo) "
        "VALUES (%s, %s, 'SOLICITUD') RETURNING id",
        (referencia, entrada),
    )
    atenciones = (await ColaWhatsAppSQL(uow).bandeja())["atenciones"]
    atencion = next(a for a in atenciones if a["id"] == atencion_id)
    assert atencion["cliente"] == "Invitada atención"
    assert atencion["mensaje"] == "Necesito ayuda"


@pytest.mark.asyncio
async def test_repartidor_consulta_solo_envios_pendientes_de_su_viaje_activo(uow):
    cliente_id = await uow.valor(
        "INSERT INTO cliente (nombre, telefono_whatsapp) "
        "VALUES ('Invitada reparto', '5492211234567') RETURNING id"
    )
    repartidores = await uow.todos("SELECT usuario_id FROM repartidor ORDER BY usuario_id LIMIT 2")
    propio, ajeno = [r["usuario_id"] for r in repartidores]
    pedidos = []
    for repartidor, estado_viaje, estado_envio in (
        (propio, "FINALIZADO", "ENTREGADO"),
        (propio, "PLANIFICADO", "ASIGNADO"),
        (propio, "PLANIFICADO", "ENTREGADO"),
        (ajeno, "PLANIFICADO", "ASIGNADO"),
    ):
        pedido_id = await uow.valor(
            "INSERT INTO pedido (cliente_id, tipo_entrega) VALUES (%s, 'RETIRO') RETURNING id",
            (cliente_id,),
        )
        pedidos.append(pedido_id)
        viaje_id = await uow.valor(
            "SELECT id FROM viaje WHERE repartidor_id=%s AND estado=%s",
            (repartidor, estado_viaje),
        )
        if viaje_id is None:
            viaje_id = await uow.valor(
                "INSERT INTO viaje (repartidor_id, estado) VALUES (%s, %s) RETURNING id",
                (repartidor, estado_viaje),
            )
        await uow.ejecutar(
            "INSERT INTO envio (pedido_id, viaje_id, estado) VALUES (%s, %s, %s)",
            (pedido_id, viaje_id, estado_envio),
        )
    sin_envio = await uow.valor(
        "INSERT INTO pedido (cliente_id, tipo_entrega) VALUES (%s, 'RETIRO') RETURNING id",
        (cliente_id,),
    )
    servicio = ServicioPedidos(RepositorioPedidosSQL(uow), None)
    app.dependency_overrides[usuario_actual] = lambda: ClaimsSesion(
        propio, Rol.REPARTIDOR, "repartidor"
    )
    app.dependency_overrides[obtener_servicio_pedidos] = lambda: servicio
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as navegador:
            respuesta = await navegador.get("/api/pedidos", params={"repartidor_id": ajeno})
        assert respuesta.status_code == 200
        assert [p["id"] for p in respuesta.json()] == [pedidos[1]]
        assert sin_envio not in [p["id"] for p in respuesta.json()]
    finally:
        app.dependency_overrides.pop(usuario_actual, None)
        app.dependency_overrides.pop(obtener_servicio_pedidos, None)
    assert await servicio.listar(cliente_id=cliente_id + 1000000, repartidor_id=propio) == []
    await uow.ejecutar("UPDATE viaje SET estado='FINALIZADO' WHERE repartidor_id=%s", (propio,))
    assert await servicio.listar(repartidor_id=propio) == []
