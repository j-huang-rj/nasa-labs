# Feature Research

**Domain:** BIND9 DNS infrastructure for course-lab authoritative + recursive DNS
**Researched:** 2026-05-05
**Confidence:** HIGH for table stakes, MEDIUM for differentiators/anti-features

## Feature Landscape

This project is not building a generic "DNS product" from scratch; it is building a narrowly-scoped BIND9 deployment that must satisfy a fixed grading contract. That changes prioritization. Anything directly exercised by the homework spec is a table stake, even if some teams would treat it as an advanced production feature.

The core shape of the product is: **two authoritative servers with split views plus one internal validating resolver**. The safest feature strategy is to treat secure, tightly-scoped DNS behavior as mandatory, and treat operator convenience features as differentiators only if they reduce configuration risk without widening scope.

### Table Stakes (Users Expect These)

Features users assume exist. Missing these = product feels incomplete.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Dual authoritative topology (primary + read-only secondary) | Redundant authoritative service is baseline DNS hygiene, and the assignment explicitly grades secondary behavior | MEDIUM | Primary owns writes/signing; secondary must replicate but reject updates/transfers |
| Split-horizon views (private/public) | Internal and external clients must receive different answers for the same zone | HIGH | In BIND9 this is view-driven; view ordering and match-clients mistakes are common failure points |
| Authoritative forward + reverse zones | DNS infrastructure is incomplete without both A/NS/SOA and PTR coverage for managed networks | HIGH | Includes `${ID}.nasa`, `172.16.0/24`, `172.16.1/24`, and classless `192.168.x.y/28` delegation |
| Secure zone replication (allow-transfer + NOTIFY) | Secondaries are expected to stay current automatically after changes | MEDIUM | Transfer scope must be narrow; notify path is part of the propagation contract |
| TSIG-scoped dynamic updates | Dynamic records are a graded requirement and a normal way to authenticate DNS updates | HIGH | Must restrict updates to `dynamic1-4` A records and specific PTR records; use `update-policy`, not broad `allow-update` |
| DNSSEC signing for public authoritative data | Secure authoritative answers are explicitly graded and expected in modern DNS infrastructure | HIGH | Assignment fixes algorithm 13 and digest 2; DS export is part of the operational workflow |
| Internal recursive resolver with selective recursion/forwarding | Internal clients expect one resolver that can answer local names and internet names correctly | HIGH | Resolve `nasa.` and `168.192.in-addr.arpa` from the course root, prefer private answers for local zones, forward everything else to `1.1.1.1` |
| DNSSEC validation with AD bit on resolver | A secure internal resolver is incomplete if it cannot validate signed answers | MEDIUM | Requires trust-anchor strategy and correct validation path for `nasa.` and `168.192.in-addr.arpa` |
| Strict query/update/recursion ACLs | DNS products are expected to avoid becoming open resolvers or overly-permissive update targets | MEDIUM | Limit recursion to DMZ + Private, transfers to the secondary, and updates to the TSIG-authorized names only |

### Differentiators (Competitive Advantage)

Features that set the product apart. Not required, but valuable.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Full Ansible-driven provisioning and artifact generation | Makes the lab reproducible, rerunnable, and less error-prone than hand-editing `named.conf` and zone files | MEDIUM | Strongest practical differentiator for this project because the course environment changes per student (`${ID}`, VPN subnet, DS/TSIG artifacts) |
| Automated DNSSEC lifecycle via `dnssec-policy`/inline signing | Reduces manual key handling mistakes and makes reconfiguration safer | MEDIUM | Not required if manual signing works, but it is the cleanest BIND9-native way to keep signatures current |
| Built-in verification harness | Shortens debug cycles and catches OJ failures before submission | MEDIUM | Examples: `named-checkconf`, `named-checkzone`, `dig` view checks, `nsupdate` tests, transfer checks, AD-bit assertions |
| Restricted observability for operators | Makes DNS behavior explainable without widening exposure | LOW | BIND9 `statistics-channels` and focused logging are useful once core behavior works; keep access local/internal only |

### Anti-Features (Commonly Requested, Often Problematic)

Features that seem good but create problems.

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Public recursion / resolver access from anywhere | Feels convenient for testing and "just works" demos | Creates an open-resolver risk, conflicts with the assignment's client scope, and complicates firewalling | Restrict recursion to DMZ and Private clients with explicit ACLs |
| General-purpose DNS control plane or web UI | Sounds more user-friendly and "production-like" | Large scope increase, introduces state drift risk, and is not graded | Keep BIND9 file-backed and manage it via Ansible templates plus narrow TSIG update paths |
| Extra transports/features not exercised by the lab (DoH/DoT, anycast, multi-primary) | Feels modern and impressive | Adds PKI/network complexity with no grading upside and more failure modes | Use plain UDP/TCP 53 and one clear primary-secondary topology |
| Manual, one-off server edits after deployment | Fast for emergencies | Breaks idempotency, causes config drift, and makes reruns unreliable | Treat the repository as the source of truth and regenerate configs through automation |

## Feature Dependencies

