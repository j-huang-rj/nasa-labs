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
- [x] 01-02-PLAN.md — Implement shared bind package, config, template, handler, and service scaffolding.

**Wave 3** *(blocked on Wave 2 completion)*
- [x] 01-03-PLAN.md — Wire inventory-driven lab identity, host modes, ACL derivation, and final verification.

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
**Wave 1**
- [x] 02-01-PLAN.md — Establish the primary view contract, ordered ACL matching, and runtime-derived DNS identity facts.

**Wave 2** *(blocked on Wave 1 completion)*
- [x] 02-02-PLAN.md — Populate forward-zone data and add generic per-view zone-file rendering with `named-checkzone` gating.

**Wave 3** *(blocked on Wave 2 completion)*
- [x] 02-03-PLAN.md — Add reverse/RFC 2317 zone data and runtime dig verification for both private and public answers.

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
**Wave 1**
- [x] 03-01-PLAN.md — Create the shared TSIG contract, rendered key include, and controller-local OJ artifact.

**Wave 2** *(blocked on Wave 1 completion)*
- [x] 03-02-PLAN.md — Enforce exact primary-side update policy, transfer ACLs, NOTIFY targets, and writable private zone storage.

**Wave 3** *(blocked on Wave 2 completion)*
- [x] 03-03-PLAN.md — Mirror the live primary zone set onto the secondary and verify read-only propagation within 10 seconds.

### Phase 4: Authoritative DNSSEC Trust Chain
**Goal**: The authoritative tier publishes signed data for all zones and exposes DS material ready for submission.
**Depends on**: Phase 3
**Requirements**: AUTH-09, AUTH-10, AUTO-02
**Success Criteria** (what must be TRUE):
  1. Queries for `${ID}.nasa`, `${ID}-sub28.{x}.168.192.in-addr.arpa`, `0.16.172.in-addr.arpa`, and `1.16.172.in-addr.arpa` return signed authoritative data using the required DNSSEC algorithm.
  2. DS records for all signed zones can be generated from live DNSKEY responses and are ready to upload to the Online Judge.
  3. All authoritative zones serve DNSSEC-signed data; no zone is left unsigned.
**Plans**: 2 plans

Plans:
**Wave 1**
- [x] 04-01-PLAN.md — Define the DNSSEC policy, zone contract, and template wiring so all master zones are signed.

**Wave 2** *(blocked on Wave 1 completion)*
- [x] 04-02-PLAN.md — Generate and distribute stable DNSSEC key material for all zones, then export live DS records and verify signed authoritative behavior.

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
**Wave 1**
- [ ] 05-01-PLAN.md — Enable resolver-mode zone rendering, lab-identity derivation, and runtime trust-anchor delivery for dns-01.

**Wave 2** *(blocked on Wave 1 completion)*
- [ ] 05-02-PLAN.md — Populate dns-01 static-stub and forwarder inventory, then verify recursive resolution, private answers, DNSSEC AD-bit validation, and blocked clients.

**Wave 3** *(blocked on Wave 2 completion)*
- [ ] 05-03-PLAN.md — Add the cross-host grading-readiness playbook for DMZ/Private resolver queries, DS extraction, propagation rechecks, and consecutive-run idempotency.

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 1.1 → 1.2 → 2 → 2.1 → 3 → 4 → 5

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Bind9 Role Foundation | 0/3 | Not started | - |
| 2. Primary Authoritative Zones | 3/3 | Complete | 2026-05-06 |
| 3. Secured Updates & Secondary Replica | 0/3 | Not started | - |
| 4. Authoritative DNSSEC Trust Chain | 2/2 | Complete | 2026-05-10 |
| 5. Internal Resolver & Final Verification | 0/3 | Not started | - |
