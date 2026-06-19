# Justificación (Punto 3)

Este documento responde las tres preguntas del Punto 3 de la prueba: **(A) por qué esta estructura arquitectónica**, **(B) cómo se maneja la seguridad de las transacciones** y **(C) cómo escalaría el sistema**. Cierra con una **tabla de decisiones** que resume cada elección frente a sus alternativas.

---

## A. ¿Por qué esta estructura arquitectónica?

### La decisión: monolito modular en capas

Adoptamos un **monolito modular en capas** con un toque de **DDD ligero**. El sistema se organiza en tres capas de responsabilidad estricta:

```
Routers (FastAPI)  →  Services (dominio)  →  Models / Persistencia (SQLAlchemy)
```

- **Routers**: solo HTTP. Autenticación, RBAC, validación I/O (Pydantic), serialización y mapeo de errores de dominio a códigos HTTP. **Cero lógica de negocio.**
- **Services**: el dominio. Implementan la máquina de estados, las guardas de turno y las invariantes. Son **agnósticos a HTTP**, lo que los hace unitariamente testeables sin levantar un servidor.
- **Persistencia**: entidades SQLAlchemy, sesión transaccional por request, esquema relacional con restricciones de integridad.

### Trade-offs: monolito modular vs. microservicios

| Criterio | Monolito modular (elegido) | Microservicios |
|----------|----------------------------|----------------|
| **Consistencia transaccional** | Una sola DB → **transacciones ACID locales**, atómicas y simples | Consistencia eventual, sagas, compensaciones |
| **Velocidad de entrega** | Alta: un solo despliegue, un solo repositorio | Baja al inicio: orquestación, contratos, infra |
| **Coste operativo** | Bajo: un proceso, un pipeline | Alto: malla de servicios, observabilidad distribuida |
| **Acoplamiento del dominio** | Adecuado: **un único bounded context** (negociación) | Sobreingeniería para un solo contexto |
| **Escalado** | Horizontal del monolito stateless (suficiente aquí) | Granular por servicio (innecesario hoy) |
| **Complejidad de depuración** | Baja: una traza local | Alta: trazas distribuidas obligatorias |

Para un sistema con **un solo bounded context** —la negociación— y con la necesidad de **transacciones atómicas** (aceptar una oferta cierra la solicitud y supersede a las demás en un único commit), el monolito modular es la elección correcta: entrega más rápido, es más fácil de razonar y evita la complejidad accidental de la consistencia distribuida.

### ¿Cuándo migraríamos a microservicios?

La **modularidad interna** preserva la opción. Extraeríamos un servicio cuando un bounded context muestre **fuerzas reales de separación**, no antes:

1. **Escalado divergente**: un contexto (p. ej. notificaciones, búsqueda, reporting) necesita escalar o desplegarse a un ritmo muy distinto del núcleo de negociación.
2. **Aislamiento de fallos**: un componente pesado o inestable amenaza la disponibilidad del flujo crítico.
3. **Autonomía de equipos**: varios equipos pisan el mismo código y el coste de coordinación supera el coste operativo de separar.
4. **Requisitos tecnológicos distintos**: un contexto requiere otro lenguaje, otra base de datos o un modelo de datos incompatible.

Candidatos naturales a extraerse primero: **notificaciones** (asíncrono por naturaleza), **reporting/analytics** (read-heavy, puede vivir sobre read-replicas) y **auth** si crece a SSO/federación. El núcleo de negociación se mantendría monolítico mientras la consistencia transaccional siga siendo su prioridad.

### DDD ligero y separación de responsabilidades

- El **lenguaje ubicuo** del dominio (solicitud, negociación, propuesta, oferta, contraoferta, supersedido) está reflejado 1:1 en entidades y servicios.
- La **máquina de estados** vive en `NegotiationService`, no esparcida por routers ni triggers de base de datos. Hay **una sola fuente de verdad** para las reglas de turno.
- La separación routers/servicios/persistencia permite **testear el dominio en aislamiento**, **sustituir la capa HTTP** sin tocar reglas y **cambiar la persistencia** (de SQLite en tests a PostgreSQL en runtime) sin reescribir el dominio.

