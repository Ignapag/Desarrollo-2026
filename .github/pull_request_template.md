## Que capacidad incorpora o modifica

<!-- pedidos, delivery, stock, pagos, reportes, usuarios, notificaciones, etc. -->

## Verificacion

- [ ] Lei `docs/ARQUITECTURA.md`.
- [ ] El codigo vive dentro de la capacidad correspondiente.
- [ ] No agregue imports manuales de routers en `app/main.py`.
- [ ] No agregue dependencias de negocio a `app/core/dependencias.py`.
- [ ] No cree otro proyecto `frontend/` fuera de `App/frontend/`.
- [ ] Ejecute `ruff check .` y `pytest -q` en el backend.
- [ ] Ejecute `npm run lint` y `npm run build` si toque el frontend.
- [ ] Agregue o actualice pruebas de la capacidad.

## Notas de integracion

<!-- Dependencias con otros modulos, migraciones o decisiones que debe conocer el revisor. -->
