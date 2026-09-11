-- =====================================================================
-- 001 - Usuarios, seguridad, zonas de cobertura y direcciones
-- Sistema de Gestion Monu Burger
-- =====================================================================

CREATE EXTENSION IF NOT EXISTS citext;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ---------------------------------------------------------------------
-- usuario: unifica a TODOS los actores con credenciales del sistema.
-- Cambio respecto del ER original: CLIENTE pasa a ser un subtipo de
-- USUARIO (antes era una entidad suelta sin credenciales), porque el
-- alcance exige que el cliente inicie sesion, siga su pedido y consulte
-- su historial de pedidos. Ver CAMBIOS.md (C-09).
-- ---------------------------------------------------------------------
CREATE TABLE usuario (
    id              BIGINT      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nombre          TEXT        NOT NULL,
    apellido        TEXT        NOT NULL,
    username        CITEXT      NOT NULL UNIQUE,
    email           CITEXT      UNIQUE,
    telefono        TEXT,
    password_hash   TEXT        NOT NULL,
    rol             TEXT        NOT NULL,
    estado          TEXT        NOT NULL DEFAULT 'ACTIVO',
    fecha_alta      TIMESTAMPTZ NOT NULL DEFAULT now(),
    actualizado_en  TIMESTAMPTZ NOT NULL DEFAULT now(),
    ultimo_acceso   TIMESTAMPTZ,
    CONSTRAINT usuario_rol_chk    CHECK (rol IN ('ADMINISTRADOR','DUENIO','EMPLEADO','REPARTIDOR','CLIENTE')),
    CONSTRAINT usuario_estado_chk CHECK (estado IN ('ACTIVO','INACTIVO')),
    CONSTRAINT usuario_nombre_chk CHECK (length(btrim(nombre)) > 0),
    CONSTRAINT usuario_user_chk   CHECK (length(username) >= 4)
);

CREATE INDEX usuario_rol_idx ON usuario (rol) WHERE estado = 'ACTIVO';

-- ---------------------------------------------------------------------
-- repartidor: atributos propios del subtipo REPARTIDOR.
-- Se agregan coordenadas de ultima posicion conocida para poder resolver
-- la asignacion "por cercania" que pide RF-04. Ver CAMBIOS.md (C-05).
-- ---------------------------------------------------------------------
CREATE TABLE repartidor (
    usuario_id      BIGINT      PRIMARY KEY REFERENCES usuario (id) ON DELETE RESTRICT,
    estado          TEXT        NOT NULL DEFAULT 'DISPONIBLE',
    vehiculo        TEXT,
    ultima_lat      NUMERIC(9,6),
    ultima_lng      NUMERIC(9,6),
    ultima_pos_en   TIMESTAMPTZ,
    CONSTRAINT repartidor_estado_chk CHECK (estado IN ('DISPONIBLE','EN_RUTA','FUERA_DE_SERVICIO'))
);

-- ---------------------------------------------------------------------
-- cliente: atributos propios del subtipo CLIENTE.
-- ---------------------------------------------------------------------
CREATE TABLE cliente (
    usuario_id          BIGINT      PRIMARY KEY REFERENCES usuario (id) ON DELETE RESTRICT,
    telefono_whatsapp   TEXT        NOT NULL,
    acepta_notif_wsp    BOOLEAN     NOT NULL DEFAULT TRUE,
    notas               TEXT
);

CREATE INDEX cliente_telefono_idx ON cliente (telefono_whatsapp);

-- ---------------------------------------------------------------------
-- zona_cobertura: entidad nueva. El ER solo tenia un atributo "zona"
-- dentro de ENVIO, insuficiente para validar direcciones (RF-12).
-- El poligono se guarda como GeoJSON en jsonb para dibujarlo con Leaflet
-- y validar el punto con punto_en_zona(). Ver CAMBIOS.md (C-04).
-- ---------------------------------------------------------------------
CREATE TABLE zona_cobertura (
    id              BIGINT      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nombre          TEXT        NOT NULL UNIQUE,
    descripcion     TEXT,
    poligono        JSONB       NOT NULL,
    centro_lat      NUMERIC(9,6) NOT NULL,
    centro_lng      NUMERIC(9,6) NOT NULL,
    costo_envio     NUMERIC(12,2) NOT NULL DEFAULT 0,
    activa          BOOLEAN     NOT NULL DEFAULT TRUE,
    CONSTRAINT zona_costo_chk CHECK (costo_envio >= 0)
);

-- ---------------------------------------------------------------------
-- punto_encuentro: puntos intermedios propuestos para pedidos fuera de
-- zona, tal como opera hoy el negocio (RF-12).
-- ---------------------------------------------------------------------
CREATE TABLE punto_encuentro (
    id              BIGINT      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nombre          TEXT        NOT NULL,
    referencia      TEXT,
    lat             NUMERIC(9,6) NOT NULL,
    lng             NUMERIC(9,6) NOT NULL,
    zona_id         BIGINT      REFERENCES zona_cobertura (id) ON DELETE SET NULL,
    activo          BOOLEAN     NOT NULL DEFAULT TRUE
);

