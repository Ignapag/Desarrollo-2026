-- Extras reales: la composición efectiva vive en receta_snapshot y la venta queda congelada.
ALTER TABLE pedido_item ADD COLUMN extras_snapshot JSONB NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE pedido_item ADD CONSTRAINT pedido_item_extras_array_chk
    CHECK (jsonb_typeof(extras_snapshot) = 'array');
COMMENT ON COLUMN pedido_item.extras_snapshot IS
    'Agregados por hamburguesa: ingrediente, cantidad, porcion en unidad de inventario y precio de venta congelados.';
-- No habilita opciones históricas ni inventa precios/porciones. El local debe configurarlas.
