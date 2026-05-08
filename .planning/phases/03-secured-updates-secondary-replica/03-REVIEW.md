---
phase: 03-secured-updates-secondary-replica
reviewed: 2026-05-09T12:00:00Z
depth: deep
files_reviewed: 13
files_reviewed_list:
  - .opencode/artifacts/phase-03-tsig-upload.txt
  - ansible/inventory/host_vars/primary-ns-01/main.yml
  - ansible/inventory/host_vars/primary-ns-01/secrets.example.yml
  - ansible/inventory/host_vars/secondary-ns-01/main.yml
  - ansible/inventory/host_vars/secondary-ns-01/secrets.example.yml
  - ansible/playbooks/roles/bind9/defaults/main.yml
  - ansible/playbooks/roles/bind9/meta/argument_specs.yml
  - ansible/playbooks/roles/bind9/tasks/assert.yml
  - ansible/playbooks/roles/bind9/tasks/config.yml
  - ansible/playbooks/roles/bind9/tasks/verify.yml
  - ansible/playbooks/roles/bind9/templates/named.conf.j2
  - ansible/playbooks/roles/bind9/templates/named.keys.conf.j2
  - ansible/playbooks/roles/bind9/templates/named.zones.conf.j2
findings:
  critical: 0
  warning: 3
  info: 2
  total: 5
status: issues_found
---

# Phase 03: Code Review Report

**Reviewed:** 2026-05-09T12:00:00Z
**Depth:** deep
**Files Reviewed:** 13
**Status:** issues_found

## Summary

Phase 03 implements TSIG-secured dynamic DNS updates on the primary nameserver and a slave/replica secondary nameserver. The review covered all 13 files at deep depth, including cross-file import/call chain analysis, BIND9 config template rendering, variable precedence across host_vars/defaults/secrets, and security posture of the DNS configuration.

**Key positives:**
- TSIG key handling is well-structured: real secrets live in gitignored `secrets.yml` files; only name/algorithm are committed in defaults and example files. The `.opencode/` directory is in `.gitignore`, covering the TSIG artifact.
- The primary zone configuration correctly uses `update-policy` (not `allow-update`) with per-host grants for forward zones and `zonesub` grants for PTR zones — proper BIND9 security practice.
- The secondary zone configuration correctly omits `dynamic_update_scope`, `allow-transfer`, `soa`, `ns`, and `records` — appropriate for read-only slave zones.
- The verification task is thorough: dynamic update success path, unsigned rejection, out-of-policy rejection, AXFR refusal on both primary and secondary, and propagation convergence test.
- The `named.zones.conf.j2` template correctly handles all zone types (master, slave) and `dynamic_update_scope` variants (`forward_a_hosts`, `ptr_zonesub`) with proper guard clauses.

**Key concerns:**
- Secondary slave zones rely on BIND9's default `allow-transfer` ACL rather than explicit restriction.
- The propagation verification test has a hardcoded IP that creates a tight coupling.
- The TSIG artifact file could bypass `.gitignore` protection if `.opencode/` directory exclusions are ever relaxed.

## Warnings

### WR-01: Secondary slave zones lack explicit `allow-transfer` restriction

**File:** `ansible/inventory/host_vars/secondary-ns-01/main.yml:75-109`
**Issue:** All five slave zones on `secondary-ns-01` omit the `allow-transfer` field. While the `named.zones.conf.j2` template (line 34-36) correctly renders `allow-transfer` only when the field is defined, this means BIND9 applies its built-in default ACL `{ localnets; localhost; }`. This allows any host on the secondary's local subnet (172.16.0.0/24) to perform zone transfers (AXFR/IXFR) from the secondary. In a lab environment this is low-risk, but it means any compromised DMZ host could enumerate all DNS records.

**Fix:** Explicitly deny zone transfers on the secondary's slave zones by adding `allow_transfer: []` (which renders as `allow-transfer { };` — denying all):

```yaml
# In ansible/inventory/host_vars/secondary-ns-01/main.yml
bind9_zones:
  - name: "{{ bind9_forward_zone_name }}"
    view: private
    type: slave
    masters: ["172.16.1.53"]
    file: "slaves/private/db.{{ bind9_forward_zone_name }}"
    allow_transfer: []    # deny all — secondary is read-only

  - name: "{{ bind9_forward_zone_name }}"
    view: public
    type: slave
    masters: ["172.16.1.53"]
    file: "slaves/public/db.{{ bind9_forward_zone_name }}"
    allow_transfer: []

  # ... repeat for all slave zones
```

### WR-02: Propagation test hardcodes expected IP address

