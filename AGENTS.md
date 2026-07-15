# AGENTS.md

Operating instructions for coding agents working in `kazoogh/Dictate`.

## Repository scope

- Repository: `kazoogh/Dictate`
- Project type: `python-application`
- Monorepo: no
- Purpose (from docs): Dictate

A local dictation app for Windows with two modes:

- **Quick Dictate** — press a global hotkey, speak, paste into any text box (Wispr Flow style)
- **Clinical Session** — record full appointments (up to 2 hours), transcribe locally, generate AI answer sheets from clinical note templates

No cloud transcription. OpenAI is used **only** for clinical answer sheet generation.

## Req



## Required inspection before changing code

1. Read this file and `PROJECT.md`.
2. Inspect relevant source files for the requested change.
3. Prefer existing scripts in package manifests / Makefiles / CI over invented commands.
4. Do not invent deployment or infrastructure steps without repository evidence.

## Allowed changes

- Source, tests, and configuration required to implement the requested task.
- Documentation when the task explicitly asks for docs, or when updating operating docs via an approved docs PR.

## Restricted changes

- Do **not** commit secrets, tokens, private keys, or production credentials.
- Do **not** create placeholder implementation files (`AUTOMATION_NOTES.md`, `RETRY_*.md`, task-description copies).
- Do **not** skip required validation when scripts exist.
- Do **not** open a pull request without meaningful repository changes.
- Do **not** deploy or merge to protected/default branches without explicit approval.
- Do **not** modify generated build artifacts unless the task requires it.

## Coding conventions

- Languages: python
- Frameworks: none detected
- Package managers: pip/poetry

## Required validation

- Tests: Unknown — requires repository owner confirmation.
- Typecheck: Unknown — requires repository owner confirmation.
- Lint: Unknown — requires repository owner confirmation.
- Build: Unknown — requires repository owner confirmation.

## Branch / PR expectations

- Use a dedicated feature/fix/docs branch — never commit directly to the default branch.
- PR descriptions must summarize real changes and validation performed.
- Documentation-only PRs must not modify runtime source unless requested.

## Deployment restrictions

- Unknown — requires repository owner confirmation.


---

## Evidence & review

- Project type: `python-application`
- Languages: python
- Generated from repository inspection (not guessed from external context).
- Evidence paths:
  - `requirements.txt`
  - `README.md`
- Last review: automated ARTI repository intelligence
