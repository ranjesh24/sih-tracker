# rules.md — Development Rules

**Project:** Marg (SIH26127)
**Version:** 1.0
**Applies to:** every contributor, human and AI

These rules exist because four people and an AI agent are writing one codebase in six days. Consistency is not aesthetic preference here — it is what makes the code readable by someone who did not write it, at 11 p.m., under pressure.

---

## 1. The Five Hard Rules

Violating any of these is a defect regardless of whether the code works.

### R1 — Spec first

**Never write code that contradicts the specification documents.**

`prd.md`, `techspec.md`, `schema.md`, `appflow.md`, and `design.md` are the source of truth. If the code and the spec disagree, the code is wrong.

If a spec is genuinely wrong or incomplete:

1. Stop.
2. Say what the conflict is and which document governs.
3. Propose the change to the spec.
4. Wait for a decision.
5. Update the spec, then write the code.

Do not "improve" a specified design silently. A column name that differs from `schema.md`, an endpoint path that differs from `techspec.md` §5.4, a colour that is not in `design.md` §4 — each is a defect, and each one costs someone else an hour of confusion.

### R2 — Zero-hallucination packages

**Only use dependencies explicitly listed in `techspec.md` §2.**

- No `pip install` of a package not in the spec's tables.
- No `pnpm add` of a package not in the spec's tables.
- No importing a library because it seemed available.
- If a task genuinely needs a new dependency: stop, state which one and why, get agreement, add it to `techspec.md` **and** to the requirements file, then use it.

This rule catches a specific and common AI failure: writing code that imports a plausible-sounding package that does not exist, or that exists but is not installed. The import looks reasonable, the code looks correct, and it fails at runtime in a way that reads as an environment problem.

Corollary: **do not invent APIs on packages that are installed.** If unsure whether a method exists, check the installed version rather than assuming. `ultralytics`, `paddleocr`, and `torchreid` have all changed their APIs between versions, and training data is not a reliable guide to the version pinned here.

### R3 — Defensive coding

**Validate at every boundary. Fail loudly and early.**

- Every request body is a Pydantic model. No handler reads `request.json()` directly.
- Every external input — OCR output, video frames, worker payloads — is validated before use.
- Every function that can fail returns a typed result or raises a typed exception. No silent `except: pass`.
- Every `except` block names the exception class it catches. Bare `except:` is forbidden.
- Model weights, config values, and file paths are validated at startup, not at first use. A missing weight file must fail when the worker starts, not on frame 400 (`appflow.md` §6.4).
- Frontend: every API response is typed. No `any`. No unchecked `as`.

### R4 — Update the tracker

**Update `tracker.md` after every file modification, in the same response.**

Move the status symbol, add the timestamp, state in the response which task ID moved and to what. See `tracker.md`'s agent instructions for format.

A tracker written at the end of a session is written from memory and is wrong.

### R5 — Do not break the demo path

**The path from "start the pipeline" to "show a trajectory with a bridged plate failure" must work at all times.**

Before committing anything that touches `identity_resolver.py`, `spatiotemporal_gate.py`, `vector_index.py`, the ingest endpoint, or the trajectory endpoint, run the end-to-end check from `implementationplan.md` gate 2. If it breaks, fix it before moving on.

Everything else in the system is negotiable. This path is not.

---

## 2. File Organisation

Follow `techspec.md` §8 exactly. Do not create directories that are not in it.

### Where things go

| Content | Location |
|---|---|
| Business logic | `backend/app/services/` |
| Database access | `backend/app/repositories/` |
| Route handlers | `backend/app/api/v1/` |
| Request/response models | `backend/app/schemas/` |
| Database models | `backend/app/models/` |
| Cross-cutting concerns | `backend/app/core/` |
| React pages | `frontend/src/pages/` |
| Reusable components | `frontend/src/components/` |
| Data-fetching hooks | `frontend/src/hooks/` |
| Client state | `frontend/src/stores/` |
| Utilities | `frontend/src/lib/` |

### Layering — enforced

```
routes → services → repositories → models
```

- A route handler contains no business logic. It validates, calls a service, and shapes a response.
- A service contains no SQL and no ORM query. It calls repositories.
- A repository contains no business logic. It queries and returns models.
- No layer imports upward. A service never imports from `api/`.

This is the rule that makes NFR-SC2 real — swapping SQLite for PostgreSQL means changing `repositories/` and nothing else. It is also what lets services be unit tested without a database.

### Size limits

- Python file: 400 lines. Longer means it is doing more than one thing.
- React component: 200 lines. Longer means it should be split.
- Function: 50 lines. Longer means extract.

