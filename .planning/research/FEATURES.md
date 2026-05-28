# Feature Research

**Domain:** HW1-3 LDAP service automation for NASA Labs on AlmaLinux/OpenLDAP/SSSD  
**Researched:** 2026-05-28  
**Confidence:** HIGH for assignment behavior and OpenLDAP/SSSD semantics; MEDIUM for exact AlmaLinux package/module availability of optional OpenLDAP password-quality and OTP modules

## Feature Landscape

This milestone is a graded LDAP behavior contract, not a generic enterprise identity-platform build. The safest product shape is: **one OpenLDAP server in the private zone, LDAPS-only client access from the DMZ workstations, SSSD-based Unix identity/auth on clients, sudo rules stored in LDAP, and NFS-mounted homes shared by all LDAP clients**.

The feature categories below map directly to the HW1-3 grading sections. Features marked P1 are required for passing; “differentiators” are reliability tools that reduce grading risk but are not separate assignment requirements.

### Table Stakes (OJ-Graded / Non-Negotiable)

| Grading Section | Feature | Expected Behavior | Complexity | Dependencies / Notes |
|-----------------|---------|-------------------|------------|----------------------|
| Basic Configuration | DNS + topology for `ldap`, `workstation1`, `workstation2` | `ldap.{STUID}.nasa` resolves to the private-zone LDAP server; `workstation1` and `workstation2` resolve to DMZ clients; clients can reach LDAP over TCP/636 | MEDIUM | Existing BIND9 split-view DNS, router DMZ→private LDAPS policy, new workstation VM inventory/cloud-init |
| Basic Configuration | LDAPS-only OpenLDAP endpoint | LDAP authentication/searches use `ldaps://ldap.{STUID}.nasa:636`; do **not** rely on StartTLS over 389; clients trust the self-signed CA/cert | HIGH | OpenLDAP TLS config, self-signed cert/key, SSSD `ldap_uri = ldaps://...`, firewall 636/tcp |
| Organizational Unit Naming | Required DIT containers | Base DN is `dc={STUID},dc=nasa`; required OUs exist exactly: `ou=People`, `ou=Group`, `ou=Ppolicy`, `ou=SUDOers`, `ou=Fortune` | LOW | Base database initialized before users/groups/overlays reference these DNs |
| PosixGroup | `ta` and `stu` groups | `cn=ta,ou=Group,...` is `posixGroup` with `gidNumber: 10000`; `cn=stu,ou=Group,...` is `posixGroup` with `gidNumber: 20000`; `memberUid` lists the assigned users | MEDIUM | SSSD rfc2307 group lookup; user entries must have matching primary/supplemental groups |
| PosixGroup | Workstation login authorization | `ta` users can SSH to both workstations; `stu` can SSH to `workstation1` only and is denied on `workstation2` | MEDIUM | Prefer SSSD `access_provider = simple` with `simple_allow_groups = ta,stu` on workstation1 and `ta` on workstation2; depends on LDAP group resolution |
| PosixGroup | LDAP-backed sudo authorization | `ta` can run all sudo commands on all workstations; `stu` can run only `ls` on workstation1 | HIGH | Sudo LDAP schema/rules under `ou=SUDOers`; SSSD sudo provider or sudo LDAP backend; exact hostname/path matching matters |
| People | Required users | `generalta` UID 10000 and `mailta` UID 10001 are in `ta`; `stu` UID 20000 is in `stu`; all have `homeDirectory`, `mail`, hashed `userPassword`, and the required SSH public key | MEDIUM | LDAP schemas: core/cosine/inetorgperson/nis plus OpenSSH `ldapPublicKey` schema or equivalent `sshPublicKey` definition |
| Access Control | Admin write delegation without password read | `generalta` and `mailta` can manage LDAP users/groups, including password writes; they must **not** read any `userPassword`, including other users’ passwords | HIGH | OpenLDAP `olcAccess` ordering and exact privilege masks; do not make these users `rootdn` because rootdn bypasses ACLs |
| Access Control | Self-service attributes | Users can modify only their own `userPassword`, `loginShell`, and `sshPublicKey`; all other attributes are read-only to ordinary users | HIGH | Specific ACLs for attributes before broad read rules; separate write targets for `attrs=userPassword`, `attrs=loginShell,sshPublicKey`, and general reads |
| Access Control | Password search protection | Authenticated users can search/read normal user attributes but can only authenticate/write their own password; `userPassword` is hidden from broad read/search results | HIGH | `userPassword` ACL must precede `to * by users read`; use `auth`/`=xw`/`=w`, not broad `write`/`read` levels |
| Access Control | NFS-backed shared home directories | `/u/ta` and `/u/stu` are mounted on both workstations; per-user dirs have mode `711` and owner/group `{name}:ta` or `{name}:stu`; file changes are visible from both clients | HIGH | NFS server/export, client mounts, UID/GID consistency via LDAP, DMZ→private NFS firewall path; prefer NFSv4-only to minimize ports |
| Password Policy | No password reuse | LDAP rejects a user password change that reuses the previous password | MEDIUM | OpenLDAP `ppolicy` overlay, policy object under `ou=Ppolicy`, `pwdInHistory >= 1`; rootdn modifications bypass history checks |
| Password Policy | Minimum length and character classes | LDAP rejects new passwords under 8 bytes/chars and passwords that do not include at least 3 of upper/lower/digit/special classes | HIGH | Built-in `pwdMinLength: 8` requires `pwdCheckQuality`; 3-class checking requires an OpenLDAP password-check module such as `ppm` or custom `ppolicy_check_module` |
| TOTP | Password+TOTP for `generalta` and `stu` | Password-based SSH/LDAP bind succeeds only when the user enters `<password><current 6-digit TOTP>`; wrong/missing/replayed TOTP fails | HIGH | Prefer OpenLDAP `slapo-otp`/OATH overlay so LDAP simple bind verifies appended OTP server-side; SSSD/PAM passes the password string to LDAP |
| TOTP | SSH public key exemption | SSH key login for `generalta` and `stu` succeeds without TOTP prompt; password login still requires TOTP | HIGH | OpenSSH must not set `AuthenticationMethods` that force keyboard-interactive after successful publickey; `UsePAM yes` still runs account/session via SSSD |
| Fortune | Custom `fortune` objectClass via OLC | `cn=config` contains a custom schema under the UUID OID branch; objectClass `fortune` extends `top` and supports `author`, `id`, and RFC4519 `description` | HIGH | OLC schema entry under `cn=schema,cn=config`; `author` matching rules should be `caseIgnoreMatch`, `caseIgnoreSubstringsMatch`, `caseIgnoreOrderingMatch`; `id` uses integer syntax |
| Fortune | YAML import into LDAP | Fortunes from the provided YAML are imported as LDAP entries under `ou=Fortune`; each has deterministic DN/cn, integer `id`, `author`, and `description` | MEDIUM | YAML parsing/import role task; schema must exist before data import |
| Fortune | Server-side sorting + pagination | LDAP search controls for server-side sort and paged results work against Fortune entries | MEDIUM | Enable `slapo-sssvlv`; indexes on `id`, `author`, and `objectClass` are useful for grading/performance |
| LDAP Client | SSSD NSS/PAM/SSH integration | `getent passwd`, `id`, password SSH, and SSH public key auth all work for LDAP users on allowed workstations | HIGH | `sssd`, `pam_sss`, `nsswitch`, `sshd` `AuthorizedKeysCommand /usr/bin/sss_ssh_authorizedkeys`, LDAPS trust, SSSD cache invalidation after changes |
| Mail dependency | `mailta` LDAP identity unblocks HW1-2 LDAP tests | Existing mail role can enable LDAP lookup for `ta` users once LDAP is stable; `mailta` exists with mail address `mailta@{STUID}.nasa` | MEDIUM | Existing Dovecot/Postfix LDAP scaffolding; do after core HW1-3 identity works |

