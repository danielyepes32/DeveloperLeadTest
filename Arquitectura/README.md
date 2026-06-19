# Arquitectura — Solicitudes de Producto y Ofertas de Proveedores

> Documentación de arquitectura de la prueba técnica. Autor: Líder Técnico.
> Stack: **Python 3.12 · FastAPI · SQLAlchemy 2.0 · Pydantic v2 · PostgreSQL 16**.

## Índice

| # | Documento | Contenido |
|---|-----------|-----------|
| 1 | [README.md](./README.md) | Resumen ejecutivo y visión general (este documento) |
| 2 | [diagrama-contexto.md](./diagrama-contexto.md) | Diagrama de contexto y de componentes (Mermaid) |
| 3 | [modelo-datos.md](./modelo-datos.md) | Modelo entidad-relación (Mermaid `erDiagram`) |
| 4 | [maquina-estados.md](./maquina-estados.md) | Máquinas de estados de `ProductRequest` y `Negotiation` |
| 5 | [diagrama-secuencia.md](./diagrama-secuencia.md) | Ciclo completo de negociación (Mermaid `sequenceDiagram`) |
| 6 | [Justificación.md](./Justificación.md) | Punto 3: estructura, seguridad y escalabilidad |
| 7 | [gestión de equipo.md](./gestión%20de%20equipo.md) | Punto 4: liderazgo, sprints, revisión de código y CI/CD |

---

## 1. Visión

El sistema modela una **negociación turn-based** entre clientes y proveedores:

1. Un **cliente** publica una **solicitud de producto** (`ProductRequest`).
2. Un **proveedor** responde con una **oferta** de precio, abriendo un **hilo de negociación** (`Negotiation`).
3. El cliente puede **aceptar**, **rechazar** o **contraofertar**; el proveedor puede a su vez **re-contraofertar**.
4. La negociación es una **máquina de estados**: en cada turno solo la **contraparte de la última propuesta** puede actuar, hasta llegar a un estado terminal (`accepted` / `rejected`).

El historial de propuestas (`Proposal`) es **append-only e inmutable**, lo que produce una auditoría natural de toda la negociación.

## 2. Estilo arquitectónico

**Monolito modular en capas** (layered, con un toque de DDD ligero). El flujo de una petición atraviesa tres capas con responsabilidades estrictas:

```
HTTP  →  Routers (FastAPI)  →  Services (dominio)  →  Models / Persistencia (SQLAlchemy)  →  PostgreSQL
         · validación I/O        · reglas de negocio    · mapeo ORM, transacciones
         · auth + RBAC           · máquina de estados    · esquema relacional
         · serialización         · guardas de dominio
```

- **Routers**: traducen HTTP a llamadas de dominio. Resuelven autenticación (JWT), autorización (RBAC por dependencias) y validación de entrada/salida (Pydantic v2). **No** contienen lógica de negocio.
- **Services**: corazón del sistema. Implementan la máquina de estados de la negociación, las guardas de turno y las invariantes. Mapean errores de dominio a códigos HTTP (400/403/404/409). Son **agnósticos a HTTP** y unitariamente testeables.
- **Models / Persistencia**: entidades SQLAlchemy 2.0, sesión transaccional por request y esquema relacional con restricciones de integridad (unicidad, claves foráneas).

### ¿Por qué un monolito modular y no microservicios?

Para el alcance de esta prueba —un único *bounded context* de negociación— un monolito modular maximiza la **velocidad de entrega**, simplifica las **transacciones atómicas** (una sola base de datos, sin necesidad de sagas ni consistencia eventual) y reduce el coste operativo. La **modularidad interna** (separación routers/servicios/persistencia) preserva la opción de extraer microservicios el día que un contexto justifique despliegue y escalado independientes. El razonamiento completo y los criterios de migración están en [Justificación.md](./Justificación.md).

## 3. Preocupaciones de producción horneadas en el diseño

| Preocupación | Mecanismo |
|--------------|-----------|
| **Idempotencia** | Header `Idempotency-Key` en todos los POST mutantes; tabla `idempotency_keys` (key → respuesta); los reintentos devuelven la respuesta cacheada y evitan ofertas/decisiones duplicadas. |
| **Observabilidad** | Logs estructurados en JSON; middleware que asigna `X-Request-ID` (correlation id) propagado por `contextvar`; logging de inicio/fin con latencia y status; `/metrics` (Prometheus), `/health` (liveness) y `/ready` (readiness con chequeo de DB). |
| **Trazabilidad** | Tabla `audit_log` con cada transición de estado (actor, acción, entidad, detalle JSON, `request_id`, timestamp); historial de `proposals` inmutable y append-only. |
| **Persistencia** | PostgreSQL 16 + SQLAlchemy 2.0. En el ejercicio el esquema se inicializa con `metadata.create_all`; en producción se gestionaría con **migraciones Alembic** (versionadas, revisables y reversibles). |

## 4. Seguridad (resumen)

JWT (HS256) + hashing **bcrypt** + **RBAC** con roles `CLIENT` y `SUPPLIER` aplicados por dependencias de FastAPI. Validación estricta con Pydantic v2, ORM parametrizado contra inyección SQL, secretos por variables de entorno y auditoría completa. Detalle en [Justificación.md](./Justificación.md).

## 5. Entorno prod-like

- **Dockerfile multi-stage** (build de dependencias → imagen runtime ligera).
- **docker-compose**: servicios `api` + `db` (PostgreSQL con `healthcheck`).
- **CI (GitHub Actions)**: `ruff` (lint) → `pytest` → build de imagen.
- **Tests**: `pytest` con SQLite en memoria para velocidad; PostgreSQL en runtime real.

## 6. Frontend

Página estática ligera en **HTML + JavaScript vanilla** servida por FastAPI vía `StaticFiles`, que ejerce el flujo de extremo a extremo. Demuestra los dos lenguajes del cargo (Python + JavaScript) sin introducir un framework de frontend que no aporta al objetivo de la prueba.

## 7. Endpoints

| Método | Ruta | Rol | Descripción |
|--------|------|-----|-------------|
| `POST` | `/auth/register` | — | Registro de usuario |
| `POST` | `/auth/login` | — | Login, devuelve JWT bearer |
| `POST` | `/requests` | CLIENT | Crear solicitud de producto |
| `GET` | `/requests` | auth | Listar solicitudes |
| `GET` | `/requests/{id}` | auth | Detalle de solicitud |
| `POST` | `/requests/{id}/offers` | SUPPLIER | Enviar oferta (abre negociación) |
| `GET` | `/negotiations` | auth | Listar negociaciones del usuario |
| `GET` | `/negotiations/{id}` | auth | Detalle de negociación |
| `POST` | `/negotiations/{id}/accept` | contraparte | Aceptar última propuesta |
| `POST` | `/negotiations/{id}/reject` | contraparte | Rechazar negociación |
| `POST` | `/negotiations/{id}/counter` | contraparte | Contraofertar |
| `GET` | `/health` | — | Liveness |
| `GET` | `/ready` | — | Readiness (chequeo de DB) |
| `GET` | `/metrics` | — | Métricas Prometheus |
