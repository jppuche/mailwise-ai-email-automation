# Bloque 2: Auth System

## Objetivo

Implementar autenticacion JWT (python-jose) + hashing bcrypt (passlib) + refresh tokens en Redis
con dos roles (Admin, Reviewer) como claims del token, soportando login/refresh/logout/me
para la SPA React de single-tenant.

## Dependencias

- Bloque 0 (Foundation): estructura `src/`, pyproject.toml, Docker Compose operativo
- Bloque 1 (Database + Models): modelo `User` con columnas `id`, `username`, `hashed_password`,
  `role`, `is_active` definido en SQLAlchemy 2.0 y migrado via Alembic

## Archivos a crear/modificar

### Backend (backend-worker)

- `src/core/security.py` — Creacion y verificacion de JWTs (python-jose), hashing de passwords
  (passlib[bcrypt]), utilidades de extraccion de claims. Define `TokenPayload` como TypedDict.
- `src/core/config.py` — Modificar: agregar settings de auth (`JWT_SECRET_KEY`, `JWT_ACCESS_TTL_MINUTES`,
  `JWT_REFRESH_TTL_DAYS`, `BCRYPT_ROUNDS`, `CORS_ORIGINS`). Todos con carga desde env vars.
- `src/api/deps.py` — Dependencias FastAPI: `get_current_user`, `require_admin`,
  `require_reviewer_or_admin`. Encapsulan extraccion del token Bearer del header y lookup en DB.
- `src/api/routers/auth.py` — Router con cuatro endpoints: `POST /auth/login`,
  `POST /auth/refresh`, `POST /auth/logout`, `GET /auth/me`.
- `src/api/schemas/auth.py` — Modelos Pydantic: `LoginRequest`, `TokenResponse`,
  `RefreshRequest`, `UserResponse`. Sin `dict[str, Any]` en ningun campo.
- `src/adapters/redis_client.py` — Crear (si no existe): cliente Redis async (aioredis / redis-py
  asyncio) con structured try/except para ConnectionError y TimeoutError. Expone
  `set_refresh_token`, `get_refresh_token`, `delete_refresh_token`.
- `src/main.py` — Modificar: registrar router de auth y middleware CORS con origenes
  desde `settings.CORS_ORIGINS`.

### Frontend (frontend-worker)

_(Bloque 2 no crea componentes UI — solo define los endpoints que el frontend consumira en
bloques posteriores. El frontend-worker puede generar los tipos TypeScript desde el schema
OpenAPI una vez que este bloque este completo.)_

- Ninguno en este bloque.

### Tests (Inquisidor)

- `tests/unit/test_security.py` — Tests unitarios para `create_access_token`,
  `verify_access_token`, `hash_password`, `verify_password`, `create_refresh_token`.
  Sin llamadas a DB ni Redis (pure functions).
- `tests/unit/test_auth_schemas.py` — Validacion de que `LoginRequest` rechaza campos
  faltantes/tipos invalidos; que `TokenResponse` serializa correctamente.
- `tests/integration/test_auth_endpoints.py` — Tests de endpoints con `httpx.AsyncClient`
  y DB de test real (factory-boy para crear User). Cubre: login OK, login 401,
  refresh OK, refresh invalido, logout, /me con token valido e invalido,
  403 en endpoint admin para rol Reviewer.
- `tests/integration/test_redis_client.py` — Tests con Redis real (docker-compose test profile)
  para `set/get/delete_refresh_token`, expiracion de TTL, comportamiento ante Redis caido
  (mock de conexion para simular ConnectionError).

## Skills aplicables

- **tighten-types:** Todos los schemas de request/response son Pydantic `BaseModel`. El payload
  interno del JWT es `TypedDict` (`TokenPayload`) — no `dict[str, Any]`. El campo `role` usa
  el enum `UserRole` en el modelo y se serializa a string en el claim. `get_current_user`
  retorna `User` (modelo SQLAlchemy), nunca `Any`.
- **try-except:** Operaciones en Redis (set/get/delete de refresh tokens) son external-state:
  structured try/except para `redis.exceptions.ConnectionError`, `redis.exceptions.TimeoutError`.
  Decode del JWT: try/except para `jose.ExpiredSignatureError`, `jose.JWTClaimsError`,
  `jose.JWTError`. Verificacion de password: condicional (`if not verify_password(...): raise 401`)
  — no try/except (computo local).
- **pre-mortem Cat 8:** Todos los defaults load-bearing configurables via env var (ver tabla
  en seccion Criterios de exito). `JWT_SECRET_KEY` no tiene default — la app no arranca sin el.
- **contract-docstrings:** `src/adapters/redis_client.py` documenta invariantes, garantias,
  errores externos y errores silenciados (ninguno silenciado — todos re-raised como tipos propios).

