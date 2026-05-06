---
phase: 2
slug: primary-authoritative-zones
status: draft
nyquist_compliant: true
wave_0_complete: true
created: 2026-05-06
---

# Phase 2 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | other — ansible-playbook syntax/runtime checks plus BIND admin commands |
| **Config file** | `ansible/ansible.cfg` |
| **Quick run command** | `ansible-playbook -i ansible/inventory/hosts.example.yml ansible/playbooks/bootstrap.yml --syntax-check` |
| **Full suite command** | `ansible-playbook -i ansible/inventory/hosts.yml ansible/playbooks/bootstrap.yml --limit primary-ns-01 && ansible -i ansible/inventory/hosts.yml primary-ns-01 -m ansible.builtin.command -a "named-checkconf /etc/named.conf" && ansible -i ansible/inventory/hosts.yml primary-ns-01 -m ansible.builtin.shell -a "systemctl is-enabled named && systemctl is-active named"` |
| **Estimated runtime** | ~60 seconds |

---

## Sampling Rate

- **After every task commit:** Run `ansible-playbook -i ansible/inventory/hosts.example.yml ansible/playbooks/bootstrap.yml --syntax-check`
- **After every plan wave:** Run `ansible-playbook -i ansible/inventory/hosts.yml ansible/playbooks/bootstrap.yml --limit primary-ns-01`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 60 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 02-01-01 | 01 | 1 | AUTH-02 | T-02-01 / T-02-02 | Private/public ordering is explicit and public `any` cannot shadow private clients | static | `rg -n "bind9_views|bind9_zones|private|public|order" ansible/playbooks/roles/bind9/defaults/main.yml ansible/playbooks/roles/bind9/meta/argument_specs.yml ansible/playbooks/roles/bind9/tasks/assert.yml ansible/inventory/host_vars/primary-ns-01/main.yml` | ✅ | ⬜ pending |
| 02-01-02 | 01 | 1 | AUTH-02 | T-02-01 / T-02-02 | Runtime-derived forward/reverse names and ordered view config render without syntax regressions | syntax | `ansible-playbook -i ansible/inventory/hosts.example.yml ansible/playbooks/bootstrap.yml --syntax-check` | ✅ | ⬜ pending |
| 02-02-01 | 02 | 2 | AUTH-03 / AUTH-04 | T-02-03 | Forward-zone data is rendered separately per view and public data omits `private-ns` A records | static | `rg -n "private-ns|internal-agent|bind9_vpn_router_ip|bind9_forward_zone_name|file: "private/db|file: "public/db" ansible/inventory/host_vars/primary-ns-01/main.yml` | ✅ | ⬜ pending |
| 02-02-02 | 02 | 2 | AUTH-03 / AUTH-04 | T-02-04 | Every rendered zone file is checked with `named-checkzone` before `named` starts | static | `rg -n "named-checkzone|bind9_zones|db.zone.j2" ansible/playbooks/roles/bind9/tasks/service.yml ansible/playbooks/roles/bind9/tasks/config.yml ansible/playbooks/roles/bind9/templates/db.zone.j2` | ✅ | ⬜ pending |
| 02-03-01 | 03 | 3 | AUTH-05 / AUTH-06 | T-02-05 | Reverse zones include both the RFC 2317 carrier CNAMEs and delegated child PTR records | static | `rg -n "0\.16\.172\.in-addr\.arpa|1\.16\.172\.in-addr\.arpa|sub28|CNAME|PTR" ansible/inventory/host_vars/primary-ns-01/main.yml` | ✅ | ⬜ pending |
| 02-03-02 | 03 | 3 | AUTH-02 / AUTH-05 / AUTH-06 | T-02-05 / T-02-06 | Runtime verification proves both private and public answers from the primary using source-bound dig commands | runtime | `ansible-playbook -i ansible/inventory/hosts.example.yml ansible/playbooks/bootstrap.yml --syntax-check && rg -n "dig -b 172\.16\.1\.53|dig -b 127\.0\.0\.1|private-ns|bind9_vpn_ns_ip" ansible/playbooks/roles/bind9/tasks/verify.yml` | ✅ | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

Existing infrastructure covers all phase requirements.

---

## Manual-Only Verifications

All phase behaviors have automated verification once `ansible/inventory/hosts.yml` points at reachable lab hosts.

---

## Validation Sign-Off

- [x] All tasks have automated verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all missing references
- [x] No watch-mode flags
- [x] Feedback latency < 60s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
