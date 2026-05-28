# Project Research Summary

**Project:** HW1-3 LDAP Service Automation
**Domain:** Linux infrastructure — OpenLDAP identity/auth/home for NASA Labs on AlmaLinux 9
**Researched:** 2026-05-28
**Confidence:** HIGH

## Executive Summary

This milestone adds a graded LDAP identity infrastructure to an existing Ansible-managed AlmaLinux lab topology that already includes split-view DNS (BIND9), a firewalld router, WireGuard VPN, Docker agents, and mail (Dovecot/Postfix). The HW1-3 spec requires an OpenLDAP server in the private zone with LDAPS-only access, an NFSv4 home export, two DMZ workstations configured as SSSD-backed LDAP clients, and specific graded behaviors: password policy enforcement (no reuse, min 8 chars, 3 character classes), TOTP password+OTP authentication with SSH key exemption, custom Fortune schema with server-side sorting, strict ACLs (admin write delegation without password read), and sudo rules stored in LDAP.

**Recommended approach:** Add a dedicated private-zone VM (`ldap-01`, `172.16.1.10/24`) colocating OpenLDAP and the NFSv4 `/u` home export. Add two DMZ workstation VMs (`workstation1` `172.16.0.11`, `workstation2` `172.16.0.12`). Create three new Ansible component roles — `openldap` (server-side slapd/OLC/schema/ACL/overlays), `nfs` (NFSv4 export + client mounts), `ldap-client` (SSSD/PAM/SSH/sudo/TOTP on workstations) — and execute in strict dependency order: bootstrap → DNS → OpenLDAP → NFS → workstation clients → mail integration.

**Key risks and mitigations:** (1) OpenLDAP **ACL ordering** — password protection rules must precede broad read rules; test with non-root binds before declaring done. (2) **LDAPS vs StartTLS** — the spec requires `ldaps://` on 636, not StartTLS on 389; the router firewall already limits DMZ→private to TCP/636. (3) **TOTP overlay availability** — `openldap-servers` from EPEL bundles `otp.so`, but this must be verified on the actual AlmaLinux image before building overlays. (4) **Static NFS source-IP masquerading** — the router masquerades DMZ→internal traffic, so an explicit preserve-source exemption for `ldap-01` is required or NFS exports will see router IPs. (5) **Mail regression** — keep `mail_ldap_enabled` gated off until LDAP server, CA trust, and `mailta` TA-group behavior are independently verified.

## Key Findings

### Recommended Stack

OpenLDAP server packages require EPEL on AlmaLinux (`openldap-servers` is not in BaseOS/AppStream). Clients use BaseOS packages only. All overlay modules (`ppolicy.so`, `otp.so`, `sssvlv.so`, `check_password.so`) are bundled in `openldap-servers-2.6.8-2.el9` from EPEL.

**Core technologies:**
- **OpenLDAP server** (`openldap-servers` from EPEL 9): Required by the lab for OLC/cn=config, overlay modules, and LDAPS. Do not replace with 389 DS or FreeIPA.
- **SSSD + `sssd-ldap`** (BaseOS 2.9.8): Standard RHEL-family LDAP identity/auth/sudo client. Handles NSS, PAM, SSH key lookup, and sudo rules through one daemon.
- **NFSv4** (`nfs-utils` from BaseOS): Synchronized home directories across workstations. NFSv4-only avoids `rpcbind`/dynamic-port firewall complexity.
- **`authselect`** (BaseOS 1.2.6): Manages PAM/NSS profiles (`authselect select sssd with-mkhomedir`). Replaces deprecated `authconfig`.
- **`check_password.so`** (bundled in `openldap-servers`): Enables 3-character-class password quality enforcement. Configure via `check_password.conf` with `minPoints 3`.
- **OpenSSL + `ca-certificates`** (BaseOS): Self-signed LDAPS certificates with SAN for `ldap.{STUID}.nasa`; trust distributed via `update-ca-trust`.

**See detailed source:** `.planning/research/STACK.md`

### Expected Features

All P1 features are OJ-graded and non-negotiable.

