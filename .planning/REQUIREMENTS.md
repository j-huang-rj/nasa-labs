# Requirements: NASA Labs — DNS Lab (HW1-1)

**Defined:** 2026-05-05
**Core Value:** Pass all OJ grading checkpoints — authoritative DNS, resolver, DNSSEC

## v1 Requirements

Requirements for the DNS lab assignment. All are mandatory per the spec.

### Primary Authoritative NS

- [ ] **AUTH-01**: BIND9 installed, running, and listening on port 53 on primary-ns-01 (172.16.1.53)
- [x] **AUTH-02**: Two views configured — `private` (matching DMZ + Private zones) and `public` (matching any other source)
- [ ] **AUTH-03**: Forward zone `${ID}.nasa` with all required A records in both views (private view: internal IPs; public view: VPN IPs)
- [ ] **AUTH-04**: SOA record with MNAME = `private-ns.${ID}.nasa.`
- [ ] **AUTH-05**: Reverse zones for `172.16.0.in-addr.arpa` and `172.16.1.in-addr.arpa` (both views)
- [ ] **AUTH-06**: Classless reverse zone `{ID}-sub28.{x}.168.192.in-addr.arpa` using RFC 2317 delegation (both views)
- [ ] **AUTH-07**: TSIG key for dynamic updates; `update-policy` allows only `dynamic1-4` A records + PTR records
- [ ] **AUTH-08**: `allow-transfer` to secondary NS (172.16.0.53); `also-notify` to secondary NS
- [ ] **AUTH-09**: DNSSEC signing with algorithm 13 (ECDSAP256SHA256), digest 2 (SHA-256) for forward zone + VPN reverse zone
- [ ] **AUTH-10**: `172.16.{0|1}` reverse zones are NOT signed (per spec allowance)

### Secondary Authoritative NS

- [x] **SEC-01**: BIND9 installed, running, and listening on port 53 on secondary-ns-01 (172.16.0.53)
- [ ] **SEC-02**: Same two-view structure as primary, but all zones are `type slave`
- [ ] **SEC-03**: `primaries` pointing at 172.16.1.53; zone transfer completes within 10 seconds
- [ ] **SEC-04**: No `allow-update`, no `allow-transfer` — read-only replica
- [ ] **SEC-05**: Dynamic updates received by primary propagate to secondary within 10 seconds

### Internal Resolver

- [ ] **RES-01**: BIND9 installed, running, and listening on port 53 on dns-01 (172.16.1.153)
- [ ] **RES-02**: Recursive resolution for `nasa.` and `168.192.in-addr.arpa` from root server 192.168.255.1
- [ ] **RES-03**: Private-view answers for `{ID}.nasa` and `16.172.in-addr.arpa` (via primary NS at 172.16.1.53)
- [ ] **RES-04**: Forward all other domains to Cloudflare DNS 1.1.1.1
- [ ] **RES-05**: DNSSEC validation with AD bit set in responses for `nasa.` and `168.192.in-addr.arpa`
- [ ] **RES-06**: `allow-query` restricted to DMZ (172.16.0.0/24) and Private (172.16.1.0/24) zones

### Automation & Submission

- [x] **AUTO-01**: All BIND9 config generated idempotently by Ansible `bind9` role
- [ ] **AUTO-02**: DS records generated and ready for OJ upload
- [ ] **AUTO-03**: TSIG key generated and ready for OJ upload

## v2 Requirements

(None — all requirements are in v1 per assignment scope)

## Out of Scope

| Feature | Reason |
|---------|--------|
| HW1-2 (Mail) | Separate assignment |
| HW1-3 (LDAP) | Separate assignment |
| Manual writeup (`manual/dns.md`) | Documentation, not automation |
| Alternative DNS software (PowerDNS, Unbound, etc.) | Spec guarantees only BIND9 |
| BIND9 chroot (`bind-chroot`) | Unnecessary complexity for lab |
| DNS-over-HTTPS / DNS-over-TLS | Not required by spec |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| AUTH-01 | Phase 1 | Pending |
| AUTH-02 | Phase 2 | Complete |
| AUTH-03 | Phase 2 | Pending |
| AUTH-04 | Phase 2 | Pending |
| AUTH-05 | Phase 2 | Pending |
| AUTH-06 | Phase 2 | Pending |
| AUTH-07 | Phase 3 | Pending |
| AUTH-08 | Phase 3 | Pending |
| AUTH-09 | Phase 4 | Pending |
| AUTH-10 | Phase 4 | Pending |
| SEC-01 | Phase 1 + Quick 260506-i20 | Done |
| SEC-02 | Phase 3 | Pending |
| SEC-03 | Phase 3 | Pending |
| SEC-04 | Phase 3 | Pending |
| SEC-05 | Phase 3 | Pending |
| RES-01 | Phase 1 | Pending |
| RES-02 | Phase 5 | Pending |
| RES-03 | Phase 5 | Pending |
| RES-04 | Phase 5 | Pending |
| RES-05 | Phase 5 | Pending |
| RES-06 | Phase 5 | Pending |
| AUTO-01 | Phase 1 + Quick 260506-i20 | Done |
| AUTO-02 | Phase 4 | Pending |
| AUTO-03 | Phase 3 | Pending |

**Coverage:**
- v1 requirements: 24 total
- Mapped to phases: 24
- Unmapped: 0 ✓

---
*Requirements defined: 2026-05-05*
*Last updated: 2026-05-06 after quick task 260506-i20*
