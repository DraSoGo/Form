# Training Activities Design

## Goal

Unify strength and cardio planning under Training, replace Body cardio entry with daily steps, source exercise equipment from Settings, let AI fill blank exercise metadata, and add safe deletion without losing workout history.

## Accepted behavior

- Exercises are either Strength or Cardio. Existing exercises become Strength.
- Strength plan items retain sets, reps, rest, RIR and RPE. Cardio plan items require duration in minutes only.
- Starting a planned session creates strength sets and cardio logs from their matching plan items.
- Body & recovery records daily steps instead of new cardio entries.
- Existing legacy cardio entries remain readable under Training and remain importable.
- Exercise equipment is chosen from the signed-in user's Settings equipment. The stored label remains text so deleting an equipment option cannot corrupt history.
- Aliases and muscle fields are optional. Saving an exercise with missing metadata queues AI analysis. AI fills only blank metadata and never overwrites user-entered values.
- Deleting an exercise archives it. Archived exercises disappear from new plan/session choices while historical sets and plans remain readable.
- User-owned mutable records expose POST-only delete actions. Versioned targets and plans are retained as history.
- JSON archive schema v2 exports the new fields and records; schema v1 remains importable with safe defaults.

## Data design

- `Exercise.activity_type`: `strength` or `cardio`; default `strength`.
- `Exercise.archived`: boolean; default false.
- `StepEntry`: date, positive step count, note.
- `WorkoutCardio`: session, exercise, order, minutes, completed, notes.
- Existing `CardioEntry` is retained as legacy history.
- Coaching adds `exercise` as a structured task with a bounded metadata schema.

## Safety and rollback

The migration only adds columns/tables. Rollback can run the previous application against the expanded database because existing columns are unchanged. Archived exercises and legacy cardio are never destructively migrated. Archive v1 import supplies `strength` and `archived=false`; archive v2 includes all new data.

## Non-goals

- Distance, pace, heart rate and calorie estimates for cardio.
- Automatic deletion of versioned plans or targets.
- Rewriting historical plan JSON.