**Must have (table stakes — all P1):**
- LDAPS-only OpenLDAP endpoint on 636 with self-signed CA/cert trust distribution
- Required DIT: `ou=People`, `ou=Group`, `ou=Ppolicy`, `ou=SUDOers`, `ou=Fortune` under `dc={STUID},dc=nasa`
- Users `generalta` (UID 10000), `mailta` (UID 10001), `stu` (UID 20000) with exact UIDs/GIDs/homes/mail/SSH keys
- `ta` group (GID 10000) and `stu` group (GID 20000) as `posixGroup` with `memberUid`
- ACLs: admin (`generalta`/`mailta`) can write passwords but cannot read `userPassword`; users self-service on `loginShell`/`sshPublicKey`/`userPassword` only
- Password policy: no reuse, min 8 chars, 3 character classes (via `ppolicy` + `check_password.so`)
- TOTP: password+OTP for `generalta` and `stu` at LDAP bind; SSH public key exempt
- Fortune custom OLC schema under UUID OID branch; YAML import; server-side sorting and pagination via `slapo-sssvlv`
- SSSD NSS/PAM/SSH key/sudo integration on both workstations
- Host-specific login: `ta` everywhere, `stu` workstation1 only
- Sudo from LDAP: `ta` ALL, `stu` only `ls` on workstation1
- NFSv4 shared `/u` homes with cross-workstation sync
- Mail LDAP integration for `mailta`/`ta` (unblock HW1-2)

**Should have (reliability, not directly graded):**
- Protocol-level LDAP smoke tests covering all grading sections
- ACL regression harness with `slapacl`/live binds as non-root identities
- OLC schema/overlay idempotency checks
- SSSD cache management in verification tasks

**Defer / do not build:**
- LDAP replication/HA (adds grading risk, no requirement)
- FreeIPA/389 DS migration (out of scope)
- Kerberized NFS/LDAP (not required, LDAPS + NFSv4 sufficient)
- User self-service web UI (not graded)
- `pam_oath` as primary TOTP implementation (duplicates secrets, breaks SSH key exemption)

**See detailed source:** `.planning/research/FEATURES.md`

### Architecture Approach

The architecture adds a new private-zone VM for LDAP+NFS and two DMZ workstation VMs, using three new component Ansible roles. The LDAP data model lives in shared inventory variables consumed by DNS, NFS, workstation, and mail roles. Playbook ordering enforces strict dependency direction: DNS records before service FQDNs, LDAP server before NFS exports, NFS exports before workstation mounts, and mail LDAP last.

**Major components:**
1. **`openldap` role** — slapd package, LDAPS listener, OLC `cn=config`, MDB database, base DN, schemas, overlays (`ppolicy`, `otp`, `sssvlv`), ACLs, and DIT data. Runs on `ldap-01` (private zone, `172.16.1.10`).
2. **`nfs` role** — NFSv4-only server mode (export `/u` from `ldap-01`) and client mount mode (mount `/u` on workstations). Host-agnostic, driven by variables.
3. **`ldap-client` role** — SSSD configuration, CA trust, NSS/PAM/SSH key/sudo integration, TOTP enforcement via PAM path. Runs on `workstation1`/`workstation2` with host-specific group allow-lists.
4. **Existing consumers** — `bind9` role publishes A/PTR records for new hosts; `firewall` role on router-01 adds NFSv4 policy and masquerade exemption; `mail` role enables LDAP passdb as final step.

**Architecture patterns used:**
- Dedicated identity/home server in private zone (do not reuse DNS or agent hosts)
- LDAPS-only server boundary (636 only, no 389/StartTLS for remote clients)
- Shared LDAP data model, multiple consumers (one inventory source for UIDs/GIDs/attrs)
- Workstation access as host-specific policy (same role, different vars)
- NFSv4-only with static mounts (no `autofs`, no NFSv3 dynamic ports)
- Mail LDAP as a consumer, not a full workstation client

**See detailed source:** `.planning/research/ARCHITECTURE.md`

### Critical Pitfalls

