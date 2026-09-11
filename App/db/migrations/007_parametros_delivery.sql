-- =====================================================================
-- 007 - Parametros del modulo de asignacion de repartidores
-- =====================================================================

-- ---------------------------------------------------------------------
-- Criterio de agrupacion acordado con el cliente: dos pedidos viajan
-- juntos si estan en la MISMA zona de cobertura y a menos de este radio
-- entre si. La zona sola no alcanza (Ensenada es grande); el radio solo
-- tampoco (la distancia en linea recta engania entre zonas separadas por
-- el arroyo o la autopista).
-- ---------------------------------------------------------------------
INSERT INTO parametro (clave, valor, descripcion) VALUES
    ('delivery.radio_agrupacion_km', '1.5',
     'Distancia maxima entre dos pedidos para que salgan en el mismo viaje'),
    ('delivery.radio_busqueda_repartidor_km', '10',
     'Distancia maxima entre un repartidor y el primer domicilio del viaje'),
    ('delivery.espera_segundo_pedido', 'false',
     'Si es true, el sistema retiene un pedido esperando otro cercano. '
     'Acordado en false: un pedido listo sale solo, sin sumar demora.')
ON CONFLICT (clave) DO NOTHING;

-- Los pedidos listos para despacho se consultan en cada planificacion.
CREATE INDEX IF NOT EXISTS pedido_listo_idx ON pedido (creado_en)
    WHERE estado = 'LISTO';
