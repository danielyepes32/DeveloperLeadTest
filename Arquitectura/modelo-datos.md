# Modelo de datos

Esquema relacional normalizado en **PostgreSQL 16**, mapeado con **SQLAlchemy 2.0**. El diseño persigue tres objetivos: **integridad por construcción** (restricciones en la base, no solo en código), **auditoría natural** (historial inmutable de propuestas + bitácora de transiciones) y **resistencia a reintentos** (claves de idempotencia).

## Diagrama entidad-relación

```mermaid
erDiagram
    USER ||--o{ PRODUCT_REQUEST : "crea (client_id)"
    USER ||--o{ NEGOTIATION : "participa (supplier_id)"
    USER ||--o{ PROPOSAL : "emite (actor_id)"
    USER ||--o{ AUDIT_LOG : "actúa (actor_id)"
    USER ||--o{ IDEMPOTENCY_KEY : "posee (user_id)"
    PRODUCT_REQUEST ||--o{ NEGOTIATION : "recibe (request_id)"
    NEGOTIATION ||--o{ PROPOSAL : "contiene (negotiation_id)"

    USER {
        int id PK
        string email UK "único"
        string hashed_password "bcrypt"
        string role "client | supplier"
        string full_name
        datetime created_at
    }

    PRODUCT_REQUEST {
        int id PK
        int client_id FK "→ USER"
        string product_name
        string description
        int quantity
        string status "open | closed | cancelled"
        datetime created_at
        datetime updated_at
    }

    NEGOTIATION {
        int id PK
        int request_id FK "→ PRODUCT_REQUEST"
        int supplier_id FK "→ USER"
        string status "active | accepted | rejected"
        decimal agreed_amount "nullable"
        datetime created_at
        datetime updated_at
    }

    PROPOSAL {
        int id PK
        int negotiation_id FK "→ NEGOTIATION"
        int actor_id FK "→ USER"
        string actor_role "client | supplier"
        string kind "offer | counter"
        decimal amount
        string currency "default COP"
        string message
        datetime created_at
    }

    AUDIT_LOG {
        int id PK
        string request_id "correlation id"
        int actor_id FK "→ USER"
        string action
        string entity_type
        int entity_id
        json details
        datetime created_at
    }

    IDEMPOTENCY_KEY {
        string key PK
        int user_id FK "→ USER"
        string method
        string path
        int response_status
        json response_body
        datetime created_at
    }
```

## Notas de diseño

### Restricciones e integridad
- **`USER.email`** es único: identidad inequívoca para login.
- **`NEGOTIATION (request_id, supplier_id)`** tiene **restricción única compuesta**: un único hilo de negociación por proveedor por solicitud. Impide que un proveedor abra dos negociaciones paralelas sobre la misma solicitud.
- Las claves foráneas garantizan integridad referencial a nivel de base, no solo en código.

### `PROPOSAL` — append-only e inmutable
La tabla de propuestas **nunca se actualiza ni se borra**: cada oferta o contraoferta es una fila nueva. El orden cronológico (`created_at` + `id`) reconstruye la negociación completa. La **última propuesta** determina de quién es el turno y, al aceptar, fija `agreed_amount`. Esto produce **auditoría natural** sin lógica adicional y elimina condiciones de carrera sobre un campo mutable de "monto actual".

### `AUDIT_LOG` — trazabilidad de transiciones
Cada transición de la máquina de estados (crear solicitud, ofertar, aceptar, rechazar, contraofertar, supersedir) escribe una fila con `actor_id`, `action`, `entity_type`/`entity_id`, `details` (JSON) y el **`request_id`** de correlación. Permite reconstruir *quién hizo qué, cuándo y en qué petición*, y cruzar la auditoría con los logs estructurados.

### `IDEMPOTENCY_KEY` — resistencia a reintentos
Clave primaria = el header `Idempotency-Key`. Guarda `method`, `path`, `response_status` y `response_body`. Ante un reintento de red, el sistema devuelve la respuesta cacheada en vez de ejecutar la mutación de nuevo. Evita ofertas o decisiones duplicadas.

### Tipos
- **`amount` / `agreed_amount`** se modelan como **`Decimal`** (no `float`) para evitar errores de redondeo en montos monetarios.
- **`currency`** por defecto `COP`; se persiste explícitamente por si el dominio crece a multimoneda.
- Las marcas temporales se almacenan en UTC.

### Evolución del esquema
En el ejercicio el esquema se inicializa con `metadata.create_all`. En **producción** se gestionaría con **migraciones Alembic**: versionadas, revisables en *code review* y reversibles, para evolucionar el esquema sin pérdida de datos ni *downtime* descontrolado.
