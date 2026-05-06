# Quick Task 260506-h79: bind9 inventory cleanup - Research

**Researched:** 2026-05-06
**Domain:** Ansible role metadata, inventory cleanup, and package ownership
**Confidence:** MEDIUM

<user_constraints>

## User Constraints (from CONTEXT.md)

### Task Boundary

Four cleanup items for the bind9 role and inventory: [VERIFIED: file read]
1. Keep `bind9_listen_ipv4` explicit in host_vars (do NOT auto-derive from `network_interfaces[].ip4`) [VERIFIED: file read]
2. Remove `lab_id: 14` from `group_vars/all.yml` and remove the assertion in `config.yml` that checks `lab_id == bind9_derived_lab_id` [VERIFIED: file read]
3. Remove `bind-utils` from `base/tasks/install.yml` since it's already in `bind9/defaults/main.yml` under `bind9_packages` [VERIFIED: file read]
4. Use Jinja2 references in `argument_specs.yml` for non-mandatory field defaults (e.g., `default: "{{ bind9_packages }}"`) instead of hardcoding values [VERIFIED: file read]

### Implementation Decisions

### bind9_listen_ipv4 derivation
- Keep `bind9_listen_ipv4` explicit in host_vars — do NOT auto-derive from `network_interfaces[].ip4`. Explicit control over which interfaces BIND listens on. [VERIFIED: file read]

### lab_id assertion strategy
- Remove `lab_id: 14` from `group_vars/all.yml` entirely [VERIFIED: file read]
- Remove the assertion task in `config.yml` that checks `lab_id == bind9_derived_lab_id` [VERIFIED: file read]
- The derived `bind9_derived_lab_id` remains the single source of truth for VPN identity [VERIFIED: file read]

### argument_specs default style
- Use Jinja2 references (e.g., `default: "{{ bind9_packages }}"`) for non-mandatory fields in `argument_specs.yml` to stay DRY with `defaults/main.yml` [VERIFIED: file read]

### the agent's Discretion
- Item 3 (removing bind-utils from base role) is straightforward — no ambiguity [VERIFIED: file read]

### Deferred Ideas
- No `Deferred Ideas` section is present in `260506-h79-CONTEXT.md`. [VERIFIED: file read]

</user_constraints>

## Summary

The live Ansible code impact is narrow: `lab_id` is only referenced in `ansible/inventory/group_vars/all.yml` and the soon-to-be-removed assertion inside `ansible/playbooks/roles/bind9/tasks/config.yml`; `bind-utils` is only named in `ansible/playbooks/roles/base/tasks/install.yml` and `ansible/playbooks/roles/bind9/defaults/main.yml`; and `bind9_derived_lab_id` has no current live consumer outside that assertion. [VERIFIED: codebase grep]

