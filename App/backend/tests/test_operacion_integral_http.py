"""Recorridos del panel con ASGI, PostgreSQL y commits reales por request.

Sin overrides: sólo el consumidor asíncrono de WhatsApp se invoca como helper,
con una interpretación determinista y su propia transacción, sin proveedores.
Los fixtures SQL preparan actores, catálogo y cobertura; nunca pedidos o pagos.
"""

from dataclasses import dataclass
from decimal import Decimal
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio

from app.core.config import settings
from app.core.db import UnidadDeTrabajo, abrir_pool, cerrar_pool, conexion
from app.core.seguridad import hashear_password
from app.main import app
from app.modules.whatsapp.presentation.dependencias import construir_servicio
from tests.soporte_bd import exigir_base_descartable

PASSWORD = "HttpIntegral2026!"


async def solicitud(api, metodo, ruta, *, esperado=200, **datos):
    respuesta = await api.request(metodo, ruta, **datos)
    assert respuesta.status_code == esperado, (ruta, respuesta.status_code, respuesta.text)
    return respuesta.json()


async def consultar(sql, parametros=None):
    # Otra conexión observa exclusivamente lo confirmado por las requests.
    async with conexion() as conn:
        return await UnidadDeTrabajo(conn).todos(sql, parametros)


@dataclass
class Circuito:
    api: httpx.AsyncClient
    invitado: httpx.AsyncClient
    empleado: int
    repartidor: int
    username: str
    rider_username: str
    telefono: str
    producto: int
    ingrediente: int
    localidad: str

    async def login(self, *, rider=False):
        sesion = await solicitud(
            self.api,
            "POST",
            "/api/auth/login",
            json={
                "username": self.rider_username if rider else self.username,
                "password": PASSWORD,
            },
        )
        assert sesion["rol"] == ("REPARTIDOR" if rider else "EMPLEADO")
        assert settings.cookie_sesion in self.api.cookies

    async def mensaje(self, texto="", media_id=None):
        identificador = f"integral-{uuid4().hex}"
        await solicitud(
            self.api,
            "POST",
            "/api/whatsapp/simular",
            esperado=202,
            json={
                "id": identificador,
                "telefono": self.telefono,
                "texto": texto,
                "media_id": media_id,
            },
        )
        # La ruta sólo recibe/encola. Este paso representa al worker y confirma
        # su transacción; no reemplaza servicios, repositorios ni resultados SQL.
        async with conexion() as conn:
            await construir_servicio(UnidadDeTrabajo(conn)).procesar(
                identificador,
                {"accion": "consulta", "argumentos": {}},
            )

    async def crear_invitado(self):
        borrador = await solicitud(
            self.invitado,
            "POST",
            "/api/whatsapp/borradores",
            esperado=201,
            json={
                "tipo_entrega": "RETIRO",
                "metodo_pago": "TRANSFERENCIA",
                "contacto": {
                    "nombre": "Invitado",
                    "apellido": "Integral",
                    "telefono": self.telefono,
                },
                "items": [{"producto_id": self.producto, "cantidad": 1}],
            },
        )
        assert not self.invitado.cookies
        await self.login()
        await self.mensaje(borrador["mensaje"])
        filas = await solicitud(self.api, "GET", "/api/pedidos?activos=true")
        pedidos = [p for p in filas if any(i["producto_id"] == self.producto for i in p["items"])]
        assert len(pedidos) == 1
        pedido = pedidos[0]
        (cliente,) = await consultar(
            "SELECT usuario_id FROM cliente WHERE id=%s", (pedido["cliente_id"],)
        )
        assert cliente["usuario_id"] is None
        assert pedido["estado"] == "PENDIENTE"
        return pedido

    async def detalle(self, pedido):
        return await solicitud(self.api, "GET", f"/api/pedidos/{pedido['id']}")

    async def estado(self, pedido, estado, *, esperado=200):
        return await solicitud(
            self.api,
            "PATCH",
            f"/api/pedidos/{pedido['id']}/estado",
            esperado=esperado,
            json={
                "estado": estado,
                "estado_esperado": pedido["estado"],
                "version_esperada": pedido["version"],
            },
        )

    async def editar(self, pedido, *, esperado=200, **cambios):
        return await solicitud(
            self.api,
            "PATCH",
            f"/api/pedidos/{pedido['id']}/operacion",
            esperado=esperado,
            json={
                "motivo": "Solicitud confirmada por el cliente",
                "version_esperada": pedido["version"],
                **cambios,
            },
        )

    async def stock(self):
        (fila,) = await consultar(
            "SELECT cantidad_actual, (SELECT count(*) FROM movimiento_stock "
            "WHERE ingrediente_id=i.id AND tipo='CONSUMO') AS consumos "
            "FROM ingrediente i WHERE id=%s",
            (self.ingrediente,),
        )
        return fila


