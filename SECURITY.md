# Security

Sponte is a local orchestration CLI for development workflows. It drives native harness CLIs and does not sandbox commands, file access, network access, secrets, or production resources.

## Supported versions

Sponte is pre-1.0 and experimental. Security fixes target the latest public code unless a release branch is explicitly maintained.

## Reporting a vulnerability

If the GitHub repository has private vulnerability reporting enabled, use that first. Otherwise, open a minimal GitHub issue that describes the impact without including secrets, private code, credentials, or exploit details that would put users at immediate risk.

## Operational guidance

- Run Sponte only in development workspaces.
- Do not run it with production credentials or against production environments.
- Review generated diffs, harness output, and commands before trusting long-running unattended loops.
- Rotate any credentials that may have been exposed to an unsafe agent session.