## Expected Behavior by Grading Section

### 1. Basic Configuration

Use **OpenLDAP with dynamic configuration (`cn=config`) and LDAPS on 636**. The assignment explicitly says “LDAPS” and “not StartTLS,” so clients should be configured with `ldaps://ldap.{STUID}.nasa` rather than `ldap://...` plus StartTLS. SSSD also documents that LDAP authentication requires TLS/SSL or LDAPS; using LDAPS aligns both the spec and SSSD.

Expected checks:

- `ldapsearch -H ldaps://ldap.{STUID}.nasa -b dc={STUID},dc=nasa ...` succeeds from both workstations.
- Plain LDAP/389 is not the primary client path; do not build grading around StartTLS.
- The self-signed CA or server cert is distributed to clients so SSSD can verify or intentionally trust it.
- Existing DNS, router NAT/firewalld, WireGuard, mail, and DNSSEC behavior must not regress.

### 2. Organizational Unit Naming

Create the required OUs before all dependent entries:

```text
dc={STUID},dc=nasa
├── ou=People
├── ou=Group
├── ou=Ppolicy
├── ou=SUDOers
└── ou=Fortune
```

Treat these names as grader-visible. Do not substitute `ou=Users`, `ou=Groups`, `ou=Policies`, or lowercase variants unless tests prove the grader is case-insensitive for DNs.

### 3. PosixGroup, Login Authorization, and Sudo

Use **rfc2307-style `posixGroup` with `memberUid`** because the spec says `posixGroup` and provides numeric GIDs. This lets SSSD default mappings work cleanly:

```ldif
dn: cn=ta,ou=Group,dc={STUID},dc=nasa
objectClass: top
objectClass: posixGroup
cn: ta
gidNumber: 10000
memberUid: generalta
memberUid: mailta

dn: cn=stu,ou=Group,dc={STUID},dc=nasa
objectClass: top
objectClass: posixGroup
cn: stu
gidNumber: 20000
memberUid: stu
```

For login authorization, prefer **SSSD simple access provider** over complicated LDAP filters, because the policy is group-based and differs by workstation:

- workstation1: `simple_allow_groups = ta, stu`
- workstation2: `simple_allow_groups = ta`

