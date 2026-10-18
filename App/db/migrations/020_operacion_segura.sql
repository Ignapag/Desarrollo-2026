-- Autoridad de pedidos: versionado y auditoria aditivos, sin reescribir historia.
ALTER TABLE pedido
    ADD COLUMN version INT NOT NULL DEFAULT 1 CHECK (version > 0),
    ADD COLUMN metodo_pago_acordado TEXT NOT NULL DEFAULT 'EFECTIVO'
        CHECK (metodo_pago_acordado IN ('EFECTIVO','TRANSFERENCIA')),
    ADD COLUMN preparacion_en TIMESTAMPTZ,
    ADD COLUMN listo_en TIMESTAMPTZ;

UPDATE pedido p SET metodo_pago_acordado=b.metodo_pago
FROM whatsapp_borrador b WHERE b.pedido_id=p.id AND b.metodo_pago IS NOT NULL;
UPDATE pedido p SET
    confirmado_en=COALESCE(p.confirmado_en, (
        SELECT min(h.creado_en) FROM pedido_estado_historial h
        WHERE h.pedido_id=p.id AND h.estado_nuevo IN
            ('CONFIRMADO','EN_PREPARACION','LISTO','EN_CAMINO','ENTREGADO'))),
    preparacion_en=(SELECT min(h.creado_en) FROM pedido_estado_historial h
        WHERE h.pedido_id=p.id AND h.estado_nuevo='EN_PREPARACION'),
    listo_en=(SELECT min(h.creado_en) FROM pedido_estado_historial h
        WHERE h.pedido_id=p.id AND h.estado_nuevo='LISTO');

ALTER TABLE pedido_estado_historial
    ADD COLUMN origen TEXT NOT NULL DEFAULT 'HISTORICO',
    ADD COLUMN version INT,
    ADD COLUMN cambios JSONB,
    ADD COLUMN tratamiento_stock TEXT;

ALTER TABLE pago
    ADD COLUMN clave_operacion UUID UNIQUE,
    ADD COLUMN datos_operacion JSONB CHECK
        (datos_operacion IS NULL OR jsonb_typeof(datos_operacion)='object');

-- Cada cambio real genera un evento. Un estado que vuelve a ocurrir tiene otra
-- version; reintentar un comando rechazado no genera notificaciones adicionales.
CREATE OR REPLACE FUNCTION whatsapp_evento_estado() RETURNS TRIGGER
LANGUAGE plpgsql AS $func$
DECLARE contacto TEXT;
BEGIN
    IF NEW.estado=OLD.estado THEN RETURN NEW; END IF;
    SELECT telefono INTO contacto FROM whatsapp_borrador WHERE pedido_id=NEW.id;
    IF contacto IS NULL THEN RETURN NEW; END IF;
    INSERT INTO whatsapp_salida(clave,telefono,texto)
    VALUES ('estado:' || NEW.id || ':v' || NEW.version, contacto,
        'Pedido #' || NEW.numero || ': ' || replace(NEW.estado,'_',' ') || '.')
    ON CONFLICT(clave) DO NOTHING;
    RETURN NEW;
END;
$func$;
