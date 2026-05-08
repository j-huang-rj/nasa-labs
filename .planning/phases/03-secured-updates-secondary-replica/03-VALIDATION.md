---
phase: 03
slug: secured-updates-secondary-replica
status: draft
nyquist_compliant: true
wave_0_complete: true
created: 2026-05-09
---

# Phase 03 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | other — Ansible runtime assertions plus `dig`/`nsupdate` CLI probes |
| **Config file** | `ansible/ansible.cfg` |
| **Quick run command** | `ansible-playbook --syntax-check -i ansible/inventory/hosts.yml ansible/playbooks/dns.yml` |
| **Full suite command** | `ansible-playbook -i ansible/inventory/hosts.yml ansible/playbooks/dns.yml --limit primary-ns-01,secondary-ns-01` |
| **Estimated runtime** | ~90 seconds |

---

## Sampling Rate

- **After every task commit:** Run `ansible-playbook --syntax-check -i ansible/inventory/hosts.yml ansible/playbooks/dns.yml`
- **After every plan wave:** Run `ansible-playbook -i ansible/inventory/hosts.yml ansible/playbooks/dns.yml --limit primary-ns-01,secondary-ns-01`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 90 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 03-01-01 | 01 | 1 | AUTO-03 | T-03-01 / T-03-02 | Shared TSIG secret stays gitignored while tracked templates define only placeholders and include paths | config | `rg -n "bind9_tsig_key|named.keys.conf|phase-03-tsig-upload" ansible/playbooks/roles/bind9 ansible/inventory/host_vars/primary-ns-01 ansible/inventory/host_vars/secondary-ns-01 && test -f .opencode/artifacts/phase-03-tsig-upload.txt` | ✅ | ⬜ pending |
| 03-02-01 | 02 | 2 | AUTH-07, AUTH-08 | T-03-03 / T-03-04 | Only signed `dynamic1-4` A updates and private PTR updates are accepted; unsigned or broader updates are refused | integration | `ansible-playbook -i ansible/inventory/hosts.yml ansible/playbooks/dns.yml --limit primary-ns-01 && ansible -i ansible/inventory/hosts.yml primary-ns-01 -m ansible.builtin.shell -a "nsupdate -k /etc/named/named.keys.conf ..."` | ✅ | ⬜ pending |
| 03-03-01 | 03 | 3 | SEC-02, SEC-03, SEC-04, SEC-05 | T-03-05 / T-03-06 | Secondary mirrors the primary within 10 seconds and refuses direct updates or onward AXFR | integration | `ansible-playbook -i ansible/inventory/hosts.yml ansible/playbooks/dns.yml --limit primary-ns-01,secondary-ns-01 && ansible -i ansible/inventory/hosts.yml secondary-ns-01 -m ansible.builtin.command -a "dig @172.16.0.53 dynamic2.<derived-zone> A +short"` | ✅ | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

Existing infrastructure covers all phase requirements.

---

## Manual-Only Verifications

All phase behaviors have automated verification.

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 90s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
