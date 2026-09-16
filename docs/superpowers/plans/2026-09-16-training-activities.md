# Training Activities Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add typed strength/cardio training, steps, equipment choices, AI exercise metadata, and safe deletion while preserving existing history.

**Architecture:** Expand the existing Django models rather than replacing strength records. Plan validation dispatches by exercise type, sessions own either sets or cardio logs, and archive v2 accepts legacy v1 input. Exercise deletion is archival; mutable log deletion is hard deletion with ownership checks.

**Tech Stack:** Django 5.2, server-rendered templates, small vanilla JavaScript plan editor, Pydantic structured AI output, PostgreSQL/SQLite tests.

**Spec:** `docs/superpowers/specs/2026-09-16-training-activities.md`

## Global Constraints

- Preserve every existing record and old archive import path.
- Every mutation is scoped to the signed-in user and POST-only.
- AI fills blank exercise metadata only.
- Cardio planning records minutes only.

---

### Task 1: Expand training and recovery data

**Files:** `core/models.py`, `core/migrations/`, `core/forms.py`, `core/test_flows.py`

**Interfaces:** Produces `StepEntry`, `WorkoutCardio`, `Exercise.activity_type`, `Exercise.archived`, `StepForm`, `CardioLogForm`, and a user-aware `ExerciseForm(user=...)`.

- [ ] Write tests proving existing exercises default to Strength, muscles may be blank, equipment choices contain only the current user's Settings values, and steps reject negative values.
- [ ] Run the focused tests and confirm they fail because the fields/models and user-aware choices do not exist.
- [ ] Add the additive models, form behavior and migration with existing exercises defaulted to Strength.
- [ ] Run the focused tests and migration checks until they pass.

### Task 2: Validate and instantiate typed plans

**Files:** `core/services.py`, `core/static/core/plan.js`, `core/templates/core/plan.html`, `core/templates/core/session.html`, `core/views.py`, `core/urls.py`, `core/test_flows.py`

**Interfaces:** `create_plan` accepts Strength prescriptions or `{exercise, day, minutes, order, notes}` Cardio prescriptions; `start_session` creates `WorkoutSet` or `WorkoutCardio` records.

- [ ] Write tests proving Cardio requires 1–1440 minutes, Strength keeps its range checks, archived exercises are rejected, and session creation/copy handles both record types.
- [ ] Run the focused tests and confirm the typed-plan expectations fail.
- [ ] Implement type-aware validation, session creation, cardio edit/completion, active-only choices, and dynamic plan fields.
- [ ] Run the focused tests and verify both activity paths pass.

### Task 3: Replace Body cardio with steps and expose safe deletes

**Files:** `core/views.py`, `core/urls.py`, `core/templates/core/body.html`, `core/templates/core/workouts.html`, `core/templates/core/session.html`, nutrition templates, `core/test_flows.py`

**Interfaces:** `record_delete(request, kind, pk)` hard-deletes owned mutable logs; `exercise_archive` archives owned exercises; legacy cardio appears read-only under Training.

- [ ] Write tests for POST-only ownership-protected deletes, photo-file cleanup, exercise archival with retained workout history, and steps shown on Body while legacy cardio appears under Training.
- [ ] Run the focused tests and confirm the routes/UI behavior are absent.
- [ ] Add the routes, ownership mapping, cleanup behavior and compact delete/archive forms to relevant pages.
- [ ] Run the focused tests and verify unauthorized/cross-user requests cannot mutate data.

### Task 4: Fill blank exercise metadata with AI

**Files:** `coaching/models.py`, `coaching/migrations/`, `coaching/schemas.py`, `coaching/router.py`, `coaching/services.py`, `coaching/tests.py`, `core/views.py`

**Interfaces:** `enqueue_exercise(user, exercise)` creates a deduplicated `exercise` job with a snapshot; `run_job` applies only blank aliases/muscle/classification fields when the snapshot still matches.

- [ ] Write tests for enqueue-on-blank, structured schema rejection, blank-only application, stale edit rejection and full-metadata no-enqueue.
- [ ] Run the focused tests and confirm the exercise coaching task is absent.
- [ ] Add the task/schema/job application and enqueue it after exercise save.
- [ ] Run coaching and core focused tests until they pass.

### Task 5: Preserve archives across schema versions

**Files:** `core/archive.py`, `core/test_archive.py`

**Interfaces:** `export_archive` emits schema v2; `validate_archive` accepts v1/v2 and supplies safe defaults for fields/models absent from v1.

- [ ] Write tests for v1 exercise import defaults and v2 Step/Cardio/exercise round-trip.
- [ ] Run archive tests and confirm v2/new-model cases fail.
- [ ] Implement schema-aware expected fields, defaults, semantic validation and dependency ordering.
- [ ] Run archive tests and full Django suite.

### Task 6: Production verification and deployment

**Files:** `docs/verification.md`, deployment checkout on `192.168.1.48`

**Interfaces:** Production migration and routing for the verified GPT candidate.

- [ ] Run all tests, deployment checks and migration drift checks locally.
- [ ] Commit the reviewed change and deploy the exact revision with the established Compose procedure.
- [ ] Configure the exercise task route to the already verified GPT model without printing credentials.
- [ ] Verify migration state, health, authenticated Strength/Cardio/Steps/delete flows, AI exercise completion, backup and restore test, then record evidence.
