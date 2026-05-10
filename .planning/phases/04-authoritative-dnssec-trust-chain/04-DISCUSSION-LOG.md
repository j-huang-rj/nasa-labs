# Phase 4: Authoritative DNSSEC Trust Chain - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-10
**Phase:** 04-authoritative-dnssec-trust-chain
**Areas discussed:** DNSSEC Signing Method, Key Management Strategy, DS Record Export Workflow

---

## DNSSEC Signing Method

| Option | Description | Selected |
|--------|-------------|----------|
| dnssec-policy custom | Explicit "nasa-lab" policy block with algorithm 13, digest 2, unlimited CSK lifetime. Per-zone opt-in. Immune to ISC default-policy drift. | ✓ |
| dnssec-policy default | Built-in BIND policy. Zero config, matches algorithm 13/digest 2. Risk: default policy may change across BIND point releases. | |
| auto-dnssec maintain | Legacy approach. Works on BIND 9.16 but deprecated in 9.18+ and removed in 9.20+. Not recommended for greenfield. | |
| Manual dnssec-signzone | Offline signing. Maximum control but breaks render pipeline and risks signature expiry. Not recommended for OJ grading. | |

**User's choice:** dnssec-policy custom (Recommended)
**Notes:** Custom policy gives exact control over algorithm/digest, protects against ISC default-policy drift across EL9 point releases, and preserves the per-zone opt-in pattern already used for `dynamic_update_scope`.

---

## Key Management Strategy

| Option | Description | Selected |
|--------|-------------|----------|
| Pre-generated + imported | dnssec-keygen -G on control node, store in secrets.yml, distribute via Ansible. Follows existing TSIG pattern. Keys survive VM rebuild. DS computable before deployment. | ✓ |
| BIND auto-generate (default) | Let dnssec-policy auto-generate CSK on-target. Zero Ansible overhead. Risk: VM rebuild loses keys, must re-submit DS to OJ. | |
| dnssec-policy + manual-mode | BIND generates keys but KASP won't auto-advance states. Signing automatic, rollover requires rndc. Less battle-tested. | |
| TSIG-style template distribution | Static Ansible-managed key files, no KASP. Uses deprecated auto-dnssec maintain. Violates ISC migration path. | |

**User's choice:** Pre-generated + imported (Recommended)
**Notes:** Follows existing secrets.yml pattern for TSIG keys and WireGuard credentials. Keys survive VM rebuild (critical for course lab environment). dnssec-keygen -G avoids KASP auto-retire pitfall.

---

## DS Record Export Workflow

| Option | Description | Selected |
|--------|-------------|----------|
| On-target post-sign extraction | dig + dnssec-dsfromkey on primary NS after signing. Matches lab spec exactly. Requires DNS running. Output surfaced via registered var or file. | ✓ |
| Pre-compute from key files | dnssec-dsfromkey on .key files on control node before deployment. DS available immediately, no DNS dependency. | |
| Ansible-delegated control-node | delegate_to: localhost dig + dnssec-dsfromkey. DS files on control node. Requires bind-utils on macOS. Adds network dependency. | |

**User's choice:** On-target post-sign extraction
**Notes:** Matches lab spec exactly. DS records extracted via `dig @172.16.1.53 <zone> DNSKEY | dnssec-dsfromkey -f - <zone>` on primary NS after signing. Student submits DS to OJ manually.

**Follow-up confirmation:** User confirmed on-target only (not both paths). DS records available after playbook run, student submits manually.

---

## the agent's Discretion

- Exact `dnssec-policy` block placement (dedicated include vs. inline in options)
- Key directory path on primary NS
- Whether to add a `bind9_dnssec` feature flag or always include when `bind9_mode == 'authoritative_primary'`
- Exact Ansible task structure for key generation
- Whether `inline-signing yes;` is global or per-zone
- Verification task details in `verify.yml`

## Deferred Ideas

None — discussion stayed within phase scope.