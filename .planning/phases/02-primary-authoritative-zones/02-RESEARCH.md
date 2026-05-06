# Phase 2: Primary Authoritative Zones - Research

**Researched:** 2026-05-06  
**Scope:** Phase 2 only  
**Confidence:** High

## Goal

Deliver the primary authoritative DNS behavior for the lab-owned forward and reverse zones without reintroducing the stale inventory-wide `lab_id` coupling that was removed after Phase 1. The phase must render split views, zone stanzas, and per-view zone data from Ansible-managed inputs, then prove the primary returns the required answers for both internal and external query paths.

## What the current codebase already dictates

- Keep using the single `bind9` component role; do not fork separate primary-only roles.
- Preserve the existing role structure and logging conventions: `tasks/main.yml` -> `assert.yml` -> `setup.yml` -> phase files with `PHASE [...]` task names.
- Keep whole-file templating. Do not switch to `lineinfile` or `blockinfile` for BIND config fragments or zone files.
- Keep SELinux path ownership split from prior work: config under `/etc/named` with `named_conf_t`, zone data under `/var/named` with `named_cache_t`.
- Do **not** reintroduce tracked `lab_id: 14` inventory data. The live repo removed that coupling in quick task `260506-h79`; Phase 2 should continue from `bind9_derived_lab_id` and VPN-derived facts computed at runtime.
- The primary already listens on `127.0.0.1` and `172.16.1.53`; this makes loopback-vs-service-IP validation possible without adding a synthetic external host to the repo.

## Locked decisions that planning must implement

- **D2-1**: Keep a hybrid contract with `bind9_views` for view policy and `bind9_zones` for zone data.
- **D2-2**: Render `named.zones.conf` as an include from `named.conf`, and render separate zone data files under `/var/named/`.
- **D2-3**: Extend the existing arithmetic in `tasks/config.yml`; do not add new dependencies or move the logic into templates.
- **D2-4**: Use SOA serial `YYYYMMDD01` and fixed timers `refresh=3600`, `retry=1800`, `expire=604800`, `minimum=86400`.

## Key external findings

### 1. BIND views are independent copies of the same zone

ISC documents that the same zone loaded in two views is independent in memory, and their worked examples store each view's zone file separately (`trusted/db.*` vs `guest/db.*`). That means this phase should model the forward zone twice (private/public), keep reverse zones duplicated per view, and give each `bind9_zones` entry a distinct `file` path such as `private/db.<zone>` or `public/db.<zone>`.

**Planning consequence:** `bind9_zones` must be per-view data, not one shared zone body reused by both views.

### 2. View matching is first-match, so the broad public view must be last

BIND view clauses are processed in declaration order; once a view matches, view selection stops. Because the public view is effectively `any`, the private view must be rendered first and the public view must be rendered last.

**Planning consequence:** make `bind9_views[].order` authoritative, assert `private.order < public.order`, and sort the template output by that order instead of trusting YAML insertion order.

### 3. `named-checkconf` is not enough once the phase introduces real zones

`named-checkzone` validates the syntax and integrity of a zone file before it is loaded. `named-checkconf` only validates the configuration graph. Once Phase 2 adds real zone files, the service start gate must validate both the config and each rendered zone file.

**Planning consequence:** update `tasks/service.yml` to loop over `bind9_zones` and run `named-checkzone <zone> <file>` before `named` is enabled/restarted.

### 4. RFC 2317 requires both a delegated child zone and carrier CNAMEs

ISC's RFC 2317 guidance shows that classless reverse delegation works by delegating a child label such as `0-63.2.0.192.in-addr.arpa`, then placing CNAMEs in the parent reverse zone that redirect `dig -x` lookups to the child zone. For this lab's `/28`, the natural child name is `${ID}-sub28.<x>.168.192.in-addr.arpa` and the parent carrier zone is `<x>.168.192.in-addr.arpa`.

**Planning consequence:** Phase 2 should model the RFC 2317 requirement as two related per-view zones:
- a carrier zone for `<x>.168.192.in-addr.arpa` containing CNAMEs for the router/client/ns VPN addresses
- a delegated child zone for `${ID}-sub28.<x>.168.192.in-addr.arpa` containing the PTR records

### 5. Public/private verification can be done from the primary itself

Given the current repo state, `bind9_dmz_clients` and `bind9_internal_clients` cover `172.16.0.0/24` and `172.16.1.0/24`, while loopback is outside those ACLs unless explicitly added. This means:
- `dig -b 172.16.1.53 @172.16.1.53 ...` can exercise the **private** view
- `dig -b 127.0.0.1 @127.0.0.1 ...` can exercise the **public** view

**Planning consequence:** keep localhost out of the private `match-clients` list, then use loopback-vs-service-IP queries in `verify.yml` so execution can validate both views without depending on a separate VPN client host.

## Recommended implementation shape

### 1. Extend the current runtime fact block instead of replacing it

Keep the existing VPN-derived facts in `tasks/config.yml` and add these concrete outputs there:

- `bind9_vpn_router_ip`
- `bind9_vpn_client_ip`
- `bind9_vpn_ns_ip`
- `bind9_forward_zone_name`
- `bind9_vpn_parent_reverse_zone_name`
- `bind9_vpn_child_reverse_zone_name`
- `bind9_primary_mname`
- `bind9_soa_serial`

This follows D2-3 and keeps all homework-specific arithmetic in one place.

