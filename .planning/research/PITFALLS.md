# Pitfalls Research

**Domain:** BIND9 DNS infrastructure for NASA Labs HW1-1 (split-view authoritative DNS, secondary replication, dynamic updates, DNSSEC, internal resolver on AlmaLinux)
**Researched:** 2026-05-05
**Confidence:** MEDIUM

## Critical Pitfalls

### Pitfall 1: View ordering leaks the wrong answers

**What goes wrong:**
The public view matches internal clients first, or a broad ACL (`any`, overly broad subnet, wrong VPN/DMZ matcher) shadows the intended private view. Result: internal clients get public answers, external clients may see private data, or recursion policy lands on the wrong view entirely.

**Why it happens:**
In split DNS, the configuration looks declarative, but view matching is effectively first-match routing. Teams often define the permissive view first, or they reuse ACLs without testing from each network path in the assignment.

**How to avoid:**
- Put the most specific private view first and the catch-all public view last.
- Define ACLs once (`acl "dmz_and_private" { 172.16.0.0/24; 172.16.1.0/24; };`) and reuse them.
- Test every view boundary explicitly: DMZ host, Private host, VPN-side host.
- Validate with `named-checkconf` before restart and `dig @server name +short` from each source network after deploy.

**Warning signs:**
- `dig` from `172.16.0.0/24` or `172.16.1.0/24` returns VPN/public IPs instead of `172.16.*` answers.
- External queries can resolve `private-ns.${ID}.nasa.` or other private-only records.
- Recursion behavior differs from expectation because clients are landing in the wrong view.

**Phase to address:**
Phase 2 — Split views and authoritative answer correctness.

---

### Pitfall 2: Secondary server is not split-view aware

**What goes wrong:**
The primary has private/public views, but the secondary is configured as a simple slave without matching views and per-view zones. Transfers may fail, or worse, the secondary serves the wrong dataset to the wrong clients.

**Why it happens:**
Developers assume “secondary” means one zone definition per zone name. In BIND9 with views, each served view needs compatible zone definitions and transfer policy. Split-view authoritative DNS is two replication paths, not one.

**How to avoid:**
- Mirror the view structure on the secondary.
- Define zone transfer sources, TSIG keys, and `masters`/`primaries` per view.
- Treat private and public replicas as separate verification targets even when the zone name is the same.
- Add post-deploy checks that query the secondary from both internal and external source networks.

**Warning signs:**
- AXFR succeeds for one view but not the other.
- Secondary answers are identical from internal and external networks when they should differ.
- Logs show transfer denied, not authoritative, or unexpected view selection.

**Phase to address:**
Phase 2 — Split views and secondary replication.

---

### Pitfall 3: TSIG keys do not match across update, transfer, and notify paths

**What goes wrong:**
Dynamic updates fail with `NOTAUTH`/`REFUSED`, zone transfers are denied, or NOTIFY packets are ignored because the key name, algorithm, secret, or referencing clause differs between primary, secondary, and `nsupdate` clients.

**Why it happens:**
TSIG is easy to partially wire up: the key exists on disk, but it is referenced inconsistently across `allow-update`/`update-policy`, `allow-transfer`, `also-notify`, and secondary `primaries`/`server` definitions. Copy-paste configuration makes this worse.

**How to avoid:**
- Generate one canonical TSIG artifact per purpose and distribute it from Ansible templates/vars rather than hand-copying.
- Keep the key name, algorithm, and secret identical on both ends.
- Use narrow `update-policy` grants instead of broad `allow-update`.
- Verify each path independently: `nsupdate`, AXFR/IXFR, and NOTIFY-triggered refresh.

**Warning signs:**
- `nsupdate` succeeds against one host but not another.
- Secondary only updates after manual restart or SOA refresh timer expiry.
- Logs contain `bad auth`, `tsig verify failure`, `refused notify`, or transfer denied messages.

**Phase to address:**
Phase 3 — Dynamic updates and TSIG-secured replication.

---

### Pitfall 4: Treating dynamic zones like static files

**What goes wrong:**
Manual edits to a dynamic zone file disappear, journal files diverge from the text zone file, PTR records fall out of sync with A records, or DNSSEC-signed dynamic content becomes inconsistent.

**Why it happens:**
BIND9 stores live dynamic state in journals. Teams edit the zone file directly after enabling updates, forget `rndc freeze/thaw` or `rndc sync`, and assume the file on disk is the source of truth.