---

## B. ¿Cómo se maneja la seguridad de las transacciones?

La seguridad se aborda en **defensa en profundidad**: varias capas independientes, de modo que un fallo en una no compromete el sistema.

### 1. Autenticación — JWT (HS256) + bcrypt
- Las contraseñas se almacenan con **hashing bcrypt** (con salt y factor de coste), nunca en texto plano. bcrypt es deliberadamente lento para resistir fuerza bruta.
- El login emite un **JWT firmado (HS256)** con identidad y rol. El servidor es **stateless**: valida la firma y la expiración en cada request, sin sesión en memoria.
- El secreto JWT y la expiración del token se inyectan por **variables de entorno** (`JWT_SECRET`, `ACCESS_TOKEN_EXPIRE_MINUTES`), nunca hardcodeados.

### 2. Autorización — RBAC por dependencias de FastAPI
- Roles `CLIENT` y `SUPPLIER` aplicados con dependencias declarativas (`require_role(...)`). Un proveedor no puede crear solicitudes; un cliente no puede ofertar.
- **Principio de menor privilegio**: cada endpoint exige el rol mínimo necesario. Además, la **guarda de turno** verifica propiedad/contraparte (solo la contraparte de la última propuesta actúa), una autorización a nivel de objeto, no solo de rol.

### 3. Validación de entrada — Pydantic v2
- Todo payload se valida contra un esquema Pydantic: tipos, rangos (montos > 0), campos obligatorios. Lo que no valida, no llega al dominio. Esto frena entradas malformadas y reduce la superficie de ataque.

### 4. Idempotencia — no duplicar transacciones
- El header **`Idempotency-Key`** en todos los POST mutantes, respaldado por la tabla `idempotency_keys`, garantiza que un reintento de red **no** genere una segunda oferta o una doble aceptación. En un sistema de negociación monetaria, duplicar una transacción es un fallo de seguridad/integridad, no solo de UX.

### 5. Atomicidad — transacciones de DB por request
- Cada acción de negociación se ejecuta en **una sola transacción**. Aceptar una oferta cambia la negociación, cierra la solicitud, supersede a las demás y registra auditoría **en un único commit**: o todo, o nada. No existen estados intermedios observables ni inconsistentes ante un fallo a media ejecución.

### 6. Inyección SQL — ORM parametrizado
- Toda la persistencia pasa por **SQLAlchemy 2.0** con consultas parametrizadas. No se construye SQL por concatenación de strings, eliminando la clase de vulnerabilidad de inyección SQL.

### 7. Gestión de secretos
- Secretos y configuración sensible por **variables de entorno** (cargadas con `pydantic-settings`). El `.env.example` documenta las variables sin exponer valores reales; `.env` está fuera del control de versiones. En producción se usaría un gestor de secretos (Vault, AWS Secrets Manager, etc.).

### 8. Auditoría
- La tabla `audit_log` registra **cada transición de estado** con actor, acción, entidad, detalle JSON y `request_id`. Sumado al historial **inmutable append-only** de `proposals`, ofrece un rastro completo y no repudiable de toda negociación, esencial para investigar incidentes y demostrar integridad.

> **Nota adicional de hardening** (no implementado en el alcance de la prueba, pero parte del diseño de producción): TLS terminado en el balanceador, rate limiting por IP/usuario, rotación de secretos, cabeceras de seguridad HTTP y CORS restrictivo.

---

## C. ¿Cómo escalaría el sistema?

### 1. API stateless tras balanceador → escalado horizontal
- La API **no guarda estado de sesión** (el JWT lleva la identidad). Esto permite poner **N réplicas** detrás de un balanceador y escalar horizontalmente añadiendo instancias. Sin afinidad de sesión, sin estado pegajoso.

