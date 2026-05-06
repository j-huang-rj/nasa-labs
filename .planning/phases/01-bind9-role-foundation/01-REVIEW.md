---
phase: 01-bind9-role-foundation
reviewed: 2026-05-06T12:00:00Z
depth: standard
files_reviewed: 17
files_reviewed_list:
  - ansible/inventory/group_vars/all.yml
  - ansible/inventory/host_vars/dns-01/main.yml
  - ansible/inventory/host_vars/primary-ns-01/main.yml
  - ansible/inventory/host_vars/secondary-ns-01/main.yml
  - ansible/playbooks/roles/bind9/defaults/main.yml
  - ansible/playbooks/roles/bind9/handlers/main.yml
  - ansible/playbooks/roles/bind9/meta/argument_specs.yml
  - ansible/playbooks/roles/bind9/tasks/assert.yml
  - ansible/playbooks/roles/bind9/tasks/config.yml
  - ansible/playbooks/roles/bind9/tasks/install.yml
  - ansible/playbooks/roles/bind9/tasks/main.yml
  - ansible/playbooks/roles/bind9/tasks/service.yml
  - ansible/playbooks/roles/bind9/tasks/setup.yml
  - ansible/playbooks/roles/bind9/tasks/verify.yml
  - ansible/playbooks/roles/bind9/templates/named.acl.conf.j2
  - ansible/playbooks/roles/bind9/templates/named.conf.j2
  - ansible/playbooks/roles/bind9/templates/named.options.conf.j2
findings:
  critical: 0
  warning: 5
  info: 3
  total: 8
status: issues_found
---

# Phase 01: Code Review Report — bind9 Role Foundation

**Reviewed:** 2026-05-06
**Depth:** standard
**Files Reviewed:** 17
**Status:** issues_found

## Summary

Reviewed the complete bind9 Ansible role (defaults, handlers, argument specs, 6 task files, 3 templates) plus 4 inventory files. The role follows the project's component-role architecture with proper phase markers, SELinux contexts, and a verification pipeline. No hardcoded secrets, no dangerous functions, no debug artifacts found.

Five warnings identified: a handler that can't propagate listen-address changes, an assertion that crashes on undefined input, a silent-failure path in VPN derivation, hardcoded subnets bypassing ACL definitions, and self-referencing defaults in argument specs. Three info items on missing phase markers, redundant validation, and unused computed facts.

## Warnings

### WR-01: Handler only reloads — listen address changes require restart

**File:** `ansible/playbooks/roles/bind9/handlers/main.yml:4`
**Issue:** The handler uses `state: reloaded`, which sends SIGHUP to named. SIGHUP re-reads configuration files but does not rebind listening sockets. If `bind9_listen_ipv4` changes between playbook runs (e.g., migrating from one IP to another), named continues listening on the old address until manually restarted. The handler fires after config template changes, so this is the only mechanism that applies config updates.
**Fix:** Use `state: restarted` to ensure socket rebinding, or add a second handler for restart and trigger it conditionally when listen addresses change:
```yaml
- name: "PHASE [handler : Restart named]"
  ansible.builtin.systemd_service:
    name: "{{ bind9_service_name }}"
    state: restarted
```

### WR-02: `bind9_mode` assertion crashes on undefined instead of failing cleanly

**File:** `ansible/playbooks/roles/bind9/tasks/assert.yml:20`
**Issue:** The assertion `bind9_mode in ['authoritative_primary', 'authoritative_secondary', 'resolver']` evaluates `bind9_mode` directly. If `bind9_mode` is not defined, Jinja2 raises an undefined variable error before the `fail_msg` on line 21-23 is evaluated. The operator sees a raw Jinja2 traceback instead of the helpful failure message. The `fail_msg` already uses `bind9_mode | default("(undefined)")` which shows awareness of this case, but the `that` condition doesn't protect against it.
**Fix:** Add a `is defined` precondition or use a default filter in the `that` clause:
```yaml
that:
  - bind9_mode is defined
  - bind9_mode in ['authoritative_primary', 'authoritative_secondary', 'resolver']
```

### WR-03: Silent failure in VPN identity derivation

