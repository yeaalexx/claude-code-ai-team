<!-- AUTO-CREATED by Claude Code during project bootstrap.
     Standard error response format and HTTP status code guidelines.
     All services MUST follow these conventions for consistent error handling. -->

# Standard Error Format

> Every service MUST return errors in this format for consistency.
> Clients depend on this structure for error handling and display.

## Error Response Envelope

```json
{
  "error": {
    "code": "<MACHINE_READABLE_CODE>",
    "message": "<Human-readable description>"
  }
}
```

<!-- Extend the envelope if your project needs additional fields. Common additions: -->
<!--
{
  "error": {
    "code": "VALIDATION_FAILED",
    "message": "Field 'name' is required.",
    "details": [
      { "field": "name", "rule": "required" }
    ],
    "request_id": "<X-Request-ID value>"
  }
}
-->

## HTTP Status Code Guidelines

| Status | When to Use | Example |
|--------|------------|---------|
| `200 OK` | Successful GET, PUT, PATCH | Returning a resource or updated resource |
| `201 Created` | Successful POST that creates a resource | New entity created |
| `204 No Content` | Successful DELETE or action with no response body | Resource deleted |
| `400 Bad Request` | Invalid input, validation failure | Missing required field |
| `401 Unauthorized` | Missing or invalid authentication | No/expired JWT |
| `403 Forbidden` | Authenticated but insufficient permissions | Wrong role/tenant |
| `404 Not Found` | Resource does not exist | Entry ID not in database |
| `409 Conflict` | State conflict (duplicate, version mismatch) | Duplicate unique key |
| `422 Unprocessable Entity` | Semantically invalid (valid syntax, bad logic) | Invalid state transition |
| `500 Internal Server Error` | Unexpected server error | Unhandled exception |

## Rules

1. **Always return JSON** — even for errors. Never return plain text error messages.
2. **Never leak internals** — error messages must not include stack traces, SQL queries, or internal paths.
3. **Use `code` for programmatic handling** — clients switch on `error.code`, not `error.message`.
4. **Use `message` for humans** — should be clear enough for a developer reading logs.
5. **Follow RFC 9110** — use HTTP status codes strictly per their defined semantics.

## Project Error Codes

<!-- Add project-specific error codes here as they are defined. -->

| Code | HTTP Status | Description |
|------|-------------|-------------|
| <!-- e.g., TENANT_NOT_FOUND --> | <!-- 404 --> | <!-- Tenant ID does not exist --> |
