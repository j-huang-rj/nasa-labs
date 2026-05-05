# NASA Labs — DNS Lab (HW1-1)

## What This Is

Ansible-automated BIND9 DNS infrastructure for the NASA/Network Administration course HW1-1 assignment. Three DNS servers — a primary authoritative NS, a secondary authoritative NS, and an internal recursive resolver — configured with split views, DNSSEC signing, TSIG dynamic updates, and zone transfers. The goal is to pass all Online Judge test cases.

## Core Value

Pass all OJ grading checkpoints: authoritative DNS (forward + reverse, public + private views), zone transfer with NOTIFY, dynamic updates propagating to secondary, recursive resolution with DNSSEC validation (AD bit set).

## Requirements

### Validated

- ✓ Router firewall rules for DNS (port 53 on dmz→internal, internal→vpn) — existing
- ✓ Cloud-init VM configs for primary-ns-01, secondary-ns-01, dns-01 — existing
- ✓ Ansible inventory with host_vars and bind9_enabled flags — existing
- ✓ Network connectivity and NAT routing through router-01 — existing

### Active

- [ ] Primary NS: BIND9 installed and running with two views (private/public)
- [ ] Primary NS: Forward zone files for `${ID}.nasa` (both views with correct A records)
- [ ] Primary NS: Reverse zone files for `172.16.0`, `172.16.1`, and classless `192.168.x.y/28`
- [ ] Primary NS: Zone transfer (allow-transfer + also-notify) to secondary NS
- [ ] Primary NS: Dynamic update with TSIG key for `dynamic1-4` A records + PTR records
- [ ] Primary NS: DNSSEC signing (algorithm 13, digest 2) for forward + VPN reverse zones
- [ ] Secondary NS: Slave replica with same two-view structure, no update/transfer allowed
- [ ] Internal Resolver: Recursive resolution for `nasa.` and `168.192.in-addr.arpa` from root `192.168.255.1`
- [ ] Internal Resolver: Private-view answers for `{ID}.nasa` and `16.172.in-addr.arpa`
- [ ] Internal Resolver: Forward all other domains to Cloudflare `1.1.1.1`
- [ ] Internal Resolver: DNSSEC validation with AD bit for `nasa.` and `168.192.in-addr.arpa`
- [ ] DS record upload to OJ for `${ID}.nasa` and `{ID}-sub28.{x}.168.192.in-addr.arpa`
- [ ] TSIG key upload to OJ

### Out of Scope

- HW1-2 (Mail) — separate assignment
- HW1-3 (LDAP) — separate assignment
- Manual writeup (`manual/dns.md`) — documentation, not automation
- Alternative DNS software (PowerDNS, Unbound, etc.) — BIND9 only per spec guarantee

## Context

- This is a course lab (HW1-1) with a fixed deadline (6/22 23:59 UTC+8)
- The VPN subnet ID is dynamic — derived from WireGuard tools, zones must template `${ID}`
- The existing `bind9` Ansible role is a stub (only a TODO comment in `tasks/main.yml`)
- Router firewall already has DNS-53 allowances in place for dmz→internal and internal→vpn
- All three DNS VMs are already provisioned via cloud-init with correct IPs and network config
- The course recommends IaC (Ansible) approach — we're following that
- HW1-0 through HW1-3 must all pass simultaneously for full credit

## Constraints

- **Software**: BIND9 only — the spec says only BIND9 is tested and guaranteed to pass
- **Automation**: All configuration must be Ansible-automated (no manual server steps)
- **Dynamic ID**: VPN subnet ID comes from WireGuard tools; zone files must template it
- **Firewall**: Must work with existing firewalld rules already on router-01
- **Deadline**: 6/22 23:59 UTC+8 — all HW1-0 through HW1-3 must pass simultaneously

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| BIND9 only | Spec guarantees only BIND9 passes | — Pending |
| Ansible role per component | Matches existing pattern (base, firewall, network, etc.) | — Pending |
| Split-view DNS (private/public) | Spec requires different answers for internal vs external queries | — Pending |
| TSIG for dynamic updates | Spec requires dynamic update support with key-based auth | — Pending |
| DNSSEC algorithm 13 (ECDSAP256SHA256) | Spec mandates this algorithm | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-05-05 after initialization*