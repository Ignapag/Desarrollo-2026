-- =====================================================================
-- 009 - Menu comercial definido por Emilio
--
-- Migra el catalogo que originalmente vivia como datos mock del frontend
-- a la fuente de verdad PostgreSQL. Los productos seed anteriores se
-- conservan para no romper pedidos historicos, pero quedan inactivos.
-- =====================================================================

ALTER TABLE producto
    ADD COLUMN variantes JSONB NOT NULL DEFAULT '[]'::jsonb;

ALTER TABLE producto
    ADD CONSTRAINT producto_variantes_array_chk
    CHECK (jsonb_typeof(variantes) = 'array');

INSERT INTO categoria (nombre, orden, activa) VALUES
    ('Nuestras Burgers', 10, TRUE),
    ('Monufusión', 20, TRUE),
    ('Opciones Individuales', 30, TRUE),
    ('Combos', 40, TRUE),
    ('Acompañamientos', 50, TRUE),
    ('Bebidas', 60, TRUE),
    ('Dips Extra', 70, TRUE),
    -- Se crean antes del seed para que sus productos historicos puedan
    -- quedar inactivos tambien en una instalacion desde cero.
    ('Hamburguesas', 100, TRUE),
    ('Acompaniamientos', 110, TRUE),
    ('Postres', 120, TRUE)
ON CONFLICT (nombre) DO UPDATE
SET orden = EXCLUDED.orden, activa = TRUE;

-- Ingredientes que originalmente estaban en seed.sql. Deben existir antes
-- de cargar las recetas porque el ejecutor aplica migraciones y luego seeds.
INSERT INTO ingrediente
    (nombre, unidad_medida, cantidad_actual, umbral_minimo, costo_unitario,
     dias_reposicion)
VALUES
    ('Medallon de carne',     'UNIDAD', 200, 40, 1200.00, '{MARTES,JUEVES,SABADO}'),
    ('Pan de papa',           'UNIDAD', 220, 40,  600.00, '{MARTES,JUEVES,SABADO}'),
    ('Queso cheddar',         'UNIDAD', 300, 50,  400.00, '{MARTES,JUEVES}'),
    ('Panceta',               'GR',    5000, 1000,   8.00, '{MARTES,JUEVES}'),
    ('Lechuga',               'GR',    3000, 800,    3.00, '{MARTES,VIERNES}'),
    ('Tomate',                'GR',    3000, 800,    4.00, '{MARTES,VIERNES}'),
    ('Cebolla caramelizada',  'GR',    2000, 500,    6.00, '{MARTES}'),
    ('Papas congeladas',      'KG',      40, 10,  3500.00, '{MIERCOLES}'),
    ('Helado',                'KG',      10, 3,   6000.00, '{MIERCOLES}'),
    ('Gaseosa linea 500',     'UNIDAD',  80, 20,   900.00, '{LUNES,JUEVES}')
ON CONFLICT (nombre) DO NOTHING;

-- Ingredientes adicionales necesarios para que los productos importados
-- tengan receta y participen del control de disponibilidad/stock.
INSERT INTO ingrediente
    (nombre, unidad_medida, cantidad_actual, umbral_minimo, costo_unitario)
VALUES
    ('Medallon Smash',       'UNIDAD', 120, 20, 1200.00),
    ('Medallon NotCo',       'UNIDAD',  40, 10, 1600.00),
    ('Bacon en cubos',       'GR',    1500, 300,    9.00),
    ('Huevo',                'UNIDAD',  60, 12,  250.00),
    ('Provoleta',            'UNIDAD',  40, 10,  900.00),
    ('Cebolla cruda',        'GR',    1500, 300,    3.00),
    ('Cebolla en cubos',     'GR',    1500, 300,    3.00),
    ('Cebolla crispy',       'GR',    1200, 250,    7.00),
    ('Rucula',               'GR',     800, 150,    5.00),
    ('Pepinillos',           'GR',    1000, 200,    5.00),
    ('Salsa Monu',           'GR',    1500, 300,    4.00),
    ('Alioli',               'GR',    1200, 250,    4.00),
    ('Barbacoa',             'GR',    1200, 250,    4.00),
    ('Mayonesa',             'GR',    1500, 300,    3.00),
    ('Mayonesa ahumada',     'GR',    1000, 200,    5.00),
    ('Ketchup',              'GR',    1500, 300,    3.00),
    ('Mostaza',              'GR',    1500, 300,    3.00),
    ('Salsa Smash',          'GR',    1000, 200,    5.00),
    ('Nuggets congelados',   'UNIDAD', 200, 30,  250.00)
ON CONFLICT (nombre) DO NOTHING;

