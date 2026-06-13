# Monetization & B2B architecture

Status: **design / agreed** (pre-Stage 12). This doc fixes the data model and
the seams so we can ship **plans + quotas + metering** now without repainting
ourselves into a corner when the product grows into the
**кафедра → преподаватели → курсы → студенты** (department → teachers →
courses → students) B2B model.

Guiding principle: **design forward, build narrow.** We do *not* build the
whole B2B system now. We only add what monetization needs today, but we put the
abstractions where the B2B model will later plug in with additive migrations
(new tables / nullable columns), never a rewrite.

---

## 1. Why this shape

The product's wedge is **answers grounded in *your* materials, with sources** —
not a generic chatbot. The same retrieval/isolation we already built is what a
department would pay for: a teacher uploads a course's methodichki/lectures, and
students ask questions scoped to exactly those materials.

Good news: the current schema is already ~80% of the B2B model.

- `Workspace` is conceptually already a **Course**.
- `WorkspaceMember.role` (column already exists) is already the hook for
  per-workspace roles.

The big future additions are only: an **Organization**, **multi-workspace
membership** (a user in several courses), and **active-workspace selection**.
Stage 12 touches none of those.

---

## 2. Target data model (future — NOT built now)

```
Organization (кафедра/вуз)              [FUTURE]
  ├─ plan: "org"
  └─ OrganizationMember(user_id, role: org_admin | teacher | student)   [FUTURE]

User  (platform account)                [EXISTS]
  ├─ is_superuser → PLATFORM admin (us) — distinct from any org/course role
  └─ plan: "free" | "pro"                [NEW in Stage 12]  ← personal billing subject

Workspace ( = Course )                   [EXISTS]
  ├─ owner_user_id                       [EXISTS]
  ├─ organization_id (nullable)          [FUTURE]  null = personal; set = course
  └─ WorkspaceMember(user_id, role: owner | teacher | student | viewer)  [role EXISTS]

Document → workspace_id                  [EXISTS, ID-based storage]
UsageEvent (metering ledger)             [NEW in Stage 12]
```

**Teacher / Student are roles, not tables.** A user's relationship to a course
is `WorkspaceMember.role`; to a department, `OrganizationMember.role`. This
avoids duplicate-ФИО and rename problems — everything keys on IDs, names are
just attributes.

`is_superuser` stays the **platform** admin flag (us, the operators). It is
deliberately separate from org/course roles so a department admin never gets
platform-wide powers.

---

## 3. The billing seam: `get_billing_context(workspace)`

All quota/limit logic goes through **one resolver** so it never reads a plan
field directly. This is the single most important forward-compat decision.

```
get_billing_context(workspace) -> BillingContext:
    plan                : "free" | "pro" | "org"
    billing_subject_type: "user"   (now)   | "organization" (future)
    billing_subject_id  : user.id  (now)   | organization.id (future)
    limits              : PlanLimits for that plan

    # resolution:
    now:    subject = workspace.owner_user      → type="user",         plan=user.plan
    future: if workspace.organization_id:
                subject = workspace.organization → type="organization", plan=org.plan
            else:
                subject = workspace.owner_user   → type="user",         plan=user.plan
```

Why a *context* and not just `effective_plan()`: quotas are counted **per
billing subject**. Today that's the user; for a department it's the
organization (all its courses share one quota/invoice). Returning the
`billing_subject_{type,id}` now means the quota counting code is already written
against "the subject", so adding the org branch later changes **only the
resolver** — not the enforcement, not the metering.

`Workspace.plan` (already in the schema, currently unused) is reserved as a
**future per-course override**; we keep it dormant to avoid confusion.

---

## 4. Plans

| Plan   | Billing subject | Meaning                                             |
|--------|-----------------|-----------------------------------------------------|
| `free` | user            | personal workspace, tight limits                    |
| `pro`  | user            | extended personal limits, better experience         |
| `org`  | organization    | department: teachers + students + N courses, shared quota *(future)* |

`PlanLimits` (per plan) is config-driven, e.g.: `max_materials`,
`chat_per_day`, `summary_per_day`, `upload_per_day`, `model` (model tier is a
field now; both plans point at the currently-configured model until a cheaper
tier is wired). Concrete Stage-12 numbers live in the Stage 12-1 plan.

