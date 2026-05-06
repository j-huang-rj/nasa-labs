---
phase: 02-primary-authoritative-zones
plan: 03
subsystem: ansible/bind9
tags: [bind9, reverse-zone, rfc-2317, ptr, cname, dig, verification, split-view]

# Dependency graph
requires:
  - phase: 02-primary-authoritative-zones
    plan: 02
    provides: bind9_zones contract, db.zone.j2 template, per-view zone render pipeline, named-checkzone validation
provides:
  - Reverse-zone data for 172.16.0/24 and 172.16.1/24 in both views
  - RFC 2317 carrier zone with CNAME delegation to child /28 zone
  - RFC 2317 child zone with PTR records for VPN router/client/ns
  - Source-bound dig verification matrix proving split-view correctness
affects: [secondary-ns, dnssec]

# Tech tracking
tech-stack:
  added: [dig]
  patterns: [rfc-2317-classless-delegation, source-bound-dig-verification, authoritative-flag-assertion]

key-files:
  created: []
  modified:
    - ansible/inventory/host_vars/primary-ns-01/main.yml
    - ansible/playbooks/roles/bind9/tasks/verify.yml

key-decisions:
  - "Private 1.16.172.in-addr.arpa exposes private-ns PTR; public maps host 53 to ns only — no private-ns exposure"
  - "RFC 2317 carrier zone uses CNAME records pointing to child zone; child zone holds actual PTRs"
  - "dig verification uses source-bound queries (-b flag) to force view selection"
  - "Authoritative checks assert flags: qr aa on full dig responses"
  - "private-ns absence in public view checked via ANSWER: 0 or NXDOMAIN"

requirements-completed:
  - AUTH-03
  - AUTH-05
  - AUTH-06

# Metrics
duration: 3min
completed: 2026-05-06
---

# Phase 2 Plan 03: Reverse Zones + Runtime Dig Verification Summary

**Reverse-zone data with RFC 2317 classless delegation and source-bound dig verification proving split-view correctness**

## Performance

- **Duration:** 3 min
- **Started:** 2026-05-06T10:29:05Z
- **Completed:** 2026-05-06T10:32:36Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- Added 8 reverse-zone entries to bind9_zones (4 zone names × 2 views each)
- 0.16.172.in-addr.arpa: private has router+ns PTR; public has ns+agent PTR
- 1.16.172.in-addr.arpa: private has router+private-ns+dns+internal-agent PTR; public has ns-only PTR (no private-ns exposure)
- RFC 2317 carrier zone: CNAME records in both views pointing to child /28 zone
- RFC 2317 child zone: PTR records for VPN router/client/ns IPs in both views
- Added 9 source-bound dig verification tasks (4 private, 5 public)
- Asserts authoritative responses (flags: qr aa) on 5 dig queries
- Asserts private-ns NXDOMAIN/ANSWER: 0 in public view
- Asserts VPN NS IP reverse resolution through RFC 2317 carrier/child path

## Task Commits

Each task was committed atomically:

1. **Task 1: Add reverse-zone and RFC 2317 delegation data for both views** - `1a3f329` (feat)
2. **Task 2: Prove both views with a source-bound dig verification matrix** - `182b899` (feat)

## Files Created/Modified

- `ansible/inventory/host_vars/primary-ns-01/main.yml` - Added 8 reverse-zone entries (0.16.172, 1.16.172, carrier, child × 2 views)
- `ansible/playbooks/roles/bind9/tasks/verify.yml` - Added 9 dig-based verification tasks with authoritative assertions

## Decisions Made

- Private 1.16.172.in-addr.arpa exposes private-ns PTR record; public view maps host 53 to ns only — prevents private-ns exposure to VPN clients per AUTH-06
- RFC 2317 carrier zone uses CNAME delegation pattern: host octets in parent zone are CNAMEs pointing into the delegated child /28 zone
- Child zone holds actual PTR records for VPN router/client/ns — standard RFC 2317 implementation
- Source-bound dig queries (-b 172.16.1.53 for private, -b 127.0.0.1 for public) force BIND9 view selection
- Full dig output checked for flags: qr aa to confirm authoritative responses, not just present in cache
- private-ns absence in public view verified via ANSWER: 0 or NXDOMAIN status check

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed register variable naming for ansible-lint compliance**
- **Found during:** Task 2 (ansible-lint run)
- **Issue:** ansible-lint `var-naming[no-role-prefix]` requires role-internal register variables to use `bind9_` prefix
- **Fix:** Renamed all `_verify_*` register variables to `_bind9_verify_*`
- **Files modified:** verify.yml
- **Commit:** 182b899

**2. [Rule 1 - Bug] Fixed CNAME record YAML line-length for ansible-lint compliance**
- **Found during:** Task 2 (ansible-lint run)
- **Issue:** CNAME record inline dict entries exceeded 160-char line-length limit
- **Fix:** Reformatted CNAME records from inline `{ name, type, value }` to multi-line YAML dict format
- **Files modified:** main.yml
- **Commit:** 182b899

## Issues Encountered

None.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- All reverse-zone data (local + RFC 2317 VPN) in place for both views
- Dig verification matrix proves split-view forward and reverse resolution
- db.zone.j2 template handles PTR and CNAME records generically — no template changes needed
- config.yml zone render loop and service.yml named-checkzone loop automatically pick up new zones
- Ready for Phase 3 (secondary NS, transfers)

## Self-Check: PASSED

- Both key files exist on disk (main.yml, verify.yml)
- Task 1 commit verified: 1a3f329
- Task 2 commit verified: 182b899
- No accidental file deletions in any commit
- ansible-playbook --syntax-check passes
- ansible-lint passes with 0 failures, 0 warnings
- Pattern verification confirms: in-addr.arpa (8), CNAME (6), PTR (15), dig -b (9), flags: qr aa (5), NXDOMAIN (1)

---
*Phase: 02-primary-authoritative-zones*
*Completed: 2026-05-06*
