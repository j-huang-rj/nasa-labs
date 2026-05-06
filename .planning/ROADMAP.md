# Roadmap: NASA Labs — DNS Lab (HW1-1)

## Overview

This roadmap delivers the BIND9 lab in the dependency order the grader will experience it: first a reusable Ansible `bind9` role with lab identity from inventory, then the primary authoritative service, then secured replication and updates, then DNSSEC trust artifacts, and finally the internal resolver plus end-to-end verification.

**Lab identity:** `lab_id: 14` (set in group/host vars, referenced as `{{ lab_id }}` in templates). Each phase ends with behavior that can be observed with `dig`, `nsupdate`, service checks, or consecutive Ansible runs.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [ ] **Phase 1: Bind9 Role Foundation** - Provision all three DNS hosts from one data-driven Ansible role with runtime-derived lab identity.
- [ ] **Phase 2: Primary Authoritative Zones** - Serve the graded forward and reverse zones from the primary with correct split-view answers.
- [ ] **Phase 3: Secured Updates & Secondary Replica** - Accept only authorized updates on the primary and replicate them to a read-only secondary.
- [ ] **Phase 4: Authoritative DNSSEC Trust Chain** - Sign the graded authoritative zones and generate OJ-ready DS artifacts.
- [ ] **Phase 5: Internal Resolver & Final Verification** - Deliver recursive internal DNS with DNSSEC validation and confirm grading readiness.

## Phase Details

### Phase 1: Bind9 Role Foundation
**Goal**: Operator can provision the primary, secondary, and resolver hosts from one `bind9` component role that uses `lab_id: 14` from inventory instead of hardcoding `${ID}`.
**Depends on**: Nothing (first phase)
**Requirements**: AUTH-01, SEC-01, RES-01, AUTO-01
**Success Criteria** (what must be TRUE):
  1. Operator can run the playbook and end with `named` installed, enabled, and listening on port 53 on `172.16.1.53`, `172.16.0.53`, and `172.16.1.153`.
  2. The same `bind9` role renders host-mode-specific configuration for primary, secondary, and resolver hosts from inventory data without manual file editing on the VMs.
  3. The lab identity (`lab_id: 14`) and VPN subnet inputs are sourced from inventory variables rather than committed as hardcoded values in templates.
  4. Re-running the role with unchanged inputs does not rewrite BIND configuration or drift host state.
**Plans**: 3 plans

Plans:
**Wave 1**
- [x] 01-01-PLAN.md — Define the bind9 role schema, defaults, and entrypoint scaffolding.

**Wave 2** *(blocked on Wave 1 completion)*
- [ ] 01-02-PLAN.md — Implement shared bind package, config, template, handler, and service scaffolding.

**Wave 3** *(blocked on Wave 2 completion)*
- [ ] 01-03-PLAN.md — Wire inventory-driven lab identity, host modes, ACL derivation, and final verification.

### Phase 2: Primary Authoritative Zones
**Goal**: Internal and external clients receive the correct authoritative forward and reverse answers from the primary server for the lab-owned zones.
**Depends on**: Phase 1
**Requirements**: AUTH-02, AUTH-03, AUTH-04, AUTH-05, AUTH-06
**Success Criteria** (what must be TRUE):
  1. DMZ and Private clients querying the primary receive the private view of `${ID}.nasa` with the required 172.16.x.x records.
  2. VPN-side or other external clients querying the primary receive the public view of `${ID}.nasa` with the required VPN-address answers and no exposure of `private-ns.${ID}.nasa.`.
  3. Forward lookups and reverse lookups for `172.16.0/24`, `172.16.1/24`, and the delegated VPN `/28` reverse zone all return authoritative answers from the primary.
  4. The SOA for `${ID}.nasa` identifies `private-ns.${ID}.nasa.` as the MNAME.
**Plans**: 3 plans

Plans:
- [ ] 02-01: Build shared ACLs and private/public view templates with correct first-match ordering for DMZ, Private, and external clients.
- [ ] 02-02: Render forward zone data for both views, including the required host records, NS data, and SOA values.
- [ ] 02-03: Render reverse zones for `172.16.0`, `172.16.1`, and the RFC 2317 VPN delegation, then validate them with BIND tooling and `dig`.