1. **Misordered OpenLDAP ACLs expose passwords or block authentication** — ACLs are order-sensitive; `userPassword` protections must precede broad read rules. Use exact privilege masks (`=w`, `=xw`) instead of `write` when read must not be implied. Test with non-root binds, never only as `rootdn`. *Prevention phase: Phase 3 (DIT/ACL hardening).*
2. **Treating `cn=config` as editable files instead of LDAP state** — Direct edits to `/etc/openldap/slapd.d/*.ldif` cause startup failures and idempotency loss. Use `ldapi:///` with SASL EXTERNAL for all config changes. Search before add to prevent duplicates. *Prevention phase: Phase 2 (OLC foundation).*
3. **Implementing StartTLS on 389 when the lab requires LDAPS on 636** — Tutorials default to StartTLS, but the spec requires `ldaps://` and the router only opens TCP/636. Configure slapd for `ldaps:///`, distribute self-signed CA, and verify with `openssl s_client` from each client zone. *Prevention phase: Phases 1-2 (DNS/firewall + LDAPS).*
4. **Password policy exists but does not enforce character classes** — `pwdMinLength` alone handles length; 3-class enforcement requires a quality module (`check_password.so` bundled in `openldap-servers`) with `pwdCheckQuality: 2`. Test via user-initiated `ldappasswd`, not rootdn. *Prevention phase: Phase 4 (overlays).*
5. **TOTP implemented in PAM instead of at the LDAP bind boundary** — `pam_oath` duplicates secrets on every workstation and can force TOTP on SSH key auth. Use the OpenLDAP `otp` overlay for server-side TOTP verification during simple bind. SSH key exemption is automatic if PAM is not forced after publickey. *Prevention phase: Phase 4-5 (OTP overlay + client auth).*
6. **Overall package availability risk** — Overlay modules (`otp.so`, `ppolicy.so`, `check_password.so`, `sssvlv.so`) are expected in EPEL's `openldap-servers` but must be verified on the actual course AlmaLinux image before deep overlay work begins. *Prevention phase: Phase 0 spike.*

**See detailed source:** `.planning/research/PITFALLS.md`

## Implications for Roadmap

### Phase 0: Package Feasibility Spike
**Rationale:** The entire LDAP overlay strategy depends on `otp.so`, `check_password.so`, and `sssvlv.so` availability. Verify these on the actual course AlmaLinux image before building anything.
**Delivers:** Confirmed module paths and package versions; adjusted role defaults.
**Addresses:** Overlay availability assumption from STACK.md.
**Avoids:** Pitfall 14 (overlay package availability) — discovering late that a required module is missing.
**Research flag: 🔬 Needs active investigation** — build a throwaway AlmaLinux VM, install `openldap-servers`, list `/usr/lib64/openldap/`, and test-load each overlay module.

### Phase 1: Topology & VM Foundation
**Rationale:** New VMs (ldap-01, workstation1, workstation2) must exist with cloud-init provisioning, inventory entries, host vars, and functional groups before any services can be configured.
**Delivers:** Cloud-init seed directories, inventory host entries under `internal`/`dmz`, functional groups (`ldap_servers`, `workstations`, `ldap_clients`, `nfs_servers`, `nfs_clients`), host vars with examples, and `bootstrap.yml` reachability.
**Addresses:** DNS/topology foundation from FEATURES.md P1.
**Avoids:** Pitfall 13 (cross-zone firewall regression) by starting with narrow policies.
**Uses:** Existing cloud-init patterns, existing `bootstrap.yml` ordering (router-first).
**Standard patterns:** Cloud-init + inventory is well-documented in the existing project. Skip research-phase for this.

### Phase 2: DNS & Firewall Integration
**Rationale:** DNS records must exist before services verify FQDNs and certificates. Router firewall policies must be in place before services listen.
**Delivers:** A/PTR records for `ldap`, `workstation1`, `workstation2`; DNS client resolver restoration; DMZ→private LDAPS (636) policy; new NFSv4 (2049) policy; `ldap-01` masquerade exemption; `ldap-01` host firewall for 636+2049.
**Addresses:** DNS requirements, router firewall integration from ARCHITECTURE.md.
**Avoids:** Pitfall 3 (LDAPS vs StartTLS) by locking firewall to 636 only; Pitfall 8 (NFS source IP masquerading) by adding exemption early.
**Uses:** Existing `bind9` role, existing `firewall` role on `router-01`.
**Standard patterns:** BIND DNS record extension and firewalld policy addition follow existing patterns. Skip research-phase.

