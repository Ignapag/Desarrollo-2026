-- =====================================================================
-- Datos iniciales de desarrollo - Monu Burger
-- Idempotente: se puede ejecutar varias veces sin duplicar.
-- Las contrasenias se hashean con bcrypt via pgcrypto (crypt + gen_salt('bf')),
-- compatible con la verificacion que hace el backend en Python.
-- =====================================================================

-- ------------------------- Parametros ---------------------------------
INSERT INTO parametro (clave, valor, descripcion) VALUES
    ('negocio.nombre',                 'Monu Burger',  'Nombre comercial'),
    ('negocio.telefono_whatsapp',      '5492211234567','Numero exclusivo del negocio'),
    ('pedido.minutos_cancelacion',     '5',            'Minutos para cancelar tras confirmar'),
    ('delivery.pedidos_por_viaje',     '2',            'Pedidos maximos por salida de repartidor'),
    ('caja.hora_cierre_noche',         '00:00',        'Cierre automatico turno noche'),
    ('caja.hora_cierre_mediodia',      '14:30',        'Cierre automatico turno mediodia'),
    ('notificacion.demora_max_segundos','30',          'RNF-10: demora maxima de notificacion')
ON CONFLICT (clave) DO NOTHING;

-- ------------------------- Usuarios -----------------------------------
-- Contrasenia de todos los usuarios de desarrollo: Monu2026!
INSERT INTO usuario (nombre, apellido, username, email, telefono, password_hash, rol) VALUES
    ('Admin',   'Sistema',    'admin',      'admin@monuburger.local',    NULL, crypt('Monu2026!', gen_salt('bf')), 'ADMINISTRADOR'),
    ('Ignacio', 'Pagotto',    'ipagotto',   'ipagotto@monuburger.local', NULL, crypt('Monu2026!', gen_salt('bf')), 'DUENIO'),
    ('Jose',    'Santoro',    'jsantoro',   'jsantoro@monuburger.local', NULL, crypt('Monu2026!', gen_salt('bf')), 'DUENIO'),
    ('Emilio',  'Rivero',     'erivero',    'erivero@monuburger.local',  NULL, crypt('Monu2026!', gen_salt('bf')), 'DUENIO'),
    ('Juan',    'Martinez',   'jmartinez',  'jmartinez@monuburger.local',NULL, crypt('Monu2026!', gen_salt('bf')), 'DUENIO'),
    ('Nicolas', 'Leguizamon', 'nleguizamon','nleguiza@monuburger.local', NULL, crypt('Monu2026!', gen_salt('bf')), 'EMPLEADO'),
    ('Tomas',   'Aramburu',   'taramburu',  'taramburu@monuburger.local',NULL, crypt('Monu2026!', gen_salt('bf')), 'EMPLEADO'),
    ('Marcos',  'Delivery',   'mdelivery',  NULL,                        '2211111111', crypt('Monu2026!', gen_salt('bf')), 'REPARTIDOR'),
    ('Lucia',   'Delivery',   'ldelivery',  NULL,                        '2212222222', crypt('Monu2026!', gen_salt('bf')), 'REPARTIDOR'),
    ('Ana',     'Cliente',    'acliente',   'ana@example.com',           '2213333333', crypt('Monu2026!', gen_salt('bf')), 'CLIENTE')
ON CONFLICT (username) DO NOTHING;

INSERT INTO repartidor (usuario_id, estado, vehiculo, ultima_lat, ultima_lng)
SELECT id, 'DISPONIBLE', 'Moto', -34.860000, -57.910000 FROM usuario WHERE username = 'mdelivery'
ON CONFLICT (usuario_id) DO NOTHING;

INSERT INTO repartidor (usuario_id, estado, vehiculo, ultima_lat, ultima_lng)
SELECT id, 'DISPONIBLE', 'Moto', -34.865000, -57.920000 FROM usuario WHERE username = 'ldelivery'
ON CONFLICT (usuario_id) DO NOTHING;

INSERT INTO cliente (usuario_id, telefono_whatsapp)
SELECT id, '5492213333333' FROM usuario WHERE username = 'acliente'
ON CONFLICT (usuario_id) DO NOTHING;

