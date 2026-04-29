# Contributing

## 1. Introduction

Thank you for your interest in contributing to the Secure Execution Gateway (SEG).

SEG is an open source project focused on secure execution, strict action allowlisting, and filesystem sandboxing for containerized automation environments.

## 2. Contribution Status

The repository is not currently accepting external code contributions.

> [!IMPORTANT]
> External pull requests are currently paused while the project stabilizes its public API, security model, and release workflow.

The project is still stabilizing several core areas before opening the pull request process to external contributors:

- API design
- security model
- testing coverage
- CI workflows
- release process

This restriction is intended to keep the public interface and review process stable before formal contribution rules are introduced.

## 3. Future Contribution Model

Once external contributions are enabled, the repository will publish explicit guidelines for:

- branching strategy
- pull request workflow
- code style requirements
- testing expectations
- security review requirements

Those rules are not defined yet and should not be assumed before they are
documented.

## 4. Providing Feedback

Feedback is still welcome while the project is stabilizing.

Useful feedback includes:

- architecture suggestions
- documentation improvements
- usability observations
- bug reports

For non-security topics, use the GitHub issue tracker.

## 5. Security Reporting

Security vulnerabilities must be reported privately.

Do not disclose security issues through public GitHub issues.

Follow the responsible disclosure process defined in [SECURITY.md](SECURITY.md).

## 6. Development Documentation

Developers who want to work with the codebase locally should use [DEVELOPMENT.md](DEVELOPMENT.md).

The development guide covers:

- local environment setup
- authenticated action API routes under `/v1/actions` and `/v1/files`
- Makefile workflow
- CI reproduction
- pre-commit hooks
- helper scripts in `scripts/`
- troubleshooting

## 7. Related Documentation

The main technical and project documents are:

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- [docs/THREAT_MODEL.md](docs/THREAT_MODEL.md)
- [docs/TESTING.md](docs/TESTING.md)
- [docs/CI.md](docs/CI.md)
- [SECURITY.md](SECURITY.md)
- [DEVELOPMENT.md](DEVELOPMENT.md)

These documents describe the internal design, security model, testing strategy, release workflows, and local development process for SEG.

---
