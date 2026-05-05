# Phase 1: Bind9 Role Foundation - Research

**Researched:** 2026-05-05  
**Scope:** Phase 1 only  
**Confidence:** High

## Goal

Create the first usable version of the `bind9` component role so the repository can provision `primary-ns-01`, `secondary-ns-01`, and `dns-01` from one role with inventory-driven behavior. There is no phase `CONTEXT.md`, so Phase 1 planning should treat `ROADMAP.md`, `REQUIREMENTS.md`, `PROJECT.md`, `lab/dns.md`, and existing codebase conventions as the source of truth.

## What the codebase already dictates

- Keep one **component role** named `bind9`; do not create separate primary, secondary, and resolver roles.
- Match existing role structure: `tasks/main.yml` with `START` and `END`, `assert.yml`, `setup.yml`, and phase task files imported from `setup.yml`.
- Use **whole-file templates**, not `lineinfile` or `blockinfile`, so repeated runs stay deterministic.
- Keep secrets in gitignored `host_vars/*/secrets.yml`; tracked files may reference secret variable names but must not copy secret values.
- `bootstrap.yml` already applies `bind9` only to `dmz` and `internal` hosts when `bind9_enabled` is true.
- Existing DNS host vars already declare the static service IPs and expose port 53 through firewalld.

## Recommended implementation shape

### 1. Role file layout

Create the same shape used by the existing component roles:

- `ansible/playbooks/roles/bind9/defaults/main.yml`
- `ansible/playbooks/roles/bind9/meta/argument_specs.yml`
- `ansible/playbooks/roles/bind9/tasks/main.yml`
- `ansible/playbooks/roles/bind9/tasks/assert.yml`
- `ansible/playbooks/roles/bind9/tasks/setup.yml`
- `ansible/playbooks/roles/bind9/tasks/install.yml`
- `ansible/playbooks/roles/bind9/tasks/config.yml`
- `ansible/playbooks/roles/bind9/tasks/service.yml`
- `ansible/playbooks/roles/bind9/tasks/verify.yml`
- `ansible/playbooks/roles/bind9/handlers/main.yml`
- `ansible/playbooks/roles/bind9/templates/named.conf.j2`
- `ansible/playbooks/roles/bind9/templates/named.options.conf.j2`
- `ansible/playbooks/roles/bind9/templates/named.acl.conf.j2`

### 2. Inventory contract for Phase 1

Use inventory data instead of host-specific branching in the role:

- `group_vars/all.yml`: add `lab_id: 14`
- `host_vars/primary-ns-01/main.yml`: add `bind9_mode: authoritative_primary`, `bind9_listen_ipv4: [172.16.1.53]`
- `host_vars/secondary-ns-01/main.yml`: add `bind9_mode: authoritative_secondary`, `bind9_listen_ipv4: [172.16.0.53]`
- `host_vars/dns-01/main.yml`: add `bind9_mode: resolver`, `bind9_listen_ipv4: [172.16.1.153]`

Keep `bind9_enabled: true` in host vars. Do not copy `wireguard_address` into tracked files; consume it from existing inventory host vars at runtime.

### 3. Runtime identity derivation

The repo already stores the VPN address as `wireguard_address` in gitignored host secrets. Phase 1 should wire later templates to inventory-derived values by:

- reading `hostvars[bind9_identity_source_host].wireguard_address` with default `router-01`
- deriving the VPN `/28` network with homework-specific math: `network_base = (octet4 // 16) * 16`
- rebuilding `a.b.c.network_base/28`
- validating the provided `lab_id` against the homework formula `octet3 * 16 + network_base / 16`

This keeps `${ID}` and VPN subnet data out of tracked templates while still making both values available to later zone and view templates.

### 4. Package and service baseline

For Phase 1, install distro packages only:

- `bind`
- `bind-utils`

Use `named` as the systemd service. Render `/etc/named.conf` plus include fragments under `/etc/named/`. Create `/var/named/dynamic` now so later dynamic-update and DNSSEC phases do not need to redesign paths.

### 5. Shared config behavior to establish now

- Authoritative hosts: `recursion no;`
- Resolver host: `recursion yes;`
- Resolver query and recursion ACL: `127.0.0.1`, `172.16.0.0/24`, `172.16.1.0/24`
- Listen only on explicit inventory IPs plus localhost
- `listen-on-v6 { none; };`
- Validate config with `named-checkconf /etc/named.conf` before service enable or reload

Phase 1 does **not** need real zones, transfers, TSIG, or DNSSEC policy yet; it needs the structure that later phases plug into.

## Pitfalls to avoid in Phase 1

1. **Multiple roles for one subsystem** — violates the repo architecture and makes later shared changes expensive.
2. **Editing `/etc/named.conf` piecemeal** — use templates so reruns do not drift.
3. **Hardcoding `14`, `${ID}`, or VPN CIDRs inside templates** — keep those values inventory-derived.
4. **Open recursion on authoritative hosts** — authoritative modes should render `recursion no` immediately.
5. **Skipping validation before service start** — `named` must not restart on invalid config.

## Validation Architecture

### Quick validation

- `ansible-playbook -i ansible/inventory/hosts.example.yml ansible/playbooks/bootstrap.yml --syntax-check`
- `rg -n "bind9_mode|bind9_listen_ipv4|named-checkconf" ansible/playbooks/roles/bind9 ansible/inventory/group_vars/all.yml ansible/inventory/host_vars/primary-ns-01/main.yml ansible/inventory/host_vars/secondary-ns-01/main.yml ansible/inventory/host_vars/dns-01/main.yml`

### Runtime validation after implementation

- `ansible-playbook -i ansible/inventory/hosts.yml ansible/playbooks/bootstrap.yml --limit primary-ns-01,secondary-ns-01,dns-01`
- `ansible -i ansible/inventory/hosts.yml primary-ns-01,secondary-ns-01,dns-01 -m ansible.builtin.command -a "named-checkconf /etc/named.conf"`
- `ansible -i ansible/inventory/hosts.yml primary-ns-01,secondary-ns-01,dns-01 -m ansible.builtin.shell -a "systemctl is-enabled named && systemctl is-active named && ss -ltnu | grep -E "(:53\b)""`
- `ansible -i ansible/inventory/hosts.yml primary-ns-01,secondary-ns-01,dns-01 -m ansible.builtin.shell -a "grep -R "\${ID}" /etc/named.conf /etc/named/*.conf"`

## Recommended planning split

1. **Plan 01** — define defaults, argument specs, role entrypoint, and assert and setup scaffolding.
2. **Plan 02** — implement package install, template rendering, config directories, service management, and handler wiring.
3. **Plan 03** — wire `lab_id` plus host modes plus inventory-derived VPN identity into tracked inventory and runtime verification.

## Sources

- `lab/dns.md`
- `.planning/PROJECT.md`
- `.planning/ROADMAP.md`
- `.planning/REQUIREMENTS.md`
- `.planning/STATE.md`
- `.planning/research/SUMMARY.md`
- `.planning/codebase/ARCHITECTURE.md`
- `.planning/codebase/CONVENTIONS.md`
- `.planning/codebase/CONCERNS.md`
- `ansible/playbooks/bootstrap.yml`
- `ansible/inventory/group_vars/all.yml`
- `ansible/inventory/host_vars/primary-ns-01/main.yml`
- `ansible/inventory/host_vars/secondary-ns-01/main.yml`
- `ansible/inventory/host_vars/dns-01/main.yml`
- `ansible/inventory/host_vars/router-01/secrets.example.yml`
- Context7: `/websites/bind9_readthedocs_io_en_stable`
- Context7: `/ansible/ansible-documentation`
