# Arquitectura del proyecto

El proyecto usa un **monolito modular con arquitectura screaming**: al abrir el
repositorio se ven primero las capacidades de Monu Burger y, dentro de cada
una, sus detalles tecnicos. Clean Architecture se mantiene **dentro** de cada
capacidad; no se reemplaza por carpetas globales `controllers/`, `services/` o
`repositories/`.

## Estructura canonica

```text
App/
├── backend/app/
│   ├── core/                         infraestructura transversal
│   └── modules/
│       ├── delivery/
│       ├── pedidos/
│       ├── stock/
│       ├── pagos/
│       ├── reportes/
│       ├── usuarios/
│       └── notificaciones/
│           ├── domain/               reglas puras
│           ├── application/          casos de uso
│           ├── infrastructure/       SQL y servicios externos
│           └── presentation/         HTTP, esquemas y dependencias
└── frontend/src/
    ├── auth/
    ├── ordering/                     menu, carrito y seguimiento
    ├── fulfillment/                  pedidos y delivery
    ├── kitchen/
    ├── inventory/
    ├── management/
    └── shared/                       solo piezas realmente compartidas
```

`App/frontend/` es el unico frontend valido. No se debe volver a crear
`frontend/` en la raiz del repositorio.

## Contrato de un modulo backend

1. Todo el codigo propio vive en `app/modules/<capacidad>/`.
2. `core/` no importa capacidades de negocio.
3. Las fabricas de servicios se declaran en
   `<capacidad>/presentation/dependencias.py`, no en
   `app/core/dependencias.py`.
4. Cada router se publica como una instancia `router` dentro de un archivo
   `presentation/router*.py`.
5. `app.main` descubre esos archivos automaticamente. Para agregar un modulo
   no se modifica `main.py`.
6. `domain/` no importa FastAPI, Pydantic, psycopg ni `app.core`.
7. Una capacidad no importa la infraestructura privada de otra. Si necesita
   colaborar, consume un contrato publico de aplicacion.

Ejemplo minimo:

```text
app/modules/pagos/
├── domain/entidades.py
├── application/servicio_pagos.py
├── infrastructure/repositorio_sql.py
└── presentation/
    ├── dependencias.py
    ├── esquemas.py
    └── router.py                      exporta `router`
```

El descubrimiento tambien admite `router_caja.py`, `router_admin.py` u otros
routers de la misma capacidad, siempre que el nombre empiece con `router`.

## Contrato del frontend

- Las carpetas representan recorridos o capacidades, no tipos tecnicos.
- Un componente usado por una sola capacidad se queda dentro de ella.
- `shared/` no contiene reglas de pedidos, stock, caja o delivery.
- `App.jsx` compone navegacion y layouts; no guarda reglas de negocio.
- Las llamadas HTTP y el estado de una capacidad permanecen junto a esa
  capacidad.
- Los nombres nuevos se escriben en minusculas y con una sola convencion. No
  mezclar `components/Menu` con `ordering` para la misma funcionalidad.

## Como integrar las ramas existentes

Antes de abrir o actualizar el Pull Request:

```bash
git checkout main
git pull
git checkout TuRama
git merge main
```

Luego aplicar estas reglas segun la rama:

- **Emilio:** su organizacion `auth`, `ordering`, `fulfillment`, `inventory`,
  `kitchen`, `management` y `shared` es la base screaming del frontend.
- **Juan:** el proyecto creado en `frontend/` no se integra como una segunda
  aplicacion. Hay que trasladar menu, carrito y seguimiento a
  `App/frontend/src/ordering/` y reutilizar el `package.json` canonico.
- **Jose:** `stock/` y `reportes/` ya respetan el limite por capacidad. Cada
  modulo debe agregar sus routers y dependencias dentro de su carpeta.
- **Tomas:** `usuarios/` y `notificaciones/` se integran como capacidades. Las
  dependencias de esos servicios no se agregan al archivo central de `core`.
- **Pagos y caja:** todos los avances se consolidan bajo un unico
  `modules/pagos/`; no se fusionan ramas intermedias que ya fueron revertidas.

En una resolucion de conflictos se conserva el registro automatico de routers
y se eliminan los imports manuales de capacidades desde `app.main`.

## Comprobacion antes del Pull Request

```bash
cd App/backend
ruff check .
pytest -q

cd ../frontend
npm ci
npm run lint
npm run build
```

`tests/test_arquitectura.py` protege los limites principales y rechaza un
segundo frontend en la raiz.
