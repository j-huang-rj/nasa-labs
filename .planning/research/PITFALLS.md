# Pitfalls Research

**Domain:** HW1-3 LDAP service automation added to existing NASA Labs AlmaLinux + Ansible + firewalld + mail infrastructure  
**Researched:** 2026-05-28  
**Confidence:** HIGH for OpenLDAP/SSSD/sudo/NFS documented behavior and assignment-visible pitfalls; MEDIUM for AlmaLinux package/module availability and exact OJ probes until verified on the course VM image

## Context-Specific Assumptions

- LDAP is a **subsequent milestone**: HW1-0/HW1-1/HW1-2 behavior must keep passing while LDAP is added.
- LDAP server lives in the **private/internal zone** as `ldap.{STUID}.nasa`; workstations live in the **DMZ** as `workstation1` and `workstation2`.
- The router already contains a narrow `dmz-to-internal-ldaps` policy for TCP/636. Any NFS addition needs similarly narrow cross-zone policy; do not replace this with broad DMZ→internal access.
- The existing mail role already has Dovecot LDAP scaffolding behind `mail_ldap_enabled`; it is a seam, not proof that mail LDAP integration is complete.
- Final implementation should remain Ansible-first, component-role based, and reboot-safe. Manual `ldapmodify` experiments are acceptable only as disposable diagnosis, not final state.

## Critical Pitfalls

### Pitfall 1: Misordered OpenLDAP ACLs expose passwords or block authentication

**What goes wrong:**
Users cannot bind, users can read other users' `userPassword`, `generalta` can read passwords despite the spec forbidding it, or self-service changes to `userPassword`, `loginShell`, and `sshPublicKey` fail. SSSD/Dovecot/mail auth may time out or report invalid credentials even though entries exist.

**Why it happens:**
OpenLDAP ACLs are order-sensitive. `slapd` stops at the first matching `to <what>` rule and first matching `by <who>` clause. Access levels are cumulative: `write` implies `read`, `search`, `compare`, `auth`, and `disclose`. In `cn=config`, `olcAccess` is an ordered multi-value attribute with `{N}` prefixes, so appending rules casually changes semantics. The `rootdn` bypasses ACLs, which can hide failures during admin-only tests.

**How to avoid:**
- Manage the database `olcAccess` as one intentional ordered list, not as scattered appends.
- Put password/secret-specific ACLs before broad `to * by users read` rules.
- For `userPassword`, use privilege specifiers where the lab requires write-without-read, for example `=w` or `=xw`, instead of the `write` access level when read must not be implied.
- Preserve anonymous `auth` access to `userPassword` so simple binds work without exposing hashes.
- Add explicit ACL tests as non-root identities:
  - anonymous/user bind succeeds over LDAPS;
  - `generalta` can modify another user's password but `ldapsearch` as `generalta` does **not** return `userPassword`;
  - normal users can modify only their own `userPassword`, `loginShell`, and `sshPublicKey`;
  - normal users cannot write group membership or sudo rules.
- Use `community.general.ldap_attrs` with `ordered: true` and `state: exact` for `olcAccess`; avoid raw `ldapmodify add: olcAccess` after the list exists.

**Warning signs:**
- `ldapsearch -D uid=generalta,... userPassword` returns password hashes.
- `ldapwhoami -H ldaps://ldap... -D uid=stu,... -w <password>` fails while root/admin bind works.
- Re-running Ansible keeps adding or re-numbering `{0}`, `{1}`, `{2}` ACLs.
- SSSD logs show lookup/bind failures, but `ldapsearch -Y EXTERNAL -H ldapi:///` as root works.

**Phase to address:**
Phase 3 — DIT, users/groups, and ACL hardening. ACLs must be tested before client/PAM/NFS work begins.

---

### Pitfall 2: Treating `cn=config` as editable files instead of LDAP state

**What goes wrong:**
`slapd` fails to start after a reboot, module loads are duplicated, schemas are added under the wrong DN, overlays attach to the wrong database, or `ldapadd` fails with “Already exists”/“Undefined attribute type” during repeat runs.

**Why it happens:**
OpenLDAP's `slapd-config` backend stores configuration as LDIF files, but official guidance says not to edit those files directly. Runtime configuration must be changed through LDAP operations. The config tree is structured: modules under `cn=module{N},cn=config`, schemas under `cn=schema,cn=config`, databases under `olcDatabase={N}<backend>,cn=config`, and overlays under the target database.

**How to avoid:**
- Use `ldapi:///` with SASL EXTERNAL for local config changes from Ansible.
- Load modules before creating overlay entries: `ppolicy`, `otp`, and `sssvlv` must exist before their `olcOverlay=...` entries are added.
- Search before add. If a schema/module/overlay exists, reconcile attributes rather than blindly adding a second entry.
- Never edit `/etc/openldap/slapd.d/*.ldif` with templates or `lineinfile`.
- Keep the OpenLDAP role split into phases: install → base config → modules → schema → database → overlays → DIT data.

**Warning signs:**
- `slaptest` or `systemctl restart slapd` fails after Ansible modifies `slapd.d` files.
- `ldapsearch -Y EXTERNAL -H ldapi:/// -b cn=config` shows duplicate module/schema names.
- Overlay entries exist under `cn=config` but not under `olcDatabase={...}mdb,cn=config`.
- Manual fixes disappear or conflict on the next playbook run.

**Phase to address:**
Phase 2 — slapd/LDAPS/OLC foundation.

---

### Pitfall 3: Implementing StartTLS on 389 when the lab requires LDAPS on 636

**What goes wrong:**
OpenLDAP works locally with `ldapsearch -ZZ`, but OJ, SSSD, Dovecot, or workstation tests fail because they connect to `ldaps://ldap.{STUID}.nasa:636`. Or clients disable certificate verification to “make it work,” hiding a DNS/certificate mismatch.

**Why it happens:**
Many LDAP tutorials default to `ldap://` plus StartTLS. The HW1-3 spec explicitly says LDAPS and “not LDAP over TLS (StartTLS).” The existing router policy also opens only TCP/636 from DMZ to internal.

