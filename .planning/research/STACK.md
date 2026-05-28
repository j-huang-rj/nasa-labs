# Stack Research

**Domain:** HW1-3 LDAP lab stack additions on AlmaLinux 9  
**Researched:** 2026-05-28  
**Confidence:** HIGH for package names/availability; MEDIUM-HIGH for OJ-specific overlay behavior until validated against the grader

## Recommendation in One Sentence

Add an AlmaLinux 9 OpenLDAP server role that enables EPEL only where needed for `openldap-servers`, uses the EPEL-packaged OpenLDAP 2.6 overlay modules (`ppolicy`, `otp`, `sssvlv`), configures LDAPS with OpenSSL-generated self-signed certificates, and adds SSSD/sudo/NFS client packages on the workstation hosts without introducing FreeIPA, 389 Directory Server, `pam_oath`, or a second authentication stack.

## Key Package Finding

`openldap-servers` is **not available in the default AlmaLinux 9 BaseOS/AppStream/Extras repos**. It is available from **EPEL 9** as `openldap-servers-2.6.8-2.el9`. The client libraries/tools (`openldap`, `openldap-clients`) are in BaseOS as `2.6.8-4.el9`.

Therefore the LDAP server role must add `epel-release` before installing `openldap-servers`. This should be scoped to LDAP-capable hosts, not applied globally to every VM.

## Recommended Stack

### Core Technologies

| Technology | Version checked | Purpose | Why Recommended |
|------------|-----------------|---------|-----------------|
| AlmaLinux | 9.8 package line from `almalinux:9` x86_64 repos | OS baseline for LDAP server/workstations | Matches the existing project VM baseline and avoids the mixed-OS assumption from older mail research. |
| EPEL release package | `epel-release-9-9.el9` from AlmaLinux Extras | Enables EPEL 9 repository | Required because the OpenLDAP server RPM is in EPEL, not stock AlmaLinux repos. Scope it to LDAP server/admin tooling only. |
| OpenLDAP server | `openldap-servers-2.6.8-2.el9` from EPEL | `slapd`, `slapd.d`/OLC, OpenLDAP overlays | Required by the lab. Includes the needed overlay modules and `check_password.so`; do not replace with 389 DS even though 389 DS is in AppStream. |
| OpenLDAP libraries/clients | `openldap-2.6.8-4.el9`, `openldap-clients-2.6.8-4.el9` from BaseOS | LDAP runtime libraries and CLI tools (`ldapadd`, `ldapmodify`, `ldapsearch`, `ldappasswd`) | Use CLI tools for OLC bootstrap, schema loads, LDIF validation, and grader/debug checks. |
| OpenLDAP overlays | packaged inside `openldap-servers` | `ppolicy`, `otp`, `sssvlv`, password quality checking | No separate `ppolicy`, `oath`, or `sssvlv` RPM is needed. Modules are under `/usr/lib64/openldap/`. |
| SSSD LDAP client | `sssd-2.9.8-4.el9_8`, `sssd-ldap-2.9.8-4.el9_8` from BaseOS | NSS/PAM LDAP identity and authentication on workstations | Standard RHEL-family client stack; integrates with PAM, SSH authorized keys, sudo responder, caching, and LDAPS trust settings. |
| sudo with SSSD/LDAP support | `sudo-1.9.17p2-3.el9_8`, `libsss_sudo-2.9.8-4.el9_8` from BaseOS | LDAP-backed sudo rules | AlmaLinux `sudo` is built with `--with-ldap` and `--with-sssd`, and ships the OpenLDAP sudo schema. Prefer SSSD sudo provider over direct sudo LDAP. |
| NFS utilities | `nfs-utils-2.5.4-42.el9_8` from BaseOS | NFS server/client for shared home directories | One package covers server exports and client mounts. Prefer NFSv4/static mounts to avoid `autofs` and dynamic NFSv3 firewall complexity. |
| OpenSSL and trust store | `openssl-3.5.5-2.el9_8`, `ca-certificates-2025.2.80_v9.0.305-91.el9` from BaseOS | Generate LDAPS self-signed certs and distribute trust | Minimal, distro-native tooling. Generate SAN-bearing certs for `ldap.{STUID}.nasa`; install cert as trusted anchor on SSSD/mail clients. |
| Ansible controller | local `ansible-core 2.21.0`; `ansible.posix 2.1.0` already installed | Automation engine and existing firewalld/mount modules | Continue existing component-role pattern. No managed host needs `ansible-core`; only the controller does. |

