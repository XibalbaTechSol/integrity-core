# Security Policy

## Scope

This repository may contain experimental, prototype, or production-adjacent code. Do not assume that a feature marked planned, experimental, or unverified is safe for production.

## Reporting a vulnerability

Do not open a public issue for an undisclosed vulnerability. Use GitHub’s private vulnerability reporting or security-advisory mechanism for this repository when available. If it is unavailable, contact the repository maintainers through the XibalbaTechSol organization’s private GitHub contact path and include only the minimum necessary detail.

Please include:

- Affected commit, version, or workflow.
- Reproduction steps or proof of concept.
- Impact and affected trust boundary.
- Suggested mitigation, if known.
- Whether the report contains sensitive data.

Do not include credentials, private keys, live personal data, or undisclosed exploit material beyond what is necessary to reproduce the issue.

## Response and disclosure

Maintainers will acknowledge receipt when possible, investigate privately, and coordinate remediation and disclosure. Public disclosure timing depends on impact, available mitigation, affected users, and upstream coordination.

## Security boundaries

Changes involving authentication, authorization, identity, cryptography, secrets, tenant isolation, deployment controls, or sensitive data require explicit maintainer review and tests. Never weaken a security control to make a test or deployment pass.