**How to avoid:**
- Configure `slapd` to listen on `ldaps:///` and publish `ldap.{STUID}.nasa` with a certificate whose SAN/CN matches that name.
- Use `ldaps://ldap.{STUID}.nasa:636` in SSSD, Dovecot, sudo/SSSD, and verification commands.
- Distribute the self-signed CA/certificate trust to DMZ workstations and the mail host; do not set `ldap_tls_reqcert = never` or `validate_certs: false` in final config.
- Open exactly the required path: DMZ → internal TCP/636 to the LDAP server, plus the LDAP host's own firewalld port. Keep VPN→router SSH reject and existing DNS policies intact.
- Verify from each client zone, not from the LDAP server itself:
  - `ldapsearch -H ldaps://ldap.{STUID}.nasa:636 -x -b dc={STUID},dc=nasa '(objectClass=*)' dn`;
  - `openssl s_client -connect ldap.{STUID}.nasa:636 -servername ldap.{STUID}.nasa`.

**Warning signs:**
- Only `ldapsearch -ZZ -H ldap://...` works.
- SSSD logs show TLS trust or hostname verification failures.
- `firewall-cmd --list-all` on router shows 389 opened or broad DMZ→internal ACCEPT.
- Dovecot LDAP checks work only when certificate validation is disabled.

**Phase to address:**
Phase 1 — DNS/firewall/topology; Phase 2 — LDAPS service foundation.

---

### Pitfall 4: Password policy exists but does not enforce reuse, length, or character classes

**What goes wrong:**
Weak passwords, reused passwords, or two-class passwords are accepted. OJ changes a password and the same value can be reused. Alternatively, all password changes fail because the policy requires quality checking but only receives pre-hashed values.

**Why it happens:**
The `ppolicy` overlay is necessary but not sufficient. `pwdMinLength` handles length, `pwdInHistory` handles reuse history, and `pwdCheckQuality` controls syntax checking. Character-class rules require a password quality module such as OpenLDAP's `ppm` check module or an equivalent `check_password()` module. The ppolicy man page also notes that no history checking occurs when the password is modified by the `rootdn`, even though history may be saved.

**How to avoid:**
- Create `ou=Ppolicy,<baseDN>` and a default policy entry referenced by `ppolicy_default`.
- Set at minimum:
  - `pwdAttribute: userPassword`;
  - `pwdMinLength: 8`;
  - `pwdInHistory: 1` or higher;
  - `pwdCheckQuality: 2` so inability to check is a failure, not silently accepted.
- Add a quality checker for “at least 3 of 4 classes.” If using `ppm`, encode its config in `pwdCheckModuleArg` with `minQuality 3` and class definitions.
- Seed initial `TA_PASSWORD` as a hash if required, but test policy using user-initiated password changes over LDAPS, not rootdn replacements.
- Do not manage mutable ppolicy operational attributes (`pwdHistory`, `pwdFailureTime`, `pwdChangedTime`, lockout state) with Ansible `state: exact`.
- Avoid lockout requirements not in the assignment. OJ may perform repeated or malicious attempts; unnecessary lockout can brick `generalta` mid-grading.

**Warning signs:**
- `ldappasswd` as the user accepts `short1A` or accepts the previous password.
- `pwdHistory` never appears after user password changes.
- Password tests pass only when performed as `cn=admin`/rootdn.
- Logs report “unable to check password quality” or “constraint violation” for all password changes.

**Phase to address:**
Phase 4 — overlays and policy behavior.

---

### Pitfall 5: TOTP is implemented in PAM instead of at the LDAP bind boundary

**What goes wrong:**
Public-key SSH logins incorrectly prompt for TOTP, password+TOTP (`password123456`) is rejected, TOTP is required for `mailta`, or mail/Dovecot auth breaks because a mail client does not append an OTP.

**Why it happens:**
The OpenLDAP `otp` overlay is designed to intercept simple binds for users with OATH object classes: users append the OTP code to the end of their LDAP password. Many tutorials instead use `pam_oath`, which makes the workstation own the TOTP decision and can affect public-key login if PAM is forced after publickey authentication. OpenSSH `AuthenticationMethods` can also accidentally require `publickey,keyboard-interactive` for every login.

**How to avoid:**
- Prefer OpenLDAP `slapo-otp`/`otp.la` on the LDAP database, not per-workstation `pam_oath`, for this lab.
- Apply OATH/TOTP object classes and token links only to `generalta` and `stu`, not `mailta`.
- Store `oathSecret` as raw octets. If the OJ tool provides Base32 text, decode it before loading; use base64 LDIF (`::`) or Ansible binary handling so LDAP receives bytes, not the literal Base32 string.
- Use `oathOTPLength: 6`, `oathTOTPTimeStepPeriod: 60`, and SHA-1 as the OID expected by the OpenLDAP OATH schema, not as an arbitrary display string if the module expects an OID.
- Do not reset mutable OTP state such as `oathTOTPLastTimeStep` on every Ansible run.
- Keep OpenSSH's public-key path independent. Do not globally set `AuthenticationMethods publickey,keyboard-interactive` or similar unless a phase-specific test proves it preserves public-key exemption.
- Ensure time sync (`chronyd`) on LDAP server and clients; a 60-second step still fails if clocks drift far enough.

**Warning signs:**
- `ssh -i <key> generalta@workstation1` succeeds at publickey then prompts for a second factor.
- `ldapwhoami -H ldaps://... -D uid=generalta,... -w '<TA_PASSWORD><TOTP>'` fails while `<TA_PASSWORD>` alone succeeds.
- The same TOTP code can be reused repeatedly because Ansible resets last-used state.
- `mailta` authentication asks for or requires a TOTP code.

**Phase to address:**
Phase 4 — OTP overlay; Phase 5 — SSH/PAM integration verification.

---

### Pitfall 6: SSSD resolves users but SSH authentication still fails

**What goes wrong:**
`getent passwd generalta` works, but SSH password auth fails; public-key auth fails; `stu` can log into `workstation2`; or all LDAP users are denied after enabling `access_provider = ldap`.