**File:** `ansible/playbooks/roles/bind9/tasks/verify.yml:359`
**Issue:** The propagation poll task uses a hardcoded IP `172.16.1.202` in the `until` condition. This creates a tight coupling: if the nsupdate command (line 334) ever changes the test IP or if someone manually creates a `dynamic2` record with a different address, the propagation test fails with a misleading error rather than a clear "IP mismatch" message. The cleanup tasks (lines 365-385) also hardcode `172.16.1.202`, compounding the coupling.

**Fix:** Extract the test IP into a variable (or use a set_fact at the start of the propagation block) so the create, poll, and cleanup tasks all reference the same source of truth:

```yaml
- name: "PHASE [verify : Propagation - set test address]"
  ansible.builtin.set_fact:
    _bind9_prop_test_ip: "172.16.1.202"

- name: "PHASE [verify : Propagation - create dynamic2 A record on primary]"
  ansible.builtin.command:
    cmd: >-
      nsupdate -k /etc/named/named.keys.conf <<'NSUPDATE'
      server 172.16.1.53
      zone {{ bind9_forward_zone_name }}
      update add dynamic2.{{ bind9_forward_zone_name }}. 300 A {{ _bind9_prop_test_ip }}
      send
      NSUPDATE
  changed_when: false
  register: _bind9_verify_prop_create

- name: "PHASE [verify : Propagation - poll secondary until dynamic2 appears]"
  ansible.builtin.command:
    cmd: >-
      dig -b 172.16.0.53 @172.16.0.53
      dynamic2.{{ bind9_forward_zone_name }} A +short
  changed_when: false
  register: _bind9_verify_prop_poll
  until: "'{{ _bind9_prop_test_ip }}' in _bind9_verify_prop_poll.stdout"
  retries: 10
  delay: 1
```

### WR-03: TSIG artifact file relies solely on directory-level gitignore

**File:** `.opencode/artifacts/phase-03-tsig-upload.txt`
**Issue:** The TSIG artifact contains a real HMAC-SHA256 secret (`PquK/hQmJH9yBOcKZ4jn04oizTQI3r2vFhJKZL5QMV0=`). It is protected from git tracking only by `.gitignore` line 22 (`.opencode/`). There is no file-level exclusion (e.g., `.opencode/artifacts/*.txt`). If the `.opencode/` directory exclusion is ever removed (e.g., during a `.gitignore` cleanup), the artifact and its secret would be silently staged on the next `git add`. The file confirmed not tracked by git (`git ls-files --error-unmatch` returns error).

**Fix:** Add an explicit file-level exclusion to `.gitignore` as defense-in-depth:

```gitignore
# In .gitignore, after line 22:
.opencode/
.opencode/artifacts/*.txt
```

## Info

### IN-01: `bind9_tsig_key` default has empty secret — intentional but fragile

**File:** `ansible/playbooks/roles/bind9/defaults/main.yml:52-55`
**Issue:** The default `bind9_tsig_key` has `secret: ""`. If an authoritative host lacks a `secrets.yml` override, the key file renders with an empty secret. The verify task (assert at line 441-451) catches this condition, but only when `run_once: true` picks a host that triggers the check. In the current dns group (primary-ns-01, secondary-ns-01, dns-01), `dns-01` uses `resolver` mode and is filtered out by the `when` clause, so the check runs against one of the two authoritative hosts that do have secrets. If a new authoritative host were added to the `dns` group without a `secrets.yml`, behavior would depend on Ansible's host iteration order.

**Fix:** No change strictly required for the current setup. For robustness, the assert task could iterate over all authoritative hosts rather than using `run_once`:

```yaml
# Instead of run_once: true, loop over authoritative hosts
- name: "PHASE [verify : Assert bind9_tsig_key on all authoritative hosts]"
  ansible.builtin.assert:
    quiet: true
    that:
      - hostvars[item].bind9_tsig_key is defined
      - hostvars[item].bind9_tsig_key.secret | default('') | length > 0
    fail_msg: "bind9_tsig_key.secret is empty on {{ item }}"
  loop: "{{ groups['dns'] }}"
  when: hostvars[item].bind9_mode in ['authoritative_primary', 'authoritative_secondary']
  delegate_to: localhost
  run_once: true
```

### IN-02: Secondary `named.keys.conf` rendered even when unused for zone operations

**File:** `ansible/playbooks/roles/bind9/tasks/config.yml:55-63`
**Issue:** The `Render TSIG keys conf` task runs unconditionally (no `when` clause on `bind9_mode`). On the secondary, this renders a `named.keys.conf` file containing the TSIG key. The secondary's slave zones don't reference the key in `allow-transfer` or `update-policy` directives, so the key file is only needed for the nsupdate-based verification tests. This is harmless — extra config lines that BIND9 loads but doesn't use — but it's worth noting that the secondary's zone transfer security relies on IP-based masters ACL, not TSIG authentication.

