-- =====================================================================
-- 003 - Pedidos, personalizacion, historial de estados y promociones
-- =====================================================================

CREATE SEQUENCE pedido_numero_seq START 1000;

CREATE TABLE pedido (
    id                  BIGINT        GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    numero              BIGINT        NOT NULL UNIQUE DEFAULT nextval('pedido_numero_seq'),
    cliente_id          BIGINT        NOT NULL REFERENCES cliente (usuario_id) ON DELETE RESTRICT,
    tipo_entrega        TEXT          NOT NULL DEFAULT 'DELIVERY',
    direccion_id        BIGINT        REFERENCES direccion (id) ON DELETE RESTRICT,
    punto_encuentro_id  BIGINT        REFERENCES punto_encuentro (id) ON DELETE SET NULL,
    canal               TEXT          NOT NULL DEFAULT 'WEB',
    estado              TEXT          NOT NULL DEFAULT 'PENDIENTE',
    subtotal            NUMERIC(12,2) NOT NULL DEFAULT 0,
    costo_envio         NUMERIC(12,2) NOT NULL DEFAULT 0,
    descuento_total     NUMERIC(12,2) NOT NULL DEFAULT 0,
    total               NUMERIC(12,2) NOT NULL DEFAULT 0,
    observaciones       TEXT,
    hora_entrega_pedida TIMESTAMPTZ,
    creado_en           TIMESTAMPTZ   NOT NULL DEFAULT now(),
    confirmado_en       TIMESTAMPTZ,
    cancelable_hasta    TIMESTAMPTZ,
    entregado_en        TIMESTAMPTZ,
    cancelado_en        TIMESTAMPTZ,
    motivo_cancelacion  TEXT,
    -- Estados del alcance: pendiente, en preparacion, listo, en camino, entregado
    CONSTRAINT pedido_estado_chk CHECK (estado IN
        ('PENDIENTE','CONFIRMADO','EN_PREPARACION','LISTO','EN_CAMINO','ENTREGADO','CANCELADO')),
    CONSTRAINT pedido_tipo_chk   CHECK (tipo_entrega IN ('DELIVERY','RETIRO')),
    CONSTRAINT pedido_canal_chk  CHECK (canal IN ('WEB','WHATSAPP','MOSTRADOR')),
    CONSTRAINT pedido_montos_chk CHECK (subtotal >= 0 AND descuento_total >= 0 AND total >= 0),
    -- Validacion del alcance: la direccion es obligatoria para delivery
    CONSTRAINT pedido_direccion_chk CHECK (tipo_entrega <> 'DELIVERY' OR direccion_id IS NOT NULL)
);

CREATE INDEX pedido_estado_idx  ON pedido (estado, creado_en DESC);
CREATE INDEX pedido_cliente_idx ON pedido (cliente_id, creado_en DESC);
CREATE INDEX pedido_fecha_idx   ON pedido (creado_en DESC);

-- ---------------------------------------------------------------------
-- pedido_item: los precios se congelan al confirmar (snapshot), para que
-- un cambio de precio en el menu no altere pedidos ni reportes historicos.
-- ---------------------------------------------------------------------
CREATE TABLE pedido_item (
    id                  BIGINT        GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    pedido_id           BIGINT        NOT NULL REFERENCES pedido (id) ON DELETE CASCADE,
    producto_id         BIGINT        NOT NULL REFERENCES producto (id) ON DELETE RESTRICT,
    nombre_producto     TEXT          NOT NULL,
    cantidad            INT           NOT NULL,
    precio_unitario     NUMERIC(12,2) NOT NULL,
    costo_opciones      NUMERIC(12,2) NOT NULL DEFAULT 0,
    subtotal            NUMERIC(12,2) NOT NULL,
    aclaraciones        TEXT,
    CONSTRAINT pedido_item_cant_chk   CHECK (cantidad > 0),
    CONSTRAINT pedido_item_precio_chk CHECK (precio_unitario >= 0)
);

CREATE INDEX pedido_item_pedido_idx   ON pedido_item (pedido_id);
CREATE INDEX pedido_item_producto_idx ON pedido_item (producto_id);