**How to avoid:**
- Separate static zones from dynamic zones in the design.
- For dynamic zones, use `nsupdate` for record changes; if manual edits are unavoidable, `rndc freeze`, edit, then `rndc thaw`.
- Use `rndc sync -clean` when you need the zone file and journal reconciled.
- Build verification that updates both forward A records and corresponding PTR records.

**Warning signs:**
- Records appear after `nsupdate` but vanish after reload/restart.
- Zone file contents do not match live query results.
- `.jnl` files accumulate while operators keep editing the base zone file directly.

**Phase to address:**
Phase 3 — Dynamic update workflow and operational correctness.

---

### Pitfall 5: DNSSEC is done once instead of operated continuously

**What goes wrong:**
Zones are initially signed, but signatures expire, DS records do not match the active key material, dynamic updates are not reflected in signed data, or automation regenerates keys unexpectedly and breaks the chain of trust.

**Why it happens:**
Teams treat DNSSEC as a one-time `dnssec-signzone` step instead of ongoing zone maintenance. In BIND9, `dnssec-policy`/`inline-signing` and write access matter; signing also interacts with dynamic updates and transfers.

**How to avoid:**
- Prefer BIND-managed signing (`dnssec-policy` with inline signing) over ad hoc manual signing scripts.
- Keep key material stable across reruns; do not regenerate keys unless intentionally rotating.
- Ensure the daemon can write signed zone state.
- Verify the exact assignment requirements separately: algorithm 13, digest 2, DS upload for `${ID}.nasa` and `{ID}-sub28.{x}.168.192.in-addr.arpa`.
- Add a post-change check: authoritative server returns DNSKEY/RRSIG, and the internal resolver returns `ad` for validated answers.

**Warning signs:**
- `dig DNSKEY` works but DS uploaded to OJ no longer validates.
- AD bit is absent from internal resolver answers under `nasa.` or `168.192.in-addr.arpa`.
- Re-running Ansible changes key files or signed zone artifacts unexpectedly.

**Phase to address:**
Phase 4 — DNSSEC signing, trust chain, and validation.

---

### Pitfall 6: Recursive resolver is really just a forwarder with broken validation

**What goes wrong:**
The internal resolver answers queries, but it is not performing the assignment’s intended resolution path: it forwards `nasa.` or `168.192.in-addr.arpa` incorrectly, misses private-view overrides for `${ID}.nasa.` / `16.172.in-addr.arpa`, or returns answers without validated `AD` flags.

**Why it happens:**
Resolver configuration has three overlapping behaviors here: recursive resolution from the course root, private authoritative overrides, and forwarding all other domains to `1.1.1.1`. It is easy to solve one of the three and accidentally break another.

**How to avoid:**
- Model resolver behavior explicitly by zone category: local/private overrides, course-root recursion or `static-stub`, and default forwarding for everything else.
- Enable and test DNSSEC validation on the resolver, not only on the authoritative side.
- Restrict recursion to DMZ and Private clients only.
- Verify with targeted queries: one under `${ID}.nasa`, one under `nasa.` outside your delegated zone, one under `168.192.in-addr.arpa`, and one public Internet domain.

**Warning signs:**
- Queries resolve, but response flags do not include `ad` where the spec expects validation.
- `${ID}.nasa` resolves to public-view data from internal clients.
- Forwarding to `1.1.1.1` accidentally handles `nasa.` lookups that should stay inside the course hierarchy.

**Phase to address:**
Phase 4 — Internal resolver and DNSSEC validation.

---

### Pitfall 7: Classless reverse delegation is modeled like a normal /24 reverse zone

**What goes wrong:**
The VPN reverse namespace for `192.168.x.y/28` is configured as if it were a normal octet-bound reverse zone. PTR lookups under the delegated block fail, or the parent/child delegation chain is incomplete.

**Why it happens:**
Classless in-addr.arpa delegation is unfamiliar. Teams know how to build `0.16.172.in-addr.arpa`, but not RFC 2317-style delegation for a /28 where the parent uses CNAMEs into a child zone.

**How to avoid:**
- Treat the `/28` reverse zone as an RFC 2317 delegation problem, not a standard reverse zone.
- Generate the exact delegated zone name from the assignment (`{ID}-sub28.{x}.168.192.in-addr.arpa`).
- Verify both the parent-side aliasing path and the child zone PTR records.
- Write tests for a real VPN IP in the assigned subnet, not only for the zone apex.