`identity_resolver.py` is the one permitted exception, and only for the resolution algorithm itself. Its helpers still live in separate modules.

### Directory ownership

| Owner | Directory |
|---|---|
| V | `ml-pipeline/` |
| B | `backend/` |
| F | `frontend/` |
| D | `scripts/`, `datasets/` |

Changes crossing a boundary go through the owner. This single rule eliminates most merge conflicts on a four-person week.

---

## 3. Python Conventions

### Naming

| Thing | Convention | Example |
|---|---|---|
| Module | `snake_case` | `identity_resolver.py` |
| Class | `PascalCase` | `SpatioTemporalGate` |
| Function, variable | `snake_case` | `resolve_identity` |
| Constant | `SCREAMING_SNAKE_CASE` | `VISUAL_FLOOR` |
| Private | leading underscore | `_compute_fused_score` |
| Boolean | `is_`, `has_`, `can_` prefix | `is_active`, `has_valid_plate` |
| Collection | plural | `sightings`, `candidate_vehicles` |
| Timestamp | `_at` suffix | `first_frame_at` |
| Duration | `_seconds`, `_ms` suffix | `min_transit_seconds` |
| Distance | `_m`, `_km` suffix | `distance_m` |

Units in names are not optional. `distance` is ambiguous; `distance_m` is not, and the ambiguity is exactly how a metres-versus-kilometres bug enters the feasibility gate and produces rejections nobody can explain.

### Style

- Format with `ruff format`. Line length 100.
- Lint with `ruff check`. Fix everything it reports.
- **Type hints on every function signature.** Parameters and return type, no exceptions.
- Imports in three groups, blank line between: standard library, third party, local. `ruff` enforces the order.
- f-strings for interpolation. No `%` or `.format()`.
- `pathlib.Path` for paths. No string concatenation, no `os.path.join`.
- Datetimes are always timezone-aware UTC. `datetime.now(timezone.utc)`, never `datetime.now()`.

### Docstrings

Public functions in `services/` get a docstring stating what, arguments, returns, and raises. Everything else gets a docstring only where the code is not self-evident.

```python
def gate(
    from_camera_id: str,
    to_camera_id: str,
    elapsed_seconds: int,
) -> GateResult:
    """Decide whether a transit between two cameras is physically feasible.

    Args:
        from_camera_id: Camera of the earlier sighting.
        to_camera_id: Camera of the later sighting.
        elapsed_seconds: Seconds between the two sightings, from first_frame_at.

    Returns:
        GateResult with passed, reason, and the numeric values behind the
        decision, so the reason can be shown to an operator.

    Raises:
        CameraNotFoundError: If either camera is absent from the graph.
    """
```

The comment worth writing is the one explaining *why*, not *what*. `# increment counter` above `counter += 1` is noise. `# 8 km/h floor: Indian city traffic genuinely averages single digits during congestion` is the reason someone will not "fix" the constant six months later.

### Errors

Define typed exceptions in `backend/app/core/exceptions.py`, each mapping to an error code from `techspec.md` §5.3.

```python
class MargError(Exception):
    code: str = "INTERNAL_ERROR"
    status_code: int = 500

class SpatioTemporalRejectedError(MargError):
    code = "SPATIOTEMPORAL_REJECTED"
    status_code = 422
```

The global handler converts these to the error envelope. Route handlers do not build error responses by hand.

Never catch broadly:

```python
# Wrong
try:
    result = resolve(sighting)
except Exception:
    return None

# Right
try:
    result = resolve(sighting)
except EmbeddingDimensionError as exc:
    logger.error("Embedding dimension mismatch", extra={"sighting_id": sighting.id})
    raise
```

### Configuration

Every tunable value lives in `backend/app/core/config.py` or `ml-pipeline/src/config.py`, loaded from the environment via `pydantic-settings`.

**No magic numbers in logic.** A threshold, weight, window, or limit that appears as a literal in a function body is a defect. Every one of these will be tuned against real footage during Phase 3, and a hardcoded value is one that cannot be changed without a code edit and a restart at 11 p.m. on Friday.

```python
# Wrong
if cosine_similarity >= 0.55:

# Right
if cosine_similarity >= settings.VISUAL_FLOOR:
```

### Logging

```python
logger.info("Sighting resolved", extra={
    "sighting_id": sighting.id,
    "vehicle_id": vehicle.id,
    "method": "VISUAL",
    "score": 0.88,
})
```

