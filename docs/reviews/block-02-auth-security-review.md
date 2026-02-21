# Block 02: Auth & Users -- Security Review

**Reviewer:** Sentinel (opus)
**Date:** 2026-02-21
**Scope:** Login flow, JWT management, Redis refresh tokens, RBAC deps, CORS, exception handling
**Verdict:** PASS with 1 WARNING, 4 SUGGESTIONS

---

## Files Reviewed

| File | Lines | Role |
|------|-------|------|
| `src/core/security.py` | 116 | JWT creation/verification, bcrypt password hashing |
| `src/adapters/redis_client.py` | 129 | Async Redis client for refresh token CRUD |
| `src/api/deps.py` | 71 | FastAPI auth dependencies (current user, RBAC) |
| `src/api/routers/auth.py` | 174 | Login, refresh, logout, me endpoints |
| `src/api/main.py` | 63 | CORS middleware, exception handlers, lifespan |
| `src/api/schemas/auth.py` | 63 | Pydantic request/response models |
| `src/core/config.py` | 61 | Settings (JWT, bcrypt, CORS, Redis) |
| `src/core/exceptions.py` | 41 | Domain exceptions (AuthenticationError, AuthorizationError) |
| `src/models/user.py` | 55 | User ORM model with UserRole enum |

---

## Dimension 1: Login Flow Security

### 1.1 User Enumeration -- PASS

**File:** `src/api/routers/auth.py` lines 53-68

The login endpoint uses a single unified check:

```python
if user is None or not verify_password(body.password, user.password_hash):
    raise HTTPException(status_code=401, detail="Invalid credentials")

if not user.is_active:
    raise HTTPException(status_code=401, detail="Invalid credentials")
```

Both nonexistent user and wrong password return identical HTTP 401 with identical detail string `"Invalid credentials"`. Inactive user also returns the same message. This prevents user enumeration via response content.

### 1.2 Timing Oracle -- WARNING-B02-01

**Severity:** WARNING
**File:** `src/api/routers/auth.py` lines 53-56

```python
if user is None or not verify_password(body.password, user.password_hash):
```

Python short-circuit evaluation means: when `user is None`, `verify_password()` is **never called**. The response for a nonexistent user returns in microseconds (DB lookup only), while a wrong-password response takes ~300ms (bcrypt with 12 rounds). An attacker can distinguish these two cases by measuring response time, enabling user enumeration via timing side-channel.

**Recommendation:** When `user is None`, perform a dummy `bcrypt.checkpw()` against a pre-computed hash to equalize response time:

```python
_DUMMY_HASH = bcrypt.hashpw(b"dummy", bcrypt.gensalt(rounds=12)).decode("utf-8")

# In login:
if user is None:
    verify_password("dummy", _DUMMY_HASH)  # constant-time dummy check
    raise HTTPException(status_code=401, detail="Invalid credentials")
if not verify_password(body.password, user.password_hash):
    raise HTTPException(status_code=401, detail="Invalid credentials")
```

**Mitigation context:** Single-tenant system with no public registration reduces practical risk. Upgrading to SUGGESTION would be reasonable if rate limiting is confirmed in place (currently planned for future blocks per D18).

### 1.3 Password Handling -- PASS

- `hash_password()` uses `bcrypt` directly (not deprecated passlib). Correct decision documented in docstring.
- `bcrypt_rounds` configurable via `BCRYPT_ROUNDS` env var (default 12). Compliant with D14.
- `verify_password()` is pure local computation with conditional return (no try/except). Compliant with D8.
- `LoginRequest.password` has `min_length=1` -- no empty password bypass.
- No password appears in any `logger.*` call. All log entries reference `username` or `user_id` only.

### 1.4 Password Max Length -- SUGGESTION-B02-01

**Severity:** SUGGESTION
**File:** `src/api/schemas/auth.py` line 23

```python
password: str = Field(..., min_length=1)
```

No `max_length` on password field. bcrypt has a 72-byte input limit (silently truncates beyond that). While not a vulnerability per se, extremely long passwords (megabytes) could be used for slow-hash DoS. A `max_length=128` on the schema would prevent this at the validation layer.

---

## Dimension 2: JWT Token Management

### 2.1 Secret Key -- PASS

**File:** `src/core/config.py` lines 16-18

```python
jwt_secret_key: str = Field(
    ..., description="Secret key for JWT signing — MUST be set in production"
)
```

No default value (`...` = required). Application will fail to start without `JWT_SECRET_KEY` in environment. This is correct fail-fast behavior per D14.

### 2.2 Algorithm -- PASS

**File:** `src/core/config.py` line 19, `src/core/security.py` lines 75, 90

