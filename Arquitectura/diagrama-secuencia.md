# Diagrama de secuencia — ciclo completo de negociación

Este diagrama traza un ciclo de extremo a extremo: **el cliente crea una solicitud → el proveedor oferta → el cliente contraoferta → el proveedor acepta**. Resalta los tres mecanismos de producción en el flujo: **JWT** (identidad + rol), **`Idempotency-Key`** (no duplicar mutaciones) y **`audit_log`** (trazabilidad de cada transición). Para no saturar el diagrama, los detalles transversales (correlation id `X-Request-ID`, logging JSON, transacción por request) se anotan una vez y aplican a todas las mutaciones.

```mermaid
sequenceDiagram
    autonumber
    actor C as Cliente (CLIENT)
    actor S as Proveedor (SUPPLIER)
    participant API as API FastAPI<br/>(routers + RBAC + idempotencia)
    participant SVC as NegotiationService<br/>(máquina de estados)
    participant DB as PostgreSQL

    Note over API: Todo POST mutante: valida JWT + rol,<br/>asigna X-Request-ID, abre transacción,<br/>verifica Idempotency-Key, audita la transición.

    %% 1. Cliente crea la solicitud
    C->>API: POST /requests<br/>Authorization: Bearer <JWT cliente><br/>Idempotency-Key: k1
    API->>API: get_current_user (JWT) + require_role(CLIENT)
    API->>DB: ¿existe Idempotency-Key k1?
    DB-->>API: no
    API->>SVC: crear ProductRequest(open)
    SVC->>DB: INSERT product_request (status=open)
    SVC->>DB: INSERT audit_log (action=request_created, request_id)
    API->>DB: guardar Idempotency-Key k1 → respuesta
    DB-->>API: commit
    API-->>C: 201 Created (request #R)

    %% 2. Proveedor oferta
    S->>API: POST /requests/R/offers {amount: 1000}<br/>Bearer <JWT proveedor> · Idempotency-Key: k2
    API->>API: get_current_user + require_role(SUPPLIER)
    API->>SVC: crear oferta sobre solicitud R
    SVC->>DB: ¿solicitud R open? ¿negociación (R, supplier) ya existe?
    DB-->>SVC: open=sí · existe=no
    SVC->>DB: INSERT negotiation (active)
    SVC->>DB: INSERT proposal (kind=offer, actor=supplier, amount=1000)
    SVC->>DB: INSERT audit_log (action=offer_created)
    API->>DB: guardar Idempotency-Key k2
    DB-->>API: commit
    API-->>S: 201 Created (negotiation #N) — turno: CLIENTE

    %% 3. Cliente contraoferta
    C->>API: POST /negotiations/N/counter {amount: 900}<br/>Bearer <JWT cliente> · Idempotency-Key: k3
    API->>API: get_current_user + require_role(CLIENT)
    API->>SVC: contraofertar en N
    SVC->>DB: leer última proposal de N
    DB-->>SVC: última = offer del PROVEEDOR
    Note over SVC: GUARDA DE TURNO: la contraparte es el CLIENTE → OK
    SVC->>DB: INSERT proposal (kind=counter, actor=client, amount=900)
    SVC->>DB: INSERT audit_log (action=counter_created)
    API->>DB: guardar Idempotency-Key k3
    DB-->>API: commit
    API-->>C: 201 Created — turno: PROVEEDOR

    %% Reintento de red sobre la contraoferta (idempotencia en acción)
    C-->>API: (reintento) POST /negotiations/N/counter · Idempotency-Key: k3
    API->>DB: ¿existe Idempotency-Key k3?
    DB-->>API: sí → respuesta cacheada
    API-->>C: 201 Created (misma respuesta) — sin duplicar la propuesta

    %% 4. Proveedor acepta
    S->>API: POST /negotiations/N/accept<br/>Bearer <JWT proveedor> · Idempotency-Key: k4
    API->>API: get_current_user + require_role(SUPPLIER)
    API->>SVC: aceptar N
    SVC->>DB: leer última proposal de N
    DB-->>SVC: última = counter del CLIENTE
    Note over SVC: GUARDA DE TURNO: la contraparte es el PROVEEDOR → OK
    SVC->>DB: UPDATE negotiation N (status=accepted, agreed_amount=900)
    SVC->>DB: UPDATE product_request R (status=closed)
    SVC->>DB: UPDATE otras negociaciones activas de R → rejected (superseded)
    SVC->>DB: INSERT audit_log (action=negotiation_accepted)
    API->>DB: guardar Idempotency-Key k4
    DB-->>API: commit (atómico: todo o nada)
    API-->>S: 200 OK — negociación ACCEPTED · acuerdo: 900 COP
```

## Puntos clave del flujo

- **JWT en cada paso.** El `Authorization: Bearer <JWT>` identifica al actor y su rol. La dependencia `require_role(...)` rechaza acciones del rol equivocado **antes** de tocar el dominio (403).
- **Idempotency-Key evita duplicados.** El paso del *reintento de red* sobre la contraoferta muestra el caso real: la misma `Idempotency-Key k3` no genera una segunda propuesta; se devuelve la respuesta cacheada. Esto es crítico en una negociación monetaria.
- **La guarda de turno se evalúa contra la última propuesta.** Antes de `counter` y de `accept`, el servicio lee la **última `Proposal`** y verifica que el actor sea la contraparte. Si no lo es, devuelve 409 ("no es tu turno").
- **Atomicidad de la aceptación.** Aceptar dispara varios cambios (negociación → accepted, solicitud → closed, otras negociaciones → superseded, registro de auditoría). Todos ocurren en **una sola transacción**: o se aplican juntos o se revierten juntos. No hay estados intermedios inconsistentes.
- **Trazabilidad continua.** Cada transición escribe en `audit_log` con su `request_id`, de modo que la negociación completa es reconstruible y auditable a posteriori.
