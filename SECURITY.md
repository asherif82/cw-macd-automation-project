# Security Policy

## Supported use

This repository contains automation that can modify telephony configuration, directory attributes, voicemail objects, and ServiceNow task state. Treat it as privileged infrastructure code.

## Reporting a vulnerability

Do not publish credentials, internal addresses, employee data, request IDs, or exploit details in a public issue. Report security concerns through your organization's approved security/IT process. If this repository is public by mistake, make it private and follow the organization's credential-rotation and incident-response process.

## Minimum safeguards before production

- Store secrets in an approved secret manager or protected runtime environment.
- Use dedicated service accounts with minimum required permissions.
- Validate TLS certificates; do not disable certificate verification.
- Restrict repository visibility and protect the default branch.
- Require peer review and change approval for changes affecting provisioning.
- Redact credentials and personally identifiable information from logs.
- Test failure/retry behavior and reconcile partial writes before rerunning.
