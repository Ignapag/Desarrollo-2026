-- =====================================================================
-- 002 - Catalogo (menu) y control de stock por ingrediente
-- =====================================================================

CREATE TABLE categoria (
    id          BIGINT  GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nombre      TEXT    NOT NULL UNIQUE,
    orden       INT     NOT NULL DEFAULT 0,
    activa      BOOLEAN NOT NULL DEFAULT TRUE
);

-- ---------------------------------------------------------------------
-- ingrediente: unica fuente de verdad del stock.
-- Cambio respecto del ER: se elimina PRODUCTO.stock (habia stock
-- duplicado en dos entidades) y se agrega costo_unitario, sin el cual
-- no se puede calcular la rentabilidad de RF-09.
-- Ver CAMBIOS.md (C-02, C-03).
-- ---------------------------------------------------------------------
CREATE TABLE ingrediente (
    id                      BIGINT        GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nombre                  TEXT          NOT NULL UNIQUE,
    unidad_medida           TEXT          NOT NULL,
    cantidad_actual         NUMERIC(12,3) NOT NULL DEFAULT 0,
    umbral_minimo           NUMERIC(12,3) NOT NULL,
    costo_unitario          NUMERIC(12,2) NOT NULL DEFAULT 0,
    dias_reposicion         TEXT[]        NOT NULL DEFAULT '{}',
    fecha_ultima_reposicion TIMESTAMPTZ,
    responsable_id          BIGINT        REFERENCES usuario (id) ON DELETE SET NULL,
    activo                  BOOLEAN       NOT NULL DEFAULT TRUE,
    CONSTRAINT ingrediente_unidad_chk   CHECK (unidad_medida IN ('KG','GR','LT','ML','UNIDAD')),
    CONSTRAINT ingrediente_cantidad_chk CHECK (cantidad_actual >= 0),
    CONSTRAINT ingrediente_umbral_chk   CHECK (umbral_minimo > 0),
    CONSTRAINT ingrediente_costo_chk    CHECK (costo_unitario >= 0)
);

CREATE INDEX ingrediente_bajo_stock_idx ON ingrediente (nombre)
    WHERE activo AND cantidad_actual <= umbral_minimo;

-- ---------------------------------------------------------------------
-- producto: sin columna stock. Su disponibilidad se deriva del stock de
-- sus ingredientes base (ver vista producto_disponible mas abajo).
-- ---------------------------------------------------------------------
CREATE TABLE producto (
    id              BIGINT        GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    categoria_id    BIGINT        NOT NULL REFERENCES categoria (id) ON DELETE RESTRICT,
    nombre          TEXT          NOT NULL,
    descripcion     TEXT,
    precio_base     NUMERIC(12,2) NOT NULL,
    imagen_url      TEXT,
    activo          BOOLEAN       NOT NULL DEFAULT TRUE,
    orden           INT           NOT NULL DEFAULT 0,
    creado_en       TIMESTAMPTZ   NOT NULL DEFAULT now(),
    actualizado_en  TIMESTAMPTZ   NOT NULL DEFAULT now(),
    CONSTRAINT producto_precio_chk CHECK (precio_base > 0),
    CONSTRAINT producto_nombre_uk  UNIQUE (categoria_id, nombre)
);

CREATE INDEX producto_categoria_idx ON producto (categoria_id) WHERE activo;

-- ---------------------------------------------------------------------
-- producto_ingrediente: receta. cantidad_requerida es lo que faltaba
-- para poder descontar stock automaticamente y calcular costo/rentabilidad.
-- es_base = TRUE significa que sin ese ingrediente el producto no se
-- puede vender (regla de desactivacion automatica del alcance).
-- Ver CAMBIOS.md (C-03).
-- ---------------------------------------------------------------------
CREATE TABLE producto_ingrediente (
    producto_id         BIGINT        NOT NULL REFERENCES producto (id) ON DELETE CASCADE,
    ingrediente_id      BIGINT        NOT NULL REFERENCES ingrediente (id) ON DELETE RESTRICT,
    cantidad_requerida  NUMERIC(12,3) NOT NULL,
    es_base             BOOLEAN       NOT NULL DEFAULT TRUE,
    PRIMARY KEY (producto_id, ingrediente_id),
    CONSTRAINT prod_ing_cantidad_chk CHECK (cantidad_requerida > 0)
);

