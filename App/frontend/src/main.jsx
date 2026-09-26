import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App.jsx'
import { Toaster } from 'sonner';
import './index.css'
import { AuthProvider } from './auth/AuthContext.jsx'
import { DataProvider } from './shared/store/DataContext.jsx'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <DataProvider>
          <Toaster richColors position="bottom-center" />
          <App />
        </DataProvider>
      </AuthProvider>
    </BrowserRouter>
  </React.StrictMode>,
)