**Why it happens:**
SSSD has separate providers and responders for NSS, PAM, SSH keys, sudo, and access control. `sssd.conf` must be owned by root and mode `0600`. The LDAP auth provider requires TLS/LDAPS. SSH keys require both SSSD's `ssh` responder and OpenSSH `AuthorizedKeysCommand`. LDAP access control is deny-all if `access_provider=ldap`, `ldap_access_order=filter`, and `ldap_access_filter` is missing.

**How to avoid:**
- Render `/etc/sssd/sssd.conf` as `root:root 0600` and restart/enable SSSD.
- Use `authselect select sssd` rather than hand-editing PAM stacks. Decide deliberately whether to include `with-mkhomedir`; for this lab, NFS-mounted `/u/...` homes should be mounted/provisioned centrally, not accidentally created locally before NFS is available.
- Include required SSSD services/responders: `nss`, `pam`, `ssh`, and `sudo` if using SSSD-backed sudo.
- Configure LDAPS with CA validation: `ldap_uri = ldaps://ldap.{STUID}.nasa:636`, `ldap_tls_reqcert = hard`, and a trusted CA/cert path.
- Map the assignment schema explicitly where needed:
  - users: `uid`, `uidNumber`, `gidNumber`, `homeDirectory`, `loginShell`, `sshPublicKey`;
  - groups: `posixGroup`, `cn`, `gidNumber`, `memberUid` for RFC2307 unless choosing RFC2307bis deliberately.
- Use LDAP data for host access. A robust pattern is `access_provider = ldap`, `ldap_access_order = host`, and the `host` attribute: `*` for TA users, `workstation1` for `stu`.
- Configure OpenSSH:
  - `AuthorizedKeysCommand /usr/bin/sss_ssh_authorizedkeys`;
  - `AuthorizedKeysCommandUser nobody` or a dedicated unprivileged user;
  - `PubkeyAuthentication yes` and `UsePAM yes`.
- Clear SSSD cache after schema/access changes in verification (`sss_cache -E`), but do not make routine login depend on cache clearing.

**Warning signs:**
- `id generalta` works but `/usr/bin/sss_ssh_authorizedkeys generalta` prints nothing.
- `/var/log/sssd/sssd_*.log` reports “Permission denied” for `sssd.conf` or TLS certificate validation failures.
- `stu` can authenticate on `workstation2` because only groups were checked, not host access.
- Access works online, then stale cached decisions persist after LDAP rules are changed.

**Phase to address:**
Phase 5 — workstation LDAP client, SSH, and access control.

---

### Pitfall 7: sudo rules are present in LDAP but sudo never uses them correctly

**What goes wrong:**
`ta` users cannot sudo, `stu` can run more than `ls`, `stu` cannot run `/usr/bin/ls`, or local `/etc/sudoers` rules mask broken LDAP rules.

**Why it happens:**
LDAP sudo uses `sudoRole` entries with `sudoUser`, `sudoHost`, and `sudoCommand`. Sudo commands are full paths, not shell aliases. On SSSD-backed systems, sudo should use `sss` in `nsswitch.conf`; `/etc/ldap.conf` is not used by the SSSD sudo backend. SSSD also caches sudo rules, so stale results can survive after LDAP edits.

**How to avoid:**
- Load the sudo schema and create `ou=SUDOers,<baseDN>`.
- Use SSSD-backed sudo:
  - `/etc/nsswitch.conf`: `sudoers: files sss`;
  - SSSD domain: `sudo_provider = ldap`;
  - set `ldap_sudo_search_base = ou=SUDOers,<baseDN>`.
- Create explicit rules:
  - TA rule: `sudoUser: %ta`, `sudoHost: ALL`, `sudoCommand: ALL`;
  - student rule: `sudoUser: %stu`, `sudoHost: workstation1` or matching FQDN, `sudoCommand: /usr/bin/ls` (consider `/bin/ls` only if the target OS resolves it separately).
- Keep local emergency sudo for the Ansible/bootstrap user, but do not satisfy graded LDAP sudo via local wheel membership.
- Verify with `sudo -l -U generalta` and `sudo -l -U stu` on both workstations after `sss_cache -E`.

**Warning signs:**
- `sudo -l` shows only local file-based rules.
- `sudo -l -U stu` lists `(ALL) ALL` or lists no commands.
- `sssctl user-checks stu -s sudo` differs from `sudo -l`.
- LDAP rule changes do not appear until cache expiry because no explicit cache refresh is performed in tests.

**Phase to address:**
Phase 5 — sudo-ldap integration after SSSD identity/auth works.

---

### Pitfall 8: NFS homes are mounted locally but not synchronized or not reachable through firewalld

**What goes wrong:**
Home directories appear on one workstation but not the other, files created on `workstation1` are missing on `workstation2`, logins fail after reboot because `/u` is not mounted, or DMZ workstations cannot mount the private NFS export because router policy blocks the client-initiated DMZ→internal path.

**Why it happens:**
The assignment requires consistent homes across machines, not just directories with the right names. NFS clients initiate connections from DMZ to the private-zone server. The current router only permits narrow DMZ→internal services such as LDAPS and DNS; NFS must be added deliberately. NFSv3 also uses multiple RPC services/ports unless pinned, making firewalling fragile.

**How to avoid:**
- Prefer NFSv4-only for the lab so the cross-zone firewall can allow a narrow TCP/2049 path rather than `rpcbind`/`mountd` plus random ports.
- Add a dedicated router policy for DMZ workstations → NFS server TCP/2049. Do not broaden the existing DMZ→internal reject policy.
- Export only the required home root(s), for example `/u` or `/u/ta` and `/u/stu`, to workstation IPs/subnets.
- Pre-create home directories on the NFS server with exact LDAP numeric IDs and permissions:
  - `/u/ta` and `/u/stu`: `root:root 0755`;
  - `/u/ta/generalta`, `/u/ta/mailta`: owner UID 10000/10001, group `ta` GID 10000, mode `0711`;
  - `/u/stu/stu`: owner UID 20000, group `stu` GID 20000, mode `0711`.