-- ---------------------------------------------------------------------
-- producto_opcion: ingredientes opcionales que el cliente puede agregar
-- o quitar, con su costo adicional. Entidad ausente en el ER original;
-- sin ella RF-03 (personalizacion) no tiene donde persistirse.
-- Ver CAMBIOS.md (C-01).
-- ---------------------------------------------------------------------
CREATE TABLE producto_opcion (
    id                  BIGINT        GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    producto_id         BIGINT        NOT NULL REFERENCES producto (id) ON DELETE CASCADE,
    ingrediente_id      BIGINT        NOT NULL REFERENCES ingrediente (id) ON DELETE RESTRICT,
    tipo                TEXT          NOT NULL DEFAULT 'AGREGADO',
    costo_adicional     NUMERIC(12,2) NOT NULL DEFAULT 0,
    cantidad_requerida  NUMERIC(12,3) NOT NULL DEFAULT 1,
    max_por_item        INT           NOT NULL DEFAULT 1,
    activo              BOOLEAN       NOT NULL DEFAULT TRUE,
    CONSTRAINT prod_opcion_tipo_chk  CHECK (tipo IN ('AGREGADO','QUITADO')),
    CONSTRAINT prod_opcion_costo_chk CHECK (costo_adicional >= 0),
    CONSTRAINT prod_opcion_max_chk   CHECK (max_por_item > 0),
    CONSTRAINT prod_opcion_uk        UNIQUE (producto_id, ingrediente_id, tipo)
);

-- ---------------------------------------------------------------------
-- movimiento_stock: trazabilidad de cada consumo, reposicion o ajuste.
-- El ER solo tenia la relacion REPONE sin historial. Ver CAMBIOS.md (C-06).
-- ---------------------------------------------------------------------
CREATE TABLE movimiento_stock (
    id              BIGINT        GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ingrediente_id  BIGINT        NOT NULL REFERENCES ingrediente (id) ON DELETE RESTRICT,
    tipo            TEXT          NOT NULL,
    cantidad        NUMERIC(12,3) NOT NULL,
    saldo_resultante NUMERIC(12,3) NOT NULL,
    pedido_id       BIGINT,
    usuario_id      BIGINT        REFERENCES usuario (id) ON DELETE SET NULL,
    motivo          TEXT,
    creado_en       TIMESTAMPTZ   NOT NULL DEFAULT now(),
    CONSTRAINT mov_stock_tipo_chk CHECK (tipo IN ('CONSUMO','REPOSICION','AJUSTE','DEVOLUCION','MERMA'))
);

CREATE INDEX mov_stock_ing_idx    ON movimiento_stock (ingrediente_id, creado_en DESC);
CREATE INDEX mov_stock_pedido_idx ON movimiento_stock (pedido_id);

-- ---------------------------------------------------------------------
-- alerta_stock: alertas de reposicion (RF-07).
-- ---------------------------------------------------------------------
CREATE TABLE alerta_stock (
    id              BIGINT        GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ingrediente_id  BIGINT        NOT NULL REFERENCES ingrediente (id) ON DELETE CASCADE,
    nivel           TEXT          NOT NULL,
    cantidad_al_generar NUMERIC(12,3) NOT NULL,
    estado          TEXT          NOT NULL DEFAULT 'ACTIVA',
    generada_en     TIMESTAMPTZ   NOT NULL DEFAULT now(),
    resuelta_en     TIMESTAMPTZ,
    resuelta_por    BIGINT        REFERENCES usuario (id) ON DELETE SET NULL,
    CONSTRAINT alerta_nivel_chk  CHECK (nivel IN ('BAJO','AGOTADO')),
    CONSTRAINT alerta_estado_chk CHECK (estado IN ('ACTIVA','RESUELTA'))
);

CREATE UNIQUE INDEX alerta_stock_activa_uk ON alerta_stock (ingrediente_id)
    WHERE estado = 'ACTIVA';

-- ---------------------------------------------------------------------
-- Vistas de apoyo
-- ---------------------------------------------------------------------

-- Costo de insumos por producto, base del reporte de rentabilidad (RF-09).
CREATE OR REPLACE VIEW producto_costo AS
SELECT p.id                                                   AS producto_id,
       p.nombre,
       p.precio_base,
       COALESCE(SUM(pi.cantidad_requerida * i.costo_unitario), 0) AS costo_insumos,
       p.precio_base - COALESCE(SUM(pi.cantidad_requerida * i.costo_unitario), 0) AS margen_estimado
FROM producto p
LEFT JOIN producto_ingrediente pi ON pi.producto_id = p.id
LEFT JOIN ingrediente i           ON i.id = pi.ingrediente_id
GROUP BY p.id, p.nombre, p.precio_base;

-- Disponibilidad real: activo por configuracion Y con stock en todos sus
-- ingredientes base. Reemplaza a la columna PRODUCTO.stock eliminada.
CREATE OR REPLACE VIEW producto_disponible AS
SELECT p.id AS producto_id,
       p.activo
         AND NOT EXISTS (
             SELECT 1
             FROM producto_ingrediente pi
             JOIN ingrediente i ON i.id = pi.ingrediente_id
             WHERE pi.producto_id = p.id
               AND pi.es_base
               AND i.cantidad_actual < pi.cantidad_requerida
         ) AS disponible
FROM producto p;
