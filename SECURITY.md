# Security Policy

Secure Execution Gateway (SEG) is designed as an internal service with a defense-in-depth security model. The project includes authentication, strict action allowlisting, sandboxed filesystem access, request validation middleware, and container-based isolation.

Detailed security design and threat analysis are documented separately:

- [docs/ARCHITECTURE.md](./docs/ARCHITECTURE.md): system architecture and security-relevant components
- [docs/THREAT_MODEL.md](./docs/THREAD_MODEL.md): threat analysis, attack surfaces, and mitigations
- [docs/CI.md](./docs/CI.md): automated testing, security checks, and CI workflows

This document focuses on vulnerability reporting and coordinated disclosure.

## Deployment Model

SEG is intended to run as an **internal service** inside trusted container infrastructure. It is typically deployed inside a Docker network and accessed only by other trusted services.

The service is not designed to be exposed directly to the public Internet.

## Supported Versions

Only the `main` branch is currently supported with security updates.

Pre-release versions, development branches, and forks are not guaranteed to receive security fixes.

## Reporting a Vulnerability

If you discover a security vulnerability or have security concerns, please report them directly to the project maintainer.

Contact:

Libertocrat - <libertocrat@proton.me>

Please include the following information:

- a clear summary of the issue
- affected versions (commit SHA, tag, or release version)
- environment details (OS, Python version, container runtime)
- reproducible steps or a minimal Proof-of-Concept
- relevant logs or configuration details (sanitized of secrets)
- potential impact (for example data exposure, privilege escalation, or denial of service)

If the issue allows escalation or access to sensitive data, include **SECURITY** in the email subject to prioritize the report.

Please do NOT publish details about the vulnerability publicly until a fix or mitigation plan has been provided.

## Response and Handling

Security reports will be handled confidentially.

The maintainer aims to:

- Acknowledge critical reports within **72 hours**
- Provide an estimated timeline for remediation after initial triage
- Coordinate disclosure with the reporter

## Preferred Disclosure Channels

- **GitHub Security Advisories** (preferred if this repository is hosted on GitHub): allows private disclosure, coordinated disclosure, and optionally requesting CVE assignment.
- **Email to the project contact** (Libertocrat - <libertocrat@proton.me>): acceptable for private reports when Security Advisories are not available.

Please do **NOT** open a public GitHub issue for security-sensitive reports.

## Reporter Checklist

When reporting, please include as much of the following as possible to help triage and reproduce the issue:

- A short, clear summary of the issue.
- Affected versions (commit SHA, tag, or release version) and environment details.
- Reproducible steps or a minimal Proof-of-Concept (PoC).
- Relevant logs, stack traces, or configuration files (sanitized of secrets).
- Exploitation impact (e.g. data exposure, RCE, privilege escalation) and suggested mitigations if known.
- Reporter contact information and whether encrypted communication is required.

## Secure Attachments (Optional)

If you need to send sensitive files, screenshots, or Proofs-of-Concept (PoCs), you may encrypt them using the maintainer’s public PGP key.

The public PGP key is available in the file [SECURITY_PGP_KEY.asc](SECURITY_PGP_KEY.asc) at the root of this repository.

> **PGP fingerprint**:
> 0093 2D8B E725 68F8 7C60  D138 B00F 1868 1AFD 0A6F

### Verify the PGP key (optional)

```bash
gpg --show-keys --fingerprint SECURITY_PGP_KEY.asc
```

## Coordination and Disclosure

Vulnerabilities will be disclosed publicly only after:

- A fix or mitigation has been implemented.
- Disclosure has been coordinated with the reporter.

The project follows a responsible disclosure approach in order to protect users while security fixes are prepared.

---