```text
[Network reachability + ACL baseline]
    ├──requires──> [Primary authoritative zones]
    │                  ├──requires──> [Split-horizon views]
    │                  │                  ├──requires──> [Secondary replication]
    │                  │                  └──requires──> [Internal resolver private answers]
    │                  ├──requires──> [TSIG-scoped dynamic updates]
    │                  │                  └──requires──> [Secondary replication]
    │                  └──requires──> [DNSSEC signing + DS export]
    │                                     └──enhances──> [Resolver DNSSEC validation]
    └──requires──> [Internal recursive resolver]
                           ├──requires──> [Selective forwarding/root recursion]
                           └──requires──> [DNSSEC validation]

[Public recursion] ──conflicts──> [Strict query/update/recursion ACLs]
[Manual server edits] ──conflicts──> [Full Ansible-driven provisioning]
```

### Dependency Notes

- **Network reachability + ACL baseline requires almost everything else:** if port 53 paths, view matching, or ACLs are wrong, otherwise-correct DNS features appear broken.
- **Primary authoritative zones require split-horizon views:** the same zone name must serve different RRsets to internal and external clients.
- **TSIG-scoped dynamic updates require primary authoritative zones first:** updates only make sense once the target forward and reverse zones already exist.
- **Secondary replication depends on split views and dynamic updates:** the secondary must mirror both the initial zone content and post-update state.
- **DNSSEC signing depends on stable authoritative data:** sign only after zone content, SOA/NS records, and transfer behavior are correct enough to avoid debugging signed noise.
- **Resolver DNSSEC validation depends on authoritative signing + DS publication:** validation cannot succeed if the chain of trust for the managed zones is incomplete.
- **Public recursion conflicts with strict ACLs:** opening resolver access directly undermines the intended security model.
- **Manual server edits conflict with full automation:** every manual fix creates uncertainty about what Ansible will do on the next run.

## MVP Definition

### Launch With (v1)

Minimum viable product — what is needed to satisfy the lab's value proposition.

- [x] Split-view authoritative service on the primary — required for correct public/private answers
- [x] Read-only secondary with transfer + NOTIFY propagation — required for redundancy and grading
- [x] Internal recursive resolver with selective forwarding/root recursion — required for internal name service
- [x] DNSSEC signing + DS export + resolver validation — required for the security portion of grading
- [x] TSIG-scoped dynamic updates for the graded forward/reverse records — required for dynamic DNS scoring
- [x] Strict ACLs around query, transfer, update, and recursion — required to keep the system correct and safe

### Add After Validation (v1.x)

Features to add once core is working.

- [ ] Automated DNSSEC lifecycle management — add when basic signing works and re-runs become frequent
- [ ] Verification harness / smoke tests — add as soon as the first end-to-end config is stable enough to codify
- [ ] Local-only statistics/logging view — add when debugging real failures becomes the bottleneck

### Future Consideration (v2+)

Features to defer until product-market fit is established.

- [ ] RPZ-based policy filtering — useful for security appliances, not necessary for this homework deliverable
- [ ] Catalog zones or multi-server fleet management — premature for a fixed three-node lab
- [ ] Encrypted transports (DoT/DoH) or anycast exposure — out of scope for the grading contract

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Split-horizon authoritative zones | HIGH | HIGH | P1 |
| Secondary replication with NOTIFY | HIGH | MEDIUM | P1 |
| Forward + reverse authoritative coverage | HIGH | HIGH | P1 |
| TSIG-scoped dynamic updates | HIGH | HIGH | P1 |
| Internal recursive resolver behavior | HIGH | HIGH | P1 |
| DNSSEC signing + validation | HIGH | HIGH | P1 |
| Full Ansible-driven provisioning | HIGH | MEDIUM | P2 |
| Verification harness / observability | MEDIUM | MEDIUM | P2 |
| RPZ / advanced policy controls | LOW | MEDIUM | P3 |

**Priority key:**
- P1: Must have for launch
- P2: Should have, add when possible
- P3: Nice to have, future consideration

## Recommendation for Requirements Definition

For this project, requirements should be written as **secure DNS behavior contracts**, not generic feature bullets. In practice that means specifying: which clients can query which service, which view must answer which question, which names can be updated, which zones must transfer, and which responses must validate.

The most important scoping decision is to treat **"production-style extras" as anti-features unless they directly reduce risk for the graded path**. The project wins by being correct, reproducible, and narrow — not by demonstrating every BIND9 capability.

## Sources

- [HIGH] `/Users/j.huang.rj/dev/nasa-labs/lab/dns.md` — assignment feature contract and grading weights
- [HIGH] `/Users/j.huang.rj/dev/nasa-labs/.planning/PROJECT.md` — project scope, constraints, and active requirements
- [HIGH] https://bind9.readthedocs.io/en/stable/reference — BIND9 reference for views, `update-policy`, transfer controls, `response-policy`, and `statistics-channels`
- [HIGH] https://bind9.readthedocs.io/en/stable/dnssec-guide — BIND9 DNSSEC signing and validation guidance
- [MEDIUM] https://bind9.readthedocs.io/en/stable/chapter5 and https://bind9.readthedocs.io/en/stable/chapter6 — operational examples for DNSSEC validation, ACLs, dynamic updates, and zone configuration

---
*Feature research for: BIND9 DNS infrastructure lab*
*Researched: 2026-05-05*