-- Reservar los productos del seed como historicos evita que seed.sql los
-- reactive al ejecutarse despues de esta migracion en una base nueva.
WITH legado(categoria, nombre, descripcion, precio, orden) AS (
    VALUES
    ('Hamburguesas', 'Monu Clasica', 'Medallon, queso cheddar, lechuga y tomate', 7500.00, 1),
    ('Hamburguesas', 'Monu Doble', 'Doble medallon, doble cheddar y cebolla', 9800.00, 2),
    ('Hamburguesas', 'Monu Bacon', 'Medallon, cheddar y panceta crocante', 8900.00, 3),
    ('Acompaniamientos', 'Papas Monu', 'Porcion de papas fritas', 4200.00, 1),
    ('Postres', 'Helado 1/4', 'Cuarto kilo de helado artesanal', 5000.00, 1),
    ('Bebidas', 'Gaseosa 500ml', 'Linea de gaseosas 500 ml', 2000.00, 99)
)
INSERT INTO producto
    (categoria_id, nombre, descripcion, precio_base, activo, orden)
SELECT c.id, l.nombre, l.descripcion, l.precio, FALSE, l.orden
FROM legado l
JOIN categoria c ON c.nombre = l.categoria
ON CONFLICT (categoria_id, nombre) DO NOTHING;