### 2. Base de datos: índices, paginación y read-replicas
- **Índices** sobre las claves de acceso frecuente: `product_request.status`, `negotiation.request_id`, `negotiation.supplier_id`, `proposal.negotiation_id`, `idempotency_key.key`.
- **Paginación** obligatoria en los listados (`GET /requests`, `GET /negotiations`) para acotar el tamaño de respuesta y la carga de la DB.
- **Read-replicas** de PostgreSQL para derivar la carga de lectura (listados, detalle, reporting) y dejar el primario para escrituras. El patrón append-only de `proposals` encaja muy bien con replicación.

### 3. Caché
- Caché (p. ej. Redis) para lecturas calientes y poco mutables (catálogos, detalle de solicitudes cerradas). La idempotencia ya tiene su propia tabla, pero su lookup también podría apoyarse en caché de baja latencia.

### 4. Asincronía: colas y eventos
- Las **notificaciones** (avisar al cliente de una oferta, al proveedor de una aceptación) se sacan del camino crítico hacia una **cola/eventos** (Celery+Redis, RabbitMQ o un bus de eventos). La transición de estado es síncrona y atómica; el efecto secundario (notificar) es asíncrono y reintentable. Esto reduce la latencia percibida y desacopla fallos de terceros (email/push) del flujo de negociación.

### 5. Particionar por bounded context → microservicios cuando aplique
- Como se detalló en la sección A, cuando un contexto justifique escalado/despliegue independiente (notificaciones, reporting, búsqueda), se **extrae** a un servicio propio. La modularidad interna actual hace que esa extracción sea evolutiva, no un *big bang*.

### 6. Particionamiento de datos
- A gran escala, **particionar/sharding** las tablas de mayor crecimiento (`proposals`, `audit_log`) por rango temporal o por `request_id`. El historial inmutable se presta a particionamiento por tiempo y a archivado en frío de datos antiguos.

### 7. Observabilidad como prerrequisito del escalado
- No se escala lo que no se mide. La observabilidad ya horneada —`/metrics` (Prometheus), logs JSON estructurados, `X-Request-ID` de correlación, latencia por request, `/health` y `/ready`— es **condición previa** para escalar con seguridad: permite detectar cuellos de botella, dimensionar réplicas, definir SLOs y disparar autoescalado sobre métricas reales.

---

## Tabla de decisiones

| Decisión | Alternativas consideradas | Por qué la elegimos |
|----------|---------------------------|----------------------|
| **Monolito modular en capas** | Microservicios; monolito sin capas (big ball of mud) | Un único bounded context + transacciones atómicas; entrega rápida y bajo coste operativo, sin cerrar la puerta a extraer servicios después |
| **FastAPI** | Flask, Django, Express/Node | Async nativo, validación con Pydantic integrada, OpenAPI automático, alto rendimiento; idiomático para el cargo (Python) |
| **PostgreSQL 16** | MySQL, MongoDB | ACID fuerte para transacciones de negociación, tipos `JSON`/`Decimal`, integridad referencial, read-replicas y particionamiento maduros |
| **SQLAlchemy 2.0 (ORM)** | SQL crudo, query builder | Parametrización contra inyección SQL, portabilidad SQLite↔Postgres (tests vs runtime), modelado declarativo del esquema |
| **JWT (HS256) stateless** | Sesiones server-side; OAuth completo | Permite API stateless → escalado horizontal sin afinidad de sesión; suficiente para el alcance |
| **bcrypt** | SHA-256 plano, argon2 | Estándar probado, lento por diseño (resistente a fuerza bruta), con salt; soportado y simple de operar |
| **RBAC por dependencias** | Checks ad-hoc en cada handler | Autorización declarativa, centralizada y testeable; menor privilegio por endpoint |
| **`Idempotency-Key` + tabla** | Sin idempotencia; dedupe por lógica de negocio | Evita ofertas/decisiones duplicadas ante reintentos de red de forma genérica y verificable |
| **`Proposal` append-only** | Campo mutable "monto actual" | Auditoría natural, sin condiciones de carrera, reconstrucción completa de la negociación |
| **`audit_log` de transiciones** | Solo logs de aplicación | Trazabilidad estructurada, consultable y correlacionada (`request_id`); rastro no repudiable |
| **Logs JSON + `X-Request-ID` + `/metrics`** | Logs de texto plano sin correlación | Observabilidad prerrequisito del escalado: correlación, latencia, SLOs, autoescalado por métricas |
| **`metadata.create_all` (hoy) → Alembic (prod)** | Solo `create_all` en producción | Velocidad en el ejercicio; migraciones versionadas/reversibles/revisables para evolucionar el esquema en producción sin pérdida de datos |
| **Frontend HTML+JS vanilla** | React/Vue/Angular | Demuestra Python+JS (los dos lenguajes del cargo) sin sobreingeniería de frontend ajena al objetivo de la prueba |
| **Docker multi-stage + compose + GH Actions** | Despliegue manual; imagen monolítica sin etapas | Entorno prod-like reproducible, imagen runtime ligera, CI con quality gates (lint+tests+build) |