### Phase 3: OpenLDAP Server Foundation + DIT
**Rationale:** LDAP server must be operational with LDAPS, OLC, schemas, and base DIT before ACLs, overlays, or clients can be tested.
**Delivers:** `slapd` installed (EPEL), LDAPS listener on 636 with self-signed cert, OLC `cn=config`, MDB database, base DN, all required OUs, NIS/core/cosine/inetorgperson schemas, sudo schema, custom Fortune schema, SSH public key schema.
**Addresses:** Basic Configuration + OUs from FEATURES.md.
**Avoids:** Pitfall 2 (OLC file edits) by using `ldapi:///` + SASL EXTERNAL for all config changes.
**Research flag: 🔬** Verify EPEL repo scoping (only on `ldap_servers` group, not globally). The self-signed cert generation with correct SAN (`DNS:ldap.{STUID}.nasa`, `IP:172.16.1.10`) needs Ansible task design but is well-documented.

### Phase 4: Overlays, ACLs, and Advanced Features
**Rationale:** Overlays (ppolicy, otp, sssvlv) and ACLs depend on the database and base DIT being ready. ACLs must protect data before users/groups are populated.
**Delivers:** ppolicy overlay with password history/min length/3-class enforcement (`check_password.so`); `slapo-otp` overlay with TOTP token entries for `generalta` and `stu`; `slapo-sssvlv` overlay with indexes; OLcAccess ACLs (password protection, self-service, admin delegation); Fortune YAML import; initial users/groups/TA password/TOTP secret entry.
**Addresses:** ACLs, Password Policy, TOTP, Fortune from FEATURES.md (highest-complexity items).
**Avoids:** Pitfall 1 (ACL ordering) by defining the full `olcAccess` list as one ordered `state: exact` operation; Pitfall 4 (ppolicy gaps) by configuring `check_password.so` with `minPoints 3`; Pitfall 5 (TOTP in PAM) by using server-side `otp` overlay.
**Research flags: 🔬🔬 High-uncertainty phases:**
- **TOTP OTP overlay**: Validate `otp.so` module availability and exact OATH attribute schema on AlmaLinux. Test password+OTP bind flow with `ldapwhoami`.
- **Password quality module**: Verify `check_password.so` configuration format vs `ppm` module. Test character class rejection with known-bad passwords.
- **sssvlv sorting**: Verify sorted + paged `ldapsearch` against Fortune entries.
- **Secret encoding**: Confirm TA password hash format and TOTP secret base32→raw conversion.

### Phase 5: NFS Home Export + Mount
**Rationale:** NFS server must export `/u` before workstations mount it. Home directory ownership must use LDAP UID/GID values (numeric on the server since it is not an LDAP client of itself).
**Delivers:** NFSv4 server export of `/u` from `ldap-01`; pre-created `/u/ta/generalta`, `/u/ta/mailta`, `/u/stu/stu` with numeric ownership; NFSv4 client mounts on both workstations; cross-workstation sync validation.
**Addresses:** NFS shared homes from FEATURES.md P1.
**Avoids:** Pitfall 8 (NFS sync/firewall failures) by using NFSv4-only + explicit router policy + source-IP preservation.
**Standard patterns:** NFS export/mount is well-documented on RHEL9. Skip research-phase.

