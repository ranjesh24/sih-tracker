# CLAUDE.md

Entry point for Claude Code working in this repository. Read this first, every session.

---

## What this is

**Marg** — a city-wide vehicle trajectory reconstruction system for Smart India Hackathon 2026, problem statement **SIH26127**.

It tracks vehicles across multiple non-overlapping CCTV cameras and reconstructs their route on a map. It does this by fusing three signals: number plate reads (ANPR), visual appearance embeddings (Re-ID), and a spatio-temporal feasibility gate that rejects matches violating the physics of road travel.

**The deliverable is a presentation with a live demo, not deployed software.** This is the most important fact about the project. It means the prototype needs to be convincing, not complete. Production hardening is not a goal and time spent on it is time lost.

**Timeline:** 6 days, Monday through Saturday, presenting Saturday. Team of 4.

---

## Read these before writing anything

Specifications live in `docs/`. They are the source of truth. Code that contradicts them is a defect.

| File | Read it when |
|---|---|
| `docs/rules.md` | **Always. Every session, before any code.** |
| `docs/prd.md` | Understanding what a feature is for, or checking an acceptance criterion |
| `docs/techspec.md` | Any dependency, endpoint, auth, or config question |
| `docs/schema.md` | Anything touching the database |
| `docs/appflow.md` | Any frontend route, state, error, or empty state |
| `docs/design.md` | Any UI work at all |
| `docs/implementationplan.md` | Understanding phase order and verification gates |
| `docs/tracker.md` | **Before starting and after finishing any task** |

Do not work from a task title alone. Read the section that governs it.

---

## The five rules

Full text in `docs/rules.md` §1. Summarised because they matter most:

1. **Spec first.** Never write code contradicting the specs. If a spec is wrong, say so, propose the change, wait, then update the spec before the code.
2. **Zero-hallucination packages.** Only dependencies listed in `techspec.md` §2. Do not invent packages. Do not invent methods on packages that exist — `ultralytics`, `paddleocr`, and `torchreid` have all changed APIs between versions.
3. **Defensive coding.** Validate at every boundary. Pydantic on the backend, typed responses on the frontend. No bare `except:`. No `any`. Fail at startup, not on frame 400.
4. **Update the tracker.** After every file modification, in the same response. State which task ID moved and to what.
5. **Do not break the demo path.** Pipeline start → trajectory with a bridged plate failure. Everything else is negotiable.

---

## Architecture in one screen

```
ml-pipeline/  (Python 3.11, PyTorch, CUDA — heavy venv)
   one worker process per camera
   frame → YOLOv8n → ByteTrack → tracklet
   tracklet ends → best-shot → plate OCR + OSNet 512-D embedding
   → POST /api/v1/ingest/sightings
                    │
                    ▼
backend/      (Python 3.11, FastAPI — lightweight venv)
   IdentityResolver
     tier 1  plate match (rapidfuzz + OCR confusion map)
     tier 2  camera_graph.feasible_candidates() generates the candidate set;
             vision (cosine) ranks within it; FAISS optimises over that set
     gate    SpatioTemporalGate (networkx camera graph)  ← the differentiator
     tier 3  new identity
   → SQLite write → WebSocket broadcast
                    │
                    ▼
frontend/     (Node 22, React 19, Vite, TypeScript)
   camera wall · Leaflet trajectory map · evidence panel · search · admin
```

Three isolated environments. `ml-pipeline/` and `backend/` have separate virtualenvs; `frontend/` has its own `node_modules`. Keep it that way — it is why a PyTorch upgrade cannot break the API server.

---

## The thing that makes this project novel

**The spatio-temporal feasibility gate.**

MTMC research exists. Indian ANPR implementations exist in quantity. Nobody has publicly combined them, and the reason combining them is hard is the "White Maruti" problem: Indian roads carry thousands of visually identical vehicles, and an appearance embedding cannot distinguish two white hatchbacks of the same model.

The gate solves this with physics rather than better embeddings. If Camera A and Camera B are 5 km apart with a realistic transit window of 6 to 25 minutes, a visually identical vehicle appearing at B fourteen seconds after A is not the same vehicle — regardless of how high the cosine similarity is.

Concretely:

- `camera_edges` (`schema.md` §3.4) stores distance and min/max transit time per road segment.
- `camera_graph.py` loads it into networkx and sums transit windows along shortest paths.
- `spatiotemporal_gate.py` rejects infeasible candidates before scoring.
- `match_decisions` (`schema.md` §3.7) persists **every rejection with its reason and numbers**.

That last point is what makes the demo work. The evidence panel shows "matched at 0.91 visual similarity, rejected: 5.2 km apart in 14 seconds, minimum feasible 312 s". A rejection an operator can inspect is more persuasive than a match with a high score.

**If you are touching the resolver, the gate, or the decisions table, be careful. This is the part that wins the round.**

