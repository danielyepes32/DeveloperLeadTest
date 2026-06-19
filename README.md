# Procurement — Solicitudes de Producto y Ofertas de Proveedores

API para gestionar **solicitudes de productos** entre clientes y proveedores, con un
flujo de **negociación turn-based** (oferta → contraoferta → aceptar/rechazar) modelado
como **máquina de estados**. Incluye autenticación **JWT + RBAC**, e idempotencia,
observabilidad, trazabilidad y persistencia horneadas en el diseño.

> Prueba técnica para el cargo de **Líder de Desarrollo**. El componente implementado a
> fondo es el **flujo de negociación + autenticación/autorización**.

## Stack

| Capa | Tecnología |
|------|-----------|
| API | Python 3.12 · FastAPI · Pydantic v2 |
| Persistencia | PostgreSQL 16 · SQLAlchemy 2.0 |
| Seguridad | JWT (PyJWT, HS256) · bcrypt · RBAC por dependencias |
| Frontend | HTML + JavaScript vanilla (servido por la API) |
| Observabilidad | Logs JSON · `X-Request-ID` · Prometheus `/metrics` |
| Dependencias | **uv** (`pyproject.toml` + `uv.lock`) |
| Entrega | Docker multi-stage (uv) · Docker Compose · GitHub Actions · pytest |

La documentación de arquitectura, justificación técnica (punto 3) y gestión de equipo
(punto 4) está en **[`Arquitectura/`](Arquitectura/)**.

---

## Cómo ejecutar (recomendado: Docker)

Requisitos: Docker + Docker Compose.

```bash
docker compose up --build
```

Esto levanta dos servicios — `api` y `db` (Postgres) — con healthchecks. Cuando estén
arriba:

- **Aplicación web:** http://localhost:8000  (UI que ejerce el flujo completo)
- **Documentación OpenAPI (Swagger):** http://localhost:8000/docs
- **Health / Readiness:** http://localhost:8000/health · http://localhost:8000/ready
- **Métricas Prometheus:** http://localhost:8000/metrics

Para detener y limpiar:

```bash
docker compose down -v
```

### Modo desarrollo (hot reload, sin rebuilds)

Para iterar rápido sobre el código sin reconstruir la imagen — el código se monta
y `uvicorn --reload` reinicia ante cada cambio:

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up   # o: make dev
```

> El `Dockerfile` usa **uv** con la capa de dependencias cacheada: un rebuild tras un
> cambio de código toma ~5s (vs ~30s en frío), porque solo se reconstruye la capa del
> código de la app.

### Variables de entorno

Copia `.env.example` a `.env` y ajusta. En producción **genera un secreto fuerte**:

```bash
openssl rand -hex 32   # usar como JWT_SECRET
```

## Cómo ejecutar las pruebas

Los tests corren contra **SQLite en memoria** (rápidos, sin servicios externos).
Con [uv](https://docs.astral.sh/uv/) instalado:

```bash
uv sync            # instala dependencias (crea .venv)
uv run ruff check .
uv run pytest
```

o vía Makefile:

```bash
make install   # uv sync
make lint      # uv run ruff check .
make test      # uv run pytest
```

---

## Modelo de dominio (máquina de estados)

```
Cliente crea ProductRequest (open)
        │
Proveedor envía Offer ──► abre Negotiation (active) + Proposal(offer)
        │
   ┌────┴─ la contraparte de la última propuesta responde ─┐
   │                                                        │
 counter (nueva Proposal, sigue active)            accept ──► accepted  (request → closed,
   │                                                │          hermanas → rejected)
   └────────────────────────────────────────────►  reject ──► rejected
