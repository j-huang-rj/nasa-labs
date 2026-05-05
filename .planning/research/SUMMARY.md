# Project Research Summary

**Project:** NASA Labs — BIND9 DNS Infrastructure (HW1-1)
**Domain:** Split-view authoritative DNS + internal recursive resolver on AlmaLinux with Ansible automation
**Researched:** 2026-05-05
**Confidence:** HIGH (stack, features, architecture); MEDIUM (pitfalls)

## Executive Summary

This project deploys a **three-node BIND9 DNS infrastructure** on AlmaLinux 9 for a graded course lab. The system delivers split-horizon authoritative DNS (private/public views on a primary-secondary pair), TSIG-authenticated dynamic updates, DNSSEC signing and validation, and a dedicated internal recursive resolver — all provisioned via an idempotent Ansible component role.

The recommended approach is **distro-packaged BIND 9.16 from AlmaLinux AppStream**, not upstream source builds. This avoids SELinux/systemd integration friction and aligns with the repo's existing firewalld/NetworkManager conventions. The Ansible role should be data-driven: one `bind9` component role that reads `authoritative_primary`, `authoritative_secondary`, or `resolver` mode from host vars — never three separate roles. Config generation must use whole-file Jinja templates, not `lineinfile`/`blockinfile` patching, to preserve idempotency across reruns.

The key risks are **view ordering (split-horizon answer leakage)**, **TSIG consistency across update/transfer/notify paths**, and **DNSSEC lifecycle management** — treating signing as a one-time step rather than continuous maintenance. The research identifies a clear build order that front-loads the automation skeleton and zone design before layering on dynamic updates, replication, and DNSSEC. Every phase has explicit pitfall mappings and verification checkpoints. The project wins by being correct, reproducible, and narrow — not by demonstrating every BIND9 capability.

## Key Findings

### Recommended Stack

The full stack runs on AlmaLinux 9 with pinned package versions from the distro AppStream/BaseOS repositories. The controller node uses `ansible-core` (not the monolithic `ansible` package) with three pinned Galaxy collections for firewalld, NetworkManager, and IP/subnet templating. All BIND packages (`bind`, `bind-utils`, `bind-dnssec-utils`) must come from the same AppStream line to avoid version skew.

**Core technologies:**
- **AlmaLinux 9 + AppStream BIND 9.16.23**: Authoritative primary, secondary, and recursive resolver — matches the lab's repo conventions and ships every feature needed (split views, `update-policy`, inline DNSSEC signing, `rndc` journal workflows) without custom packaging.
- **Ansible Core 2.20.5**: Control-plane automation — core builtins are sufficient for package install, templating, validation, and idempotent rollout; pinning avoids the community-bundle drift.
- **firewalld 1.3.4 + python3-firewall**: DNS port exposure and recursion/transfer constraint — keeps DNS hosts on the same native firewall stack already standardized in this repo.
- **ansible.posix 2.1.0, community.general 12.6.0**: firewalld modules, SELinux toggles, and `nmcli` integration — extends the existing component-role pattern without inventing DNS-only network paths.
- **dnspython 2.8.0** (controller-side): Optional automated DNS assertions beyond `dig` — for SOA/NS, view-specific, DNSSEC AD-bit, and reverse-zone coverage checks.

