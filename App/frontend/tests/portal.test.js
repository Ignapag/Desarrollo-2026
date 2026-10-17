import assert from 'node:assert/strict';
import { test } from 'node:test';
import { aceptaSesion, resolverPortal } from '../src/shared/portal.js';

test('el portal cliente solo habilita menu y carrito, sin iniciar sesiones', () => {
  const portal = resolverPortal('clientes');
  assert.equal(portal.clientes, true);
  assert.equal(portal.personal, false);
  assert.equal(portal.inicio, '/menu');
  for (const rol of ['CLIENTE', 'EMPLEADO', 'ADMINISTRADOR', 'DUENIO', 'REPARTIDOR']) {
    assert.equal(aceptaSesion(rol, 'clientes'), false);
  }
});

test('el portal personal permite solo cuentas operativas y no ofrece checkout', () => {
  const portal = resolverPortal('personal');
  assert.equal(portal.clientes, false);
  assert.equal(portal.personal, true);
  assert.equal(portal.inicio, '/dashboard');
  assert.equal(aceptaSesion('CLIENTE', 'personal'), false);
  for (const rol of ['EMPLEADO', 'ADMINISTRADOR', 'DUENIO', 'REPARTIDOR']) {
    assert.equal(aceptaSesion(rol, 'personal'), true);
  }
  assert.equal(aceptaSesion('DESCONOCIDO', 'personal'), false);
});

test('desarrollo conserva ambos recorridos y falla ante un modo mal escrito', () => {
  assert.deepEqual(resolverPortal(), {
    modo: 'completo', clientes: true, personal: true, inicio: '/menu',
  });
  assert.equal(aceptaSesion('CLIENTE', 'completo'), true);
  assert.throws(() => resolverPortal('clientse'), /Portal inválido/);
});
