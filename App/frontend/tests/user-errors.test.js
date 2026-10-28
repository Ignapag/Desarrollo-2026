import assert from 'node:assert/strict';
import { test } from 'node:test';
import { UserFacingError, apiResponseError, userErrorMessage } from '../src/shared/api/userErrors.js';

test('un error desconocido o una marca falsificada nunca autoriza mostrar su mensaje', () => {
  for (const error of [new Error('SQL /srv password=secreto'), { name: 'UserFacingError', message: 'token interno' }, null]) {
    assert.equal(userErrorMessage(error, 'No pudimos cargar el menú.'), 'No pudimos cargar el menú.');
  }
});

test('las validaciones locales conservan instrucciones corregibles', () => {
  assert.equal(userErrorMessage(new UserFacingError('Ingresá un teléfono válido.')), 'Ingresá un teléfono válido.');
});

test('cada acción aporta contexto sin perder la advertencia de resultado incierto', () => {
  const error = apiResponseError(503, { mensaje: 'SQL interno' }, { write: true });
  const message = userErrorMessage(error, 'No pudimos registrar el pago.');
  assert.match(message, /registrar el pago/);
  assert.match(message, /Comprobá su estado.*evitar duplicaciones/);
  assert.doesNotMatch(message, /SQL|503/);
});

test('las traducciones exactas no aceptan prefijos, sufijos ni diagnósticos de errores del servidor', () => {
  for (const [status, mensaje] of [[409, 'Ese nombre de usuario ya existe SQL'], [500, 'Ese nombre de usuario ya existe']]) {
    const message = userErrorMessage(apiResponseError(status, { mensaje }), 'No pudimos crear la cuenta.');
    assert.doesNotMatch(message, /SQL|Ese nombre/);
  }
});

test('sesión vencida y falta de acceso tienen mensajes simples', () => {
  assert.equal(userErrorMessage({ status: 401, message: 'JWT firma' }), 'La sesión venció. Volvé a ingresar.');
  assert.equal(userErrorMessage({ status: 403, message: 'rol_interno' }), 'No tenés acceso a esta acción.');
});