This still uses LDAP groups through SSSD, but avoids relying on `memberOf` overlays that rfc2307 `posixGroup/memberUid` does not provide by default.

For sudo, prefer **SSSD sudo provider + sudoRole entries in LDAP** because the clients already need SSSD for NSS/PAM/SSH. Configure `sudoers: files sss`, SSSD `sudo_provider = ldap`, and `ldap_sudo_search_base = ou=SUDOers,dc={STUID},dc=nasa`.

Expected sudoRole shape:

```ldif
dn: cn=ta-all,ou=SUDOers,dc={STUID},dc=nasa
objectClass: top
objectClass: sudoRole
cn: ta-all
sudoUser: %ta
sudoHost: ALL
sudoCommand: ALL
sudoRunAsUser: ALL

dn: cn=stu-ls-workstation1,ou=SUDOers,dc={STUID},dc=nasa
objectClass: top
objectClass: sudoRole
cn: stu-ls-workstation1
sudoUser: %stu
sudoHost: workstation1
sudoHost: workstation1.{STUID}.nasa
sudoCommand: /usr/bin/ls
sudoCommand: /bin/ls
sudoRunAsUser: ALL
```

Include both `/usr/bin/ls` and `/bin/ls` unless local validation proves only one path is needed. Sudo command matching is path-sensitive.

### 4. People

Each user should be a normal Unix identity resolvable by NSS:

| User | DN | UID | Primary GID | Home | Group | TOTP? | Notes |
|------|----|-----|-------------|------|-------|-------|-------|
| `generalta` | `uid=generalta,ou=People,...` | 10000 | 10000 | `/u/ta/generalta` | `ta` | Yes | OJ primary test account; admin write delegation |
| `mailta` | `uid=mailta,ou=People,...` | 10001 | 10000 | `/u/ta/mailta` | `ta` | No per spec | Used by HW1-2 LDAP mail tests; admin write delegation |
| `stu` | `uid=stu,ou=People,...` | 20000 | 20000 | `/u/stu/stu` | `stu` | Yes | workstation1 only; sudo `ls` only |

Recommended user objectClasses: `inetOrgPerson`, `posixAccount`, `shadowAccount` if needed by clients, and `ldapPublicKey` for `sshPublicKey`. Store the assignment-provided public key exactly. Initial `userPassword` should be hashed; future user password changes should go through LDAP password modify/SSSD so ppolicy can inspect cleartext quality before storage.

### 5. Access Control: OpenLDAP ACL Syntax and Ordering

OpenLDAP ACLs are ordered. The server checks `olcAccess` values in numeric order (`{0}`, `{1}`, ...), stops at the first matching `to <what>` and first matching `by <who>` unless `continue`/`break` says otherwise, and implicitly appends `by * none stop` and `access to * by * none`. Therefore, **specific password/self-service rules must appear before broad read rules**.

Critical rule behavior:

- `write` access level implies lower read/search/compare privileges. Do **not** grant password administrators `write` level on `userPassword` if they must not read passwords.
- Use explicit privilege masks such as `=w` or `=xw` for password attributes.
- Do **not** set `generalta` or `mailta` as database `rootdn`; `rootdn` bypasses ACLs and can always read/write everything.

Expected ACL intent, expressed as behavior rather than final syntax:

```text
1. userPassword:
   - self: exact auth+write (`=xw`) for own password changes/binds
   - anonymous: `auth` only if anonymous simple bind auth is required
   - generalta/mailta: exact write (`=w`) but no read/search/compare
   - everyone else: none

2. loginShell, sshPublicKey:
   - self: write own values
   - generalta/mailta: write user/group management target entries
   - authenticated users: read/search as appropriate

3. People/Group management:
   - generalta/mailta: write to user/group subtrees and children
   - ordinary users: read/search normal attrs only

4. Catch-all:
   - authenticated users: read/search normal directory data
   - anonymous: minimal/no read unless required for bind discovery
```

Validation should include positive and negative `ldapsearch`/`ldapmodify` cases: `generalta` can reset `stu`’s password but cannot read it; `stu` can change own `loginShell` and `sshPublicKey` but cannot change `mail`, `uidNumber`, or another user’s key.

### 6. Home Directory Mounting and NFS Sync

Use **NFS shared homes** rather than per-client local home creation, because the spec requires consistent synchronization across all machines. The simplest architecture is an NFS export hosted on the LDAP/private server (or a private-zone fileserver if later separated) mounted on both workstations.

Expected filesystem state:

```text
/u/ta                 root:root 0755
/u/ta/generalta       generalta:ta 0711
/u/ta/mailta          mailta:ta    0711
/u/stu                root:root 0755
/u/stu/stu            stu:stu      0711
```

Recommended NFS stance:

- Prefer NFSv4-only (`2049/tcp`) to reduce router/firewalld complexity.
- Export read/write with `sync` and default `root_squash`; do not use `no_root_squash` for home directories unless a test proves it is required.
- Mount with `_netdev`/systemd ordering so boot does not race network availability.
- Ensure SSSD identity is available before ownership-sensitive login/session steps.
- Add DMZ→private firewall allowance for NFS, not just LDAPS.