---

## Endurecimiento implementado (seguridad de las transacciones)

Más allá de autenticación/RBAC, se reforzó el sistema en los puntos donde el dinero y el
estado cambian:

- **Bloqueo pesimista de filas (`SELECT … FOR UPDATE`)** en `accept/reject/counter` y en
  `make_offer`. Evita *lost updates* / doble-aceptación cuando ambas partes actúan en
  paralelo: serializa la transición sobre la negociación (y sobre la solicitud al cerrarla).
  No-op en SQLite (tests), efectivo en PostgreSQL.
- **Idempotencia** (`Idempotency-Key`): un reintento de red no duplica oferta/decisión.
- **Atomicidad**: la transición de estado y su registro en `audit_log` viven en la misma
  transacción de DB; si una falla, ambas se revierten.
- **Fail-fast de configuración**: la app **no arranca** en `production` con un `JWT_SECRET`
  por defecto o de menos de 32 caracteres.
- **Rate limiting** en `/auth/login` (fuerza bruta / *credential stuffing*).
- **Cabeceras de seguridad** (`X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`,
  `Permissions-Policy`) y **CORS** restrictivo por configuración.
- **Paginación** (`limit`/`offset`, acotada) en los listados, para que el crecimiento de
  datos no degrade ni exponga respuestas sin límite.

## Decisiones técnicas si el proyecto crece y hay que escalar

Lo siguiente **no** se implementó en el ejercicio por alcance/tiempo, pero es la hoja de
ruta que ejecutaría como líder a medida que el sistema y el equipo crecen.

### Automatización de proceso y calidad (equipo)
- **`pre-commit`** (ruff + ruff-format + checks básicos) para mover el lint al commit y
  mantener el CI verde.
- **`CODEOWNERS` + plantilla de PR + branch protection** (reviews obligatorios, CI verde,
  *linear history*) para escalar la revisión de código sin perder velocidad.
- **`Dependabot`/Renovate + escaneo de imagen (Trivy) + `uv audit`** como defensa de
  **cadena de suministro**; *gate* de **cobertura** y **mypy** en CI conforme sube el riesgo.
- **Versionado SemVer + release por tag** (ya reflejado en CI/CD; ver ADR 0001) y
  **changelog** automatizado.

### Observabilidad avanzada (SRE)
- **Trazas distribuidas con OpenTelemetry** (propagando el `request_id`/trace-id ya
  existente) para seguir una operación a través de servicios cuando se rompa el monolito.
- **Errores con Sentry** (o equivalente) para captura, agrupación y alertado de excepciones.
- **Logs centralizados** (Loki/ELK/Datadog) — el formato JSON ya está listo para ingesta.
- **SLOs + alertas sobre las métricas Prometheus** (latencia p95, tasa de error, saturación)
  y **autoescalado horizontal** basado en esas señales.

### Escalado de datos y arquitectura
- **Postgres**: índices ya presentes en FKs/estados → **read-replicas** y *connection
  pooling* (PgBouncer); particionado de `audit_log`/`proposals` por tiempo.
- **Caché** (Redis) para listados de solo-lectura y para mover el **rate limiting** a un
  store compartido entre réplicas.
