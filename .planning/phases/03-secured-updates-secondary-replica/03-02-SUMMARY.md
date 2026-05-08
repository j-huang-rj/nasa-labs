---
phase: 03-secured-updates-secondary-replica
plan: 02
subsystem: dns
tags: [bind9, tsig, dynamic-updates, update-policy, allow-transfer, also-notify, ansible]

# Dependency graph
requires:
  - phase: 03-secured-updates-secondary-replica
    provides: TSIG key contract (bind9_tsig_key), named.keys.conf rendering, controller-side export artifact
provides:
  - Dynamic update policy data in primary host_vars (bind9_dynamic_hosts, dynamic_update_scope, allow_transfer, also_notify)
  - update-policy rendering in named.zones.conf.j2 (forward_a_hosts name grants, ptr_zonesub PTR grants)
  - allow-transfer and also-notify rendering per master zone
  - SELinux-aware private zone file rendering (named_cache_t for dynamic, named_zone_t for static)
  - Primary-side nsupdate verification probes (signed success + unsigned/OOB/AXFR rejection)
  - Assert validation blocking dynamic_update_scope on non-private zones
affects: [03-03]

# Tech tracking
tech-stack:
  added: [nsupdate, update-policy, allow-transfer, also-notify]
  patterns: [data-driven update-policy via dynamic_update_scope zone field, SELinux setype conditional on dynamic_update_scope, named_cache_t for writable zones]

key-files:
  created: []
  modified:
    - ansible/inventory/host_vars/primary-ns-01/main.yml
    - ansible/playbooks/roles/bind9/tasks/assert.yml
    - ansible/playbooks/roles/bind9/tasks/config.yml
    - ansible/playbooks/roles/bind9/tasks/verify.yml
    - ansible/playbooks/roles/bind9/templates/named.zones.conf.j2

key-decisions:
  - "update-policy uses name grants for forward A records (dynamic1-4) and zonesub PTR grants for reverse zones per D-06"
  - "allow-transfer and also-notify use direct IP list [172.16.0.53] per zone, not a separate transfer key per D-10/D-11"
  - "Private writable zone files use named_cache_t SELinux context while public/static files remain named_zone_t"
  - "dynamic_update_scope zone field drives both update-policy rendering and SELinux setype selection"

patterns-established:
  - "Zone-level policy fields: allow_transfer, also_notify, dynamic_update_scope extend the existing bind9_zones data model per zone"
  - "Conditional SELinux setype: render_zone_data_files setype is selected from item.dynamic_update_scope presence, not from view name"
  - "Assert-gated policy: assert.yml blocks dynamic_update_scope on non-private zones before config reaches the template"
  - "Signed nsupdate verification: create/modify/add-PTR/delete success path plus unsigned, out-of-policy, and AXFR rejection checks"

requirements-completed: [AUTH-07, AUTH-08]

# Metrics
duration: 4min
completed: 2026-05-08
---

# Phase 03 Plan 02: Secured Updates Secondary Replica Summary

**Primary authoritative zone update policy, transfer control, and verification probes for signed dynamic updates and rejected operations**

## Performance

- **Duration:** 4 min
- **Started:** 2026-05-08T17:01:31Z
- **Completed:** 2026-05-08T17:06:16Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments
- Added `bind9_dynamic_hosts: ["dynamic1", "dynamic2", "dynamic3", "dynamic4"]` to primary host vars — exact list of allowed update hostnames per D-05
- Extended zone entries with `dynamic_update_scope` (forward_a_hosts for private forward, ptr_zonesub for private reverse), `allow_transfer`, and `also_notify` — no policy on public/VPN zones per D-07/D-08
- Rendered `update-policy` (name grants for dynamic1-4 A + zonesub PTR grants), `allow-transfer`, and `also-notify` in `named.zones.conf.j2`
- Added assert validation that blocks `dynamic_update_scope` on non-private zones and enforces the exact dynamic1-4 list
- Made private writable zone files use `named_cache_t` SELinux context for journal/dynamic write support
- Added full nsupdate verification: signed create/modify/add-PTR/delete success path, unsigned rejection, out-of-policy signed rejection, and AXFR refusal from loopback

## Task Commits

Each task was committed atomically:

1. **Task 1: Add exact primary-side update, transfer, and notify policy data** - `4c5c03b` (feat)
2. **Task 2: Render secure primary policy and prove allowed vs rejected operations** - `5e41034` (feat)

## Files Created/Modified
- `ansible/inventory/host_vars/primary-ns-01/main.yml` - Added bind9_dynamic_hosts, dynamic_update_scope, allow_transfer, also_notify to zone entries
- `ansible/playbooks/roles/bind9/tasks/assert.yml` - Added dynamic_hosts exact list assertion and non-private zone dynamic_update_scope block
- `ansible/playbooks/roles/bind9/tasks/config.yml` - Changed zone file setype to conditional named_cache_t for dynamic zones
- `ansible/playbooks/roles/bind9/tasks/verify.yml` - Added signed nsupdate probes (create/modify/PTR/delete) and rejection checks (unsigned, OOB, AXFR)
- `ansible/playbooks/roles/bind9/templates/named.zones.conf.j2` - Added allow-transfer, also-notify, and update-policy rendering branches

## Decisions Made
- update-policy uses name grants for forward A records (dynamic1-4) and zonesub PTR grants for reverse zones per D-06 — this matches the lab spec requirement exactly
- allow-transfer and also-notify use direct IP list [172.16.0.53] per zone per D-10/D-11 — no separate transfer key methodology
- Private writable zone files use named_cache_t SELinux context while static/public files remain named_zone_t — enables BIND journal writes under enforcing mode
- dynamic_update_scope zone field drives both update-policy rendering and SELinux setype selection — single source of truth per zone

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Primary update policy, transfer control, and notification configured — ready for Plan 03 (secondary mirror)
- TSIG key contract from Plan 01 is in place for nsupdate commands
- assert.yml gates ensure no dynamic_update_scope on non-private zones
- Verification probes cover both success and rejection paths for OJ grading

---
*Phase: 03-secured-updates-secondary-replica*
*Completed: 2026-05-08*

## Self-Check: PASSED

- All 5 key files exist on disk
- Both 03-02 commit hashes verified in git log (4c5c03b, 5e41034)
- ansible-playbook --syntax-check passes
- All plan verification grep patterns confirmed