# Security Policy

If you discover a security vulnerability or have security concerns, please report them directly to the project maintainer:

- Contact: libertocrat@proton.me

## Supported Versions

Only the `main` branch is currently supported with security updates.

Pre-release versions, development branches, and forks are not guaranteed to receive security fixes.

## Reporting a Vulnerability

1. Send an email to the address above with a clear summary of the issue.
2. Include reproducible steps, environment details (OS, Python version, container runtime), and any relevant logs or files.
3. If the issue allows escalation or access to sensitive data, include **"SECURITY"** in the email subject to prioritize the report.

Please do **NOT** publish details about the vulnerability publicly until a fix or mitigation plan has been provided.

## Response and Handling

- Reports will be handled confidentially.
- We aim to acknowledge **critical security reports within 72 hours**.
- The maintainer will provide an estimated timeline for mitigation or remediation after initial triage.

## Preferred Disclosure Channels

1. **GitHub Security Advisories** (preferred if this repository is hosted on GitHub): allows private disclosure, coordinated disclosure, and optionally requesting CVE assignment.
2. **Email to the project contact** (libertocrat@proton.me): acceptable for private reports when Security Advisories are not available.

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

We will coordinate disclosure with the reporter. Public disclosure will only occur after a fix or mitigation is available, or if explicitly agreed upon with the reporter.