@pytest_asyncio.fixture
async def circuito(uow):
    exigir_base_descartable()
    if settings.whatsapp_modo != "simulado" or settings.gemini_modo != "simulado":
        pytest.skip("Este recorrido requiere WHATSAPP_MODO/GEMINI_MODO=simulado")
    sufijo = uuid4().hex[:12]
    telefono = "549" + str(uuid4().int % 10**10).zfill(10)
    password_hash = hashear_password(PASSWORD)
    actores = []
    for rol in ("EMPLEADO", "REPARTIDOR"):
        actores.append(
            await uow.valor(
                "INSERT INTO usuario(nombre,apellido,username,password_hash,rol) "
                "VALUES('Integral','HTTP',%s,%s,%s) RETURNING id",
                (f"http_{rol.lower()}_{sufijo}", password_hash, rol),
            )
        )
    await uow.ejecutar("INSERT INTO repartidor(usuario_id) VALUES(%s)", (actores[1],))
    categoria = await uow.valor(
        "INSERT INTO categoria(nombre) VALUES(%s) RETURNING id", (f"Integral {sufijo}",)
    )
    producto = await uow.valor(
        "INSERT INTO producto(categoria_id,nombre,precio_base) VALUES(%s,%s,100) RETURNING id",
        (categoria, f"Integral {sufijo}"),
    )
    ingrediente = await uow.valor(
        "INSERT INTO ingrediente(nombre,unidad_medida,cantidad_actual,umbral_minimo) "
        "VALUES(%s,'UNIDAD',10,1) RETURNING id",
        (f"Integral {sufijo}",),
    )
    await uow.ejecutar(
        "INSERT INTO producto_ingrediente(producto_id,ingrediente_id,cantidad_requerida) "
        "VALUES(%s,%s,1)",
        (producto, ingrediente),
    )
    localidad = f"Cobertura integral {sufijo}"
    zona = await uow.valor(
        "INSERT INTO zona_cobertura(nombre,costo_envio,poligono,centro_lat,centro_lng) "
        "VALUES(%s,25,'[]',0,0) RETURNING id",
        (localidad,),
    )
    await uow.conn.commit()
    await abrir_pool()
    try:
        async with (
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://test",
            ) as api,
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://test",
            ) as guest,
        ):
            yield Circuito(
                api,
                guest,
                *actores,
                f"http_empleado_{sufijo}",
                f"http_repartidor_{sufijo}",
                telefono,
                producto,
                ingrediente,
                localidad,
            )
    finally:
        # Sólo filas propias. No TRUNCATE, reset ni rollback global que oculte
        # commits: cada request ya terminó antes de esta limpieza independiente.
        await uow.conn.rollback()
        pedidos = [
            p["id"]
            for p in await uow.todos(
                "SELECT pedido_id AS id FROM pedido_item WHERE producto_id=%s",
                (producto,),
            )
        ]
        clientes = [
            c["id"]
            for c in await uow.todos(
                "SELECT id FROM cliente WHERE whatsapp_verificado=%s",
                (telefono,),
            )
        ]
        await uow.ejecutar("DELETE FROM whatsapp_salida WHERE telefono=%s", (telefono,))
        await uow.ejecutar(
            "DELETE FROM whatsapp_atencion WHERE referencia_hash IN "
            "(SELECT referencia_hash FROM whatsapp_borrador WHERE telefono=%s)",
            (telefono,),
        )
        await uow.ejecutar("DELETE FROM whatsapp_comprobante WHERE pedido_id=ANY(%s)", (pedidos,))
        await uow.ejecutar("DELETE FROM whatsapp_cambio WHERE pedido_id=ANY(%s)", (pedidos,))
        await uow.ejecutar("DELETE FROM whatsapp_entrada WHERE telefono=%s", (telefono,))
        await uow.ejecutar(
            "DELETE FROM whatsapp_borrador WHERE telefono=%s " "OR contacto->>'telefono'=%s",
            (telefono, telefono),
        )
        await uow.ejecutar("DELETE FROM notificacion WHERE pedido_id=ANY(%s)", (pedidos,))
        await uow.ejecutar("DELETE FROM pago WHERE pedido_id=ANY(%s)", (pedidos,))
        await uow.ejecutar("DELETE FROM movimiento_stock WHERE ingrediente_id=%s", (ingrediente,))
        await uow.ejecutar("DELETE FROM pedido WHERE id=ANY(%s)", (pedidos,))
        await uow.ejecutar("DELETE FROM viaje WHERE repartidor_id=%s", (actores[1],))
        await uow.ejecutar("DELETE FROM cliente WHERE id=ANY(%s)", (clientes,))
        await uow.ejecutar("DELETE FROM producto WHERE id=%s", (producto,))
        await uow.ejecutar("DELETE FROM ingrediente WHERE id=%s", (ingrediente,))
        await uow.ejecutar("DELETE FROM categoria WHERE id=%s", (categoria,))
        await uow.ejecutar("DELETE FROM zona_cobertura WHERE id=%s", (zona,))
        await uow.ejecutar("DELETE FROM auditoria WHERE usuario_id=ANY(%s)", (actores,))
        await uow.ejecutar("DELETE FROM repartidor WHERE usuario_id=%s", (actores[1],))
        await uow.ejecutar("DELETE FROM usuario WHERE id=ANY(%s)", (actores,))
        await uow.conn.commit()
        await cerrar_pool()


