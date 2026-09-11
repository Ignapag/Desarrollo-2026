-- =====================================================================
-- 005 - Pagos, cierre de caja y conciliacion
-- Modulo que resuelve el problema CRITICO relevado (cierre de caja manual)
-- =====================================================================

CREATE TABLE cierre_caja (
    id                  BIGINT        GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    fecha               DATE          NOT NULL,
    turno               TEXT          NOT NULL,
    abierto_en          TIMESTAMPTZ   NOT NULL DEFAULT now(),
    cerrado_en          TIMESTAMPTZ,
    total_efectivo      NUMERIC(12,2) NOT NULL DEFAULT 0,
    total_billeteras    NUMERIC(12,2) NOT NULL DEFAULT 0,
    total_devoluciones  NUMERIC(12,2) NOT NULL DEFAULT 0,
    total_general       NUMERIC(12,2) NOT NULL DEFAULT 0,
    cantidad_pedidos    INT           NOT NULL DEFAULT 0,
    estado              TEXT          NOT NULL DEFAULT 'ABIERTO',
    generado_por        BIGINT        REFERENCES usuario (id) ON DELETE SET NULL,
    aprobado_por        BIGINT        REFERENCES usuario (id) ON DELETE SET NULL,
    aprobado_en         TIMESTAMPTZ,
    observaciones       TEXT,
    CONSTRAINT cierre_turno_chk  CHECK (turno IN ('MEDIODIA','NOCHE')),
    CONSTRAINT cierre_estado_chk CHECK (estado IN ('ABIERTO','PENDIENTE_APROBACION','APROBADO')),
    CONSTRAINT cierre_uk         UNIQUE (fecha, turno)
);

CREATE INDEX cierre_fecha_idx ON cierre_caja (fecha DESC);

-- ---------------------------------------------------------------------
-- pago: se agrega tipo (COBRO / DEVOLUCION) para registrar el egreso con
-- referencia al pedido original, como pide el alcance, sin crear una
-- tabla aparte. Ver CAMBIOS.md (C-11).
-- ---------------------------------------------------------------------
CREATE TABLE pago (
    id                  BIGINT        GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    pedido_id           BIGINT        NOT NULL REFERENCES pedido (id) ON DELETE RESTRICT,
    cierre_caja_id      BIGINT        REFERENCES cierre_caja (id) ON DELETE SET NULL,
    tipo                TEXT          NOT NULL DEFAULT 'COBRO',
    metodo_pago         TEXT          NOT NULL,
    monto               NUMERIC(12,2) NOT NULL,
    propina             NUMERIC(12,2) NOT NULL DEFAULT 0,
    estado              TEXT          NOT NULL DEFAULT 'PENDIENTE',
    referencia_externa  TEXT,
    registrado_por      BIGINT        REFERENCES usuario (id) ON DELETE SET NULL,
    registrado_en       TIMESTAMPTZ   NOT NULL DEFAULT now(),
    conciliado_en       TIMESTAMPTZ,
    motivo              TEXT,
    CONSTRAINT pago_tipo_chk    CHECK (tipo IN ('COBRO','DEVOLUCION')),
    CONSTRAINT pago_metodo_chk  CHECK (metodo_pago IN
        ('EFECTIVO','MERCADO_PAGO','CUENTA_DNI','NARANJA_X','OTRA_BILLETERA','TRANSFERENCIA')),
    CONSTRAINT pago_estado_chk  CHECK (estado IN ('PENDIENTE','CONCILIADO','ANULADO')),
    CONSTRAINT pago_monto_chk   CHECK (monto > 0),
    CONSTRAINT pago_propina_chk CHECK (propina >= 0)
);

CREATE INDEX pago_pedido_idx ON pago (pedido_id);
CREATE INDEX pago_cierre_idx ON pago (cierre_caja_id);
CREATE INDEX pago_fecha_idx  ON pago (registrado_en DESC);

-- Un pago ya conciliado no puede modificarse (validacion del alcance)
CREATE OR REPLACE FUNCTION protege_pago_conciliado()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $func$
BEGIN
    IF OLD.estado = 'CONCILIADO' AND NEW.estado = 'CONCILIADO'
       AND (NEW.monto <> OLD.monto
            OR NEW.metodo_pago <> OLD.metodo_pago
            OR NEW.propina <> OLD.propina
            OR NEW.pedido_id <> OLD.pedido_id) THEN
        RAISE EXCEPTION 'No se puede modificar un pago ya conciliado (pago %)', OLD.id
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$func$;

CREATE TRIGGER pago_conciliado_trg
    BEFORE UPDATE ON pago
    FOR EACH ROW
    EXECUTE FUNCTION protege_pago_conciliado();

-- Un cierre aprobado es inalterable (regla del alcance)
CREATE OR REPLACE FUNCTION protege_cierre_aprobado()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $func$
BEGIN
    IF OLD.estado = 'APROBADO' THEN
        RAISE EXCEPTION 'El cierre de caja % ya fue aprobado y es inalterable', OLD.id
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$func$;

CREATE TRIGGER cierre_aprobado_trg
    BEFORE UPDATE ON cierre_caja
    FOR EACH ROW
    WHEN (OLD.estado = 'APROBADO')
    EXECUTE FUNCTION protege_cierre_aprobado();
