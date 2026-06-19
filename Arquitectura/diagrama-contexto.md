# Diagrama de contexto y componentes

Este documento muestra dos vistas complementarias: (1) el **contexto** del sistema —quién lo usa y con qué interactúa— y (2) los **componentes internos** del monolito modular y cómo se relacionan con la persistencia y la observabilidad.

## 1. Diagrama de contexto

```mermaid
graph TB
    cliente["👤 Cliente<br/>(rol CLIENT)"]
    proveedor["👤 Proveedor<br/>(rol SUPPLIER)"]
    navegador["🌐 Navegador<br/>Frontend HTML + JS vanilla"]
    prometheus["📈 Prometheus<br/>(scrapea /metrics)"]

    subgraph sistema["Sistema — Solicitudes y Ofertas"]
        api["⚙️ API FastAPI<br/>(monolito modular)"]
        db[("🗄️ PostgreSQL 16")]
    end

    cliente --> navegador
    proveedor --> navegador
    navegador -->|"HTTPS · JWT bearer · Idempotency-Key"| api
    api -->|"SQLAlchemy 2.0 · transacción por request"| db
    prometheus -.->|"GET /metrics"| api

    classDef actor fill:#dbeafe,stroke:#1e40af,color:#1e3a8a;
    classDef ext fill:#fef3c7,stroke:#b45309,color:#7c2d12;
    class cliente,proveedor actor;
    class prometheus ext;
```

**Lectura.** Clientes y proveedores usan un navegador que carga el frontend estático servido por la propia API (`StaticFiles`). Toda mutación viaja con un **JWT bearer** (identidad + rol) y un header **`Idempotency-Key`**. La API persiste en **PostgreSQL** con una transacción atómica por petición. **Prometheus** raspa el endpoint `/metrics` para observabilidad. No hay dependencias externas adicionales: el alcance es un único bounded context autocontenido.

## 2. Diagrama de componentes (interior de la API)

```mermaid
graph TB
    subgraph edge["Capa de borde (HTTP)"]
        static["StaticFiles<br/>frontend vanilla"]
        mw["Middleware<br/>X-Request-ID · logging JSON · latencia"]
        instr["Instrumentator<br/>/metrics Prometheus"]
    end

    subgraph routers["Routers (FastAPI)"]
        rAuth["auth"]
        rReq["requests"]
        rNeg["negotiations"]
        rHealth["health / ready"]
    end

    subgraph deps["Dependencias transversales"]
        dAuth["JWT decode<br/>get_current_user"]
        dRbac["RBAC<br/>require_role(CLIENT|SUPPLIER)"]
        dIdem["Idempotencia<br/>Idempotency-Key"]
    end

    subgraph services["Services (dominio)"]
        sAuth["AuthService<br/>bcrypt · emisión JWT"]
        sReq["RequestService"]
        sNeg["NegotiationService<br/>★ máquina de estados ★<br/>guardas de turno"]
        sAudit["AuditService<br/>registra transiciones"]
    end

    subgraph persist["Persistencia (SQLAlchemy 2.0)"]
        models["Models: User · ProductRequest<br/>Negotiation · Proposal (append-only)<br/>AuditLog · IdempotencyKey"]
        session["Session<br/>(transacción por request)"]
    end

    db[("PostgreSQL 16")]

    mw --> routers
    instr -.-> mw
    rAuth --> dAuth
    rReq --> dRbac
    rNeg --> dRbac
    routers --> dIdem
    rAuth --> sAuth
    rReq --> sReq
    rNeg --> sNeg
    sNeg --> sAudit
    sReq --> sAudit
    services --> models
    models --> session
    session --> db

    classDef domain fill:#dcfce7,stroke:#15803d,color:#14532d;
    class sNeg domain;
```

**Lectura.** El borde resuelve preocupaciones transversales (correlation id, logging, métricas, idempotencia). Los **routers** delegan en **services**; el componente central es **`NegotiationService`**, que implementa la máquina de estados y las guardas de turno (ver [maquina-estados.md](./maquina-estados.md)). Cada transición de estado se registra en `AuditService` → `audit_log`. La capa de persistencia gestiona una **transacción por request**, de modo que cada acción de negociación es atómica: o se aplica completa (cambio de estado + nueva propuesta + registro de auditoría) o se revierte por completo.