- Default algorithm is `HS256`. Configurable via `JWT_ALGORITHM` env var.
- `jwt.decode()` uses `algorithms=[settings.jwt_algorithm]` (list, not string). This prevents algorithm confusion attacks where an attacker submits a token with `alg: none`.
- Single algorithm in the list prevents algorithm substitution.

### 2.3 Claims Validation -- PASS

**File:** `src/core/security.py` lines 86-106

```python
try:
    decoded = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
except ExpiredSignatureError:
    raise AuthenticationError("Token has expired") from None
except JWTClaimsError:
    raise AuthenticationError("Invalid token claims") from None
except JWTError:
    raise AuthenticationError("Invalid token") from None

if "sub" not in decoded or "role" not in decoded:
    raise AuthenticationError("Token missing required claims")
```

- Three specific exception catches in correct precedence order (specific to general).
- Post-decode validation checks for required claims `sub` and `role`.
- All failures raise `AuthenticationError` (mapped to 401 at app level).
- `from None` suppresses exception chaining, preventing internal details from leaking.

### 2.4 Token Payload Type Safety -- PASS

**File:** `src/core/security.py` lines 25-36

`TokenPayload` is a `TypedDict` with `sub: str`, `role: str`, `exp: int`. No `dict[str, Any]`. Compliant with D1.

### 2.5 JWT Algorithm Configurability -- SUGGESTION-B02-02

**Severity:** SUGGESTION
**File:** `src/core/config.py` line 19

```python
jwt_algorithm: str = Field(default="HS256")
```

The algorithm is a free-form string. An operator could misconfigure this to `none` or an asymmetric algorithm without a corresponding key pair. Consider constraining to a `Literal["HS256", "HS384", "HS512"]` type or validating at startup.

---

## Dimension 3: Redis Refresh Token Security

### 3.1 Opaque Tokens -- PASS

**File:** `src/core/security.py` lines 109-115

```python
def create_refresh_token() -> str:
    return str(uuid.uuid4())
```

Refresh tokens are UUID4 strings. Not JWTs, no decodable user information. Compliant with B02 spec and SCRATCHPAD standing decision.

### 3.2 Key Namespace -- PASS

**File:** `src/adapters/redis_client.py` line 22

```python
_REFRESH_KEY_PREFIX = "refresh:"
```

All refresh token keys use `refresh:` prefix, preventing collision with other Redis keys (Celery broker in Redis/0 per B12 spec, though refresh tokens should ideally be in a separate Redis DB).

### 3.3 TTL Enforcement -- PASS

**File:** `src/adapters/redis_client.py` lines 66-71

```python
days = ttl_days if ttl_days is not None else settings.jwt_refresh_ttl_days
key = f"{_REFRESH_KEY_PREFIX}{token}"
client = await _get_redis()
await client.setex(key, timedelta(days=days), user_id)
```

Uses `setex` (atomic set with expiry). TTL is always set -- no path where a refresh token persists without expiration. Default 7 days, configurable via `JWT_REFRESH_TTL_DAYS`. Compliant with D14.

### 3.4 Token Rotation -- PASS

**File:** `src/api/routers/auth.py` lines 124-142

```python
# Rotate: delete old, create new
with contextlib.suppress(RedisClientError):
    await delete_refresh_token(body.refresh_token)

new_access_token = create_access_token(user.id, user.role.value)
new_refresh_token = create_refresh_token()

await set_refresh_token(new_refresh_token, str(user.id))
```

Old refresh token is deleted before new one is stored. Token rotation is implemented correctly. If old-token deletion fails (suppressed RedisClientError), the new token is still issued -- this is acceptable because the old token will eventually expire via TTL.

### 3.5 Refresh Token Theft Detection -- SUGGESTION-B02-03

**Severity:** SUGGESTION

The current rotation scheme deletes the old token and issues a new one. If an attacker steals and uses a refresh token before the legitimate user does, the legitimate user's next refresh attempt will fail (token not found). However, the system does not detect this situation or alert the user.

For a single-tenant system this is low risk. In a multi-tenant future, consider token family tracking (each refresh chain shares a family ID; reuse of an old token in the family invalidates all tokens in that family).

### 3.6 Redis DB Isolation -- INFO-B02-01

**Severity:** INFO
**File:** `src/core/config.py` line 13

```python
redis_url: str = Field(default="redis://redis:6379/0")
```

Refresh tokens share Redis DB 0 with Celery broker (per B12 spec: "Broker Redis/0, backend Redis/1"). The key prefix `refresh:` provides logical separation, but a Celery `FLUSHDB` or similar operation could accidentally purge all refresh tokens.

B12 spec documents this as intentional (broker Redis/0, backend Redis/1). Refresh tokens in DB 0 with broker is acceptable if Celery never issues `FLUSHDB`. Worth noting for operational awareness.

---

## Dimension 4: RBAC Dependencies

### 4.1 HTTPBearer(auto_error=False) -- PASS

