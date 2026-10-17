"""Los documentos SQL deben mostrar el esquema final, no solo los CREATE."""

from scripts import der, diccionario


def test_diccionario_refleja_cliente_independiente_y_borrador_publico():
    documento = diccionario.generar()

    assert "| `usuario_id` | BIGINT | No | único · FK → `usuario.id` |" in documento
    assert "| `id` | BIGINT | Sí | PK · default `nextval('cliente_id_seq')` |" in documento
    assert "| `nombre` | TEXT | Sí | default `'Cliente'` |" in documento
    assert (
        "| `estado` | TEXT | Sí | valores: `ACTIVO`, `INACTIVO` · default `'ACTIVO'` |"
        in documento
    )
    assert "| `whatsapp_verificado` | TEXT | No | único |" in documento
    assert "| `cliente_id` | BIGINT | No | FK → `cliente.id` |" in documento
    assert "| `nombre_remitente` | TEXT | No | — |" in documento
    assert "FK → `cliente.usuario_id`" not in documento


def test_der_refleja_nuevas_columnas_y_relaciones_diferidas():
    documento = der.generar()

    assert "| `cliente` | `usuario_id` | `usuario` | 1 : 1 | No |" in documento
    assert "| `whatsapp_borrador` | `cliente_id` | `cliente` | 1 : N | No |" in documento
    assert "| `movimiento_stock` | `pedido_id` | `pedido` | 1 : N | No |" in documento
    assert "        jsonb variantes" in documento
    assert "        bigint atencion_id FK" in documento
    assert "        bigint enviado_por FK" in documento
    assert "        text nombre_remitente" in documento
    assert "        bigint usuario_id FK" in documento


def test_alter_respeta_orden_defaults_y_comas_en_expresiones(tmp_path, monkeypatch):
    (tmp_path / "001_original.sql").write_text(
        "CREATE TABLE ejemplo (\n"
        "    id BIGINT PRIMARY KEY,\n"
        "    codigo TEXT DEFAULT 'viejo'\n"
        ");\n", encoding="utf-8",
    )
    (tmp_path / "002_cambios.sql").write_text(
        "ALTER TABLE ejemplo ALTER COLUMN codigo SET NOT NULL,\n"
        "    ALTER COLUMN codigo SET DEFAULT concat('a,b', 'c'),\n"
        "    ADD COLUMN monto NUMERIC(12,2) DEFAULT 0;\n"
        "ALTER TABLE ejemplo ALTER COLUMN codigo DROP DEFAULT;\n"
        "ALTER TABLE ejemplo ALTER COLUMN monto SET DEFAULT 2;\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(diccionario, "DIR_MIGRACIONES", tmp_path)

    documento = diccionario.generar()

    assert "| `codigo` | TEXT | Sí | — |" in documento
    assert "| `monto` | NUMERIC(12,2) | No | default `2` |" in documento


def test_alter_reemplaza_check_de_tabla_sin_perder_restricciones(tmp_path):
    original = tmp_path / "001_original.sql"
    original.write_text(
        "CREATE TABLE ejemplo (\n"
        "    id BIGINT PRIMARY KEY,\n"
        "    estado TEXT,\n"
        "    responsable BIGINT,\n"
        "    CHECK ((estado = 'RESUELTA') = (responsable IS NOT NULL))\n"
        ");\n", encoding="utf-8",
    )
    cambio = tmp_path / "002_check.sql"
    cambio.write_text(
        "ALTER TABLE ejemplo DROP CONSTRAINT ejemplo_check;\n"
        "ALTER TABLE ejemplo ADD CONSTRAINT ejemplo_resolucion_chk "
        "CHECK (estado IS NOT NULL OR responsable IS NULL);\n", encoding="utf-8",
    )

    tabla, = diccionario.parsear_esquema([original, cambio])

    assert "ejemplo_check" not in tabla.restricciones
    assert tabla.restricciones["ejemplo_resolucion_chk"][0] == "CHECK"
    assert tabla.columnas[0].es_pk
