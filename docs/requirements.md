You are the lead engineer responsible for auditing, designing, implementing,
deploying, testing, and documenting a production-quality personal
Fitness & Nutrition AI web application on my existing home server.

IMPORTANT EXECUTION MODE
========================

This is an end-to-end autonomous implementation task.

Do NOT stop after the audit.
Do NOT stop after writing a plan.
Do NOT ask me to approve each phase.

Workflow:
1. Audit the existing infrastructure and codebase READ-ONLY first.
2. Decide the appropriate architecture and technology stack based on what is
   actually present on the server.
3. Break the project into implementation phases yourself.
4. Write the audit findings and implementation plan to documentation.
5. Immediately execute the phases sequentially.
6. Test and verify each phase before moving to the next.
7. Deploy the finished application.
8. Perform final end-to-end verification.
9. Produce final documentation and a concise completion report.

You may stop and ask me something ONLY when:
- a required credential/secret is unavailable,
- permissions make the requested action impossible,
- continuing would require a destructive/irreversible action against existing
  data or services and there is no safe alternative,
- or a requirement is genuinely impossible to infer safely.

Do not ask for approval merely because a new phase is starting.

Never destroy or unnecessarily modify existing services.

SERVER
======

SSH target:

    drasogo@192.168.1.48

This Ubuntu server is already running multiple Docker applications.

Known application area is around:

    /srv/docker/apps/

Existing services may include things such as:
- Nextcloud
- Immich
- Paperless-ngx
- OJ / grader
- Uptime Kuma
- other Docker services

DO NOT assume this list is complete.

Existing production services must continue working.

There is also a NAS / TrueNAS system used for storage and backups.
Known datasets visible previously include things such as:
- Backup
- server-backup
- nextcloud
- immich
- paperless

Do not touch existing datasets or files belonging to other applications.

I may also have previous Codex context in:

    codex resume 01a04e7c-0f63-79e1-8414-6d288a38de1c

Use existing context if available, but verify the current server state instead
of trusting stale assumptions.

============================================================
PHASE 0 — MANDATORY READ-ONLY INFRASTRUCTURE AUDIT
============================================================

Before writing or changing anything, inspect the server.

At minimum inspect:

- OS/version
- CPU/RAM/storage
- filesystem free space
- mounted filesystems
- NAS / SMB / CIFS mounts
- Docker version
- Docker Compose version
- docker ps
- docker networks
- docker volumes
- existing compose projects
- /srv/docker/apps structure
- ports currently in use
- firewall/UFW configuration
- Tailscale state
- Tailscale Serve / Funnel state if configured
- reverse proxy configuration if present
- HTTPS/public access currently used by existing services
- current Git repositories
- backup conventions
- application directory permissions
- databases already running
- logging/monitoring setup
- whether a shared PostgreSQL service already exists
- whether Redis or similar infrastructure already exists

Do not change anything during this audit.

Save findings to something similar to:

    docs/infrastructure-audit.md

Include:
- current architecture
- available resources
- conflicts/risks
- occupied ports
- storage strategy
- existing public-access method
- recommended application stack
- why that stack was chosen

Choose the technology stack AFTER this audit.

Do not blindly choose Next.js/FastAPI/etc. before inspecting the environment.

============================================================
APPLICATION GOAL
============================================================

Build a single-user personal web application that works as an:

    AI Personal Fitness & Nutrition Coach

It must help track:

- body composition
- nutrition
- food photographs
- workout plans
- actual workout sessions
- progressive overload
- cardio
- sleep
- gym equipment
- daily trends
- AI recommendations
- nutrition targets
- workout program changes

It must work well on mobile.

It must be installable as a PWA.

It does NOT need offline synchronization in this version.

============================================================
USER MODEL
============================================================

This is a SINGLE-USER application.

Do NOT implement public registration.

Authentication:
- Username + password
- No Google login
- No multi-user system
- No email password reset required for v1

Use secure password hashing, preferably Argon2id.

Authentication/session requirements:
- server-side authentication
- Secure cookies
- HttpOnly cookies
- SameSite protection
- CSRF protection where appropriate
- login rate limiting
- secure logout
- session expiration
- change-password screen

No password or AI API secret may ever be stored in frontend code,
localStorage, committed source code, or client-visible environment variables.

============================================================
BODY / HEALTH PROFILE
============================================================

Create an editable health/profile section.

