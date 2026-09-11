# Mis tareas — Ignacio Pagotto

Tareas asignadas a mí en el plan por responsable del proyecto
**Sistema de Gestión Monu Burger**. Son 18 y están en el orden en que hay que
hacerlas.

> La columna "Trabaja junto con" aparecía cortada en el margen derecho del
> original: donde decía "Juan Ignaci…" se completó como **Juan Ignacio
> Martínez**. Conviene verificarlo.

---

## Pendiente ahora

Lo que falta de mi parte, en orden de dependencia:

- [ ] **9. Algoritmo de agrupación geográfica**
  Ya existen la tabla `viaje` (con el tope de 2 pedidos por salida impuesto por
  trigger), `zona_cobertura` con polígonos GeoJSON y la función `distancia_km()`
  (haversine). Falta el algoritmo que arma los grupos de pedidos cercanos.
- [ ] **10. Lógica de asignación automática**
  Ya existen `repartidor.estado`, la última posición conocida
  (`ultima_lat` / `ultima_lng`) y los estados de `envio`. Falta elegir el
  repartidor disponible más cercano y crear el viaje.
- [ ] **11. Pruebas de asignación**
  Para probar de punta a punta hacen falta pedidos confirmados, y el módulo de
  Pedidos todavía no está implementado. Coordinar con quien lo tenga asignado.
- [ ] **13. Control de Avance — Septiembre**
- [ ] **14. Pruebas funcionales por módulo** — con José Joaquín Santoro, Emilio B. Rivero, Juan Ignacio Martínez
- [ ] **15. Pruebas de integración end-to-end** — con José Joaquín Santoro, Emilio B. Rivero, Juan Ignacio Martínez
- [ ] **16. Pruebas de rendimiento** — con José Joaquín Santoro
  Referencia: RNF-01 exige respuesta < 2 s en condiciones normales.
- [ ] **17. Corrección de defectos y regresión** — con José Joaquín Santoro
- [ ] **18. Cierre del Proyecto** — con José Joaquín Santoro
  Entrega final, capacitación y documentación de cierre.

## Hecho

- [x] **7. Carga inicial y procedimientos almacenados**
  `seed.sql` cargado en la base compartida: usuarios, zonas, ingredientes,
  productos y recetas. Funciones y triggers aplicados y verificados.
- [x] **8. Pruebas de integridad**
  Esquema aplicado sobre PostgreSQL 17 en Supabase sin errores.
  27 pruebas en `App/backend/tests/test_integridad_bd.py`, todas pasan.

- [x] **1. Planificación**
- [x] **2. Análisis de requerimientos** — con Emilio B. Rivero, Juan Ignacio Martínez
  Entrevista estructurada con un socio; 14 RF y 10 RNF identificados.
- [x] **3. Documentación del relevamiento y alcance** — con Emilio B. Rivero, Juan Ignacio Martínez
  Entregado en la Actividad N°2 (reentrega).
- [x] **4. Control de Avance — Junio**
- [x] **5. Diseño del modelo de datos (DER)**
  El DER entregado se corrigió: 12 cambios documentados como C-01…C-12 en
  [docs/CAMBIOS_DER.md](docs/CAMBIOS_DER.md). **Queda actualizar el diagrama del informe** con
  esas correcciones.
- [x] **6. Implementación de esquema y tablas**
  6 migraciones en `db/migrations/` (001 a 006), con índices, constraints y
  vistas de apoyo.
- [x] **12. Control de Avance — Agosto**

---

## Transcripción completa del plan

Tal como figura en el cronograma original.

| # | Tarea | Módulo / Fase | Inicio | Fin | Duración | Trabaja junto con |
|---|-------|---------------|--------|-----|----------|-------------------|
| 1 | Planificación | Gestión del Proyecto | 16/3/26 | 25/3/26 | 8 días | — |
| 2 | Análisis de requerimientos | Relevamiento | 1/4/26 | 7/4/26 | 5 días | Emilio B. Rivero, Juan Ignacio Martínez |
| 3 | Documentación del relevamiento y alcance | Relevamiento | 8/4/26 | 14/4/26 | 5 días | Emilio B. Rivero, Juan Ignacio Martínez |
| 4 | Control de Avance - Junio | Seguimiento y Control | 1/6/26 | 2/6/26 | 2 días | — |
| 5 | Diseño del modelo de datos (DER) | Base de Datos | 3/6/26 | 9/6/26 | 5 días | — |
| 6 | Implementación de esquema y tablas | Base de Datos | 10/6/26 | 16/6/26 | 5 días | — |
| 7 | Carga inicial y procedimientos almacenados | Base de Datos | 17/6/26 | 22/6/26 | 4 días | — |
| 8 | Pruebas de integridad | Base de Datos | 23/6/26 | 25/6/26 | 3 días | — |
| 9 | Algoritmo de agrupación geográfica | Asignación de Repartidores | 29/6/26 | 3/7/26 | 5 días | — |
| 10 | Lógica de asignación automática | Asignación de Repartidores | 6/7/26 | 10/7/26 | 5 días | — |
| 11 | Pruebas de asignación | Asignación de Repartidores | 13/7/26 | 15/7/26 | 3 días | — |
| 12 | Control de Avance - Agosto | Seguimiento y Control | 3/8/26 | 4/8/26 | 2 días | — |
| 13 | Control de Avance - Septiembre | Seguimiento y Control | 1/9/26 | 2/9/26 | 2 días | — |
| 14 | Pruebas funcionales por módulo | Pruebas e Integración | 14/9/26 | 21/9/26 | 6 días | José Joaquín Santoro, Emilio B. Rivero, Juan Ignacio Martínez |
| 15 | Pruebas de integración end-to-end | Pruebas e Integración | 22/9/26 | 28/9/26 | 5 días | José Joaquín Santoro, Emilio B. Rivero, Juan Ignacio Martínez |
| 16 | Pruebas de rendimiento | Pruebas e Integración | 29/9/26 | 1/10/26 | 3 días | José Joaquín Santoro |
| 17 | Corrección de defectos y regresión | Pruebas e Integración | 2/10/26 | 6/10/26 | 3 días | José Joaquín Santoro |
| 18 | Cierre del Proyecto | Gestión del Proyecto | 7/10/26 | 19/10/26 | 8,38 días | José Joaquín Santoro |