### OpenLDAP Server Packages

| Package | Version checked | Repo | Purpose | Install? |
|---------|-----------------|------|---------|----------|
| `epel-release` | `9-9.el9` | AlmaLinux Extras | Enables EPEL repo config | Yes, before `openldap-servers` |
| `openldap-servers` | `2.6.8-2.el9` | EPEL | Provides `slapd`, `slaptest`, `/etc/openldap/slapd.d`, modules, schemas | Yes, LDAP server only |
| `openldap` | `2.6.8-4.el9` | BaseOS | LDAP shared libraries | Yes, dependency/runtime |
| `openldap-clients` | `2.6.8-4.el9` | BaseOS | `ldapadd`, `ldapmodify`, `ldapsearch`, `ldappasswd` | Yes, server and any admin/debug host |
| `openssl` | `3.5.5-2.el9_8` | BaseOS | Self-signed LDAPS certificate/key generation | Yes |
| `ca-certificates` | `2025.2.80_v9.0.305-91.el9` | BaseOS | System trust store and `update-ca-trust` | Yes, server and clients |
| `oathtool` | `2.6.12-1.el9` | EPEL | Local validation of TOTP secrets | Optional for testing; not required by `slapo-otp` |
| `liboath` | `2.6.12-1.el9` | EPEL | OATH library dependency for `oathtool` | Optional; pulled by `oathtool` |

### Overlay Availability

| Lab Need | Package/Module | Path verified | Notes |
|----------|----------------|---------------|-------|
| Password policy overlay | `ppolicy` in `openldap-servers` | `/usr/lib64/openldap/ppolicy.so` | Supports password history/min length/lockout policy. Configure via OLC `olcOverlay=ppolicy`. |
| 3-character-class password quality | `check_password.so` in `openldap-servers` | `/usr/lib64/openldap/check_password.so`, `/etc/openldap/check_password.conf` | `ppolicy` alone is not enough for “3 character classes”; use this checker with `pwdCheckQuality: 2` and `minPoints 3`. |
| TOTP/OATH overlay | `otp` in `openldap-servers` | `/usr/lib64/openldap/otp.so` | The module name is `otp`, not `oath`. It implements RFC 4226 HOTP and RFC 6238 TOTP using `oathOTP*` attributes. |
| Server-side sorting + VLV/paged search | `sssvlv` in `openldap-servers` | `/usr/lib64/openldap/sssvlv.so` | Implements server-side sort and virtual list view; also replaces paged-results behavior so sorted paged searches work. |
| sudo LDAP schema | `schema.olcSudo` in `sudo` package | `/usr/share/doc/sudo/schema.olcSudo` | Load into `cn=config` so LDAP can store `sudoRole` entries under `ou=SUDOers`. |
| SSH public key schema | project-provided schema LDIF | not packaged by OpenSSH/SSSD | Add a small OLC schema for `ldapPublicKey` / `sshPublicKey`; SSSD supplies the lookup command, not the schema. |
| Fortune custom objectClass | project-provided schema LDIF | N/A | Define as custom OLC schema in the LDAP role using a private/local OID arc. No package exists or is needed. |

### LDAP Client / Workstation Packages