User profile should support at least:

- age
- sex
- height
- fitness goal
- activity level if needed for calorie calculations

Body measurements must support historical entries with timestamp.

Metrics include:

- weight
- body fat %
- muscle %
- visceral fat
- body age
- BMR kcal
- BMI

Important:
values may come from multiple sources.

Support source metadata such as:

- manual
- smart_scale
- calculated
- future_external_source

For example:

    BMR (Smart Scale)
    BMR (Calculated)

must be allowed to coexist.

Calculated metrics must not overwrite device-reported metrics.

When analysing trends, prefer comparing measurements from the same source.

Do not treat a single BIA reading as medically exact.

Trend analysis should prefer 7/14/30 day patterns where appropriate.

============================================================
SLEEP
============================================================

Keep recovery tracking simple for this version.

Only track:

- date
- hours slept
- optional note

Do NOT add complex mood/stress/RHR/readiness tracking unless required
internally by the framework.

AI should be able to use sleep trends when interpreting workout performance.

============================================================
NUTRITION TARGETS
============================================================

Calculate initial nutrition targets using profile/body/activity/goal data.

At minimum support:

- target calories
- protein
- carbohydrates
- fat
- fiber

User must be able to manually edit targets.

AI may recommend changing targets based on historical trends, but AI MUST NOT
change them automatically.

Changes must appear as:

    Suggested Change

with:

    Current -> Proposed
    reason
    relevant evidence/trend

Buttons:

    Accept
    Reject

Only Accept changes the active target.

Store version/history.

============================================================
FOOD / NUTRITION LOGGING
============================================================

Support all of these:

1. Food photograph
2. Photograph + user note
3. Manual food entry
4. Saved foods
5. Meal templates
6. User corrections
7. Personal food memory/library
8. Future barcode/external-food-database integration

Example note:

    อกไก่ 100 กรัม

AI must use the user's note as stronger evidence than visual guessing.

Food analysis should estimate:

- detected foods
- amount/range
- calories
- protein
- carbohydrates
- fat
- fiber
- sugar when reasonably inferable
- sodium when reasonably inferable

Never pretend image-based quantities are exact.

Prefer ranges/confidence where uncertain.

Example:

    rice estimated 150-200 g

instead of:

    rice exactly 173 g

Show uncertainty/confidence in the UI.

============================================================
FOOD CORRECTION MEMORY
============================================================

AI output must be editable.

User can correct:

- food name
- quantity
- calories
- protein
- carbs
- fat
- fiber
- other relevant nutritional values

Track states such as:

    ai_estimated
    user_corrected
    confirmed

When the user confirms/corrects recurring foods, store those values in a
Personal Food Library.

Example:

    Nutrilite protein 34 g
    chicken breast 100 g
    usual breakfast

When similar food appears again, use confirmed personal data as context.

Do NOT fine-tune any model automatically.

This is retrieval/context memory only.

============================================================
FOOD IMAGE RETENTION
============================================================

Food photographs should be stored separately from database metadata.

Retention setting must be configurable:

- 30 days
- 90 days
- 180 days
- keep forever

Allow manual deletion of an individual photograph.

Deleting/expiring a photograph must NOT delete the nutrition entry.

The entry should remain with a marker such as:

    original image expired

============================================================
WORKOUT EXERCISE LIBRARY
============================================================

Create an Exercise Library.

Exercises must support at least:

- canonical name
- aliases if useful
- primary muscle group(s)
- secondary muscle group(s) if useful
- equipment
- compound/isolation classification
- custom exercise support

Avoid duplicate logical exercises such as:

    DB Bench
    Dumbbell Bench
    Dumbbell Bench Press

being treated as unrelated exercises.

============================================================
GYM EQUIPMENT
============================================================

Keep equipment inventory SIMPLE.

User needs only a list of available equipment/machines.

Examples:

- Smith Machine
- Cable Machine
- Dumbbells
- Leg Press
- Barbell
- Bench

Allow add/delete/edit names.

AI must consider this inventory before recommending exercise substitutions.

Do NOT build a complicated equipment database with brand/model/photos/etc.

============================================================
WORKOUT PLAN
============================================================

Support workout templates such as:

    Push
    Pull
    Legs
    Upper
    Lower
    Full Body
    Custom

Support BOTH scheduling styles:

1. Fixed calendar schedule
   e.g. Tuesday = Push