@pytest.mark.asyncio
async def test_transferencia_invitado_revision_humana_no_cocina_automaticamente(circuito):
    c = circuito
    pedido = await c.crear_invitado()
    identidad = (pedido["id"], pedido["numero"])
    assert (await c.stock()) == {"cantidad_actual": Decimal("10"), "consumos": 0}
    await c.mensaje(media_id="comprobante-simulado-integral")
    bandeja = await solicitud(c.api, "GET", "/api/whatsapp/bandeja")
    comprobante = next(p for p in bandeja["comprobantes"] if p["pedido_id"] == pedido["id"])
    assert comprobante["estado"] == "PENDIENTE"
    actual = await c.detalle(pedido)
    assert actual["pagos"] == [] and Decimal(actual["neto_cobrado"]) == 0
    await c.estado(actual, "EN_PREPARACION", esperado=409)
    assert await c.detalle(pedido) == actual
    assert (await c.stock())["consumos"] == 0

    # Una cookie real de repartidor no permite acreditar fondos.
    await c.login(rider=True)
    revision = {
        "aprobar": True,
        "motivo": "Ingreso bancario comprobado",
        "total_verificado": actual["total"],
    }
    await solicitud(
        c.api,
        "POST",
        f"/api/whatsapp/comprobantes/{comprobante['id']}/revision",
        esperado=403,
        json=revision,
    )
    await c.login()
    for _ in range(2):
        await solicitud(
            c.api, "POST", f"/api/whatsapp/comprobantes/{comprobante['id']}/revision", json=revision
        )
    aprobado = await c.detalle(pedido)
    assert aprobado["estado"] == "PENDIENTE" and aprobado["preparacion_en"] is None
    assert aprobado["version"] == actual["version"]
    assert Decimal(aprobado["saldo_pendiente"]) == 0
    assert len(aprobado["pagos"]) == 1
    assert aprobado["pagos"][0]["estado"] == "CONCILIADO"
    pagos = await solicitud(c.api, "GET", f"/api/pagos/pedido/{pedido['id']}")
    assert len(pagos) == 1 and pagos[0]["registrado_por"] == c.empleado
    assert (await c.stock())["consumos"] == 0
    preparado = await c.estado(aprobado, "EN_PREPARACION")
    assert (preparado["id"], preparado["numero"]) == identidad
    assert preparado["preparacion_en"] and preparado["confirmado_en"]
    assert preparado["historial"][-1]["usuario_id"] == c.empleado
    assert (await c.stock()) == {"cantidad_actual": Decimal("9"), "consumos": 1}


