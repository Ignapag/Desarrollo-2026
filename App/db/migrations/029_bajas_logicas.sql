-- Las ediciones conservan las relaciones retiradas y sus claves históricas.
ALTER TABLE pedido_item ADD COLUMN eliminado_en TIMESTAMPTZ;
ALTER TABLE producto_ingrediente ADD COLUMN eliminado_en TIMESTAMPTZ;
ALTER TABLE producto_variante_ingrediente ADD COLUMN eliminado_en TIMESTAMPTZ;
ALTER TABLE rol_permiso ADD COLUMN eliminado_en TIMESTAMPTZ;

CREATE INDEX pedido_item_vigente_idx ON pedido_item (pedido_id)
    WHERE eliminado_en IS NULL;

CREATE OR REPLACE FUNCTION receta_producto(p_producto_id BIGINT, p_variante TEXT DEFAULT NULL)
RETURNS TABLE(ingrediente_id BIGINT, cantidad_requerida NUMERIC, es_base BOOLEAN)
LANGUAGE sql STABLE AS $$
    WITH explicita AS (
        SELECT r.ingrediente_id, r.cantidad_requerida, r.es_base
        FROM producto_variante_ingrediente r
        WHERE r.producto_id = p_producto_id AND r.eliminado_en IS NULL
          AND lower(btrim(r.variante)) = lower(btrim(p_variante))
    )
    SELECT * FROM explicita
    UNION ALL
    SELECT r.ingrediente_id, r.cantidad_requerida, r.es_base
    FROM producto_ingrediente r
    WHERE r.producto_id = p_producto_id AND r.eliminado_en IS NULL
      AND NOT EXISTS (SELECT 1 FROM explicita)
$$;

CREATE OR REPLACE VIEW producto_costo AS
SELECT p.id AS producto_id,
       p.nombre,
       p.precio_base,
       COALESCE(SUM(pi.cantidad_requerida * i.costo_unitario), 0) AS costo_insumos,
       p.precio_base - COALESCE(SUM(pi.cantidad_requerida * i.costo_unitario), 0) AS margen_estimado
FROM producto p
LEFT JOIN producto_ingrediente pi ON pi.producto_id = p.id AND pi.eliminado_en IS NULL
LEFT JOIN ingrediente i ON i.id = pi.ingrediente_id
GROUP BY p.id, p.nombre, p.precio_base;
