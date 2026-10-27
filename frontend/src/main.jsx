import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, MemoryRouter } from 'react-router-dom'
import { DEMO } from './api'
import App from './App'
import { AuthProvider } from './auth'
import './styles.css'

// The demo runs inside a frame where the URL path can't change, so it routes in memory.
const Router = DEMO ? MemoryRouter : BrowserRouter

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <Router>
      <AuthProvider>
        <App />
      </AuthProvider>
    </Router>
  </StrictMode>,
)