2. Rotation
   e.g. Push -> Pull -> Legs -> Rest -> repeat

Workout plans must be versioned.

Changing a workout plan must never destroy history.

============================================================
WORKOUT PLAN EXERCISE FIELDS
============================================================

Plan exercises should support things such as:

- exercise
- order
- target sets
- rep range
- target RIR/RPE if configured
- suggested rest time
- optional notes

============================================================
ACTUAL WORKOUT SESSION
============================================================

Workout Plan and actual Workout Session MUST be separate concepts.

During a real workout, user can start a session on mobile.

Each actual set should support:

- weight
- reps
- RIR
- RPE
- set type
- completed/not completed
- rest duration when available
- failure flag
- notes

Set types should include at minimum:

- warmup
- working
- drop

Support:

- supersets
- failure sets
- exercise notes
- session notes

Provide:

    Copy Last Session

to make repeated workouts fast to enter.

============================================================
REST TIMER
============================================================

During a workout session provide an in-browser/PWA rest timer.

It should:
- work well on mobile
- have quick preset times
- optionally use target rest time from the workout plan
- notify clearly when time is complete

============================================================
PROGRESSIVE OVERLOAD
============================================================

Store enough history to analyse real progression.

Examples:

Bench Press

Week 1:
50 kg x 8,8,7

Week 2:
50 kg x 9,8,8

Week 3:
50 kg x 10,10,9

AI should be able to recommend:

- keep same load
- increase reps
- increase load
- decrease load
- add/remove sets
- deload when appropriate

Recommendations must use actual performance and RIR/RPE, not simply elapsed time.

Provide charts/history where useful.

Track personal records where practical.

============================================================
WEEKLY TRAINING VOLUME
============================================================

Calculate approximate weekly volume by muscle group.

Examples:

Chest      12 sets/week
Back       16 sets/week
Quads      10 sets/week
Hamstrings 8 sets/week
Biceps     8 sets/week
Triceps    10 sets/week

Default presentation should preferably distinguish direct sets from indirect
work rather than presenting scientifically questionable precision.

Allow AI to evaluate:

- frequency
- volume
- push/pull balance
- upper/lower balance
- exercise selection
- recovery
- progression

============================================================
CARDIO
============================================================

Keep cardio tracking intentionally simple.

Store:

- cardio type
- duration
- date/time
- optional note

Example:

    Incline Walking — 30 minutes

Do NOT require:
- speed
- incline
- distance
- heart rate
- calories burned

============================================================
AI SUGGESTED CHANGES
============================================================

AI must NEVER directly alter important health/workout/nutrition plans.

AI produces a structured Suggested Change.

Example:

    Bench Press
    Before: 4 sets
    Proposed: 3 sets
    Reason: ...

Buttons:

    Accept
    Reject

Accept creates a new version.

Reject stores the rejection.

Keep:
- timestamp
- model/provider used
- reason
- old value
- proposed value
- user decision

Suggested changes may include:

- workout plan changes
- exercise substitutions
- sets/reps
- training frequency
- nutrition targets

============================================================
BODY TREND TRIGGER ENGINE
============================================================

When body metrics are entered:

Do NOT call AI blindly every time.

First run a lightweight deterministic trend/rule layer.

Use sensible documented and configurable thresholds.

Examples of potential triggers:

- meaningful weight trend
- meaningful body-fat trend
- prolonged low sleep
- repeated workout performance decline
- unusually rapid change
- target clearly not progressing over sufficient data

Avoid reacting to one noisy measurement.

If a meaningful trigger occurs:
- request AI analysis
- optionally generate Suggested Changes

Document default thresholds.

============================================================
AI COACH CHAT
============================================================

Create a Coach Chat screen.

The AI should be able to answer questions such as:

- วันนี้กินไปกี่แคลแล้ว
- โปรตีนเฉลี่ย 7 วันเท่าไหร่
- Bench เดือนนี้ดีขึ้นไหม
- ช่วยดูโปรแกรม Push ให้หน่อย
- ทำไม performance สัปดาห์นี้ตก
- ช่วยปรับตารางออกกำลังกาย

Chat must use application data as context.

If the user requests a data-changing action such as:

    ปรับโปรแกรมให้หน่อย

AI must NOT modify the database directly.

It should create a Suggested Change that the user can Accept/Reject.

============================================================
CONTEXT BUILDER
============================================================

