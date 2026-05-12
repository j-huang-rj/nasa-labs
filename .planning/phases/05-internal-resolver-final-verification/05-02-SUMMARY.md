---
phase: 05-internal-resolver-final-verification
plan: 02
subsystem: dns
tags: [bind9, dns, ansible, resolver, forward-zone, dnssec, ad-bit, acl]

# Dependency graph
requires:
  - phase: 05-01
    provides: Resolver-mode zone rendering via named.zones.conf, trust-anchor template and runtime DNSKEY fetch
provides:
  - Resolver per-zone forward routing and Cloudflare global forwarder in dns-01 host_vars
  - Expanded resolver verification matrix (private-view routing, AD-bit, blocked-client)
  - RES-02 through RES-06 readiness via role-level dig assertions
affects: [05-03, dns-resolver, dnssec, verification]

# Tech tracking
tech-stack:
  added: []
  patterns: [per-zone type-forward routing overriding global forward-only, delegated blocked-client probe via router WireGuard source IP]

key-files:
  created: []
  modified:
    - ansible/inventory/host_vars/dns-01/main.yml
    - ansible/playbooks/roles/bind9/tasks/verify.yml

key-decisions:
  - "Four global-scoped per-zone `type forward; forward only;` blocks targeting the course root and lab primary NS per D-01/D-02/D-03"
  - "Per-zone forward overrides are required because the global `forward only` policy does NOT bypass `static-stub` zones (ARM Reference); only `type forward` zones bypass global forwarding"
  - "Blocked-client probe uses router's WireGuard source IP via delegate_to per D-14"
  - "AD-bit checks use dig +dnssec SOA queries to force EDNS with DO bit per RES-05"

patterns-established:
  - "Resolver per-zone forward routing: each lab zone declares `type forward; forward only; forwarders { <ip>; };` so the global `forward only` -> Cloudflare policy applies to everything except the explicitly listed lab zones"
  - "Delegated verification: blocked-client probe delegates to router and uses its WireGuard IP as source"

requirements-completed:
  - RES-02
  - RES-03
  - RES-04
  - RES-05
  - RES-06

# Metrics
duration: 2min
completed: 2026-05-10
---

# Phase 5 Plan 02: Resolver Forward-Zone Routing & Verification Matrix Summary

**Four per-zone forward declarations and Cloudflare global forwarder in dns-01 host_vars, plus expanded resolver verification covering private-view routing, AD-bit DNSSEC validation, and blocked-client ACL enforcement**

## Performance

- **Duration:** 2 min
- **Started:** 2026-05-10T17:11:00Z
- **Completed:** 2026-05-10T17:13:34Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- Declared resolver `bind9_forwarders: [1.1.1.1]` and four global `bind9_zones` entries each with `type: forward, forward: only, forwarders: [...]` in dns-01 host_vars
- Per-zone forwards route nasa./168.192.in-addr.arpa. to course-root 192.168.255.1 and lab zones to primary NS 172.16.1.53
- Expanded resolver verify.yml with course-root NOERROR assertions (RES-02), private-view routing checks (RES-03), AD-bit DNSSEC validation (RES-05), and blocked VPN-subnet probe (RES-06)

## Task Commits

Each task was committed atomically:

1. **Task 1: Declare the resolver forward zones and Cloudflare forwarder** - `898a02d` (feat, originally as static-stub; corrected post-execution)
2. **Task 2: Expand resolver verification for private answers, DNSSEC AD-bit checks, and blocked clients** - `31d2306` (feat)

## Files Created/Modified
- `ansible/inventory/host_vars/dns-01/main.yml` - Added bind9_forwarders [1.1.1.1] and four global bind9_zones forward entries
- `ansible/playbooks/roles/bind9/tasks/verify.yml` - Added 6 new resolver verification tasks: nasa SOA, 168.192.in-addr.arpa SOA, private-NS forward/reverse, forward zone AD-bit, blocked-client probe

## Decisions Made
- Four global-scoped `type forward; forward only;` zones with no view field per D-01/D-02/D-03
- Per-zone forwards required: BIND's global `forward only` policy does NOT bypass `static-stub` zones — only `type forward` zones bypass global forwarding (ARM Reference and BIND 9.8.4-P2 changelog confirm this). The original D-12 assumption that "longest-prefix match" would cause static-stub to override the global forwarder was incorrect; longest-prefix selection applies to forward zones, not static-stub.
- VPN child reverse zone (`{{ bind9_vpn_child_reverse_zone_name }}`) AD-bit assertions are NOT verified from internal vantage points. The zone is declared only in primary-ns-01's `public` view, whose `match-clients` excludes `internal_clients` and `dmz_clients`. dns-01 (172.16.1.153), dmz-agent-01 (172.16.0.123), and internal-agent-01 (172.16.1.123) all match the exclusion ACLs and receive REFUSED from the lab primary NS for that zone. AD-bit validation for it is grading-time-only (TA queries from the VPN subnet at 192.168.255.x). The forward-zone (`{{ bind9_forward_zone_name }}`) AD-bit check on internal vantage already proves the validator is wired against the runtime trust anchors.
- Blocked-client probe uses router's WireGuard source IP via delegate_to per D-14
- AD-bit checks use dig +dnssec SOA queries forcing EDNS with DO bit per RES-05

## Deviations from Plan

The plan as written declared `type: static-stub` zones; runtime testing during phase finalization showed those zones were silently bypassed by the global `forward only` policy, producing SERVFAIL with `insecurity proof failed resolving 'nasa/SOA/IN': 1.1.1.1#53` in BIND logs (Cloudflare cannot serve the lab's signed zones). After confirming the BIND semantics with ISC ARM citations, the inventory was changed in-place to `type: forward; forward: only; forwarders: [...]` per zone. The bind9 role template (`named.zones.conf.j2`) already supported this without modification.

The plan also specified VPN child reverse zone AD-bit assertions in verify.yml and from DMZ/Private vantage in dns_e2e.yml. Runtime testing showed those assertions could never pass from internal vantage because primary-ns-01 view scoping (public-view-only zone, match-clients excludes lab subnets) returns REFUSED. The three internal-vantage assertions were removed; the corresponding TA-side validation happens at grading from the VPN subnet, where the public view is reachable.

## Issues Encountered

1. The original `static-stub` zone design did not bypass global forwarding. Corrected to per-zone `type forward` declarations.
2. VPN child reverse zone AD-bit assertions were over-specified for internal vantage and unreachable by view-scoping design. Assertions removed; coverage retained for the forward zone (which IS in the private view and validates from internal vantage).

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Resolver host vars fully declare per-zone forward routing and Cloudflare fallback forwarding
- Verification matrix covers RES-02 through RES-06 at the role level
- Ready for 05-03 (end-to-end cross-host verification and idempotency checks)

## Self-Check: PASSED

- SUMMARY.md: FOUND
- Task 1 commit (898a02d): FOUND
- Task 2 commit (31d2306): FOUND
- Metadata commit (5a1bb02): FOUND
- dns-01/main.yml: FOUND
- verify.yml: FOUND
- No unexpected file deletions across any commit
- No stubs or placeholder patterns detected
- No security-relevant surface beyond plan scope
- Pre-existing dirty bind9 template files left untouched

---
*Phase: 05-internal-resolver-final-verification*
*Completed: 2026-05-10*