# v1.9 Non-Interference Contract (Apollo-veo)

This contract is the ¡°do-not-break-the-base¡± rule-set for v1.9 scenario expansion.
All PRs that add new scenarios (ApolloAvatar, HotFollow, etc.) MUST comply.

## 0) Base Freeze (Hard Freeze)
The following are considered the stable base. Do NOT change their behavior unless fixing a bug with explicit approval:

- Suitcase main pipeline: parse ¡ú subtitles ¡ú dub ¡ú pack
- Suitcase create page: `/tasks/new`
- Existing task board rendering + polling behavior
- Task repository/storage semantics (S3/R2 keys, task state persistence)
- Existing Workbench flows (unless purely additive + isolated)

**Rule:** New scenarios are added as side-car modules; base code paths remain untouched.

---

## 1) Hexagonal / Ports-and-Adapters Boundary
New scenario code must follow this dependency direction:

router (HTTP) ¡ú service (orchestrate) ¡ú ports (interfaces) ¡ú providers (external APIs)

**Allowed locations for new scenario code:**
- `gateway/app/routers/`
- `gateway/app/domain/`
- `gateway/app/services/`
- `gateway/app/ports/`
- `gateway/app/providers/`
- `gateway/app/templates/` (new pages only)
- `gateway/app/static/` (new assets only)

**Disallowed:**
- Copying/rebuilding a parallel task system
- Editing Suitcase pipeline logic to ¡°fit¡± the new scenario
- Heavy logic in router

---

## 2) Thin Router Rule
Each scenario router MUST only:
1) bind request/response schemas
2) call a single service entrypoint
3) map errors to HTTP responses

**Router must NOT:**
- call external APIs directly
- implement orchestration/state machine
- contain large branching logic (model selection belongs in service/provider)

Target: router file <= ~200 lines.

---

## 3) Scenario Isolation in UI
To avoid scenario interference:

- Task list MAY filter by kind, e.g. `/tasks?kind=apollo_avatar`
- Each scenario MUST have its own create page:
  - Suitcase: `/tasks/new` (unchanged)
  - ApolloAvatar: `/tasks/apollo-avatar/new`
  - HotFollow: `/tasks/hot-follow/new` (placeholder for now)

**Rule:** `/tasks/new` must never become a mixed ¡°everything form¡±.
All new scenario UI is separate templates/pages.

Workbench can remain shared, but no scenario-specific fields may be injected into Suitcase create page.

---

## 4) Billing & Safety Gates (Two-Layer Gate)
All external API calls that can incur cost MUST be protected by two gates:

### Gate A (deployment gate)
- Scenario routes are registered ONLY if `ENABLE_<SCENARIO>=1`.

Example:
- `ENABLE_APOLLO_AVATAR=1` registers ApolloAvatar routes.

### Gate B (billing gate / live gate)
- Actual external API execution is allowed ONLY if:
  - `APOLLO_AVATAR_LIVE_ENABLED=1` (env)
  - AND request/task meta sets `live_enabled=true`

Otherwise, the system MUST return demo/static outputs without cost.

---

## 5) Provider Replaceability Requirement
Model/API vendors must be swappable without touching business orchestration:

- Service depends on a port interface (e.g. `VideoGenPort`)
- Provider implements the port (Fal, Akool, Wavespeed, etc.)
- Selection logic is in service/config, not scattered

---

## 6) PR Checklist (Mandatory)
Every PR introducing or evolving a scenario must pass:

- [ ] Suitcase pipeline behavior unchanged (parse/subtitles/dub/pack)
- [ ] `/tasks/new` unchanged (no ApolloAvatar fields injected)
- [ ] New UI is isolated to new page(s)
- [ ] Router is thin (no external API calls, no orchestration)
- [ ] Provider is replaceable (service depends on port interface)
- [ ] Live gate defaults to OFF (demo by default)
- [ ] Only additive changes to templates/static (no global UI breakage)