Expected validation: create a file as `generalta` on workstation1 under `/u/ta/generalta`; observe the same file with same UID/GID ownership on workstation2.

### 7. Password Policy Overlay

Use **OpenLDAP `ppolicy` overlay** with a default policy object under `ou=Ppolicy`. Built-in ppolicy supports history and minimum length when syntax checking can inspect the password.

Expected policy behavior:

```ldif
pwdAttribute: userPassword
pwdInHistory: 1          # or higher; prevents immediate previous-password reuse
pwdMinLength: 8
pwdCheckQuality: 2       # reject if quality cannot be checked
pwdAllowUserChange: TRUE
```

The “3 character classes” requirement is not satisfied by `pwdMinLength` alone. It needs an OpenLDAP password quality module (`ppolicy_check_module`) such as OpenLDAP’s `ppm` contrib module or an equivalent custom checker, with `pwdUseCheckModule: TRUE` and module arguments that enforce at least 3 of uppercase/lowercase/digit/special.

Important edge cases:

- If clients send already-hashed passwords, ppolicy may be unable to check length/classes; with `pwdCheckQuality: 2`, those changes should be rejected.
- `rootdn` modifications bypass history checks. Use normal LDAP password modify paths for validation.
- If using `ppolicy_hash_cleartext`, deny compare/search/read on `userPassword` to all normal users.

### 8. TOTP / OATH Overlay and PAM Integration

Use **OpenLDAP `slapo-otp`** if available in the installed OpenLDAP build. It is the cleanest match to the assignment because it stores OATH attributes in LDAP and verifies password+TOTP during LDAP simple bind.

Expected server-side TOTP behavior:

- Users with `oathOTPUser`/`oathTOTPUser`-derived objectClasses are subject to OTP.
- The user enters normal password followed immediately by the current TOTP code, e.g. `secret123456`.
- The OTP token entry stores `oathSecret` as raw bytes (base64 in LDIF using `::`).
- TOTP params set `oathOTPLength: 6`, `oathTOTPTimeStepPeriod: 60`, and SHA-1 HMAC (`oathHMACAlgorithm: 1.2.840.113549.2.7` for HMAC-SHA1).
- `oathTOTPLastTimeStep` prevents replay of a code already accepted in the same/previous time step.

Expected PAM/SSH behavior:

- Password SSH login goes through OpenSSH → PAM → `pam_sss` → SSSD LDAP auth → OpenLDAP simple bind; the combined password+OTP string reaches the OTP overlay.
- SSH public key login uses `sss_ssh_authorizedkeys` for the key and does not invoke password authentication, so it is exempt from TOTP.
- Keep `UsePAM yes` for account/session checks, but do not force `keyboard-interactive` after publickey for these users.

Avoid a `pam_oath`-only local `/etc/users.oath` design as the primary implementation. It can validate TOTP at PAM, but it makes LDAP no longer the source of truth for OATH attributes unless extra sync logic is built. Use it only as a contingency if the OpenLDAP OTP overlay is unavailable, and flag it for validation.

### 9. Fortune Custom Schema, Import, Sorting, and Pagination

Use **OLC (`cn=config`) schema customization**, not slapd.conf-only schema files. Add one schema entry under `cn=schema,cn=config` with UUID-branch OIDs. The UUID branch is `2.25.<uuid-as-decimal>`; reserve child arcs under it for this lab, for example:

```text
2.25.<uuid-decimal>.1  author attribute
2.25.<uuid-decimal>.2  id attribute
2.25.<uuid-decimal>.3  fortune objectClass
```

Recommended attribute/objectClass semantics:

```ldif
olcAttributeTypes: ( 2.25.<uuid>.1 NAME 'author'
  EQUALITY caseIgnoreMatch
  ORDERING caseIgnoreOrderingMatch
  SUBSTR caseIgnoreSubstringsMatch
  SYNTAX 1.3.6.1.4.1.1466.115.121.1.15 )

olcAttributeTypes: ( 2.25.<uuid>.2 NAME 'id'
  EQUALITY integerMatch
  ORDERING integerOrderingMatch
  SYNTAX 1.3.6.1.4.1.1466.115.121.1.27
  SINGLE-VALUE )

olcObjectClasses: ( 2.25.<uuid>.3 NAME 'fortune'
  SUP top STRUCTURAL
  MUST ( cn $ author $ id )
  MAY ( description ) )
```

`description` should be the existing RFC4519 attribute, not a new custom attribute. Import YAML entries deterministically under `ou=Fortune`, e.g. `cn=fortune-106,ou=Fortune,...`, with `id: 106`, `author`, and folded/multiline `description` preserved as LDAP LDIF values.

Enable **`slapo-sssvlv`** because the spec explicitly hints it for server-side sorting and pagination. It implements server-side sort and virtual list view and replaces paged results handling so paging works with sorting. Validate with searches sorted by `id` and `author` plus paged results.

### 10. LDAP Client: SSSD for NSS, PAM, SSH Keys, and Sudo

Use **SSSD as the client integration boundary**. It provides NSS (`getent`, `id`), PAM password auth (`pam_sss`), SSH public key lookup (`sss_ssh_authorizedkeys`), cached identity, and sudo-rule retrieval.

