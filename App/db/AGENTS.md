# SQL y esquema

Seguí [AGENTS raíz](../../AGENTS.md) y [guía del equipo](../../docs/GUIA_EQUIPO.md).
El responsable indicado allí coordina los cambios de la base compartida.

- `migrations/`: SQL numerado aplicado en orden con checksum en `schema_migrations`.
- `seed.sql`: datos de desarrollo; no es una migración ni se carga implícitamente.
- Motor local/CI: PostgreSQL 16. La base en nube debe comprobarse por separado.

Todo cambio de esquema usa una migración nueva con el siguiente prefijo disponible.
No editar ni renumerar migraciones ya aplicadas. No crear un segundo esquema,
ORM o runner. Mantener restricciones, índices y compatibilidad de consumidores.
En migraciones con datos, revisar reejecución del seed, secuencias e IDs; no
inventar identificadores manuales que colisionen.

Antes de aplicar SQL confirmar destino local o descartable; no usar la base
compartida para pruebas de agentes. No ejecutar reset, DROP, TRUNCATE ni borrar
volúmenes por rutina. Respetar la coordinación del equipo para aplicar cambios
de esquema compartido; la autorización a editar SQL no implica aplicarlo en nube.

Desde `App/backend`, con una base de prueba explícita:

```powershell
.\.venv\Scripts\python.exe -m scripts.migrate --seed
.\.venv\Scripts\python.exe -m scripts.migrate --status
.\.venv\Scripts\python.exe -m scripts.diccionario
.\.venv\Scripts\python.exe -m scripts.der
```

Validar desde base vacía y ejecutar los tests afectados. Revisar los diffs de
`docs/DER.md` y `docs/DICCIONARIO_DATOS.md`; se generan del SQL, no se editan a mano.
Detalle y alcance de cada comando en [desarrollo](../../docs/DESARROLLO.md).