-- ---------------------------------------------------------------------
-- direccion: se normaliza como entidad propia (el ER la tenia como
-- atributo compuesto repetido en CLIENTE y en PEDIDO) y se le agregan
-- coordenadas + zona resuelta. Ver CAMBIOS.md (C-05).
-- ---------------------------------------------------------------------
CREATE TABLE direccion (
    id              BIGINT      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    cliente_id      BIGINT      NOT NULL REFERENCES cliente (usuario_id) ON DELETE CASCADE,
    calle           TEXT        NOT NULL,
    numero          TEXT        NOT NULL,
    piso_depto      TEXT,
    codigo_postal   TEXT,
    localidad       TEXT,
    referencia      TEXT,
    lat             NUMERIC(9,6),
    lng             NUMERIC(9,6),
    zona_id         BIGINT      REFERENCES zona_cobertura (id) ON DELETE SET NULL,
    es_principal    BOOLEAN     NOT NULL DEFAULT FALSE,
    activa          BOOLEAN     NOT NULL DEFAULT TRUE,
    creada_en       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX direccion_cliente_idx ON direccion (cliente_id) WHERE activa;

-- ---------------------------------------------------------------------
-- auditoria: implementa HISTORIALACTIVIDAD del ER y el RNF-09.
-- Se agregan entidad / entidad_id / datos para que el log sea consultable
-- por objeto afectado y no solo por texto libre. Ver CAMBIOS.md (C-08).
-- ---------------------------------------------------------------------
CREATE TABLE auditoria (
    id              BIGINT      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    usuario_id      BIGINT      REFERENCES usuario (id) ON DELETE SET NULL,
    accion          TEXT        NOT NULL,
    entidad         TEXT        NOT NULL,
    entidad_id      TEXT,
    datos           JSONB,
    ip              INET,
    creado_en       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX auditoria_fecha_idx   ON auditoria (creado_en DESC);
CREATE INDEX auditoria_entidad_idx ON auditoria (entidad, entidad_id);
CREATE INDEX auditoria_usuario_idx ON auditoria (usuario_id, creado_en DESC);

-- ---------------------------------------------------------------------
-- parametro: parametros globales del negocio (horarios de turno,
-- minutos de cancelacion, umbral de notificaciones, etc.).
-- ---------------------------------------------------------------------
CREATE TABLE parametro (
    clave           TEXT        PRIMARY KEY,
    valor           TEXT        NOT NULL,
    descripcion     TEXT,
    actualizado_en  TIMESTAMPTZ NOT NULL DEFAULT now(),
    actualizado_por BIGINT      REFERENCES usuario (id) ON DELETE SET NULL
);

-- ---------------------------------------------------------------------
-- punto_en_zona: ray casting sobre el poligono GeoJSON de la zona.
-- Evita depender de PostGIS, que no esta en el stack declarado.
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION punto_en_zona(p_lat NUMERIC, p_lng NUMERIC, p_poligono JSONB)
RETURNS BOOLEAN
LANGUAGE plpgsql
IMMUTABLE
AS $func$
DECLARE
    v_puntos  JSONB;
    v_total   INT;
    v_i       INT;
    v_j       INT;
    v_dentro  BOOLEAN := FALSE;
    xi NUMERIC; yi NUMERIC; xj NUMERIC; yj NUMERIC;
BEGIN
    IF p_lat IS NULL OR p_lng IS NULL OR p_poligono IS NULL THEN
        RETURN FALSE;
    END IF;

    -- GeoJSON Polygon: coordinates[0] = anillo exterior, pares [lng, lat]
    v_puntos := p_poligono -> 'coordinates' -> 0;
    IF v_puntos IS NULL THEN
        RETURN FALSE;
    END IF;

    v_total := jsonb_array_length(v_puntos);
    v_j := v_total - 1;

    FOR v_i IN 0 .. v_total - 1 LOOP
        xi := (v_puntos -> v_i ->> 0)::NUMERIC;
        yi := (v_puntos -> v_i ->> 1)::NUMERIC;
        xj := (v_puntos -> v_j ->> 0)::NUMERIC;
        yj := (v_puntos -> v_j ->> 1)::NUMERIC;

        IF ((yi > p_lat) <> (yj > p_lat))
           AND (p_lng < (xj - xi) * (p_lat - yi) / NULLIF(yj - yi, 0) + xi) THEN
            v_dentro := NOT v_dentro;
        END IF;

        v_j := v_i;
    END LOOP;

    RETURN v_dentro;
END;
$func$;
