---
phase: 1
slug: bind9-role-foundation
status: draft
nyquist_compliant: true
wave_0_complete: true
created: 2026-05-05
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | other — ansible-playbook syntax and runtime checks plus BIND admin commands |
| **Config file** | `ansible/ansible.cfg` |
| **Quick run command** | `ansible-playbook -i ansible/inventory/hosts.example.yml ansible/playbooks/bootstrap.yml --syntax-check` |
| **Full suite command** | `ansible-playbook -i ansible/inventory/hosts.yml ansible/playbooks/bootstrap.yml --limit primary-ns-01,secondary-ns-01,dns-01 && ansible -i ansible/inventory/hosts.yml primary-ns-01,secondary-ns-01,dns-01 -m ansible.builtin.command -a "named-checkconf /etc/named.conf" && ansible -i ansible/inventory/hosts.yml primary-ns-01,secondary-ns-01,dns-01 -m ansible.builtin.shell -a "systemctl is-enabled named && systemctl is-active named && ss -ltnu | grep -E "(:53\b)""` |
| **Estimated runtime** | ~60 seconds |

---

## Sampling Rate

- **After every task commit:** Run `ansible-playbook -i ansible/inventory/hosts.example.yml ansible/playbooks/bootstrap.yml --syntax-check`
- **After every plan wave:** Run `ansible-playbook -i ansible/inventory/hosts.yml ansible/playbooks/bootstrap.yml --limit primary-ns-01,secondary-ns-01,dns-01 && ansible -i ansible/inventory/hosts.yml primary-ns-01,secondary-ns-01,dns-01 -m ansible.builtin.command -a "named-checkconf /etc/named.conf"`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 60 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 01-01-01 | 01 | 1 | AUTO-01 | T-01-01 / T-01-02 | Invalid bind9 variables fail before host changes | static | `rg -n "bind9_mode|bind9_listen_ipv4|bind9_service_name" ansible/playbooks/roles/bind9/defaults/main.yml ansible/playbooks/roles/bind9/meta/argument_specs.yml` | ✅ | ⬜ pending |
| 01-01-02 | 01 | 1 | AUTO-01 | T-01-01 | Role entrypoint matches component-role conventions | syntax | `ansible-playbook -i ansible/inventory/hosts.example.yml ansible/playbooks/bootstrap.yml --syntax-check` | ✅ | ⬜ pending |
| 01-02-01 | 02 | 2 | AUTH-01 | T-01-03 | Packages and config paths are managed deterministically | static | `rg -n "ansible.builtin.dnf|/var/named/dynamic|include_tasks: install.yml|include_tasks: config.yml" ansible/playbooks/roles/bind9/tasks/setup.yml ansible/playbooks/roles/bind9/tasks/install.yml ansible/playbooks/roles/bind9/tasks/config.yml` | ✅ | ⬜ pending |
| 01-02-02 | 02 | 2 | SEC-01 | T-01-03 / T-01-04 | `named` never starts from invalid config and authoritative modes stay non-recursive | syntax | `ansible-playbook -i ansible/inventory/hosts.example.yml ansible/playbooks/bootstrap.yml --syntax-check` | ✅ | ⬜ pending |
| 01-03-01 | 03 | 3 | AUTO-01 | T-01-05 | Inventory provides `lab_id`, host modes, and explicit listen IPs | static | `rg -n "lab_id: 14|bind9_mode:|bind9_listen_ipv4:" ansible/inventory/group_vars/all.yml ansible/inventory/host_vars/primary-ns-01/main.yml ansible/inventory/host_vars/secondary-ns-01/main.yml ansible/inventory/host_vars/dns-01/main.yml` | ✅ | ⬜ pending |
| 01-03-02 | 03 | 3 | RES-01 | T-01-05 / T-01-06 | Inventory-derived identity renders clean config and all three hosts listen on port 53 | runtime | `ansible-playbook -i ansible/inventory/hosts.yml ansible/playbooks/bootstrap.yml --limit primary-ns-01,secondary-ns-01,dns-01 && ansible -i ansible/inventory/hosts.yml primary-ns-01,secondary-ns-01,dns-01 -m ansible.builtin.command -a "named-checkconf /etc/named.conf" && ansible -i ansible/inventory/hosts.yml primary-ns-01,secondary-ns-01,dns-01 -m ansible.builtin.shell -a "systemctl is-enabled named && systemctl is-active named && ss -ltnu | grep -E "(:53\b)""` | ✅ | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

Existing infrastructure covers all phase requirements.

---

## Manual-Only Verifications

All phase behaviors have automated verification once inventory hosts are reachable.

---

## Validation Sign-Off

- [x] All tasks have automated verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all missing references
- [x] No watch-mode flags
- [x] Feedback latency < 60s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