Expected client configuration behavior:

```ini
[sssd]
services = nss, pam, ssh, sudo
domains = nasa

[domain/nasa]
id_provider = ldap
auth_provider = ldap
chpass_provider = ldap
access_provider = simple
sudo_provider = ldap
ldap_uri = ldaps://ldap.{STUID}.nasa
ldap_search_base = dc={STUID},dc=nasa
ldap_user_search_base = ou=People,dc={STUID},dc=nasa
ldap_group_search_base = ou=Group,dc={STUID},dc=nasa
ldap_sudo_search_base = ou=SUDOers,dc={STUID},dc=nasa
ldap_schema = rfc2307
ldap_user_ssh_public_key = sshPublicKey
ldap_tls_reqcert = demand
ldap_tls_cacert = /path/to/lab-ca.crt
```

Expected SSH behavior:

```text
AuthorizedKeysCommand /usr/bin/sss_ssh_authorizedkeys
AuthorizedKeysCommandUser nobody
UsePAM yes
```

SSSD defaults already map `ldap_user_ssh_public_key` to `sshPublicKey`, but set it explicitly to avoid schema ambiguity. After changing LDAP groups, keys, sudoRole entries, or access policies, invalidate SSSD caches during validation (`sss_cache` or service restart) so stale denies/allows do not masquerade as server failures.

## Differentiators (Reliability, Not Extra Grading Scope)

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Protocol-level LDAP smoke tests | Converts OJ behavior into local checks | MEDIUM | Test LDAPS bind/search, ACL positives/negatives, ppolicy rejection, TOTP password+code, SSH key auth, password auth, sudo matrix, NFS sync, Fortune sort/page |
| ACL regression harness using `slapacl`/live binds | Prevents silent over-permissive ACLs | MEDIUM | Especially important for “admin can write but not read passwords”; validate with binds as `generalta`, `mailta`, `stu`, anonymous, and root/admin |
| OLC schema/overlay idempotency checks | Avoids duplicate schema and overlay entries on reruns | MEDIUM | Search `cn=config` before adding; use stable schema CN/OIDs; use Ansible LDAP modules or guarded `ldapmodify` |
| NFSv4-only export design | Minimizes firewall complexity | MEDIUM | Prefer one 2049/tcp policy over NFSv3 rpcbind/mountd port sprawl; still validate Alma/OpenLDAP VM support |
| SSSD cache reset in verification | Removes stale-cache false negatives | LOW | Run after LDAP data changes before SSH/sudo tests |
| Secret-shape validation | Prevents OJ secret encoding mistakes | LOW | Verify TA password hash, raw/base32/base64 TOTP secret conversions, and no real secrets in tracked vars |
| Mail LDAP activation gate | Unblocks HW1-2 LDAP tests only after identity works | LOW | Flip `mail_ldap_enabled` after `mailta` can bind and is in `ta`; avoid breaking existing local mail tests |

## Anti-Features (Explicitly Do Not Build)

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| StartTLS-on-389 as the primary LDAP path | Common LDAP TLS pattern | HW1-3 explicitly says LDAPS, not StartTLS; SSSD client behavior and firewall tests may target 636 | Use `ldaps://...:636` and distribute self-signed CA/cert |
| Making `generalta`/`mailta` the database `rootdn` | Easiest way to make admin writes work | `rootdn` can always read/write everything, violating password read protection | Keep a separate deployment/admin DN; delegate with ACLs using exact privilege masks |
| Broad `to * by users write` ACL | Makes self-modification and admin operations pass quickly | Lets users change UID/GID/group/mail/sudo/OTP/Fortune data and likely fails malicious OJ actions | Specific `attrs=` ACLs for self-service; subtree write only for delegated admins |
| Local `/etc/sudoers.d` rules for `ta`/`stu` | Faster than sudo LDAP | Spec says use LDAP including sudo rules; local files can drift across workstations | Store `sudoRole` entries under `ou=SUDOers`; fetch through SSSD sudo or sudo LDAP |
| Local Unix accounts for LDAP users on each workstation | Makes SSH/NFS ownership easier initially | Bypasses LDAP identity checks and can hide SSSD failures; UID/GID drift breaks NFS sync | Resolve users through SSSD/NSS from LDAP; use numeric ownership where needed during bootstrap |
| Per-workstation local home directories | Avoids NFS setup | Violates synchronization requirement; files differ between workstations | Shared NFS export mounted at `/u/ta` and `/u/stu` |
| `pam_oath` local usersfile as primary TOTP source | Familiar PAM TOTP setup | TOTP secret/policy not enforced by LDAP bind; duplicates secrets outside LDAP | Use OpenLDAP `slapo-otp`; reserve `pam_oath` as contingency only |
| `no_root_squash` NFS home exports | Avoids root permission surprises | Lets client root act as server root over home data; unnecessary for normal user homes | Use default `root_squash`, correct UID/GID, and explicit directory ownership |
| FreeIPA/389DS migration | Full-featured identity stack | Out of scope; assignment targets OpenLDAP/OLC customization and current project is OpenLDAP | Implement the required OpenLDAP features directly |
| LDAP replication/HA | Production resilience | Not graded and adds major schema/ppolicy/OTP/NFS state complexity | Single LDAP/NFS server with reboot persistence |