**Fix:** No change required. The rendered key file is needed for verification and doesn't harm the secondary's runtime behavior. If desired, the task could be conditioned:

```yaml
- name: "PHASE [config : Render TSIG keys conf]"
  when: bind9_mode in ['authoritative_primary', 'authoritative_secondary']
  ansible.builtin.template:
    src: named.keys.conf.j2
    dest: "{{ bind9_keys_conf_path }}"
    ...
```

---

_Reviewed: 2026-05-09T12:00:00Z_
_Reviewer: gsd-code-reviewer_
_Depth: deep_

## Re-Review (Iteration 1)

**Reviewed:** 2026-05-09T14:00:00Z
**Depth:** quick
**Files Re-Reviewed:** 3
**Status:** clean

### WR-01 Fix Verification: `allow_transfer: []` on secondary slave zones

**File:** `ansible/inventory/host_vars/secondary-ns-01/main.yml`

**Verdict: ✅ Correct and complete.**

All 5 slave zones now carry `allow_transfer: []`:
- Line 82: private forward zone ✓
- Line 90: public forward zone ✓
- Line 98: private reverse zone `0.16.172.in-addr.arpa` ✓
- Line 106: private reverse zone `1.16.172.in-addr.arpa` ✓
- Line 114: public RFC 2317 child zone ✓

The empty list `[]` will render as `allow-transfer { };` in `named.zones.conf.j2` (template line 34-36), denying all zone transfers. This matches the original fix recommendation exactly. No new issues introduced.

### WR-02 Fix Verification: Propagation test IP extraction to `set_fact`

**File:** `ansible/playbooks/roles/bind9/tasks/verify.yml`

**Verdict: ✅ Correct and complete.**

Two `set_fact` tasks were added at lines 328-334:
- `_bind9_prop_test_ip` set to `"172.16.1.202"` (line 330)
- `_bind9_prop_test_ip_rev` computed from the IP via Jinja2 `.split('.')` (line 334)

The reverse computation `{{ _bind9_prop_test_ip.split('.')[3] }}.{{ _bind9_prop_test_ip.split('.')[2] }}.{{ _bind9_prop_test_ip.split('.')[1] }}.{{ _bind9_prop_test_ip.split('.')[0] }}.in-addr.arpa` correctly yields `202.1.16.172.in-addr.arpa` for `172.16.1.202`. The Jinja2 expression is verbose but valid and functional.

All 6 downstream references now use the variables:
- Line 342: nsupdate create A record uses `{{ _bind9_prop_test_ip }}` ✓
- Line 354: nsupdate create PTR record uses `{{ _bind9_prop_test_ip_rev }}` ✓
- Line 367: propagation poll `until` condition uses `{{ _bind9_prop_test_ip }}` ✓ (note: the original review example used `'{{ ... }}'` quoting but the actual fix uses the bare variable, which is fine since Ansible evaluates the `until` expression as Jinja2)
- Line 379: cleanup A delete uses the variable indirectly (references `dynamic2.` record name, not the IP) ✓
- Line 390: cleanup PTR delete uses `{{ _bind9_prop_test_ip_rev }}` ✓

No hardcoded `172.16.1.202` remains in the propagation block. The `set_fact` tasks are correctly scoped inside the `when: bind9_mode == 'authoritative_secondary'` block. No new issues introduced.

### WR-03 Fix Verification: `.opencode/artifacts/*.txt` in `.gitignore`

**File:** `.gitignore`

**Verdict: ✅ Correct (defense-in-depth).**

Line 23 now reads `.opencode/artifacts/*.txt`. This is technically redundant with line 22 (`.opencode/`) which already ignores the entire directory tree. However, the original finding was specifically about defense-in-depth — if the `.opencode/` line is ever removed during a gitignore cleanup, the artifact-level pattern provides a safety net. The fix serves its stated purpose. No new issues introduced.

### Re-Review Summary

| Finding | Original Severity | Fix Status | New Issues |
|---------|------------------|------------|------------|
| WR-01 | Warning | ✅ Fixed | 0 |
| WR-02 | Warning | ✅ Fixed | 0 |
| WR-03 | Warning | ✅ Fixed | 0 |

All 3 warnings from the initial review have been correctly addressed. No new issues were introduced by the fixes. The Ansible syntax (set_fact, Jinja2 expressions, empty list values) is valid.

---

_Re-Reviewed: 2026-05-09T14:00:00Z_
_Reviewer: gsd-code-reviewer_
_Depth: quick (re-review of 3 fixed files)_
