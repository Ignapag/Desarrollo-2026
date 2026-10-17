import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv } from 'vite'
import { resolverPortal } from './src/shared/portal.js'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const variables = loadEnv(mode, process.cwd(), 'VITE_')
  const modo = ['clientes', 'personal'].includes(mode)
    ? mode
    : process.env.VITE_PORTAL || variables.VITE_PORTAL || 'completo'
  resolverPortal(modo)
  return {
    plugins: [react()],
    define: { 'import.meta.env.VITE_PORTAL': JSON.stringify(modo) },
    server: {
      proxy: {
        '/api': 'http://127.0.0.1:8000',
      },
    },
  }
})
