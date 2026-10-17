-- Los callbacks pueden adelantarse a la persistencia de la respuesta HTTP de Meta.
CREATE TABLE whatsapp_estado_envio (
    proveedor_id TEXT NOT NULL,
    telefono TEXT NOT NULL,
    estado TEXT NOT NULL CHECK (estado IN ('sent','delivered','read','failed')),
    recibido_en TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (proveedor_id, telefono, estado)
);
