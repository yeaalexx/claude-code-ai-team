<!-- AUTO-CREATED by Claude Code during project bootstrap.
     Multi-tenancy rules for the project.
     Claude will populate project-specific isolation strategy during bootstrap. -->

# Multi-Tenancy Rules

> How tenant isolation is enforced across the platform.
> These rules are non-negotiable — violations are security incidents.

## Isolation Strategy

<!-- Describe your project's tenant isolation approach. Common strategies:
     - Schema-per-tenant: each tenant gets a separate DB schema
     - Row-Level Security (RLS): shared tables with tenant_id column + RLS policies
     - Database-per-tenant: fully separate databases
     - Hybrid: schema-per-tenant with RLS as defense-in-depth -->

**Strategy:** <!-- e.g., Schema-per-tenant with RLS defense-in-depth -->

## Tenant ID Propagation

1. <!-- How tenant ID enters the system (e.g., extracted from JWT claim at API gateway) -->
2. <!-- How tenant ID is set in database context (e.g., SET app.tenant_id = '<uuid>' at request start) -->
3. <!-- How tenant ID flows between services (e.g., X-Tenant-ID header on inter-service calls) -->
4. <!-- How tenant ID is included in events (e.g., tenant_id field in Kafka event payload) -->

## Rules

1. Every database query MUST be scoped to the current tenant. No exceptions.
2. Tenant context MUST be set at the start of every request, before any DB operations.
3. Cross-tenant data access is forbidden unless explicitly authorized by a sharing mechanism.
4. Tenant IDs in URLs, headers, and JWT claims MUST be validated and consistent.
5. Background jobs and event consumers MUST set tenant context before processing.

## Anti-Patterns

<!-- Document tenant isolation mistakes to avoid. -->

<!--
### TA-001: Short title
- **Risk:** What could go wrong (e.g., data leak between tenants)
- **Wrong pattern:** The code pattern that causes the issue
- **Correct pattern:** The safe alternative
-->