## Candidate Tools

No candidate tool dependencies — exit conditions achievable without candidates.

## Criterios de exito (deterministicos)

### Calidad de codigo

- [ ] `ruff check src/` — 0 violaciones
- [ ] `ruff format src/ --check` — 0 diferencias
- [ ] `mypy src/` — 0 errores de tipo

### Defaults load-bearing (pre-mortem Cat 8)

| Default | Valor | Env Var | Verificacion |
|---------|-------|---------|--------------|
| JWT access TTL | 15 min | `JWT_ACCESS_TTL_MINUTES` | Token expirado retorna 401 en test |
| JWT refresh TTL | 7 dias | `JWT_REFRESH_TTL_DAYS` | Redis TTL seteado correctamente en test |
| bcrypt rounds | 12 | `BCRYPT_ROUNDS` | Hash de password tarda < 2s en test |
| CORS origins | `["http://localhost:5173"]` | `CORS_ORIGINS` | Header `Access-Control-Allow-Origin` presente en respuesta |
| JWT secret key | (sin default) | `JWT_SECRET_KEY` | App lanza `ValueError` / falla startup si ausente |

- [ ] Todos los defaults de la tabla estan en `src/core/config.py` cargados desde env
- [ ] `JWT_SECRET_KEY` ausente impide arranque de la app (verificado en test de config)

### Tipos (tighten-types)

- [ ] Sin `dict[str, Any]` en ningun archivo bajo `src/api/schemas/` ni `src/core/security.py`
- [ ] `UserRole` es un enum Python (no string libre) en schemas y modelo
- [ ] `TokenPayload` es `TypedDict` con campos `sub: str`, `role: str`, `exp: int`
- [ ] `get_current_user` retorna `User` (SQLAlchemy model), no `Any`

### Manejo de excepciones (try-except)

- [ ] `redis_client.py`: try/except explicito para `ConnectionError` y `TimeoutError` en cada
  operacion de Redis — sin `except Exception` desnudo
- [ ] `verify_access_token`: captura `ExpiredSignatureError`, `JWTClaimsError`, `JWTError`
  en bloques separados con mensajes de error distintos
- [ ] Verificacion de password usa condicional, no try/except

### Comportamiento funcional

- [ ] `POST /auth/login` con credenciales validas retorna `access_token` + `refresh_token` + `token_type: "bearer"`
- [ ] `POST /auth/login` con password incorrecto retorna HTTP 401
- [ ] `POST /auth/login` con usuario inexistente retorna HTTP 401 (mismo mensaje — no revelar si usuario existe)
- [ ] `POST /auth/refresh` con refresh token valido retorna nuevo `access_token`
- [ ] `POST /auth/refresh` con refresh token invalido/expirado retorna HTTP 401
- [ ] `POST /auth/logout` elimina el refresh token de Redis; un segundo uso del mismo refresh token retorna 401
- [ ] `GET /auth/me` con token valido retorna `UserResponse` del usuario autenticado
- [ ] `GET /auth/me` sin token retorna HTTP 401
- [ ] `GET /auth/me` con token expirado retorna HTTP 401
- [ ] Endpoint decorado con `require_admin` retorna HTTP 403 para rol Reviewer
- [ ] Endpoint decorado con `require_reviewer_or_admin` acepta ambos roles

### Seguridad

- [ ] Passwords nunca aparecen en logs (verificar en handler de login)
- [ ] `LoginRequest` no expone `hashed_password` en ninguna respuesta
- [ ] Refresh tokens son UUID opacos (no JWTs decodificables con informacion de usuario)

## Exit conditions para Ralph Loop

El bloque esta COMPLETO cuando TODOS los criterios de exito se cumplen.
Si CUALQUIER criterio falla, el loop itera hasta que pase.

**Orden de implementacion sugerido para minimizar re-trabajo:**
1. `src/core/config.py` (settings de auth) — base para todo lo demas
2. `src/api/schemas/auth.py` (Pydantic models) — define los contratos antes de implementar
3. `src/core/security.py` (JWT + bcrypt) — logica pura, testeable sin DB
4. `src/adapters/redis_client.py` (cliente Redis async)
5. `src/api/deps.py` (dependencias FastAPI)
6. `src/api/routers/auth.py` (endpoints)
7. `src/main.py` (registro de router + CORS)

**Stop condition:** Si un gate falla 3+ veces en el mismo error, escalar al usuario.

**Consultas requeridas antes de implementar:**
- Consultar Inquisidor para confirmar typing de `TokenPayload` (TypedDict vs dataclass)
  y firma de `get_current_user` con asyncpg session.
- Consultar Sentinel para revision de seguridad de `redis_client.py` y flujo de revocacion
  de refresh tokens.