## Feature Dependencies

```text
[Existing DNS/router/firewalld]
    ├──requires──> [DNS records: ldap, workstation1, workstation2]
    ├──requires──> [DMZ→private LDAPS 636/tcp]
    └──requires──> [DMZ→private NFS path]

[OpenLDAP base server + LDAPS]
    ├──requires──> [Base DN dc={STUID},dc=nasa]
    ├──requires──> [OU: People, Group, Ppolicy, SUDOers, Fortune]
    ├──enables──> [Users/groups]
    ├──enables──> [ACLs]
    ├──enables──> [ppolicy overlay]
    ├──enables──> [slapo-otp TOTP]
    └──enables──> [Fortune OLC schema]

[Users/groups]
    ├──enables──> [SSSD NSS/PAM identity]
    ├──enables──> [SSH password auth]
    ├──enables──> [SSH public key lookup]
    ├──enables──> [NFS home ownership]
    ├──enables──> [sudoRole group rules]
    └──enables──> [mailta mail LDAP integration]

[ACLs]
    ├──must precede validation of──> [admin delegation]
    ├──must precede validation of──> [self-service changes]
    └──must protect──> [userPassword + oathSecret]

[ppolicy schema/overlay]
    └──enables──> [password reuse/min length/class rules]

[slapo-otp schema/overlay]
    ├──requires──> [oath TOTP params + token entries]
    └──enables──> [password+TOTP LDAP bind]

[SSSD LDAP client]
    ├──requires──> [LDAPS trust]
    ├──requires──> [People/Group entries]
    ├──enables──> [SSH password auth]
    ├──enables──> [SSH public key auth from LDAP]
    └──enables──> [sudo LDAP provider]

[Fortune OLC schema]
    ├──must precede──> [YAML import]
    └──with slapo-sssvlv──> [server-side sorting + pagination]
```

### Dependency Notes

- **LDAPS is foundational:** SSSD LDAP auth requires encrypted transport, and the assignment requires LDAPS specifically. Build LDAPS before client auth.
- **DIT and schema before data:** People/Group/Ppolicy/SUDOers/Fortune OUs and custom schemas must exist before importing entries that reference them.
- **ACL ordering is a dependency, not cleanup:** If broad read/write ACLs land before password/self-service ACLs, later rules may never execute.
- **TOTP depends on server-side OATH objects:** The OpenLDAP OTP overlay needs user → token → params references and raw secret storage before binds can validate appended codes.
- **Fortune depends on OLC:** The grader may check `cn=config`; a runtime-only or slapd.conf-only schema file is not sufficient.
- **NFS depends on UID/GID consistency:** LDAP identity must resolve consistently on NFS server and both workstations, or ownership and permissions will look wrong.
- **Sudo depends on host and command matching:** `stu`’s rule should match the workstation1 hostname form the client reports and the full path for `ls`.

## MVP Definition

### Launch With (v1.2 Minimum Passing HW1-3)

- [ ] DNS/topology: `ldap`, `workstation1`, `workstation2` records and DMZ/private firewall paths for LDAPS and NFS.
- [ ] LDAPS OpenLDAP server: base DN, self-signed TLS, OLC configuration, required OUs.
- [ ] Core identity: `ta`/`stu` posixGroups and `generalta`, `mailta`, `stu` user entries with exact UIDs/GIDs/home/mail/key/password values.
- [ ] SSSD clients: NSS/PAM/SSH key lookup works on both workstations over LDAPS.
- [ ] Login authorization: `ta` everywhere, `stu` workstation1 only.
- [ ] Sudo LDAP: `ta` all commands all workstations; `stu` `ls` only on workstation1.
- [ ] ACLs: delegated admin writes, self-service attrs, password read protection, negative tests.
- [ ] NFS homes: mounted `/u/ta` and `/u/stu` with required modes/owners and cross-workstation sync.
- [ ] Password policy: no reuse, min 8, 3 classes enforced by LDAP ppolicy path.
- [ ] TOTP: `generalta` and `stu` password+TOTP auth with SSH-key exemption.
- [ ] Fortune: custom OLC schema, YAML import, server-side sorting and pagination.
- [ ] Mail unblock: once LDAP is stable, enable existing mail LDAP integration for `ta`/`mailta` without regressing HW1-2.

### Add After Core Validation

- [ ] Full smoke-test playbook for every grading section — valuable because OJ may perform malicious or reboot-after-change tests.
- [ ] Detailed debug artifact collection — `ldapsearch`, `slapacl`, `sssctl`, `sudo -l`, NFS mount, and SSH transcript outputs without secrets.
- [ ] SSSD cache management tasks — prevents stale state during iterative grading rehearsals.

### Defer / Do Not Build