- Keep `root_squash` unless a tightly scoped, documented provisioning step requires server-side root ownership changes. Do not use `no_root_squash` as a shortcut.
- Mount with systemd/network-aware options and verify after reboot. Avoid `pam_mkhomedir` creating local `/u/...` directories before NFS is mounted.

**Warning signs:**
- `mount -a` works only when firewalld is stopped.
- `df -T /u/ta/generalta` shows a local filesystem on one workstation.
- Files created as `generalta` on one workstation do not appear on the other.
- Ownership displays as numeric IDs or `nobody` because LDAP/NFS ID mapping is inconsistent.

**Phase to address:**
Phase 6 — NFS home synchronization and reboot validation.

---

### Pitfall 9: SELinux blocks the correct configuration, leading to unsafe `setenforce 0` fixes

**What goes wrong:**
LDAPS key files are unreadable by `slapd`, SSH public-key auth fails only with NFS homes, NFS exports are denied, or custom paths work only when SELinux is permissive.

**Why it happens:**
AlmaLinux follows RHEL SELinux behavior. Non-standard certificate paths, NFS-mounted homes, and exported directories need correct labels/booleans. Disabling SELinux makes tests pass locally but creates non-reproducible and less secure final state.

**How to avoid:**
- Keep SELinux enforcing during implementation and validation.
- Place OpenLDAP cert/key material in standard paths where possible and run `restorecon`; if using custom paths, manage `semanage fcontext` and `restorecon` in Ansible.
- Set NFS-related booleans deliberately:
  - on clients: `setsebool -P use_nfs_home_dirs on` so SSH/PAM can use NFS homes;
  - on the NFS server: use proper labels and only enable broader NFS export booleans if required by the chosen export path.
- Inspect denials with `ausearch -m AVC -ts recent` or `journalctl`, then encode the fix in Ansible.

**Warning signs:**
- “Works with `setenforce 0`” becomes the only known fix.
- `sshd` denies reading NFS-backed `authorized_keys` or home files.
- `slapd` logs certificate/key permission errors despite Unix mode appearing correct.
- Ansible has tasks disabling SELinux or setting permissive mode permanently.

**Phase to address:**
Phase 2 for slapd TLS; Phase 6 for NFS homes; recheck in Phase 5 SSH.

---

### Pitfall 10: Ansible LDAP tasks are not idempotent for ordered or mutable LDAP state

**What goes wrong:**
Every playbook run changes LDAP state, duplicates entries, regenerates password hashes/TOTP tokens, resets OTP replay protection, or fails with “Type or value exists.” Clean rebuilds diverge from manually fixed VMs.

**Why it happens:**
LDAP entries are stateful and some attributes are ordered (`olcAccess`) or mutable by overlays (`pwdHistory`, `pwdFailureTime`, `oathTOTPLastTimeStep`). `community.general.ldap_entry` only asserts entry existence; it does not update attributes on existing entries. Salted password hashes generated during each run also differ even for the same password.

**How to avoid:**
- Use `community.general.ldap_entry` for entry presence and `community.general.ldap_attrs` for attribute reconciliation.
- Use `state: exact` only for static desired attributes. Never exact-manage overlay runtime attributes.
- Use `ordered: true` for `olcAccess` and be explicit about X-ordered DNs.
- Generate password hashes and OTP secrets once from gitignored secrets, or update passwords only on explicit rotation. Do not run `slappasswd` with a new random salt on every converge unless the task is guarded by “create only.”
- Use `no_log: true` for bind passwords, TA password, hashes where appropriate, and TOTP secrets.
- Add a consecutive-run idempotency gate: second run should report no LDAP changes except expected service checks.

**Warning signs:**
- `ansible-playbook` reports LDAP changes on every run with unchanged variables.
- OTP codes can be reused after deployment because `oathTOTPLastTimeStep` was reset.
- User password hashes differ after each converge.
- OLC DNs gain new `{N}` prefixes after repeated runs.

**Phase to address:**
Phase 1 — role foundation; enforced in every phase.

---

### Pitfall 11: Mail LDAP is enabled before LDAP semantics are complete

**What goes wrong:**
Previously passing mail tests regress when `mail_ldap_enabled` flips. Local `admin`/`test` auth breaks, `mailta` cannot authenticate, Dovecot binds fail because the CA is missing, or mail accepts the wrong LDAP users because group filtering is incomplete.

**Why it happens:**
The existing mail role's LDAP template establishes an LDAPS/auth-bind seam, but it does not prove the final HW1-3 schema, CA trust, group restrictions, TOTP exceptions, and mailbox behavior. `mailta` is used for HW1-2 LDAP-related tests and should be in the `ta` group but should not be subject to TOTP per HW1-3.

**How to avoid:**
- Flip `mail_ldap_enabled` only after LDAP server, LDAPS CA trust, `mailta`, `ta` group membership, and Dovecot auth-bind are verified independently.
- Keep local mail users first and LDAP additive; local `admin`/`test` must continue to pass with LDAP enabled and disabled.
- Add a Dovecot LDAP filter that restricts mail LDAP users to intended `ta` identities. Be careful with RFC2307 `memberUid` vs RFC2307bis `member`/`memberOf`; do not use `memberOf` unless the overlay is actually configured.
- Ensure mail clients are not forced to append TOTP for `mailta`.
- Run mail Phase 03–06 regression plus LDAP-specific `mailta` auth/delivery after enabling.

**Warning signs:**
- `doveadm auth test mailta <TA_PASSWORD>` fails while direct `ldapwhoami` succeeds.
- `doveadm auth test admin admin` starts timing out against LDAP.
- Dovecot LDAP config uses LDAPS but no CA cert exists under `/etc/pki/ca-trust/source/anchors/ldap-ca.crt`.
- Non-`ta` LDAP users can authenticate to mail.

**Phase to address:**
Phase 7 — mail LDAP integration and full regression.

---

### Pitfall 12: Fortune schema imports but sorting/pagination still fail

**What goes wrong:**
Fortune entries can be added, but OJ sorting/pagination checks fail. Searches cannot sort by `author`, substring matching behaves case-sensitively, `id` sorts lexicographically instead of numerically, or server-side sort controls are unavailable.

