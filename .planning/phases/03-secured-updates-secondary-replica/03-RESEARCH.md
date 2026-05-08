# Phase 3: Secured Updates & Secondary Replica - Research

**Researched:** 2026-05-09  
**Scope:** Phase 3 only  
**Confidence:** High

## Goal

Deliver the secured-authoritative part of the lab: one shared TSIG secret gates the allowed dynamic updates on the primary, the primary replicates its live zone state to a read-only secondary fast enough for the grader, and the control node can export the same secret material for OJ submission without committing any secrets.

## What the current codebase already dictates

- Keep using the single `bind9` component role. Do not fork a secondary-only role or add host-branching templates.
- Preserve the existing role flow and naming conventions: `tasks/main.yml` -> `assert.yml` -> `setup.yml` -> `install.yml` / `config.yml` / `service.yml` / `verify.yml`, with `PHASE [...]` task names.
- Keep whole-file templating. Add a separate `named.keys.conf.j2` include instead of editing rendered config in place.
- Preserve the secret split pattern: tracked `secrets.example.yml`, gitignored `secrets.yml`, no live secret values in tracked files.
- Reuse the existing BIND include structure in `named.conf.j2`; new key material should be defined before any zone stanza consumes it.
- Reuse the existing `bind9_views` + `bind9_zones` data model from Phase 2. Phase 3 should extend zone entries with replication/update fields instead of inventing a parallel schema.
- The repo already creates `/var/named/dynamic` with `named_cache_t` and `/var/named/slaves` for secondaries. Phase 3 should build on those writable-path conventions rather than redesigning storage.
- `ansible/inventory/host_vars/secondary-ns-01/main.yml` is still only a mode/listen stub, so full view mirroring belongs in this phase.
- `ansible/inventory/host_vars/primary-ns-01/secrets.example.yml` does not exist yet, even though the current phase context expects it. Planning should create it.
- The live `primary-ns-01/main.yml` on disk is the source of truth for which zones the secondary must mirror. Do not plan against older summaries when they disagree with the file currently in the repo.

## Locked decisions that planning must implement

- **D-01**: One shared TSIG key for the whole phase.
- **D-02**: Generate it with `tsig-keygen` outside Ansible, store it in gitignored `secrets.yml` on both authoritative hosts.
- **D-03**: Render key material through a dedicated `named.keys.conf.j2` include.
- **D-04**: Export the key name, algorithm, and secret for OJ submission from the controller-side secret source.
- **D-05**: Define `bind9_dynamic_hosts: ["dynamic1", "dynamic2", "dynamic3", "dynamic4"]` in `host_vars/primary-ns-01/main.yml`.
- **D-06**: Use `update-policy` `name` grants for the forward A records and `zonesub` grants for allowed PTR zones.
- **D-07**: Apply forward-zone update policy only to the private view copy of `${ID}.nasa`.
- **D-08**: Apply PTR update policy only to the private `0.16.172.in-addr.arpa` and `1.16.172.in-addr.arpa` zones.
- **D-09**: Accept that granted name/type pairs allow create, modify, and delete.
- **D-10**: Use `allow-transfer { 172.16.0.53; };` on the primary, not a separate transfer key.
- **D-11**: Emit `also-notify { 172.16.0.53; };` from the primary for the replicated zones.
- **D-12**: The secondary must not define `allow-update` or `allow-transfer`.
- **D-13**: Mirror the primary explicitly in `host_vars/secondary-ns-01/main.yml` with `type: slave` and `masters: [172.16.1.53]`.
- **D-14**: Keep slave files under `/var/named/slaves/`.
- **D-15**: The secondary reuses the same ACL names and view names as the primary.

## Key external findings

### 1. `update-policy` is the correct control surface, and it cannot be paired with `allow-update`

Current ISC BIND 9 docs are explicit: `update-policy` is only meaningful on primary/master zones, and a zone must not specify both `update-policy` and `allow-update`.

**Planning consequence:** Phase 3 should render only `update-policy` on the primary's writable private zones and should never add `allow-update` anywhere.

### 2. Zone-level `also-notify` is the best fit for this repo

ISC documents `also-notify` at both global and zone scope, with zone scope overriding global behavior. Because this repo already renders authoritative zones from `named.zones.conf.j2`, zone-local NOTIFY targets are the least ambiguous way to keep split-view replication attached to the same data entries that define the zone.

**Planning consequence:** render `also-notify` per master zone in `named.zones.conf.j2`, not globally in `named.options.conf.j2`.

### 3. Repeated zone names across views are independent zone instances

BIND treats the same zone name in multiple views as separate instances. That means the secondary cannot safely reuse a single slave file path for private/public copies of the same zone name.

**Planning consequence:** give the secondary explicit per-view slave file paths such as `slaves/private/db.<zone>` and `slaves/public/db.<zone>` even when the zone name repeats.

### 4. NOTIFY + full transfer is acceptable; IXFR is optional

The lab spec requires convergence within 10 seconds but does not require IXFR specifically. Current BIND docs and the assignment both allow the implementation to rely on NOTIFY-triggered AXFR as long as the end-to-end refresh fits the timing window.

**Planning consequence:** prioritize deterministic NOTIFY + transfer behavior and a timed propagation check; do not spend scope on IXFR-only optimizations.

### 5. Writable dynamic zone state must use the repo's writable SELinux pattern

Dynamic updates create journal activity and require named-writable zone storage. The repo already distinguishes config (`named_conf_t`) from writable cache/dynamic paths (`named_cache_t`).