### Phase 3: Secured Updates & Secondary Replica
**Goal**: Authorized updates land on the primary and reach a read-only secondary replica quickly and safely.
**Depends on**: Phase 2
**Requirements**: AUTH-07, AUTH-08, SEC-02, SEC-03, SEC-04, SEC-05, AUTO-03
**Success Criteria** (what must be TRUE):
  1. A client using the generated TSIG key can update only `dynamic1-4.${ID}.nasa` A records and approved PTR records on the primary.
  2. Unsigned updates, out-of-policy updates, and unauthorized transfer attempts are rejected.
  3. The secondary serves the same split-view zone content as the primary but does not accept direct updates or onward zone transfers.
  4. Changes accepted by the primary are visible on the secondary within 10 seconds through NOTIFY and zone transfer.
**Plans**: 3 plans

Plans:
- [ ] 03-01: Generate and distribute TSIG material for update, transfer, and notify paths and export the OJ-uploadable secret artifact.
- [ ] 03-02: Configure primary-side dynamic update policy, transfer ACLs, NOTIFY behavior, and writable SELinux-safe zone state.
- [ ] 03-03: Deploy the secondary with mirrored views and slave zones, then verify propagation timing with `nsupdate` and `dig`.

### Phase 4: Authoritative DNSSEC Trust Chain
**Goal**: The authoritative tier publishes signed data for the graded public zones and exposes DS material ready for submission.
**Depends on**: Phase 3
**Requirements**: AUTH-09, AUTH-10, AUTO-02
**Success Criteria** (what must be TRUE):
  1. Queries for `${ID}.nasa` and `${ID}-sub28.{x}.168.192.in-addr.arpa` return signed authoritative data using the required DNSSEC algorithm.
  2. DS records for the forward zone and VPN reverse zone can be generated from live DNSKEY responses and are ready to upload to the Online Judge.
  3. The `172.16.0.in-addr.arpa` and `172.16.1.in-addr.arpa` zones remain authoritative and usable without requiring DNSSEC signatures.
**Plans**: 2 plans

Plans:
- [ ] 04-01: Enable BIND-managed DNSSEC signing for the forward zone and VPN reverse zone while preserving stable key and journal state across reruns.
- [ ] 04-02: Add DS-export workflow and validation steps that prove the signed zones answer correctly without signing the private 172.16 reverse zones.

### Phase 5: Internal Resolver & Final Verification
**Goal**: Internal clients can use the resolver for course-owned and Internet DNS, with DNSSEC validation and access control verified end to end.
**Depends on**: Phase 4
**Requirements**: RES-02, RES-03, RES-04, RES-05, RES-06
**Success Criteria** (what must be TRUE):
  1. DMZ and Private clients can resolve `nasa.` and `168.192.in-addr.arpa` through `172.16.1.153`, and local lab zones are answered from the private authoritative view.
  2. DMZ and Private clients can resolve non-lab Internet domains through the resolver via `1.1.1.1`.
  3. Validated answers under `nasa.` and `168.192.in-addr.arpa` return with the AD bit set.
  4. Clients outside the DMZ and Private subnets are refused or blocked from using the resolver.
**Plans**: 3 plans

Plans:
- [ ] 05-01: Configure recursive resolution, course-zone conditional forwarding or stubs, and upstream forwarding for general Internet names.
- [ ] 05-02: Enforce resolver ACLs and DNSSEC validation behavior for only the allowed client networks.
- [ ] 05-03: Run the complete verification matrix across views, transfers, updates, DNSSEC, SELinux, and consecutive Ansible runs to confirm grading readiness.

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 1.1 → 1.2 → 2 → 2.1 → 3 → 4 → 5

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Bind9 Role Foundation | 0/3 | Not started | - |
| 2. Primary Authoritative Zones | 0/3 | Not started | - |
| 3. Secured Updates & Secondary Replica | 0/3 | Not started | - |
| 4. Authoritative DNSSEC Trust Chain | 0/2 | Not started | - |
| 5. Internal Resolver & Final Verification | 0/3 | Not started | - |
