-- Unidades vendibles según el stock actual de los ingredientes base de la receta.
-- Coherente con variante_producto_disponible: 0 equivale a no disponible. El tope de
-- 50 coincide con el máximo de unidades por ítem que aceptan los pedidos.
CREATE FUNCTION variante_producto_max_unidades(p_producto_id BIGINT, p_variante TEXT DEFAULT NULL)
RETURNS INTEGER LANGUAGE sql STABLE AS $$
    SELECT CASE WHEN NOT p.activo THEN 0 ELSE LEAST(50, COALESCE((
        SELECT min(CASE WHEN i.activo THEN floor(i.cantidad_actual / r.cantidad_requerida) ELSE 0 END)
        FROM receta_producto(p.id, p_variante) r
        JOIN ingrediente i ON i.id = r.ingrediente_id
        WHERE r.es_base AND r.cantidad_requerida > 0
    ), 50))::INTEGER END
    FROM producto p WHERE p.id = p_producto_id
$$;

-- Sin variantes usa la receta base; con variantes, la variante que más unidades admite.
CREATE FUNCTION producto_max_unidades(p_producto_id BIGINT)
RETURNS INTEGER LANGUAGE sql STABLE AS $$
    SELECT CASE WHEN jsonb_array_length(p.variantes) = 0
                THEN variante_producto_max_unidades(p.id)
                ELSE (SELECT max(variante_producto_max_unidades(p.id, v->>'nombre'))
                      FROM jsonb_array_elements(p.variantes) v) END
    FROM producto p WHERE p.id = p_producto_id
$$;
