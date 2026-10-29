-- Auditoria transaccional de cambios operativos. Las escrituras de SQL directo
-- tambien dejan rastro; el backend aporta contexto validado mediante SET LOCAL.
ALTER TABLE auditoria
    ADD COLUMN origen TEXT,
    ADD COLUMN identificador_operacion TEXT;

CREATE INDEX auditoria_operacion_idx ON auditoria (identificador_operacion)
    WHERE identificador_operacion IS NOT NULL;

-- Solo se proyectan campos de negocio conocidos de los JSON estructurados.
-- No se exportan JSON libres, cuerpos de proveedor, tokens ni credenciales.
CREATE FUNCTION monu_auditoria_json_negocio(p_valor JSONB, p_campo TEXT DEFAULT 'objeto')
RETURNS JSONB LANGUAGE plpgsql IMMUTABLE
AS $func$
DECLARE
    v_resultado JSONB;
    v_clave TEXT;
    v_valor JSONB;
    v_proyectado JSONB;
    v_numericos TEXT[] := ARRAY[
        'id','item_id','pedido_id','producto_id','ingrediente_id','producto_opcion_id',
        'cliente_id','usuario_id','direccion_id','envio_id','zona_id','version','pedido_version',
        'cantidad','cantidad_requerida','precio','precio_unitario','costo_adicional',
        'costo_opciones','subtotal','total','total_anterior','costo_envio','pagado',
        'descuento_total','max_por_item','fondos'];
    v_textos TEXT[] := ARRAY[
        'nombre','apellido','telefono','calle','numero','localidad','referencia','piso_depto',
        'codigo_postal','variante','tipo','estado','estado_envio','tipo_entrega','metodo_pago',
        'metodo_pago_acordado','observaciones','aclaraciones','motivo','revision_motivo',
        'entrada_id','producto','ingrediente','campo','origen','tratamiento_stock'];
    v_booleanos TEXT[] := ARRAY['es_base','activo','activa','asignado','operativa'];
    v_listas TEXT[] := ARRAY[
        'variantes','items','composicion','ingredientes','opciones','receta_snapshot','acciones'];
    v_objetos TEXT[] := ARRAY[
        'objeto','contacto','direccion','direccion_nueva','propuesta','argumentos','operacion',
        'cambios','anterior','posterior','nuevo','antes','despues','accion'];
