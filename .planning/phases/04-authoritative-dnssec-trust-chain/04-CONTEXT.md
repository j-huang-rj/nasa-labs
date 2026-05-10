# Phase 4: Authoritative DNSSEC Trust Chain - Context

**Gathered:** 2026-05-10
**Status:** Ready for planning

<domain>
## Phase Boundary

Sign the graded authoritative zones (`${ID}.nasa` and `${ID}-sub28.{x}.168.192.in-addr.arpa`) with DNSSEC algorithm 13 (ECDSAP256SHA256), generate DS records ready for OJ upload, and ensure the `172.16.{0|1}` reverse zones remain unsigned and authoritative without DNSSEC.

</domain>

<decisions>
## Implementation Decisions

### DNSSEC Signing Method
- **D-01:** Use `dnssec-policy "nasa-lab"` — a custom BIND9 dnssec-policy block with explicit algorithm 13 (ECDSAP256SHA256), CDS digest type 2 (SHA-256), and unlimited CSK lifetime. Applied per-zone only to signing-eligible zones.
- **D-02:** The `dnssec-policy` block is defined in `named.options.conf.j2` (or a dedicated include) and referenced by name in `named.zones.conf.j2` per-zone via `dnssec-policy nasa-lab;` directive. Zones that must NOT be signed (172.16.{0|1} reverse zones) simply omit the directive.
- **D-03:** `inline-signing yes;` is included in the zone block for signed zones, allowing BIND to maintain the `.signed` sidecar alongside the unsigned zone file without disrupting the existing hash-based idempotency pipeline.
- **D-04:** The unsigned zone file (rendered by `db.zone.j2`) remains the source of truth. BIND's inline-signing maintains the `.signed` version independently. The hash-sidecar pipeline tracks the unsigned template — as long as the unsigned template stays hash-stable, the signed output is never disturbed.

### Key Management Strategy
- **D-05:** Pre-generate DNSSEC signing keys using `dnssec-keygen -G` (no timing metadata) on the Ansible control node. Store key material in `secrets.yml` following the existing secret split pattern (`secrets.yml` gitignored, `secrets.example.yml` tracked with placeholders).
- **D-06:** Distribute keys to the primary NS key-directory via Ansible template. BIND's KASP engine adopts imported keys with no timing metadata without auto-retiring them.
- **D-07:** One CSK (Combined Signing Key) per signing-eligible zone. Since both views of `${ID}.nasa` share the same zone name, BIND uses the same key for both views — this is correct per BIND's KASP behavior.
- **D-08:** Key directory follows existing SELinux pattern: `named_conf_t` for key files (consistent with TSIG key file handling in Phase 3).

### DS Record Export Workflow
- **D-09:** DS records are extracted on-target after signing using the lab-spec command: `dig @172.16.1.53 <zone> DNSKEY | dnssec-dsfromkey -f - <zone>`. This runs as an Ansible task on the primary NS after BIND has signed the zones.
- **D-10:** DS records are surfaced to the student via registered Ansible variables (displayed in playbook output). The student manually submits them to the OJ — Ansible does not automate OJ submission.
- **D-11:** DS extraction is included in `verify.yml` as a validation step, confirming that the live DNSKEY matches the expected algorithm and digest type.

### Zones to Sign
- **D-12:** Signing-eligible zones (3 total): `${ID}.nasa` private view, `${ID}.nasa` public view, `${ID}-sub28.{x}.168.192.in-addr.arpa` public view.
- **D-13:** Explicitly unsigned zones: `0.16.172.in-addr.arpa` and `1.16.172.in-addr.arpa` (private view reverse zones). These remain authoritative without DNSSEC per spec allowance (AUTH-10).

### the agent's Discretion
- Exact `dnssec-policy` block placement (dedicated include file vs. inline in `named.options.conf.j2`) — planner can choose based on template structure.
- Key directory path on the primary NS (e.g., `/var/named/keys/` vs. `/etc/named/keys/`) — planner can choose based on BIND9 conventions and SELinux.
- Whether to add a `bind9_dnssec` feature flag in `defaults/main.yml` or always include DNSSEC tasks when `bind9_mode == 'authoritative_primary'` — planner can decide.
- Exact Ansible task structure for key generation (local action vs. shell command vs. custom module) — planner can choose.
- Whether `named.zones.conf.j2` adds `inline-signing yes;` globally for all zones or only for signed zones — planner should add it only for signed zones.
- Verification task details in `verify.yml` (dig commands, assertion checks) — planner can design.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Lab Specification
- `lab/dns.md` — Authoritative HW1-1 spec: DNSSEC signing requirements (algorithm 13, digest 2), DS record generation command, grading rubric (35% weight)

