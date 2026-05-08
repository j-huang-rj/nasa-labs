---
id: SEED-002
status: dormant
planted: 2026-05-08
planted_during: Phase 02 (primary-authoritative-zones)
trigger_when: When provisioning WireGuard on primary-ns-01, or when implementing post-converge DNS verification, or when working on Phase 3+ (secondary NS / zone transfers / WireGuard)
scope: Medium
---

# SEED-002: Enable Automated Public-View DNS Verification

## Why This Matters

127.0.0.1 was added to the private view's `match_clients` because local processes (zone transfers, health checks) should see internal records — this is the correct operational posture. However, this makes local public-view verification impossible: every reachable source IP (127.0.0.1, 172.16.1.53) matches the private view first, so no query can fall through to the public view from the primary NS itself.

The current `verify.yml` only tests the private view via source-bound `dig -b` queries. Public-view correctness (VPN IPs, no private-ns exposure) is asserted structurally in zone data but never verified at runtime with an actual DNS query.

## When to Surface

**Trigger:** When provisioning WireGuard on primary-ns-01, or when implementing post-converge verification, or when working on Phase 3+ (secondary NS / zone transfers / WireGuard)

This seed should be presented during `/gsd-new-milestone` when the milestone scope matches any of these conditions:
- Adding WireGuard interface to primary-ns-01
- Implementing cross-host DNS verification (secondary NS querying primary)
- Building a post-converge verification play that runs after all DNS servers and WireGuard are provisioned
- Working on Phase 3 (secondary NS) or later phases that involve WireGuard

## Scope Estimate

**Medium** — A phase or two. Requires: (1) WireGuard on primary-ns-01 to acquire a VPN IP, (2) a separate post-converge verification play that runs from the secondary NS using its VPN IP as source to query the primary's VPN IP. The verification play itself is straightforward once the network path exists.

## Breadcrumbs

Related code and decisions found in the current codebase:

- `ansible/inventory/host_vars/primary-ns-01/main.yml` — bind9_views definition with 127.0.0.1 in private match_clients (lines 32-43)
- `ansible/playbooks/roles/bind9/tasks/verify.yml` — current source-bound dig verification only tests private view (lines 84, 110, 126)
- `ansible/playbooks/roles/bind9/tasks/assert.yml` — structural validation of bind9_views ordering and zone-view cross-references (lines 35-101)
- `ansible/playbooks/roles/bind9/templates/named.zones.conf.j2` — ordered view rendering template
- `.planning/phases/02-primary-authoritative-zones/CONTEXT.md` — D2-1 (hybrid views+zones schema), D2-3 (VPN IP derivation)
- `.planning/phases/02-primary-authoritative-zones/02-03-SUMMARY.md` — source-bound dig verification matrix (9 tasks, all private-view)

## Notes

### Current Limitation

Public-view verification is intentionally omitted from the bind9 role. The primary NS (primary-ns-01) has no WireGuard interface, so there is no VPN-side source IP available to send a query that falls through to the public view.

### Proposed Implementation

To enable automated public-view verification:

1. Add WireGuard to primary-ns-01 so it acquires a VPN IP
2. From the secondary NS (which already has wg0), run:
   ```
   dig -b <secondary_vpn_ip> @<primary_vpn_ip> <query> <type> +norecurse
   ```
   The VPN source IP will not match any private-view ACL, so the query will fall through to the public view.

3. This should be implemented as a **separate post-converge verification play** that runs after both DNS servers and WireGuard are fully provisioned — not as part of the bind9 role itself, since the role cannot assume WireGuard exists on the target host.

### Design Decision Record

- 127.0.0.1 in private match_clients is correct for operational reasons (zone transfers, health checks need internal view)
- Structural assertions in assert.yml and zone data already validate public-view correctness (no private-ns, VPN IPs only)
- Runtime verification of public view requires cross-host network path that doesn't exist yet