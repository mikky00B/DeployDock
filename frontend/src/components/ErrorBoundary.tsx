import { Component, type ErrorInfo, type ReactNode } from "react";

type Props = {
  children: ReactNode;
};

type State = {
  hasError: boolean;
  message: string;
};

export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, message: "" };

  static getDerivedStateFromError(error: Error): State {
    return {
      hasError: true,
      message: error.message || "An unexpected error occurred.",
    };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error("Uncaught UI error:", error, info.componentStack);
  }

  render() {
    if (this.state.hasError) {
      return (
        <main className="loading-page">
          <div style={{ maxWidth: 480, textAlign: "center", padding: "32px 24px" }}>
            <h1 style={{ fontSize: "1.25rem", marginBottom: 12 }}>Something went wrong</h1>
            <p style={{ opacity: 0.8, marginBottom: 20 }}>{this.state.message}</p>
            <button
              type="button"
              className="primary-inline-button"
              onClick={() => window.location.reload()}
            >
              Reload page
            </button>
          </div>
        </main>
      );
    }
    return this.props.children;
  }
}