**What NOT to use:** `bind-chroot` (adds path/SELinux complexity with no grading benefit), upstream BIND tarballs (lose distro integration), broad `allow-update` ACLs (use `update-policy` instead), manual `dnssec-signzone` cron jobs (fight BIND's dynamic journal model), or non-BIND daemons (PowerDNS/NSD/Unbound — the assignment explicitly requires BIND9).

### Expected Features

The feature landscape is driven by the grading contract, not generic product-market fit. Every table-stake feature maps directly to an Online Judge checkpoint.

**Must have (table stakes — all P1):**
- **Split-horizon authoritative zones** (private/public views on both primary and secondary) — graders expect different RRsets from internal vs. external clients for the same zone name.
- **Dual authoritative topology** (writable primary + read-only secondary with NOTIFY/AXFR/IXFR) — redundant service and transfer propagation are explicitly graded.
- **Forward + reverse authoritative coverage** including RFC 2317 classless delegation for the VPN `/28` subnet — incomplete PTR coverage fails the reverse-zone checkpoint.
- **TSIG-scoped dynamic updates** for `dynamic1-4` A records and corresponding PTRs — broad `allow-update` is both less secure and less precise; use `update-policy` tied to a named key.
- **DNSSEC signing + DS export + resolver validation** — algorithm 13 (ECDSA P-256 SHA-256), digest 2 (SHA-256); both authoritative signing and resolver `ad` flag are graded.
- **Internal recursive resolver** with selective forwarding — resolve course-owned zones from the course root (`192.168.255.1`), forward everything else to `1.1.1.1`, return private-view answers for local zones.
- **Strict ACLs** on query, transfer, update, and recursion — no open recursion, no public zone transfers, no overbroad update grants.

**Should have (differentiators — P2):**
- **Full Ansible-driven provisioning and artifact generation** — strongest practical differentiator; makes the lab reproducible across student `${ID}` changes and VPN subnet rotation.
- **Automated DNSSEC lifecycle via `dnssec-policy`/inline signing** — reduces manual key-handling mistakes and makes reconfiguration safer than ad hoc `dnssec-signzone`.
- **Built-in verification harness** — `named-checkconf`, `named-checkzone`, per-view `dig` matrix, `nsupdate` smoke tests, AD-bit assertions.

**Defer (v2+):**
- RPZ-based policy filtering, catalog zones, encrypted transports (DoT/DoH), anycast — none are graded or needed for a three-node lab.

### Architecture Approach

Three separate BIND roles on three hosts: **primary authoritative** (172.16.1.53, writable source of truth, DNSSEC signer, TSIG update target), **secondary authoritative** (172.16.0.53, read-only replica via NOTIFY + AXFR/IXFR), and **internal recursive resolver** (172.16.1.153, recursion + DNSSEC validation + conditional forwarding). A single `bind9` Ansible role supports all three host modes via data-driven variable schema — never fork into separate "primary role" / "resolver role" files. Config is generated as whole-file Jinja templates (named.conf fragments for options, ACLs, keys, views, zones) from structured host vars. Verification is a first-class phase, not ad hoc debugging.

**Major components:**
1. **Ansible bind9 role** — package install, config generation, key placement, zone bootstrapping, validation, service lifecycle. Phased task files mirror the BIND lifecycle: install → config → keys → zones → service → verify.
2. **Primary authoritative service** — canonical zone data, dynamic update target, DNSSEC signer, NOTIFY origin, transfer source. Uses `view`, `zone type primary`, `update-policy`, `dnssec-policy`, `also-notify`, `allow-transfer`.
3. **Secondary authoritative service** — mirrored zone replicas via TSIG-authenticated transfers. Must replicate the same view structure as the primary. Uses `zone type secondary` with per-view `primaries` declarations.
4. **Internal resolver** — recursion for DMZ/Private clients, DNSSEC validation, conditional forwarding for course-owned zones, upstream forwarding for Internet names.
5. **View/ACL layer** — centralized `acl` definitions reused across views; private view first (most specific `match-clients`), catch-all public view last.

### Critical Pitfalls

1. **View ordering leaks the wrong answers** — BIND view matching is first-match, not most-specific. Put the private view first and the `any` catch-all public view last. Verify with `dig` from DMZ, Private, and VPN source networks against both authoritative servers. This is the single most common split-DNS failure mode.

2. **Secondary server is not split-view aware** — The primary has two views but the secondary is configured as a flat slave. Result: transfers fail or the secondary serves identical answers regardless of source. Mirror the exact view structure and per-view `primaries` declarations on the secondary.

3. **TSIG keys do not match across update, transfer, and notify paths** — A key exists on disk but is referenced inconsistently across `update-policy`, `allow-transfer`, `also-notify`, and secondary `primaries` blocks. Generate one canonical TSIG artifact per purpose from Ansible and distribute it to all consumers; never hand-copy.

4. **DNSSEC is done once instead of operated continuously** — Signatures expire, DS records drift from active keys after reruns, or dynamic updates are not reflected in signed data. Use BIND-managed `dnssec-policy` with inline signing, keep key material stable across reruns, and verify `ad` flag on resolver answers after every change.

5. **Classless reverse delegation is modeled like a normal /24 reverse zone** — The VPN `/28` subnet requires RFC 2317 delegation (parent-side CNAMEs into a child zone), not a standard octet-bound zone. Get this right in Phase 1 before DNSSEC is layered on top; verify with `dig -x <vpn-ip>`.

Additional high-impact pitfalls covered in detail: treating dynamic zones like static files (use `rndc freeze/thaw/sync`), SELinux blocking BIND writes (use `/var/named/dynamic` paths and `restorecon`), notify/transfer pipeline too slow for the under-10-second grading window (use immediate NOTIFY, not SOA refresh), and Ansible config generation losing idempotency (render whole templates, never `lineinfile`).

## Implications for Roadmap

Based on research, the recommended phase structure follows the BIND lifecycle from automation skeleton through authoritative foundation, dynamic/replication layer, DNSSEC, resolver, and verification. Each phase builds on the last, and phases are grouped by dependency rather than by host.

### Phase 1: Automation Skeleton & Zone Design
**Rationale:** Every later phase depends on consistent data shape, correct reverse-zone modeling (the RFC 2317 classless delegation must be designed before static zones are built), and idempotent config generation that won't drift across reruns.
**Delivers:** Role directory structure, variable schema (host modes, view definitions, zone declarations, TSIG secret inputs, verification toggles), Jinja template scaffolding, `named-checkconf`/`named-checkzone` integration, and RFC 2317 reverse-zone design for the VPN `/28` subnet.
**Addresses:** FEATURES — reverse zone coverage foundation; PITFALLS — #7 (classless reverse delegation), #10 (Ansible idempotency).
**Research flags:** Standard Ansible role patterns — skip research-phase. Zone design needs careful RFC 2317 implementation; flag for review but not full research.

### Phase 2: Primary Authoritative & Split Views
**Rationale:** The primary is the source of truth for every downstream component. Split views must be correct before replication, updates, or DNSSEC are layered on — debugging view mismatches after adding signing is extremely painful.
**Delivers:** BIND installed on primary, base `named.conf` with options/ACLs, private and public `view` blocks with `match-clients`, static forward zones (`${ID}.nasa`), static reverse zones (`172.16.0/24`, `172.16.1/24`, RFC 2317 classless zone), per-view answer verification from DMZ, Private, and VPN source networks.
**Addresses:** FEATURES — split-horizon authoritative zones, forward + reverse coverage; PITFALLS — #1 (view ordering), #2 (view schema design for secondary). **Both authoritative servers must agree on view structure — design it here even though secondary deployment comes in Phase 3.**
**Research flags:** BIND split-view configuration is well-documented but view-to-transfer interaction for multi-view secondaries has nuance — may benefit from a targeted research-phase on per-view transfer addressing strategies.

### Phase 3: Dynamic Updates & Secured Replication
**Rationale:** Dynamic updates and replication are tightly coupled: the secondary must mirror both initial zone content and post-update state. TSIG keys must be consistent across update, transfer, and notify paths. Getting SELinux writable paths right here avoids hidden failures surfacing later.
**Delivers:** TSIG key generation and distribution, `update-policy` for `dynamic1-4` A records and PTRs, `allow-transfer`/`also-notify` per view, secondary authoritative server (BIND installed, mirrored views, `type secondary` zones with TSIG-authenticated transfers), writable zone state under `/var/named/dynamic` with SELinux contexts, NOTIFY-driven propagation verified under 10 seconds, and `nsupdate` smoke tests with secondary convergence.
**Addresses:** FEATURES — TSIG-scoped dynamic updates, secondary replication with NOTIFY, strict ACLs; PITFALLS — #3 (TSIG mismatch), #4 (dynamic zone handling), #8 (SELinux writes), #9 (transfer timing).
**Research flags:** BIND9 TSIG and update-policy behavior is well-documented with clear examples — standard patterns, skip research-phase. The primary → secondary view-aware transfer path may need validation but not full research.

### Phase 4: DNSSEC Signing & Internal Resolver
**Rationale:** The resolver's DNSSEC validation cannot succeed without signed authoritative data and correct trust chain. Signing must be stable before the resolver is configured, and both must be verified together because the AD-bit behavior spans authoritative and recursive tiers.
**Delivers:** `dnssec-policy` with `ecdsap256sha256` and inline signing on primary, DS record export for `${ID}.nasa` and classless reverse zone, key material stability across reruns, internal resolver (BIND installed, `recursion yes`, `dnssec-validation auto`, conditional forwarding for course zones, `1.1.1.1` forwarding for Internet), recursion restricted to DMZ + Private ACLs, and verified `ad` flag on resolver answers.
**Addresses:** FEATURES — DNSSEC signing + validation, internal recursive resolver; PITFALLS — #5 (DNSSEC continuity), #6 (resolver as forwarder).
**Research flags:** BIND `dnssec-policy` with inline signing has good documentation — standard patterns, skip research-phase for the mechanism itself. The interaction of conditional forwarding with DNSSEC validation for the course root hierarchy benefits from targeted testing but not full research.

### Phase 5: Verification & Hardening
**Rationale:** BIND failures are often cross-component, not local syntax errors. A comprehensive verification matrix catches edge cases that individual phase tests miss. This is also the phase to validate SELinux enforcing mode and idempotency under consecutive playbook runs — things that "look done" but aren't.
**Delivers:** End-to-end `dig` matrix (all views, all source networks, all zone types), `nsupdate` propagation test with secondary convergence timing, AD-bit verification for course-owned and Internet domains, reverse lookup for a real VPN IP through the RFC 2317 delegation chain, `named-checkconf`/`named-checkzone` clean on all hosts, consecutive Ansible runs are no-op, SELinux enforcing validation with no AVC denials, and grading checklist walkthrough.
**Addresses:** FEATURES — verification harness (P2 differentiator); PITFALLS — #8 (SELinux enforcing), #10 (idempotency), "looks done but isn't" checklist.
**Research flags:** Standard operational validation — skip research-phase.

### Phase Ordering Rationale

The order follows strict dependency chains discovered in research:
- **Phase 1 before Phase 2:** Zone design and variable schema must exist before any BIND config is rendered. The RFC 2317 reverse delegation design is foundational — getting it wrong late means rework through DNSSEC and resolver phases.
- **Phase 2 before Phase 3:** Dynamic updates and secondary replication are meaningless without stable authoritative zones. View structure designed in Phase 2 becomes the replication contract for Phase 3.
- **Phase 3 before Phase 4:** DNSSEC signing must operate over zones that already handle dynamic updates correctly. The resolver depends on signed authoritative data existing.
- **Phase 4 as a combined signing + resolver phase:** These are tested together because AD-bit behavior spans both tiers; splitting them would create a "works in isolation, fails together" gap.
- **Phase 5 is continuous:** Verification tasks defined here run after every earlier phase as well; Phase 5 formalizes the complete matrix.

### Research Flags

**Phases likely needing deeper research during planning:**
- **Phase 2 — Split views:** The view-to-secondary-transfer interaction for multi-view authoritative servers has enough nuance (distinguishing replication identity per view, source/addressing strategy, TSIG-based matching) that a targeted research-phase on BIND view-aware secondary configuration would reduce implementation risk.
- **Phase 4 — Resolver DNSSEC + conditional forwarding:** The interaction of `dnssec-validation auto` with conditional forwarding and `static-stub` for the course root hierarchy (`192.168.255.1`) has subtle behavior around trust anchor establishment.

**Phases with well-documented patterns (skip research-phase):**
- **Phase 1:** Standard Ansible role structure, variable schema, and Jinja templating — established patterns in this repo and Ansible documentation.
- **Phase 3:** BIND9 TSIG, `update-policy`, and NOTIFY/AXFR/IXFR are well-documented in ISC's reference manual with clear examples.
- **Phase 5:** Operational validation (`dig`, `nsupdate`, `named-checkconf`) — standard DNS admin tooling.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | All package versions verified against official AlmaLinux 9/10 repository metadata and PyPI/Galaxy APIs. Source quality is direct from authoritative package registries. |
| Features | HIGH (table stakes) / MEDIUM (differentiators) | Table-stake features derived directly from the grading spec (`lab/dns.md`) with BIND9 reference docs confirming feasibility. Differentiator value is based on lab environment experience, not user research. |
| Architecture | HIGH | Standard BIND9 patterns from ISC documentation match the three-node topology exactly. Build order is well-supported by dependency analysis. Anti-patterns are confirmed by BIND documentation. |
| Pitfalls | MEDIUM | Derived from BIND documentation, RFC 2317, SELinux policy guidance, and repo-specific concerns. Most are traceable to known BIND behaviors, but practical severity depends on exact lab environment (SELinux policy version, firewalld zone interactions, OJ timing tolerance). |

**Overall confidence:** HIGH for stack and architecture decisions, MEDIUM for pitfall prevention strategies that depend on runtime environment specifics.

### Gaps to Address

- **Per-view transfer addressing on secondary:** The ARCHITECTURE.md flags that when the same zone name exists in multiple views, the secondary's transfer path must land in the correct primary view. The exact mechanism (source IP differentiation, TSIG key per view, or `server` stanzas) needs validation during Phase 2 implementation. Handle by: targeted testing during Phase 2 with explicit per-view `primaries` declarations.
- **SELinux policy version on target VMs:** The PITFALLS.md research references `named_write_master_zones` boolean behavior from `named_selinux(8)`, but the exact policy available on the AlmaLinux 9 images may differ. Handle by: test under enforcing mode early in Phase 3; if the boolean is absent, fall back to explicit `semanage fcontext` rules.
- **OJ timing tolerance for transfer propagation:** The "under 10 seconds" requirement is inferred from assignment context, not from an official specification. Handle by: design for sub-5-second propagation with immediate NOTIFY; verify with timed tests in Phase 3.
- **VPN subnet `${ID}` derivation:** The exact mapping between student ID and the VPN `/28` subnet octet needs to be explicitly documented or derived from the assignment materials. Handle by: clarify during requirements definition; if ambiguous, surface as a variable in host vars with a clear comment.

## Sources

### Primary (HIGH confidence)
- Official AlmaLinux 9/10 AppStream and BaseOS repository metadata — verified `bind` (9.16.23), `bind-utils`, `bind-dnssec-utils`, `firewalld` (1.3.4), and `python3-firewall` package versions
- ISC BIND 9 Administrator Reference Manual (stable) — `view`, `update-policy`, `allow-transfer`, `also-notify`, `dnssec-policy`, inline-signing, `rndc` operational workflows, dynamic update behavior, DNSSEC validation
- ISC BIND 9 DNSSEC Guide — `dnssec-policy` on primary zones, `dnssec-validation auto`, key management, DS export workflow
- RFC 2317 — Classless IN-ADDR.ARPA delegation using parent-side CNAMEs into delegated child zones
- Ansible documentation (release and maintenance policy, `ansible-core` versioning) and Galaxy APIs (`ansible.posix`, `community.general`, `ansible.utils`)
- `/Users/j.huang.rj/dev/nasa-labs/lab/dns.md` — assignment feature contract and grading weights
- `/Users/j.huang.rj/dev/nasa-labs/.planning/PROJECT.md` — project scope, constraints, and active requirements

### Secondary (MEDIUM confidence)
- `/Users/j.huang.rj/dev/nasa-labs/.planning/codebase/CONCERNS.md` — existing automation/idempotency concerns relevant to BIND role design
- `/Users/j.huang.rj/dev/nasa-labs/.planning/codebase/ARCHITECTURE.md` — existing repo architecture and router-first play ordering
- `named_selinux(8)` policy guidance (mirror) — named write constraints and `named_write_master_zones` boolean
- BIND 9 documentation chapters 5, 6, and 7 — operational examples for DNSSEC validation, ACLs, dynamic updates, `rndc freeze/thaw/sync`, and zone configuration

### Tertiary (LOW confidence)
- PyPI JSON APIs for `ansible-lint` and `dnspython` — version confirmation only; no functional dependency on these versions beyond what's tested in the controller environment

---
*Research completed: 2026-05-05*
*Ready for roadmap: yes*
