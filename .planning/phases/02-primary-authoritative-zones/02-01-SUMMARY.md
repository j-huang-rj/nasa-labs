---
phase: 02-primary-authoritative-zones
plan: 01
subsystem: ansible/bind9
tags: [bind9, views, zones, dns, authoritative, split-view, vpn-identity]

# Dependency graph
requires:
  - phase: 01-bind9-role-foundation
    provides: bind9 component role, config/include scaffold, VPN CIDR derivation, named.conf include pattern
provides:
  - bind9_views and bind9_zones contract with ordered private/public views
  - Runtime-derived DNS identity facts (forward zone name, reverse zone names, VPN host IPs, SOA serial, MNAME)
  - named.zones.conf.j2 template rendering views sorted by order
  - named.zones.conf include in named.conf
affects: [02-02, 02-03, secondary-ns, resolver]

# Tech tracking
tech-stack:
  added: []
  patterns: [ordered-view-rendering, runtime-derived-identity-facts, cross-reference-validation]

key-files:
  created:
    - ansible/playbooks/roles/bind9/templates/named.zones.conf.j2
  modified:
    - ansible/playbooks/roles/bind9/defaults/main.yml
    - ansible/playbooks/roles/bind9/meta/argument_specs.yml
    - ansible/playbooks/roles/bind9/tasks/assert.yml
    - ansible/playbooks/roles/bind9/tasks/config.yml
    - ansible/playbooks/roles/bind9/templates/named.conf.j2
    - ansible/inventory/host_vars/primary-ns-01/main.yml

key-decisions:
  - "View sorting uses Jinja2 sort(attribute='order') to guarantee private-before-public rendering"
  - "DNS identity facts derived from existing VPN CIDR arithmetic in config.yml (no new inventory state)"
  - "SOA serial uses static NN=01 per D2-4; re-running Ansible does not change the serial"
  - "match-clients in private view references ACL names (bind9_dmz_clients, bind9_internal_clients) not CIDR literals"
  - "named.acl.conf.j2 kept without localhost — loopback queries exercise public view per research finding #5"

patterns-established:
  - "Pattern: bind9_views/bind9_zones hybrid contract — view policy and zone data independently extensible"
  - "Pattern: Sorted-by-order view rendering in Jinja2 prevents public 'any' from shadowing private clients"
  - "Pattern: Runtime-derived identity facts in set_fact block keep inventory free of lab-specific state"

requirements-completed:
  - AUTH-02

# Metrics
duration: 3min
completed: 2026-05-06
---

# Phase 2 Plan 01: Primary Authoritative Zones — View and Identity Contract Summary

**Ordered private/public view contract with runtime-derived DNS identity facts, enabling per-view zone rendering without inventory-tracked lab ID**

## Performance

- **Duration:** 3 min
- **Started:** 2026-05-06T10:08:32Z
- ** **Completed:** 2026-05-06T10:11:46Z
- **Tasks:** 2
- **Files modified:** 7 (6 modified, 1 created)

## Accomplishments
- Established `bind9_views` / `bind9_zones` data contract with assertion-guaranteed private-before-public ordering
- Derived all VPN DNS identity facts (router/client/NS IPs, forward/reverse zone names, SOA MNAME/serial) at runtime from WireGuard address arithmetic
- Created `named.zones.conf.j2` template rendering ordered views with per-view zone stanzas
- Wired `named.zones.conf` into the BIND configuration include chain

## Task Commits

Each task was committed atomically:

1. **Task 1: Define the authoritative-primary view and zone contract** - `2b4196d` (feat)
2. **Task 2: Render ordered view scaffolding and derived DNS identity facts** - `c4e9028` (feat)

## Files Created/Modified
- `ansible/playbooks/roles/bind9/templates/named.zones.conf.j2` - New template for ordered view and zone rendering
- `ansible/playbooks/roles/bind9/defaults/main.yml` - Added bind9_views and bind9_zones defaults
- `ansible/playbooks/roles/bind9/meta/argument_specs.yml` - Added bind9_views and bind9_zones option definitions
- `ansible/playbooks/roles/bind9/tasks/assert.yml` - Added authoritative_primary view/zone validation assertions
- `ansible/playbooks/roles/bind9/tasks/config.yml` - Added VPN host IP derivations and DNS identity facts; added zones conf render task
- `ansible/playbooks/roles/bind9/templates/named.conf.j2` - Added named.zones.conf include
- `ansible/inventory/host_vars/primary-ns-01/main.yml` - Added private (order 10) and public (order 99) view definitions

## Decisions Made
- View sorting in template uses `sort(attribute='order')` to guarantee private-before-public rendering, matching BIND9's first-match semantics
- DNS identity facts derived from existing VPN CIDR arithmetic (no new inventory state per D2-3 and quick task h79)
- SOA MNAME derived as `private-ns.{{ bind9_forward_zone_name }}.` in set_fact block, not per-zone inventory data
- Loopback kept out of private view match_clients to preserve the ability to test the public view locally

## Deviations from Plan

None — plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness
- View/zone contract and DNS identity facts ready for 02-02 forward zone data rendering
- `bind9_zones: []` placeholder awaiting population with forward zone records
- `named.zones.conf.j2` template loop over `bind9_zones` ready to render per-view zone stanzas
- VPN-derived facts (`bind9_forward_zone_name`, `bind9_vpn_child_reverse_zone_name`, etc.) available for 02-02 and 02-03 templates

## Self-Check: PASSED

- All 7 key files exist on disk
- Both task commits verified in git log (2b4196d, c4e9028)
- No accidental file deletions in any commit
- ansible-playbook --syntax-check passes
- Pattern verification for bind9_views, bind9_zones, named.zones.conf, bind9_vpn_ns_ip, bind9_vpn_child_reverse_zone_name all confirmed

---
*Phase: 02-primary-authoritative-zones*
*Completed: 2026-05-06*