- [ ] Multi-server LDAP replication or HA — not required and complicates ppolicy/OTP state.
- [ ] FreeIPA/389DS replacement — out of scope and misses OLC customization objective.
- [ ] Kerberized NFS/LDAP — production-grade but not required; LDAPS + NFSv4 is sufficient for lab behavior.
- [ ] User self-service web UI — not graded; LDAP modify operations are enough.

## Feature Prioritization Matrix

| Feature | User/OJ Value | Implementation Cost | Priority |
|---------|---------------|---------------------|----------|
| LDAPS OpenLDAP base + DNS/firewall | HIGH | HIGH | P1 |
| Required OUs/base DIT | HIGH | LOW | P1 |
| Users/groups with exact IDs/attrs | HIGH | MEDIUM | P1 |
| SSSD NSS/PAM client auth | HIGH | HIGH | P1 |
| SSH public keys from LDAP | HIGH | MEDIUM | P1 |
| Workstation-specific login authorization | HIGH | MEDIUM | P1 |
| Sudo LDAP rules | HIGH | HIGH | P1 |
| ACL admin/self/password protection | HIGH | HIGH | P1 |
| NFS shared homes | HIGH | HIGH | P1 |
| ppolicy no-reuse/min/classes | HIGH | HIGH | P1 |
| TOTP password+OTP with key exemption | HIGH | HIGH | P1 |
| Fortune OLC schema/import/sort/page | HIGH | HIGH | P1 |
| Mail LDAP integration for `mailta` | HIGH for cross-HW scoring | MEDIUM | P1 after LDAP core |
| Smoke-test harness | HIGH for reliability | MEDIUM | P2 |
| SSSD cache/debug tooling | MEDIUM | LOW | P2 |
| LDAP HA/replication | LOW for OJ | HIGH | P3 / Avoid |
| FreeIPA migration | LOW/negative for spec | HIGH | P3 / Avoid |

**Priority key:**

- P1: Required for HW1-3 grading or cross-HW pass consistency.
- P2: Not directly graded, but reduces deadline/debug risk.
- P3 / Avoid: Production feature or alternative stack that increases grading risk.

## Grading-Sensitive Edge Cases

| Area | Edge Case | Expected Behavior |
|------|-----------|-------------------|
| LDAPS | Client uses `ldap://` StartTLS | Do not rely on this path; grading/client configs should use `ldaps://...:636` |
| TLS | Self-signed cert not trusted by SSSD | SSSD auth fails; install CA/cert and use `ldap_tls_reqcert = demand` where possible |
| ACL ordering | Broad `to * by users read` appears before `userPassword` ACL | Password protection may be bypassed or later rule ignored; put `userPassword` first |
| ACL privilege | `by generalta write` on `userPassword` | `write` level implies read/search/compare; use exact `=w` for admin password writes |
| ACL rootdn | `generalta` configured as rootdn | Fails password-read requirement because rootdn bypasses ACLs |
| ppolicy | Password changed with pre-hashed value | Length/classes may be uncheckable; with `pwdCheckQuality: 2`, reject or ensure clients use password modify with cleartext over LDAPS |
| ppolicy | Previous password reused by ordinary user | LDAP rejects due to `pwdInHistory`; rootdn bypass should not be used in validation |
| TOTP | OJ secret encoding mismatch | Store `oathSecret` as raw bytes/base64 LDIF for LDAP; share/use the correct base32/raw form for TOTP generation |
| TOTP | SSH key login asks for OTP | Misconfigured `AuthenticationMethods`; publickey should be exempt |
| TOTP | Password login without TOTP succeeds | `slapo-otp` not active or user lacks OATH objectClasses/token refs |
| SSSD access | `stu` can log into workstation2 | Workstation2 `simple_allow_groups` or cache is wrong; clear cache and retest |
| SSH keys | `sss_ssh_authorizedkeys stu` returns no key | Missing `ldapPublicKey` objectClass/`sshPublicKey`, SSSD service `ssh`, or ACL read access to key |
| Sudo | `stu` can run `sudo cat` | sudoRole too broad or local sudoers grants extra access |
| Sudo | `stu` cannot run `sudo ls` | Command path or `sudoHost` mismatch; include `/usr/bin/ls` and `/bin/ls`, short and FQDN hostnames |
| NFS | Homes exist but changes do not sync | Local directories are being used instead of shared mount |
| NFS | Correct files but wrong owner names | UID/GID mismatch or SSSD unavailable on one host |
| Fortune | Schema exists in file but not `cn=config` | Fails OLC check; add schema as `olcSchemaConfig` entry |
| Fortune | Author matching is case-sensitive | Use case-ignore equality/substring/ordering matching rules for `author` |
| Fortune | Sorted paged search fails | `slapo-sssvlv` missing or not active on database/global config |

## Recommendation for Requirements Definition

Write phase requirements as observable LDAP/SSH/sudo/NFS behavior, not just package tasks. Examples: “a bind as `uid=generalta,...` with `<TA_PASSWORD><current TOTP>` succeeds over LDAPS,” “a bind as `generalta` cannot read `stu`’s `userPassword` but can replace it,” “`stu` can SSH to workstation1 but not workstation2,” “`sudo -l -U stu` on workstation1 lists only `ls`,” and “a file created under `/u/ta/generalta` on workstation1 appears on workstation2.”