---

## Failure mode to watch for

The gate can sit completely inert while everything appears to work. Trajectories render, matches happen, the demo looks fine — and the differentiating component was never actually invoked, because the topology was not loaded or the transit windows were too permissive to constrain anything.

Check it explicitly:

```sql
SELECT visual_score, elapsed_seconds, min_transit_seconds, rejection_reason
FROM match_decisions
WHERE rejection_reason = 'TEMPORAL_TOO_FAST'
ORDER BY visual_score DESC LIMIT 5;
```

If this returns nothing, something is wrong. This is GATE-205 in `tracker.md` and it is the single most likely silent failure in the build.

---

## Commands

```bash
# Backend
cd backend && source venv/bin/activate
uvicorn app.main:app --reload                    # localhost:8000
alembic upgrade head
python scripts/seed_users.py
python scripts/seed_cameras.py
pytest -v --cov=app/services

# ML pipeline
cd ml-pipeline && source venv/bin/activate
python scripts/download_models.py                # run once, before going offline
python scripts/run_worker.py --camera CAM-01 --visualize
python scripts/run_all_workers.py

# Frontend
cd frontend
pnpm install
pnpm dev                                         # localhost:5173
pnpm build && pnpm lint

# Full demo
./scripts/demo.sh                                # all workers + backend + frontend
./scripts/reset_demo.sh                          # clear data, keep cameras and users
```

---

## Non-obvious things that will cost you time

**SQLite foreign keys are off by default.** Every `ON DELETE` rule in `schema.md` is inert without `PRAGMA foreign_keys=ON` per connection. The listener is in `backend/app/db/session.py` (`schema.md` §5). Verify with `PRAGMA foreign_keys;` returning 1.

**`pip install torchreid` gets the wrong package.** PyPI's `torchreid` 0.2.5 is not the library. Use `pip install git+https://github.com/KaiyangZhou/deep-person-reid.git`.

**Do not use passlib.** `passlib` 1.7.4 reads `bcrypt.__about__.__version__`, which bcrypt 5 removed, and the combination raises on import. Call the `bcrypt` package directly.

**Pin opencv 4.9.0.80, not the 5.x line.** OpenCV 5 changed Python API defaults and every reference you will search for assumes 4.x.

**Ultralytics YOLOv8 is AGPL-3.0.** Fine for a hackathon and an open repository. Not fine for closed commercial use. Know this before a judge asks. The detector sits behind an interface and an Apache-2.0 alternative drops in.

**Embeddings are normalised exactly once**, in `encode_embedding` (`schema.md` §4). Normalising twice, or not at all, produces similarity scores that are subtly wrong and very hard to notice.

**FAISS is not concurrent-safe** for simultaneous add and search. Ingest is serialised behind one async lock. Do not remove it.

**Worker clocks must share an epoch.** All workers offset their synthetic timestamps from a common start time. Drift produces false `TEMPORAL_TOO_FAST` rejections that look exactly like a matching bug. `received_at` exists on `sightings` purely to detect this.

**The demo must run offline** (requirement D-6). Local map tiles in `frontend/public/tiles/`, self-hosted fonts in `frontend/public/fonts/`, model weights pre-downloaded. No CDN links, no external API calls at runtime. Venue wifi fails; plan for it.

---

## Design constraints

Full system in `docs/design.md`. The hard prohibitions, because they are absolute:

- **No purple, violet, indigo, or magenta.** Anywhere.
- **No gradients** except one functional fade over camera-tile text.
- **No glassmorphism**, no `backdrop-filter`.
- **No emoji.** Not in UI, toasts, comments, or commit messages.
- **No terracotta near `#D97757`** and no cream near `#F4F1EA`. Both are recognisable AI-design signatures.
- **No all-caps labels**, no tracked-out eyebrows, no `→` appended to button text.
- **No raw hex outside `styles/tokens.css`.**

The palette derives from Indian vehicle registration plates and road signage — sign green as the accent, amber for uncertainty, oxide red for rejection. Dark, dense, quiet. It is a control-room instrument, not a product landing page.

---

## Working style

- **Ranked recommendations over balanced option lists.** If asked which approach, say which one and why, then note the alternative.
- **Honest feasibility over optimism.** If something will not work in the time available, say so immediately. A wrong assumption caught in a question costs thirty seconds; caught at gate 2 it costs an evening.
- **Say what is incomplete.** If something is stubbed, untested, or partially implemented, state it explicitly. Never present partial work as finished.
- **Ask when uncertain** rather than guessing at a name, a path, or an API.

---

## Current state

Check `docs/tracker.md`. It is the live status of every task.

Phase order is defined in `docs/implementationplan.md`. Do not start a phase before the previous phase's gate block is fully `[x]`. Gates are verified by running the commands, not by inspection.
