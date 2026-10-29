-- intento_login: fallos de inicio de sesión de la ventana vigente (CU_USR_01), una fila por username (usuario:<lower>) o por IP confiable (ip:<dirección>). Cada intento se reserva antes de verificar la contraseña con una única sentencia atómica; un login exitoso borra la fila del username. Es estado técnico de corta vida: no se audita fila a fila, se purga al vencer y los intentos quedan en auditoria.
CREATE TABLE intento_login (
    clave       TEXT        PRIMARY KEY,
    fallos      INTEGER     NOT NULL CHECK (fallos >= 0),
    vence_en    TIMESTAMPTZ NOT NULL,
    CONSTRAINT intento_login_clave_chk
        CHECK (clave ~ '^(usuario|ip):' AND length(clave) <= 200)
);

-- La purga busca las ventanas vencidas sin recorrer la tabla completa.
CREATE INDEX intento_login_vence_idx ON intento_login (vence_en);