The strongest roadmap split is **LDAPS identity foundation → client auth → access controls/NFS → ppolicy/TOTP → sudo/Fortune → cross-HW mail activation**. This order keeps each later feature anchored to a working directory and avoids debugging sudo, TOTP, or Fortune controls while basic LDAPS/SSSD identity is still unstable.

## Sources

- [HIGH] `/Users/j.huang.rj/dev/nasa-labs/lab/ldap.md` — HW1-3 assignment requirements and grading sections.
- [HIGH] `/Users/j.huang.rj/dev/nasa-labs/.planning/PROJECT.md` — current milestone scope, topology constraints, existing DNS/mail/network dependencies.
- [HIGH] Context7 `/openldap/openldap` — OpenLDAP feature/documentation index for ACLs, ppolicy, schemas, overlays, and TLS/LDAPS concepts.
- [HIGH] OpenLDAP 2.6 Admin Guide: Access Control — https://www.openldap.org/doc/admin26/access-control.html; verifies `olcAccess` syntax, ordering, implicit deny, and common `userPassword` ACL patterns.
- [HIGH] OpenLDAP `slapd.access(5)` source man page — https://raw.githubusercontent.com/openldap/openldap/master/doc/man/man5/slapd.access.5; verifies first-match ACL evaluation, `stop`/`continue`/`break`, access levels, exact privilege masks, and rootdn bypass.
- [HIGH] OpenLDAP 2.6 Admin Guide: slapd-config — https://www.openldap.org/doc/admin26/slapdconf2.html; verifies `cn=config`, ordered config entries, `olcAccess`, `olcAttributeTypes`, and `olcObjectClasses`.
- [HIGH] OpenLDAP 2.6 Admin Guide: Schema Specification — https://www.openldap.org/doc/admin26/schema.html; verifies custom schema/OID practices and attribute/objectClass definition structure.
- [HIGH] OpenLDAP `slapo-ppolicy(5)` source man page — https://raw.githubusercontent.com/openldap/openldap/master/doc/man/man5/slapo-ppolicy.5; verifies `pwdInHistory`, `pwdMinLength`, `pwdCheckQuality`, `ppolicy_check_module`, and password quality module semantics.
- [HIGH] OpenLDAP `slapo-otp(5)` source man page — https://raw.githubusercontent.com/openldap/openldap/master/doc/man/man5/slapo-otp.5; verifies OATH/TOTP overlay behavior, password+OTP bind semantics, OATH attributes, SHA algorithm support, and token/params relationships.
- [HIGH] OpenLDAP `slapo-sssvlv(5)` source man page — https://raw.githubusercontent.com/openldap/openldap/master/doc/man/man5/slapo-sssvlv.5; verifies server-side sorting, virtual list view, and paged-results interaction.
- [MEDIUM] OpenLDAP `ppm` password quality module docs via Context7/OpenLDAP contrib — verifies character-class enforcement is a password-check-module concern, not built-in `pwdMinLength` alone.
- [HIGH] Context7 `/sssd/sssd` and SSSD man pages (`sssd-ldap`, `sssd-simple`, `sssd-sudo`, `sss_ssh_authorizedkeys`) — verifies LDAPS/TLS requirement for LDAP auth, rfc2307 defaults, `sshPublicKey`, simple group allow lists, and sudo provider behavior.
- [HIGH] SSSD simple provider man page — https://manpages.debian.org/unstable/sssd-common/sssd-simple.5.en.html; verifies `simple_allow_groups` behavior and group-based access rules.
- [HIGH] Sudo LDAP manual — https://www.sudo.ws/docs/man/sudoers.ldap.man; verifies `ou=SUDOers`, `sudoRole`, `sudoUser`, `sudoHost`, and `sudoCommand` semantics.
- [HIGH] Red Hat NFS documentation — https://docs.redhat.com/en/documentation/red_hat_enterprise_linux/6/html/storage_administration_guide/nfs-serverconfig; verifies `/etc/exports` syntax and default `root_squash`/`sync` behavior.
- [HIGH] OATH Toolkit `pam_oath` manual — https://oath-toolkit.codeberg.page/pam_oath.html; used only to classify `pam_oath` as a fallback/anti-feature relative to LDAP-server-side OTP.
- [HIGH] RFC4517 — https://datatracker.ietf.org/doc/html/rfc4517; verifies Directory String matching rules such as `caseIgnoreMatch`, `caseIgnoreSubstringsMatch`, and `caseIgnoreOrderingMatch`.
- [HIGH] RFC4519 — https://datatracker.ietf.org/doc/html/rfc4519; verifies the standard LDAP user schema, including existing `description`.
- [MEDIUM] ITU/OID UUID arc reference — https://www.itu.int/en/ITU-T/asn1/Pages/UUID/uuids.aspx and https://oid-base.com/get/2.25; verifies the UUID OID branch `2.25` and no-registration UUID-derived OID pattern.

---
*Feature research for: HW1-3 LDAP service automation*  
*Researched: 2026-05-28*
