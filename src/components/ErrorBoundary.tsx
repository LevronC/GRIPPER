import { Component, type ErrorInfo, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { routes } from '../lib/routes'

interface Props {
  children: ReactNode
}

interface State {
  hasError: boolean
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false }

  static getDerivedStateFromError(): State {
    return { hasError: true }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('Gripper UI error:', error, info.componentStack)
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="min-h-screen bg-[#1e0037] text-white flex items-center justify-center p-8">
          <div className="max-w-md text-center space-y-4">
            <h1 className="text-xl font-semibold">Something went wrong</h1>
            <p className="text-white/70 text-sm">
              The terminal hit an unexpected error. Refresh the page or return to the home screen.
            </p>
            <div className="flex gap-3 justify-center">
              <button
                type="button"
                onClick={() => window.location.reload()}
                className="px-4 py-2 rounded-lg bg-purple-600 hover:bg-purple-500 text-sm font-medium"
              >
                Refresh
              </button>
              <Link
                to={routes.home}
                className="px-4 py-2 rounded-lg border border-white/20 hover:border-white/40 text-sm"
              >
                Home
              </Link>
            </div>
          </div>
        </div>
      )
    }

    return this.props.children
  }
}
