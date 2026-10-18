-- El saldo conciliado y el método actual del pedido son la autoridad.
-- La marca histórica del borrador no cambia cuando el empleado cobra por el panel.
CREATE OR REPLACE FUNCTION whatsapp_validar_saldo_transferencia() RETURNS TRIGGER
LANGUAGE plpgsql AS $func$
BEGIN
    IF NEW.estado = 'EN_PREPARACION' AND OLD.estado <> NEW.estado
       AND NEW.metodo_pago_acordado = 'TRANSFERENCIA'
       AND NEW.total > (
           SELECT COALESCE(sum(CASE WHEN tipo = 'COBRO' THEN monto ELSE -monto END), 0)
           FROM pago WHERE pedido_id = NEW.id AND estado = 'CONCILIADO'
       ) THEN
        RAISE EXCEPTION 'La transferencia requiere revision del saldo vigente'
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$func$;
