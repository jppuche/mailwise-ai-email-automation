// AUTO-GENERATED — DO NOT EDIT MANUALLY
// Run: npm run generate-types
// Source: http://localhost:8000/openapi.json
//
// This file is a PLACEHOLDER matching the actual backend schemas (B02/B13/B14).
// Run `npm run generate-types` with the backend live to regenerate the full spec.

export type paths = Record<string, never>;
export type webhooks = Record<string, never>;

export interface components {
  schemas: {
    /** POST /api/v1/auth/login request body */
    LoginRequest: {
      username: string;
      password: string;
    };
    /** Successful auth response: access token + refresh token */
    TokenResponse: {
      access_token: string;
      refresh_token: string;
      token_type: string;
    };
    /** POST /api/v1/auth/refresh request body */
    RefreshRequest: {
      refresh_token: string;
    };
    /** GET /api/v1/auth/me response — safe user representation */
    UserResponse: {
      id: string;
      username: string;
      role: "admin" | "reviewer";
      is_active: boolean;
    };
    HTTPValidationError: {
      detail?: components["schemas"]["ValidationError"][];
    };
    ValidationError: {
      loc: (string | number)[];
      msg: string;
      type: string;
    };
  };
  responses: never;
  parameters: never;
  requestBodies: never;
  headers: never;
  pathItems: never;
}

export type $defs = Record<string, never>;

export type external = Record<string, never>;

export type operations = Record<string, never>;