@pytest.mark.asyncio
async def test_correccion_efectivo_delivery_fallido_regreso_retiro_y_cobro_idempotente(circuito):
    c = circuito
    pedido = await c.crear_invitado()
    identidad = (pedido["id"], pedido["numero"])
    await c.estado(pedido, "EN_PREPARACION", esperado=409)
    efectivo = await c.editar(pedido, metodo_pago_acordado="EFECTIVO")
    assert efectivo["pagos"] == [] and Decimal(efectivo["saldo_pendiente"]) == 100
    delivery = await c.editar(
        efectivo,
        tipo_entrega="DELIVERY",
        direccion_nueva={
            "calle": "Primera",
            "numero": "10",
            "localidad": c.localidad,
        },
    )
    vigente = await c.editar(
        delivery,
        direccion_nueva={
            "calle": "Corregida",
            "numero": "22",
            "localidad": c.localidad,
            "referencia": "Puerta verde",
        },
        observaciones="Sin timbre",
    )
    assert Decimal(vigente["total"]) == 125 and Decimal(vigente["costo_envio"]) == 25
    await c.editar(delivery, observaciones="Respuesta atrasada", esperado=409)
    assert await c.detalle(pedido) == vigente
    assert vigente["direccion"]["calle"] == "Corregida"
    assert vigente["items"] == pedido["items"]
    preparado = await c.estado(vigente, "EN_PREPARACION")
    assert Decimal(preparado["saldo_pendiente"]) == 125
    listo = await c.estado(preparado, "LISTO")
    riders = await solicitud(c.api, "GET", "/api/delivery/repartidores")
    assert any(r["id"] == c.repartidor for r in riders)
    asignado = await solicitud(
        c.api,
        "POST",
        f"/api/delivery/pedidos/{pedido['id']}/asignar",
        json={"repartidor_id": c.repartidor, "motivo": "Asignación manual en mostrador"},
    )
    envio, viaje = asignado["envio_id"], asignado["viaje_id"]
    await c.login(rider=True)
    await solicitud(c.api, "POST", f"/api/delivery/viajes/{viaje}/iniciar")
    await solicitud(
        c.api,
        "POST",
        f"/api/delivery/envios/{envio}/fallo",
        json={"motivo": "Cliente ausente; paquete vuelve al local"},
    )
    await c.login()
    fallido = await c.detalle(pedido)
    assert fallido["estado"] == "EN_CAMINO" and fallido["envio"]["estado"] == "FALLIDO"
    assert fallido["envio"]["viaje_id"] == viaje
    await c.editar(fallido, tipo_entrega="RETIRO", esperado=409)
    regreso = {
        "motivo": "Paquete recibido físicamente en el local",
        "version_esperada": listo["version"],
    }
    # Regreso desengancha antes de validar versión: el 409 debe revertir esas
    # escrituras, no sólo rechazar un comando antes de entrar al servicio.
    await solicitud(
        c.api, "POST", f"/api/delivery/envios/{envio}/regreso", esperado=409, json=regreso
    )
    assert await c.detalle(pedido) == fallido
    detalle_viaje = await solicitud(c.api, "GET", f"/api/delivery/viajes/{viaje}")
    assert detalle_viaje["estado"] == "EN_RUTA"
    assert detalle_viaje["envios"][0]["id"] == envio
    regreso["version_esperada"] = fallido["version"]
    await solicitud(c.api, "POST", f"/api/delivery/envios/{envio}/regreso", json=regreso)
    regresado = await c.detalle(pedido)
    assert regresado["estado"] == "LISTO" and regresado["envio"]["viaje_id"] is None
    detalle_viaje = await solicitud(c.api, "GET", f"/api/delivery/viajes/{viaje}")
    assert detalle_viaje["estado"] == "FINALIZADO" and detalle_viaje["retorno_en"]
    riders = await solicitud(c.api, "GET", "/api/delivery/repartidores")
    assert any(r["id"] == c.repartidor for r in riders)
    retiro = await c.editar(regresado, tipo_entrega="RETIRO")
    assert Decimal(retiro["total"]) == 100 and retiro["direccion_id"] is None
    entregado = await c.estado(retiro, "ENTREGADO")
    assert entregado["observaciones"] == "Sin timbre"
    assert (entregado["id"], entregado["numero"]) == identidad
    assert Decimal(entregado["saldo_pendiente"]) == 100
    cobro = {
        "pedido_id": pedido["id"],
        "clave_operacion": str(uuid4()),
        "monto_recibido": "120.00",
        "monto_a_pagar": "100.00",
        "conciliar_inmediato": True,
        "registrado_por": c.repartidor,
    }
    primero = await solicitud(c.api, "POST", "/api/pagos/efectivo", esperado=201, json=cobro)
    reintento = await solicitud(c.api, "POST", "/api/pagos/efectivo", esperado=201, json=cobro)
    assert reintento == primero
    assert primero["pago"]["registrado_por"] == c.empleado
    assert Decimal(primero["detalle"]["vuelto"]) == 20
    await solicitud(
        c.api,
        "POST",
        "/api/pagos/efectivo",
        esperado=409,
        json={**cobro, "monto_recibido": "130.00"},
    )
    saldo = await solicitud(c.api, "GET", f"/api/pagos/pedido/{pedido['id']}/estado")
    assert saldo["esta_saldado"] and saldo["cantidad_pagos"] == 1
    assert Decimal(saldo["total_pagado"]) == 100 and Decimal(saldo["saldo_pendiente"]) == 0
    final = await c.detalle(pedido)
    assert final["estado"] == "ENTREGADO" and final["version"] == entregado["version"]
    assert len(final["pagos"]) == 1 and Decimal(final["neto_cobrado"]) == 100
    assert (final["id"], final["numero"]) == identidad
    assert (await c.stock()) == {"cantidad_actual": Decimal("9"), "consumos": 1}
    (logistica,) = await consultar(
        "SELECT (SELECT count(*) FROM envio WHERE pedido_id=%s) AS envios, "
        "(SELECT count(*) FROM viaje WHERE repartidor_id=%s) AS viajes",
        (pedido["id"], c.repartidor),
    )
    assert logistica == {"envios": 1, "viajes": 1}
    assert final["historial"][-1]["usuario_id"] == c.empleado
    assert any(
        h["observacion"] == regreso["motivo"] and h["origen"] == "DELIVERY"
        for h in final["historial"]
    )
    eventos = await consultar(
        "SELECT accion,usuario_id,datos FROM auditoria WHERE entidad='envio' AND entidad_id=%s",
        (str(envio),),
    )
    assert any(e["accion"] == "ENVIO_FALLIDO" and e["usuario_id"] == c.repartidor for e in eventos)
    assert any(
        e["accion"] == "ENVIO_REGRESADO"
        and e["usuario_id"] == c.empleado
        and e["datos"]["motivo"] == regreso["motivo"]
        for e in eventos
    )
