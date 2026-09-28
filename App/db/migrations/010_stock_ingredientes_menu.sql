-- =====================================================================
-- 010 - Inventario de prueba alineado con las hamburguesas de Emilio
--
-- Los ingredientes anteriores se conservan para mantener la integridad
-- de pedidos y movimientos historicos, pero solo quedan activos los que
-- participan de las hamburguesas actuales. El stock de prueba es 100.
-- =====================================================================

WITH ingredientes(nombre, unidad, umbral, costo) AS (
    VALUES
    ('Medallon de carne',    'UNIDAD', 20.000, 1200.00),
    ('Medallon Smash',       'UNIDAD', 20.000, 1200.00),
    ('Medallon NotCo',       'UNIDAD', 20.000, 1600.00),
    ('Panceta',              'GR',     20.000,    8.00),
    ('Bacon en cubos',       'GR',     20.000,    9.00),
    ('Huevo',                'UNIDAD', 20.000,  250.00),
    ('Pan de papa',          'UNIDAD', 20.000,  600.00),
    ('Queso cheddar',        'UNIDAD', 20.000,  400.00),
    ('Provoleta',            'UNIDAD', 20.000,  900.00),
    ('Tomate',               'GR',     20.000,    4.00),
    ('Lechuga',              'GR',     20.000,    3.00),
    ('Cebolla cruda',        'GR',     20.000,    3.00),
    ('Cebolla en cubos',     'GR',     20.000,    3.00),
    ('Cebolla caramelizada', 'GR',     20.000,    6.00),
    ('Cebolla crispy',       'GR',     20.000,    7.00),
    ('Rucula',               'GR',     20.000,    5.00),
    ('Pepinillos',           'GR',     20.000,    5.00),
    ('Salsa Monu',           'GR',     20.000,    4.00),
    ('Alioli',               'GR',     20.000,    4.00),
    ('Barbacoa',             'GR',     20.000,    4.00),
    ('Mayonesa',             'GR',     20.000,    3.00),
    ('Mayonesa ahumada',     'GR',     20.000,    5.00),
    ('Ketchup',              'GR',     20.000,    3.00),
    ('Mostaza',              'GR',     20.000,    3.00),
    ('Salsa Smash',          'GR',     20.000,    5.00)
)
INSERT INTO ingrediente
    (nombre, unidad_medida, cantidad_actual, umbral_minimo, costo_unitario, activo)
SELECT nombre, unidad, 100.000, umbral, costo, TRUE
FROM ingredientes
ON CONFLICT (nombre) DO UPDATE
SET unidad_medida = EXCLUDED.unidad_medida,
    cantidad_actual = 100.000,
    umbral_minimo = EXCLUDED.umbral_minimo,
    costo_unitario = EXCLUDED.costo_unitario,
    activo = TRUE;

UPDATE ingrediente
SET activo = FALSE
WHERE nombre NOT IN (
    'Medallon de carne', 'Medallon Smash', 'Medallon NotCo',
    'Panceta', 'Bacon en cubos', 'Huevo', 'Pan de papa',
    'Queso cheddar', 'Provoleta', 'Tomate', 'Lechuga',
    'Cebolla cruda', 'Cebolla en cubos', 'Cebolla caramelizada',
    'Cebolla crispy', 'Rucula', 'Pepinillos', 'Salsa Monu',
    'Alioli', 'Barbacoa', 'Mayonesa', 'Mayonesa ahumada',
    'Ketchup', 'Mostaza', 'Salsa Smash'
);

UPDATE alerta_stock a
SET estado = 'RESUELTA', resuelta_en = now()
FROM ingrediente i
WHERE i.id = a.ingrediente_id
  AND NOT i.activo
  AND a.estado = 'ACTIVA';

-- Reemplaza las recetas minimas de la migracion 009 por la composicion
-- completa de cada hamburguesa. Cada cantidad vale una porcion para que
-- el stock 100 resulte practico durante las pruebas funcionales.
DELETE FROM producto_ingrediente pi
USING producto p, categoria c
WHERE pi.producto_id = p.id
  AND p.categoria_id = c.id
  AND c.nombre IN ('Nuestras Burgers', 'Monufusion', 'Monufusión',
                   'Opciones Individuales');

