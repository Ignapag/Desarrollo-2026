"""Demo persistente local: python -m scripts.whatsapp_demo.

Exige DATABASE_URL explícita de loopback y ambos proveedores simulados. Crea
datos ficticios y consume stock al preparar el segundo pedido; no borra datos.
"""

from __future__ import annotations

import asyncio
import os
import secrets
import sys
from urllib.parse import urlsplit
from uuid import uuid4

import psycopg
from psycopg.conninfo import conninfo_to_dict

from app.core.config import settings
from app.core.db import UnidadDeTrabajo, abrir_pool, cerrar_pool, conexion
from app.errores import ErrorDominio, ReglaDeNegocio
from app.modules.pedidos.domain.entidades import EstadoPedido
from app.modules.whatsapp.presentation.dependencias import construir_servicio
from app.modules.whatsapp.presentation.procesamiento import procesar_entrada, procesar_lote

_LOCALES = {"localhost", "127.0.0.1", "::1"}


def comprobar(condicion: bool, mensaje: str) -> None:
    if not condicion:
        raise RuntimeError(mensaje)


def validar_entorno() -> None:
    """Rechaza destinos implícitos/remotos antes de abrir cualquier conexión."""
    explicita = os.environ.get("DATABASE_URL", "")
    comprobar(
        bool(explicita) and explicita == settings.database_url,
        "Definí DATABASE_URL explícitamente para una base local descartable.",
    )
    partes = urlsplit(settings.database_url)
    comprobar(
        partes.scheme in {"postgres", "postgresql"} and partes.hostname in _LOCALES,
        "La demo solo admite PostgreSQL en localhost, 127.0.0.1 o ::1.",
    )
    parametros = conninfo_to_dict(settings.database_url)
    comprobar(
        parametros.get("host") in _LOCALES,
        "El host efectivo de PostgreSQL también debe ser local.",
    )
    comprobar(
        not parametros.get("service") and not os.environ.get("PGSERVICE"),
        "La demo no admite servicios de conexión indirectos.",
    )
    hostaddr = parametros.get("hostaddr") or os.environ.get("PGHOSTADDR")
    comprobar(
        not hostaddr or hostaddr in _LOCALES,
        "La dirección efectiva de PostgreSQL también debe ser local.",
    )
    comprobar(not settings.es_produccion, "La demo no admite entorno de producción.")
    comprobar(
        settings.whatsapp_modo == settings.gemini_modo == "simulado",
        "Definí WHATSAPP_MODO=simulado y GEMINI_MODO=simulado.",
    )


async def datos_iniciales() -> tuple[int, int, dict, tuple[str, str]]:
    async with conexion() as conn:
        uow = UnidadDeTrabajo(conn)
        comprobar(
            bool(await uow.valor("SELECT to_regclass('whatsapp_estado_envio')")),
            "Aplicá las migraciones locales, incluida 012, antes de la demo.",
        )
        cliente_id = await uow.valor(
            "SELECT c.id FROM cliente c JOIN usuario u ON u.id=c.usuario_id "
            "WHERE u.estado='ACTIVO' AND u.rol='CLIENTE' ORDER BY c.usuario_id LIMIT 1"
        )
        empleado_id = await uow.valor(
            "SELECT id FROM usuario WHERE rol='EMPLEADO' AND estado='ACTIVO' ORDER BY id LIMIT 1"
        )
        producto = await uow.uno(
            "SELECT p.id,p.variantes FROM producto p WHERE p.nombre=%s AND p.activo "
            "AND EXISTS (SELECT 1 FROM producto_ingrediente pi JOIN ingrediente i "
            "ON i.id=pi.ingrediente_id WHERE pi.producto_id=p.id AND lower(i.nombre)='tomate')",
            ("La Típica",),
        )
        comprobar(
            bool(cliente_id and empleado_id and producto),
            "Se necesitan el seed local y La Típica activa con receta de tomate.",
        )
        comprobar(
            any(v["nombre"] == "Doble" for v in producto["variantes"]),
            "La Típica debe tener la variante Doble del catálogo local.",
        )
        # Prefijo ficticio de la demo y sufijos distintos en cada ejecución.
        while True:
            telefonos = tuple(f"5492215{secrets.randbelow(1000000):06d}" for _ in range(2))
            usados = await uow.valor(
                "SELECT EXISTS (SELECT 1 FROM whatsapp_borrador WHERE telefono IN (%s,%s))",
                telefonos,
            )
            if telefonos[0] != telefonos[1] and not usados:
                break
    return (
        cliente_id,
        empleado_id,
        {
            "producto_id": producto["id"],
            "cantidad": 1,
            "variante": "Doble",
        },
        telefonos,
    )