On the docs question, the official Ansible documentation I checked presents `meta/argument_specs.yml` defaults inline inside the argument spec and documents `roles/<role>/defaults/main.yml` separately as the place for role defaults. The docs snippets do not demonstrate `argument_specs.yml` importing defaults from `defaults/main.yml`; however, GitHub role examples show templated defaults in `argument_specs.yml`, so Jinja references are ecosystem-common even if that pattern is not the one shown in the official docs. [CITED: https://github.com/ansible/ansible-documentation/blob/devel/docs/docsite/rst/playbook_guide/playbooks_reuse_roles.rst] [CITED: https://github.com/ansible/ansible-documentation/blob/devel/docs/docsite/rst/playbook_guide/playbooks_variables.rst] [VERIFIED: GitHub code search]

**Primary recommendation:** Remove `lab_id` from `group_vars/all.yml`, delete only the `lab_id` assertion block, keep the VPN derivation block because `bind9_vpn_network_cidr` still feeds `named.acl.conf.j2`, remove `bind-utils` from the base role, and treat Jinja defaults in `argument_specs.yml` as a DRY project convention rather than an explicitly documented Ansible best practice. [VERIFIED: codebase grep] [CITED: https://github.com/ansible/ansible-documentation/blob/devel/docs/docsite/rst/playbook_guide/playbooks_reuse_roles.rst] [CITED: https://github.com/ansible/ansible-documentation/blob/devel/docs/docsite/rst/playbook_guide/playbooks_variables.rst]

## Project Constraints (from AGENTS.md)

- Use component roles (`base`, `docker`, `routing`, `network`, `firewall`, `wireguard`, `bind9`), not system roles. [CITED: /Users/j.huang.rj/dev/nasa-labs/AGENTS.md]
- Keep inventory grouped by topology (`router`, `dmz`, `private`) and keep variable names generic and host-agnostic. [CITED: /Users/j.huang.rj/dev/nasa-labs/AGENTS.md]
- Run `ansible-lint` on playbooks and roles. [CITED: /Users/j.huang.rj/dev/nasa-labs/AGENTS.md]
- Preserve role/task naming conventions: role boundaries use `START`/`END`; phase tasks use `PHASE [<phase_name> : ...]`. [CITED: /Users/j.huang.rj/dev/nasa-labs/AGENTS.md]
- Do not conflate manual interface naming (`enp0s*`) with automation-managed interface naming (`eth*`). [CITED: /Users/j.huang.rj/dev/nasa-labs/AGENTS.md]

## Focused Findings

### 1) `argument_specs.yml` default style

- Official Ansible role-argument-validation docs show `default:` values written inline in `meta/argument_specs.yml` examples. [CITED: https://github.com/ansible/ansible-documentation/blob/devel/docs/docsite/rst/playbook_guide/playbooks_reuse_roles.rst]
- Official Ansible variable docs describe `roles/<role>/defaults/main.yml` as the place where role defaults are defined when no higher-precedence value is supplied. [CITED: https://github.com/ansible/ansible-documentation/blob/devel/docs/docsite/rst/playbook_guide/playbooks_variables.rst]
- In the official docs snippets reviewed here, `argument_specs.yml` and `defaults/main.yml` are shown as separate mechanisms; the docs do not show a DRY cross-reference pattern between them. [CITED: https://github.com/ansible/ansible-documentation/blob/devel/docs/docsite/rst/playbook_guide/playbooks_reuse_roles.rst] [CITED: https://github.com/ansible/ansible-documentation/blob/devel/docs/docsite/rst/playbook_guide/playbooks_variables.rst]
- GitHub examples from `ansible-middleware/keycloak`, `lablabs/ansible-role-rke2`, and `sap-linuxlab/community.sap_install` use Jinja expressions inside `meta/argument_specs.yml` defaults, which shows that templated defaults are a real ecosystem pattern. [CITED: https://github.com/ansible-middleware/keycloak/blob/main/roles/keycloak_quarkus/meta/argument_specs.yml] [CITED: https://github.com/lablabs/ansible-role-rke2/blob/main/meta/argument_specs.yml] [CITED: https://github.com/sap-linuxlab/community.sap_install/blob/main/roles/sap_hana_preconfigure/meta/argument_specs.yml]
- Recommendation: follow the locked decision to use Jinja references for non-mandatory defaults, but describe that as a repo DRY choice, not as something the official docs explicitly prescribe. [CITED: https://github.com/ansible/ansible-documentation/blob/devel/docs/docsite/rst/playbook_guide/playbooks_reuse_roles.rst] [CITED: https://github.com/ansible/ansible-documentation/blob/devel/docs/docsite/rst/playbook_guide/playbooks_variables.rst] [CITED: https://github.com/ansible-middleware/keycloak/blob/main/roles/keycloak_quarkus/meta/argument_specs.yml]

### 2) Other `lab_id` references

- In live Ansible code under `ansible/`, `lab_id` appears only in `ansible/inventory/group_vars/all.yml` and `ansible/playbooks/roles/bind9/tasks/config.yml`. [VERIFIED: codebase grep]
- Additional `lab_id` references exist in `.planning/ROADMAP.md`, Phase 01 planning artifacts, and `.git/logs/...`; those are documentation/history references, not execution paths. [VERIFIED: codebase grep]
- No `lab_id` reference was found in `ansible/playbooks/roles/bind9/templates/`, other role task files, or inventory host vars. [VERIFIED: codebase grep]

### 3) `bind-utils` usage elsewhere

- The live package name `bind-utils` appears only in `ansible/playbooks/roles/base/tasks/install.yml` and `ansible/playbooks/roles/bind9/defaults/main.yml`. [VERIFIED: codebase grep]
- `ansible/playbooks/roles/bind9/tasks/install.yml` installs `{{ bind9_packages }}`, so hosts that run the `bind9` role still receive `bind-utils` after it is removed from the base role. [VERIFIED: file read]
- I found no Ansible task in `ansible/` invoking `dig`, `nsupdate`, `delv`, `nslookup`, `named-checkzone`, or `named-compilezone`. [VERIFIED: codebase grep]
- Repo convention note: among current role metadata files, `bind9/meta/argument_specs.yml` is the only `argument_specs.yml` already using a Jinja default; the other roles use literal defaults or omit defaults entirely. [VERIFIED: codebase grep]

### 4) Gotchas when removing the `lab_id` assertion

- `bind9_derived_lab_id` is defined in `ansible/playbooks/roles/bind9/tasks/config.yml` and its only current live consumer is the assertion block slated for removal. [VERIFIED: codebase grep]
- `bind9_vpn_network_cidr` must remain, because `ansible/playbooks/roles/bind9/templates/named.acl.conf.j2` conditionally renders `acl "bind9_vpn_clients" { {{ bind9_vpn_network_cidr }}; };`. [VERIFIED: codebase grep]
- `bind9_vpn_network_base` is also currently write-only in live code after computation; no template or task outside `config.yml` reads it. [VERIFIED: codebase grep]
- Practical implication: removing only the assertion is safe for current runtime behavior, but it leaves `bind9_derived_lab_id` and `bind9_vpn_network_base` as intentionally retained dead facts unless a later change consumes them. [VERIFIED: codebase grep]

## Common Pitfalls

- Do not remove the whole VPN derivation block just because `lab_id` is going away; `bind9_vpn_network_cidr` is still consumed by `named.acl.conf.j2`. [VERIFIED: codebase grep]
- Do not overclaim the docs position on Jinja defaults in `argument_specs.yml`; the official docs show inline literal defaults, while templated defaults are supported by ecosystem practice rather than clearly promoted in the docs I reviewed. [CITED: https://github.com/ansible/ansible-documentation/blob/devel/docs/docsite/rst/playbook_guide/playbooks_reuse_roles.rst] [CITED: https://github.com/ansible-middleware/keycloak/blob/main/roles/keycloak_quarkus/meta/argument_specs.yml]

## Open Questions

1. **Should `bind9_derived_lab_id` and `bind9_vpn_network_base` stay after the assertion is removed?** [VERIFIED: codebase grep]
   - What we know: neither fact has a current live consumer after the assertion is deleted, but `bind9_vpn_network_cidr` still does. [VERIFIED: codebase grep]
   - What's unclear: whether the team wants to preserve those facts for future bind9 phases or remove them as dead state in a later cleanup. [VERIFIED: codebase grep]
   - Recommendation: honor the locked decision for this quick task and keep `bind9_derived_lab_id`, but call out in the implementation notes that it is presently future-facing rather than consumed. [VERIFIED: file read] [VERIFIED: codebase grep]

## Assumptions Log

All claims in this quick-task research were verified in the codebase or cited from official/community sources; no additional user confirmation is required to execute the requested cleanup. [VERIFIED: file read] [VERIFIED: codebase grep] [CITED: https://github.com/ansible/ansible-documentation/blob/devel/docs/docsite/rst/playbook_guide/playbooks_reuse_roles.rst]

## Sources

### Primary

- `ansible/playbooks/roles/bind9/defaults/main.yml` — current bind9 package and path defaults. [VERIFIED: file read]
- `ansible/playbooks/roles/bind9/meta/argument_specs.yml` — current bind9 argument spec defaults. [VERIFIED: file read]
- `ansible/playbooks/roles/bind9/tasks/config.yml` — current VPN derivation and `lab_id` assertion logic. [VERIFIED: file read]
- `ansible/playbooks/roles/bind9/tasks/install.yml` — current bind9 package installation task. [VERIFIED: file read]
- `ansible/playbooks/roles/bind9/templates/named.acl.conf.j2` — current consumer of `bind9_vpn_network_cidr`. [VERIFIED: file read]
- `ansible/inventory/group_vars/all.yml` — current `lab_id` inventory source. [VERIFIED: file read]
- `ansible/playbooks/roles/base/tasks/install.yml` — current base-package ownership of `bind-utils`. [VERIFIED: file read]
- Official Ansible docs: role argument validation and role defaults. [CITED: https://github.com/ansible/ansible-documentation/blob/devel/docs/docsite/rst/playbook_guide/playbooks_reuse_roles.rst] [CITED: https://github.com/ansible/ansible-documentation/blob/devel/docs/docsite/rst/playbook_guide/playbooks_variables.rst]

### Secondary

- Community role examples showing Jinja defaults inside `meta/argument_specs.yml`. [CITED: https://github.com/ansible-middleware/keycloak/blob/main/roles/keycloak_quarkus/meta/argument_specs.yml] [CITED: https://github.com/lablabs/ansible-role-rke2/blob/main/meta/argument_specs.yml] [CITED: https://github.com/sap-linuxlab/community.sap_install/blob/main/roles/sap_hana_preconfigure/meta/argument_specs.yml]

## Metadata

**Confidence breakdown:**

- Docs-backed argument-spec guidance: MEDIUM — official docs are clear about inline defaults and separate role defaults, but they do not explicitly adjudicate the DRY Jinja-reference style requested here. [CITED: https://github.com/ansible/ansible-documentation/blob/devel/docs/docsite/rst/playbook_guide/playbooks_reuse_roles.rst] [CITED: https://github.com/ansible/ansible-documentation/blob/devel/docs/docsite/rst/playbook_guide/playbooks_variables.rst]
- Codebase audit (`lab_id`, `bind-utils`, `bind9_derived_lab_id`): HIGH — repo-wide grep produced a narrow and consistent result set. [VERIFIED: codebase grep]

**Research date:** 2026-05-06
**Valid until:** 2026-06-05
