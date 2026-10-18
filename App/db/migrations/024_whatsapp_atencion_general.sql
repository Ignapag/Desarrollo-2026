-- Consultas y adjuntos del remitente sin asignar una compra implícitamente.
ALTER TABLE whatsapp_atencion
    ALTER COLUMN referencia_hash DROP NOT NULL,
    ADD COLUMN telefono TEXT,
    DROP CONSTRAINT whatsapp_atencion_motivo_check,
    ADD CONSTRAINT whatsapp_atencion_motivo_check
        CHECK (motivo IN ('SOLICITUD','PROVEEDOR','COMPROBANTE')),
    ADD CONSTRAINT whatsapp_atencion_origen_chk CHECK (
        (referencia_hash IS NOT NULL AND telefono IS NULL)
        OR (referencia_hash IS NULL AND telefono IS NOT NULL AND telefono ~ '^[0-9]{11,15}$')
    ),
    ADD CONSTRAINT whatsapp_atencion_comprobante_general_chk
        CHECK (motivo <> 'COMPROBANTE' OR referencia_hash IS NULL);

CREATE UNIQUE INDEX whatsapp_atencion_general_solicitud_pendiente_uq
ON whatsapp_atencion (telefono)
WHERE estado = 'PENDIENTE' AND referencia_hash IS NULL AND motivo = 'SOLICITUD';

CREATE UNIQUE INDEX whatsapp_atencion_general_comprobante_entrada_uq
ON whatsapp_atencion (entrada_id)
WHERE referencia_hash IS NULL AND motivo = 'COMPROBANTE';
