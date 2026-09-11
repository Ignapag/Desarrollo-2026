-- =====================================================================
-- 004 - Delivery: viajes (salidas) y envios
-- =====================================================================

-- ---------------------------------------------------------------------
-- viaje: entidad nueva. La regla del negocio dice que cada repartidor
-- sale con hasta 2 pedidos cercanos entre si; el ER tenia ENVIO 1:1 con
-- PEDIDO y no podia representar esa agrupacion. Ver CAMBIOS.md (C-06).
-- ---------------------------------------------------------------------
CREATE TABLE viaje (
    id              BIGINT      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    repartidor_id   BIGINT      NOT NULL REFERENCES repartidor (usuario_id) ON DELETE RESTRICT,
    estado          TEXT        NOT NULL DEFAULT 'PLANIFICADO',
    creado_en       TIMESTAMPTZ NOT NULL DEFAULT now(),
    salida_en       TIMESTAMPTZ,
    retorno_en      TIMESTAMPTZ,
    asignado_por    BIGINT      REFERENCES usuario (id) ON DELETE SET NULL,
    asignacion_auto BOOLEAN     NOT NULL DEFAULT TRUE,
    CONSTRAINT viaje_estado_chk CHECK (estado IN ('PLANIFICADO','EN_RUTA','FINALIZADO','CANCELADO'))
);

CREATE INDEX viaje_repartidor_idx ON viaje (repartidor_id, creado_en DESC);

-- Un repartidor no puede tener dos viajes abiertos a la vez
CREATE UNIQUE INDEX viaje_abierto_uk ON viaje (repartidor_id)
    WHERE estado IN ('PLANIFICADO','EN_RUTA');

CREATE TABLE envio (
    id                  BIGINT      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    pedido_id           BIGINT      NOT NULL UNIQUE REFERENCES pedido (id) ON DELETE CASCADE,
    viaje_id            BIGINT      REFERENCES viaje (id) ON DELETE SET NULL,
    zona_id             BIGINT      REFERENCES zona_cobertura (id) ON DELETE SET NULL,
    punto_encuentro_id  BIGINT      REFERENCES punto_encuentro (id) ON DELETE SET NULL,
    orden_en_viaje      INT         NOT NULL DEFAULT 1,
    estado              TEXT        NOT NULL DEFAULT 'PENDIENTE',
    distancia_km        NUMERIC(8,3),
    asignado_en         TIMESTAMPTZ,
    en_camino_en        TIMESTAMPTZ,
    entregado_en        TIMESTAMPTZ,
    observaciones       TEXT,
    CONSTRAINT envio_estado_chk CHECK (estado IN ('PENDIENTE','ASIGNADO','EN_CAMINO','ENTREGADO','FALLIDO')),
    CONSTRAINT envio_orden_chk  CHECK (orden_en_viaje > 0)
);

CREATE INDEX envio_viaje_idx  ON envio (viaje_id, orden_en_viaje);
CREATE INDEX envio_estado_idx ON envio (estado);

-- ---------------------------------------------------------------------
-- Limite de 2 pedidos por salida (regla de negocio del alcance).
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION valida_capacidad_viaje()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $func$
DECLARE
    v_max   INT;
    v_carga INT;
BEGIN
    IF NEW.viaje_id IS NULL THEN
        RETURN NEW;
    END IF;

    SELECT COALESCE((SELECT valor::INT FROM parametro WHERE clave = 'delivery.pedidos_por_viaje'), 2)
      INTO v_max;

    SELECT count(*) INTO v_carga
    FROM envio
    WHERE viaje_id = NEW.viaje_id
      AND id <> COALESCE(NEW.id, -1);

    IF v_carga >= v_max THEN
        RAISE EXCEPTION 'El viaje % ya tiene % pedidos asignados (maximo %)',
            NEW.viaje_id, v_carga, v_max
            USING ERRCODE = 'check_violation';
    END IF;

    RETURN NEW;
END;
$func$;

CREATE TRIGGER envio_capacidad_trg
    BEFORE INSERT OR UPDATE OF viaje_id ON envio
    FOR EACH ROW
    EXECUTE FUNCTION valida_capacidad_viaje();

-- ---------------------------------------------------------------------
-- distancia_km: haversine, para la asignacion por cercania (RF-04)
-- sin depender de PostGIS.
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION distancia_km(lat1 NUMERIC, lng1 NUMERIC, lat2 NUMERIC, lng2 NUMERIC)
RETURNS NUMERIC
LANGUAGE sql
IMMUTABLE
AS $func$
    SELECT CASE
        WHEN lat1 IS NULL OR lng1 IS NULL OR lat2 IS NULL OR lng2 IS NULL THEN NULL
        ELSE ROUND((
            6371 * 2 * asin(sqrt(
                power(sin(radians(lat2 - lat1) / 2), 2) +
                cos(radians(lat1)) * cos(radians(lat2)) *
                power(sin(radians(lng2 - lng1) / 2), 2)
            ))
        )::NUMERIC, 3)
    END;
$func$;
