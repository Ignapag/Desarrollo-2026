"""Pruebas de integridad del esquema (tarea 8 del cronograma).

Verifican contra la base real que las reglas de negocio que viven en el
esquema efectivamente se cumplen: claves foraneas, CHECKs, indices unicos,
triggers y funciones.

Cada prueba corre dentro de una transaccion que se revierte al terminar, asi
que **no ensucian la base compartida del grupo**.

    pytest tests/test_integridad_bd.py -v

Si no hay base configurada o accesible, las pruebas se saltean.
"""

from __future__ import annotations

from collections.abc import Iterator

import psycopg
import pytest
from psycopg.rows import dict_row

from app.core.config import settings


@pytest.fixture(scope="session")
def conexion_disponible() -> bool:
    try:
        with psycopg.connect(settings.database_url, connect_timeout=10):
            return True
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"Base no accesible: {exc.__class__.__name__}")


@pytest.fixture
def cur(conexion_disponible: bool) -> Iterator[psycopg.Cursor]:
    """Cursor dentro de una transaccion que siempre se revierte."""
    with psycopg.connect(settings.database_url, row_factory=dict_row) as conn:
        conn.autocommit = False
        with conn.cursor() as cursor:
            yield cursor
        conn.rollback()


def valor(cur: psycopg.Cursor, sql: str, parametros=None):
    cur.execute(sql, parametros)
    fila = cur.fetchone()
    return next(iter(fila.values())) if fila else None


# --------------------------------------------------------------------
# Estructura
# --------------------------------------------------------------------

def test_estan_todas_las_tablas(cur):
    esperadas = {
        "usuario", "repartidor", "cliente", "zona_cobertura", "punto_encuentro",
        "direccion", "auditoria", "parametro", "categoria", "ingrediente",
        "producto", "producto_ingrediente", "producto_opcion", "movimiento_stock",
        "alerta_stock", "pedido", "pedido_item", "pedido_item_opcion",
        "pedido_estado_historial", "promocion", "pedido_promocion", "viaje",
        "envio", "cierre_caja", "pago", "notificacion_plantilla", "notificacion",
    }
    cur.execute(
        """
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
        """
    )
    reales = {f["table_name"] for f in cur.fetchall()}
    assert esperadas <= reales, f"faltan tablas: {sorted(esperadas - reales)}"


def test_estan_las_vistas(cur):
    cur.execute("SELECT table_name FROM information_schema.views WHERE table_schema='public'")
    vistas = {f["table_name"] for f in cur.fetchall()}
    assert {"producto_costo", "producto_disponible", "notificacion_latencia"} <= vistas


def test_el_seed_cargo(cur):
    assert valor(cur, "SELECT count(*) FROM usuario") >= 10
    assert valor(cur, "SELECT count(*) FROM zona_cobertura") == 3
    assert valor(cur, "SELECT count(*) FROM producto") >= 6


# --------------------------------------------------------------------
# Restricciones
# --------------------------------------------------------------------

def test_rechaza_rol_invalido(cur):
    with pytest.raises(psycopg.errors.CheckViolation):
        cur.execute(
            """
            INSERT INTO usuario (nombre, apellido, username, password_hash, rol)
            VALUES ('X', 'Y', 'rolmalo', 'hash', 'GERENTE')
            """
        )


def test_rechaza_username_duplicado(cur):
    with pytest.raises(psycopg.errors.UniqueViolation):
        cur.execute(
            """
            INSERT INTO usuario (nombre, apellido, username, password_hash, rol)
            VALUES ('X', 'Y', 'admin', 'hash', 'EMPLEADO')
            """
        )


def test_username_es_case_insensitive(cur):
    """CITEXT: 'ADMIN' y 'admin' son el mismo usuario."""
    assert valor(cur, "SELECT count(*) FROM usuario WHERE username = 'ADMIN'") == 1


def test_rechaza_cliente_inexistente_en_pedido(cur):
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        cur.execute(
            "INSERT INTO pedido (cliente_id, tipo_entrega) VALUES (999999, 'RETIRO')"
        )


def test_delivery_exige_direccion(cur):
    """Validacion del alcance: la direccion es obligatoria en delivery."""
    cliente_id = valor(cur, "SELECT usuario_id FROM cliente LIMIT 1")
    with pytest.raises(psycopg.errors.CheckViolation):
        cur.execute(
            "INSERT INTO pedido (cliente_id, tipo_entrega, direccion_id)"
            " VALUES (%s, 'DELIVERY', NULL)",
            (cliente_id,),
        )