-- ------------------------- Zonas de cobertura -------------------------
-- Poligonos aproximados (GeoJSON, pares [lng, lat]) de las zonas relevadas.
INSERT INTO zona_cobertura (nombre, descripcion, poligono, centro_lat, centro_lng, costo_envio) VALUES
    ('Ensenada', 'Ensenada completo',
     '{"type":"Polygon","coordinates":[[[-57.935,-34.835],[-57.880,-34.835],[-57.880,-34.885],[-57.935,-34.885],[-57.935,-34.835]]]}',
     -34.860000, -57.907000, 0),
    ('El Dique', 'El Dique completo',
     '{"type":"Polygon","coordinates":[[[-57.965,-34.850],[-57.930,-34.850],[-57.930,-34.890],[-57.965,-34.890],[-57.965,-34.850]]]}',
     -34.870000, -57.948000, 0),
    ('Punta Lara', 'Hasta el Hospital Municipal',
     '{"type":"Polygon","coordinates":[[[-57.985,-34.800],[-57.930,-34.800],[-57.930,-34.840],[-57.985,-34.840],[-57.985,-34.800]]]}',
     -34.820000, -57.958000, 0)
ON CONFLICT (nombre) DO NOTHING;

INSERT INTO punto_encuentro (nombre, referencia, lat, lng, zona_id)
SELECT 'Hospital Municipal Punta Lara', 'Limite de zona hacia Punta Lara', -34.808000, -57.965000, id
FROM zona_cobertura WHERE nombre = 'Punta Lara'
ON CONFLICT DO NOTHING;

-- ------------------------- Categorias ---------------------------------
INSERT INTO categoria (nombre, orden) VALUES
    ('Hamburguesas', 1),
    ('Acompaniamientos', 2),
    ('Postres', 3),
    ('Bebidas', 4)
ON CONFLICT (nombre) DO NOTHING;

-- ------------------------- Ingredientes -------------------------------
INSERT INTO ingrediente (nombre, unidad_medida, cantidad_actual, umbral_minimo, costo_unitario, dias_reposicion) VALUES
    ('Medallon de carne', 'UNIDAD', 200, 40, 1200.00, '{MARTES,JUEVES,SABADO}'),
    ('Pan de papa',       'UNIDAD', 220, 40,  600.00, '{MARTES,JUEVES,SABADO}'),
    ('Queso cheddar',     'UNIDAD', 300, 50,  400.00, '{MARTES,JUEVES}'),
    ('Panceta',           'GR',    5000, 1000,   8.00, '{MARTES,JUEVES}'),
    ('Lechuga',           'GR',    3000,  800,   3.00, '{MARTES,VIERNES}'),
    ('Tomate',            'GR',    3000,  800,   4.00, '{MARTES,VIERNES}'),
    ('Cebolla caramelizada','GR',  2000,  500,   6.00, '{MARTES}'),
    ('Papas congeladas',  'KG',      40,   10, 3500.00, '{MIERCOLES}'),
    ('Helado',            'KG',      10,    3, 6000.00, '{MIERCOLES}'),
    ('Gaseosa linea 500',  'UNIDAD',  80,   20,  900.00, '{LUNES,JUEVES}')
ON CONFLICT (nombre) DO NOTHING;

-- ------------------------- Productos ----------------------------------
INSERT INTO producto (categoria_id, nombre, descripcion, precio_base, orden)
SELECT c.id, v.nombre, v.descripcion, v.precio, v.orden
FROM (VALUES
    ('Hamburguesas',    'Monu Clasica',   'Medallon, queso cheddar, lechuga y tomate',        7500.00, 1),
    ('Hamburguesas',    'Monu Doble',     'Doble medallon, doble cheddar y cebolla',          9800.00, 2),
    ('Hamburguesas',    'Monu Bacon',     'Medallon, cheddar y panceta crocante',             8900.00, 3),
    ('Acompaniamientos','Papas Monu',     'Porcion de papas fritas',                          4200.00, 1),
    ('Postres',         'Helado 1/4',     'Cuarto kilo de helado artesanal',                  5000.00, 1),
    ('Bebidas',         'Gaseosa 500ml',  'Linea de gaseosas 500 ml',                         2000.00, 1)
) AS v(categoria, nombre, descripcion, precio, orden)
JOIN categoria c ON c.nombre = v.categoria
ON CONFLICT (categoria_id, nombre) DO NOTHING;

