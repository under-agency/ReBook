import { Component, ErrorInfo, ReactNode } from "react";
import { Button } from "./ui";

/** Одна упавшая страница не должна оставлять белый экран на весь кабинет. */
export default class ErrorBoundary extends Component<
  { children: ReactNode },
  { error: Error | null }
> {
  state: { error: Error | null } = { error: null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("Страница упала:", error, info.componentStack);
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div className="empty">
        <span className="empty-title">Страница не открылась</span>
        <span>Мы записали ошибку. Обновите страницу или вернитесь на главную.</span>
        <div className="row mt-2">
          <Button onClick={() => this.setState({ error: null })}>Попробовать снова</Button>
          <Button variant="primary" onClick={() => { window.location.href = "/"; }}>
            На главную
          </Button>
        </div>
      </div>
    );
  }
}
