import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import LandingPage from './pages/LandingPage'
import DocsPage from './pages/DocsPage'
import GripperDashboard from './components/GripperDashboard'
import { routes } from './lib/routes'

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path={routes.home} element={<LandingPage />} />
        <Route path={routes.docs} element={<DocsPage />} />
        <Route path={routes.terminal} element={<GripperDashboard />} />
        <Route path="*" element={<Navigate to={routes.home} replace />} />
      </Routes>
    </BrowserRouter>
  )
}

export default App
