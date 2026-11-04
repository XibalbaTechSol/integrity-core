# ADR-0001: Six-function test

## Decision

Every component must name the function it performs:

1. Identity
2. Rules
3. Enforcement
4. Evidence
5. Feedback
6. Access

The component must also name its authority, data boundary, failure mode, and acceptance gate. Components that duplicate an existing authority are deferred or archived unless an ADR explicitly changes the authority map.

## Consequences

This keeps Integrity small, allows Shield and Cortex to remain independently sellable, and makes third-party extensions possible without allowing adapters, model providers, UI code, or connectors to become hidden policy authorities.