def test_rechaza_stock_negativo(cur):
    with pytest.raises(psycopg.errors.CheckViolation):
        cur.execute(
            "UPDATE ingrediente SET cantidad_actual = -1"
            " WHERE id = (SELECT min(id) FROM ingrediente)"
        )


def test_rechaza_precio_cero(cur):
    categoria_id = valor(cur, "SELECT id FROM categoria LIMIT 1")
    with pytest.raises(psycopg.errors.CheckViolation):
        cur.execute(
            "INSERT INTO producto (categoria_id, nombre, precio_base) VALUES (%s, 'Gratis', 0)",
            (categoria_id,),
        )


def test_producto_unico_por_categoria(cur):
    cur.execute("SELECT categoria_id, nombre FROM producto LIMIT 1")
    fila = cur.fetchone()
    with pytest.raises(psycopg.errors.UniqueViolation):
        cur.execute(
            "INSERT INTO producto (categoria_id, nombre, precio_base) VALUES (%s, %s, 1000)",
            (fila["categoria_id"], fila["nombre"]),
        )


def test_una_sola_alerta_activa_por_ingrediente(cur):
    ingrediente_id = valor(cur, "SELECT min(id) FROM ingrediente")
    cur.execute(
        "INSERT INTO alerta_stock (ingrediente_id, nivel, cantidad_al_generar)"
        " VALUES (%s, 'BAJO', 1)",
        (ingrediente_id,),
    )
    with pytest.raises(psycopg.errors.UniqueViolation):
        cur.execute(
            "INSERT INTO alerta_stock (ingrediente_id, nivel, cantidad_al_generar)"
            " VALUES (%s, 'AGOTADO', 0)",
            (ingrediente_id,),
        )


def test_cierre_de_caja_unico_por_fecha_y_turno(cur):
    cur.execute("INSERT INTO cierre_caja (fecha, turno) VALUES ('2026-01-01', 'NOCHE')")
    with pytest.raises(psycopg.errors.UniqueViolation):
        cur.execute("INSERT INTO cierre_caja (fecha, turno) VALUES ('2026-01-01', 'NOCHE')")


# --------------------------------------------------------------------
# Triggers
# --------------------------------------------------------------------

def _crear_pedido(cur) -> int:
    cliente_id = valor(cur, "SELECT usuario_id FROM cliente LIMIT 1")
    return valor(
        cur,
        "INSERT INTO pedido (cliente_id, tipo_entrega) VALUES (%s, 'RETIRO') RETURNING id",
        (cliente_id,),
    )


def test_trigger_limita_dos_pedidos_por_viaje(cur):
    """Regla del negocio: cada repartidor sale con hasta 2 pedidos."""
    repartidor_id = valor(cur, "SELECT usuario_id FROM repartidor LIMIT 1")
    viaje_id = valor(
        cur,
        "INSERT INTO viaje (repartidor_id) VALUES (%s) RETURNING id",
        (repartidor_id,),
    )

    for _ in range(2):
        pedido_id = _crear_pedido(cur)
        cur.execute(
            "INSERT INTO envio (pedido_id, viaje_id) VALUES (%s, %s)", (pedido_id, viaje_id)
        )

    tercero = _crear_pedido(cur)
    with pytest.raises(psycopg.errors.CheckViolation):
        cur.execute(
            "INSERT INTO envio (pedido_id, viaje_id) VALUES (%s, %s)", (tercero, viaje_id)
        )


def test_un_repartidor_no_tiene_dos_viajes_abiertos(cur):
    repartidor_id = valor(cur, "SELECT usuario_id FROM repartidor LIMIT 1")
    cur.execute("INSERT INTO viaje (repartidor_id) VALUES (%s)", (repartidor_id,))
    with pytest.raises(psycopg.errors.UniqueViolation):
        cur.execute("INSERT INTO viaje (repartidor_id) VALUES (%s)", (repartidor_id,))


def test_pago_conciliado_es_inmutable(cur):
    pedido_id = _crear_pedido(cur)
    pago_id = valor(
        cur,
        """
        INSERT INTO pago (pedido_id, metodo_pago, monto, estado)
        VALUES (%s, 'EFECTIVO', 1000, 'CONCILIADO') RETURNING id
        """,
        (pedido_id,),
    )
    with pytest.raises(psycopg.errors.CheckViolation):
        cur.execute("UPDATE pago SET monto = 9999 WHERE id = %s", (pago_id,))