**Why it happens:**
The custom `fortune` object class requires correct OLC schema definitions, not just LDIF data. `author` must use case-insensitive, space-insensitive equality/substr/ordering matching. `id` should be integer syntax with integer matching/ordering. The assignment also hints `slapo-sssvlv`; without that overlay, sorting with paged/VLV behavior can be missing or inefficient.

**How to avoid:**
- Define schema under `cn=schema,cn=config` with unique UUID-branch OIDs.
- Do not redefine standard `description`; use the RFC4519 attribute as required.
- Define custom attributes precisely:
  - `author`: Directory String syntax, `caseIgnoreMatch`, `caseIgnoreSubstringsMatch`, `caseIgnoreOrderingMatch`;
  - `id`: Integer syntax, `integerMatch`, `integerOrderingMatch`.
- Load `sssvlv` overlay on the LDAP database and set conservative limits for this small lab dataset.
- Verify controls and behavior, not just entry existence: sorted searches by author, substring searches, integer ordering, and paged results.

**Warning signs:**
- `ldapsearch -E sss=author ...` returns unavailable critical extension or ignores ordering.
- `id=10` sorts before `id=2`.
- Searching `author=*feynman*` fails when case differs.
- `cn=fortune,...` entries exist but `objectClass=fortune` is not listed in `cn=config` schema search.

**Phase to address:**
Phase 4 — custom schema, Fortune import, and sssvlv overlay.

---

### Pitfall 13: Cross-zone firewall rules become broad regressions

**What goes wrong:**
LDAP/NFS starts working, but prior HW1-0/HW1-1/HW1-2 checks fail because DMZ↔internal policies, VPN restrictions, masquerade behavior, or DNS forwarding paths changed. Alternatively, LDAP works from the server but workstations/mail cannot reach it.

**Why it happens:**
The easiest firewall fix is broad `ACCEPT` between zones. This repo intentionally uses named firewalld policies with priorities and narrow allowed ports. LDAP adds TCP/636; NFS adds TCP/2049 if NFSv4-only; mail LDAP adds another DMZ client of the same LDAP path.

**How to avoid:**
- Treat router policy as a contract. Add only explicit new flows:
  - DMZ workstations/mail → internal LDAP TCP/636;
  - DMZ workstations → internal NFS TCP/2049 if using NFSv4-only.
- Keep existing reject policies and priorities intact; new accepts must sort before the reject they intentionally bypass.
- Keep NetworkManager zone ownership on managed interfaces and reserve permanent firewalld bindings for non-NM interfaces such as `wg0`.
- Verify old DNS/mail/firewall checkpoints after adding LDAP paths.

**Warning signs:**
- `firewall_policies` loses `dmz-to-internal` REJECT or `vpn-to-lan` REJECT semantics.
- NFS requires stopping firewalld or allowing all DMZ→internal traffic.
- VPN can reach LDAP or SSH paths that should remain private.
- DNS or mail OJ tests fail after LDAP firewall changes.

**Phase to address:**
Phase 1 — topology/firewall/DNS; re-verify every phase.

---

### Pitfall 14: Required OpenLDAP overlays are not available in the AlmaLinux package set

**What goes wrong:**
The plan assumes `ppolicy.la`, `otp.la`, `sssvlv.la`, or `ppm.so` exists, but the target VM lacks the module. Implementation then stalls late in the milestone or falls back to non-equivalent PAM/client-side hacks.

**Why it happens:**
OpenLDAP documents official and contributed modules, but distributions differ in what they package. RHEL-family packaging also differs from Debian/Ubuntu tutorials. AlmaLinux may need additional repositories, module packages, or a controlled build for some contrib overlays.

**How to avoid:**
- Spike package/module availability in the first LDAP phase on the actual course AlmaLinux image.
- Record exact package names and module paths in role defaults, not inline tasks.
- Add an Ansible assert that checks for required module files before configuring overlays.
- If `ppm` or `otp` is not packaged, decide early whether to build a package, use a course-provided repo, or adjust the roadmap. Do not defer this until after the DIT is built.

**Warning signs:**
- `ldapmodify` returns “module not found” or “overlay not found.”
- `ls /usr/lib64/openldap/` lacks expected `.la` modules.
- Tutorials reference Debian paths that do not exist on AlmaLinux.
- TOTP implementation drifts toward workstation-local PAM because the LDAP overlay was not verified.

**Phase to address:**
Phase 0/1 — package feasibility spike before deep implementation.

---

## Technical Debt Patterns

Shortcuts that seem reasonable under deadline but create grading or recovery failures.

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Editing `/etc/openldap/slapd.d` files directly | Fast one-off config change | `slapd` startup failures, non-idempotent config, divergence from OLC | Never for final implementation |
| Broad DMZ→internal ACCEPT for LDAP/NFS | Makes clients connect quickly | Regresses firewall grading and exposes private services | Never; add narrow port/service policies |
| Using `ldap://` + StartTLS because tutorials do | Easier SSSD examples | Violates lab's LDAPS requirement and existing 636 firewall path | Only as a throwaway diagnostic, not final |
| Client-side `pam_oath` for TOTP | Avoids OpenLDAP OTP overlay setup | Breaks public-key exemption and duplicates secrets on workstations | Avoid unless OTP overlay is proven unavailable and the behavior is revalidated |
| `ldap_tls_reqcert = never` / disabled cert validation | Hides CA/SAN problems | Insecure final state; OJ-like clients may still fail | Only during diagnosis, immediately revert |
| Regenerating password hashes/TOTP secrets on every run | Simple templating | Idempotency failure, password drift, TOTP replay state reset | Never; use stable secrets and explicit rotation |
| Local sudoers rules for LDAP users | Makes `sudo` pass locally | Does not satisfy “use LDAP”; masks broken sudo-ldap | Only for bootstrap/admin break-glass users, not graded identities |
| `no_root_squash` NFS exports | Makes Ansible/client root writes easy | Client root can own/modify all homes; security and grading risk | Avoid; provision ownership server-side |
| Enabling ppolicy lockout | Looks production-like | OJ malicious/retry attempts can lock `generalta`; not required | Avoid unless explicitly required later |
| Exact-managing LDAP operational attributes | Makes LDIF look complete | Resets ppolicy/OTP runtime state and causes changed runs | Never |

