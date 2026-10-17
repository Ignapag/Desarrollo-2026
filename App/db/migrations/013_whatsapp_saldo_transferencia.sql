-- Una aprobación histórica no acredita el saldo después de una devolución.
CREATE FUNCTION whatsapp_validar_saldo_transferencia() RETURNS TRIGGER
LANGUAGE plpgsql AS $func$
BEGIN
    IF NEW.estado = 'EN_PREPARACION' AND OLD.estado <> NEW.estado AND EXISTS (
        SELECT 1 FROM whatsapp_borrador b
        WHERE b.pedido_id = NEW.id AND b.metodo_pago = 'TRANSFERENCIA'
        AND (b.estado_pago <> 'APROBADO' OR NEW.total > (
            SELECT COALESCE(sum(CASE WHEN tipo = 'COBRO' THEN monto ELSE -monto END), 0)
            FROM pago WHERE pedido_id = NEW.id AND estado = 'CONCILIADO'
        ))
    ) THEN
        RAISE EXCEPTION 'La transferencia requiere revision del saldo vigente'
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$func$;
CREATE TRIGGER whatsapp_saldo_transferencia_trg BEFORE UPDATE OF estado ON pedido
    FOR EACH ROW EXECUTE FUNCTION whatsapp_validar_saldo_transferencia();