WITH menu(categoria, nombre, descripcion, precio, imagen, variantes, orden) AS (
    VALUES
    ('Nuestras Burgers', 'Cheese',
     'Ingredientes: Carne, cheddar, salsa monu.', 11000.00,
     '/menu/chesee burger.jpg',
     '[{"nombre":"Simple","precio":11000},{"nombre":"Doble","precio":13500},{"nombre":"Triple","precio":15500}]'::jsonb, 1),
    ('Nuestras Burgers', 'Bacon',
     'Ingredientes: Carne, cheddar, bacon, salsa monu.', 12000.00,
     '/menu/BaconBurger.jpg',
     '[{"nombre":"Simple","precio":12000},{"nombre":"Doble","precio":14500},{"nombre":"Triple","precio":16500}]'::jsonb, 2),
    ('Nuestras Burgers', 'Crispy',
     'Ingredientes: Carne, cheddar, bacon, cebolla crispy, alioli.', 13000.00,
     '/menu/CrispyBurger.jpg',
     '[{"nombre":"Simple","precio":13000},{"nombre":"Doble","precio":15500},{"nombre":"Triple","precio":17500}]'::jsonb, 3),
    ('Nuestras Burgers', 'Monulibra',
     'Ingredientes: Carne, cheddar, cebolla en cubos, ketchup, mostaza.', 13000.00,
     '/menu/MonuLibraBurgerjpg.jpg',
     '[{"nombre":"Simple","precio":13000},{"nombre":"Doble","precio":15500},{"nombre":"Triple","precio":17500}]'::jsonb, 4),
    ('Nuestras Burgers', 'Monuburger',
     'Ingredientes: Carne, cheddar, cebolla caramelizada, bacon, huevo, barbacoa.', 14000.00,
     '/menu/MonuBurger.jpg',
     '[{"nombre":"Simple","precio":14000},{"nombre":"Doble","precio":16500},{"nombre":"Triple","precio":18500}]'::jsonb, 5),
    ('Nuestras Burgers', 'La Típica',
     'Ingredientes: Carne, cheddar, lechuga, tomate, mayonesa.', 12500.00,
     '/menu/LaTipicaBurger.jpg',
     '[{"nombre":"Simple","precio":12500},{"nombre":"Doble","precio":15000},{"nombre":"Triple","precio":17000}]'::jsonb, 6),
    ('Nuestras Burgers', 'Witcher',
     'Ingredientes: Carne, cheddar, bacon, tomate, lechuga, cebolla, pepinillos, mayonesa y ketchup.', 13500.00,
     '/menu/WitcherBurger.jpg',
     '[{"nombre":"Simple","precio":13500},{"nombre":"Doble","precio":16000},{"nombre":"Triple","precio":18000}]'::jsonb, 7),
    ('Nuestras Burgers', '18 Supermash',
     'Ingredientes: Carne smasheada, cheddar, panceta, pepinillo y salsa smash.', 14000.00,
     '/menu/18supersmash.jpg',
     '[{"nombre":"Simple","precio":14000},{"nombre":"Doble","precio":16500},{"nombre":"Triple","precio":18500}]'::jsonb, 8),
    ('Nuestras Burgers', 'Oklahoma',
     'Ingredientes: Carne smasheada con cebolla cruda, cheddar y salsa monu.', 13500.00,
     '/menu/oklahomaBurger.jpg',
     '[{"nombre":"Simple","precio":13500},{"nombre":"Doble","precio":16000},{"nombre":"Triple","precio":18000}]'::jsonb, 9),
    ('Nuestras Burgers', 'Provoteca',
     'Ingredientes: Carne, provoleta, cebolla caramelizada, rúcula y alioli.', 12500.00,
     '/menu/ProvotecaBurger.jpg',
     '[{"nombre":"Simple","precio":12500},{"nombre":"Doble","precio":15000},{"nombre":"Triple","precio":17000}]'::jsonb, 10),
    ('Nuestras Burgers', 'Big Monu',
     'Ingredientes: Carne, cheddar, cebolla, lechuga, pepinillos y salsa monu.', 13000.00,
     '/menu/BigMonuBurger.jpg',
     '[{"nombre":"Simple","precio":13000},{"nombre":"Doble","precio":15500},{"nombre":"Triple","precio":17500}]'::jsonb, 11),
    ('Nuestras Burgers', 'Not Monu',
     'Ingredientes: Medallón NotCo, cheddar, mayonesa, tomate y lechuga.', 13500.00,
     '/menu/notMonu.jpg',
     '[{"nombre":"Simple","precio":13500},{"nombre":"Doble","precio":16000},{"nombre":"Triple","precio":18000}]'::jsonb, 12),
    ('Nuestras Burgers', 'Nueva Jersey',
     'Ingredientes: Carne, cheddar, bacon en cubos tiernizado y mayonesa ahumada.', 14000.00,
     NULL,
     '[{"nombre":"Simple","precio":14000},{"nombre":"Doble","precio":16500},{"nombre":"Triple","precio":18500}]'::jsonb, 13),
    ('Monufusión', 'Baconhoma',
     'Ingredientes: Carne smasheada con cebolla cruda, cheddar, bacon y salsa monu.', 14000.00,
     NULL,
     '[{"nombre":"Simple","precio":14000},{"nombre":"Doble","precio":16500},{"nombre":"Triple","precio":18500}]'::jsonb, 1),
    ('Monufusión', 'Tipiteca',
     'Ingredientes: Carne, provoleta, tomate, rúcula y mayonesa.', 12500.00,
     NULL,
     '[{"nombre":"Simple","precio":12500},{"nombre":"Doble","precio":15000},{"nombre":"Triple","precio":17000}]'::jsonb, 2),
    ('Opciones Individuales', 'Keco',
     'Una carne smasheada, cheddar, cebolla crispy y alioli. No incluye papas.', 9500.00,
     NULL, '[]'::jsonb, 1),
    ('Opciones Individuales', 'Cito',
     'Un medallón de carne, cheddar, cebolla en cubos, ketchup, mostaza y bacon. No incluye papas.', 9500.00,
     NULL, '[]'::jsonb, 2),
    ('Opciones Individuales', 'Tino Andino',
     'Un medallón de carne, provoleta, cheddar en pan y mayonesa. No incluye papas.', 9500.00,
     NULL, '[]'::jsonb, 3),
    ('Opciones Individuales', 'Santi',
     'Un medallón de carne, cheddar, cebolla crispy, lechuga y alioli. No incluye papas.', 9500.00,
     NULL, '[]'::jsonb, 4),
    ('Combos', 'Combo: Típica + Bacon',
     'La Típica doble + Bacon simple + 1 porción de papas.', 23000.00,
     NULL, '[]'::jsonb, 1),
    ('Combos', 'Combo: Bacon + Típica',
     'Bacon doble + La Típica simple + 1 porción de papas.', 23000.00,
     NULL, '[]'::jsonb, 2),
    ('Combos', 'Combo: Nuggets + Papas',
     'Nuggets + papas fritas.', 15000.00,
     '/menu/nuggetsmonu.jpg', '[]'::jsonb, 3),
    ('Acompañamientos', 'Papas Fritas (Porción)',
     'Porción de papas fritas.', 8000.00,
     '/menu/papasfritasMonu.jpg', '[]'::jsonb, 1),
    ('Acompañamientos', 'Nuggets',
     '10 unidades. Incluye 2 dips: salsa monu y barbacoa.', 11000.00,
     '/menu/nuggetsmonu.jpg', '[]'::jsonb, 2),
    ('Bebidas', 'Coca Cola', '500 ml', 2200.00,
     '/menu/cocacolamonu.jpg', '[]'::jsonb, 1),
    ('Bebidas', 'Sprite', '500 ml', 2200.00,
     '/menu/sprite.jpg', '[]'::jsonb, 2),
    ('Bebidas', 'Fanta', '500 ml', 2200.00,
     '/menu/fantamonu.jpg', '[]'::jsonb, 3),
    ('Dips Extra', 'Salsa Monu', 'Dip extra', 1000.00, NULL, '[]'::jsonb, 1),
    ('Dips Extra', 'Alioli', 'Dip extra', 1000.00, NULL, '[]'::jsonb, 2),
    ('Dips Extra', 'Barbacoa', 'Dip extra', 1000.00, NULL, '[]'::jsonb, 3),
    ('Dips Extra', 'Mayonesa', 'Dip extra', 1000.00, NULL, '[]'::jsonb, 4),
    ('Dips Extra', 'Ketchup', 'Dip extra', 1000.00, NULL, '[]'::jsonb, 5),
    ('Dips Extra', 'Mostaza', 'Dip extra', 1000.00, NULL, '[]'::jsonb, 6)
)
INSERT INTO producto
    (categoria_id, nombre, descripcion, precio_base, imagen_url, variantes, activo, orden)
