import { Component } from "react";

/* A rendering error in one page shows this message instead of blanking the
   whole app; the navigation stays usable. Keyed by page in App, so moving to
   another page resets it. */
export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { failed: false };
  }

  static getDerivedStateFromError() {
    return { failed: true };
  }

  componentDidCatch(error, info) {
    console.error("page render failed", error, info?.componentStack);
  }

  render() {
    if (!this.state.failed) return this.props.children;
    const isId = this.props.lang !== "en";
    return (
      <div className="panel panel-body page-error" role="alert">
        <p className="page-error-title">{isId ? "Bagian ini gagal ditampilkan" : "This part could not be shown"}</p>
        <p className="page-error-text">
          {isId
            ? "Coba muat ulang halaman. Untuk keadaan darurat, ikuti arahan BPBD DKI Jakarta atau telepon 112."
            : "Try reloading the page. In an emergency, follow BPBD DKI Jakarta or call 112."}
        </p>
        <button className="btn" onClick={() => window.location.reload()}>
          {isId ? "Muat ulang" : "Reload"}
        </button>
      </div>
    );
  }
}