Do NOT dump the entire database into AI on every request.

Build a dedicated Context Builder.

Depending on task, include only relevant information such as:

- profile
- latest body metrics
- current active targets
- current workout plan
- available gym equipment
- today's nutrition
- recent nutrition summary
- 7/14/30 day trend summaries
- recent workout performance
- sleep
- relevant previous confirmed food memory

Keep prompts bounded and cost-conscious.

The Context Builder should be reusable by:

- food analysis
- body analysis
- workout analysis
- Coach Chat
- Daily Summary

============================================================
AI API / ROUTER
============================================================

There are multiple MaxPlus AI API keys/providers.

DO NOT hard-code plaintext keys.

Use server-side environment variables / secrets.

Create configuration similar to:

    AI_CLAUDE_API_KEY
    AI_GPT_API_KEY
    AI_CHINA_API_KEY

The actual names may be improved, but secrets must remain server-side.

One key/provider may correspond to Claude/native-style models.
One may correspond to GPT/Codex-related pools.
One may correspond to Chinese models.

Do NOT assume the same endpoint/model works for every key.

Read the provided:

    api.txt

carefully.

Relevant MaxPlus root is expected to be around:

    https://api.maxplus-ai.cc

but verify from documentation/configuration.

At startup/admin testing:
- call the appropriate /v1/models endpoint for each configured provider/key
- discover available models
- store/display availability
- do capability tests where necessary

AI Settings page must allow model/provider priority PER TASK.

Task classes should include at least:

- Food Vision
- Workout Analysis
- Body/Progress Analysis
- Daily Summary
- Coach Chat

Example priority:

    Claude
    GPT
    China

but user can reorder.

============================================================
VISION CAPABILITY
============================================================

Do NOT confuse IMAGE GENERATION with IMAGE UNDERSTANDING.

The API documentation contains image-generation endpoints, but food analysis
requires a text/vision model capable of understanding uploaded food images.

Before selecting a Food Vision model:

1. Discover models available to each configured key.
2. Inspect supported input protocol if documented.
3. Perform a small safe vision smoke test.
4. Mark models/providers as vision-capable or not.
5. Only route food photographs to confirmed compatible models.

If a text provider cannot accept images, skip it for Food Vision rather than
fabricating support.

Do not use an image-generation endpoint to analyse food.

============================================================
AI FAILOVER
============================================================

Implement bounded failover.

Do not retry forever.

Each candidate provider/model should be attempted at most once per logical
request unless a short retry is explicitly appropriate.

Classify errors.

Potentially retry/fail over on conditions such as:
- timeout
- connection failure
- 408
- rate limiting / 429
- temporary upstream/service failure / 5xx
- provider-specific unavailable model
- exhausted provider/credit when a fallback provider is available

Do NOT blindly fail over forever on malformed requests.

For generic invalid request / malformed payload:
- stop
- log a safe diagnostic
- surface a useful error

For invalid_model/capability mismatch:
- mark candidate incompatible
- try the next configured candidate if reasonable

No infinite loops.

UI must show:
- provider/model used
- whether fallback occurred
- safe error state
- Retry button when all configured candidates fail

AI Settings should provide:

    Test Provider / Test Model

and display:
- status
- latency
- last successful test
- latest safe error message

============================================================
AI LOGGING
============================================================

Store useful metadata such as:

- task type
- provider
- model
- latency
- success/failure
- fallback sequence
- timestamp
- related record id
- safe error type

Avoid logging plaintext secrets.

Avoid unnecessarily logging highly sensitive raw payloads.

============================================================
DAILY SUMMARY
============================================================

Implement automatic Daily Summary.

User can configure summary time.

Timezone should default to:

    Asia/Bangkok

Also provide:

    End Day

button.

End Day runs summary immediately.

If data is later added, provide:

    Re-analyze

Do NOT overwrite previous summaries silently.

Store summary versions.

A Daily Summary should consider:

- today's calories/macros
- nutrition targets
- protein
- fiber
- workout
- cardio
- sleep
- recent body metrics
- useful 7/14/30 day trends

Do not overreact to one day.

============================================================
DAILY SUMMARY SCHEDULER
============================================================

Use a durable server-side scheduler suitable for the chosen stack.

Do not rely only on an open browser tab.

Avoid duplicate summaries if the job runs twice.

Make scheduled tasks idempotent.

