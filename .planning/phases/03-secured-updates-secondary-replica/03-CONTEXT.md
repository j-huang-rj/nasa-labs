# Phase 3: Secured Updates & Secondary Replica - Context

**Gathered:** 2026-05-08
**Status:** Ready for planning

<domain>
## Phase Boundary

Accept only authorized TSIG-keyed dynamic updates on the primary (restricted to `dynamic1-4` A records and PTR records in private reverse zones), replicate all zone data to a read-only secondary via NOTIFY + zone transfer within 10 seconds, and produce the TSIG key artifact for OJ upload. The secondary must serve identical split-view content but reject direct updates and onward transfers.

</domain>

<decisions>
## Implementation Decisions

### TSIG Key Strategy
- **D-01:** Single shared TSIG key for all BIND9 paths (update, transfer, notify). One key covers `update-policy`, `allow-transfer` (if TSIG were used), and `also-notify` — no separate keys per operation.
- **D-02:** Pre-generate the TSIG key using `tsig-keygen` outside Ansible, store in `secrets.yml` on both primary and secondary hosts. Follows the existing secret split pattern (`secrets.yml` gitignored, `secrets.example.yml` tracked with placeholders).
- **D-03:** The TSIG key definition is rendered via a new `named.keys.conf.j2` template included from `named.conf.j2`, keeping key material separate from zone/policy configuration.
- **D-04:** OJ submission artifact: the TSIG key name, algorithm, and secret — exported from `secrets.yml` in the format the OJ tool expects.

### Update Policy Boundaries
- **D-05:** Data-driven grant enumeration: define `bind9_dynamic_hosts: ["dynamic1", "dynamic2", "dynamic3", "dynamic4"]` in `host_vars/primary-ns-01/main.yml`. The template iterates this list to emit exact `name` match grants in `update-policy`.
- **D-06:** BIND9 `update-policy` uses `name` match type for forward zone A records (exact hostname grants — only `dynamic1-4` can be updated, not arbitrary subdomains). Uses `zonesub` match type for PTR records in reverse zones (allows any PTR within the specific reverse zone).
- **D-07:** `update-policy` applies only to the **private view** copy of the forward zone `${ID}.nasa`. The public view must remain read-only (no update-policy).
- **D-08:** PTR update grants apply to `0.16.172.in-addr.arpa` and `1.16.172.in-addr.arpa` (private view reverse zones) only. The VPN reverse zone (`{ID}-sub28.{x}.168.192.in-addr.arpa`, public view) must NOT receive update-policy.
- **D-09:** BIND9 `update-policy` does not distinguish create vs. modify vs. delete — if a name+type pair is granted, all three operations are permitted. This is acceptable per spec.

### Zone Transfer Authentication
- **D-10:** IP-based ACL for zone transfers: `allow-transfer { 172.16.0.53; }` on the primary. Extends the existing `named.acl.conf.j2` ACL pattern with zero new secrets.
- **D-11:** `also-notify { 172.16.0.53; }` on the primary for each zone/view, ensuring the secondary receives NOTIFY messages to initiate transfers within the 10-second window.
- **D-12:** The secondary has NO `allow-transfer` and NO `allow-update` — it is a read-only replica per SEC-04.

### Secondary View Mirroring
- **D-13:** Full explicit mirror in `host_vars/secondary-ns-01/main.yml`: define `bind9_views` (same two-view structure as primary) and `bind9_zones` (same zone names/views, but `type: slave` with `masters: [172.16.1.53]`). Zero template or arg_specs changes needed — the existing `named.zones.conf.j2` already supports `type: slave` and `masters`.
- **D-14:** Slave zone files are stored in `/var/named/slaves/` (already created by `config.yml` when `bind9_mode == 'authoritative_secondary'`). View-specific subdirectories (`slaves/private/`, `slaves/public/`) may be used if needed for disambiguation.
- **D-15:** The secondary's views use the same ACL names (`dmz_clients`, `internal_clients`, `vpn_clients`) as the primary. The `named.acl.conf.j2` template renders these ACLs for all authoritative modes.

### the agent's Discretion
- Exact TSIG key name convention (e.g., `update-key` vs. `tsig-key` vs. `${ID}-update`) — planner/researcher can choose a clear, descriptive name.
- Whether to pre-create `dynamic1-4` A records in zone data files with placeholder IPs or let `nsupdate` create them from scratch — planner can decide based on verification convenience.
- Whether slave zone file paths use view-specific subdirectories (`slaves/private/`, `slaves/public/`) or flat naming (`slaves/db.private.${ID}.nasa`) — planner can choose based on BIND9 best practices.
- SOA serial update strategy for dynamic zones (BIND9 auto-increments journal serials, but initial zone data serial format) — planner can follow the existing YYYYMMDDNN convention.
- Exact `also-notify` placement (per-zone in `named.zones.conf.j2` vs. global in `named.options.conf.j2`) — planner can choose based on template structure.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Lab Specification
- `lab/dns.md` — Authoritative HW1-1 spec: dynamic update policy (§Dynamic zone), zone transfer requirements (§Zone transfer), secondary NS requirements (§Secondary name server), grading rubric (§Grading)

