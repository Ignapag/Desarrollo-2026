-- Recetas explícitas por variante. No se infieren cantidades ni se modifican
-- las recetas históricas: una variante sin configuración conserva la base.
CREATE TABLE producto_variante_ingrediente (
    producto_id BIGINT NOT NULL REFERENCES producto(id) ON DELETE CASCADE,
    variante TEXT NOT NULL CHECK (btrim(variante) <> ''),
    ingrediente_id BIGINT NOT NULL REFERENCES ingrediente(id) ON DELETE RESTRICT,
    cantidad_requerida NUMERIC(12,3) NOT NULL CHECK (cantidad_requerida > 0),
    es_base BOOLEAN NOT NULL DEFAULT TRUE,
    PRIMARY KEY (producto_id, variante, ingrediente_id)
);

CREATE INDEX producto_variante_receta_idx
    ON producto_variante_ingrediente(producto_id, lower(btrim(variante)));

CREATE FUNCTION receta_producto(p_producto_id BIGINT, p_variante TEXT DEFAULT NULL)
RETURNS TABLE(ingrediente_id BIGINT, cantidad_requerida NUMERIC, es_base BOOLEAN)
LANGUAGE sql STABLE AS $$
    WITH explicita AS (
        SELECT r.ingrediente_id, r.cantidad_requerida, r.es_base
        FROM producto_variante_ingrediente r
        WHERE r.producto_id = p_producto_id
          AND lower(btrim(r.variante)) = lower(btrim(p_variante))
    )
    SELECT * FROM explicita
    UNION ALL
    SELECT r.ingrediente_id, r.cantidad_requerida, r.es_base
    FROM producto_ingrediente r
    WHERE r.producto_id = p_producto_id AND NOT EXISTS (SELECT 1 FROM explicita)
$$;

CREATE FUNCTION variante_producto_disponible(p_producto_id BIGINT, p_variante TEXT DEFAULT NULL)
RETURNS BOOLEAN LANGUAGE sql STABLE AS $$
    SELECT p.activo AND NOT EXISTS (
        SELECT 1 FROM receta_producto(p.id, p_variante) r
        JOIN ingrediente i ON i.id = r.ingrediente_id
        WHERE r.es_base AND (NOT i.activo OR i.cantidad_actual < r.cantidad_requerida)
    ) FROM producto p WHERE p.id = p_producto_id
$$;

-- Conserva columnas y disponibilidad general cuando alguna variante se puede
-- vender. El catálogo además expone la disponibilidad de cada variante.
CREATE OR REPLACE VIEW producto_disponible AS
SELECT p.id AS producto_id,
       CASE WHEN jsonb_array_length(p.variantes) = 0
            THEN variante_producto_disponible(p.id)
            ELSE EXISTS (
                SELECT 1 FROM jsonb_array_elements(p.variantes) v
                WHERE variante_producto_disponible(p.id, v->>'nombre')
            ) END AS disponible
FROM producto p;
