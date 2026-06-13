# Courses & roles (Stage 15)

Status: **design / agreed**. Scope decision (locked): **build courses + roles +
join-by-code + course switcher now; defer the formal Organization (кафедра/вуз)
entity to the billing stage.** Companion to
[`multi-tenant-security.md`](multi-tenant-security.md) (auth/isolation seams) and
[`monetization-and-b2b.md`](monetization-and-b2b.md) (billing seam).

Same principle as before: **design forward, build narrow.**

---

## 0. The picture (plain)

Today every user has exactly one **personal** workspace, visible only to them.
Stage 15 adds **courses** — shared workspaces other people join.

Example:
- Teacher Ivanov creates the course **«Сети»**, uploads the methodichki.
- Students join with a **code** (e.g. `СЕТИ-2024`) and see **only** that course's
  materials.
- A student can **ask questions and make summaries**, but **cannot delete** the
  teacher's materials. The teacher can.
- A person can be in several courses → a **course switcher** at the top picks the
  active one.

Why this is cheap: a **course is just a shared `Workspace`**, and the vector DB
already filters every query by `workspace_id`. So **course isolation comes for
free** — no ChromaDB change, no new isolation logic. We're adding *membership*,
*roles*, *joining*, and *active-course selection* on top of primitives that
already exist.

---

## 1. What already exists (no change needed)

- `Workspace` — already supports multiple members (`Workspace.members`), an
  `owner_user_id`, and a `plan`. A course is a `Workspace`.
- `WorkspaceMember(user_id, workspace_id, role)` — the table **already exists**
  with a `role` column (currently only ever one `owner` row per personal
  workspace). This is the membership + role hook.
- `Document.workspace_id` + ChromaDB metadata `workspace_id` — already the
  isolation key. A course's materials are isolated because the course is a
  distinct `workspace_id`.
- `get_billing_context(workspace)` — already resolves the billing subject from
  `workspace.owner`. A course bills its owner (the teacher) — see §6.

---

## 2. Data model (additive, all nullable / defaulted)

| Change | Why |
|--------|-----|
| `Workspace.kind` — `"personal"` (default) / `"course"` | Distinguish a user's personal space from courses in the UI / API. Existing rows default to `"personal"`. |
| `Workspace.join_code` (nullable, indexed) | The code a student types to join a course. Personal workspaces have none. |
| `Workspace.join_enabled` (bool, default true) | Teacher can pause joining without rotating the code. |
| `User.active_workspace_id` (nullable FK) | The user's currently selected workspace. `null` → personal. The **only** thing the active-workspace switcher writes; always membership-validated on use (§5). |

**Roles** live in `WorkspaceMember.role`. Stage 15 uses three:

- `owner` — the course creator. Full rights incl. *delete course*.
- `teacher` — co-manager added by the owner. Same as owner **except** can't
  delete the course or remove the owner.
- `student` — participant: ask / summarize, read materials.

(`viewer` — read-only — is documented as a trivial future addition; not built
now to keep the role set small.)

A user's **personal** workspace keeps a single `owner` membership of themselves,
so today's behavior is unchanged: in your personal space you are `owner` and can
do everything.

No `Organization` table, no `Workspace.organization_id` in Stage 15 — deferred
to billing (§7). A course owned directly by a teacher is the unit now.

---

## 3. The authorization seam: `can(user, action, workspace)`

The new **single decider** for "what's allowed". Every mutating endpoint goes
through it instead of ad-hoc checks, so a missed check can't become a privilege
escalation. It reads the caller's `WorkspaceMember.role` in that workspace.

Permission matrix:

| action | owner | teacher | student |
|--------|:----:|:------:|:------:|
| view course / list materials | ✓ | ✓ | ✓ |
| chat | ✓ | ✓ | ✓ |
| summary | ✓ | ✓ | ✓ |
| upload material | ✓ | ✓ | ✗ |
| reindex material | ✓ | ✓ | ✗ |
| delete material | ✓ | ✓ | ✗ |
| manage members (invite link, remove, set role) | ✓ | ✓ | ✗ |
| rename course / rotate-disable join code | ✓ | ✓ | ✗ |
| delete course | ✓ | ✗ | ✗ |

A non-member gets `False` for everything (and the endpoint returns `403`).

This mirrors the other two deciders: `get_current_workspace_id` decides *which*
workspace, `get_billing_context` decides *which billing subject*, and now `can(...)`
decides *what's allowed*.

---

## 4. Active-workspace selection (the second seam)

`get_current_workspace_id` today returns `current_user.personal_workspace.id`.
Stage 15 makes the active workspace **selectable** but keeps the hard invariant:

> **`workspace_id` is always derived from auth + membership, never trusted from
> the client request body or URL.**

