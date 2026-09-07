# AGENTS.md — anime-list-web

## Environment and commands

- **Primary OS**: Windows (PowerShell/Warp).
- **Python**: 3.12 (`.python-version`).
- **Package manager**: `uv` (uses `uv.lock`).
- **Install/sync**: `uv sync` (use `uv sync --refresh` only when a metadata refresh is needed).
- **Framework**: Reflex.
- **Lint/fix**: `ruff check --fix .`
- **Do not use**: `pip`, manual `venv`, or `requirements.txt` as source of truth.
- **No global package installation** — everything through the project-local uv environment.

## Architecture

```
anime-list-web          (Reflex frontend)
       │ HTTP/JSON
       ▼
anime-list-api          (FastAPI backend — source of truth)
       │
       ▼
    MongoDB
```

- `anime-list-web` is the frontend/web application.
- `anime-list-api` is the backend and source of truth.
- Communication with the backend is HTTP/JSON only.
- **Never connect directly to MongoDB** from the frontend.
- **Never duplicate backend business logic** in the frontend.
- **Never introduce repositories, ORM layers, or another persistence layer.**
- Centralize backend communication in a dedicated API client/service boundary (`app/services/`).
- Use typed/Pydantic models where they provide a clear API contract.
- Prefer simple solutions over unnecessary abstraction.

## Authentication and security

- Authentication is provided by the existing FastAPI backend.
- Use the backend's existing JWT access-token and refresh-token mechanism.
- **Do not introduce a second authentication system.**
- **Do not use Reflex Enterprise/OIDC authentication** for this application.
- JWTs are opaque to the frontend; the frontend must not implement JWT validation or duplicate backend authentication logic.
- Access and refresh tokens remain in backend-only Reflex State.
- **Do not store authentication tokens in LocalStorage or SessionStorage** unless this architectural decision is explicitly revisited.
- The backend remains responsible for authentication and authorization.
- Frontend permission checks are only for UX and conditional UI.
- **Never treat frontend navigation guards as a security boundary.**
- **Never bypass backend authorization.**
- Do not expose secrets or tokens in logs.

### Secret Handling

- Real secret values must never be read, exposed, copied, or modified.
- `.env` files and other secret-bearing files are always out of scope.
- When inspecting another repository, agents may inspect source code, schemas, tests, documentation, and `.env.example` files when necessary, but must not inspect real secret values.
- Credentials must never be retrieved merely because they are accessible.
- Secrets must never appear in reports, logs, diffs, commits, or generated files.

## Reflex State

- Reflex State is server-side and scoped to the user session.
- Sensitive authentication values belong in backend-only State variables.
- Avoid module-level/global mutable state for user sessions.
- Event handlers should remain focused and explicit.
- Use async event handlers for asynchronous API communication.
- Background events should only be used for genuinely long-running or concurrent work, not ordinary API requests.
- Do not put large amounts of business logic inside UI components.

## API communication

- Use async `httpx` for backend HTTP communication.
- API calls are centralized in `app/services/`, not scattered throughout components/pages.
- The API client handles authentication headers and the established refresh/retry flow:
  - A failed access-token request may trigger refresh and one retry.
  - If refresh fails, the frontend invalidates the local session and requires login again.
  - Never retry authentication failures indefinitely.
- Backend response contracts must be respected. Frontend models may represent those API contracts for validation and typing, but must not introduce independent business rules.
- Timeouts and malformed/unexpected responses must be handled deliberately.

Do not implement the API client yet; this is an architectural rule only.

## Permissions

- Backend permissions are authoritative.
- Current backend permissions: `read`, `write`, `admin`.
- The frontend may use these permissions to control visibility and UX.
- **The frontend must never assume that hiding a control provides security.**
- Do not add or redefine permissions independently in the frontend.

## Project structure

```
app/
├── services/      # Backend/API communication, API models
├── state/         # Reflex state
├── pages/         # Page-level UI
├── components/    # Reusable UI components
└── config.py      # Application configuration
```

- Do not require every directory to exist immediately.
- Do not create abstractions merely to satisfy the structure.

## Configuration

- Configuration through environment variables/settings where appropriate.
- `.env` must **never** be committed.
- `.env.example` should document required configuration without real secrets.
- The backend API base URL must be configurable.
- Do not hard-code production URLs in application logic.
- Do not commit credentials, tokens, API secrets, or other sensitive values.

## Tests

- Tests should be deterministic and isolated.
- API client tests must mock HTTP responses.
- Tests must **not** depend on production services or production data.
- **Do not require MongoDB** for frontend tests.
- Test authentication/session behavior and API error handling at the appropriate layer.
- Do not ignore failing tests — investigate the cause before moving on.
- Avoid excessive end-to-end infrastructure unless it becomes necessary.

## Code quality

- Ruff rules: `E`, `W`, `F`, `I`.
- Line length: 100.
- Typed Python where practical.
- Explicit code over clever abstractions.
- Small functions and focused modules.
- Avoid unnecessary dependencies.
- Avoid premature architecture.
- Preserve readability and maintainability.
- **Do not introduce additional linters, type checkers, frameworks, state-management libraries, or infrastructure** unless a task explicitly requires them.

## Agent workflow

**Before modifying code**:

1. Inspect the relevant files and understand the context.
2. Check existing architecture and conventions.
3. Identify dependencies and possible side effects.
4. Make the smallest change that solves the task.
5. Important architectural decisions must be surfaced before implementation rather than silently introducing a new architecture.

**After modifying code**:

1. Run relevant tests.
2. Run `ruff check .`.
3. Review `git diff`.
4. Review `git status`.
5. Verify there are no unrelated changes.
6. Confirm the final diff contains only task-related changes.

## Git

- **No automatic commits** — leave changes ready for review.
- **No automatic push** — wait for explicit authorization.
- **Do not discard user changes** without authorization.
- **No destructive operations** (reset, checkout, clean) without authorization.
- **Do not rewrite history.**
- Review changes before considering a task complete.
- Do not assume the backend repository and frontend repository share Git history.

## Scope and limits

- Keep the frontend simple and maintainable.
- Do not overengineer.
- **Do not modify `../anime-list-api`** unless a future task explicitly requires a coordinated backend change and that change is explicitly authorized.
- Do not duplicate backend functionality merely because it is convenient from the frontend.
- Do not add infrastructure before there is a demonstrated requirement.
- When an architectural decision is unclear or conflicts with the established ADR, stop and present options before implementing.
