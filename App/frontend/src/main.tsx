import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import { CarritoProvider } from './context/CarritoContext.tsx'
import { PedidosProvider } from './context/PedidosContext.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <CarritoProvider>
      <PedidosProvider>
        <App />
      </PedidosProvider>
    </CarritoProvider>
  </StrictMode>,
)