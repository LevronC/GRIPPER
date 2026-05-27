import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import LandingPage from './pages/LandingPage'
import DocsPage from './pages/DocsPage'
import GripperDashboard from './components/GripperDashboard'
import { ErrorBoundary } from './components/ErrorBoundary'
import { routes } from './lib/routes'

function App() {
  return (
    <ErrorBoundary>
      <BrowserRouter>
        <Routes>
          <Route path={routes.home} element={<LandingPage />} />
          <Route path={routes.docs} element={<DocsPage />} />
          <Route path={routes.terminal} element={<GripperDashboard />} />
          <Route path="*" element={<Navigate to={routes.home} replace />} />
        </Routes>
      </BrowserRouter>
    </ErrorBoundary>
  )
}

export default App
