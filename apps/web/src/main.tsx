import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { registerSW } from 'virtual:pwa-register'

import { App } from './App'
import './styles.css'

registerSW({ immediate: true })

const root = document.getElementById('root')
if (root === null) {
  throw new Error('Root element is missing')
}

createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