---

## 5. Metering: `UsageEvent`

Append-only ledger — powers **both** quota enforcement **and** real cost
measurement (we need the latter to set prices honestly; cf. the OpenRouter
402-credits incident).

| Column                 | Why                                                      |
|------------------------|----------------------------------------------------------|
| `id`                   | PK (String36)                                            |
| `workspace_id`         | where it happened (a course, later)                      |
| `user_id`              | who did it                                               |
| `action`              | `chat` / `summary` / `upload`                            |
| `units`                | quota units (1 per action now; tokens later)             |
| `billing_subject_type` | `user` now, `organization` later — aggregate by this     |
| `billing_subject_id`   | the subject the quota/invoice belongs to                 |
| `created_at`           | indexed; daily windows + reporting                       |
| `meta` (JSON, nullable)| model, char/token counts, cost, error — best-effort      |

No foreign keys (same rationale as `AuditEvent`): the ledger must outlive a
deleted user/workspace for accounting. Counting a daily window =
`COUNT(*) WHERE billing_subject_id = ? AND action = ? AND created_at >= start_of_day`.

---

## 6. File storage — already safe, unchanged

Current layout: `docs/<workspace_id>/<document_id>__<filename>`.

This already solves duplicate-ФИО / rename / tenant-safety because:

- the path is built only from **IDs** (no teacher names), and
- the **source of truth is `Document.stored_path` in the DB** — paths are never
  reconstructed from names.

- **Now:** keep as is.
- **Future (orgs):** new files go under `docs/<org_id>/<workspace_id>/...`; old
  files stay where they are (`stored_path` understands both). **No file
  migration.**

Hard rule to preserve: *never build a path from a name — always read
`stored_path`.*

---

## 7. Scope: Stage 12 vs deferred

**Stage 12 (now):**
- `User.plan` (`free`/`pro`)
- `PlanLimits` config + `get_billing_context()` resolver (user branch only)
- `UsageEvent` metering
- quota checks on `chat` / `summary` / `upload`
- minimal usage / paywall UI

**Deferred (designed, separate stages).** Note: after Stage 12 the strategic
model was fixed to **B2B-seat primary**, so the **B2B foundation (security /
roles) now comes before billing** — see
[`multi-tenant-security.md`](multi-tenant-security.md). Updated order:
- **Stage 13 — Multi-tenant security / B2B foundation** ✅: per-user rate-limit,
  live-session ban, superuser user-management. (The `can(...)` resolver + roles
  moved to Stage 15 — they need shared workspaces.)
- **Stage 14 — Streaming chat** ✅: UX insert (token-by-token assistant).
- **Stage 15 — Org & courses:** `Organization` / `OrganizationMember` tables,
  `Workspace.organization_id` (nullable), `can(user, action, workspace)` +
  roles, org branch in the billing resolver, invite-by-code,
  **active-workspace selector**, per-org isolation.
- **Stage 16 — Billing:** payment provider (ЮKassa / Stripe) + webhooks → flips
  the plan (org seats + B2C pro/season) on payment.

---

## 8. Migration path (all additive)

1. **Stage 12** — `User.plan`, limits, `UsageEvent`, billing-context resolver,
   paywall UI. ✅
2. **Stage 13** ✅ — multi-tenant security primitives (per-user rate-limit,
   ban enforcement, user-management) — see `multi-tenant-security.md`.
3. **Stage 14** ✅ — streaming chat (UX insert).
4. **Stage 15** — `Organization` / `OrganizationMember` / `Workspace.organization_id`
   + `can(...)` + roles + org branch in `get_billing_context`; courses,
   multi-membership, active-workspace selection.
5. **Stage 16** — billing provider + webhooks.

### The seams we protect

- **`api_app.get_current_workspace_id`** — today resolves the personal
  workspace from auth. Stage 15 makes the active workspace *selectable*. Because
  every workspace access already funnels through this one resolver, that change
  stays localized.
- **`get_billing_context(workspace)`** — every quota/limit decision goes through
  this one function, so org billing is a one-branch change.

Keep both seams as the *only* places that decide "which workspace" and "which
billing subject", and the B2B step is additive, not a rewrite.