BEGIN
    IF p_valor IS NULL THEN RETURN NULL; END IF;
    -- Una clave desconocida se omite incluso si contiene NULL u otro objeto.
    IF NOT (p_campo = ANY(v_numericos || v_textos || v_booleanos || v_listas || v_objetos)
            OR p_campo = 'preparacion_en') THEN RETURN NULL; END IF;
    IF jsonb_typeof(p_valor) = 'null' THEN RETURN p_valor; END IF;

    -- Deltas del historial: validar ambos valores con el tipo del campo original.
    IF jsonb_typeof(p_valor) = 'object'
       AND p_campo <> ALL(v_objetos)
       AND (p_valor ? 'anterior' OR p_valor ? 'nuevo') THEN
        v_resultado := '{}'::jsonb;
        FOR v_clave,v_valor IN SELECT key,value FROM jsonb_each(p_valor) LOOP
            IF v_clave NOT IN ('anterior','nuevo') THEN CONTINUE; END IF;
            v_proyectado := monu_auditoria_json_negocio(v_valor,p_campo);
            IF v_proyectado IS NOT NULL THEN
                v_resultado := v_resultado || jsonb_build_object(v_clave,v_proyectado);
            END IF;
        END LOOP;
        RETURN NULLIF(v_resultado,'{}'::jsonb);
    END IF;

    IF jsonb_typeof(p_valor) = 'array' THEN
        IF p_campo <> ALL(v_listas) AND p_campo <> 'objeto' THEN RETURN NULL; END IF;
        SELECT COALESCE(jsonb_agg(proyectado ORDER BY n)
                            FILTER (WHERE proyectado IS NOT NULL),'[]'::jsonb)
        INTO v_resultado
        FROM (SELECT e.n, monu_auditoria_json_negocio(e.valor) AS proyectado
              FROM jsonb_array_elements(p_valor) WITH ORDINALITY e(valor,n)) e;
        RETURN v_resultado;
    END IF;

    IF p_campo = ANY(v_numericos) AND (
        jsonb_typeof(p_valor) = 'number'
        OR (jsonb_typeof(p_valor) = 'string' AND (p_valor #>> '{}') ~ '^-?[0-9]+(\.[0-9]+)?$')
    ) THEN RETURN p_valor; END IF;
    -- Los IDs web: incluyen un derivado de la cookie de sesion demostrativa.
    -- Correlacionar el mensaje sin exportar ese componente a auditoria.
    IF p_campo = 'entrada_id' AND jsonb_typeof(p_valor) = 'string'
       AND (p_valor #>> '{}') LIKE 'web:%' THEN
        RETURN to_jsonb('sha256:' || encode(
            sha256(convert_to(p_valor #>> '{}','UTF8')),'hex'));
    END IF;
    IF (p_campo = ANY(v_textos) OR p_campo = 'accion')
       AND jsonb_typeof(p_valor) = 'string' THEN RETURN p_valor; END IF;
    IF p_campo = ANY(v_booleanos) AND (
        jsonb_typeof(p_valor) = 'boolean'
        OR (jsonb_typeof(p_valor) = 'string' AND (p_valor #>> '{}') IN ('True','False','true','false'))
    ) THEN RETURN p_valor; END IF;
    IF p_campo = 'preparacion_en' AND jsonb_typeof(p_valor) = 'string'
       AND (p_valor #>> '{}') ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}[ T]' THEN
        RETURN p_valor;
    END IF;
    IF jsonb_typeof(p_valor) <> 'object' THEN
        RETURN NULL;
    END IF;
    IF p_campo <> ALL(v_objetos) THEN RETURN NULL; END IF;
    v_resultado := '{}'::jsonb;
    FOR v_clave, v_valor IN SELECT key,value FROM jsonb_each(p_valor) LOOP
        v_proyectado := monu_auditoria_json_negocio(v_valor,v_clave);
        IF v_proyectado IS NOT NULL THEN
            v_resultado := v_resultado || jsonb_build_object(v_clave,v_proyectado);
        END IF;
    END LOOP;
    RETURN v_resultado;
END;
$func$;

-- El esquema guarda GeoJSON Polygon. Las coordenadas se conservan solo si
-- son anillos de puntos numericos; cualquier propiedad libre queda fuera.
CREATE FUNCTION monu_auditoria_poligono(p_valor JSONB)
RETURNS JSONB LANGUAGE plpgsql IMMUTABLE
AS $func$
DECLARE
    v_anillo JSONB;
    v_punto JSONB;
    v_coordenada JSONB;
BEGIN
    IF jsonb_typeof(p_valor) IS DISTINCT FROM 'object'
       OR (p_valor ->> 'type') IS DISTINCT FROM 'Polygon'
       OR jsonb_typeof(p_valor -> 'coordinates') IS DISTINCT FROM 'array' THEN
        RETURN NULL;
    END IF;
    FOR v_anillo IN SELECT value FROM jsonb_array_elements(p_valor -> 'coordinates') LOOP
        IF jsonb_typeof(v_anillo) <> 'array' THEN RETURN NULL; END IF;
        FOR v_punto IN SELECT value FROM jsonb_array_elements(v_anillo) LOOP
            IF jsonb_typeof(v_punto) <> 'array' THEN RETURN NULL; END IF;
            IF jsonb_array_length(v_punto) < 2 THEN RETURN NULL; END IF;
            FOR v_coordenada IN SELECT value FROM jsonb_array_elements(v_punto) LOOP
                IF jsonb_typeof(v_coordenada) <> 'number' THEN RETURN NULL; END IF;
            END LOOP;
        END LOOP;
    END LOOP;
    RETURN jsonb_build_object('type','Polygon','coordinates',p_valor -> 'coordinates');
END;
$func$;

CREATE FUNCTION monu_auditoria_imagen(p_fila JSONB, p_campos TEXT[])
RETURNS JSONB LANGUAGE plpgsql IMMUTABLE
AS $func$
DECLARE
    v_resultado JSONB := '{}'::jsonb;
    v_campo TEXT;
    v_valor JSONB;
BEGIN
    IF p_fila IS NULL THEN RETURN NULL; END IF;
    FOREACH v_campo IN ARRAY p_campos LOOP
        IF NOT (p_fila ? v_campo) THEN CONTINUE; END IF;
        v_valor := p_fila -> v_campo;
        IF v_campo = 'valor' AND p_fila ? 'clave' THEN
            -- parametro puede alojar configuracion arbitraria. Solo copiar los
            -- parametros de negocio conocidos y con su formato esperado.
            IF NOT (
                ((p_fila ->> 'clave') IN (
                    'pedido.minutos_cancelacion','delivery.pedidos_por_viaje',
                    'delivery.radio_agrupacion_km','delivery.radio_busqueda_repartidor_km',
                    'notificacion.demora_max_segundos')
                 AND (p_fila ->> 'valor') ~ '^[0-9]+(\.[0-9]+)?$')
                OR ((p_fila ->> 'clave') IN ('caja.hora_cierre_noche','caja.hora_cierre_mediodia')
                    AND (p_fila ->> 'valor') ~ '^[0-9]{2}:[0-9]{2}$')
                OR ((p_fila ->> 'clave') = 'delivery.espera_segundo_pedido'
                    AND (p_fila ->> 'valor') IN ('true','false'))
                OR ((p_fila ->> 'clave') = 'negocio.telefono_whatsapp'
                    AND (p_fila ->> 'valor') ~ '^[0-9]{11,15}$')
                OR ((p_fila ->> 'clave') = 'negocio.nombre'
                    AND length(p_fila ->> 'valor') <= 200
                    AND (p_fila ->> 'valor') !~ '^[[:space:]]*[\{\[]')
            ) THEN CONTINUE; END IF;
        END IF;
        IF v_campo IN ('variantes','receta_snapshot','items','contacto','direccion','entrada_id',
                       'propuesta','accion','anterior','posterior','cambios') THEN
            v_valor := monu_auditoria_json_negocio(v_valor,v_campo);
        ELSIF v_campo = 'poligono' THEN
            v_valor := monu_auditoria_poligono(v_valor);
        ELSIF v_campo = 'imagen_url' AND (
            lower(p_fila ->> v_campo) LIKE 'data:%'
            OR (p_fila ->> v_campo) ~ '[?#]'
            OR (p_fila ->> v_campo) ~ '://[^/]*@'
        ) THEN
            v_valor := to_jsonb('[IMAGEN_RESERVADA]'::text);
        END IF;
        v_resultado := v_resultado || jsonb_build_object(v_campo,v_valor);
    END LOOP;
    RETURN v_resultado;
END;
$func$;

CREATE FUNCTION monu_registrar_cambio()
RETURNS TRIGGER LANGUAGE plpgsql
AS $func$
DECLARE
    v_antes JSONB;
    v_despues JSONB;
    v_fila JSONB;
    v_clave JSONB := '{}'::jsonb;
    v_campos TEXT[] := string_to_array(TG_ARGV[1], ',');
    v_claves TEXT[] := string_to_array(TG_ARGV[0], ',');
    v_modificados TEXT[];
    v_nombre TEXT;
    v_valor JSONB;
    v_usuario BIGINT;
    v_ip INET;
    v_origen TEXT;
    v_identificador TEXT;
    v_entidad_id TEXT;
BEGIN
    IF TG_OP <> 'INSERT' THEN v_antes := to_jsonb(OLD); END IF;
    IF TG_OP <> 'DELETE' THEN v_despues := to_jsonb(NEW); END IF;

    SELECT array_agg(campo ORDER BY campo) INTO v_modificados
    FROM (
        SELECT jsonb_object_keys(COALESCE(v_antes,'{}'::jsonb)
                                || COALESCE(v_despues,'{}'::jsonb)) AS campo
    ) c
    WHERE (v_antes -> campo) IS DISTINCT FROM (v_despues -> campo)
      AND (TG_OP <> 'UPDATE' OR campo <> 'actualizado_en');
    IF v_modificados IS NULL THEN RETURN NULL; END IF;

    v_fila := COALESCE(v_despues,v_antes);
    FOREACH v_nombre IN ARRAY v_claves LOOP
        v_valor := v_fila -> v_nombre;
        -- referencia_hash deriva de una referencia de acceso. Correlacionar sin
        -- duplicarla en el log consultable por personal.
        IF v_nombre = 'referencia_hash' AND v_valor IS NOT NULL THEN
            v_valor := to_jsonb('sha256:' || encode(
                sha256(convert_to(v_fila ->> v_nombre,'UTF8')),'hex'));
        END IF;
        v_clave := v_clave || jsonb_build_object(v_nombre,v_valor);
    END LOOP;
    IF cardinality(v_claves) = 1 THEN
        v_entidad_id := v_clave ->> v_claves[1];
    ELSE
        v_entidad_id := v_clave::text;
    END IF;

    v_usuario := NULLIF(current_setting('monu.usuario_id',true),'')::BIGINT;
    v_ip := NULLIF(current_setting('monu.ip',true),'')::INET;
    v_origen := COALESCE(NULLIF(current_setting('monu.origen',true),''),
                         'SQL:' || session_user);
    v_identificador := COALESCE(
        NULLIF(current_setting('monu.identificador_operacion',true),''),
        'sql:' || txid_current()::text);
    INSERT INTO auditoria
        (usuario_id,accion,entidad,entidad_id,datos,ip,origen,identificador_operacion,creado_en)
    VALUES (
        v_usuario,
        CASE TG_OP WHEN 'INSERT' THEN 'DATOS_INSERTADOS'
                   WHEN 'UPDATE' THEN 'DATOS_MODIFICADOS'
                   ELSE 'DATOS_ELIMINADOS' END,
        TG_TABLE_NAME, v_entidad_id,
        jsonb_build_object(
            'operacion',TG_OP,'clave',v_clave,
            'antes',monu_auditoria_imagen(v_antes,v_campos),
            'despues',monu_auditoria_imagen(v_despues,v_campos),
            'campos_modificados',to_jsonb(v_modificados),
            'sesion_bd',session_user),
        v_ip,v_origen,v_identificador,clock_timestamp()
    );
    RETURN NULL;
END;
$func$;

-- No hay bandera de request ni GUC que habilite el borrado. El mantenimiento
-- requiere privilegios administrativos de PostgreSQL para desactivar protecciones.
CREATE FUNCTION monu_impedir_destruccion()
RETURNS TRIGGER LANGUAGE plpgsql
AS $func$
BEGIN
    RAISE EXCEPTION 'Conservacion de datos: % no esta permitido en %. Use baja logica o mantenimiento administrativo.',
        TG_OP,TG_TABLE_NAME USING ERRCODE = '55000';
END;
$func$;

-- Lista cerrada de tablas y campos. Los campos no enumerados nunca se copian
-- a antes/despues. Su cambio se identifica solo por nombre en campos_modificados.
DO $config$
DECLARE
    v_esquema TEXT := current_schema();
    v_funcion TEXT;
    v_argumentos TEXT;
    v_tabla TEXT;
    v_clave TEXT;
    v_campos TEXT;
BEGIN
    -- Fijar el esquema de cada helper al de esta migracion. No depender del
    -- search_path del llamador ni desviar escrituras hacia public cuando se
    -- instala/valida el sistema en un esquema aislado.
    FOR v_funcion,v_argumentos IN
        SELECT * FROM (VALUES
            ('monu_auditoria_json_negocio','jsonb,text'),
            ('monu_auditoria_poligono','jsonb'),
            ('monu_auditoria_imagen','jsonb,text[]'),
            ('monu_registrar_cambio',''),
            ('monu_impedir_destruccion','')
        ) AS funciones(nombre,argumentos)
    LOOP
        EXECUTE format('ALTER FUNCTION %I.%I(%s) SET search_path TO pg_catalog,%I',
                       v_esquema,v_funcion,v_argumentos,v_esquema);
    END LOOP;
    FOR v_tabla,v_clave,v_campos IN
        SELECT * FROM (VALUES
            ('usuario','id','id,nombre,apellido,username,email,telefono,rol,estado,fecha_alta,actualizado_en,ultimo_acceso'),
            ('cliente','id','id,usuario_id,nombre,estado,telefono_whatsapp,acepta_notif_wsp,whatsapp_verificado,telefono_contacto,notas'),
            ('repartidor','usuario_id','usuario_id,estado,vehiculo,ultima_lat,ultima_lng,ultima_pos_en'),
            ('zona_cobertura','id','id,nombre,descripcion,poligono,centro_lat,centro_lng,costo_envio,activa'),
            ('punto_encuentro','id','id,nombre,referencia,lat,lng,zona_id,activo'),
            ('direccion','id','id,cliente_id,calle,numero,piso_depto,codigo_postal,localidad,referencia,lat,lng,zona_id,es_principal,activa,creada_en'),
            ('parametro','clave','clave,valor,descripcion,actualizado_en,actualizado_por'),
            ('categoria','id','id,nombre,orden,activa'),
            ('ingrediente','id','id,nombre,unidad_medida,cantidad_actual,umbral_minimo,costo_unitario,dias_reposicion,fecha_ultima_reposicion,responsable_id,activo'),
            ('producto','id','id,categoria_id,nombre,descripcion,precio_base,imagen_url,activo,orden,variantes,creado_en,actualizado_en'),
            ('producto_ingrediente','producto_id,ingrediente_id','producto_id,ingrediente_id,cantidad_requerida,es_base,eliminado_en'),
            ('producto_variante_ingrediente','producto_id,variante,ingrediente_id','producto_id,variante,ingrediente_id,cantidad_requerida,es_base,eliminado_en'),
            ('producto_opcion','id','id,producto_id,ingrediente_id,tipo,costo_adicional,cantidad_requerida,max_por_item,activo'),
            ('movimiento_stock','id','id,ingrediente_id,tipo,cantidad,saldo_resultante,pedido_id,usuario_id,motivo,creado_en'),
            ('alerta_stock','id','id,ingrediente_id,nivel,cantidad_al_generar,estado,generada_en,resuelta_en,resuelta_por'),
            ('pedido','id','id,numero,cliente_id,tipo_entrega,direccion_id,punto_encuentro_id,canal,estado,subtotal,costo_envio,descuento_total,total,hora_entrega_pedida,creado_en,confirmado_en,cancelable_hasta,entregado_en,cancelado_en,version,metodo_pago_acordado,preparacion_en,listo_en,observaciones,motivo_cancelacion'),
            ('pedido_item','id','id,pedido_id,producto_id,nombre_producto,cantidad,precio_unitario,costo_opciones,subtotal,variante,receta_snapshot,eliminado_en,aclaraciones'),
            ('pedido_item_opcion','id','id,pedido_item_id,producto_opcion_id,ingrediente_id,nombre_opcion,tipo,cantidad,costo_adicional'),
            ('pedido_estado_historial','id','id,pedido_id,estado_anterior,estado_nuevo,usuario_id,creado_en,origen,version,tratamiento_stock,observacion,cambios'),
            ('promocion','id','id,nombre,codigo,tipo,valor,monto_minimo,vigencia_desde,vigencia_hasta,activa,creada_por,creada_en'),
            ('pedido_promocion','pedido_id,promocion_id','pedido_id,promocion_id,monto_descontado,aplicada_por,aplicada_en'),
            ('viaje','id','id,repartidor_id,estado,creado_en,salida_en,retorno_en,asignado_por,asignacion_auto'),
            ('envio','id','id,pedido_id,viaje_id,zona_id,punto_encuentro_id,orden_en_viaje,estado,distancia_km,asignado_en,en_camino_en,entregado_en,observaciones'),
            ('cierre_caja','id','id,fecha,turno,abierto_en,cerrado_en,total_efectivo,total_billeteras,total_devoluciones,total_general,cantidad_pedidos,estado,generado_por,aprobado_por,aprobado_en,observaciones'),
            ('pago','id','id,pedido_id,cierre_caja_id,tipo,metodo_pago,monto,propina,estado,registrado_por,registrado_en,conciliado_en,clave_operacion,motivo,referencia_externa'),
            ('notificacion_plantilla','id','id,clave,nombre,cuerpo,activa,actualizado_por,actualizado_en'),
            ('notificacion','id','id,plantilla_id,clave,cliente_id,pedido_id,canal,estado,intentos,creada_en,enviada_en'),
            ('rol_acceso','rol','rol,version'),
            ('rol_permiso','rol,permiso','rol,permiso,eliminado_en'),
            ('whatsapp_borrador','referencia_hash','cliente_id,telefono,items,tipo_entrega,metodo_pago,direccion,contacto,propuesta,estado,estado_pago,pedido_id,version,creado_en,expira_en,ultimo_mensaje_en'),
            ('whatsapp_cambio','id','id,pedido_id,version,accion,anterior,posterior,estado,revisado_por,revisado_en,creado_en'),
            ('whatsapp_comprobante','id','id,entrada_id,pedido_id,estado,revisado_por,revisado_en,creado_en,motivo'),
            ('whatsapp_atencion','id','id,entrada_id,motivo,estado,resuelta_por,resuelta_en,creado_en,resolucion')
        ) AS configuracion(tabla,clave,campos)
    LOOP
        EXECUTE format(
            'CREATE TRIGGER monu_auditar_cambio AFTER INSERT OR UPDATE OR DELETE ON %I.%I '
            'FOR EACH ROW EXECUTE FUNCTION %I.monu_registrar_cambio(%L,%L)',
            v_esquema,v_tabla,v_esquema,v_clave,v_campos);
        EXECUTE format(
            'CREATE TRIGGER monu_conservar_filas BEFORE DELETE ON %I.%I '
            'FOR EACH ROW EXECUTE FUNCTION %I.monu_impedir_destruccion()',
            v_esquema,v_tabla,v_esquema);
        EXECUTE format(
            'CREATE TRIGGER monu_conservar_tabla BEFORE TRUNCATE ON %I.%I '
            'FOR EACH STATEMENT EXECUTE FUNCTION %I.monu_impedir_destruccion()',
            v_esquema,v_tabla,v_esquema);
    END LOOP;
END;
$config$;

CREATE TRIGGER monu_conservar_log_filas BEFORE UPDATE OR DELETE ON auditoria
    FOR EACH ROW EXECUTE FUNCTION monu_impedir_destruccion();
CREATE TRIGGER monu_conservar_log_tabla BEFORE TRUNCATE ON auditoria
    FOR EACH STATEMENT EXECUTE FUNCTION monu_impedir_destruccion();

COMMENT ON COLUMN auditoria.origen IS
    'Canal y operacion validados por el backend; SQL:session_user para escrituras directas sin contexto.';
COMMENT ON COLUMN auditoria.identificador_operacion IS
    'Correlacion generada por el servidor para agrupar eventos de una operacion, sin credenciales.';