### Phase 6: Workstation LDAP Clients
**Rationale:** SSSD/PAM/SSH/sudo/TOTP client configuration must happen after both LDAP server and NFS server are provably working.
**Delivers:** CA trust installed; SSSD configured for LDAPS NSS/PAM/SSH key/sudo; `authselect sssd` profile; OpenSSH `AuthorizedKeysCommand`; host-specific `simple_allow_groups`; TOTP enforcement on password auth path; `sudoers: files sss` with SSSD sudo provider.
**Addresses:** SSSD client integration, SSH keys, host access, sudo from FEATURES.md.
**Avoids:** Pitfall 6 (SSSD auth failures) by setting `sssd.conf` root:root 0600, enabling required responders, and setting `ldap_tls_reqcert = hard`; Pitfall 7 (sudo LDAP not consumed) by configuring both SSSD sudo provider and `/etc/nsswitch.conf`.
**Research flag: 🔬** SSH key exemption + TOTP interaction on SSSD/PAM path needs verification. Confirm `AuthenticationMethods` is not globally set and `UsePAM yes` does not force TOTP after publickey. Validate with actual SSH key and password+TOTP logins.

### Phase 7: Mail LDAP Integration
**Rationale:** Mail is the final consumer. Enabling it before LDAP is stable regresses HW1-2 passing tests.
**Delivers:** `mail_ldap_enabled: true`; LDAP variables wired to existing Dovecot LDAP passdb template; CA cert deployed to mail host; TA-group-only mail user filter; full mail regression (local + LDAP).
**Addresses:** Cross-HW scoring for `mailta` from FEATURES.md.
**Avoids:** Pitfall 11 (mail LDAP regression) by keeping `mail_ldap_enabled` gated until LDAP verification passes independently.
**Standard patterns:** Mail role's existing LDAP scaffolding is already designed. The main task is wiring variables and running regression. Skip research-phase.

### Phase Ordering Rationale

- **Phase 0 first** because overlay availability is an existential prerequisite for the entire TOTP/password-quality roadmap. Deferred validation of module availability is the #1 schedule risk.
- **Phase 1 before Phase 2** because VMs must exist before DNS records or firewall policies can be applied to them.
- **Phase 2 before Phase 3** because LDAP server FQDN and firewall must be prepared before slapd starts listening.
- **Phase 3 before Phase 4** because the database and DIT must exist before overlays attach to them and ACLs protect their data.
- **Phase 4 before Phase 5** because NFS home ownership uses LDAP UID/GID values that are defined in shared vars, but NFS does not depend on overlays — this could run in parallel if validated.
- **Phase 5 before Phase 6** because workstation homes must be mounted before `mkhomedir` creates local directories that shadow the NFS mount.
- **Phase 6 before Phase 7** because mail LDAP depends on a working LDAP identity infrastructure.
- At each phase boundary, run existing HW1-0/HW1-1/HW1-2 tests to confirm no regression.

### Research Flags Summary

| Phase | Research Needed | Risk if Skipped |
|-------|-----------------|-----------------|
| Phase 0 | Verify `otp.so`, `check_password.so`, `sssvlv.so` on actual AlmaLinux `openldap-servers` package | Late-phase discovery of missing modules forces architecture change |
| Phase 4 | TOTP `otp` overlay exact OATH schema attributes, secret encoding, password+OTP bind test; `check_password.so` vs `ppm` module details; sssvlv sort/pagination validation | ACL/policy logic built against wrong assumptions |
| Phase 6 | SSH key exemption interaction with PAM TOTP enforcement; SSSD `TOTP` in PAM path + `UsePAM yes` + publickey exemption | SSH key logins broken or TOTP bypassed |

Phases 1, 2, 5, and 7 follow well-documented/established patterns and do not need dedicated research-phase calls.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Package names/versions/repos verified via AlmaLinux `dnf repoquery` from container on 2026-05-28. Overlay module paths confirmed via RPM file inventory. |
| Features | HIGH | Assignment spec (`lab/ldap.md`) read and mapped to grading sections. OpenLDAP/SSSD/sudo man pages and admin guides verified each feature's expected behavior. |
| Architecture | HIGH | Based on existing project conventions (component roles, topology groups, playbook ordering, router-first, firewall policy model). Verified against actual inventory/playbook files and the graphify project query. |
| Pitfalls | HIGH | Each pitfall sourced from official OpenLDAP docs, man pages, RHEL9 guides, SSSD docs, and the existing project's router/mail/OLC patterns. Recovery strategies documented. |

**Overall confidence:** HIGH