============================================================
PWA
============================================================

Build the web app as an installable PWA.

Requirements:

- mobile-first responsive UI
- manifest
- service worker as needed for installation/push
- icons
- installable from browser
- good workout-session UX on phone
- food camera/upload UX

Offline database/sync is NOT required.

============================================================
PWA PUSH NOTIFICATIONS
============================================================

Implement web push notifications.

At minimum support notifications for:

- Daily Summary ready
- new AI Suggested Change
- optional reminder near configured summary time

Avoid noisy notifications for every data entry.

Store push subscriptions securely.

Support revoke/unsubscribe.

============================================================
DASHBOARD
============================================================

Provide a clear home dashboard.

Useful information:

- today's calorie progress
- protein progress
- carbs/fat/fiber where relevant
- today's workout
- recent body metrics
- recent sleep
- AI alerts/suggested changes
- latest Daily Summary
- 7-day trend highlights

Keep the UI practical rather than decorative.

============================================================
TRENDS
============================================================

Support useful charts/history for:

- weight
- body fat
- muscle %
- calorie intake
- protein intake
- workout performance
- weekly training volume
- sleep

Prefer:
- 7 day
- 14 day
- 30 day

views where useful.

============================================================
EXPORT / IMPORT
============================================================

Implement:

- CSV export for major domains
  - Body
  - Nutrition
  - Workout

Also implement full JSON archive export.

JSON export must include:

    schema_version

Implement JSON import.

Import must:
- validate schema
- validate references
- reject malformed data safely
- avoid duplicate/corrupt insertion
- support future migration/version handling

Do not silently overwrite live data.

Provide preview/validation before import commit where practical.

============================================================
DATABASE
============================================================

Prefer PostgreSQL unless the infrastructure audit finds a compelling reason
not to.

The LIVE PostgreSQL data directory should reside on reliable local server
storage, preferably SSD.

Do NOT run PostgreSQL's live data directory directly on an SMB/CIFS share.

Use the NAS for:
- backups
- retained food images/media if appropriate
- exports
- archives

Design migrations properly.

Use indexes where appropriate.

Use transactions for multi-step writes.

============================================================
NAS STORAGE
============================================================

During audit, determine the currently mounted NAS paths and conventions.

Create/use a dedicated area for this application.

Example conceptual layout:

    fitness/
      media/
      db-backup/
      exports/

Do not assume this exact layout if existing conventions suggest something
better.

Never write into other applications' directories.

If creating a new TrueNAS dataset/share requires access not available from
the Ubuntu server, create a clear document:

    docs/NAS-ACTIONS.md

with the exact dataset/share/mount actions required.

Do not block all application development merely because TrueNAS management UI
access is unavailable.

Use a safe local path temporarily if necessary, but clearly document the
migration to NAS.

============================================================
BACKUP / DISASTER RECOVERY
============================================================

Implement backup for:

- PostgreSQL
- food/media files
- necessary application configuration excluding secrets
- exports if appropriate

Backup destination:
NAS dedicated application area.

Retention target:

- daily backups for 14 days
- weekly backups for 8 weeks

Avoid unnecessary duplicate massive media copies if snapshot/incremental
methods are more appropriate.

Provide:

- backup script/job
- retention cleanup
- logging
- backup health/status
- documented restore procedure

Most importantly:

TEST RESTORE.

Do not merely claim backups work.

Perform a safe test restore into an isolated temporary database/location,
verify it, then remove the temporary test data.

Provide an Admin/maintenance view or clearly documented command to run:

    backup
    verify
    restore test

============================================================
PUBLIC INTERNET ACCESS
============================================================

The application is intended to be accessible from the public internet.

However:

DO NOT decide the exposure method before auditing existing infrastructure.

Inspect:

- existing reverse proxy
- existing domain
- TLS setup
- Cloudflare if present
- Tailscale Serve/Funnel
- port mappings
- firewall

Reuse the safest existing pattern where possible.

Requirements:

- HTTPS
- no direct PostgreSQL exposure
- no direct NAS exposure
- no unnecessary Docker ports exposed publicly
- authentication required
- do not break existing public services
- do not replace existing Funnel/reverse-proxy configuration blindly

If Tailscale Funnel is already being used, inspect the existing routes very
carefully before modifying them.

Never remove another application's route by accident.

Back up relevant configs before modification.