def test_cierre_aprobado_es_inmutable(cur):
    cierre_id = valor(
        cur,
        """
        INSERT INTO cierre_caja (fecha, turno, estado)
        VALUES ('2026-01-02', 'MEDIODIA', 'APROBADO') RETURNING id
        """,
    )
    # El trigger levanta el error con ERRCODE 'check_violation'
    with pytest.raises(psycopg.errors.CheckViolation, match="inalterable"):
        cur.execute("UPDATE cierre_caja SET total_efectivo = 1 WHERE id = %s", (cierre_id,))


# --------------------------------------------------------------------
# Funciones
# --------------------------------------------------------------------

def test_punto_en_zona_reconoce_adentro_y_afuera(cur):
    cur.execute("SELECT poligono FROM zona_cobertura WHERE nombre = 'Ensenada'")
    poligono = cur.fetchone()["poligono"]

    # Centro de Ensenada: dentro
    assert valor(cur, "SELECT punto_en_zona(-34.860, -57.907, %s::jsonb)",
                 (psycopg.types.json.Json(poligono),)) is True
    # Buenos Aires capital: fuera
    assert valor(cur, "SELECT punto_en_zona(-34.603, -58.381, %s::jsonb)",
                 (psycopg.types.json.Json(poligono),)) is False


def test_punto_en_zona_tolera_nulos(cur):
    assert valor(cur, "SELECT punto_en_zona(NULL, NULL, NULL)") is False


def test_distancia_km_es_razonable(cur):
    """Ensenada a La Plata centro: unos 6 km en linea recta."""
    distancia = valor(cur, "SELECT distancia_km(-34.860, -57.907, -34.921, -57.954)")
    assert 5 < float(distancia) < 12


def test_distancia_km_de_un_punto_a_si_mismo_es_cero(cur):
    assert float(valor(cur, "SELECT distancia_km(-34.86, -57.90, -34.86, -57.90)")) == 0


# --------------------------------------------------------------------
# Vistas
# --------------------------------------------------------------------

def test_vista_producto_costo_calcula_margen(cur):
    cur.execute(
        "SELECT nombre, precio_base, costo_insumos, margen_estimado FROM producto_costo "
        "WHERE nombre = 'Monu Clasica'"
    )
    fila = cur.fetchone()
    assert fila is not None
    assert fila["costo_insumos"] > 0, "la receta del seed deberia dar costo > 0"
    assert fila["margen_estimado"] == fila["precio_base"] - fila["costo_insumos"]


def test_vista_producto_disponible_responde_para_todos(cur):
    total = valor(cur, "SELECT count(*) FROM producto")
    assert valor(cur, "SELECT count(*) FROM producto_disponible") == total


def test_producto_sin_stock_base_no_esta_disponible(cur):
    """Si un ingrediente base llega a cero, el producto deja de estar disponible."""
    cur.execute(
        """
        SELECT pi.producto_id, pi.ingrediente_id
        FROM producto_ingrediente pi
        WHERE pi.es_base
        LIMIT 1
        """
    )
    fila = cur.fetchone()
    cur.execute(
        "UPDATE ingrediente SET cantidad_actual = 0 WHERE id = %s", (fila["ingrediente_id"],)
    )
    disponible = valor(
        cur,
        "SELECT disponible FROM producto_disponible WHERE producto_id = %s",
        (fila["producto_id"],),
    )
    assert disponible is False


# --------------------------------------------------------------------
# Seed
# --------------------------------------------------------------------

def test_las_contrasenias_del_seed_son_bcrypt_verificables(cur):
    """El seed hashea con pgcrypto; el backend verifica con bcrypt de Python.

    Si los formatos no fueran compatibles, nadie podria iniciar sesion.
    """
    import bcrypt

    hash_guardado = valor(cur, "SELECT password_hash FROM usuario WHERE username = 'admin'")
    assert hash_guardado.startswith("$2"), f"no parece bcrypt: {hash_guardado[:10]}"
    assert bcrypt.checkpw(b"Monu2026!", hash_guardado.encode())
    assert not bcrypt.checkpw(b"incorrecta", hash_guardado.encode())


def test_las_recetas_del_seed_referencian_ingredientes_reales(cur):
    huerfanos = valor(
        cur,
        """
        SELECT count(*) FROM producto_ingrediente pi
        LEFT JOIN ingrediente i ON i.id = pi.ingrediente_id
        WHERE i.id IS NULL
        """,
    )
    assert huerfanos == 0


def test_todo_producto_tiene_receta(cur):
    sin_receta = valor(
        cur,
        """
        SELECT count(*) FROM producto p
        WHERE NOT EXISTS (SELECT 1 FROM producto_ingrediente pi WHERE pi.producto_id = p.id)
        """,
    )
    assert sin_receta == 0, "sin receta no se puede descontar stock ni calcular rentabilidad"