### Gaps to Address

These are areas where research was well-informed but needs validation during implementation:

- **TOTP OTP overlay exact module name:** `otp.so` / `otp.la` expected in `/usr/lib64/openldap/` — verify on target AlmaLinux image in Phase 0.
- **Password quality module:** `check_password.so` is bundled and documented, but exact `check_password.conf` syntax for 3-class enforcement needs implementation-level testing. Fallback: OpenLDAP `ppm` contrib module.
- **SSSD password+TOTP flow:** The architecture assumes `<password><6-digit TOTP>` appended at LDAP simple bind reaches the `otp` overlay. The exact PAM/SSSD → LDAP bind path needs end-to-end testing with SPENGO/simple auth mechanism.
- **Mail TA-group filter:** The current mail LDAP scaffold does not enforce TA-group-only mail users. Need to decide between LDAP group filter vs inventory-rendered allow-list strategy.
- **SELinux booleans on AlmaLinux 9:** `use_nfs_home_dirs` and `slapd` cert access need permissive/enforcing testing on the actual VM image.
- **Ansible `community.general` LDAP module availability:** The project currently has `community.general 12.6.0` locally. LDAP modules need `python3-ldap` on the delegated host. Decide whether to use `ldap_attrs`/`ldap_entry` or render LDIF and pipe through `ldapmodify -Y EXTERNAL`.

## Sources

### Primary (HIGH confidence)
- `.planning/PROJECT.md` — milestone scope, topology, constraints, existing conventions
- `lab/ldap.md` — HW1-3 assignment requirements and grading sections
- AlmaLinux 9.8 `dnf repoquery` from `almalinux:9` container — confirmed package names, versions, repos, overlay module paths
- OpenLDAP 2.6 Admin Guide — Access Control, slapd-config, Schema Specification, TLS/LDAPS
- OpenLDAP man pages: `slapo-ppolicy(5)`, `slapo-otp(5)`, `slapo-sssvlv(5)`, `slapd-config(5)`, `slapd.access(5)`
- SSSD man pages: `sssd-ldap(5)`, `sssd-simple(5)`, `sssd-sudo(5)`, `sss_ssh_authorizedkeys(1)`
- sudo `sudoers.ldap` manual — `sudoRole` semantics, SSSD integration
- Existing repo: `inventory/hosts.yml`, `playbooks/site.yml`, `host_vars/router-01/main.yml`, `host_vars/primary-ns-01/main.yml`, mail role LDAP templates/asserts
- OpenSSH `sshd_config(5)` — `AuthorizedKeysCommand`, `UsePAM`, `AuthenticationMethods`
- RFC4517, RFC4519 — Directory String matching rules, standard attribute definitions

### Secondary (MEDIUM-HIGH confidence)
- OpenLDAP `ppm` contrib module docs — character-class password quality module behavior
- Red Hat RHEL 9 documentation — SSSD LDAP with TLS, NFS server/client configuration, firewalld policies
- Red Hat SELinux/NFS boolean guidance — `use_nfs_home_dirs` and `semanage fcontext` patterns
- OATH Toolkit `pam_oath` manual — classified as a fallback/anti-feature relative to LDAP OTP overlay
- ITU UUID OID arc reference — `2.25` OID branch for custom Fortune schema

### Tertiary (LOW confidence — needs validation)
- EPEL package set on actual course AlmaLinux 9 image (not tested, only verified from container repoquery)
- `check_password.so` exact configuration format on AlmaLinux 9 (inferred from OpenLDAP source)
- SSSD `chpass_provider = ldap` interaction with `otp` overlay password+OTP bind (needs end-to-end test)
- `community.general` LDAP module availability and `python3-ldap` on controller vs delegated host

---

**Phase ordering recommended for roadmap:**
Phase 0 (spike) → Phase 1 (topology) → Phase 2 (DNS/firewall) → Phase 3 (OpenLDAP server) → Phase 4 (overlays/ACLs/features) → Phase 5 (NFS) → Phase 6 (workstations) → Phase 7 (mail)

*Research completed: 2026-05-28*
*Ready for roadmap: yes*