- Structured, with an `extra` dict. Not interpolated prose.
- `request_id` on every backend log line.
- Never log passwords, tokens, the ingest key, or full plate text at `INFO`.
- `DEBUG` for per-frame detail, `INFO` for per-sighting, `WARNING` for recoverable, `ERROR` for failures needing attention.

---

## 4. TypeScript and React Conventions

### Naming

| Thing | Convention | Example |
|---|---|---|
| Component file | `PascalCase.tsx` | `TrajectoryMap.tsx` |
| Hook file | `camelCase.ts`, `use` prefix | `useTrajectory.ts` |
| Utility file | `camelCase.ts` | `formatTimestamp.ts` |
| Component | `PascalCase` | `MatchExplanation` |
| Hook | `use` prefix | `useLiveEvents` |
| Type, interface | `PascalCase` | `SightingRead` |
| Constant | `SCREAMING_SNAKE_CASE` | `MAX_EVENT_ROWS` |
| Event handler | `handle` prefix | `handleConfirmClick` |
| Handler prop | `on` prefix | `onConfirm` |
| Boolean prop | `is`, `has`, `can` prefix | `isLoading` |

### Types

- **`any` is forbidden.** `unknown` plus narrowing where the type is genuinely unknown. Lint enforces this (E-3).
- `type` for unions and object shapes, `interface` only for extensible contracts.
- API types are generated from FastAPI's OpenAPI schema into `src/types/api.ts`. Do not hand-write a type that mirrors a backend model — it will drift.
- No non-null assertion (`!`) except immediately after an explicit check the compiler cannot see. Comment why.

### Components

- Function components only. No classes except a single error boundary.
- One exported component per file. Small sub-components used only by that component may live in the same file below it.
- Props destructured in the signature with an inline or named type.
- No default exports except for pages, where the router requires them.

```tsx
type ConfidenceBadgeProps = {
  status: MatchStatus;
  score?: number;
};

export function ConfidenceBadge({ status, score }: ConfidenceBadgeProps) {
  // ...
}
```

### State

- Server state: React Query. Never `useEffect` plus `useState` to fetch.
- Client state: Zustand, one store per domain (`authStore`, `liveStore`, `uiStore`).
- Local state: `useState`.
- **Never `localStorage` or `sessionStorage` for the access token** (NFR-S2).

### Styling

- Tailwind utilities only, referencing tokens through the theme.
- **No raw hex values outside `styles/tokens.css`.** Enforced by grep in TASK-402.
- No inline `style` except for genuinely dynamic values — a map marker's computed position, a polyline colour derived from a vehicle hash.
- `cn()` from `lib/cn.ts` (clsx + tailwind-merge) for conditional classes. No string concatenation of class names.
- Every rule in `design.md` §3 applies. No purple. No gradients except the tile fade. No `backdrop-filter`. No emoji.

### Data fetching

```tsx
export function useTrajectory(vehicleId: string) {
  return useQuery({
    queryKey: ["trajectory", vehicleId],
    queryFn: () => api.get<TrajectoryRead>(`/vehicles/${vehicleId}/trajectory`),
    staleTime: 30_000,
  });
}
```

- Query keys are arrays, most general segment first.
- Every hook handles loading, error, and empty explicitly. A component that renders only the success case is incomplete.
- Mutations invalidate the queries they affect.

---

## 5. API Contract Rules

- Every endpoint in `techspec.md` §5.4 is implemented at exactly the specified path and method. No additions without a spec update.
- Every list response uses the envelope from §5.2. Every single-resource response is unwrapped.
- Every error uses the envelope from §5.3, generated by the global handler.
- Every timestamp crossing the wire is ISO-8601 UTC with `Z`. The frontend converts to local time at render only.
- Every protected endpoint declares its role dependency. The default is authenticated; privileged is explicit.
- Response models are separate from database models. A `Sighting` (SQLModel) is never returned directly — a `SightingRead` (Pydantic) is. This is what prevents a schema change from silently altering the API and what makes role-based plate masking possible in one place.

---

## 6. Testing Rules

### What must be tested

| Module | Requirement |
|---|---|
| `spatiotemporal_gate.py` | Every rejection reason, plus multi-hop paths. Near 100%. |
| `identity_resolver.py` | Every tier, ambiguity margin, new-identity path. Near 100%. |
| `plate_matcher.py` | Exact, fuzzy, every confusion pair, non-match. |
| `normalizer.py` | Real OCR failure strings, valid and invalid plates. |
| `vector_index.py` | Add, search, rebuild, dimension mismatch. |
| `camera_graph.py` | Path finding, no path, window summation. |
| Auth | Login, refresh rotation, reuse detection, role enforcement. |
| Everything else | Best effort. Coverage target is 70% on `services/` overall (E-2). |

