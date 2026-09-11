-- =====================================================================
-- 008 - Sobrecargas de las funciones geograficas para double precision
-- =====================================================================
--
-- Las funciones de la migracion 004 y 001 estan declaradas con NUMERIC.
-- Cuando se las llama desde Python con floats, psycopg los envia como
-- double precision y PostgreSQL responde:
--
--     function distancia_km(double precision, ...) does not exist
--
-- Obligar a cada modulo a castear en cada consulta es una fuente segura de
-- errores, asi que se agregan sobrecargas que delegan en las originales.
-- Las migraciones ya aplicadas no se tocan.
-- =====================================================================

CREATE OR REPLACE FUNCTION distancia_km(
    lat1 DOUBLE PRECISION,
    lng1 DOUBLE PRECISION,
    lat2 DOUBLE PRECISION,
    lng2 DOUBLE PRECISION
)
RETURNS NUMERIC
LANGUAGE sql
IMMUTABLE
AS $func$
    SELECT distancia_km(lat1::NUMERIC, lng1::NUMERIC, lat2::NUMERIC, lng2::NUMERIC);
$func$;

CREATE OR REPLACE FUNCTION punto_en_zona(
    p_lat DOUBLE PRECISION,
    p_lng DOUBLE PRECISION,
    p_poligono JSONB
)
RETURNS BOOLEAN
LANGUAGE sql
IMMUTABLE
AS $func$
    SELECT punto_en_zona(p_lat::NUMERIC, p_lng::NUMERIC, p_poligono);
$func$;