| Package | Version checked | Repo | Purpose | Notes |
|---------|-----------------|------|---------|-------|
| `sssd` | `2.9.8-4.el9_8` | BaseOS | SSSD meta/core daemon | Install on `workstation1` and `workstation2`. |
| `sssd-ldap` | `2.9.8-4.el9_8` | BaseOS | LDAP identity/auth backend | Required for `id_provider = ldap`, `auth_provider = ldap`, `sudo_provider = ldap`. |
| `sssd-tools` | `2.9.8-4.el9_8` | BaseOS | `sssctl` diagnostics | Install for validation and cache/debug commands. |
| `sssd-common` | `2.9.8-4.el9_8` | BaseOS | `sss_ssh_authorizedkeys`, SSSD responders | Pulled by `sssd`; explicitly rely on `/usr/bin/sss_ssh_authorizedkeys` for SSH keys. |
| `libsss_sudo` | `2.9.8-4.el9_8` | BaseOS | sudo ↔ SSSD client library | Install with `sudo`/SSSD clients; supports `sudoers: files sss`. |
| `authselect` | `1.2.6-3.el9` | BaseOS | PAM/NSS profile management | Use `authselect select sssd with-mkhomedir` instead of editing PAM files by hand. |
| `oddjob` | `0.34.7-7.el9` | AppStream | oddjob service | Needed by mkhomedir workflow. |
| `oddjob-mkhomedir` | `0.34.7-7.el9` | AppStream | Create home dirs on first login when not NFS-mounted yet | Useful fallback; still configure NFS home mounts for sync. |
| `sudo` | `1.9.17p2-3.el9_8` | BaseOS | sudo binary and sudo LDAP schema docs | No separate `sudo-ldap` package exists on AlmaLinux 9. |
| `openssh-server` | `9.9p1-7.el9_8.alma.1` | BaseOS | SSHD with `AuthorizedKeysCommand` | Existing base may already include it; LDAP client role should manage the SSSD key command config. |
| `nfs-utils` | `2.5.4-42.el9_8` | BaseOS | NFS client mount helpers | Install on all workstation clients and the NFS server host. |
| `ca-certificates` | `2025.2.80_v9.0.305-91.el9` | BaseOS | Trust LDAP self-signed cert | Copy LDAP cert to `/etc/pki/ca-trust/source/anchors/` and run `update-ca-trust`. |
| `openldap-clients` | `2.6.8-4.el9` | BaseOS | Debug/test LDAPS from clients | Optional but recommended for `ldapsearch -H ldaps://ldap...` checks. |

### Supporting Libraries / Optional Ansible Dependencies

| Library / Collection | Version checked | Purpose | When to Use |
|----------------------|-----------------|---------|-------------|
| `ansible.posix` collection | local `2.1.0` | Existing `firewalld`, `sysctl`; useful for `ansible.posix.mount` and `ansible.posix.seboolean` | Already part of this project’s role surface. Keep using it for NFS mounts/firewalld rather than shelling out. |
| `community.general` collection | local `12.6.0` | Optional LDAP modules: `community.general.ldap_entry`, `ldap_attrs`, `ldap_passwd` | Use only if you install `python3-ldap` on the delegated host and want module-level LDAP idempotency. Not strictly required. |
| `python3-ldap` | `3.4.3-2.el9` from AppStream | Python LDAP binding for `community.general.ldap_*` modules | Install on the LDAP server if LDAP tasks are delegated there and use `community.general`. Otherwise skip. |
| `python3-pyasn1`, `python3-pyasn1-modules` | `0.4.8-7.el9_7` | Supporting ASN.1 libs for Python LDAP use cases | Optional with `python3-ldap` workflows. |
| `community.crypto` collection | not installed locally | Idempotent key/CSR/certificate modules | Optional. Prefer plain `openssl` commands/templates unless the project adds a `requirements.yml` and installs this collection. |

## Installation

