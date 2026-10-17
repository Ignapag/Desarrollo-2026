## Que capacidad incorpora o modifica

<!-- pedidos, delivery, stock, pagos, reportes, usuarios, notificaciones, etc. -->

## Verificacion

- [ ] Lei `docs/ARQUITECTURA.md`.
- [ ] Segui `AGENTS.md`, las instrucciones del area y `docs/CLEAN_CODE.md`.
- [ ] El codigo vive dentro de la capacidad correspondiente.
- [ ] No agregue imports manuales de routers en `app/main.py`.
- [ ] No agregue dependencias de negocio a `app/core/dependencias.py`.
- [ ] No cree otro proyecto `frontend/` fuera de `App/frontend/`.
- [ ] Ejecute las verificaciones del backend pertinentes; suite SQL/HTTP sobre base descartable.
- [ ] Ejecute `npm run lint` y `npm run build` si toque el frontend.
- [ ] Agregue o actualice pruebas de comportamiento cuando el cambio lo requiere.
- [ ] Actualice la documentacion de contratos/comandos afectados y declare verificaciones omitidas.

## Notas de integracion

<!-- Dependencias con otros modulos, migraciones o decisiones que debe conocer el revisor. -->