============================================================
SECURITY
============================================================

Treat this as a public internet application storing personal health data.

At minimum implement/check:

- password hashing
- secure sessions
- CSRF
- rate limiting
- upload validation
- MIME/file signature checking
- image size limits
- request size limits
- SQL injection prevention via ORM/parameterized queries
- XSS-safe rendering
- security headers
- secure cookies
- secrets outside repository
- .env excluded from Git
- .env.example without secrets
- server-side API calls only
- safe logs
- no AI secrets exposed to browser
- no database or NAS public exposure

Food uploads should accept only intended image formats.

Generate safe random file names rather than trusting upload filenames.

============================================================
HEALTH / AI SAFETY
============================================================

This application is a fitness/nutrition coaching tool, not a diagnosis tool.

AI system prompts must instruct the model to:

- avoid diagnosing disease
- avoid presenting uncertain food-image estimates as exact
- treat smart-scale body fat/muscle values as estimates
- prioritise trends over a single measurement
- flag potential injury/medical/eating-disorder concerns for professional
  assessment rather than diagnosing
- avoid extreme calorie reductions
- explain meaningful workout changes
- distinguish recommendations from facts

============================================================
ADMIN / SETTINGS
============================================================

Provide settings for at least:

- account/password
- timezone
- Daily Summary time
- nutrition targets
- food image retention
- AI providers/models/priorities
- Test AI Model
- gym equipment
- push notifications
- backup status if practical
- export/import

============================================================
BODY ANALYSIS AUTOMATION
============================================================

When new body data arrives:

1. Save data.
2. Recalculate local deterministic metrics/trends.
3. Run trigger rules.
4. If no meaningful trigger:
   do not waste an AI request.
5. If trigger fires:
   build appropriate context.
6. Ask AI for analysis.
7. If a program/target change is proposed:
   create Suggested Change.
8. Notify user through web push when appropriate.

============================================================
FOOD ANALYSIS FLOW
============================================================

Expected flow:

1. User takes/uploads photo.
2. User optionally adds note.
3. Validate image.
4. Store image.
5. Build relevant context.
6. Route request to configured Food Vision providers.
7. Use fallback if necessary.
8. Return structured nutrition estimate.
9. Save estimate + uncertainty.
10. User may correct it.
11. Save confirmed correction into Personal Food Library when appropriate.
12. Update daily totals.
13. Dashboard reflects new totals.

============================================================
WORKOUT FLOW
============================================================

Expected flow:

1. User selects scheduled/template workout.
2. Start Workout Session.
3. Show previous session values.
4. Enter each set.
5. Rest Timer starts where appropriate.
6. Finish workout.
7. Store actual results.
8. Calculate progression/volume statistics.
9. Trigger AI only when user requests analysis or a meaningful rule is met.
10. AI may create Suggested Change.
11. User Accept/Rejects.

============================================================
IMPLEMENTATION QUALITY
============================================================

Use a maintainable project structure.

Avoid giant files.

Separate concerns such as:

- auth
- body
- nutrition
- workouts
- AI router
- AI context builder
- AI schemas
- scheduler
- notifications
- storage
- backups

Use typed/validated structured outputs from AI wherever possible.

Do not parse important AI actions from arbitrary prose.

Define schemas for things such as:

    NutritionEstimate
    DailySummary
    WorkoutAnalysis
    SuggestedChange
    BodyTrendAnalysis

Validate AI responses before writing to database.

============================================================
TESTING
============================================================

Create automated tests appropriate to the chosen stack.

At minimum test critical behavior around:

- authentication
- nutrition calculations
- workout data
- workout plan versioning
- Suggested Change Accept/Reject
- body metric history
- trend rules
- context builder
- AI routing
- AI fallback
- image retention logic
- daily summary idempotency
- import validation
- backup scripts where testable

Do not make live paid AI calls in the normal automated test suite.

Mock/provider-adapter test AI integrations.

Provide a separate optional live smoke test.

============================================================
AI API SMOKE TEST
============================================================

After configuration is available:

Safely test:

- provider authentication
- /models
- one tiny text request
- vision request for providers believed to support it
- fallback behavior
- malformed key/error handling

Never print full API keys.

Mask keys in logs.

============================================================
OBSERVABILITY
============================================================

Provide:

- Docker health checks where useful
- useful application logs
- AI request status without secrets
- scheduler logs
- backup logs

