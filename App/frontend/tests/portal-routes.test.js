import assert from 'node:assert/strict';
import { PassThrough } from 'node:stream';
import { test } from 'node:test';
import { createElement } from 'react';
import { renderToPipeableStream } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';
import { createServer } from 'vite';

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