WITH receta(producto, ingrediente) AS (
    VALUES
    ('Cheese', 'Medallon de carne'), ('Cheese', 'Pan de papa'),
    ('Cheese', 'Queso cheddar'), ('Cheese', 'Salsa Monu'),

    ('Bacon', 'Medallon de carne'), ('Bacon', 'Pan de papa'),
    ('Bacon', 'Queso cheddar'), ('Bacon', 'Panceta'), ('Bacon', 'Salsa Monu'),

    ('Crispy', 'Medallon de carne'), ('Crispy', 'Pan de papa'),
    ('Crispy', 'Queso cheddar'), ('Crispy', 'Panceta'),
    ('Crispy', 'Cebolla crispy'), ('Crispy', 'Alioli'),

    ('Monulibra', 'Medallon de carne'), ('Monulibra', 'Pan de papa'),
    ('Monulibra', 'Queso cheddar'), ('Monulibra', 'Cebolla en cubos'),
    ('Monulibra', 'Ketchup'), ('Monulibra', 'Mostaza'),

    ('Monuburger', 'Medallon de carne'), ('Monuburger', 'Pan de papa'),
    ('Monuburger', 'Queso cheddar'), ('Monuburger', 'Cebolla caramelizada'),
    ('Monuburger', 'Panceta'), ('Monuburger', 'Huevo'),
    ('Monuburger', 'Barbacoa'),

    ('La Típica', 'Medallon de carne'), ('La Típica', 'Pan de papa'),
    ('La Típica', 'Queso cheddar'), ('La Típica', 'Lechuga'),
    ('La Típica', 'Tomate'), ('La Típica', 'Mayonesa'),

    ('Witcher', 'Medallon de carne'), ('Witcher', 'Pan de papa'),
    ('Witcher', 'Queso cheddar'), ('Witcher', 'Panceta'),
    ('Witcher', 'Tomate'), ('Witcher', 'Lechuga'),
    ('Witcher', 'Cebolla cruda'), ('Witcher', 'Pepinillos'),
    ('Witcher', 'Mayonesa'), ('Witcher', 'Ketchup'),

    ('18 Supermash', 'Medallon Smash'), ('18 Supermash', 'Pan de papa'),
    ('18 Supermash', 'Queso cheddar'), ('18 Supermash', 'Panceta'),
    ('18 Supermash', 'Pepinillos'), ('18 Supermash', 'Salsa Smash'),

    ('Oklahoma', 'Medallon Smash'), ('Oklahoma', 'Pan de papa'),
    ('Oklahoma', 'Cebolla cruda'), ('Oklahoma', 'Queso cheddar'),
    ('Oklahoma', 'Salsa Monu'),

    ('Provoteca', 'Medallon de carne'), ('Provoteca', 'Pan de papa'),
    ('Provoteca', 'Provoleta'), ('Provoteca', 'Cebolla caramelizada'),
    ('Provoteca', 'Rucula'), ('Provoteca', 'Alioli'),

    ('Big Monu', 'Medallon de carne'), ('Big Monu', 'Pan de papa'),
    ('Big Monu', 'Queso cheddar'), ('Big Monu', 'Cebolla cruda'),
    ('Big Monu', 'Lechuga'), ('Big Monu', 'Pepinillos'),
    ('Big Monu', 'Salsa Monu'),

    ('Not Monu', 'Medallon NotCo'), ('Not Monu', 'Pan de papa'),
    ('Not Monu', 'Queso cheddar'), ('Not Monu', 'Mayonesa'),
    ('Not Monu', 'Tomate'), ('Not Monu', 'Lechuga'),

    ('Nueva Jersey', 'Medallon de carne'), ('Nueva Jersey', 'Pan de papa'),
    ('Nueva Jersey', 'Queso cheddar'), ('Nueva Jersey', 'Bacon en cubos'),
    ('Nueva Jersey', 'Mayonesa ahumada'),

    ('Baconhoma', 'Medallon Smash'), ('Baconhoma', 'Pan de papa'),
    ('Baconhoma', 'Cebolla cruda'), ('Baconhoma', 'Queso cheddar'),
    ('Baconhoma', 'Panceta'), ('Baconhoma', 'Salsa Monu'),

    ('Tipiteca', 'Medallon de carne'), ('Tipiteca', 'Pan de papa'),
    ('Tipiteca', 'Provoleta'), ('Tipiteca', 'Tomate'),
    ('Tipiteca', 'Rucula'), ('Tipiteca', 'Mayonesa'),

    ('Keco', 'Medallon Smash'), ('Keco', 'Pan de papa'),
    ('Keco', 'Queso cheddar'), ('Keco', 'Cebolla crispy'), ('Keco', 'Alioli'),

    ('Cito', 'Medallon de carne'), ('Cito', 'Pan de papa'),
    ('Cito', 'Queso cheddar'), ('Cito', 'Cebolla en cubos'),
    ('Cito', 'Ketchup'), ('Cito', 'Mostaza'), ('Cito', 'Panceta'),

    ('Tino Andino', 'Medallon de carne'), ('Tino Andino', 'Pan de papa'),
    ('Tino Andino', 'Provoleta'), ('Tino Andino', 'Queso cheddar'),
    ('Tino Andino', 'Mayonesa'),

    ('Santi', 'Medallon de carne'), ('Santi', 'Pan de papa'),
    ('Santi', 'Queso cheddar'), ('Santi', 'Cebolla crispy'),
    ('Santi', 'Lechuga'), ('Santi', 'Alioli')
)
INSERT INTO producto_ingrediente
    (producto_id, ingrediente_id, cantidad_requerida, es_base)
SELECT p.id, i.id, 1.000, TRUE
FROM receta r
JOIN producto p ON p.nombre = r.producto
JOIN ingrediente i ON i.nombre = r.ingrediente
ON CONFLICT (producto_id, ingrediente_id) DO UPDATE
SET cantidad_requerida = EXCLUDED.cantidad_requerida,
    es_base = TRUE;