```

Reglas (validadas en la capa de dominio, ver `app/services/negotiation.py`):

- Solo el **cliente dueño** y el **proveedor** participan en su negociación.
- En una negociación `active`, **solo la contraparte de la última propuesta** puede
  responder — no puedes responder tu propia propuesta (→ `409`).
- `accept/reject/counter` son ilegales sobre una negociación terminal (→ `409`).
- Aceptar una oferta **cierra** la solicitud y **descarta** las negociaciones hermanas.

## Endpoints

| Método | Ruta | Rol | Descripción |
|--------|------|-----|-------------|
| POST | `/auth/register` | — | Registrar cliente o proveedor |
| POST | `/auth/login` | — | Obtener JWT |
| GET | `/auth/me` | auth | Usuario actual |
| POST | `/requests` | client | Crear solicitud |
| GET | `/requests` | auth | Listar (cliente: propias · proveedor: abiertas) |
| GET | `/requests/{id}` | auth | Detalle |
| POST | `/requests/{id}/offers` | supplier | Ofertar (abre negociación) |
| GET | `/negotiations` | auth | Listar mis negociaciones |
| GET | `/negotiations/{id}` | participante | Detalle + historial de propuestas |
| POST | `/negotiations/{id}/accept` | participante | Aceptar la última propuesta |
| POST | `/negotiations/{id}/reject` | participante | Rechazar |
| POST | `/negotiations/{id}/counter` | participante | Contraofertar |

Los `POST` mutantes aceptan el header **`Idempotency-Key`**: un reintento con la misma
clave devuelve la respuesta original sin duplicar el efecto.

### Ejemplo (curl)

```bash
B=http://localhost:8000
# registro + login
curl -s $B/auth/register -d '{"email":"buyer@acme.com","password":"password123","full_name":"Buyer","role":"client"}'   -H 'Content-Type: application/json'
curl -s $B/auth/register -d '{"email":"seller@acme.com","password":"password123","full_name":"Seller","role":"supplier"}' -H 'Content-Type: application/json'
BUYER=$(curl -s $B/auth/login  -d '{"email":"buyer@acme.com","password":"password123"}'  -H 'Content-Type: application/json' | jq -r .access_token)
SELLER=$(curl -s $B/auth/login -d '{"email":"seller@acme.com","password":"password123"}' -H 'Content-Type: application/json' | jq -r .access_token)
# solicitud -> oferta -> contraoferta -> aceptar
RID=$(curl -s $B/requests -H "Authorization: Bearer $BUYER" -H 'Content-Type: application/json' -d '{"product_name":"Servers","quantity":4}' | jq -r .id)
NID=$(curl -s $B/requests/$RID/offers -H "Authorization: Bearer $SELLER" -H 'Content-Type: application/json' -d '{"amount":9000000,"currency":"COP"}' | jq -r .id)
curl -s -X POST $B/negotiations/$NID/counter -H "Authorization: Bearer $BUYER"  -H 'Content-Type: application/json' -d '{"amount":7500000}'
curl -s -X POST $B/negotiations/$NID/accept  -H "Authorization: Bearer $SELLER" -H 'Idempotency-Key: accept-1'
```

---

## Preocupaciones de producción

| Concern | Implementación |
|---------|----------------|
| **Idempotencia** | Header `Idempotency-Key` → tabla `idempotency_keys`; el reintento devuelve la respuesta cacheada (`app/deps.py`, `app/routers/_helpers.py`). |
| **Observabilidad** | Logs JSON estructurados; middleware que asigna/propaga `X-Request-ID`; métricas Prometheus en `/metrics`; probes `/health` y `/ready`. |
| **Trazabilidad** | Tabla `audit_log` con cada transición (actor, acción, entidad, `request_id` de correlación); historial `proposals` append-only. |
| **Persistencia** | PostgreSQL + SQLAlchemy. El esquema se bootstrapea con `create_all`; en producción se gestionaría con **migraciones Alembic** (ver `Arquitectura/Justificación.md`). |
| **Seguridad** | JWT + bcrypt, RBAC por dependencias, validación con Pydantic, ORM parametrizado (anti-inyección), secretos por entorno, contenedor non-root. |
| **Transacciones** | Bloqueo pesimista (`SELECT … FOR UPDATE`) en accept/reject/counter/offer → sin doble-aceptación ni *lost updates*; transición + auditoría atómicas. |
| **Hardening** | Fail-fast si `JWT_SECRET` inseguro en producción · rate limit en `/auth/login` · security headers · CORS configurable. |
| **Escalabilidad** | Paginación (`limit`/`offset`) en listados; índices en FKs/estados. |

## Estructura del proyecto

```
app/
  main.py            # wiring: middleware, manejo de errores, métricas, SPA
  config.py          # settings 12-factor (env)
  database.py        # engine + sesión (Postgres / SQLite en tests)
  security.py        # bcrypt + JWT
  middleware.py      # correlation id + access logging
  logging_config.py  # formato JSON + contextvar request_id
  deps.py            # auth, RBAC (require_role), idempotencia
  errors.py          # errores de dominio -> HTTP
  models.py          # ORM (User, ProductRequest, Negotiation, Proposal, AuditLog, ...)
  schemas.py         # contratos Pydantic
  services/          # lógica de dominio (negotiation = máquina de estados, users, audit)
  routers/           # auth, requests, negotiations, health
  static/            # frontend (HTML + JS)
tests/               # pytest (auth, flujo de negociación, idempotencia)
Arquitectura/        # diagramas + Justificación.md + gestión de equipo.md
pyproject.toml · uv.lock          # dependencias (uv)
Dockerfile · docker-compose.yml · docker-compose.dev.yml
.github/workflows/ci.yml · Makefile
```

## CI

`/.github/workflows/ci.yml`: lint (ruff) → tests (pytest) → build de la imagen Docker
en cada push/PR.
```
