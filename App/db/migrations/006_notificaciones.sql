-- =====================================================================
-- 006 - Notificaciones de WhatsApp (integracion n8n)
-- Entidades ausentes en el ER: el modulo del bot exige plantillas
-- configurables y timestamp de cada notificacion enviada (RNF-10: 30 s).
-- Ver CAMBIOS.md (C-12).
-- =====================================================================

CREATE TABLE notificacion_plantilla (
    id              BIGINT      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    clave           TEXT        NOT NULL UNIQUE,
    nombre          TEXT        NOT NULL,
    cuerpo          TEXT        NOT NULL,
    activa          BOOLEAN     NOT NULL DEFAULT TRUE,
    actualizado_por BIGINT      REFERENCES usuario (id) ON DELETE SET NULL,
    actualizado_en  TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT plantilla_clave_chk CHECK (clave IN
        ('BIENVENIDA','PEDIDO_CONFIRMADO','EN_CAMINO','ENTREGADO','ALERTA_STOCK','CIERRE_CAJA'))
);

CREATE TABLE notificacion (
    id                  BIGINT      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    plantilla_id        BIGINT      REFERENCES notificacion_plantilla (id) ON DELETE SET NULL,
    clave               TEXT        NOT NULL,
    destinatario        TEXT        NOT NULL,
    cliente_id          BIGINT      REFERENCES cliente (usuario_id) ON DELETE SET NULL,
    pedido_id           BIGINT      REFERENCES pedido (id) ON DELETE SET NULL,
    cuerpo_renderizado  TEXT        NOT NULL,
    canal               TEXT        NOT NULL DEFAULT 'WHATSAPP',
    estado              TEXT        NOT NULL DEFAULT 'PENDIENTE',
    intentos            INT         NOT NULL DEFAULT 0,
    error               TEXT,
    creada_en           TIMESTAMPTZ NOT NULL DEFAULT now(),
    enviada_en          TIMESTAMPTZ,
    CONSTRAINT notif_estado_chk CHECK (estado IN ('PENDIENTE','ENVIADA','FALLIDA','DESCARTADA')),
    CONSTRAINT notif_canal_chk  CHECK (canal IN ('WHATSAPP','EMAIL','PANEL'))
);

CREATE INDEX notif_pendientes_idx ON notificacion (creada_en)
    WHERE estado = 'PENDIENTE';
CREATE INDEX notif_pedido_idx ON notificacion (pedido_id, creada_en DESC);

-- Latencia real de envio, para verificar el cumplimiento del RNF-10.
CREATE OR REPLACE VIEW notificacion_latencia AS
SELECT n.id,
       n.clave,
       n.pedido_id,
       n.creada_en,
       n.enviada_en,
       EXTRACT(EPOCH FROM (n.enviada_en - n.creada_en)) AS segundos_demora,
       (n.enviada_en - n.creada_en) <= INTERVAL '30 seconds' AS cumple_rnf10
FROM notificacion n
WHERE n.estado = 'ENVIADA';
