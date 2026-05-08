---
phase: 03-secured-updates-secondary-replica
plan: 01
subsystem: dns
tags: [tsig, bind9, ansible, secrets, dynamic-updates]

# Dependency graph
requires:
  - phase: 02-primary-authoritative-zones
    provides: bind9 role with views, zones, ACLs, and zone data templates
provides:
  - Shared TSIG key contract (bind9_tsig_key) for both authoritative hosts
  - named.keys.conf.j2 template rendered from bind9_tsig_key
  - Controller-local TSIG export artifact at .opencode/artifacts/phase-03-tsig-upload.txt
  - Tracked placeholder schema in secrets.example.yml for both hosts
affects: [03-02, 03-03]

# Tech tracking
tech-stack:
  added: [tsig-keygen, named.keys.conf include]
  patterns: [gitignored secrets + tracked placeholders, controller-side artifact export, include-before-zones key loading]

key-files:
  created:
    - ansible/inventory/host_vars/primary-ns-01/secrets.example.yml
    - ansible/playbooks/roles/bind9/templates/named.keys.conf.j2
    - .opencode/artifacts/phase-03-tsig-upload.txt
  modified:
    - ansible/playbooks/roles/bind9/defaults/main.yml
    - ansible/playbooks/roles/bind9/meta/argument_specs.yml
    - ansible/inventory/host_vars/secondary-ns-01/secrets.example.yml
    - ansible/playbooks/roles/bind9/templates/named.conf.j2
    - ansible/playbooks/roles/bind9/tasks/config.yml
    - ansible/playbooks/roles/bind9/tasks/verify.yml

key-decisions:
  - "Single shared TSIG key (lab_ddns_shared/hmac-sha256) for all BIND9 auth paths per D-01/D-02"
  - "Key definition rendered via named.keys.conf.j2 included before zones per D-03"
  - "Controller-side artifact export follows D-04: name, algorithm, secret from same gitignored source"
  - "Preserved existing secret split pattern: secrets.example.yml (tracked placeholders) + secrets.yml (gitignored live values)"

patterns-established:
  - "TSIG key contract: defaults provide name/algorithm with empty secret; secrets.yml overrides with live value"
  - "Include chain order: named.acl.conf → named.options.conf → named.keys.conf → named.zones.conf (keys before zones)"
  - "Artifact export pattern: delegate_to:localhost + run_once:true for controller-side assertions and file generation"

requirements-completed: [AUTH-07, AUTO-03]

# Metrics
duration: 3min
completed: 2026-05-08
---

# Phase 03 Plan 01: Secured Updates Secondary Replica Summary

**Shared TSIG key contract, named.keys.conf rendering, and controller-local OJ export artifact established for both authoritative hosts**

## Performance

- **Duration:** 3 min
- **Started:** 2026-05-08T16:55:40Z
- **Completed:** 2026-05-08T16:59:25Z
- **Tasks:** 2
- **Files modified:** 8

## Accomplishments
- Established a single canonical TSIG key contract (`bind9_tsig_key`) with `lab_ddns_shared` / `hmac-sha256` defaults, shared by both authoritative hosts
- Created `named.keys.conf.j2` template included from `named.conf.j2` before the zones stanza, ensuring key definitions are available to future `update-policy` and `allow-transfer` directives
- Generated controller-local TSIG export artifact at `.opencode/artifacts/phase-03-tsig-upload.txt` for OJ submission
- Added verify.yml assertion that `bind9_tsig_key` is present with non-empty name/algorithm/secret before deployment continues

## Task Commits

Each task was committed atomically:

1. **Task 1: Extend the tracked TSIG secret contract and placeholder files** - `0c9fa26` (feat)
2. **Task 2: Render the shared key include and create the local TSIG artifact** - `88a5e02` (feat)

## Files Created/Modified
- `ansible/inventory/host_vars/primary-ns-01/secrets.example.yml` - TSIG key placeholder schema for primary NS
- `ansible/inventory/host_vars/secondary-ns-01/secrets.example.yml` - Extended with TSIG key placeholder
- `ansible/playbooks/roles/bind9/defaults/main.yml` - Added bind9_tsig_key, bind9_keys_conf_path, bind9_tsig_artifact_path
- `ansible/playbooks/roles/bind9/meta/argument_specs.yml` - Documented bind9_tsig_key, bind9_keys_conf_path, bind9_tsig_artifact_path
- `ansible/playbooks/roles/bind9/templates/named.conf.j2` - Added named.keys.conf include before zones
- `ansible/playbooks/roles/bind9/templates/named.keys.conf.j2` - New template rendering BIND key stanza from bind9_tsig_key
- `ansible/playbooks/roles/bind9/tasks/config.yml` - Added named.keys.conf render task with SELinux context
- `ansible/playbooks/roles/bind9/tasks/verify.yml` - Added localhost assertion/export block for TSIG key

## Decisions Made
- Single shared TSIG key `lab_ddns_shared` for all BIND9 auth paths (update, transfer, notify) per D-01
- Key material rendered via dedicated `named.keys.conf.j2` included before zones (D-03), keeping key config separate from zone policy
- Controller-side export follows D-04: three canonical fields (name, algorithm, secret) derived from the same gitignored source
- Preserved existing secret split pattern: tracked placeholders only, live values in gitignored secrets.yml

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- TSIG key contract ready for Phase 03 Plan 02 (update-policy, allow-transfer, also-notify)
- Key rendering pipeline verified via ansible-playbook --syntax-check
- Both authoritative hosts have consistent placeholder schemas; only live secrets.yml differs
- named.keys.conf include positioned before zones, making key available for future zone policy directives

---
*Phase: 03-secured-updates-secondary-replica*
*Completed: 2026-05-08*