Mechanics:
- `POST /api/workspaces/{id}/activate` — the switcher's only write. The server
  **validates the caller is a member** of `{id}`, then sets
  `User.active_workspace_id = {id}`. Non-member → `403`, nothing changes.
- `get_current_workspace_id` resolves `active_workspace_id`, **re-checking
  membership on every request**. If the user was removed from that course (or it
  was deleted), the resolver silently falls back to the personal workspace — a
  removed student's stale selection can't leak the course.
- `GET /api/workspaces` — "my spaces": the personal workspace + every course the
  user is a member of (with the user's role in each), for the switcher UI.

Because every workspace access already funnels through this one resolver, making
the workspace selectable stays localized — the same reason the design has guarded
this seam since Stage 6.

---

## 5. Join-by-code flow

- On course creation the server generates a short, unique `join_code`
  (e.g. 6–8 chars, ambiguity-free alphabet).
- `POST /api/courses` — any authenticated user creates a course; they become its
  `owner` (and a `WorkspaceMember(role="owner")` row). Creates a
  `kind="course"` workspace.
- `POST /api/courses/join` `{code}` — if the code matches an enabled course, add
  a `WorkspaceMember(role="student")`. **Idempotent** (already a member → no-op,
  not an error). Disabled/!found code → `404`/`409`.
- Teacher can **rotate** (regenerate `join_code`) or **disable** (`join_enabled`)
  from the manage-members screen. Rotating invalidates the old code immediately.

Bulk onboarding by code is the B2B substitute for SSO until SSO lands (per
`multi-tenant-security.md` §4).

---

## 6. Billing / quota consequence (known, accepted)

A course bills **its owner (the teacher)**: `get_billing_context` resolves
`workspace.owner`, so every chat/summary/upload **inside a course counts against
the teacher's plan/quota**, regardless of which student did it.

For Stage 15 (pre-billing) that means a `free` teacher's course shares the
teacher's free limits across all students — tight, and a natural upgrade nudge.
This is **correct and intended**: it's exactly the seat the кафедра will pay for.
When the Organization tier lands, `get_billing_context` gains one branch (course
→ organization) and the quota counting code is unchanged — that's the whole point
of returning `billing_subject_*` since Stage 12.

`record_usage` already stamps `user_id` (the actor) separately from
`billing_subject_id` (who pays), so per-student analytics ("what students ask")
is already capturable for a future teacher-analytics feature.

---

## 7. Scope: Stage 15 vs deferred

**Stage 15 (now):** `Workspace.kind/join_code/join_enabled`,
`User.active_workspace_id`, `can(user, action, workspace)`, active-workspace
selection + membership validation, course create / join-by-code / manage-members,
role-aware UI + course switcher.

**Deferred (designed, later stages):**
- **Organization (кафедра/вуз) entity** + `OrganizationMember` + admin →
  billing stage. Its main job is "who pays" and dept-admin; courses work without
  it. `Workspace.organization_id` is added then (nullable, additive).
- **Org branch in `get_billing_context`** → billing stage.
- **`viewer` role**, per-org **physical Chroma isolation**, **SSO**, **teacher
  analytics**, **answer cache** — all designed in `multi-tenant-security.md`,
  none blocking.

---

## 8. Sub-stage plan

1. **15-1 — data model + migration.** `Workspace.kind/join_code/join_enabled`,
   `User.active_workspace_id`; Alembic migration (additive); membership/query
   helpers. No behavior change yet. Tests.
2. **15-2 — `can(user, action, workspace)`** + membership helpers; route every
   mutating endpoint (upload / reindex / delete / chat / summary / manage)
   through it. Tests incl. per-role authorization. Personal-workspace behavior
   stays identical (owner → all rights).
3. **15-3 — active-workspace selection.** `get_current_workspace_id` resolves
   `active_workspace_id` with per-request membership re-check; `POST
   /api/workspaces/{id}/activate`; `GET /api/workspaces`. Isolation tests stay
   green.
4. **15-4 — courses + join-by-code.** `POST /api/courses`, `POST
   /api/courses/join`, rotate/disable code, manage-members (list/remove/role).
   Tests.
5. **15-5 — frontend.** Course switcher + "my courses" list, create-course,
   join-by-code, role-aware UI (hide upload/delete/manage for students).
6. **15-6 — docs.** README / ARCHITECTURE / CLAUDE.md + finalize this doc.

---

## 9. Seams to protect (unchanged contract)

| Seam | Decides | Stage |
|------|---------|-------|
| `get_current_workspace_id` | *which* workspace (now selectable, membership-validated) | 6 → **15** |
| `get_billing_context` | *which* billing subject + limits | 12 |
| `can(user, action, workspace)` | *what's allowed* | **15** |

Keep these three the only places that make these decisions and the Organization
step (billing stage) stays additive, not a rewrite.