**File:** `ansible/playbooks/roles/bind9/tasks/config.yml:3-20`
**Issue:** The VPN derivation block reads `hostvars[bind9_identity_source_host].wireguard_address` with `default('')`. If `router-01` doesn't have `wireguard_address` defined (WireGuard not yet provisioned, or secrets.yml missing), the entire VPN derivation silently produces no result. `bind9_vpn_network_cidr` is never set, and `named.acl.conf.j2` silently omits the `bind9_vpn_clients` ACL. For `secondary-ns-01` — which has `wireguard_enabled: true`, VPN firewall rules on port 53, and `bind9_mode: authoritative_secondary` — this means DNS resolution from VPN clients silently fails with no error during the playbook run.
**Fix:** Add an assertion or warning when running in authoritative mode and the VPN address is empty:
```yaml
- name: "PHASE [config : Warn if VPN address unavailable for authoritative mode]"
  ansible.builtin.debug:
    msg: "WARNING: bind9_identity_source_host '{{ bind9_identity_source_host }}' has no wireguard_address; VPN ACL will be omitted"
  when: _bind9_source_wg_address | length == 0
```

### WR-04: Hardcoded subnets in resolver options bypass ACL definitions

**File:** `ansible/playbooks/roles/bind9/templates/named.options.conf.j2:17-23`
**Issue:** The resolver-mode `allow-query` and `allow-recursion` directives hardcode `172.16.0.0/24` and `172.16.1.0/24` as literal CIDR strings. Meanwhile, `named.acl.conf.j2` defines `bind9_dmz_clients` and `bind9_internal_clients` ACLs with the same CIDRs. This creates maintenance duplication — if subnets are renumbered, both files must be updated independently. The ACL file exists precisely to centralize these definitions.
**Fix:** Reference the ACL names instead of duplicating CIDRs:
```jinja2
    allow-query {
        127.0.0.1;
        bind9_dmz_clients;
        bind9_internal_clients;
    };
    allow-recursion {
        127.0.0.1;
        bind9_dmz_clients;
        bind9_internal_clients;
    };
```
Note: This requires `named.acl.conf` to be included before `named.options.conf` in `named.conf.j2`, or moving the ACL include above the options include.

### WR-05: Self-referencing circular defaults in argument_specs

**File:** `ansible/playbooks/roles/bind9/meta/argument_specs.yml:24,28,32,36,40,44,48,52,56`
**Issue:** Nine options define `default: "{{ variable_name }}"` where `variable_name` is the same option being documented (e.g., `bind9_packages` has `default: "{{ bind9_packages }}"`). Ansible resolves these against `defaults/main.yml` at runtime, so it works — but the circular reference is fragile documentation. If a variable is removed from `defaults/main.yml` but not from `argument_specs.yml`, the self-reference produces an undefined variable in documentation output. The pattern also obscures what the actual default value is when reading the specs.
**Fix:** Use literal values matching `defaults/main.yml`:
```yaml
bind9_packages:
  type: list
  elements: str
  required: false
  default:
    - bind
    - bind-utils
```

## Info

### IN-01: Missing PHASE START/END markers in config.yml

**File:** `ansible/playbooks/roles/bind9/tasks/config.yml`
**Issue:** Per AGENTS.md logging convention, phase boundaries in task files must use `PHASE [<phase_name> : START]` and `PHASE [<phase_name> : END]` debug markers. Every other bind9 task file (`assert.yml`, `setup.yml`, `verify.yml`) follows this convention. `config.yml` is the only outlier — it jumps straight into functional tasks.
**Fix:** Add markers:
```yaml
- name: "PHASE [config : START]"
  become: false
  ansible.builtin.debug:
    msg: "Configure bind9"

# ... existing tasks ...

- name: "PHASE [config : END]"
  become: false
  ansible.builtin.debug:
    msg: "Completed config phase"
```

### IN-02: Redundant `named-checkconf` in verify.yml

**File:** `ansible/playbooks/roles/bind9/tasks/verify.yml:8-12`
**Issue:** `named-checkconf` runs in both `service.yml:3-8` (before service start, gated by `bind9_config_validate_enabled`) and `verify.yml:8-12` (after service start, always runs). The config file hasn't changed between these two points, making the verify.yml check redundant. The verify.yml check also lacks the `bind9_config_validate_enabled` toggle, creating an inconsistency.
**Fix:** Either remove the duplicate from `verify.yml` (service.yml already validates before start), or keep it as a deliberate post-startup double-check but add `when: bind9_config_validate_enabled | bool` for consistency.

### IN-03: `bind9_derived_lab_id` and `bind9_vpn_network_base` computed but unused

**File:** `ansible/playbooks/roles/bind9/tasks/config.yml:16-18`
**Issue:** These facts are set via `set_fact` but never consumed by any template or task in the bind9 role. A codebase-wide grep confirms no other role reads them either. Per planning docs (260506-h79), they were intentionally retained for potential future use. Noting for awareness — if no future phase consumes them, they should be removed as dead code.
**Fix:** No immediate action required. Track consumption in future phases; remove if unused after phase 01 is complete.

---

_Reviewed: 2026-05-06T12:00:00Z_
_Reviewer: the agent (gsd-code-reviewer)_
_Depth: standard_