### Existing Codebase
- `ansible/playbooks/roles/bind9/templates/named.zones.conf.j2` — Zone renderer; already supports `type: slave` with `masters` directive; needs `allow-transfer`, `also-notify`, and `update-policy` additions
- `ansible/playbooks/roles/bind9/templates/named.conf.j2` — Main config; needs `named.keys.conf` include
- `ansible/playbooks/roles/bind9/templates/named.acl.conf.j2` — ACL definitions; may need transfer ACL addition
- `ansible/playbooks/roles/bind9/templates/named.options.conf.j2` — Options block; may need `also-notify` global defaults
- `ansible/playbooks/roles/bind9/templates/db.zone.j2` — Zone data template; needs dynamic host record support
- `ansible/playbooks/roles/bind9/defaults/main.yml` — Role defaults; needs TSIG key path, dynamic zone dir defaults
- `ansible/playbooks/roles/bind9/meta/argument_specs.yml` — Argument schema; needs `bind9_dynamic_hosts`, `bind9_tsig_key` additions
- `ansible/playbooks/roles/bind9/tasks/config.yml` — Config tasks; needs SELinux context for dynamic zone dir, key file rendering
- `ansible/playbooks/roles/bind9/tasks/verify.yml` — Verification; needs `nsupdate` and AXFR/IXFR tests
- `ansible/inventory/host_vars/primary-ns-01/main.yml` — Primary NS host vars; needs `bind9_dynamic_hosts`, `bind9_tsig_key`, transfer/notify config
- `ansible/inventory/host_vars/secondary-ns-01/main.yml` — Secondary NS host vars; needs full `bind9_views` and `bind9_zones` with slave type
- `ansible/inventory/host_vars/primary-ns-01/secrets.example.yml` — TSIG key placeholder template
- `ansible/inventory/host_vars/secondary-ns-01/secrets.example.yml` — TSIG key placeholder template (same key)

### Prior Phase Decisions
- `.planning/STATE.md` — Accumulated context: zone data schema, view rendering, VPN IP derivation, SOA timers, SELinux setype attributes
- `.planning/REQUIREMENTS.md` — AUTH-07, AUTH-08, SEC-02, SEC-03, SEC-04, SEC-05, AUTO-03 requirements
- `.planning/ROADMAP.md` — Phase 3 success criteria and plan outline

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **`named.zones.conf.j2` template**: Already renders `type: slave` zones with `masters` directive. Only needs `allow-transfer`, `also-notify`, and `update-policy` additions per zone/view.
- **`named.acl.conf.j2` template**: Already defines `dmz_clients`, `internal_clients`, `vpn_clients` ACLs. The secondary reuses these same ACLs for view matching.
- **`config.yml` task**: Already creates `/var/named/slaves/` directory when `bind9_mode == 'authoritative_secondary'` and `/var/named/dynamic/` with `named_cache_t` SELinux context for primary mode.
- **`verify.yml` task**: Already has mode-specific dig tests. Needs `nsupdate` and AXFR/propagation timing tests for Phase 3.
- **`argument_specs.yml`**: Already validates `bind9_views` and `bind9_zones` structure. Needs new optional fields for dynamic hosts and TSIG key.
- **Secret split pattern**: `secrets.yml` (gitignored) + `secrets.example.yml` (tracked, commented placeholders). TSIG key follows this pattern.

### Established Patterns
- **Component role pattern**: One `bind9` role driven by `host_vars`. No mode-specific branching in templates — behavior is data-driven.
- **Zone data schema**: `bind9_views` (policy: name, order, match-clients) + `bind9_zones` (data: name, view, type, records, etc.). Phase 3 extends this with `update_policy_rules`, `allow_transfer`, `also_notify` fields.
- **Feature flags**: `bind9_enabled` controls role inclusion. No new feature flags needed for Phase 3.
- **SELinux context**: Config paths use `named_conf_t`, dynamic zone dir uses `named_cache_t`. TSIG key file needs `named_conf_t`.
- **Logging convention**: `PHASE [<name> : <task>]` naming. New tasks follow this pattern.

### Integration Points
- **`dns.yml` playbook**: Pre-tasks derive VPN identity from router-01's `wireguard_address`. TSIG key reference in `secrets.yml` is consumed by the `bind9` role template rendering.
- **`named.conf.j2`**: Needs a new `include` directive for `named.keys.conf` (TSIG key definition).
- **`named.zones.conf.j2`**: Needs `allow-transfer`, `also-notify`, and `update-policy` directives rendered per zone/view.
- **`host_vars/secondary-ns-01/main.yml`**: Currently a stub (51 lines). Needs full `bind9_views` and `bind9_zones` definitions mirroring the primary's structure with `type: slave`.
- **`host_vars/primary-ns-01/secrets.yml`** and **`host_vars/secondary-ns-01/secrets.yml`**: Need TSIG key material (same key on both hosts).

</code_context>

<specifics>
## Specific Ideas

- The lab spec (`lab/dns.md` §Dynamic zone) explicitly states: "only allow updating the A records of dynamic1-4" and "only allow updating PTR records" in the reverse zones. This maps directly to BIND9 `update-policy` with `name` match for forward and `zonesub` for reverse.
- The lab spec (`lab/dns.md` §Zone transfer) states: "IXFR is optional, as long as the whole transfer process completes within 10 seconds." This means AXFR is acceptable and NOTIFY is required.
- The lab spec (`lab/dns.md` §Secondary name server) states: "the secondary NS should not be updatable or transferable." This means no `allow-update` and no `allow-transfer` on the secondary.
- The OJ grading rubric allocates 13% to dynamic update (10% for propagation to secondary) and 12% to secondary NS functionality. Propagation timing is critical.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.
</deferred>

---

*Phase: 03-secured-updates-secondary-replica*
*Context gathered: 2026-05-08*