**File:** `src/api/deps.py` line 18

```python
_bearer_scheme = HTTPBearer(auto_error=False)
```

`auto_error=False` prevents FastAPI from raising its default 403 for missing credentials. The custom `get_current_user` raises `AuthenticationError` (mapped to 401) instead. This is the correct pattern per the spec.

### 4.2 User Lookup After Token Verification -- PASS

**File:** `src/api/deps.py` lines 35-44

```python
payload: TokenPayload = verify_access_token(credentials.credentials)

result = await db.execute(select(User).where(User.id == payload["sub"]))
user = result.scalar_one_or_none()

if user is None:
    raise AuthenticationError("User not found")

if not user.is_active:
    raise AuthenticationError("User account is disabled")
```

After JWT verification, the user is loaded from DB and checked for existence and active status. This means:
- Deleted users cannot access the API even with a valid token.
- Deactivated users are immediately locked out (within token TTL).
- Role is checked against current DB state, not stale JWT claims.

Note: The role check in `require_admin` and `require_reviewer_or_admin` uses `current_user.role` from DB, not from the JWT `role` claim. This is correct -- the JWT role claim is available but the authoritative source is the DB.

### 4.3 Role Enforcement -- PASS

**File:** `src/api/deps.py` lines 49-69

```python
if current_user.role != UserRole.ADMIN:
    raise AuthorizationError("Admin access required")

if current_user.role not in (UserRole.ADMIN, UserRole.REVIEWER):
    raise AuthorizationError("Reviewer or Admin access required")
```

- Uses `UserRole` enum comparison (not string comparison). Compliant with D11.
- `AuthorizationError` mapped to 403 in exception handlers.
- Two-role system (ADMIN, REVIEWER) is simple and complete. No role hierarchy bugs possible with explicit checks.

### 4.4 Logout Requires Authentication -- PASS

**File:** `src/api/routers/auth.py` lines 146-162

```python
async def logout(
    body: RefreshRequest,
    _current_user: User = Depends(get_current_user),
) -> None:
```

Logout requires a valid access token. An unauthenticated caller cannot revoke arbitrary refresh tokens. The `_current_user` parameter is unused (underscore prefix) but enforces authentication.

Note: The logout endpoint does not verify that the refresh token being deleted belongs to the authenticated user. In a single-tenant system with 2 roles this is acceptable -- any authenticated user can only know their own refresh token. In a multi-tenant system, this would need ownership verification.

---

## Dimension 5: CORS Middleware

### 5.1 Origin Configuration -- PASS

**File:** `src/core/config.py` line 25, `src/api/main.py` lines 29-36

```python
cors_origins: list[str] = Field(default=["http://localhost:5173"])

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

- Origins loaded from config, not hardcoded in middleware. Compliant with B13/B19 directives.
- Default is `["http://localhost:5173"]` (Vite dev server). Reasonable for development.
- `allow_credentials=True` is required for cookie-based refresh tokens (B15 plans httpOnly cookies on frontend).

### 5.2 CORS Default Value -- SUGGESTION-B02-04

**Severity:** SUGGESTION
**File:** `src/core/config.py` line 25

```python
cors_origins: list[str] = Field(default=["http://localhost:5173"])
```

B19 spec states: "`CORS_ORIGINS` no default (fail-fast)". The current implementation has a default. This contradicts the B19 directive. However, B19 is a future block and this default is reasonable for development. When B19 is implemented, this should be changed to `Field(...)` (required, no default) for production safety.

---

## Dimension 6: Exception Handling / Information Leakage

### 6.1 Exception Handlers -- PASS

**File:** `src/api/main.py` lines 40-53

```python
@app.exception_handler(AuthenticationError)
async def authentication_error_handler(request: Request, exc: AuthenticationError) -> JSONResponse:
    return JSONResponse(status_code=401, content={"detail": str(exc)})

@app.exception_handler(AuthorizationError)
async def authorization_error_handler(request: Request, exc: AuthorizationError) -> JSONResponse:
    return JSONResponse(status_code=403, content={"detail": str(exc)})
