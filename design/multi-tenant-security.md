# Multi-tenant security & B2B foundation

Status: **design / agreed** (pre-Stage 13). Companion to
[`monetization-and-b2b.md`](monetization-and-b2b.md) — that doc fixes the
*billing* seam; this one fixes the *authorization / isolation / account
security* seams for the move to a real multi-tenant B2B product.

Same principle: **design forward, build narrow.** Capture the decisions now;
build them in additive stages.

---

## 0. Strategic model (fixed)

- **B2B-seat (кафедра/вуз) — primary.** The organization pays per user / course.
  A consequence that reshapes priorities: classic B2C abuse (material churn,
  account sharing) is largely **moot** — the seat is already paid for.
- **B2C — showcase + seasonal.** `free` (tight limits so we don't bleed LLM
  money) / `pro` / season-pass. Funnel + demo for the B2B sale.

→ Therefore the priorities are **isolation + roles + per-user limits + SSO +
cost control**, *not* anti-churn caps. The monthly-upload cap (anti-churn) is a
future B2C-only option, never a blocker.

---

## 1. Roles & authorization

Three independent role planes — never conflated:

| Plane | Field | Roles | Who |
|-------|-------|-------|-----|
| Platform | `User.is_superuser` | superuser | us (operators) |
| Organization | `OrganizationMember.role` *(future)* | `org_admin` / `teacher` / `student` | within a кафедра |
| Course (= workspace) | `WorkspaceMember.role` *(column exists)* | `owner` / `teacher` / `student` / `viewer` | within a course |

**Centralized authorization resolver** — the new seam:

```
can(user, action, workspace) -> bool
```

Every mutating endpoint goes through it instead of ad-hoc checks, so a missed
check can't become a privilege escalation. Examples:

- upload / reindex / delete material in a course → `teacher` / `owner` only;
- chat / summary → any member (`student` and up);
- manage members / rename course → `teacher` / `owner`;
- delete course → `owner` (or `org_admin`).

This mirrors `get_billing_context` (one place decides billing) and
`get_current_workspace_id` (one place decides *which* workspace).

---

## 2. Data isolation

- **Now:** a single Chroma collection filtered by `workspace_id` from auth
  (the `get_current_workspace_id` seam). Logical isolation — a filter bug is the
  cross-tenant leak risk.
- **B2B:** per-org Chroma collection / namespace → **physical** isolation, so a
  filter bug can never leak one university's data into another's. Defense in
  depth; a data leak between vuzy is reputational death.
- **Invariant:** `workspace_id` is **always** derived from auth + membership,
  **never** from the client. The future active-workspace selector must validate
  that the user is a member before switching.
- **Mandatory:** the isolation tests stay green
  (`test_two_users_isolation`, `test_knowledge_base_isolation`); add per-role
  authorization tests in Stage 13.

---

## 3. Rate limiting — per-user, not per-IP

⚠️ **Current bug for multi-user:** slowapi keys on `get_remote_address` (per-IP).
A university NAT shares one public IP, so one noisy student would throttle the
**entire group**.

- Fix: for **authenticated** endpoints, key the limiter by `user_id`
  (fall back to IP only for anonymous callers).
- Keep per-IP on the **public** auth endpoints (`login` / `register`) as
  anti-brute-force.

---

## 4. Account security

- **Email verification:** `User.email_verified_at` exists but is **unused** —
  wire a real verify flow.
- **Password reset:** missing — add (one-time token + email).
- **Session revocation / ban:** `is_active` is checked only at login. Enforce it
  in `get_current_user` so a ban (Stage 12-roles) or "log out everywhere" takes
  effect on already-issued JWTs.
- **SSO (later):** university login (SAML / OAuth) for B2B; until then, bulk
  onboarding via **course invite codes**.
- **2FA (later):** for `org_admin` / `teacher`.

---

## 5. Onboarding / membership UX

- Teacher creates a course (a workspace with `organization_id`).
- **Invite by course code / link** → student self-joins (no admin step).
- Active-workspace switcher + "my courses" list.
- Teacher analytics (what students ask, where the gaps are) — a paid value-add.

---

## 6. Content / legal / PII

- **Copyright:** in B2B the **teacher** uploads course materials (more
  defensible than student-uploaded textbooks).
- **152-ФЗ / data residency + retention:** policy "delete course → purge vectors
  after N days" (the reconciler already scrubs orphans); audit log already
  records security-relevant actions.

---

## 7. Cost / sustainability

- **Answer/summary cache** keyed by `(workspace_id, normalized query)` — cut LLM
  cost + latency for repeated questions over the same material.
- **Model tiering:** `free` → cheap/local, `pro`/`org` → strong (the
  `limits.model` hook from Stage 12 is ready).
- The Stage 12 metering ledger → measure real per-action cost → price org seats.

---

## 8. Reprioritized roadmap (security before billing)

> This supersedes the tentative ordering in `monetization-and-b2b.md` §8: the
> **B2B foundation (security/roles) comes before billing**, because we won't
> charge a department until multi-tenant access is safe.

1. **Stage 12 — plans / quotas / metering** ✅ (done).
2. **Stage 13 — Multi-tenant security / B2B foundation:** centralized
   `can(...)` authorization resolver, per-workspace roles
   (`teacher`/`student`/`viewer`), per-user rate-limit, isolation hardening,
   `is_active` enforced in `get_current_user`. Likely split into sub-stages.
3. **Stage 14 — Org & courses:** `Organization` / `OrganizationMember` tables,
   `Workspace.organization_id`, invite-by-code, active-workspace selection,
   per-org Chroma isolation.
4. **Stage 15 — Billing:** payment provider (ЮKassa / Stripe) + webhooks — org
   seats + B2C pro / season-pass.
5. **Later:** SSO, answer caching, teacher analytics, 2FA.

---

## Seams to protect (the only deciders)

| Seam | Decides | Status |
|------|---------|--------|
| `get_current_workspace_id` | *which* workspace | exists |
| `get_billing_context` | *which* billing subject + limits | Stage 12 |
| `can(user, action, workspace)` | *what's allowed* | **Stage 13** |

Keep these three the *only* places that make these decisions, and every B2B
step stays additive instead of a rewrite.