### Existing Codebase
- `ansible/playbooks/roles/bind9/templates/named.zones.conf.j2` — Zone renderer; needs `dnssec-policy` and `inline-signing` directives per zone/view
- `ansible/playbooks/roles/bind9/templates/named.options.conf.j2` — Options block; needs `dnssec-policy` block definition
- `ansible/playbooks/roles/bind9/templates/named.conf.j2` — Main config; may need new include for DNSSEC policy
- `ansible/playbooks/roles/bind9/templates/named.keys.conf.j2` — TSIG key template; DNSSEC keys use separate distribution path (secrets.yml → key-directory)
- `ansible/playbooks/roles/bind9/templates/db.zone.j2` — Zone data template; unsigned source of truth remains unchanged
- `ansible/playbooks/roles/bind9/defaults/main.yml` — Role defaults; needs DNSSEC policy defaults, key directory path
- `ansible/playbooks/roles/bind9/meta/argument_specs.yml` — Argument schema; needs DNSSEC-related variable additions
- `ansible/playbooks/roles/bind9/tasks/config.yml` — Config tasks; needs key directory creation, key file distribution, SELinux context
- `ansible/playbooks/roles/bind9/tasks/verify.yml` — Verification; needs DNSKEY/DNSSEC validation and DS extraction tasks
- `ansible/inventory/host_vars/primary-ns-01/main.yml` — Primary NS host vars; needs DNSSEC policy references and signing-eligible zone markers
- `ansible/inventory/host_vars/primary-ns-01/secrets.example.yml` — Needs DNSSEC key placeholders
- `ansible/playbooks/roles/bind9/library/bind9_zone_state.py` — Zone serial/hash state module; must handle `.signed` sidecar files correctly

### Prior Phase Decisions
- `.planning/STATE.md` — Accumulated context: zone data schema, view rendering, VPN IP derivation, SOA timers, SELinux setype attributes, TSIG key pattern
- `.planning/REQUIREMENTS.md` — AUTH-09, AUTH-10, AUTO-02 requirements
- `.planning/ROADMAP.md` — Phase 4 success criteria and plan outline

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **`named.zones.conf.j2` template**: Already renders per-zone directives (`type`, `file`, `masters`, `allow_transfer`, `also_notify`, `update-policy`). Needs `dnssec-policy` and `inline-signing` additions for signed zones.
- **`named.options.conf.j2` template**: Already configures BIND options including `dnssec-validation yes`. Needs `dnssec-policy` block definition.
- **`named.keys.conf.j2` template**: TSIG key template pattern. DNSSEC keys use a different distribution path (secrets.yml → key-directory, not include file).
- **`config.yml` task**: Already creates `/var/named/dynamic/` with `named_cache_t` SELinux context. Key directory needs similar treatment with `named_conf_t`.
- **`verify.yml` task**: Already has mode-specific dig tests. Needs DNSKEY/DNSSEC validation and DS extraction.
- **`argument_specs.yml`**: Already validates `bind9_views` and `bind9_zones`. Needs DNSSEC-related optional fields.
- **Secret split pattern**: `secrets.yml` (gitignored) + `secrets.example.yml` (tracked, placeholders). DNSSEC key material follows this pattern.
- **Hash-based zone serial pipeline**: `bind9_zone_state` module + `bind9_zone_serial` filter. Must handle `.signed` sidecar files correctly (track unsigned template, not signed output).

### Established Patterns
- **Component role pattern**: One `bind9` role driven by `host_vars`. DNSSEC tasks are conditional on `bind9_mode == 'authoritative_primary'`.
- **Zone data schema**: `bind9_views` (policy) + `bind9_zones` (data). DNSSEC signing is a per-zone property — add `dnssec_policy` field to zone dict.
- **Feature flags**: `bind9_enabled` controls role inclusion. DNSSEC may need its own flag or be implicit based on zone config.
- **SELinux context**: Config paths use `named_conf_t`, dynamic zone dir uses `named_cache_t`. Key files use `named_conf_t`.
- **Logging convention**: `PHASE [<name> : <task>]` naming. New tasks follow this pattern.

### Integration Points
- **`dns.yml` playbook**: Pre-tasks derive VPN identity. DNSSEC key material in `secrets.yml` is consumed by the `bind9` role template rendering.
- **`named.conf.j2`**: May need a new include for DNSSEC policy block (or inline in options).
- **`named.zones.conf.j2`**: Needs `dnssec-policy nasa-lab;` and `inline-signing yes;` directives for signed zones only.
- **`host_vars/primary-ns-01/secrets.yml`**: Needs DNSSEC key material (`.key` and `.private` file contents for each signing-eligible zone).
- **`host_vars/primary-ns-01/secrets.example.yml`**: Needs DNSSEC key placeholders.

</code_context>

<specifics>
## Specific Ideas

- The lab spec (`lab/dns.md`) mandates algorithm 13 (ECDSAP256SHA256) and digest type 2 (SHA-256) for DS records. The `dnssec-policy` block must specify these exactly.
- The lab spec (`lab/dns.md`) provides the DS extraction command: `dig @172.16.1.53 <zone> DNSKEY | dnssec-dsfromkey -f - <zone>`. This should be the verification task.
- The OJ grading rubric allocates 35% to DNSSEC (10% authoritative trust, 25% resolver validation). DS record upload is a manual student step.
- BIND9's KASP engine with `dnssec-policy` uses inline-signing by default, maintaining `.signed` sidecar files. The unsigned zone file (rendered by `db.zone.j2`) remains the source of truth.
- Pre-generated keys with `dnssec-keygen -G` (no timing metadata) prevent KASP from auto-retiring keys, which is critical for a stable lab environment.
- Both views of `${ID}.nasa` share the same zone name, so BIND uses the same CSK for both views — this is correct per BIND's KASP behavior and matches the lab's requirement.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.
</deferred>

---

*Phase: 04-authoritative-dnssec-trust-chain*
*Context gathered: 2026-05-10*