### 2. Split Phase 2 into three sequential plans

1. **Plan 02-01** — establish `bind9_views` / `bind9_zones` contracts, private/public ordering, and `named.zones.conf` scaffolding.
2. **Plan 02-02** — add forward-zone data plus generic zone-file rendering and `named-checkzone` pre-start validation.
3. **Plan 02-03** — add reverse zones (including RFC 2317 carrier + child zones) and extend `verify.yml` with the dig matrix for both views.

This matches the roadmap, keeps each plan under the context budget, and respects the shared ownership of `host_vars/primary-ns-01/main.yml`.

### 3. Treat SOA MNAME as a derived role fact, not per-zone inventory data

D2-1 names `soa` timer fields but does not allocate a dedicated inventory key for MNAME. The cleanest fit is to derive a single role fact:

- `bind9_primary_mname = private-ns.{{ bind9_forward_zone_name }}.`

Then render every zone's SOA with that MNAME while leaving `bind9_zones[].soa` focused on the timer/admin fields required by D2-1 and D2-4.

### 4. Use one generic text-zone template for forward and reverse zones

A single `db.zone.j2` template can render:
- `$TTL`
- `SOA`
- `NS` records
- arbitrary `records` rows with duplicate owners allowed

That keeps reverse-zone work in Plan 02-03 limited to data and verification, rather than reworking rendering logic again.

## Pitfalls to avoid

1. **Reintroducing `lab_id` inventory state** — Phase 2 should continue from runtime-derived identity facts only.
2. **Putting public `any` before private clients** — that silently routes all queries to the public view.
3. **Sharing one zone file path between both views** — ISC explicitly treats view copies as independent; per-view files are safer and easier to debug.
4. **Validating only `named.conf`** — real zone files can still be malformed while `named-checkconf` passes.
5. **Implementing only the RFC 2317 child zone** — `dig -x` needs the parent carrier CNAMEs too.
6. **Adding localhost to the private ACL** — that removes the cheapest way to prove the public view during execution.

## Validation Architecture

### Quick validation

- `ansible-playbook -i ansible/inventory/hosts.example.yml ansible/playbooks/bootstrap.yml --syntax-check`
- `rg -n "bind9_views|bind9_zones|named.zones.conf|named-checkzone|sub28" ansible/playbooks/roles/bind9 ansible/inventory/host_vars/primary-ns-01/main.yml`

### Runtime validation after implementation

- `ansible-playbook -i ansible/inventory/hosts.yml ansible/playbooks/bootstrap.yml --limit primary-ns-01`
- `ansible -i ansible/inventory/hosts.yml primary-ns-01 -m ansible.builtin.command -a "named-checkconf /etc/named.conf"`
- `ansible -i ansible/inventory/hosts.yml primary-ns-01 -m ansible.builtin.shell -a "named-checkzone $(python3 - <<'PY2'
print('placeholder')
PY2
)"`
- `ansible -i ansible/inventory/hosts.yml primary-ns-01 -m ansible.builtin.command -a "dig -b 172.16.1.53 @172.16.1.53 private-ns.<derived-zone> A"`
- `ansible -i ansible/inventory/hosts.yml primary-ns-01 -m ansible.builtin.command -a "dig -b 127.0.0.1 @127.0.0.1 ns.<derived-zone> A"`
- `ansible -i ansible/inventory/hosts.yml primary-ns-01 -m ansible.builtin.command -a "dig -b 127.0.0.1 @127.0.0.1 -x <vpn-ns-ip>"`

## Sources

- `lab/dns.md`
- `.planning/PROJECT.md`
- `.planning/ROADMAP.md`
- `.planning/REQUIREMENTS.md`
- `.planning/STATE.md`
- `.planning/phases/02-primary-authoritative-zones/CONTEXT.md`
- `.planning/phases/01-bind9-role-foundation/01-01-SUMMARY.md`
- `.planning/phases/01-bind9-role-foundation/01-02-SUMMARY.md`
- `.planning/phases/01-bind9-role-foundation/01-03-SUMMARY.md`
- `.planning/quick/260506-h79-bind9-inventory-cleanup-derive-listen-ip/260506-h79-SUMMARY.md`
- `ansible/playbooks/roles/bind9/defaults/main.yml`
- `ansible/playbooks/roles/bind9/meta/argument_specs.yml`
- `ansible/playbooks/roles/bind9/tasks/assert.yml`
- `ansible/playbooks/roles/bind9/tasks/config.yml`
- `ansible/playbooks/roles/bind9/tasks/service.yml`
- `ansible/playbooks/roles/bind9/tasks/verify.yml`
- `ansible/playbooks/roles/bind9/templates/named.conf.j2`
- `ansible/playbooks/roles/bind9/templates/named.options.conf.j2`
- `ansible/playbooks/roles/bind9/templates/named.acl.conf.j2`
- `ansible/inventory/host_vars/primary-ns-01/main.yml`
- `https://kb.isc.org/docs/aa-00851` — ISC: Understanding views in BIND 9
- `https://kb.isc.org/docs/aa-01589` — ISC: Classless in-addr.arpa subnet delegation
- `https://bind9.readthedocs.io/en/stable/reference.html` — BIND 9 configuration reference (first-match ACL behavior)
- `https://manpages.debian.org/testing/bind9utils/named-compilezone.8.en.html` — `named-checkzone` / `named-compilezone` behavior
