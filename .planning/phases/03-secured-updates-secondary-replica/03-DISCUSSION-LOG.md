# Phase 3: Secured Updates & Secondary Replica - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-08
**Phase:** 03-secured-updates-secondary-replica
**Areas discussed:** TSIG key strategy, Update policy boundaries, Zone transfer authentication, Secondary view mirroring

---

## TSIG Key Strategy

| Option | Description | Selected |
|--------|-------------|----------|
| Single shared key, pre-generated | Pre-generate with tsig-keygen, store in secrets.yml on both hosts. Fits existing pattern, idempotent, single OJ artifact. | ✓ |
| Single shared key, Ansible-generated | Ansible command task generates key on primary, fact-distributes to secondary. Fully automated but fragile idempotency. | |
| Separate update + transfer keys | Separate keys for update vs. transfer/notify. Defense in depth but over-engineered for 3-host lab. | |

**User's choice:** Single shared key, pre-generated
**Notes:** Fits the existing secret split pattern. One key covers all BIND9 paths (update-policy, allow-transfer if TSIG were used, also-notify). Minimizes OJ export to one artifact.

---

## Update Policy Boundaries

| Option | Description | Selected |
|--------|-------------|----------|
| Data-driven from host_vars | Define bind9_dynamic_hosts list in host_vars, template iterates to emit exact-name grants. Maintainable, data-driven. | ✓ |
| Exact-name grants inline | Hardcode 4 grant rules per forward zone in template. Maximum precision, no extra variables. | |
| Subdomain delegation | Delegate dynamic.{Z}.nasa as separate child zone with wildcard grant. ISC best practice but adds zone topology complexity. | |
| Separate policy file per zone | Generate named.policy.conf per zone, zone statements include these files. Cleanest separation but overkill for 4-host scope. | |

**User's choice:** Data-driven from host_vars
**Notes:** Uses `name` match type for forward zone A records (exact hostname grants) and `zonesub` for PTR records in reverse zones. Update-policy applies only to the private view. VPN reverse zone must NOT receive update-policy.

---

## Zone Transfer Authentication

| Option | Description | Selected |
|--------|-------------|----------|
| IP-based ACL | allow-transfer { 172.16.0.53; } — extends existing ACL pattern, zero new secrets, matches spec literal text. | ✓ |
| TSIG-authenticated | allow-transfer { key "xfer-key"; } — cryptographic verification, ISC recommended, but adds key distribution complexity. | |
| IP + TSIG combined | allow-transfer { 172.16.0.53; key "xfer-key"; } — defense in depth, but overkill for fixed-topology lab. | |

**User's choice:** IP-based ACL
**Notes:** Extends the existing named.acl.conf.j2 ACL pattern. The secondary has a fixed IP (172.16.0.53). OJ tests functional propagation, not auth method. TSIG for updates is a separate requirement with its own key.

---

## Secondary View Mirroring

| Option | Description | Selected |
|--------|-------------|----------|
| Full explicit mirror in host_vars | Define bind9_views and bind9_zones in secondary-ns-01/main.yml with type: slave and masters. Zero code changes. | ✓ |
| Views in group_vars, zones in host_vars | Move bind9_views to group_vars/dns.yml, keep per-host bind9_zones. DRY for views but resolver inherits unused vars. | |
| Derive from primary via hostvars | Secondary reads hostvars['primary-ns-01'].bind9_zones and transforms master→slave. Single source of truth but violates component role pattern. | |

**User's choice:** Full explicit mirror in host_vars
**Notes:** The existing named.zones.conf.j2 template already supports type: slave with masters directive. Zero template or arg_specs changes needed — just populate host_vars. Self-contained per host, explicit audit trail.

---

## the agent's Discretion

- Exact TSIG key name convention
- Whether to pre-create dynamic1-4 A records in zone data files or let nsupdate create them
- Slave zone file path naming (flat vs. view-specific subdirectories)
- SOA serial update strategy for dynamic zones
- also-notify placement (per-zone vs. global)

## Deferred Ideas

None — discussion stayed within phase scope.