## Integration Gotchas

Common mistakes when connecting LDAP to existing lab services.

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| LDAP ↔ BIND9 | Adding `ldap`, `workstation1`, `workstation2` records in only one view or with names not matching cert SANs | Add records through the existing BIND role data model and verify from OJ/VPN, DMZ, and internal paths |
| LDAP ↔ router firewalld | Replacing existing policy with broad zone accept | Preserve existing policies; add narrow DMZ→internal TCP/636 and NFS TCP/2049 if needed |
| slapd ↔ LDAPS certs | Self-signed cert installed but clients do not trust it | Generate/deploy CA/cert via Ansible; install CA trust on workstations and mail host; keep validation on |
| OpenLDAP ACL ↔ SSSD | ACLs allow bind but not attribute reads needed for NSS/group resolution | Permit authenticated/client reads of non-secret identity attrs (`uidNumber`, `gidNumber`, `cn`, `memberUid`, `homeDirectory`, `loginShell`, `sshPublicKey`) while protecting passwords and secrets |
| SSSD ↔ OpenSSH | SSSD has SSH keys cached but sshd never asks SSSD | Configure `AuthorizedKeysCommand /usr/bin/sss_ssh_authorizedkeys` and include SSSD `ssh` responder |
| SSSD ↔ host login policy | `stu` restricted by local client config only or not restricted at all | Store host/service access in LDAP attributes and configure SSSD access provider to consume them |
| sudo ↔ SSSD | `sudoers: ldap` used while SSSD is configured, or `sudoers: files` only | Use `sudoers: files sss`, `sudo_provider=ldap`, and `ldap_sudo_search_base=ou=SUDOers,<baseDN>` |
| NFS ↔ LDAP IDs | Homes owned by local users or wrong numeric IDs | Create homes using LDAP UID/GID numbers and verify `id`/`ls -ln` consistency on every host |
| NFS ↔ firewalld | NFSv3/random RPC ports blocked by router | Prefer NFSv4-only and allow TCP/2049 explicitly |
| NFS ↔ SELinux/SSH | SSH key auth fails only with NFS homes | Enable `use_nfs_home_dirs` and verify SELinux denials rather than disabling SELinux |
| LDAP ↔ mail role | `mail_ldap_enabled` flipped before `mailta`/CA/group filters are ready | Treat mail LDAP as final integration; run full mail regression after enabling |

## Performance Traps

Patterns that work in a small manual demo but fail under grading timing, retries, or repeated Ansible runs.

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| SSSD enumeration of all LDAP users/groups | Slow boot/login, noisy LDAP logs | Keep `enumerate = false`; verify direct `getent passwd user` and `id user` | OJ retries SSH/auth rapidly |
| Stale SSSD cache after ACL/group/sudo changes | Old login/sudo decisions persist | Use `sss_cache -E` in verification after LDAP changes; tune sudo refresh only if needed | Phase 5/7 validation |
| NFSv3 dynamic RPC ports | Mounts work with firewalld off only | Use NFSv4-only TCP/2049 or pin ports explicitly | NFS phase and reboot tests |
| Server-side sort over unindexed Fortune data | Sorting works for tiny samples but slows or times out | Add appropriate equality/substr/ordering indexes for searched Fortune attrs if dataset grows | Fortune import/search checks |
| OJ repeated bad auth locks account | `generalta` suddenly cannot bind | Do not configure ppolicy lockout unless required; provide admin unlock recovery | OJ malicious/retry tests |
| TOTP clock drift | Password+OTP fails intermittently | Enable time sync and use the required 60-second step/window deliberately | TOTP grading window |
| Rebuilding slapd config by restarting repeatedly | Transient auth outages during multi-role runs | Apply OLC changes idempotently; restart only when package/listener changes require it | Full `site.yml` converge |

## Security Mistakes

Domain-specific security issues beyond generic host hardening.

| Mistake | Risk | Prevention |
|---------|------|------------|
| Anonymous or broad authenticated read of `userPassword`, `oathSecret`, or bind secrets | Credential/TOTP seed exposure | Secret-specific ACLs before broad reads; test with non-admin binds |
| Granting `generalta` access to `cn=config` or using rootdn for graded user behavior | TA account can rewrite server config; ACL tests are bypassed | Use a separate admin/rootdn for automation; grant `generalta` only required DIT write privileges |
| Disabling LDAPS certificate validation | MITM risk and hidden cert/DNS mismatch | Install CA trust and keep validation hard/on |
| Committing `TA_PASSWORD`, password hashes tied to real secrets, TOTP seed, LDAP bind password, or private keys | Secret leak and forced rotation | Use gitignored `secrets.yml`; commit examples/placeholders only |
| Using `no_root_squash` for NFS homes | Client root owns all user homes | Keep `root_squash`; provision ownership on the NFS server |
| Broad VPN/DMZ access to LDAP/NFS | Private directory/home data exposed | Restrict router and host firewalls to exact source zones/ports/hosts |
| PAM-side TOTP secrets copied to every workstation | Secret sprawl and inconsistent auth behavior | Centralize TOTP validation in OpenLDAP OTP overlay |
| Local sudoers grants for LDAP groups | Bypasses LDAP audit/requirements | Keep graded sudo rules as LDAP `sudoRole` entries; local rules only for bootstrap admin |

## UX / Operator Pitfalls

Common operator-experience mistakes in this infrastructure project.

