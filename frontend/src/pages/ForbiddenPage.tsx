// src/pages/ForbiddenPage.tsx
import { Link } from "react-router-dom";

export default function ForbiddenPage() {
  return (
    <div className="error-page">
      <div className="error-page__code">403</div>
      <h1 className="error-page__title">Access denied</h1>
      <p className="error-page__message">
        You do not have permission to access this page. Admin role is required.
      </p>
      <div className="error-page__action">
        <Link to="/" className="btn btn--primary" style={{ display: "inline-flex", width: "auto" }}>
          Back to dashboard
        </Link>
      </div>
    </div>
  );
}
