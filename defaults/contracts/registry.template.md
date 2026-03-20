<!-- AUTO-CREATED by Claude Code during project bootstrap.
     This is the service registry — the manifest of all services in the project.
     Claude will populate this as services are built.
     Keep in sync with docker-compose.yml and deployment configs. -->

# Service Registry

> Canonical list of all services, their runtimes, ports, and dependency relationships.
> Update this file whenever a service is added, removed, or changes its dependencies.

## Services

| Name | Runtime | Port | Depends On | Depended By |
|------|---------|------|------------|-------------|
| <!-- service-name --> | <!-- e.g., NestJS / Node 20 --> | <!-- e.g., 3001 --> | <!-- e.g., PostgreSQL, Redis, Kafka --> | <!-- e.g., frontend, other-service --> |

<!-- Example row:
| eln-core | NestJS 10 / Node 20 | 3001 | PostgreSQL, Redis, Kafka, Keycloak | frontend, lims, ontology |
-->

## Infrastructure Dependencies

| Name | Type | Port | Used By |
|------|------|------|---------|
| <!-- e.g., PostgreSQL --> | <!-- Database --> | <!-- 5432 --> | <!-- all services --> |

<!-- List databases, message brokers, caches, auth providers, and other
     infrastructure that services depend on. -->
