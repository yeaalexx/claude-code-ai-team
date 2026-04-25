<!-- AUTO-CREATED by Claude Code during project bootstrap.
     This is the event catalog — all asynchronous events flowing between services.
     Claude will populate this as event-driven integrations are built.
     Every Kafka topic (or equivalent) should have an entry here. -->

# Event Catalog

> Canonical list of all asynchronous events (Kafka topics, message queues, etc.)
> flowing between services. Update whenever a new event type is introduced.

## Events

| Topic | Producer | Schema | Consumers | Key Rules |
|-------|----------|--------|-----------|-----------|
| <!-- e.g., orders.placed --> | <!-- e.g., order-service --> | <!-- e.g., OrderPlacedEvent v1 --> | <!-- e.g., billing, inventory-service --> | <!-- e.g., must include tenant_id, order_id --> |

<!-- Add one row per event topic. If a topic carries multiple event types,
     list each type as a separate row with the same topic name. -->

## Standard Event Envelope

<!-- Define your project's standard event format here. Example: -->

```json
{
  "event_id": "<uuid-v7>",
  "event_type": "<topic.action>",
  "timestamp": "<ISO-8601 UTC>",
  "tenant_id": "<uuid>",
  "actor_id": "<uuid>",
  "payload": {
    "<!-- event-specific fields -->"
  }
}
```

## Rules

1. All events MUST include `event_id`, `event_type`, `timestamp`, and `tenant_id`.
2. Consumers MUST be idempotent — duplicate delivery is possible.
3. Events are append-only facts — never mutate a published event schema in a breaking way.
4. Schema changes require a new version (e.g., `EntryCreatedEvent v2`).
