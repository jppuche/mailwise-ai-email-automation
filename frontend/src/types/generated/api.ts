// AUTO-GENERATED — DO NOT EDIT MANUALLY
// Run: npm run generate-types
// Source: http://localhost:8000/openapi.json
//
// This file is a PLACEHOLDER until the backend is running.
// Run `npm run generate-types` with the backend live to regenerate.

export type paths = Record<string, never>;
export type webhooks = Record<string, never>;

export interface components {
  schemas: {
    LoginRequest: {
      email: string;
      password: string;
    };
    LoginResponse: {
      access_token: string;
      token_type: string;
      expires_in: number;
      user: components["schemas"]["UserInfo"];
    };
    RefreshResponse: {
      access_token: string;
      token_type: string;
      expires_in: number;
      user: components["schemas"]["UserInfo"];
    };
    UserInfo: {
      id: string;
      email: string;
      role: "Admin" | "Reviewer";
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