- **Eventos/colas** (outbox + broker) para notificaciones y para desacoplar *bounded
  contexts* (Solicitudes / Ofertas / Decisiones) hacia microservicios cuando el dominio y
  la carga lo justifiquen — no antes (evitar complejidad prematura).
- **API stateless tras balanceador** (ya lo es: JWT, sin sesión en memoria salvo el rate
  limiter, que se externaliza a Redis) → escalado horizontal trivial.

## Evolución a SaaS multi-tenant (producto, no código a la medida)

Cuando el sistema crece como **SaaS**, cada cliente/organización (tenant) pedirá "extras".
La decisión clave de liderazgo es tratarlo como **producto configurable**, no resolver con
*forks* ni `if cliente == X`. Eso evita deuda técnica exponencial y vuelve cada feature
reutilizable por todos.

### Modelo de aislamiento (tenancy)
Tres patrones, elegidos por costo vs. aislamiento — normalmente **híbrido por tier**:

| Patrón | Aislamiento | Costo/escala | Cuándo |
|--------|-------------|--------------|--------|
| **Pool** — esquema compartido + `tenant_id` en cada fila | Lógico | El más barato y denso | Default (mayoría de tenants) |
| **Bridge** — un *schema* Postgres por tenant | Medio | Medio | Tenants medianos / cierta compliance |
| **Silo** — una base/instancia por tenant | Fuerte (físico) | El más caro | Enterprise / regulatorio (datos en región propia) |

**Recomendación:** arrancar **pool** con **Row-Level Security (RLS) de PostgreSQL** y
escalar tenants grandes a *schema* o base dedicada (mismo código, distinto *routing*).

### Aislamiento de datos — defensa en profundidad
- `tenant_id` en **toda** entidad; el claim `tenant_id` viaja en el **JWT**.
- Una **dependencia de tenant-context** (igual que el `require_role` actual) inyecta el
  tenant en la sesión y hace `SET app.current_tenant = :id`; las **políticas RLS** de
  Postgres filtran físicamente — aunque una query olvide el `WHERE`, la fila ajena no se ve.
- La capa de servicios ya centraliza el acceso a datos → introducir el *scoping* por tenant
  es un cambio acotado, no una reescritura.

### Configuración sobre personalización (clave para que sea producto)
- **Entitlements / planes + feature flags por tenant**: las "cosas extra" se **activan**, no
  se programan por cliente. Un solo *codebase*, comportamiento por datos.
- **Campos personalizados** vía `JSONB` (metadata extensible) sin migraciones por cliente.
- **Parámetros de la máquina de estados configurables** por tenant (p.ej. expiración de
  ofertas, monedas, niveles de aprobación) leídos de una tabla de settings, no de ramas.
- **Extensibilidad por integración, no por fork**: **webhooks** y **API pública versionada**
  para que el tenant construya sus flujos; *theming*/white-label por configuración.
- **Plantillas/workflows declarativos**: lo específico del tenant se modela como **datos**.

### Operación SaaS
- **Onboarding/provisioning automatizado** de tenants (incl. creación de schema/DB si aplica).
- **Cuotas y rate limits por tenant**; aislamiento de *noisy neighbor*.
- **Observabilidad y costos etiquetados por `tenant_id`** (logs/métricas ya correlacionados).
- **Metering/billing** por uso; **export/borrado por tenant** (GDPR/retención).
- **Arquitectura por celdas (cell-based)** para acotar el *blast radius* y desplegar/migrar
  tenants por lotes.

### Camino de migración desde hoy (single-tenant)
1. Tabla `tenants` + `tenant_id` en entidades y en el JWT.
2. Dependencia de tenant-context + **RLS** activada (deny-by-default).
3. Tabla de **settings/feature-flags** por tenant; gating por plan.
4. Tenants grandes → *schema*/DB dedicada con el **mismo** código (routing por conexión).

> Principio rector: **toda diferencia entre clientes es configuración o extensión, nunca una
> rama de código.** Así el producto escala en clientes sin escalar en complejidad.