| Pitfall | Operator Impact | Better Approach |
|---------|-----------------|-----------------|
| No identity/auth test matrix | Debugging LDAP through SSH logs becomes slow under deadline | Maintain scripted checks for `ldapsearch`, `id`, `getent`, `sss_ssh_authorizedkeys`, SSH key/password/TOTP, `sudo -l`, NFS sync, and mail LDAP |
| Logging secrets while diagnosing binds | Password/TOTP leakage into Ansible output or journal | Use `no_log` for binds/secrets and log only usernames/DNs/result codes |
| Unclear ownership of `/u` homes | Ansible, PAM, and NFS fight over directories | Make the NFS server role own home creation; clients only mount/use homes |
| Manual LDAP fixes not captured | Clean rebuild fails even though current VM passes | Convert every successful manual `ldapmodify` into an idempotent task immediately |
| Reboot not tested until the end | `slapd`, NFS mounts, SSSD, or firewalld fail post-reboot | Add reboot validation before declaring each phase complete |

## "Looks Done But Isn't" Checklist

Things that appear complete but are missing critical graded behavior.

- [ ] **DNS:** `ldap`, `workstation1`, and `workstation2` resolve correctly from the grader-visible path and internal clients.
- [ ] **LDAPS:** `ldapsearch -H ldaps://ldap.{STUID}.nasa:636` works from both workstations with certificate validation enabled.
- [ ] **No StartTLS dependency:** Final clients do not require `ldap://` + `-ZZ` for graded behavior.
- [ ] **OLC:** `cn=config` contains expected modules, schemas, database, and overlays; no direct `slapd.d` edits are used.
- [ ] **ACL password protection:** `generalta` can change passwords but cannot read `userPassword`; normal users cannot read others' passwords.
- [ ] **ACL self-service:** Users can modify only their own `userPassword`, `loginShell`, and `sshPublicKey`.
- [ ] **ppolicy:** Password reuse is rejected; passwords under 8 chars are rejected; passwords with fewer than 3 character classes are rejected via user password-change flow.
- [ ] **TOTP:** `generalta` and `stu` require `<password><6-digit TOTP>` for password auth; `mailta` does not; public-key SSH does not ask for TOTP.
- [ ] **SSSD identity:** `getent passwd generalta`, `id generalta`, `getent group ta`, and `getent group stu` return correct UID/GID/group data on both workstations.
- [ ] **SSH keys:** `/usr/bin/sss_ssh_authorizedkeys generalta` returns the LDAP `sshPublicKey`; SSH key login works without password/TOTP.
- [ ] **Host access:** `stu` can log into `workstation1` but not `workstation2`; TA users can log into both.
- [ ] **sudo:** TA users can run all commands; `stu` can run only `ls` on `workstation1`; behavior comes from LDAP sudoRole data.
- [ ] **NFS homes:** `/u/ta/generalta`, `/u/ta/mailta`, and `/u/stu/stu` have exact permissions/ownership and are the same mounted filesystem on both workstations.
- [ ] **NFS sync:** A file created on one workstation appears on the other after normal filesystem sync, without manual copy.
- [ ] **SELinux:** All checks pass with SELinux enforcing; no permanent `setenforce 0` or permissive config exists.
- [ ] **Fortune:** Custom schema is visible in `cn=config`; Fortune searches support server-side sorting and pagination.
- [ ] **Mail LDAP:** With `mail_ldap_enabled: true`, `mailta` works for mail LDAP tests and local mail users still pass.
- [ ] **Idempotency:** A second Ansible run reports no unexpected LDAP changes; password/TOTP/operational state does not churn.
- [ ] **Reboot:** Router, LDAP server, workstations, NFS mounts, SSSD, and mail LDAP behavior survive reboot.

## Recovery Strategies

When pitfalls occur despite prevention, how to recover.

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Broken `olcAccess` locks out normal binds | MEDIUM | Use local `ldapi:///` SASL EXTERNAL/root access, replace the full ordered `olcAccess` list, then rerun ACL tests as users |
| `slapd` will not start after config edits | HIGH | Stop editing files; restore last known-good `slapd.d`/backup, validate with `slaptest`, reapply changes through LDAP operations |
| LDAPS cert mismatch | LOW-MEDIUM | Regenerate cert with correct SAN, deploy CA to clients/mail, `restorecon`, restart slapd/SSSD/Dovecot, test with `openssl s_client` |
| ppolicy not enforcing | MEDIUM | Verify overlay/default policy DN, install/check quality module, test with user `ldappasswd`; avoid rootdn test path |
| TOTP broken | MEDIUM-HIGH | Verify `otp` overlay/module, token/params DNs, raw secret encoding, time sync, and SSH auth path; remove accidental `pam_oath`/forced AuthenticationMethods |
| SSSD cache lies | LOW | `sss_cache -E`, restart SSSD, retest with `getent`, `id`, `sss_ssh_authorizedkeys`, then fix underlying LDAP/SSSD config |
| sudo LDAP stale/wrong | LOW-MEDIUM | Clear SSSD sudo cache, verify `nsswitch.conf`, `sudo_provider`, search base, and `sudoRole` attrs with `sudo -l -U` |
| NFS homes local or unsynced | MEDIUM | Unmount, remove accidental local homes only after backup, fix router/host firewalls and fstab/autofs, mount NFS, restore ownership server-side |
| SELinux denial | LOW-MEDIUM | Reproduce with enforcing, inspect AVCs, add boolean/fcontext/restorecon task, never keep permissive as final state |
| Mail LDAP regression | MEDIUM | Set `mail_ldap_enabled: false` to restore local baseline, fix LDAP CA/user/group/filter, then re-enable and run full mail regression |

## Pitfall-to-Phase Mapping

