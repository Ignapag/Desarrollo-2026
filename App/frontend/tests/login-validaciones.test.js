import assert from 'node:assert/strict';
import { after, before, test } from 'node:test';
import { act, createElement } from 'react';
import { MemoryRouter } from 'react-router-dom';
import react from '@vitejs/plugin-react';
import { createTestServer } from './vite-test-server.js';
import { installMinimalDom, elements, reactProps, deferred } from './minimal-dom.js';
let server, dom, createRoot, Login, setAuth;
before(async () => {
  dom = installMinimalDom(); ({ createRoot } = await import('react-dom/client'));
  server = await createTestServer({ configFile: false, plugins: [{ name: 'auth-login-validation', enforce: 'pre', resolveId(source) { if (source === 'sonner') return '\0sonner-login-test'; }, load(id) {
    if (id === '\0sonner-login-test') return 'export const toast={error(){},success(){}};';
    if (id.replaceAll('\\', '/').endsWith('/src/auth/AuthContext.jsx')) return 'let auth; export const setAuth=(next)=>{auth=next}; export const useAuth=()=>auth;';
  } }, react()], ssr: { noExternal: ['sonner'] }, server: { middlewareMode: true, hmr: false, ws: false }, optimizeDeps: { noDiscovery: true }, appType: 'custom', logLevel: 'silent' });
  ({ default: Login } = await server.ssrLoadModule('/src/auth/Login.jsx'));
  ({ setAuth } = await server.ssrLoadModule('/src/auth/AuthContext.jsx'));
});
after(async () => { await server?.close(); dom?.restore(); });
async function mount(t, auth) {
  setAuth(auth);
  const container = document.createElement('div'); document.body.appendChild(container);
  const root = createRoot(container);
  await act(async () => root.render(createElement(MemoryRouter, null, createElement(Login))));
  t.after(async () => { await act(async () => root.unmount()); document.body.removeChild(container); });
  return container;
}
const field = (container, id) => elements(container, (node) => node.getAttribute?.('id') === id)[0];
const form = (container) => elements(container, (node) => node.localName === 'form')[0];
const submit = { preventDefault() {} };
async function change(node, value) { await act(async () => reactProps(node).onChange({ target: { value } })); }
test('usuario de espacios se rechaza con error asociado y foco', async (t) => {
  let calls = 0;
  const container = await mount(t, { login: async () => { calls++; return { success: true }; } });
  await change(field(container, 'username'), '   '); await change(field(container, 'password'), 'secret');
  await act(async () => reactProps(form(container)).onSubmit(submit));
  assert.equal(calls, 0);
  assert.equal(field(container, 'username').getAttribute('aria-invalid'), 'true');
  assert.equal(document.activeElement, field(container, 'username'));
});
test('doble submit de login envía una sola solicitud y muestra fallo persistente', async (t) => {
  const wait = deferred(); let calls = 0;
  const container = await mount(t, { login: () => { calls++; return wait.promise; } });
  await change(field(container, 'username'), 'ana'); await change(field(container, 'password'), 'secret');
  let one, two;
  await act(async () => { const handler = reactProps(form(container)).onSubmit; one = handler(submit); two = handler(submit); });
  assert.equal(calls, 1);
  await act(async () => { wait.resolve({ error: 'Credenciales inválidas' }); await Promise.all([one, two]); });
  assert.match(container.textContent, /Credenciales inválidas/);
});