```

Domain exceptions are mapped to HTTP status codes at the app level. The `str(exc)` messages are controlled strings set by the codebase (e.g., "Token has expired", "Admin access required"), not raw exception messages from third-party libraries. No stack traces or internal details leak.

### 6.2 Redis Error Handling -- PASS

**File:** `src/api/routers/auth.py` lines 73-80, 98-105, 131-138, 155-162

All Redis failures return HTTP 503 with generic message `"Authentication service temporarily unavailable"`. No Redis connection strings, error details, or stack traces leak to the client. The original error is logged server-side only (`logger.error`).

### 6.3 Log Safety -- PASS

Audit of all `logger.*` calls in `src/api/routers/auth.py`:

| Line | Call | Fields Logged | Sensitive Data? |
|------|------|---------------|-----------------|
| 57 | `logger.warning("login_failed", username=...)` | username | No (public identifier) |
| 64 | `logger.warning("login_inactive_user", username=...)` | username | No |
| 76 | `logger.error("redis_store_refresh_failed", user_id=...)` | user_id (UUID) | No |
| 82 | `logger.info("login_success", user_id=...)` | user_id (UUID) | No |
| 101 | `logger.error("redis_get_refresh_failed")` | (none) | No |
| 134 | `logger.error("redis_store_refresh_failed", user_id=...)` | user_id (UUID) | No |
| 158 | `logger.error("redis_delete_refresh_failed")` | (none) | No |

No passwords, tokens, or hashes in any log statement. Compliant with D17.

### 6.4 Suppressed Errors in Refresh -- PASS (with note)

**File:** `src/api/routers/auth.py` lines 117, 125

```python
with contextlib.suppress(RedisClientError):
    await delete_refresh_token(body.refresh_token)
```

Two uses of `contextlib.suppress` for old-token deletion during rotation. These are intentional: if we cannot delete the old token, the operation should still proceed (old token will expire via TTL). The contract docstring in `redis_client.py` explicitly states "Errors silenced: None" -- the suppression happens at the caller level (auth.py), not in the adapter itself. This is architecturally correct.

---

## Dimension 7: Data Contract Validation

### 7.1 Schema Completeness -- PASS

- `LoginRequest`: typed fields, no `Any`, min/max length constraints.
- `TokenResponse`: explicit fields, `token_type` default "bearer".
- `RefreshRequest`: `min_length=1` prevents empty string.
- `UserResponse`: `from_attributes=True` for ORM mode. Excludes `password_hash` by only declaring safe fields (`id`, `username`, `role`, `is_active`).

### 7.2 UserRole Enum -- PASS

`UserRole` is imported from `src/models/user.py` into schemas. Single source of truth. No string-literal role values in schemas. Compliant with D11.

---

## Compliance Matrix

| Directive | Status | Notes |
|-----------|--------|-------|
| D1 (tighten-types) | PASS | TokenPayload=TypedDict, no dict[str,Any], get_current_user returns User |
| D5 (contract-docstrings) | PASS | redis_client.py has full contract: invariants, guarantees, errors |
| D7 (try-except) | PASS | Specific exception types, structured catches, no bare except |
| D8 (local computation) | PASS | verify_password uses conditional, not try/except |
| D11 (stringly-typed) | PASS | UserRole enum throughout, no free-form role strings |
| D14 (load-bearing defaults) | PASS | JWT TTL, bcrypt rounds, CORS origins all configurable via env |
| D17 (PII in logs) | PASS | No passwords/tokens in logs, user_id only |
| D18 (single-tenant security) | PASS | CORS + input validation sufficient for current phase |

---

## Findings Summary

| ID | Severity | Component | Finding |
|----|----------|-----------|---------|
| WARNING-B02-01 | WARNING | auth.py login | Timing oracle: bcrypt not called for nonexistent users, enabling user enumeration via response time measurement |
| SUGGESTION-B02-01 | SUGGESTION | schemas/auth.py | No max_length on password field; bcrypt truncates at 72 bytes; potential slow-hash DoS with very long inputs |
| SUGGESTION-B02-02 | SUGGESTION | config.py | jwt_algorithm is free-form string; could be misconfigured to "none" or asymmetric algorithm |
| SUGGESTION-B02-03 | SUGGESTION | auth.py refresh | No refresh token family tracking for theft detection (acceptable for single-tenant) |
| SUGGESTION-B02-04 | SUGGESTION | config.py | CORS default contradicts B19 "no default" directive (acceptable until B19 implementation) |
| INFO-B02-01 | INFO | redis_client.py | Refresh tokens share Redis DB 0 with Celery broker; prefix separation only |

---

## Pre-existing Findings (carry forward)

The SCRATCHPAD import bug (line 130-135) regarding `from jose import JWTClaimsError` has been fixed -- the current code at line 19 shows:

```python
from jose.exceptions import JWTClaimsError
```

This is the correct import path. Finding resolved.

---

## Verdict

**PASS.** The auth system is well-designed with strong security fundamentals. The timing oracle (WARNING-B02-01) is the only finding above SUGGESTION level, and its practical exploitability is limited in a single-tenant system -- especially once rate limiting is added in future blocks. All spec-mandated security invariants are verified:

- Same 401 for wrong password AND nonexistent user (content-level)
- Passwords never in logs
- Refresh tokens are opaque UUIDs, not JWTs
- Token rotation on /refresh
- bcrypt used directly (not passlib)
- HTTPBearer(auto_error=False) for custom 401

No CRITICAL findings. No implementation changes required to proceed to Block 03.