-- ------------------------- Recetas ------------------------------------
INSERT INTO producto_ingrediente (producto_id, ingrediente_id, cantidad_requerida, es_base)
SELECT p.id, i.id, v.cantidad, v.es_base
FROM (VALUES
    ('Monu Clasica', 'Medallon de carne', 1,   TRUE),
    ('Monu Clasica', 'Pan de papa',       1,   TRUE),
    ('Monu Clasica', 'Queso cheddar',     1,   TRUE),
    ('Monu Clasica', 'Lechuga',           20,  FALSE),
    ('Monu Clasica', 'Tomate',            30,  FALSE),
    ('Monu Doble',   'Medallon de carne', 2,   TRUE),
    ('Monu Doble',   'Pan de papa',       1,   TRUE),
    ('Monu Doble',   'Queso cheddar',     2,   TRUE),
    ('Monu Doble',   'Cebolla caramelizada', 40, FALSE),
    ('Monu Bacon',   'Medallon de carne', 1,   TRUE),
    ('Monu Bacon',   'Pan de papa',       1,   TRUE),
    ('Monu Bacon',   'Queso cheddar',     1,   TRUE),
    ('Monu Bacon',   'Panceta',           50,  TRUE),
    ('Papas Monu',   'Papas congeladas',  0.3, TRUE),
    ('Helado 1/4',   'Helado',            0.25,TRUE),
    ('Gaseosa 500ml','Gaseosa linea 500', 1,   TRUE)
) AS v(producto, ingrediente, cantidad, es_base)
JOIN producto p    ON p.nombre = v.producto
JOIN ingrediente i ON i.nombre = v.ingrediente
ON CONFLICT (producto_id, ingrediente_id) DO NOTHING;

-- ------------------------- Opcionales (RF-03) -------------------------
INSERT INTO producto_opcion (producto_id, ingrediente_id, tipo, costo_adicional, cantidad_requerida, max_por_item)
SELECT p.id, i.id, v.tipo, v.costo, v.cantidad, v.maximo
FROM (VALUES
    ('Monu Clasica', 'Queso cheddar', 'AGREGADO', 700.00,  1,  2),
    ('Monu Clasica', 'Panceta',       'AGREGADO', 1200.00, 50, 1),
    ('Monu Clasica', 'Lechuga',       'QUITADO',  0.00,    20, 1),
    ('Monu Clasica', 'Tomate',        'QUITADO',  0.00,    30, 1),
    ('Monu Doble',   'Panceta',       'AGREGADO', 1200.00, 50, 1),
    ('Monu Bacon',   'Queso cheddar', 'AGREGADO', 700.00,  1,  2)
) AS v(producto, ingrediente, tipo, costo, cantidad, maximo)
JOIN producto p    ON p.nombre = v.producto
JOIN ingrediente i ON i.nombre = v.ingrediente
ON CONFLICT (producto_id, ingrediente_id, tipo) DO NOTHING;

-- ------------------------- Plantillas de notificacion -----------------
INSERT INTO notificacion_plantilla (clave, nombre, cuerpo) VALUES
    ('BIENVENIDA', 'Mensaje de bienvenida',
     'Hola! Bienvenido a Monu Burger. Para hacer tu pedido entra a {{url_menu}}. Nuestro horario es de 19:30 a 00:00 hs.'),
    ('PEDIDO_CONFIRMADO', 'Pedido confirmado',
     'Recibimos tu pedido #{{numero_pedido}} por ${{total}}. Te avisamos cuando salga para tu domicilio.'),
    ('EN_CAMINO', 'Pedido en camino',
     'Tu pedido #{{numero_pedido}} ya salio con {{repartidor}}. Llega en unos minutos!'),
    ('ENTREGADO', 'Pedido entregado',
     'Tu pedido #{{numero_pedido}} fue entregado. Gracias por elegir Monu Burger!')
ON CONFLICT (clave) DO NOTHING;
