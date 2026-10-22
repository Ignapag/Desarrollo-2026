"""Repositorio del modulo de Usuarios y Seguridad, con SQL directo."""

from __future__ import annotations

import psycopg

from app.core.db import UnidadDeTrabajo
from app.errores import ReglaDeNegocio


class RepositorioUsuariosSQL:
    def __init__(self, uow: UnidadDeTrabajo) -> None:
        self.uow = uow

    # ------------------------------ lecturas ---------------------------

    async def por_username(self, username: str) -> dict | None:
        """Incluye password_hash: solo lo usa el login, nunca se expone."""
        return await self.uow.uno(
            """
            SELECT id, nombre, apellido, username, email, telefono, rol, estado,
                   fecha_alta, actualizado_en, ultimo_acceso, password_hash
            FROM usuario WHERE username = %s
            """,
            (username,),
        )

    async def por_id(self, usuario_id: int) -> dict | None:
        return await self.uow.uno(
            """
            SELECT id, nombre, apellido, username, email, telefono, rol, estado,
                   fecha_alta, actualizado_en, ultimo_acceso
            FROM usuario WHERE id = %s
            """,
            (usuario_id,),
        )

    async def existe_username(self, username: str, *, excluir_id: int | None = None) -> bool:
        if excluir_id is None:
            return bool(
                await self.uow.valor(
                    "SELECT EXISTS (SELECT 1 FROM usuario WHERE username = %s)", (username,)
                )
            )
        return bool(
            await self.uow.valor(
                "SELECT EXISTS (SELECT 1 FROM usuario WHERE username = %s AND id <> %s)",
                (username, excluir_id),
            )
        )

    async def buscar(
        self,
        *,
        nombre: str | None,
        apellido: str | None,
        username: str | None,
        rol: str | None,
        estado: str | None,
    ) -> list[dict]:
        """CU_USR_02: filtros combinables, todos opcionales."""
        return await self.uow.todos(
            """
            SELECT id, nombre, apellido, username, email, telefono, rol, estado,
                   fecha_alta, actualizado_en, ultimo_acceso
            FROM usuario
            WHERE (%s::text IS NULL OR nombre ILIKE '%%' || %s || '%%')
              AND (%s::text IS NULL OR apellido ILIKE '%%' || %s || '%%')
              AND (%s::text IS NULL OR username ILIKE '%%' || %s || '%%')
              AND (%s::text IS NULL OR rol = %s)
              AND (%s::text IS NULL OR estado = %s)
            ORDER BY apellido, nombre
            """,
            (nombre, nombre, apellido, apellido, username, username, rol, rol, estado, estado),
        )

    # ------------------------------ escrituras --------------------------

    async def bloquear_gestion(self, usuario_id: int) -> None:
        # Serializa cambios de rol/estado para no perder al último administrador.
        await self.uow.ejecutar("SELECT pg_advisory_xact_lock(7019262026028)")
        # Comparte el bloqueo con asignación de viajes. Después se reevalúa actividad.
        await self.uow.ejecutar(
            "SELECT usuario_id FROM repartidor WHERE usuario_id=%s FOR UPDATE", (usuario_id,),
        )

    async def sincronizar_perfil(self, usuario_id: int, rol: str, estado: str) -> None:
        if rol == "REPARTIDOR":
            await self.uow.ejecutar(
                """INSERT INTO repartidor (usuario_id, estado) VALUES (%s,%s)
                   ON CONFLICT (usuario_id) DO UPDATE SET estado=EXCLUDED.estado""",
                (usuario_id, "DISPONIBLE" if estado == "ACTIVO" else "FUERA_DE_SERVICIO"),
            )
        else:
            await self.uow.ejecutar(
                "UPDATE repartidor SET estado='FUERA_DE_SERVICIO' WHERE usuario_id=%s",
                (usuario_id,),
            )
        if rol == "CLIENTE":
            # Nunca fusionar por teléfono declarado ni borrar perfiles con historial.
            await self.uow.ejecutar(
                """INSERT INTO cliente (usuario_id, nombre, telefono_whatsapp)
                   SELECT id, concat_ws(' ', nombre, apellido), COALESCE(telefono,'')
                   FROM usuario WHERE id=%s ON CONFLICT (usuario_id) DO NOTHING""",
                (usuario_id,),
            )

    async def administradores_activos(self) -> int:
        return await self.uow.valor(
            "SELECT count(*) FROM usuario WHERE rol='ADMINISTRADOR' AND estado='ACTIVO'"
        )

    async def crear(
        self,
        *,
        nombre: str,
        apellido: str,
        username: str,
        email: str | None,
        telefono: str | None,
        password_hash: str,
        rol: str,
    ) -> int:
        try:
            fila = await self.uow.uno(
                """
                INSERT INTO usuario
                    (nombre, apellido, username, email, telefono, password_hash, rol)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (nombre, apellido, username, email, telefono, password_hash, rol),
            )
        except psycopg.errors.UniqueViolation as exc:
            # Carrera entre el chequeo previo del caso de uso y el INSERT:
            # la restriccion UNIQUE de la base es la que realmente lo garantiza.
            raise ReglaDeNegocio("Ese nombre de usuario ya existe") from exc
        return fila["id"]  # type: ignore[index]

    async def actualizar(
        self, usuario_id: int, *, nombre: str, apellido: str, username: str, estado: str
    ) -> None:
        await self.uow.ejecutar(
            """
            UPDATE usuario
               SET nombre = %s, apellido = %s, username = %s, estado = %s,
                   actualizado_en = now()
             WHERE id = %s
            """,
            (nombre, apellido, username, estado, usuario_id),
        )

    async def cambiar_estado(self, usuario_id: int, estado: str) -> None:
        await self.uow.ejecutar(
            "UPDATE usuario SET estado = %s, actualizado_en = now() WHERE id = %s",
            (estado, usuario_id),
        )

    async def cambiar_rol(self, usuario_id: int, rol: str) -> None:
        await self.uow.ejecutar(
            "UPDATE usuario SET rol = %s, actualizado_en = now() WHERE id = %s",
            (rol, usuario_id),
        )

    async def actualizar_ultimo_acceso(self, usuario_id: int) -> None:
        await self.uow.ejecutar(
            "UPDATE usuario SET ultimo_acceso = now() WHERE id = %s", (usuario_id,)
        )

    # ------------------------- reglas de baja ---------------------------

    async def tiene_actividad_operativa(self, usuario_id: int) -> bool:
        """Chequeo minimo de asociaciones activas antes de desactivar (CU_USR_04).

        Hoy solo cubre al Repartidor (viajes abiertos), el unico vinculo
        fuerte que existe en el esquema implementado. Si otro modulo agrega
        una asociacion que tambien deberia bloquear la baja (por ejemplo, un
        Empleado con pedidos en curso a su nombre), se suma aca.
        """
        return bool(
            await self.uow.valor(
                """
                SELECT EXISTS (
                    SELECT 1 FROM viaje
                    WHERE repartidor_id = %s AND estado IN ('PLANIFICADO','EN_RUTA')
                )
                """,
                (usuario_id,),
            )
        )
