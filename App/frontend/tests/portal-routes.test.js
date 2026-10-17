import assert from 'node:assert/strict';
import { PassThrough } from 'node:stream';
import { test } from 'node:test';
import { createElement } from 'react';
import { renderToPipeableStream, renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';
import { createServer } from 'vite';

async function menuConEstado(t, estado) {
  const servidor = await createServer({
    mode: 'clientes', server: { middlewareMode: true, hmr: false }, logLevel: 'silent',
    plugins: [{
      name: 'catalogo-de-prueba', enforce: 'pre',
      load(id) {
        if (id.replaceAll('\\', '/').endsWith('/src/shared/store/DataContext.jsx')) {
          return `export const useData = () => ({state: ${JSON.stringify(estado)}, dispatch() {}, async refreshData() {}});`;
        }
        return null;
      },
    }],
  });
  t.after(() => servidor.close());
  const { default: Menu } = await servidor.ssrLoadModule('/src/ordering/Menu.jsx');
  return renderToStaticMarkup(createElement(MemoryRouter, null, createElement(Menu)));
}

async function vista(servidor, ruta) {
  const [{ default: App }, { AuthProvider }, { DataProvider }] = await Promise.all([
    servidor.ssrLoadModule('/src/App.jsx'),
    servidor.ssrLoadModule('/src/auth/AuthContext.jsx'),
    servidor.ssrLoadModule('/src/shared/store/DataContext.jsx'),
  ]);
  const arbol = createElement(MemoryRouter, { initialEntries: [ruta] },
    createElement(AuthProvider, null, createElement(DataProvider, null, createElement(App))));
  return new Promise((resolve, reject) => {
    const salida = new PassThrough();
    let html = '';
    salida.on('data', (parte) => { html += parte.toString(); });
    salida.on('end', () => resolve(html));
    const render = renderToPipeableStream(arbol, {
      onAllReady() { render.pipe(salida); },
      onShellError: reject,
      onError: reject,
    });
  });
}

test('las rutas de clientes muestran menu y no renderizan login ni gestion', async (t) => {
  const servidor = await createServer({
    mode: 'clientes', server: { middlewareMode: true, hmr: false }, logLevel: 'silent',
  });
  t.after(() => servidor.close());
  const menu = await vista(servidor, '/menu');
  assert.match(menu, /Buscar en el menú/);
  assert.match(menu, /Cargando menú/);
  assert.doesNotMatch(menu, /Agregar Cheese al carrito/);
  assert.doesNotMatch(menu, /href="\/login"/);
  for (const ruta of ['/login', '/dashboard/orders', '/delivery']) {
    const html = await vista(servidor, ruta);
    assert.doesNotMatch(html, /Iniciar sesión|Panel de Control|Repartidor Activo/);
  }
});

test('el portal personal muestra credenciales y no renderiza menu publico', async (t) => {
  const servidor = await createServer({
    mode: 'personal', server: { middlewareMode: true, hmr: false }, logLevel: 'silent',
  });
  t.after(() => servidor.close());
  const login = await vista(servidor, '/login');
  assert.match(login, /Iniciar sesión/);
  assert.match(login, /autoComplete="current-password"/i);
  assert.doesNotMatch(login, /Ver el menú y pedir sin cuenta/);
  assert.doesNotMatch(await vista(servidor, '/menu'), /Buscar en el menú|Abrir carrito/);
});

test('un fallo de catalogo ofrece reintento y no permite comprar datos anteriores', async (t) => {
  const html = await menuConEstado(t, {
    catalogStatus: 'error', catalogError: 'No pudimos cargar el menú. Intentá nuevamente.',
    catalog: [{ id: 54, name: 'Cheese', available: true, active: true }],
  });
  assert.match(html, /role="alert"/);
  assert.match(html, /Reintentar/);
  assert.doesNotMatch(html, /Agregar Cheese al carrito/);
});

for (const disponible of [true, false]) {
  test(`el menu ${disponible ? 'habilita' : 'bloquea'} agregar un producto ${disponible ? 'disponible' : 'sin stock'}`, async (t) => {
    const html = await menuConEstado(t, {
      catalogStatus: 'ready', catalog: [{
        id: 54, name: 'Cheese', category: 'Nuestras Burgers', active: true,
        available: disponible, price: 11000, variants: [],
      }],
    });
    const boton = html.match(/<button[^>]*aria-label="Agregar Cheese al carrito"[^>]*>/)?.[0];
    assert.ok(boton);
    assert.equal(/\sdisabled(?:[=\s>])/.test(boton), !disponible);
    if (!disponible) assert.match(html, /No disponible/);
  });
}

test('personalizar Cheese solo ofrece los retiros de su receta', async (t) => {
  const html = await menuConEstado(t, {
    catalogStatus: 'ready', catalog: [{
      id: 54, name: 'Cheese', category: 'Nuestras Burgers', active: true,
      available: true, price: 11000, variants: [],
      removableIngredients: ['Queso Cheddar', 'Salsa Monu'],
    }],
  });
  assert.match(html, /Sin Queso Cheddar/);
  assert.match(html, /Sin Salsa Monu/);
  assert.doesNotMatch(html, /Sin Cebolla|Sin Pepinillos|Otras notas|extras\.\.\./);
});

test('los productos sin ingredientes quitables no ofrecen personalizacion', async (t) => {
  const html = await menuConEstado(t, {
    catalogStatus: 'ready', catalog: [{
      id: 80, name: 'Fanta', category: 'Bebidas', active: true,
      available: true, price: 2200, variants: [], removableIngredients: [],
    }],
  });
  assert.doesNotMatch(html, /Personalizar Fanta|Sacar ingredientes/);
});
