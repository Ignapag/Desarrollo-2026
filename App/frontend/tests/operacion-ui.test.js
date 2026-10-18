import assert from 'node:assert/strict';
import { after, before, test } from 'node:test';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { createServer } from 'vite';
import react from '@vitejs/plugin-react';

let server;
let forms;
let OrderPayments;
const order = { id: 909, numero: 31, version: 2, estado: 'EN_PREPARACION', tipo_entrega: 'DELIVERY', metodo_pago_acordado: 'EFECTIVO', saldo_pendiente: '1000', neto_cobrado: '500', pagos: [], direccion: { calle: 'Camino', numero: '10', localidad: 'Ensenada' } };
const props = { order, role: 'EMPLEADO', commands: {}, run: () => {}, busy: false };
before(async () => {
  server = await createServer({ configFile: false, plugins: [react()], server: { middlewareMode: true, hmr: false, ws: false }, optimizeDeps: { noDiscovery: true }, appType: 'custom' });
  forms = await server.ssrLoadModule('/src/fulfillment/OrderOperationForms.jsx');
  ({ default: OrderPayments } = await server.ssrLoadModule('/src/fulfillment/OrderPayments.jsx'));
});
after(async () => { await server?.close(); });

test('acciones de estado directas con correcciones secundarias y nota opcional', () => {
  const html = renderToStaticMarkup(createElement(forms.StateOperation, props));
  assert.match(html, /Marcar listo/);
  assert.match(html, /Volver a nuevos/);
  assert.match(html, /Volver a confirmados/);
  assert.match(html, /Cancelar pedido/);
  assert.match(html, /Más acciones/);
  assert.match(html, /Nota \(opcional\)/);
  assert.doesNotMatch(html, /required|type="checkbox"|Motivo \(obligatorio\)/);
});

test('empleado no ve reapertura privilegiada y dueño sí', () => {
  const closed = { ...order, estado: 'CANCELADO' };
  assert.equal(renderToStaticMarkup(createElement(forms.StateOperation, { ...props, order: closed })), '');
  const html = renderToStaticMarkup(createElement(forms.StateOperation, { ...props, order: closed, role: 'DUENIO' }));
  assert.match(html, /Reabrir pedido/);
});

test('repartidor no tiene formulario de edición ni comandos locales', () => {
  assert.equal(renderToStaticMarkup(createElement(forms.StateOperation, { ...props, role: 'REPARTIDOR' })), '');
  const html = renderToStaticMarkup(createElement(forms.EditOperation, { ...props, role: 'REPARTIDOR' }));
  assert.doesNotMatch(html, /<form/);
});

test('edición conserva campos de domicilio y ofrece sólo efectivo o transferencia', () => {
  const html = renderToStaticMarkup(createElement(forms.EditOperation, props));
  assert.match(html, /value="Camino"/);
  assert.match(html, /value="Ensenada"/);
  assert.match(html, /value="RETIRO"/);
  assert.match(html, /value="TRANSFERENCIA"/);
  assert.doesNotMatch(html, /MERCADO_PAGO|Mercado Pago/);
  assert.match(html, /type="submit"|Guardar cambios/);
});

test('pagos ofrece importe preparado y confirmación humana explícita sin casillas', () => {
  const html = renderToStaticMarkup(createElement(OrderPayments, { ...props, order: { ...order, metodo_pago_acordado: 'TRANSFERENCIA' }, userId: 1 }));
  assert.match(html, /Pendiente:/);
  assert.match(html, /Confirmá sólo cuando veas el dinero ingresado/);
  assert.match(html, /Confirmar ingreso de/);
  assert.doesNotMatch(html, /type="checkbox"|required=""/);
  assert.match(html, /max="1000"/);
  assert.doesNotMatch(html, /billetera|MERCADO_PAGO/);
});
