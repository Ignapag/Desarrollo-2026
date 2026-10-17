-- Derivaciones a personal: visibles en la bandeja hasta que un empleado las resuelve.
-- Una conversación tiene a lo sumo una atención pendiente; mientras exista, el bot no
-- crea ni modifica el pedido. El mensaje que la originó y la resolución quedan
-- registrados con el empleado responsable.
CREATE TABLE whatsapp_atencion (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    referencia_hash TEXT NOT NULL REFERENCES whatsapp_borrador (referencia_hash),
    entrada_id TEXT NOT NULL REFERENCES whatsapp_entrada (id),
    motivo TEXT NOT NULL CHECK (motivo IN ('SOLICITUD','PROVEEDOR')),
    estado TEXT NOT NULL DEFAULT 'PENDIENTE' CHECK (estado IN ('PENDIENTE','RESUELTA')),
    resolucion TEXT CHECK (resolucion IS NULL OR length(btrim(resolucion)) BETWEEN 1 AND 500),
    resuelta_por BIGINT REFERENCES usuario (id),
    resuelta_en TIMESTAMPTZ,
    creado_en TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK ((estado = 'RESUELTA') = (
        resolucion IS NOT NULL AND resuelta_por IS NOT NULL AND resuelta_en IS NOT NULL
    ))
);
CREATE UNIQUE INDEX whatsapp_atencion_pendiente_uq ON whatsapp_atencion (referencia_hash)
    WHERE estado = 'PENDIENTE';

-- Respuestas escritas por personal: pasan por la misma outbox y su estado real de envío.
ALTER TABLE whatsapp_salida
    ADD COLUMN atencion_id BIGINT REFERENCES whatsapp_atencion (id),
    ADD COLUMN enviado_por BIGINT REFERENCES usuario (id),
    ADD CONSTRAINT whatsapp_salida_atencion_chk CHECK ((atencion_id IS NULL) = (enviado_por IS NULL));
CREATE INDEX whatsapp_salida_atencion_idx ON whatsapp_salida (atencion_id)
    WHERE atencion_id IS NOT NULL;
