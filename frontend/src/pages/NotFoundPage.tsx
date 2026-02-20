// src/pages/NotFoundPage.tsx
import { Link } from "react-router-dom";

export default function NotFoundPage() {
  return (
    <div className="error-page">
      <div className="error-page__code">404</div>
      <h1 className="error-page__title">Page not found</h1>
      <p className="error-page__message">
        The page you are looking for does not exist or has been moved.
      </p>
      <div className="error-page__action">
        <Link to="/" className="btn btn--primary" style={{ display: "inline-flex", width: "auto" }}>
          Go to dashboard
        </Link>
      </div>
    </div>
  );
}
