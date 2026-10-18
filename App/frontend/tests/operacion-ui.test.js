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

test('formulario de corrección muestra destinos reales, motivo y confirmación física', () => {
  const html = renderToStaticMarkup(createElement(forms.StateOperation, props));
  assert.match(html, /value="PENDIENTE"/);
  assert.match(html, /value="CONFIRMADO"/);
  assert.match(html, /conservar insumos/);
  assert.match(html, /Cancelar y declarar merma/);
  assert.match(html, /Motivo \(obligatorio\)/);
  assert.match(html, /pedido #31/);
  assert.doesNotMatch(html, /pedido #909/);
});

test('empleado no ve reapertura privilegiada y dueño sí', () => {
  const closed = { ...order, estado: 'CANCELADO' };
  assert.equal(renderToStaticMarkup(createElement(forms.StateOperation, { ...props, order: closed })), '');
  const html = renderToStaticMarkup(createElement(forms.StateOperation, { ...props, order: closed, role: 'DUENIO' }));
  assert.match(html, /Reabrir y consumir insumos nuevamente/);
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

test('pagos explica acreditación humana, diferencia neto/saldo y exige verificación', () => {
  const html = renderToStaticMarkup(createElement(OrderPayments, { ...props, userId: 1 }));
  assert.match(html, /Neto conciliado/);
  assert.match(html, /Saldo pendiente/);
  assert.match(html, /Una imagen de transferencia no acredita dinero/);
  assert.match(html, /Registrar transferencia e ingreso verificado/);
  assert.match(html, /type="checkbox" required=""/);
  assert.match(html, /max="1000"/);
  assert.doesNotMatch(html, /billetera|MERCADO_PAGO/);
});
