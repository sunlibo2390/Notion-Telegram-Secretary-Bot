# Docs Overview

[Chinese Version](README.md)

| File | Description |
| --- | --- |
| `user_manual.md` | End-user deployment & command manual (Chinese). English counterpart: `user_manual.en.md`. |
| `development_guide.md` | API contracts, workflows, and testing strategy (Chinese) → see `development_guide.en.md` for English. |
| `developer_overview.md` | High-level architecture and runtime flow (Chinese). English counterpart: `developer_overview.en.md`. |
| `telegram_architecture.md` | Telegram long-polling architecture details (Chinese). English counterpart: `telegram_architecture.en.md`. |
| `user_profile_doc*.md` | Persona documents (sensitive, ignored by git). |

## Suggested Reading Order
1. Need an architectural overview? Start with `developer_overview.en.md`, then `telegram_architecture.en.md`.
2. Building new features? Combine `development_guide.en.md` + `tests/` for API contracts and examples.
3. Deploying or onboarding users? Use `README.en.md` and `docs/user_manual.en.md` (Chinese originals are linked inside each doc).

## Editing Guidelines
- When updating a doc, keep both language versions in sync and cross-link them at the top.
- Double-check sensitive info: configs (`config/settings*.toml`), persona docs, and runtime data stay out of git.