**Warning signs:**
- Forward lookups work but PTRs for VPN IPs do not.
- `dig -x <vpn-ip>` shows NXDOMAIN or stops at the parent `168.192.in-addr.arpa` hierarchy.
- DS upload for the classless reverse zone exists, but resolver validation still fails because the underlying delegation path is wrong.

**Phase to address:**
Phase 1 — Reverse zone design, before DNSSEC is layered on top.

---

### Pitfall 8: SELinux blocks BIND from writing dynamic, transferred, or signed zones

**What goes wrong:**
Named starts, but dynamic updates, inline signing, journal writes, or secondary zone transfers fail at runtime. On AlmaLinux this often appears only after enabling DNSSEC or dynamic updates.

**Why it happens:**
Basic read-only authoritative service can work with the default layout, so teams postpone SELinux thinking until write paths are introduced. Dynamic DNS, zone transfers, and DNSSEC maintenance require correct file contexts and, in common policy setups, the ability for named to write master zone files.

**How to avoid:**
- Place writable zone state in the distro-appropriate writable path (commonly under `/var/named/dynamic` or equivalent managed location).
- Manage SELinux context restoration in Ansible (`restorecon`) and verify the target types are appropriate for named-managed zone files.
- If the policy requires it on the target image, enable the write boolean used for master zone files.
- Test under `Enforcing`, not only `Permissive` or disabled SELinux.

**Warning signs:**
- Dynamic updates fail only when SELinux is enforcing.
- Signed zone files, `.jnl`, or secondary copies are not created even though configuration syntax is valid.
- Audit logs show AVC denials for `named` on zone paths.

**Phase to address:**
Phase 3 — Dynamic update/DNSSEC storage design, with verification carried into Phase 4.

---

### Pitfall 9: Notify and transfer pipeline is too slow or too passive for the 10-second spec

**What goes wrong:**
The secondary eventually converges, but not within the assignment requirement. Dynamic updates land on the primary but are not visible on the secondary before the checker times out.

**Why it happens:**
Teams rely on SOA refresh timing instead of immediate NOTIFY, forget `also-notify`, do not bump serials in static workflows, or only test eventual consistency instead of the course’s tight timing requirement.

**How to avoid:**
- Configure immediate notification from the primary to the secondary.
- Make serial management deterministic.
- Test end-to-end propagation as a timed workflow: update on primary → secondary answer visible in under 10 seconds.
- Avoid heavyweight deploy steps that reload or re-sign more than necessary after every record change.

**Warning signs:**
- Primary answers change immediately, secondary answers lag until refresh interval.
- Zone transfers succeed in logs, but only after manual `rndc retransfer` or service restart.
- OJ-like tests are flaky: pass on a second attempt, fail on a cold run.

**Phase to address:**
Phase 3 — Replication timing and convergence testing.

---

### Pitfall 10: Ansible generates BIND config piecemeal and loses idempotency

**What goes wrong:**
Repeated playbook runs duplicate blocks, drift ACLs across files, leave stale zones/views in place, or produce syntactically valid but semantically inconsistent `named.conf` fragments. Recovery becomes manual because nobody can reason about the final generated config.

**Why it happens:**
Teams reach for `lineinfile`/`blockinfile` because BIND config feels small at first. That collapses once the project needs views, keys, zone stanzas, update policy, resolver options, and SELinux-friendly writable paths.

**How to avoid:**
- Render whole config files or well-defined include files from templates; do not patch BIND config line-by-line.
- Generate zones/views/ACLs from structured variables.
- Validate with `named-checkconf` and `named-checkzone` before restart/reload.
- Keep key material and secret values separate from tracked defaults.
- Add smoke tests that run after every playbook apply.

**Warning signs:**
- Re-running Ansible changes config ordering or content when inputs did not change.
- Duplicate zone definitions or conflicting ACLs appear in generated files.
- Operators must SSH in and hand-edit BIND config after automation runs.

**Phase to address:**
Phase 1 — Automation skeleton and configuration generation, then enforced in every later phase.

---

## Technical Debt Patterns