**Planning consequence:** keep public static zone files read-only, but move the private-view writable zone storage onto a `named_cache_t` path/label so dynamic updates and journals survive reloads under SELinux enforcing mode.

### 6. The exact OJ uploader delimiter is not specified anywhere in the source artifacts

The assignment and current context clearly require the three canonical values (`name`, `algorithm`, `secret`), but no repo file defines the uploader's exact serialization.

**Planning consequence:** the authoritative contract is the three values themselves. Export them from the controller-local secret source into a plain-text artifact that is easy to transform if the local OJ helper expects a specific delimiter.

## Recommended implementation shape

### 1. Plan 03-01 — establish one tracked TSIG contract plus one local secret artifact

Use the exact shared key identity `lab_ddns_shared` with algorithm `hmac-sha256`. Add tracked placeholders in both authoritative hosts' `secrets.example.yml`, render `/etc/named/named.keys.conf`, and create a controller-local export artifact under `.opencode/artifacts/phase-03-tsig-upload.txt` so nothing secret enters git.

### 2. Plan 03-02 — make the primary safely writable and tightly scoped

Do **not** pre-create `dynamic1-4` A records in static zone files. Instead, add `bind9_dynamic_hosts`, zone-local transfer/notify directives, and template logic that emits exact `update-policy` grants only for the private forward zone and private reverse zones. Make the private authoritative zone storage writable by named with the existing SELinux-safe pattern.

### 3. Plan 03-03 — mirror the live primary onto the secondary and prove convergence

Populate `secondary-ns-01/main.yml` with the same views and the same zone names currently present on the primary, but flip every zone to `type: slave`, give each a per-view slave file path under `/var/named/slaves`, and extend verification so a signed update accepted by the primary becomes visible on the secondary within 10 seconds while direct updates and onward transfers stay refused.

## Pitfalls to avoid

1. **Mixing `allow-update` with `update-policy`** — BIND rejects this configuration and it weakens the required restriction model.
2. **Rendering one slave file path for both views of the same zone** — the private/public copies can overwrite or mask each other.
3. **Leaving writable private zones on read-only SELinux labels** — updates may appear to work until journaling or reloads fail.
4. **Testing only happy-path signed updates** — the grader also cares that unsigned and out-of-policy changes are rejected.
5. **Relying on SOA refresh timing instead of immediate NOTIFY** — eventual consistency is not enough for the lab's timing goal.
6. **Hand-copying TSIG values between hosts** — shared-key drift across `nsupdate`, primary config, and secondary config is the easiest way to create hard-to-debug failures.

## Validation Architecture

### Quick validation

- `ansible-playbook --syntax-check -i ansible/inventory/hosts.yml ansible/playbooks/dns.yml`
- `rg -n "bind9_tsig_key|named.keys.conf|bind9_dynamic_hosts|update-policy|allow-transfer|also-notify|type: slave|masters:" ansible/playbooks/roles/bind9 ansible/inventory/host_vars/primary-ns-01 ansible/inventory/host_vars/secondary-ns-01`

### Runtime validation after implementation

- `ansible-playbook -i ansible/inventory/hosts.yml ansible/playbooks/dns.yml --limit primary-ns-01,secondary-ns-01`
- `ansible -i ansible/inventory/hosts.yml primary-ns-01 -m ansible.builtin.command -a "named-checkconf /etc/named.conf"`
- `ansible -i ansible/inventory/hosts.yml primary-ns-01 -m ansible.builtin.shell -a "nsupdate -k /etc/named/named.keys.conf ..."`
- `ansible -i ansible/inventory/hosts.yml primary-ns-01 -m ansible.builtin.command -a "dig @172.16.1.53 $(python3 - <<'PY2'
print('placeholder')
PY2
) AXFR"`
- `ansible -i ansible/inventory/hosts.yml secondary-ns-01 -m ansible.builtin.command -a "dig @172.16.0.53 dynamic2.<derived-zone> A +short"`
- `ansible -i ansible/inventory/hosts.yml secondary-ns-01 -m ansible.builtin.command -a "dig @172.16.0.53 <derived-zone> AXFR"`
- `test -f .opencode/artifacts/phase-03-tsig-upload.txt`

## Sources

- `lab/dns.md`
- `.planning/PROJECT.md`
- `.planning/ROADMAP.md`
- `.planning/REQUIREMENTS.md`
- `.planning/STATE.md`
- `.planning/research/SUMMARY.md`
- `.planning/phases/03-secured-updates-secondary-replica/03-CONTEXT.md`
- `.planning/phases/01-bind9-role-foundation/01-03-SUMMARY.md`
- `.planning/phases/02-primary-authoritative-zones/02-02-SUMMARY.md`
- `.planning/phases/02-primary-authoritative-zones/02-03-SUMMARY.md`
- `ansible/playbooks/dns.yml`
- `ansible/playbooks/roles/bind9/defaults/main.yml`
- `ansible/playbooks/roles/bind9/meta/argument_specs.yml`
- `ansible/playbooks/roles/bind9/tasks/assert.yml`
- `ansible/playbooks/roles/bind9/tasks/config.yml`
- `ansible/playbooks/roles/bind9/tasks/service.yml`
- `ansible/playbooks/roles/bind9/tasks/verify.yml`
- `ansible/playbooks/roles/bind9/templates/named.conf.j2`
- `ansible/playbooks/roles/bind9/templates/named.zones.conf.j2`
- `ansible/inventory/host_vars/primary-ns-01/main.yml`
- `ansible/inventory/host_vars/secondary-ns-01/main.yml`
- Context7: `/websites/bind9_readthedocs_io_en_stable`
