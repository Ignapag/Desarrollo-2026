-- Los avisos nuevos omiten identificadores; las salidas históricas se conservan.
CREATE OR REPLACE FUNCTION whatsapp_evento_estado() RETURNS TRIGGER
LANGUAGE plpgsql AS $func$
DECLARE
    contacto TEXT;
    mensaje TEXT;
BEGIN
    IF NEW.estado = OLD.estado THEN RETURN NEW; END IF;
    SELECT telefono INTO contacto FROM whatsapp_borrador WHERE pedido_id = NEW.id;
    IF contacto IS NULL THEN RETURN NEW; END IF;
    mensaje := CASE NEW.estado
        WHEN 'PENDIENTE' THEN '🍔 *Tu pedido* fue recibido. ¡Gracias por elegir Monu Burger!'
        WHEN 'CONFIRMADO' THEN '✅ *Tu pedido* está confirmado. Te avisamos cuando empecemos a prepararlo.'
        WHEN 'EN_PREPARACION' THEN '👨‍🍳 ¡Ya estamos preparando tu pedido! Te avisamos cuando esté listo. 🍔'
        WHEN 'LISTO' THEN CASE WHEN NEW.tipo_entrega = 'RETIRO'
            THEN '🛍️ ¡Tu pedido está listo para retirar! Te esperamos en el local. 🍔'
            ELSE '🍔 ¡Tu pedido está listo! Te avisamos cuando salga para tu dirección.' END
        WHEN 'EN_CAMINO' THEN CASE WHEN NEW.tipo_entrega = 'RETIRO'
            THEN '🛍️ Tu pedido está listo para retirar. ¡Te esperamos!'
            ELSE '🛵 ¡Tu pedido está en camino! Si necesitás indicarnos algo para la entrega, escribinos por acá. 📍' END
        WHEN 'ENTREGADO' THEN '💚 ¡Gracias por elegirnos! Tu pedido figura como entregado. ¡Que lo disfrutes! 🍔'
        WHEN 'CANCELADO' THEN 'Tu pedido fue cancelado. Si ya habías pagado, escribinos para que el equipo revise el reintegro. 💬'
        ELSE '🍔 Tenemos una novedad sobre tu pedido. Escribinos y te ayudamos. 💬'
    END;
    INSERT INTO whatsapp_salida (clave, telefono, texto)
    VALUES ('estado:' || NEW.id || ':v' || NEW.version, contacto, mensaje)
    ON CONFLICT (clave) DO NOTHING;
    RETURN NEW;
END;
$func$;

-- La consulta de avisos del panel sólo necesita los comprobantes pendientes.
CREATE INDEX whatsapp_comprobante_pendiente_idx ON whatsapp_comprobante (id)
WHERE estado = 'PENDIENTE';