Shortcuts that seem reasonable but create long-term problems.

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Using `lineinfile` for `named.conf` and zone stanzas | Fast first draft | Non-idempotent drift, duplicate blocks, painful review/debugging | Never for this project |
| Manual `dnssec-signzone` commands in ad hoc tasks | Quick visible signatures | Expired signatures, accidental key churn, hard-to-reproduce deploys | Only for one-off local experiments, not roadmap implementation |
| One shared zone file design for both static and dynamic records | Fewer files initially | Journal confusion, manual edits overwritten, brittle operations | Never once dynamic updates are enabled |
| Single “secondary” config without mirrored views | Simpler mental model | Wrong answers or failed transfers in split DNS | Never for this assignment |
| Keeping live TSIG and DNSSEC private keys in tracked vars/templates | Easy bootstrap | Secret exposure and forced rotation later | Never |

## Integration Gotchas

Common mistakes when connecting BIND9 components and lab infrastructure.

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| Primary ↔ Secondary | Only configuring transfer on the zone, not matching view/key behavior on both ends | Treat each view as its own transfer path and verify notify + transfer per view |
| `nsupdate` ↔ Primary | Broad `allow-update` or mismatched TSIG parameters | Use narrow `update-policy` grants for only the permitted names/record types |
| Resolver ↔ Course root (`192.168.255.1`) | Forwarding `nasa.` to `1.1.1.1` or skipping trust setup | Resolve the course hierarchy via recursion / `static-stub` and validate DNSSEC locally |
| BIND ↔ SELinux | Storing writable state in read-only/default-labeled paths | Use writable named-managed paths, restore contexts, and verify under enforcing mode |
| Ansible ↔ BIND service management | Restarting blindly without syntax validation | Run `named-checkconf` / `named-checkzone` before reload, then smoke-test with `dig` |

## Performance Traps

Patterns that work at lab scale once, but fail under the assignment’s timing and rerun constraints.

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Waiting for SOA refresh instead of using NOTIFY | Secondary eventually catches up, but not within grading window | Configure immediate notification and time end-to-end propagation | Breaks on OJ checks that expect convergence in under 10 seconds |
| Re-signing or regenerating keys on every playbook run | Slow deploys, DS drift, signatures/key files constantly change | Keep DNSSEC state persistent and let BIND maintain signatures | Breaks after the first rerun or DS upload mismatch |
| Full service restarts for every small update | Query flaps, stale secondaries, longer propagation | Prefer targeted reload/sync patterns and avoid unnecessary restart loops | Breaks once dynamic updates and replication are exercised repeatedly |

## Security Mistakes

Domain-specific security issues beyond generic host hardening.

| Mistake | Risk | Prevention |
|---------|------|------------|
| Open recursion on authoritative servers | Amplification risk and wrong service behavior | Disable recursion on auth servers; enable it only on the internal resolver and only for DMZ/Private clients |
| Public or overly broad zone transfers | Leaks private zone contents and internal topology | Restrict `allow-transfer` by host and TSIG, and do it per view |
| Overbroad dynamic update rights | Any approved key can rewrite too much of the zone | Use explicit `update-policy` rules for only `dynamic1-4` A records and allowed PTRs |
| Committing TSIG/DNSSEC secrets | Credential exposure and trust-chain compromise | Keep live secrets in gitignored or vaulted files; commit only examples/placeholders |

## UX Pitfalls

Common operator-experience mistakes in this domain.

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| View logic spread across multiple unrelated templates | Hard to predict which answer a client should receive | Centralize ACL/view definitions and generate them from structured vars |
| No canned verification commands after deploy | Debugging becomes guesswork under time pressure | Print or document a small `dig`/`nsupdate` verification matrix per phase |
| Static and dynamic zone ownership unclear | Operators think edits “didn't save” or “randomly reverted” | Document the source of truth for each zone and enforce it in automation |

## "Looks Done But Isn't" Checklist

Things that appear complete but are missing critical pieces.

- [ ] **Split view:** Queries from DMZ/Private and VPN/external clients return the intended different RRsets on both primary and secondary.
- [ ] **Dynamic updates:** Updating `dynamic1-4` forward records also updates the allowed PTR path, and both changes replicate to the secondary.
- [ ] **DNSSEC:** DS records uploaded to OJ still match current keys after reruns, and resolver responses under `nasa.` / `168.192.in-addr.arpa` include `ad`.
- [ ] **Classless reverse delegation:** A real VPN IP resolves through the parent delegation path into the delegated `/28` child zone.
- [ ] **SELinux:** All update, transfer, and signing workflows still work with SELinux enforcing after a clean service restart.

## Recovery Strategies

