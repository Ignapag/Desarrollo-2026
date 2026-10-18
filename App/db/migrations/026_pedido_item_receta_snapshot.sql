-- Fija la receta de cada item para consumir y ajustar sin depender del catalogo futuro.
-- Las filas historicas consumieron la receta base incluso cuando el nombre indicaba
-- una variante: preservamos esa composicion, sin inventar multiplicadores.
ALTER TABLE pedido_item
    ADD COLUMN variante TEXT,
    ADD COLUMN receta_snapshot JSONB,
    ADD CONSTRAINT pedido_item_receta_snapshot_array_chk
        CHECK (receta_snapshot IS NULL OR jsonb_typeof(receta_snapshot) = 'array');

UPDATE pedido_item item
SET variante = (
    SELECT elemento.valor->>'nombre'
    FROM producto p
    CROSS JOIN LATERAL jsonb_array_elements(p.variantes) AS elemento(valor)
    WHERE p.id = item.producto_id
      AND item.nombre_producto = p.nombre || ' (' || (elemento.valor->>'nombre') || ')'
    LIMIT 1
);

UPDATE pedido_item item
SET receta_snapshot = COALESCE((
    SELECT jsonb_agg(
        jsonb_build_object(
            'ingrediente_id', pi.ingrediente_id,
            'cantidad_requerida', pi.cantidad_requerida::text,
            'es_base', pi.es_base
        ) ORDER BY pi.ingrediente_id
    )
    FROM producto_ingrediente pi
    WHERE pi.producto_id = item.producto_id
), '[]'::jsonb);

COMMENT ON COLUMN pedido_item.variante IS
    'Variante seleccionada del catalogo; NULL para productos sin variante o historia no inferible.';
COMMENT ON COLUMN pedido_item.receta_snapshot IS
    'Receta fijada al crear: lista de ingrediente_id, cantidad_requerida decimal en texto y es_base. '
    'NULL admite escrituras legacy; las operaciones normales siempre fijan la receta.';