```bash
# LDAP server host only: EPEL is required for openldap-servers.
sudo dnf install -y epel-release
sudo dnf install -y \
  openldap openldap-servers openldap-clients \
  openssl ca-certificates

# Optional LDAP server/admin validation tooling for TOTP checks.
sudo dnf install -y oathtool

# Workstation LDAP/NFS/sudo client hosts.
sudo dnf install -y \
  sssd sssd-ldap sssd-tools libsss_sudo \
  authselect oddjob oddjob-mkhomedir \
  sudo openssh-server nfs-utils ca-certificates openldap-clients

# NFS server host, if separate from the LDAP server.
sudo dnf install -y nfs-utils
```

In Ansible, do **not** hard-pin exact RPM releases in tasks. Use package names with `state: present`, then record observed versions during validation. AlmaLinux 9 minor releases can advance `_el9_8` package releases while preserving the same package names.

## Integration With Existing Component Role Pattern

| Area | Stack Decision | Integration Guidance |
|------|----------------|----------------------|
| Roles | Add component roles, not system roles | Recommended role boundaries: `ldap` for slapd/schema/data/LDAPS, `ldap_client` or `auth` for SSSD/PAM/SSH/sudo client config, and `nfs` for exports/mounts. Do not create `workstation` or `ldap_server` system roles that bake in host identity. |
| Inventory | Add LDAP server and workstation hosts by topology | LDAP server belongs in the private/internal group; workstations belong in the DMZ group. Keep variable names generic (`ldap_*`, `nfs_*`, `sssd_*`) and host-scoped. |
| Firewall | Reuse existing `firewall` role | LDAP requires LDAPS `636/tcp` from DMZ to private; NFS should prefer NFSv4 `2049/tcp` only. Avoid NFSv3 dynamic ports unless grading proves necessary. |
| DNS | Reuse existing BIND9 role | Add `ldap`, `workstation1`, and `workstation2` records through the existing zone variable model. Do not let the LDAP role write BIND zone files. |
| Certificates | Generate on LDAP server; distribute cert to clients | Use `openssl` to create SAN cert/key for `ldap.{STUID}.nasa`, configure slapd TLS paths in `cn=config`, copy cert to clients’ trust anchors, and set SSSD `ldap_uri = ldaps://ldap.{STUID}.nasa`. |
| OLC / schema | Prefer rendered LDIF + `ldapmodify -Y EXTERNAL -H ldapi:///` | This avoids a hard dependency on Python LDAP libraries. If adopting `community.general.ldap_*`, add `python3-ldap` and document it explicitly. |
| sudo rules | Use SSSD sudo provider | Configure SSSD domain with `sudo_provider = ldap` and `ldap_sudo_search_base = ou=SUDOers,dc={STUID},dc=nasa`; configure NSS as `sudoers: files sss`. |
| SSH keys | Use SSSD SSH responder/helper | Configure `AuthorizedKeysCommand /usr/bin/sss_ssh_authorizedkeys` and `AuthorizedKeysCommandUser nobody`; add the `sshPublicKey` schema and map users accordingly. |
| Home directories | Use NFS + SSSD identities | Use stable UID/GID values from LDAP, export `/u/ta` and `/u/stu` from the NFS server, mount them on workstations, and enable SELinux `use_nfs_home_dirs` if SELinux enforcing blocks access. |
| Mail integration | Flip the existing feature flag after LDAP validation | Existing Dovecot LDAP passdb scaffolding is gated by `mail_ldap_enabled`; do not duplicate mail LDAP logic in the LDAP role. Provide endpoint/base DN/CA variables for the mail role to consume. |

## Alternatives Considered