SELECT c.id, m.nombre, m.descripcion, m.precio, m.imagen, m.variantes, TRUE, m.orden
FROM menu m
JOIN categoria c ON c.nombre = m.categoria
ON CONFLICT (categoria_id, nombre) DO UPDATE
SET descripcion = EXCLUDED.descripcion,
    precio_base = EXCLUDED.precio_base,
    imagen_url = EXCLUDED.imagen_url,
    variantes = EXCLUDED.variantes,
    activo = TRUE,
    orden = EXCLUDED.orden,
    actualizado_en = now();

-- Receta mínima coherente por familia. Los ingredientes detallados del texto
-- quedan disponibles para ampliar las recetas desde el panel sin recrear el
-- producto. Esto preserva control de stock para todos los items importados.
WITH receta(producto, ingrediente, cantidad) AS (
    VALUES
    ('Cheese', 'Medallon de carne', 1.000),
    ('Bacon', 'Medallon de carne', 1.000),
    ('Crispy', 'Medallon de carne', 1.000),
    ('Monulibra', 'Medallon de carne', 1.000),
    ('Monuburger', 'Medallon de carne', 1.000),
    ('La Típica', 'Medallon de carne', 1.000),
    ('Witcher', 'Medallon de carne', 1.000),
    ('18 Supermash', 'Medallon Smash', 1.000),
    ('Oklahoma', 'Medallon Smash', 1.000),
    ('Provoteca', 'Medallon de carne', 1.000),
    ('Big Monu', 'Medallon de carne', 1.000),
    ('Not Monu', 'Medallon NotCo', 1.000),
    ('Nueva Jersey', 'Medallon de carne', 1.000),
    ('Baconhoma', 'Medallon Smash', 1.000),
    ('Tipiteca', 'Medallon de carne', 1.000),
    ('Keco', 'Medallon Smash', 1.000),
    ('Cito', 'Medallon de carne', 1.000),
    ('Tino Andino', 'Medallon de carne', 1.000),
    ('Santi', 'Medallon de carne', 1.000),
    ('Combo: Típica + Bacon', 'Medallon de carne', 3.000),
    ('Combo: Bacon + Típica', 'Medallon de carne', 3.000),
    ('Combo: Nuggets + Papas', 'Nuggets congelados', 10.000),
    ('Papas Fritas (Porción)', 'Papas congeladas', 0.300),
    ('Nuggets', 'Nuggets congelados', 10.000),
    ('Coca Cola', 'Gaseosa linea 500', 1.000),
    ('Sprite', 'Gaseosa linea 500', 1.000),
    ('Fanta', 'Gaseosa linea 500', 1.000),
    ('Salsa Monu', 'Salsa Monu', 0.050),
    ('Alioli', 'Alioli', 0.050),
    ('Barbacoa', 'Barbacoa', 0.050),
    ('Mayonesa', 'Mayonesa', 0.050),
    ('Ketchup', 'Ketchup', 0.050),
    ('Mostaza', 'Mostaza', 0.050)
)
INSERT INTO producto_ingrediente
    (producto_id, ingrediente_id, cantidad_requerida, es_base)
SELECT p.id, i.id, r.cantidad, TRUE
FROM receta r
JOIN producto p ON p.nombre = r.producto
JOIN ingrediente i ON i.nombre = r.ingrediente
ON CONFLICT (producto_id, ingrediente_id) DO UPDATE
SET cantidad_requerida = EXCLUDED.cantidad_requerida,
    es_base = TRUE;

UPDATE producto
SET activo = FALSE, actualizado_en = now()
WHERE nombre IN (
    'Monu Clasica', 'Monu Doble', 'Monu Bacon',
    'Papas Monu', 'Helado 1/4', 'Gaseosa 500ml'
);
