-- Memoria semántica y datos parciales del chat; la PII no se exporta al intérprete.
ALTER TABLE whatsapp_borrador
    ADD COLUMN contexto_chat JSONB NOT NULL DEFAULT '{}'::jsonb
        CHECK (jsonb_typeof(contexto_chat) = 'object');
ALTER TABLE whatsapp_entrada
    ADD COLUMN memoria_ia JSONB CHECK (memoria_ia IS NULL OR jsonb_typeof(memoria_ia) = 'object'),
    ADD COLUMN orden_recibido BIGINT GENERATED ALWAYS AS IDENTITY;

-- Un incidente técnico sin intervención humana puede cerrarse al retomar el bot.
-- Las atenciones solicitadas por el cliente siguen exigiendo responsable humano.
ALTER TABLE whatsapp_atencion DROP CONSTRAINT whatsapp_atencion_check;
ALTER TABLE whatsapp_atencion ADD CONSTRAINT whatsapp_atencion_resolucion_chk CHECK (
    (estado = 'RESUELTA') = (
        resolucion IS NOT NULL AND resuelta_en IS NOT NULL
        AND (resuelta_por IS NOT NULL OR motivo = 'PROVEEDOR')
    )
);
