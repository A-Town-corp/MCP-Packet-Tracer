# Security Policy

## Supported Versions

The Packet Tracer MCP Server is under active development. Security fixes are
applied to the latest released version on the `main` branch. Older tagged
releases are not guaranteed to receive backported fixes.

| Version | Supported          |
| ------- | ------------------ |
| Latest (`main`) | :white_check_mark: |
| Older releases  | :x:                |

## Reporting a Vulnerability

If you discover a security vulnerability in this project, please **do not**
open a public GitHub issue. Instead, report it responsibly using one of the
following private channels:

1. **GitHub Security Advisories (preferred):** Use the
   [Report a vulnerability](https://github.com/A-Town-corp/MCP-Packet-Tracer/security/advisories/new)
   form in the "Security" tab of this repository. This creates a private
   advisory that only maintainers can see until it is resolved.
2. **Email:** If you are unable to use GitHub Security Advisories, contact the
   maintainers privately by opening a private discussion with the repository
   owner via their GitHub profile.

Please include as much detail as possible so we can reproduce and assess the
issue quickly:

- A description of the vulnerability and its potential impact.
- Steps to reproduce, including affected files, tools, or MCP calls.
- Any proof-of-concept code, logs, or screenshots.
- The version/commit of the project you tested against.

## What to Expect

- **Acknowledgement:** We aim to acknowledge new reports within 5 business
  days.
- **Assessment:** We will investigate and confirm the issue, and may ask for
  additional information.
- **Fix & Disclosure:** Once a fix is available, we will coordinate a release
  and credit the reporter (unless anonymity is requested). We follow
  coordinated/responsible disclosure and ask reporters not to publicly
  disclose details until a fix has been released.

## Scope

This policy covers the code in this repository, including the MCP server
(Python), helper tooling, and any JavaScript/HTML assets shipped with the
project (e.g. `UI HELPER/`). It does not cover Cisco Packet Tracer itself,
which is proprietary software maintained by Cisco/Netacad.

## Preventive Measures

This repository uses the following automated security tooling:

- **Dependabot** for grouped Python and GitHub Actions dependency updates.
- **Verified patch updates:** Dependabot patch pull requests are approved for
  auto-merge only after the repository's required checks pass. Minor and major
  updates always require maintainer review.
- **CodeQL** security-extended static analysis for Python and JavaScript on
  pushes and pull requests to `main`, with Copilot Autofix enabled after a
  successful trusted analysis run.
- **Dependency review** rejects pull requests that introduce dependencies with
  known moderate-or-higher vulnerabilities or disallowed licenses.
- **Scheduled Python audits** detect newly disclosed vulnerabilities even when
  no dependency file has changed.
- **Secret scanning** and **push protection** should be enabled in GitHub's
  repository settings to help prevent credentials from being committed.

The required GitHub-side configuration and branch-protection checks are
documented in [the repository hardening guide](.github/SECURITY_HARDENING.md).

Thank you for helping keep this project and its users safe.
