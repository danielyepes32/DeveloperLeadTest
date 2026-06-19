# ADR 0001 — Estrategia de despliegue (CI/CD)

- **Estado:** Aceptado
- **Fecha:** 2026-06-18
- **Decisores:** Líder de Desarrollo

## Contexto

Necesitamos un pipeline que garantice calidad y permita entregas frecuentes y seguras
con un equipo pequeño (2–3 devs), sin desplegar manualmente y sin riesgo de subir código
roto a producción.

## Decisión

Adoptamos **trunk-based development** con dos disparadores de despliegue:

| Disparador | Acción | Ambiente | Aprobación |
|-----------|--------|----------|------------|
| Pull Request | quality gates (lint + tests) | — | review obligatorio |
| Push a `main` | build + scan + **deploy** | **staging** | automática (continuous deployment) |
| Tag `vX.Y.Z` (SemVer) | build + scan + **deploy** | **producción** | **manual** (required reviewers del environment) |

Todo cambio entra por PR y pasa los *quality gates*. Al hacer merge a `main` se despliega
automáticamente a **staging**. Producción se libera de forma **explícita y versionada**
creando un *tag* semántico, lo que activa el deploy con aprobación humana (GitHub
Environments con required reviewers).

### Quality gates antes de cualquier deploy
1. **Lint** (`ruff`).
2. **Tests** (`pytest`).
3. **Build** reproducible de la imagen (Docker + uv, capa de deps cacheada).
4. **Escaneo de vulnerabilidades** de la imagen (Trivy; falla en CRITICAL/HIGH).

## Por qué (justificación)

- **`main` siempre desplegable:** trunk-based + CD a staging da feedback inmediato y evita
  ramas de larga vida y *merge hell* — ideal para un equipo pequeño.
- **Tag = release a producción:** separar "integrado" (main→staging) de "liberado"
  (tag→prod) da una frontera **auditable y reversible**. El tag SemVer es el artefacto de
  versión: trazable, y permite `rollback` re-desplegando el tag anterior.
- **Aprobación en producción:** el environment `production` con required reviewers añade un
  control humano en el único punto donde el riesgo lo amerita, sin frenar el flujo diario.
- **Seguridad de cadena de suministro:** escaneo de imagen + lockfile (`uv.lock`) +
  imagen non-root reducen superficie de ataque antes de publicar.

## Consecuencias

- **+** Despliegues frecuentes y de bajo riesgo; producción siempre parte de un commit ya
  probado en staging.
- **+** Versionado claro y rollback trivial (re-deploy del tag previo).
- **−** Requiere disciplina de SemVer y configurar los GitHub Environments (staging,
  production con reviewers).
- **Siguiente paso:** estrategia de despliegue a prod **blue/green** o **canary** con
  healthcheck y rollback automático; *feature flags* para desacoplar deploy de release.