-- ---------------------------------------------------------------------
-- pedido_item_opcion: personalizacion efectiva de cada item (RF-03).
-- Entidad nueva. Ver CAMBIOS.md (C-01).
-- ---------------------------------------------------------------------
CREATE TABLE pedido_item_opcion (
    id                  BIGINT        GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    pedido_item_id      BIGINT        NOT NULL REFERENCES pedido_item (id) ON DELETE CASCADE,
    producto_opcion_id  BIGINT        REFERENCES producto_opcion (id) ON DELETE SET NULL,
    ingrediente_id      BIGINT        NOT NULL REFERENCES ingrediente (id) ON DELETE RESTRICT,
    nombre_opcion       TEXT          NOT NULL,
    tipo                TEXT          NOT NULL,
    cantidad            INT           NOT NULL DEFAULT 1,
    costo_adicional     NUMERIC(12,2) NOT NULL DEFAULT 0,
    CONSTRAINT item_opcion_tipo_chk CHECK (tipo IN ('AGREGADO','QUITADO')),
    CONSTRAINT item_opcion_cant_chk CHECK (cantidad > 0)
);

CREATE INDEX item_opcion_item_idx ON pedido_item_opcion (pedido_item_id);

-- ---------------------------------------------------------------------
-- pedido_estado_historial: el alcance exige timestamp de CADA cambio de
-- estado y el usuario que lo hizo; el ER solo guardaba el estado actual.
-- Ver CAMBIOS.md (C-07).
-- ---------------------------------------------------------------------
CREATE TABLE pedido_estado_historial (
    id              BIGINT      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    pedido_id       BIGINT      NOT NULL REFERENCES pedido (id) ON DELETE CASCADE,
    estado_anterior TEXT,
    estado_nuevo    TEXT        NOT NULL,
    usuario_id      BIGINT      REFERENCES usuario (id) ON DELETE SET NULL,
    observacion     TEXT,
    creado_en       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX pedido_hist_idx ON pedido_estado_historial (pedido_id, creado_en);

-- ---------------------------------------------------------------------
-- promocion / pedido_promocion: RF-14. Entidades ausentes en el ER.
-- Ver CAMBIOS.md (C-10).
-- ---------------------------------------------------------------------
CREATE TABLE promocion (
    id                  BIGINT        GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nombre              TEXT          NOT NULL,
    codigo              CITEXT        UNIQUE,
    tipo                TEXT          NOT NULL,
    valor               NUMERIC(12,2) NOT NULL,
    monto_minimo        NUMERIC(12,2) NOT NULL DEFAULT 0,
    vigencia_desde      DATE,
    vigencia_hasta      DATE,
    activa              BOOLEAN       NOT NULL DEFAULT TRUE,
    creada_por          BIGINT        REFERENCES usuario (id) ON DELETE SET NULL,
    creada_en           TIMESTAMPTZ   NOT NULL DEFAULT now(),
    CONSTRAINT promo_tipo_chk     CHECK (tipo IN ('PORCENTAJE','MONTO_FIJO')),
    CONSTRAINT promo_valor_chk    CHECK (valor > 0),
    CONSTRAINT promo_vigencia_chk CHECK (vigencia_hasta IS NULL OR vigencia_desde IS NULL OR vigencia_hasta >= vigencia_desde)
);

CREATE TABLE pedido_promocion (
    pedido_id       BIGINT        NOT NULL REFERENCES pedido (id) ON DELETE CASCADE,
    promocion_id    BIGINT        NOT NULL REFERENCES promocion (id) ON DELETE RESTRICT,
    monto_descontado NUMERIC(12,2) NOT NULL,
    aplicada_por    BIGINT        REFERENCES usuario (id) ON DELETE SET NULL,
    aplicada_en     TIMESTAMPTZ   NOT NULL DEFAULT now(),
    PRIMARY KEY (pedido_id, promocion_id),
    CONSTRAINT pedido_promo_monto_chk CHECK (monto_descontado >= 0)
);

-- FK diferida de movimiento_stock hacia pedido (la tabla se creo antes)
ALTER TABLE movimiento_stock
    ADD CONSTRAINT movimiento_stock_pedido_fk
    FOREIGN KEY (pedido_id) REFERENCES pedido (id) ON DELETE SET NULL;
