-- La carga del repartidor es informativa: no limita pedidos ni viajes en ruta.
DROP TRIGGER envio_capacidad_trg ON envio;
DROP FUNCTION valida_capacidad_viaje();
DROP INDEX viaje_abierto_uk;

-- Se acumulan pedidos en la próxima salida; otras salidas pueden seguir en ruta.
CREATE UNIQUE INDEX viaje_planificado_uk ON viaje (repartidor_id)
    WHERE estado = 'PLANIFICADO';

-- Los combos tienen composición explícita; las hamburguesas ordinarias usan
-- su categoría. NULL no inventa cuántas hamburguesas incluye un combo nuevo.
ALTER TABLE producto ADD COLUMN hamburguesas_por_unidad INTEGER
    CHECK (hamburguesas_por_unidad >= 0);

DROP TRIGGER monu_auditar_cambio ON producto;
CREATE TRIGGER monu_auditar_cambio AFTER INSERT OR UPDATE OR DELETE ON producto
    FOR EACH ROW EXECUTE FUNCTION monu_registrar_cambio(
        'id',
        'id,categoria_id,nombre,descripcion,precio_base,imagen_url,activo,orden,variantes,creado_en,actualizado_en,hamburguesas_por_unidad'
    );

UPDATE producto p SET hamburguesas_por_unidad = CASE
    WHEN p.nombre IN ('Combo: Típica + Bacon', 'Combo: Bacon + Típica') THEN 2
    ELSE 0 END
FROM categoria c
WHERE p.categoria_id = c.id AND c.nombre = 'Combos'
  AND p.nombre IN ('Combo: Típica + Bacon', 'Combo: Bacon + Típica', 'Combo: Nuggets + Papas');