Integrate with the existing monitoring convention if the server already has
one.

If Uptime Kuma is present, document the endpoint that should be monitored and
optionally configure it only if safe and straightforward.

Provide:

    /health

or equivalent for monitoring.

============================================================
GIT
============================================================

Inspect current Git state before modifying anything.

Do not overwrite unrelated user work.

Use sensible commits.

Never commit:

- secrets
- DB dumps
- production food photographs
- private health data
- .env

Include:

    .env.example

with placeholders.

============================================================
DOCUMENTATION
============================================================

At completion create useful docs, for example:

    README.md
    docs/infrastructure-audit.md
    docs/architecture.md
    docs/implementation-plan.md
    docs/deployment.md
    docs/ai-routing.md
    docs/backup-restore.md
    docs/security.md
    docs/NAS-ACTIONS.md      (if manual NAS setup is necessary)

Document:

- architecture
- Docker services
- ports
- storage
- AI providers
- environment variables
- public access
- backup
- restore
- update procedure
- rollback procedure

============================================================
PHASING
============================================================

YOU decide the phases after auditing the actual server.

Do not ask me to approve the phases.

Write them down, then execute all of them in order.

Choose phase boundaries that make testing and rollback safe.

Do not create a huge untested code dump.

A reasonable philosophy is:

    audit -> foundation -> core data -> workout/nutrition ->
    AI -> automation -> PWA/notifications -> storage/backup ->
    public deployment -> final verification

but adjust this based on what you discover.

============================================================
DEPLOYMENT SAFETY
============================================================

Before modifying an existing configuration that could affect other services:

- inspect it
- make a timestamped backup
- understand current behavior
- make the smallest possible change
- verify old services still work afterwards

Do not run global commands such as destructive Docker prune operations.

Do not remove existing containers, volumes, networks or firewall rules merely
because they appear unused without proving ownership.

============================================================
FINAL END-TO-END VERIFICATION
============================================================

Before saying the task is complete, verify at least:

1. Login works.
2. Wrong password is rejected/rate-limited.
3. Body metrics can be created and updated.
4. Historical metrics remain intact.
5. Nutrition target works.
6. Manual food entry works.
7. Food photo upload works.
8. AI food analysis works or clearly reports provider capability failure.
9. User correction works.
10. Saved food works.
11. Workout plan works.
12. Fixed schedule works.
13. Rotation works.
14. Workout session works.
15. Set logging works.
16. Rest Timer works.
17. Copy Last Session works.
18. Weekly volume calculations work.
19. Cardio log works.
20. Sleep log works.
21. Coach Chat works.
22. Suggested Change works.
23. Accept creates a new version.
24. Reject preserves current version.
25. Daily Summary can run manually.
26. Scheduled summary works.
27. Re-analyze creates another summary version.
28. AI provider fallback works.
29. Retry after all providers fail works.
30. PWA installs.
31. Push notification works.
32. Food retention setting works.
33. CSV export works.
34. JSON export works.
35. JSON validation/import works.
36. Backup job works.
37. Restore test succeeds.
38. /health works.
39. Existing server applications still work.
40. Public HTTPS access works using the chosen safe mechanism.

============================================================
FINAL REPORT
============================================================

At the end provide a concise but complete report containing:

- architecture selected
- why it was selected
- application URL
- local URL
- containers/services added
- ports used
- database/storage locations
- NAS usage
- public exposure method
- authentication method
- AI providers/models discovered
- which models support food vision
- failover order
- important files/directories
- backup schedule
- restore-test result
- tests run and results
- existing-service regression checks
- any remaining non-blocking TODOs
- any manual NAS action still required
- any secrets I must add/rotate

Do not claim success for anything that was not actually tested.

============================================================
SECRETS
============================================================

I previously supplied API keys in another context.

Treat those as compromised/exposed for production purposes.

DO NOT copy those plaintext values into:
- source files
- this repository
- Docker Compose
- frontend JavaScript
- README
- shell history where avoidable

Use secure environment configuration.

If rotated/new secrets already exist on the server, use them.

If required secrets do not exist, complete every part of the system that can
be completed safely, then ask me once for the missing secret rather than
stopping between phases.

BEGIN NOW.

Start with the read-only infrastructure audit over SSH.
Then design the phases and continue through implementation, deployment,
testing, restore verification, and documentation without waiting for
per-phase approval.

