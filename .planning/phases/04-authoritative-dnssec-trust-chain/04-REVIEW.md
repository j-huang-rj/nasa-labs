---
phase: 04-authoritative-dnssec-trust-chain
reviewed: 2026-05-10T14:30:00Z
depth: deep
files_reviewed: 9
files_reviewed_list:
  - ansible/inventory/host_vars/primary-ns-01/main.yml
  - ansible/inventory/host_vars/primary-ns-01/secrets.example.yml
  - ansible/playbooks/roles/bind9/defaults/main.yml
  - ansible/playbooks/roles/bind9/meta/argument_specs.yml
  - ansible/playbooks/roles/bind9/tasks/assert.yml
  - ansible/playbooks/roles/bind9/tasks/config.yml
  - ansible/playbooks/roles/bind9/tasks/verify.yml
  - ansible/playbooks/roles/bind9/templates/named.options.conf.j2
  - ansible/playbooks/roles/bind9/templates/named.zones.conf.j2
findings:
  critical: 2
  warning: 4
  info: 2
  total: 8
status: issues_found
---

# Phase 04: Code Review Report — Authoritative DNSSEC Trust Chain

**Reviewed:** 2026-05-10T14:30:00Z
**Depth:** deep
**Files Reviewed:** 9
**Status:** issues_found

## Summary

Deep cross-file review of the bind9 role's DNSSEC trust chain implementation covering host_vars, defaults, assertions, config tasks, verify tasks, and Jinja2 templates. The implementation is structurally sound with good assertion coverage, idempotent zone state management, and proper SELinux labeling. However, there are gaps in DNSSEC verification completeness for public-view zones and a security concern with TSIG secret handling during verification.

Cross-file tracing verified: variable references between defaults → host_vars → templates → tasks are consistent. The `bind9_zone_serial` filter, `bind9_zone_state` module, and sidecar hash mechanism form a coherent idempotency chain. The view ordering, ACL definitions, and match-clients directives are logically correct for split-horizon DNS.

## Critical Issues

### CR-01: Public-view zones excluded from primary-side DNSSEC verification and DS extraction

**File:** `ansible/playbooks/roles/bind9/tasks/verify.yml:279-374`

**Issue:** The primary-side DNSSEC verification section (DNSKEY query, RRSIG assertion, algorithm check, and DS extraction) only covers **private-view** zones. The filter `selectattr('view', 'equalto', 'private')` is applied to DNSKEY queries (line 286), assertions (lines 298, 311, 324), and DS extraction (lines 332-340). The **public-view VPN child reverse zone** (`{{ bind9_vpn_child_reverse_zone_name }}`) — which has `dnssec_policy: nasa-lab` — is never verified on the primary for:

1. DNSKEY presence
2. RRSIG presence
3. Algorithm 13 (ECDSAP256SHA256) correctness
4. DS record extraction

While the secondary verification (lines 595-631) checks DNSKEY and RRSIG for the public-view VPN child reverse zone via TSIG-keyed query, it does **not** verify algorithm correctness or extract DS records. This means:
- If the zone is signed with the wrong algorithm, neither primary nor secondary will detect it.
- DS records for the VPN child reverse zone are never displayed to the student for OJ submission.