### How

- `pytest`. Test files mirror the source tree: `tests/unit/test_spatiotemporal_gate.py`.
- One behaviour per test. Names describe the behaviour: `test_rejects_when_elapsed_below_min_transit`.
- Arrange, act, assert, with blank lines between.
- Fixtures in `conftest.py`. In-memory SQLite for integration tests.
- No network calls in tests. No model loading in unit tests — mock the embedder.

The gate and the resolver are heavily tested because they are where correctness lives and because a bug in either presents as a model quality problem rather than a logic error. That is the most expensive kind of bug to diagnose under time pressure.

---

## 7. Git Rules

### Branches

`main` plus `feat/<role>-<topic>`:

```
feat/backend-identity-resolver
feat/frontend-evidence-panel
feat/ml-plate-ocr
```

No direct pushes to `main`. Squash merge.

### Commits

```
<type>(<scope>): <subject>

[optional body]

[TASK-xxx]
```

Types: `feat`, `fix`, `refactor`, `test`, `docs`, `chore`.

```
feat(backend): add spatio-temporal feasibility gate

Rejects candidate matches whose elapsed time falls outside the summed
transit window along the shortest path between cameras. Records the
reason and the numeric values so the rejection can be shown to an operator.

[TASK-118]
```

- Subject in imperative mood, under 72 characters, no trailing period.
- Reference the task ID. This is how `tracker.md` and the commit history stay connected.
- **No emoji in commit messages.**

### Before pushing

1. `ruff check` and `ruff format` clean, or `pnpm lint` clean.
2. Tests pass.
3. `tracker.md` updated.
4. If the change touched the demo path, the gate 2 check was run.

---

## 8. Security Rules

- **No secret in the repository, ever.** Not in code, not in a comment, not in a test fixture, not in an example. `.env.example` carries names and obvious placeholders only.
- Never log a password, token, ingest key, or full plate text at `INFO` or above.
- Every state-changing endpoint enforces its role server-side. UI hiding is not access control.
- Every user input is validated by Pydantic or Zod before it reaches business logic.
- No string-interpolated SQL. SQLModel and SQLAlchemy parameterise; keep it that way.
- Compare the ingest key with `secrets.compare_digest`, never `==`.
- CORS lists the configured frontend origin explicitly. Never `*`.

---

## 9. Rules Specific to the AI Agent

### Before writing code

1. Read the governing spec section. Do not work from the task title alone.
2. Check whether the file exists. Edit rather than recreate.
3. Check `tracker.md` for whether the task is already in progress.
4. Confirm every import is a dependency listed in `techspec.md` §2.

### While writing

5. Match the conventions in this document exactly. Consistency matters more than any individual preference.
6. Use the exact names in `schema.md` and the exact paths in `techspec.md` §5.4. A close-enough name is a defect.
7. Do not add features not in the spec. An unrequested extra endpoint is scope creep, and scope creep on a six-day build is how the demo does not get rehearsed.
8. Do not add a dependency without asking.

### After writing

9. Update `tracker.md` in the same response.
10. State plainly what was implemented, what was not, and what remains untested.
11. If something was left incomplete or stubbed, say so explicitly. Do not present a partial implementation as finished.

### When uncertain

12. **Ask rather than guess.** A wrong assumption caught in a question costs thirty seconds; caught at gate 2 it costs an evening.
13. When two specs conflict, say which two and which section, and stop.
14. When a requirement seems wrong, say why and propose an alternative. Do not silently implement something different.
15. Never invent a library method to make code look complete. If unsure whether an API exists, say so and check.

### What never to do

16. Never claim a test passes without running it.
17. Never claim something is complete when it is stubbed.
18. Never write `# TODO` and mark the task `[x]`.
19. Never modify a spec document to match code that was already written. The spec changes first, deliberately, or not at all.
20. Never delete or renumber a task in `tracker.md`.

---

## 10. Definition of Done

A task is done when all of these are true:

- [ ] Code written, runs without error.
- [ ] Matches the governing specification.
- [ ] Acceptance criteria met, where the task references one.
- [ ] Tests written and passing, where §6 requires them.
- [ ] Lint and format clean.
- [ ] No new dependency added outside `techspec.md` §2.
- [ ] No hardcoded value that belongs in config.
- [ ] Errors handled at every boundary.
- [ ] `tracker.md` updated with status and timestamp.
- [ ] Merged to `main`, and `main` still runs.
- [ ] Demo path still works, if the change touched it.