async def recibir_y_procesar(
    telefono: str,
    texto: str,
    *,
    media_id: str | None = None,
    identificador: str | None = None,
) -> tuple[str, str]:
    identificador = identificador or f"demo:{uuid4().hex}"
    async with conexion() as conn:
        await construir_servicio(UnidadDeTrabajo(conn)).recibir(
            identificador,
            telefono,
            texto,
            media_id,
        )
    await procesar_entrada(identificador)
    async with conexion() as conn:
        entrada = await construir_servicio(UnidadDeTrabajo(conn)).repo.entrada(identificador)
        comprobar(entrada["estado"] == "PROCESADO", "El worker no procesó la entrada de la demo.")
    # El ID es de inbox; el texto de entrada puede contener una referencia y no se imprime.
    respuesta_visible = entrada["respuesta"]
    if settings.whatsapp_transferencia_datos:
        respuesta_visible = respuesta_visible.replace(
            settings.whatsapp_transferencia_datos,
            "[datos de transferencia omitidos en demo]",
        )
    print(f"  Entrada {identificador}: {respuesta_visible}")
    return identificador, entrada["respuesta"]


async def pedido_de(telefono: str) -> dict:
    async with conexion() as conn:
        fila = await UnidadDeTrabajo(conn).uno(
            "SELECT p.id,p.numero,p.total,p.estado,b.estado_pago FROM pedido p "
            "JOIN whatsapp_borrador b ON b.pedido_id=p.id WHERE b.telefono=%s",
            (telefono,),
        )
    comprobar(bool(fila), "El pedido operativo todavía no se creó.")
    return fila


async def vista_cocina(cliente_id: int, pedido_id: int) -> dict:
    async with conexion() as conn:
        pedidos = await construir_servicio(UnidadDeTrabajo(conn)).pedidos.listar(
            cliente_id=cliente_id
        )
    pedido = next(p for p in pedidos if p["id"] == pedido_id)
    item = pedido["items"][0]
    print(
        f"  Cocina, pedido #{pedido['numero']} (ID {pedido_id}): "
        f"{item['nombre_producto']} x{item['cantidad']} / {item.get('aclaraciones') or 'sin notas'}"
    )
    return item


async def escenario_efectivo(cliente_id: int, item: dict, telefono: str) -> int:
    print("1. Borrador, datos guiados, recepción repetida y personalización.")
    async with conexion() as conn:
        uow = UnidadDeTrabajo(conn)
        antes = await uow.valor("SELECT count(*) FROM pedido")
        borrador = await construir_servicio(uow).crear_borrador(
            cliente_id,
            {"telefono": telefono, "items": [item]},
        )
        comprobar(
            await uow.valor("SELECT count(*) FROM pedido") == antes,
            "Crear un borrador no debe crear un pedido operativo.",
        )
    print("  Borrador guardado: todavía no existe un pedido operativo.")
    entrada_id, _ = await recibir_y_procesar(telefono, borrador["mensaje"])
    await recibir_y_procesar(telefono, "retiro")
    await recibir_y_procesar(telefono, "efectivo")
    pedido = await pedido_de(telefono)
    await recibir_y_procesar(telefono, borrador["mensaje"], identificador=entrada_id)
    await recibir_y_procesar(telefono, borrador["mensaje"])
    async with conexion() as conn:
        uow = UnidadDeTrabajo(conn)
        comprobar(
            await uow.valor("SELECT count(*) FROM pedido") == antes + 1,
            "La recepción repetida creó más de un pedido.",
        )
    print(f"  Idempotencia comprobada: un pedido #{pedido['numero']} (ID {pedido['id']}).")
    await recibir_y_procesar(telefono, "¿Le podés sacar el tomate?")
    vigente = await vista_cocina(cliente_id, pedido["id"])
    comprobar(
        "sin tomate" in (vigente.get("aclaraciones") or "").casefold(),
        "Cocina debe leer la aclaración Sin Tomate guardada.",
    )
    await recibir_y_procesar(telefono, "cantidad: 2")
    comprobar(
        (await vista_cocina(cliente_id, pedido["id"]))["cantidad"] == 1,
        "El cambio de importe requiere confirmación del cliente.",
    )
    await recibir_y_procesar(telefono, "confirmar")
    comprobar(
        (await vista_cocina(cliente_id, pedido["id"]))["cantidad"] == 2,
        "La confirmación explícita no aplicó el cambio vigente.",
    )
    return pedido["id"]