| Recommended | Alternative | Why Not / When to Use Alternative |
|-------------|-------------|-----------------------------------|
| EPEL `openldap-servers` | 389 Directory Server (`389-ds-base`) | 389 DS is available in AppStream, but the lab explicitly needs OpenLDAP/slapd overlays and OLC-style schema/config work. Use 389 DS only if the course spec changes. |
| EPEL OpenLDAP RPM | Build OpenLDAP from source | Source builds add compiler/toolchain, service packaging, SELinux, and update risks. EPEL already packages OpenLDAP 2.6.8 with the required modules. |
| OpenLDAP `otp` overlay | `pam_oath` on clients | The lab wants LDAP password+TOTP behavior while SSH key auth is exempt. Client-side `pam_oath` duplicates secrets onto workstations and can accidentally affect SSH key logins. |
| SSSD LDAP/PAM/sudo/SSH | `nslcd` / `nss-pam-ldapd` / manual PAM edits | SSSD is the RHEL-family standard and handles caching, sudo, SSH keys, and authselect integration in one stack. |
| SSSD sudo provider | Direct sudo LDAP via `/etc/sudo-ldap.conf` | Alma sudo supports direct LDAP, but SSSD gives caching and aligns with the identity provider. Use direct LDAP only as a fallback if SSSD sudo behavior fails grader checks. |
| Static NFSv4 mounts | `autofs` | Static mounts are simpler and deterministic for two workstations. Add `autofs` only if later phases require on-demand mounts. |
| OpenSSL command/template | `community.crypto` collection | OpenSSL avoids adding a controller collection. Use `community.crypto` only if the project standardizes collection installation in a requirements file. |

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| `389-ds-base`, FreeIPA, Samba AD | Solves a broader directory problem but does not match OpenLDAP overlay/OLC lab requirements. | EPEL `openldap-servers`. |
| Looking for `openldap-ppolicy`, `openldap-oath`, `openldap-sssvlv` RPMs | These are not separate AlmaLinux/EPEL package names. | Install `openldap-servers`; load `ppolicy`, `otp`, and `sssvlv` modules. |
| `pam_oath` for the required TOTP behavior | Would enforce MFA in PAM/client space, duplicating secrets and risking SSH-key-auth failures. | OpenLDAP `otp` overlay on the LDAP server; use `oathtool` only for validation. |
| A nonexistent `sudo-ldap` package | AlmaLinux 9 packages LDAP/SSSD sudo support in `sudo` and `libsss_sudo`. | `sudo` + `libsss_sudo` + SSSD `sudo_provider = ldap`. |
| `authconfig` | Deprecated legacy auth management on RHEL-family systems. | `authselect select sssd with-mkhomedir`. |
| `nscd` with SSSD | Cache layering causes stale identity/group/sudo behavior. | SSSD cache only; use `sssctl cache-remove` for resets. |
| Dockerized LDAP/NFS | Adds networking, volume, SELinux, and systemd complexity for services that the lab expects as native host daemons. | Native RPMs and systemd services. |
| Hardcoded TA passwords/TOTP secrets in role defaults | Violates project secret split and lab security requirements. | Gitignored `host_vars/*/secrets.yml` and committed `secrets.example.yml`. |

## Stack Patterns by Variant

**If configuring the LDAP server:**
- Enable EPEL, install `openldap-servers openldap-clients openssl ca-certificates`.
- Load modules via OLC: `ppolicy`, `otp`, `sssvlv`; configure `check_password.so` for class-count rules.
- Load schema: core/cosine/inetorgperson/nis as needed, sudo OLC schema from `sudo`, SSH public key schema from role template, Fortune custom schema from role template.

**If configuring a workstation/client:**
- Install `sssd sssd-ldap sssd-tools libsss_sudo authselect oddjob-mkhomedir sudo openssh-server nfs-utils ca-certificates`.
- Trust LDAP cert, configure SSSD for LDAPS, enable NSS/PAM/sudo/ssh responders, set SSH `AuthorizedKeysCommand`, and mount NFS homes.

**If configuring the NFS server:**
- Install `nfs-utils` and export `/u/ta` and `/u/stu` with UID/GID-compatible ownership.
- Prefer NFSv4 over TCP 2049 and avoid enabling extra RPC services unless tests require them.

