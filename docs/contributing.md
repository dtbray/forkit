# Contributing — forkit

## Branching

- Default branch: `main`
- All work happens on feature branches. **Never commit directly to `main`.**
- Branch prefix conventions:
  - `feat/<topic>` — new feature
  - `fix/<topic>` — bug fix
  - `docs/<topic>` — docs only
  - `chore/<topic>` — build, tooling, deps
  - `refactor/<topic>` — internal refactor, no behavior change
  - `test/<topic>` — test-only changes
- Branches merge into `main` via pull request, even for solo work (creates an audit trail).

## Commits

Conventional Commits format:

```
<type>(<scope>): <subject>

<optional body>
```

Where `<type>` is one of: `feat`, `fix`, `docs`, `chore`, `refactor`, `test`, `perf`, `style`.

Examples:
- `feat(parser): add JSON-LD adapter for Serious Eats`
- `fix(api): handle null hero_image in recipe response`
- `chore(deps): bump fastapi to 0.115`

### Authorship

- Commits are authored by `Ron DeMeritt <rdemeritt@gmail.com>`.
- **Never add `Co-Authored-By: Claude` or any Claude attribution.** Even when AI is used in authoring.

## Releases

- Tag releases as `v0.X.Y` once MVP ships.
- Pre-MVP: no version tags; `main` is the working surface.

## Pull Requests

- PRs target `main`.
- PR title follows Conventional Commits (it becomes the squash-merge commit subject).
- Describe the **why** in the body, not just the **what**.
- Link related issues / spec docs (in the harness workspace).

## Issues

- Bugs, features, discussion items → GitHub Issues on this repo.
- Labels: `bug`, `enhancement`, `discussion`, `parser-adapter`, `ux`, `infra`.
