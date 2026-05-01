# Contributing

## 1. Introduction

Thank you for your interest in contributing to the Secure Execution Gateway (SEG).

SEG is an open source project focused on secure command execution, a DSL-defined action surface, API-based file management, and container-oriented isolation for automation environments.

## 2. Contribution Status

The repository is not currently accepting external code contributions.

> [!IMPORTANT]
> External pull requests are currently paused while the project stabilizes its public API, security model, DSL action surface, and release workflow.

The project is still stabilizing several core areas before opening the pull request process to external contributors:

- API design
- security model
- module and action surface
- testing coverage
- CI workflows
- release process

## 3. Future Contribution Model

Once external contributions are enabled, the repository will publish explicit guidelines for:

- branching strategy
- pull request workflow
- code style requirements
- testing expectations
- DSL spec review expectations
- security review requirements

Those rules are not defined yet and should not be assumed before they are documented.

## 4. Providing Feedback

Feedback is still welcome while the project is stabilizing.

Useful feedback includes:

- architecture suggestions
- DSL ergonomics observations
- documentation improvements
- bug reports
- usability observations around `/v1/actions`, `/v1/files`, and generated OpenAPI docs

For non-security topics, use the GitHub issue tracker.

## 5. Security Reporting

Security vulnerabilities must be reported privately.

Do not disclose security issues through public GitHub issues.

Follow the responsible disclosure process defined in [SECURITY.md](SECURITY.md).

## 6. Development Documentation

Developers who want to work with the codebase locally should use [DEVELOPMENT.md](DEVELOPMENT.md).

The development guide covers:

- local environment setup
- authenticated action and file API routes under `/v1/actions` and `/v1/files`
- DSL spec development and validation flow
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
- [scripts/README.md](scripts/README.md)

These documents describe the internal design, DSL execution model, file API, testing strategy, release workflows, local development process, and helper scripts for SEG.

---
