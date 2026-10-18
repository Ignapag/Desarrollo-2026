import assert from 'node:assert/strict';
import { test } from 'node:test';
import { periodoPanel, unidadesPorDia } from '../src/management/datosPanel.js';

test('el período usa Buenos Aires aunque UTC ya esté en el día siguiente', () => {
  const periodo = periodoPanel(new Date('2026-11-01T01:30:00Z'));
  assert.equal(periodo.desde, '2026-10-25');
  assert.equal(periodo.hasta, '2026-10-31');
  assert.equal(periodo.dias.length, 7);
});

test('agrega unidades por día sin confundirlas con pedidos y completa ceros', () => {
  const { dias } = periodoPanel(new Date('2026-01-02T12:00:00Z'));
  const serie = unidadesPorDia(dias, [
    { periodo: '2026-01-01', producto_id: 1, cantidad_vendida: 3, cantidad_pedidos: 1 },
    { periodo: '2026-01-01', producto_id: 2, cantidad_vendida: 5, cantidad_pedidos: 1 },
    { periodo: '2026-01-02', producto_id: 1, cantidad_vendida: 2 },
    { periodo: '2025-01-01', producto_id: 1, cantidad_vendida: 900 },
  ]);
  assert.equal(serie[0].fecha, '2025-12-27');
  assert.deepEqual(serie.map(({ unidades }) => unidades), [0, 0, 0, 0, 0, 8, 2]);
});

test('sin ventas la serie contiene siete ceros reales', () => {
  const { dias } = periodoPanel(new Date('2026-10-17T12:00:00Z'));
  assert.deepEqual(unidadesPorDia(dias, []).map(({ unidades }) => unidades), Array(7).fill(0));
});