**If enabling mail LDAP integration later:**
- Do not add a second LDAP client implementation. Feed the existing mail role `ldap_uri`, base DN, bind/search filters, CA cert path, and then set `mail_ldap_enabled: true`.

## Version Compatibility

| Package A | Compatible With | Notes |
|-----------|-----------------|-------|
| `openldap-servers-2.6.8-2.el9` | `openldap-2.6.8-4.el9`, `openldap-clients-2.6.8-4.el9` | Release suffix differs between EPEL server and BaseOS libraries, but RPM dependency only requires OpenLDAP `2.6.8`; install tested successfully from current repos. |
| `ppolicy.so` | `check_password.so` | Use `pwdCheckQuality: 2` plus `check_password.conf` for 3 character classes; `pwdMinLength` alone only covers length. |
| `otp.so` | LDAP simple bind/password auth | Users append TOTP to the password for simple bind. SSH key auth remains outside password bind, satisfying the “SSH key exempt” requirement if PAM is not forced through `pam_oath`. |
| `sssvlv.so` | sorted paged LDAP searches | Sorting/paging can be memory-heavy; keep limits conservative (`olcSssVlvMax*`) for lab scale. |
| `sssd-ldap-2.9.8` | OpenLDAP LDAPS | Use `ldap_uri = ldaps://ldap.{STUID}.nasa`, `ldap_search_base = dc={STUID},dc=nasa`, and a trusted CA/cert path. |
| `sssd-common` | OpenSSH `AuthorizedKeysCommand` | `/usr/bin/sss_ssh_authorizedkeys` is packaged by `sssd-common`; configure sshd to call it. |
| `sudo-1.9.17p2` | `libsss_sudo-2.9.8` and SSSD sudo responder | Set `sudoers: files sss`; load `/usr/share/doc/sudo/schema.olcSudo` into OpenLDAP for `sudoRole`. |
| `nfs-utils-2.5.4` | SSSD LDAP UID/GID identities | LDAP UID/GID consistency is mandatory; NFS permissions depend on numeric IDs matching across clients and server. |

## Sources

- `.planning/PROJECT.md` — current HW1-3 scope, topology, constraints, and existing role conventions. HIGH
- AlmaLinux 9.8 x86_64 `dnf repoquery` from `almalinux:9` container on 2026-05-28 — verified package names, versions, repos, and installability for BaseOS/AppStream/Extras/EPEL. HIGH
- AlmaLinux mirrorlists: `https://mirrors.almalinux.org/mirrorlist/9/baseos`, `/appstream`, `/extras`; EPEL 9 repo enabled via `epel-release`. HIGH
- Context7 `/openldap/openldap` plus packaged OpenLDAP man pages `slapo-ppolicy(5)`, `slapo-otp(5)`, `slapo-sssvlv(5)` from `openldap-servers-2.6.8` — verified overlay purpose and TOTP/SSSVLV/ppolicy behavior. HIGH
- RPM file inventory for `openldap-servers` — verified module paths: `/usr/lib64/openldap/{ppolicy,otp,sssvlv}.so`, `/usr/lib64/openldap/check_password.so`, and `/etc/openldap/check_password.conf`. HIGH
- AlmaLinux `sudo -V` and RPM file inventory for `sudo-1.9.17p2` — verified sudo built with LDAP and SSSD support and ships `/usr/share/doc/sudo/schema.olcSudo`. HIGH
- Packaged SSSD man pages `sssd-sudo(5)` and `sss_ssh_authorizedkeys(1)` from `sssd-2.9.8` — verified SSSD sudo provider pattern and OpenSSH `AuthorizedKeysCommand` integration. HIGH
- Local Ansible inventory: `ansible.posix 2.1.0`, `community.general 12.6.0`, `ansible-core 2.21.0` — verified existing/optional collection availability. MEDIUM-HIGH

---
*Stack research for: HW1-3 LDAP lab stack additions*  
*Researched: 2026-05-28*