How roadmap phases should address these pitfalls.

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| OpenLDAP ACL ordering/privileges | Phase 3 — DIT/users/groups/ACLs | User-bound `ldapsearch`/`ldapmodify` matrix for passwords, self attrs, groups, and secrets |
| Unsafe OLC/file edits | Phase 2 — slapd/OLC foundation | `ldapsearch -Y EXTERNAL -H ldapi:/// -b cn=config`; `slaptest`; second Ansible run clean |
| LDAPS vs StartTLS | Phase 1/2 — DNS/firewall/LDAPS | LDAPS from workstations and mail with cert validation; no 389 dependency |
| ppolicy enforcement gaps | Phase 4 — overlays | User password-change tests for reuse/min length/3 classes |
| TOTP/PAM/SSH mismatch | Phase 4/5 — OTP + client auth | Password+TOTP succeeds only for target users; publickey succeeds without TOTP |
| SSSD SSH/access mistakes | Phase 5 — workstation clients | `getent`, `id`, `sss_ssh_authorizedkeys`, SSH matrix across both workstations |
| sudo-ldap mistakes | Phase 5 — sudo integration | `sudo -l -U` and positive/negative command execution tests as `generalta`/`stu` |
| NFS sync/firewall failures | Phase 6 — homes | NFS mount after reboot; cross-workstation file visibility; router policy diff reviewed |
| SELinux interference | Phase 2/5/6 | All LDAP/SSH/NFS tests pass with enforcing; no permissive tasks |
| Ansible LDAP non-idempotency | Phase 1 and all phases | Consecutive playbook run idempotency; no secret/hash/OTP churn |
| Mail LDAP regression | Phase 7 — mail integration | Local mail regression + `mailta` LDAP auth/delivery through Dovecot |
| Fortune/sssvlv failures | Phase 4 — schema/import/search | Sorted and paged `ldapsearch` checks for Fortune entries |
| Cross-zone firewall regression | Phase 1 and all phases | Existing HW1-0/HW1-1/HW1-2 checks plus LDAP/NFS reachability from OJ-like paths |
| Overlay package availability | Phase 0/1 spike | Assert module files/packages exist on AlmaLinux target before overlay tasks |

## Sources

- [HIGH] `.planning/PROJECT.md` — current LDAP milestone scope, topology, constraints, existing mail LDAP seam, and router LDAPS policy context.
- [HIGH] `lab/ldap.md` — HW1-3 assignment requirements for LDAPS, OUs, users/groups, ACLs, ppolicy, TOTP, Fortune, clients, NFS homes, and OJ account usage.
- [HIGH] Repository files read 2026-05-28: `ansible/inventory/host_vars/router-01/main.yml` (existing `dmz-to-internal-ldaps` policy), `ansible/playbooks/roles/mail/templates/dovecot/dovecot-ldap.conf.ext.j2`, `ansible/playbooks/roles/mail/tasks/ldap_ca_cert.yml`, and mail role defaults/assertions for `mail_ldap_enabled`.
- [HIGH] OpenLDAP 2.6 Administrator Guide — Access Control: https://www.openldap.org/doc/admin26/access-control.html. Verified ACL ordering, first-match behavior, cumulative access levels, `olcAccess`, `userPassword` examples, and rootdn bypass.
- [HIGH] OpenLDAP 2.6 Administrator Guide — Configuring slapd: https://www.openldap.org/doc/admin26/slapdconf2.html. Verified `slapd-config`/OLC layout and warning not to edit LDIF files directly.
- [HIGH] OpenLDAP 2.6 Administrator Guide — Schema Specification: https://www.openldap.org/doc/admin26/schema.html. Verified custom schema/OID guidance and case-insensitive/space-insensitive matching rules.
- [HIGH] OpenLDAP man pages: `slapo-ppolicy(5)`, `slapo-otp(5)`, `slapo-sssvlv(5)`, and `slapd-config(5)` via https://www.openldap.org/software/man.cgi. Verified ppolicy attributes/history caveats, OTP password+code bind behavior and OATH attrs, sssvlv sorting/paged/VLV behavior, and config backend structure.
- [MEDIUM-HIGH] OpenLDAP `ppm` contrib module docs from official repository: https://github.com/openldap/openldap/blob/master/contrib/slapd-modules/ppm/ppm.md. Verified character-class quality module behavior and OpenLDAP 2.6 configuration notes; package availability still requires AlmaLinux validation.
- [HIGH] Red Hat RHEL 9 docs discovered via Tavily — SSSD LDAP with TLS: https://docs.redhat.com/en/documentation/red_hat_enterprise_linux/9/html/configuring_authentication_and_authorization_in_rhel/configuring-sssd-to-use-ldap-and-require-tls-authentication_configuring-authentication-and-authorization-in-rhel. Verified RHEL package/authselect/SSSD TLS/0600 guidance.
- [MEDIUM-HIGH] SSSD man pages via ManKier (`sssd-ldap`, `sssd-ldap-attributes`, `sssd-sudo`, `sss_ssh_authorizedkeys`). Verified LDAPS requirement for auth provider, access filter/host behavior, SSH key attribute mapping, sudo provider/search base, and SSSD authorized keys command.
- [HIGH] OpenSSH `sshd_config(5)` via OpenBSD/man7: https://man.openbsd.org/sshd_config and https://man7.org/linux/man-pages/man5/sshd_config.5.html. Verified `AuthenticationMethods`, `KbdInteractiveAuthentication`, `UsePAM`, and `AuthorizedKeysCommand` behavior.
- [HIGH] sudo official `sudoers.ldap` manual: https://www.sudo.ws/docs/man/sudoers.ldap.man/. Verified `sudoRole`, `sudoUser`, `sudoHost`, `sudoCommand`, `sudoOrder`, nsswitch behavior, and SSSD integration note.
- [MEDIUM-HIGH] Red Hat NFS docs discovered/extracted via Tavily — RHEL 9 search snippets plus current RHEL network file services pages. Verified `/etc/exports` syntax, export option spacing pitfall, root_squash default, NFSv4 firewall simplification, and firewalld services/ports; validate exact AlmaLinux 9 package/service defaults during implementation.
- [MEDIUM] Red Hat SELinux/NFS boolean docs and community confirmations. Verified `use_nfs_home_dirs` purpose; exact AlmaLinux policy behavior should be tested with AVC logs on target VMs.
- [HIGH] Ansible community.general LDAP module docs: `ldap_entry`, `ldap_attrs`, and `ldap_search` at https://docs.ansible.com/ansible/latest/collections/community/general/. Verified `ldap_entry` only asserts entry existence, `ldap_attrs state=exact`, `ordered`, `xorder_discovery`, LDAPS/TLS options, and check-mode support.

---
*Pitfalls research for: HW1-3 LDAP service automation added to existing NASA Labs infrastructure*  
*Researched: 2026-05-28*