async def escenario_transferencia(
    cliente_id: int, empleado_id: int, item: dict, telefono: str
) -> int:
    print("2. Transferencia ficticia, revisión humana y autorización para cocina.")
    async with conexion() as conn:
        borrador = await construir_servicio(UnidadDeTrabajo(conn)).crear_borrador(
            cliente_id,
            {
                "telefono": telefono,
                "items": [item],
                "tipo_entrega": "RETIRO",
                "metodo_pago": "TRANSFERENCIA",
            },
        )
    await recibir_y_procesar(telefono, borrador["mensaje"])
    pedido = await pedido_de(telefono)
    await recibir_y_procesar(telefono, "", media_id=f"comprobante-ficticio-{uuid4().hex}")
    async with conexion() as conn:
        uow = UnidadDeTrabajo(conn)
        comprobante_id = await uow.valor(
            "SELECT id FROM whatsapp_comprobante WHERE pedido_id=%s",
            (pedido["id"],),
        )
        comprobar(
            await uow.valor("SELECT count(*) FROM pago WHERE pedido_id=%s", (pedido["id"],)) == 0,
            "Recibir un comprobante no puede acreditar el pago.",
        )
    try:
        async with conexion() as conn:
            await construir_servicio(UnidadDeTrabajo(conn)).pedidos.cambiar_estado(
                pedido["id"],
                EstadoPedido.EN_PREPARACION,
                usuario_id=empleado_id,
            )
    except ReglaDeNegocio:
        print("  Preparación bloqueada: la transferencia todavía no fue aprobada.")
    else:
        raise RuntimeError("La preparación se habilitó antes de aprobar la transferencia.")
    async with conexion() as conn:
        await construir_servicio(UnidadDeTrabajo(conn)).revisar_comprobante(
            comprobante_id,
            True,
            empleado_id,
            "DEMO: revisión humana ficticia del importe y la acreditación; sin transferencia real.",
            total_verificado=pedido["total"],
        )
    async with conexion() as conn:
        servicio = construir_servicio(UnidadDeTrabajo(conn))
        await servicio.pedidos.cambiar_estado(
            pedido["id"],
            EstadoPedido.EN_PREPARACION,
            usuario_id=empleado_id,
        )
    vigente = await pedido_de(telefono)
    comprobar(
        vigente["estado_pago"] == "APROBADO" and vigente["estado"] == "EN_PREPARACION",
        "La revisión no habilitó correctamente la preparación.",
    )
    print(
        f"  Pedido #{pedido['numero']} (ID {pedido['id']}), comprobante ID {comprobante_id}: "
        "APROBADO por personal de prueba; EN_PREPARACION. No hubo dinero real."
    )
    return pedido["id"]


async def ejecutar() -> None:
    validar_entorno()
    print("DEMO LOCAL DESCARTABLE: guarda pedidos/pagos ficticios y consume stock de prueba.")
    print("No envía WhatsApp, no llama Gemini, no imprime referencias ni borra datos.")
    await abrir_pool()
    try:
        cliente, empleado, item, telefonos = await datos_iniciales()
        pedidos = [
            await escenario_efectivo(cliente, item, telefonos[0]),
            await escenario_transferencia(cliente, empleado, item, telefonos[1]),
        ]
        await procesar_lote(limite=100)
        async with conexion() as conn:
            salidas = await UnidadDeTrabajo(conn).todos(
                "SELECT id,estado FROM whatsapp_salida WHERE telefono IN (%s,%s) ORDER BY id",
                telefonos,
            )
        comprobar(
            bool(salidas) and all(s["estado"] == "SIMULADO" for s in salidas),
            "Quedaron respuestas sin simular; revisá la cola de esta base descartable.",
        )
        print(f"Demo verificada. Pedidos creados: {pedidos}.")
        print(f"Salidas SIMULADO, nunca aceptación real: {[s['id'] for s in salidas]}.")
        print("Los datos se conservan para inspección. Volver a ejecutar crea otros dos pedidos.")
    finally:
        await cerrar_pool()


if __name__ == "__main__":
    # La salida capturada de PowerShell debe conservar las respuestas en español.
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    try:
        asyncio.run(ejecutar())
    except RuntimeError as error:
        raise SystemExit(str(error)) from None
    except (ErrorDominio, psycopg.Error) as error:
        # No volcar cuerpos, DSN ni errores de conexión con parámetros del proveedor.
        raise SystemExit(
            f"Demo interrumpida ({type(error).__name__}). Revisá el entorno local."
        ) from None
