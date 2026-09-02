# Repository security hardening

The workflows in this directory provide security scanning and safely automate
low-risk dependency maintenance. GitHub intentionally does not allow a normal
repository commit to turn on every administrative security control. A
repository administrator should verify the following one-time settings under
**Settings → Code security and analysis**:

- Dependency graph, Dependabot alerts, and Dependabot security updates are on.
- Grouped security updates are on.
- Secret scanning, push protection, and validity checks are on where the
  repository's GitHub plan supports them.
- Private vulnerability reporting is on.
- Code scanning is configured through `.github/workflows/codeql.yml` and
  Copilot Autofix shows as enabled after the first trusted CodeQL run.

## Protect `main`

Create a branch ruleset targeting `main` with these controls:

- Require a pull request with at least one approval and dismiss stale
  approvals when new commits are pushed.
- Require conversation resolution and prevent force pushes and deletions.
- Require signed commits if every regular contributor can sign their commits.
- Require branches to be up to date before merging.
- Require these status checks:
  - `Python 3.11`
  - `Python 3.12`
  - `Python 3.13`
  - `Dependency review`
  - Both CodeQL `Analyze` matrix jobs
- Do not allow bypass except for a narrowly controlled emergency role.
- Turn on repository auto-merge so verified Dependabot patch updates can wait
  for the required checks rather than bypassing them.

GitHub may display check names slightly differently after their first run. Use
the names emitted by Actions if they differ from the names above.

## Maintenance policy

- Dependabot groups routine minor and patch updates weekly to control pull
  request noise.
- Patch-only Dependabot updates are approved and queued for squash auto-merge.
  The privileged workflow does not check out or run pull-request code.
- CI, dependency review, and CodeQL remain the merge gate. A failing update is
  left open for investigation; it is never merged around a failed check.
- Minor and major upgrades require human review because they may include
  intentional breaking changes.
- The scheduled audit catches disclosures affecting already-installed Python
  dependencies. Dependabot security updates propose the corresponding fix.

This setup automates safe, well-scoped maintenance. It intentionally does not
let an AI agent rewrite and merge arbitrary application code without review;
that would weaken the same supply-chain controls the automation is intended to
provide.
