import { Component, type ErrorInfo, type ReactNode } from 'react'
import { AlertTriangle, RefreshCw } from 'lucide-react'

interface Props {
  children: ReactNode
}

interface State {
  hasError: boolean
  error: Error | null
}

export class ErrorBoundary extends Component<Props, State> {
  public override state: State = {
    hasError: false,
    error: null,
  }

  public static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error }
  }

  public override componentDidCatch(error: Error, errorInfo: ErrorInfo): void {
    console.error('ErrorBoundary caught an unhandled rendering error:', error, errorInfo)
  }

  private handleReload = (): void => {
    window.location.reload()
  }

  public override render(): ReactNode {
    if (this.state.hasError) {
      return (
        <div className="min-h-screen flex items-center justify-center p-6 bg-slate-950 text-slate-100">
          <div className="max-w-md w-full bg-slate-900 border border-red-900/50 rounded-xl p-6 shadow-2xl">
            <div className="flex items-center gap-3 text-red-400 mb-4">
              <AlertTriangle className="w-8 h-8" />
              <h2 className="text-xl font-semibold">Unexpected UI Error</h2>
            </div>
            <p className="text-slate-400 text-sm mb-4">
              An unexpected error occurred while rendering the Corbel workspace interface.
            </p>
            {this.state.error && (
              <pre className="bg-slate-950 p-3 rounded-lg text-xs font-mono text-red-300 overflow-x-auto mb-6">
                {this.state.error.message}
              </pre>
            )}
            <button
              onClick={this.handleReload}
              className="w-full flex items-center justify-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg font-medium transition cursor-pointer"
            >
              <RefreshCw className="w-4 h-4" />
              Reload Application
            </button>
          </div>
        </div>
      )
    }

    return this.props.children
  }
}