**Fix:** The current filter is actually correct for preventing query failures (the existing review's CR-01 analysis of view-matching is accurate — querying public-view zones from the private source IP would return REFUSED). The fix should add **separate** public-view DNSSEC verification using TSIG-keyed queries:

```yaml
# After the existing private-view DNSSEC checks, add public-view checks:
- name: "PHASE [verify : DNSSEC - Query DNSKEY For Public-View Signed Zones]"
  ansible.builtin.command:
    cmd: >-
      dig -b {{ _bind9_private_source }} @{{ _bind9_private_source }}
      -y "{{ bind9_axfr_key.algorithm }}:{{ bind9_axfr_key.name }}:{{ bind9_axfr_key.secret }}"
      {{ item.name }} DNSKEY +dnssec
  changed_when: false
  register: _bind9_verify_dnskey_public
  loop: "{{ bind9_zones | selectattr('dnssec_policy', 'defined') | selectattr('view', 'equalto', 'public') | list }}"
  loop_control:
    label: "{{ item.name }} ({{ item.view }})"

- name: "PHASE [verify : Assert Public DNSKEY Contains Algorithm 13]"
  ansible.builtin.assert:
    quiet: true
    that:
      - "'DNSKEY' in _bind9_verify_dnskey_public.results[idx].stdout"
      - "'RRSIG' in _bind9_verify_dnskey_public.results[idx].stdout"
      - "' 13 ' in _bind9_verify_dnskey_public.results[idx].stdout"
    fail_msg: >-
      Public-view DNSSEC verification failed for {{ item.name }}.
      stdout={{ _bind9_verify_dnskey_public.results[idx].stdout | default('') }}
  loop: "{{ bind9_zones | selectattr('dnssec_policy', 'defined') | selectattr('view', 'equalto', 'public') | list }}"
  loop_control:
    index_var: idx
    label: "{{ item.name }} ({{ item.view }})"
```

Alternatively, since the secondary already verifies public-view DNSKEY/RRSIG (lines 595-631), add algorithm 13 checks to those secondary assertions and add DS extraction there.

### CR-02: TSIG key config renders with empty secret — produces invalid BIND configuration

**File:** `ansible/playbooks/roles/bind9/templates/named.keys.conf.j2:3-6` and `ansible/playbooks/roles/bind9/tasks/config.yml:55-64`

**Issue:** The `named.keys.conf.j2` template renders the primary TSIG key block **unconditionally**:

```jinja2
key "{{ bind9_tsig_key.name }}" {
        algorithm {{ bind9_tsig_key.algorithm }};
        secret "{{ bind9_tsig_key.secret }}";
};
```

The default for `bind9_tsig_key.secret` is `""` (empty string — see `defaults/main.yml:46`). If `secrets.yml` is not loaded (e.g., first run, missing file, or inventory misconfiguration), this produces:

```
key "lab_ddns_shared" {
        algorithm hmac-sha256;
        secret "";
};
```

An empty `secret ""` is **invalid** in BIND9 — `named-checkconf` will reject it, preventing the service from starting. The config task renders this file unconditionally for non-resolver modes (line 56: `when: bind9_mode != 'resolver'`), so the invalid config is written to disk before the service validation in `service.yml` catches it.

The `assert.yml` phase does **not** validate that `bind9_tsig_key.secret` is non-empty. The verification phase (`verify.yml:637-647`) does assert this, but it runs **after** config rendering and service start — too late to prevent the invalid config from being written.

**Fix:** Either:
1. Gate the TSIG key rendering on non-empty secret (matching the AXFR key pattern):
```jinja2
{% if bind9_tsig_key.secret | length > 0 %}
key "{{ bind9_tsig_key.name }}" {
        algorithm {{ bind9_tsig_key.algorithm }};
        secret "{{ bind9_tsig_key.secret }}";
};
{% endif %}
```

2. Or add TSIG key validation to `assert.yml` (before config rendering):
```yaml
- name: "PHASE [assert : Check bind9_tsig_key.secret Is Non-Empty For Authoritative Modes]"
  when: bind9_mode != 'resolver'
  ansible.builtin.assert:
    quiet: true
    that:
      - bind9_tsig_key.secret is defined
      - bind9_tsig_key.secret | length > 0
    fail_msg: >-
      bind9_tsig_key.secret must be non-empty for authoritative modes.
      Ensure host_vars/*/secrets.yml provides the TSIG key.
```

Option 2 is preferred because it fails early with a clear message rather than rendering invalid config.

## Warnings

### WR-01: TSIG and AXFR secrets exposed via command line in process listings

**File:** `ansible/playbooks/roles/bind9/tasks/verify.yml:151-206, 231-255, 442-452, 480-540, 544-570, 613-620`

**Issue:** Multiple verification tasks pass TSIG secrets directly on the command line via `nsupdate -y` and `dig -y`:

```yaml
cmd: >-
  nsupdate -y
  "{{ bind9_tsig_key.algorithm }}:{{ bind9_tsig_key.name }}:{{ bind9_tsig_key.secret }}"
```

The `ansible.builtin.command` module does not redact `cmd` from the target host's process listing (`/proc/*/cmdline`). On a shared or multi-user system, any user running `ps aux` during playbook execution would see the full TSIG secret in plaintext.

This affects:
- Dynamic update create/modify/delete tests (lines 151-206)
- Out-of-policy update rejection test (lines 231-255)
- Secondary propagation tests (lines 480-540)
- Secondary direct update rejection test (lines 544-570)
- AXFR keyed queries (lines 442-452, 613-620)

**Fix:** For `nsupdate`, use a temporary key file instead of the command line:
```yaml
- name: "PHASE [verify : Dynamic Update - Create dynamic1 A Record]"
  ansible.builtin.shell:
    cmd: >-
      nsupdate -k {{ _bind9_verify_keyfile.path }}
    stdin: |
      server {{ _bind9_private_source }}
      zone {{ bind9_forward_zone_name }}
      update add dynamic1.{{ bind9_forward_zone_name }}. 300 A 172.16.1.200
      send
```

Or use `ansible.builtin.copy` to write a temporary key file, then reference it with `-k`. For `dig -y`, the same approach applies. This is a lab environment so the risk is low, but the pattern should be noted.

### WR-02: DNSSEC policy `assert.yml` does not validate `csk` sub-keys

**File:** `ansible/playbooks/roles/bind9/tasks/assert.yml:137-163`

**Issue:** The DNSSEC policy assertion block validates `bind9_dnssec_policy.name` and `bind9_dnssec_policy.key_directory`, but does **not** validate the `csk` sub-structure (`csk.algorithm`, `csk.lifetime`) or `cds_digest_types`. The template (`named.options.conf.j2:62-64`) accesses these fields unconditionally:

```jinja2
csk lifetime {{ bind9_dnssec_policy.csk.lifetime }} algorithm {{ bind9_dnssec_policy.csk.algorithm }};
```

If `bind9_dnssec_policy` is defined with `name` and `key_directory` but missing `csk` (or `csk.algorithm`), the template will fail with an undefined variable error at render time — a confusing failure mode that doesn't clearly indicate the missing configuration.

**Fix:** Add assertions for the nested fields:
```yaml
- name: "PHASE [assert : Check bind9_dnssec_policy.csk Is Defined]"
  become: false
  ansible.builtin.assert:
    quiet: true
    that:
      - bind9_dnssec_policy.csk is defined
      - bind9_dnssec_policy.csk.algorithm is defined
      - bind9_dnssec_policy.csk.algorithm | length > 0
      - bind9_dnssec_policy.csk.lifetime is defined
    fail_msg: >-
      bind9_dnssec_policy.csk must define 'algorithm' and 'lifetime';
      got {{ bind9_dnssec_policy.csk | default('(undefined)') }}

- name: "PHASE [assert : Check bind9_dnssec_policy.cds_digest_types Is Defined]"
  become: false
  ansible.builtin.assert:
    quiet: true
    that:
      - bind9_dnssec_policy.cds_digest_types is defined
      - bind9_dnssec_policy.cds_digest_types | length > 0
    fail_msg: >-
      bind9_dnssec_policy.cds_digest_types must be a non-empty list;
      got {{ bind9_dnssec_policy.cds_digest_types | default('(undefined)') }}
```

### WR-03: Public-view SOA MNAME not in the public-view NS RRset

**File:** `ansible/inventory/host_vars/primary-ns-01/main.yml:94-127`

**Issue:** The public-view forward zone has:
- SOA MNAME (via `bind9_primary_mname`, rendered in `db.zone.j2:7`): likely `private-ns.{{ bind9_forward_zone_name }}.` (the primary NS FQDN)
- NS RRset: only `ns.{{ bind9_forward_zone_name }}.` (line 111)

The SOA MNAME (`private-ns`) is **not** in the public-view NS RRset. While RFC 2181 does not require MNAME to be in the NS set, it is unconventional and may cause issues with:
- DNS NOTIFY: BIND sends NOTIFY to NS records (not MNAME), so the MNAME won't receive notifications.
- Some DNS validators flag MNAME-not-in-NS as a warning.

The private-view zone correctly includes both `private-ns` and `ns` in its NS RRset (lines 69-70), so the MNAME is in the NS set there.

**Fix:** Either:
1. Add `private-ns` to the public-view NS RRset (if it should be publicly reachable), or
2. Use `ns.{{ bind9_forward_zone_name }}.` as the SOA MNAME for the public view (if the public NS is the intended MNAME).

This depends on the intended architecture — if `bind9_primary_mname` is meant to be the MNAME for both views, it should be in both NS sets.

### WR-04: Public-view DNSSEC verification on secondary lacks algorithm check

**File:** `ansible/playbooks/roles/bind9/tasks/verify.yml:595-631`

**Issue:** The secondary DNSSEC verification checks for DNSKEY and RRSIG presence in the public-view VPN child reverse zone (lines 622-631), but does **not** verify that the signing algorithm is ECDSAP256SHA256 (algorithm 13). The primary-side checks include algorithm verification (line 320: `"' 13 ' in ..."`), but this only applies to private-view zones.

If the zone were accidentally signed with a different algorithm (e.g., RSASHA256), the secondary assertions would still pass because they only check for the presence of DNSKEY/RRSIG records, not the algorithm number.

**Fix:** Add algorithm verification to the secondary DNSSEC assertions:
```yaml
- name: "PHASE [verify : Assert Secondary VPN Child Reverse Zone Has Algorithm 13]"
  ansible.builtin.assert:
    quiet: true
    that:
      - "' 13 ' in _bind9_verify_secondary_dnskey_vpn_rev.stdout"
    fail_msg: >-
      Algorithm 13 (ECDSAP256SHA256) not found in DNSKEY response for
      {{ bind9_vpn_child_reverse_zone_name }} on secondary.
      stdout={{ _bind9_verify_secondary_dnskey_vpn_rev.stdout | default('') }}
```

## Info

### IN-01: `verify.yml` uses `ansible.builtin.shell` with `set -o pipefail` for DS extraction — correct but worth noting

**File:** `ansible/playbooks/roles/bind9/tasks/verify.yml:343-348`

**Issue:** The DS extraction task uses `ansible.builtin.shell` with `set -o pipefail &&` to pipe `dig` output into `dnssec-dsfromkey`. This is the correct approach for ensuring pipe failures are propagated. However, the task is the **only** shell task in the verify phase — all other tasks use `ansible.builtin.command`. This inconsistency is minor but worth noting for maintainability.

**Fix:** No change needed — `shell` is required here for the pipe. The `set -o pipefail` is the correct defensive pattern.

### IN-02: Reverse zone PTR records for `.53` differ between the two reverse zones

**File:** `ansible/inventory/host_vars/primary-ns-01/main.yml:150-152` vs `main.yml:181-183`

**Issue:** The 172.16.0/24 reverse zone maps `.53` → `ns.{{ bind9_forward_zone_name }}.` (the DMZ secondary NS), while the 172.16.1/24 reverse zone maps `.53` → `private-ns.{{ bind9_forward_zone_name }}.` (the primary NS). This is **intentional** — both zones are in the private view, and the split PTR records reflect the different roles of the same octet in different subnets. Just flagging for awareness.

**Fix:** No change needed — this is correct by design.

---

_Reviewed: 2026-05-10T14:30:00Z_
_Reviewer: gsd-code-reviewer (deep)_
_Depth: deep_