When pitfalls occur despite prevention, how to recover.

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Wrong view answers or private data leakage | MEDIUM | Fix ACL/view order, validate with `named-checkconf`, then query from all source networks before proceeding |
| TSIG mismatch | LOW | Regenerate or redistribute the canonical key, update both endpoints, reload, then retest `nsupdate`, AXFR, and NOTIFY |
| Dynamic zone/manual edit conflict | MEDIUM | `rndc freeze`, reconcile intended records, `rndc thaw`, then verify live data and clean/sync journal state |
| Broken DNSSEC chain after rerun | HIGH | Stop key churn, restore the intended key set, re-sign or let policy recover, regenerate DS if key material truly changed, then revalidate with resolver `ad` checks |
| SELinux write denial | MEDIUM | Move writable state to proper paths, restore file contexts, enable required policy boolean if needed, then retry updates/transfers under enforcing mode |

## Pitfall-to-Phase Mapping

How roadmap phases should address these pitfalls.

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| View ordering leaks the wrong answers | Phase 2 — Split views | Matrix of `dig` queries from DMZ, Private, and VPN/external sources against both authoritative servers |
| Secondary server is not split-view aware | Phase 2 — Secondary replication | Secondary returns correct per-view answers and receives both replicas via transfer |
| TSIG mismatch across paths | Phase 3 — Dynamic updates and TSIG | `nsupdate` succeeds only for allowed names/types; AXFR/NOTIFY use the same expected keying |
| Treating dynamic zones like static files | Phase 3 — Dynamic workflow | Dynamic changes survive reload/restart and match both live queries and synced on-disk state |
| DNSSEC operated as one-time signing | Phase 4 — DNSSEC | DNSKEY/RRSIG present, DS matches, AD bit present on resolver answers |
| Resolver is really just a forwarder | Phase 4 — Resolver validation | `${ID}.nasa`, other `nasa.` names, `168.192.in-addr.arpa`, and Internet domains all follow intended resolution paths |
| Classless reverse delegation modeled incorrectly | Phase 1 — Reverse zone design | `dig -x <vpn-ip>` traverses the RFC 2317 delegation and returns the intended PTR |
| SELinux blocks writes | Phase 3 — Writable zone state | Updates, transfers, and signing succeed with SELinux enforcing and no AVC denials |
| Notify/transfer pipeline too slow | Phase 3 — Replication timing | Primary-to-secondary propagation completes in under 10 seconds after update |
| Ansible config generation loses idempotency | Phase 1 — Automation skeleton | Consecutive playbook runs are no-op except for intended state changes; config validates cleanly every run |

## Sources

- `/Users/j.huang.rj/dev/nasa-labs/lab/dns.md` — assignment requirements and grading behavior for views, transfers, dynamic update, DNSSEC, and resolver behavior. **Confidence: HIGH**
- `/Users/j.huang.rj/dev/nasa-labs/.planning/PROJECT.md` — project scope, constraints, and intended automation architecture. **Confidence: HIGH**
- `/Users/j.huang.rj/dev/nasa-labs/.planning/codebase/CONCERNS.md` — existing automation/idempotency concerns relevant to BIND role design. **Confidence: HIGH**
- BIND 9 Administrator Reference Manual (stable): https://bind9.readthedocs.io/en/stable/reference.html — view configuration, zone/view structure, transfer controls. **Confidence: HIGH**
- BIND 9 Administrator Reference Manual (stable): https://bind9.readthedocs.io/en/stable/chapter6.html — dynamic update workflow, `rndc freeze/thaw/sync`, operational behavior of dynamic zones. **Confidence: HIGH**
- BIND 9 Administrator Reference Manual (stable): https://bind9.readthedocs.io/en/stable/chapter5.html — DNSSEC policy, inline signing, key rollover behavior, writable zone-state requirements. **Confidence: HIGH**
- RFC 2317: https://www.rfc-editor.org/rfc/rfc2317.txt — classless IN-ADDR.ARPA delegation using parent-side CNAMEs into delegated child zones. **Confidence: HIGH**
- `named_selinux(8)` policy guidance (mirror): https://www.systutorials.com/docs/linux/man/8-named_selinux/ — named write constraints and `named_write_master_zones` boolean. **Confidence: MEDIUM**

---
*Pitfalls research for: BIND9 DNS infrastructure for NASA Labs HW1-1*
*Researched: 2026-05-05*
