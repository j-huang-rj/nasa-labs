# Architecture Research

**Domain:** HW1-3 LDAP service integration into the existing NASA Labs Ansible/DNS/firewall/mail topology  
**Researched:** 2026-05-28  
**Confidence:** HIGH for repo integration, host placement, DNS/firewall/playbook ordering, and NFS placement; MEDIUM for final SSSD/PAM/TOTP mechanics pending implementation-level validation on AlmaLinux packages

## Executive Recommendation

Add LDAP as a **new dedicated private-zone VM** (`ldap-01`, service FQDN `ldap.<STUID>.nasa`) and colocate the lab NFS home export on that same VM. Do **not** reuse `primary-ns-01`, `dns-01`, or `internal-agent-01` for LDAP. LDAP is identity-critical, owns secrets and ACLs, and will become a dependency for both DMZ workstations and the existing mail role. A separate private-zone VM keeps DNS, resolver, Docker agent, and identity/NFS failure domains separate while still requiring only one additional private host.

Add two new DMZ workstation VMs (`workstation1`, `workstation2`) provisioned exactly like existing cloud-init hosts: one `eth0` NIC in the DMZ, static IPs, bootstrap DNS set to public DNS, final DNS restored by Ansible to `dns-01`, and no service configuration in cloud-init. Cloud-init should only create the administrative bootstrap user and network identity; LDAP client auth, sudo rules, SSH key lookup, TOTP, and NFS mounts belong in Ansible roles.

Use three new component roles, not system roles:

- `openldap`: server-side slapd/OLC/TLS/schema/DIT/ACL/overlays/users/groups/Fortune data on `ldap_servers`.
- `nfs`: host-agnostic NFS server/client role. Server mode runs on `ldap-01`; client mount mode runs on the workstations.
- `ldap-client`: workstation-side SSSD/NSS/PAM/sshd/sudo/TOTP integration on `workstations` / `ldap_clients`.

The full converge order should become: **bootstrap → dns_configure → ldap_configure → nfs_configure → workstation_configure → mail_configure**. DNS records must exist before services verify FQDNs and certificates; the LDAP server must exist before clients and mail LDAP are enabled; the NFS server/export must exist before workstation mounts; mail LDAP stays last because the current mail role asserts LDAP reachability when `mail_ldap_enabled` is true.

## Standard Architecture

### System Overview

```text
                         Online Judge / TA VPN
                                  │
                                  │ existing DNS/VPN grading path
                                  ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│ router-01                                                                    │
│ - Existing zones: external, dmz, internal, vpn                                │
│ - Existing DMZ→internal LDAPS policy: tcp/636                                 │
│ - NEW: DMZ→internal NFSv4 policy: tcp/2049, scoped to LDAP/NFS host if role   │
│        supports source/destination rich rules                                 │
│ - NEW: masquerade exemption for ldap-01 so NFS exports see workstation IPs    │
└───────────────────────────────┬──────────────────────────────────────────────┘
                                │
              ┌─────────────────┴──────────────────┐
              │                                    │
              ▼ DMZ 172.16.0.0/24                  ▼ Private 172.16.1.0/24
┌──────────────────────────────┐      ┌───────────────────────────────────────┐
│ workstation1.<STUID>.nasa    │      │ ldap.<STUID>.nasa (`ldap-01`)          │
│ - LDAP login: ta + stu       │─────▶│ - OpenLDAP over LDAPS only            │
│ - SSH public key from LDAP   │636   │ - OLC cn=config, MDB database         │
│ - sudo rules from LDAP       │      │ - People/Group/Ppolicy/SUDOers/Fortune│
│ - NFS mount /u               │2049  │ - ppolicy + sssvlv overlays           │
└──────────────────────────────┘─────▶│ - NFSv4 export for /u homes           │
                                      └───────────────────────────────────────┘
┌──────────────────────────────┐                       ▲
│ workstation2.<STUID>.nasa    │                       │ LDAPS 636
│ - LDAP login: ta only        │                       │
│ - SSH public key from LDAP   │                       │
│ - sudo rules from LDAP       │          ┌────────────┴─────────────┐
│ - NFS mount /u               │          │ dmz-client-01 (mail)      │
└──────────────────────────────┘          │ - Existing mail role       │
                                          │ - Dovecot LDAP passdb      │
                                          │ - mail_ldap_enabled=true   │
                                          └──────────────────────────┘

┌──────────────────────────────────────────────────────────────────────────────┐
│ Existing DNS tier                                                            │
│ - primary-ns-01 owns zone records for ldap/workstation1/workstation2         │
│ - secondary-ns-01 mirrors through existing AXFR/NOTIFY                       │
│ - dns-01 resolves private clients to private-view records                    │
└──────────────────────────────────────────────────────────────────────────────┘
```

### Host Placement

| Host | Placement | Recommendation | Rationale |
|------|-----------|----------------|-----------|
| `ldap-01` / `ldap.<STUID>.nasa` | **New VM in private zone**; suggested IP `172.16.1.10/24`, gateway `172.16.1.254`, final DNS `172.16.1.153` | **Use this** | Private zone matches the assignment, DMZ can already reach private LDAPS, and identity/NFS state stays isolated from DNS and Docker agent roles. |
| NFS home server | **Colocated on `ldap-01`** | **Use this** | The lab needs synchronized `/u/ta` and `/u/stu` homes across workstations, not production storage HA. One private identity/home server is the simplest single source of truth. |
| `workstation1` | **New VM in DMZ**; suggested IP `172.16.0.11/24` | **Use this** | Assignment explicitly requires workstation1 in DMZ; it allows both `ta` and `stu` logins and mounts `/u`. |
| `workstation2` | **New VM in DMZ**; suggested IP `172.16.0.12/24` | **Use this** | Assignment explicitly requires workstation2 in DMZ; it allows `ta` logins only and mounts `/u`. |
| `primary-ns-01` | Existing internal authoritative primary DNS | **Do not reuse for LDAP** | LDAP ACL/schema mistakes or slapd restarts must not endanger HW1-1 authoritative DNS. |
| `dns-01` | Existing internal resolver | **Do not reuse for LDAP** | Resolver behavior is a previous-lab dependency; LDAP/NFS package/firewall changes add unnecessary blast radius. |
| `internal-agent-01` | Existing private Docker grading agent | **Do not reuse for LDAP** | Agent containers use host networking and should not share identity/NFS state or ports. |

Fallback if VM budget is truly constrained: put LDAP/NFS on `dns-01` rather than `primary-ns-01`, but mark it a regression risk. The recommended roadmap should assume a new `ldap-01` VM.

### Component Responsibilities

| Component | Responsibility | Typical Implementation |
|-----------|----------------|------------------------|
| `openldap` role | Slapd package install, LDAPS listener, OLC `cn=config`, MDB database, base DN, schema, overlays, ACLs, LDAP entries, verification | `slapd`/OpenLDAP on AlmaLinux; manage config through `ldapi:///` and idempotent LDIF checks. |
| `nfs` role | Server exports and client mounts for synchronized home directories | NFSv4-only using `nfs-utils`; export `/u` from `ldap-01`; mount `/u` on both workstations. |
| `ldap-client` role | Workstation OS auth, NSS, PAM, sudo, sshPublicKey lookup, TOTP enforcement, access control | SSSD-backed LDAP identity/auth/sudo plus sshd `AuthorizedKeysCommand`; PAM TOTP module gated to password auth path. |
| `bind9` role | DNS records for `ldap`, `workstation1`, `workstation2`; no LDAP service writes | Extend existing zone record lists in `primary-ns-01` host vars; secondary mirrors as today. |
| `firewall` role / `router-01` vars | Cross-zone LDAPS/NFS policy, masquerade exemptions, host port openings | Reuse `dmz-to-internal-ldaps`; add NFSv4 2049/tcp and preserve DMZ source IPs to `ldap-01`. |
| `mail` role | Dovecot LDAP passdb and mail LDAP user behavior | Existing gated `mail_ldap_enabled` path connects to `ldaps://ldap.<STUID>.nasa:636` after LDAP server is live. |

## Recommended Project Structure

```text
ansible/playbooks/
├── site.yml                         # bootstrap → dns → ldap → nfs → workstation → mail
├── ldap_configure.yml               # NEW: hosts ldap_servers, role openldap
├── nfs_configure.yml                # NEW: first nfs server, then nfs clients
├── workstation_configure.yml        # NEW: hosts workstations, role ldap-client
└── roles/
    ├── openldap/                    # NEW component role
    │   ├── defaults/main.yml        # package names, paths, ports, safe defaults
    │   ├── meta/argument_specs.yml  # validate base DN, TLS, users, groups, overlays
    │   ├── handlers/main.yml        # restart/reload slapd
    │   ├── tasks/
    │   │   ├── main.yml             # START/END + phase imports
    │   │   ├── assert.yml           # variable/schema/secret checks
    │   │   ├── install.yml          # slapd/openldap-clients/packages
    │   │   ├── tls.yml              # install cert/key, restrict permissions
    │   │   ├── olc.yml              # cn=config database/modules/listeners
    │   │   ├── schema.yml           # nis/sudo/openssh/TOTP/Fortune schema
    │   │   ├── overlays.yml         # ppolicy, sssvlv, optional memberof/refint
    │   │   ├── dit.yml              # OUs, groups, users, service accounts
    │   │   ├── acl.yml              # admin/self/password-read protections
    │   │   └── verify.yml           # ldaps search, ACL, overlay checks
    │   ├── templates/
    │   │   ├── ldap.conf.j2
    │   │   ├── slapd-defaults.j2
    │   │   └── ldif/*.j2
    │   └── files/schema/            # static schema files if not packaged
    │
    ├── nfs/                         # NEW component role, server/client modes
    │   ├── defaults/main.yml
    │   ├── meta/argument_specs.yml
    │   ├── handlers/main.yml        # exportfs reload, systemd daemon-reload
    │   ├── tasks/
    │   │   ├── main.yml
    │   │   ├── assert.yml
    │   │   ├── install.yml
    │   │   ├── server.yml           # /u tree + exports + nfs-server
    │   │   ├── client.yml           # fstab/systemd mounts for /u
    │   │   └── verify.yml
    │   └── templates/exports.j2
    │
    └── ldap-client/                 # NEW component role
        ├── defaults/main.yml
        ├── meta/argument_specs.yml
        ├── handlers/main.yml        # restart sssd/sshd
        ├── tasks/
        │   ├── main.yml
        │   ├── assert.yml
        │   ├── install.yml          # sssd, oddjob, sudo, openldap-clients, TOTP package
        │   ├── ca.yml               # trust LDAP self-signed CA/server cert
        │   ├── sssd.yml             # LDAP NSS/PAM/sudo provider
        │   ├── sshd.yml             # LDAP sshPublicKey lookup
        │   ├── sudo.yml             # sudo LDAP client settings if not via SSSD defaults
        │   ├── pam_totp.yml         # password-auth-only TOTP enforcement
        │   └── verify.yml
        └── templates/
            ├── sssd.conf.j2
            ├── sshd_ldap_keys.conf.j2
            └── pam/*.j2

ansible/inventory/
├── hosts.yml                        # add topology + functional groups
├── group_vars/all/
│   ├── ldap.yml                     # NEW shared LDAP identity/schema/user vars
│   └── nfs.yml                      # NEW shared NFS path/export vars
└── host_vars/
    ├── ldap-01/
    │   ├── main.yml                 # network, openldap_enabled, nfs_server_enabled, firewall ports
    │   ├── secrets.example.yml      # committed shape only
    │   └── secrets.yml              # gitignored real TA password/TOTP/TLS/admin secrets
    ├── workstation1/main.yml        # network, ldap_client_enabled, nfs_client_enabled, allowed groups ta+stu
    └── workstation2/main.yml        # network, ldap_client_enabled, nfs_client_enabled, allowed groups ta only

cloud-init/
├── iid-ldap-01/{meta-data.yml,network-config.yml,user-data.yml}
├── iid-workstation1/{meta-data.yml,network-config.yml,user-data.yml}
└── iid-workstation2/{meta-data.yml,network-config.yml,user-data.yml}
```

### Structure Rationale

- **Keep `openldap`, `ldap-client`, and `nfs` separate** because they own different state and run on different hosts. LDAP server tasks should not edit workstation PAM; workstation auth should not write server DIT entries; NFS exports/mounts should not be hidden inside the LDAP role.
- **Use functional groups in addition to topology groups.** `ldap-01` belongs to `internal` and `ldap_servers`; workstations belong to `dmz`, `workstations`, `ldap_clients`, and `nfs_clients`. This preserves the repo convention where `bootstrap.yml` targets topology and service playbooks target capabilities.
- **Keep DNS in `bind9`.** `openldap` may expose variables such as `ldap_fqdn` and `ldap_server_ip`, but only the existing BIND role should render zone files.
- **Keep router/firewall policy in inventory.** Service roles declare host-local ports, but cross-zone policy and masquerade exemptions remain `router-01` host vars.
- **Store shared identity once.** Define LDAP users, UIDs, GIDs, home paths, group memberships, and mail addresses in `group_vars/all/ldap.yml`; have `openldap`, `nfs`, `ldap-client`, DNS, and mail consume the same data.

## Architectural Patterns

### Pattern 1: Dedicated Identity/Home Server in Private Zone

**What:** `ldap-01` is the single authoritative host for OpenLDAP and the `/u` NFS export.  
**When to use:** Course lab with one LDAP server, two workstations, no HA requirement, and an existing router between DMZ and private zone.  
**Trade-offs:** Colocating LDAP and NFS is not production HA, but it is the correct lab trade-off: fewer VMs, no cross-private storage dependency, one host to protect, and clear dependency ordering.

Recommended host vars shape:

```yaml
# ansible/inventory/host_vars/ldap-01/main.yml
network_interfaces:
  - ifname: eth0
    zone: internal
    ip4: 172.16.1.10/24
    gw4: 172.16.1.254
    dns4:
      - 172.16.1.153
      - 1.1.1.1
    conn_name: internal-static
    default_conn_name: "cloud-init eth0"

network_bootstrap_dns4:
  - 1.1.1.1

openldap_enabled: true
nfs_server_enabled: true

firewall_zone_ports:
  - zone: internal
    port: 636
    proto: tcp
  - zone: internal
    port: 2049
    proto: tcp
```

### Pattern 2: Shared LDAP Data Model, Multiple Consumers

**What:** One inventory data model defines LDAP entities; roles render different projections of it.  
**When to use:** LDAP users/groups also determine home ownership, workstation access, sudo policy, mail acceptance, and DNS names.  
**Trade-offs:** More up-front variable validation, but avoids divergent `generalta`/`mailta`/`stu` definitions.

Recommended shared data shape:

```yaml
# ansible/inventory/group_vars/all/ldap.yml
ldap_server_host: ldap-01
ldap_server_ip: "{{ hostvars[ldap_server_host].ansible_host }}"
ldap_domain: "{{ bind9_forward_zone_name }}"
ldap_base_dn: "dc={{ ldap_domain | regex_replace('\\.', ',dc=') }}"
ldap_fqdn: "ldap.{{ ldap_domain }}"
ldap_uri: "ldaps://{{ ldap_fqdn }}:636"

ldap_groups:
  ta:
    gid: 10000
    member_uids: [generalta, mailta]
  stu:
    gid: 20000
    member_uids: [stu]

ldap_users:
  generalta:
    uid_number: 10000
    gid_number: 10000
    home: /u/ta/generalta
    mail: "generalta@{{ ldap_domain }}"
    groups: [ta]
    ssh_public_key: "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIMUa1AsYerXm5/QVrTZ7QxtkcCUfuXop004xu2hOBxNY 2026 NAP"
    totp_required: true
  mailta:
    uid_number: 10001
    gid_number: 10000
    home: /u/ta/mailta
    mail: "mailta@{{ ldap_domain }}"
    groups: [ta]
    ssh_public_key: "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIMUa1AsYerXm5/QVrTZ7QxtkcCUfuXop004xu2hOBxNY 2026 NAP"
    totp_required: false
  stu:
    uid_number: 20000
    gid_number: 20000
    home: /u/stu/stu
    mail: "stu@{{ ldap_domain }}"
    groups: [stu]
    ssh_public_key: "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIMUa1AsYerXm5/QVrTZ7QxtkcCUfuXop004xu2hOBxNY 2026 NAP"
    totp_required: true
```

Passwords, TOTP secret, admin DN password, LDAP service-bind password, and TLS private key belong in `host_vars/ldap-01/secrets.yml`, with a committed `secrets.example.yml` only.

### Pattern 3: LDAPS-Only Server Boundary

**What:** Remote consumers use `ldaps://ldap.<STUID>.nasa:636`; config management uses local `ldapi:///` on `ldap-01`. Do not expose LDAP port 389 or rely on StartTLS.  
**When to use:** The assignment explicitly says LDAPS and “not LDAP over TLS (StartTLS).”  
**Trade-offs:** Self-signed certificate distribution becomes mandatory, but the boundary is simple and testable.

Implementation implications:

- Slapd should listen on `ldapi:///` and `ldaps:///`; avoid `ldap:///` unless a package needs it locally and firewall keeps 389 closed.
- Certificate SANs must include `DNS:ldap.<STUID>.nasa` and `IP:172.16.1.10`.
- The public certificate/CA material must be available to `ldap-client` and `mail`; the private key stays on `ldap-01`.
- Prefer inventory-supplied cert/key material over “generate on server then fetch” to avoid two-pass Ansible convergence.

### Pattern 4: NFSv4-Only `/u` Home Export

**What:** Export `/u` from `ldap-01` over NFSv4 and mount it at `/u` on both workstations.  
**When to use:** Synchronized lab home directories across two DMZ workstations.  
**Trade-offs:** NFSv4-only avoids `rpcbind`/dynamic port firewall complexity. It still relies on consistent LDAP UIDs/GIDs, so UID/GID constants must match LDAP entries.

Recommended server directory ownership should use numeric IDs so the LDAP server does not need to become an LDAP client of itself:

```text
/u                    root:root      0755
/u/ta                 root:root      0755
/u/ta/generalta       10000:10000    0711
/u/ta/mailta          10001:10000    0711
/u/stu                root:root      0755
/u/stu/stu            20000:20000    0711
```

Critical router integration: because the router currently masquerades DMZ/internal traffic, add `172.16.1.10/32` to `firewall_masquerade_exempt_destinations` or an equivalent preserve-source rule. Otherwise the NFS server will see both workstations as the router IP, and workstation-specific exports/logging will be unreliable.

### Pattern 5: Workstation Access as Host-Specific Policy

**What:** The same `ldap-client` role runs on both workstations, but host vars control who can log in and what sudo rules apply.  
**When to use:** `ta` can log into both workstations; `stu` can log into workstation1 only; `stu` sudo is limited to `ls`.  
**Trade-offs:** Host vars must be explicit; do not infer access from hostname strings inside templates.

Recommended host-specific policy:

```yaml
# workstation1/main.yml
ldap_client_enabled: true
nfs_client_enabled: true
ldap_client_allowed_groups:
  - ta
  - stu

# workstation2/main.yml
ldap_client_enabled: true
nfs_client_enabled: true
ldap_client_allowed_groups:
  - ta
```

The `openldap` role should create sudoRole entries under `ou=SUDOers` that match this policy:

- `ta`: `sudoHost: ALL`, `sudoCommand: ALL`, users/group mapped to TA group.
- `stu`: `sudoHost: workstation1` / `workstation1.<STUID>.nasa`, `sudoCommand: /usr/bin/ls` (and possibly `/bin/ls` if AlmaLinux path validation shows both are needed).

### Pattern 6: Mail LDAP Is a Consumer, Not a Workstation Client

**What:** `dmz-client-01` mail services query LDAP over LDAPS; it should not receive the full OS-login `ldap-client` role unless a future requirement says TA users must SSH into the mail host.  
**When to use:** Existing Dovecot LDAP passdb scaffolding already exists and is gated behind `mail_ldap_enabled`.  
**Trade-offs:** Mail gets LDAP auth without changing system NSS/PAM on the mail server.

Existing mail role integration points:

- `mail_ldap_enabled: true`
- `mail_ldap_host: "{{ ldap_fqdn }}"`
- `mail_ldap_uri: "{{ ldap_uri }}"`
- `mail_ldap_base_dn: "{{ ldap_base_dn }}"`
- `mail_ldap_ca_cert: "{{ ldap_tls_ca_certificate }}"`
- `mail_ldap_ca_cert_path: /etc/pki/ca-trust/source/anchors/ldap-ca.crt`

The current Dovecot template binds users as `uid=%n,ou=People,<baseDN>`. That is the correct connection direction, but the mail role still needs a group-membership gate for the HW1-2 LDAP requirements: only `ta` users (`generalta`, `mailta`) should be mail-valid; `stu` should not become a mail user just because it is a `posixAccount`. Implement that gate from the same LDAP group data, either through a verified LDAP group filter/memberOf strategy or an inventory-rendered allow-list derived from `ldap_groups.ta.member_uids`. Do not maintain a separate hand-written mail LDAP user list.

## Data Flow

### Full Converge Flow

```text
site.yml
  ↓
bootstrap.yml
  ├── router-01: base → firewall → routing → network → wireguard
  └── dmz/internal hosts including ldap-01/workstation1/workstation2:
      base → firewall → network → wireguard if explicitly enabled → docker if enabled
  ↓
dns_configure.yml
  ├── bind9 publishes ldap/workstation A/PTR records
  ├── secondary-ns-01 mirrors zones through existing transfer path
  └── DNS client resolver restoration includes new LDAP/workstation hosts
  ↓
ldap_configure.yml
  └── ldap-01: openldap role configures LDAPS, OLC, schema, DIT, ACLs, overlays
  ↓
nfs_configure.yml
  ├── ldap-01: nfs role creates /u tree and exports it
  └── workstation1/workstation2: nfs role mounts /u
  ↓
workstation_configure.yml
  └── workstation1/workstation2: ldap-client role configures SSSD/PAM/SSH/sudo/TOTP
  ↓
mail_configure.yml
  └── dmz-client-01: existing mail role enables Dovecot LDAP passdb when mail_ldap_enabled=true
```

### LDAP Authentication Flow on Workstations

```text
SSH login to workstation1/workstation2
  ↓
sshd
  ├── publickey path:
  │     AuthorizedKeysCommand → SSSD/LDAP sshPublicKey lookup
  │     PAM auth TOTP is not required for successful public key auth
  │
  └── password path:
        PAM/SSSD binds against LDAPS uid=<user>,ou=People,<baseDN>
        ↓
        ldap-client TOTP PAM step checks LDAP-backed TOTP secret for generalta/stu
        ↓
        SSSD access control checks host-specific allowed groups
        ↓
        session opens with /u/<group>/<user> home on NFS
```

### NFS Home Sync Flow

```text
workstation1:/u  ─┐
                  ├── NFSv4 tcp/2049 through router DMZ→internal policy ──▶ ldap-01:/u
workstation2:/u  ─┘

LDAP provides consistent UID/GID identity:
  generalta = 10000:10000
  mailta    = 10001:10000
  stu       = 20000:20000
```

Because both workstations mount the same server-side `/u`, file changes synchronize by design. Do not attempt rsync, unison, or per-workstation local home reconciliation unless NFS is impossible.

### Mail LDAP Flow

```text
SMTP/IMAP auth for LDAP user on dmz-client-01
  ↓
Dovecot passdb ldap
  ↓ LDAPS tcp/636 through existing dmz-to-internal-ldaps router policy
ldap-01 OpenLDAP
  ├── authenticate bind as uid=<user>,ou=People,<baseDN>
  └── allow only TA group users for mail behavior
```

## DNS Integration

Add records through the existing `bind9_zones[].records` model on `primary-ns-01`; do not add DNS-writing logic to LDAP roles.

| Record | Private view | Public view recommendation | Notes |
|--------|--------------|----------------------------|-------|
| `ldap.<STUID>.nasa A` | `172.16.1.10` | Prefer omit or return only if assignment/OJ public-view check requires it | LDAP is a private-zone service. Workstations and mail resolve through `dns-01` private path. |
| `workstation1.<STUID>.nasa A` | `172.16.0.11` | Use the existing public-view pattern only if OJ needs to resolve it externally | The critical clients are inside DMZ/private resolver path. |
| `workstation2.<STUID>.nasa A` | `172.16.0.12` | Same as workstation1 | Avoid inventing DNAT/WireGuard exposure until a grading path requires it. |
| Reverse PTRs | Add `.10` in internal reverse and `.11/.12` in DMZ reverse | Public reverse only if VPN public A records are added | Helps diagnostics; not explicitly graded but low risk. |

If the OJ checks public DNS for workstation names, mirror the existing public-view style deliberately in a separate phase. Do not accidentally expose `ldap` publicly just to satisfy a DNS record checklist; LDAPS should remain private unless the spec explicitly demands VPN-side access.

## Firewall Integration

### Router (`host_vars/router-01/main.yml`)

Keep the existing `dmz-to-internal-ldaps` policy for tcp/636. Add NFSv4 access for workstation mounts and preserve source IPs to the LDAP/NFS host.

Recommended changes:

```yaml
firewall_masquerade_exempt_destinations:
  - 172.16.1.153/32  # existing dns-01 resolver exemption
  - 172.16.1.10/32   # NEW ldap/nfs server; preserves workstation source IPs

firewall_policies:
  # existing dmz-to-internal-ldaps remains
  - name: dmz-to-internal-nfs
    priority: -54
    target: ACCEPT
    ingress_zones: [dmz]
    egress_zones: [internal]
    protocols: [tcp]
    ports:
      - port: 2049
        proto: tcp
```

If the firewall role gains rich source/destination policy support, scope NFS to `workstation1`/`workstation2` sources and `ldap-01` destination. Until then, host firewall and NFS export restrictions provide the second layer.

### LDAP/NFS host (`ldap-01`)

Open only:

- `636/tcp` on internal zone for LDAPS.
- `2049/tcp` on internal zone for NFSv4.

Avoid opening `389/tcp` unless implementation validation proves a local-only listener cannot satisfy management needs. Use `ldapi:///` for Ansible configuration operations.

### Workstations

No inbound LDAP or NFS service ports. Keep only whatever SSH exposure the existing lab/grading path requires. Workstations initiate LDAPS and NFS connections to private zone.

## Playbook Ordering and Build Phases

### Phase 1: Topology and cloud-init foundation

**Build:** `cloud-init/iid-ldap-01`, `iid-workstation1`, `iid-workstation2`; inventory entries under `internal`/`dmz`; functional groups `ldap_servers`, `workstations`, `ldap_clients`, `nfs_servers`, `nfs_clients`; host vars and secret examples.  
**Verify:** `ansible-inventory --graph`; `bootstrap.yml` reaches all new hosts; router-first ordering still works.  
**Avoids:** debugging LDAP before routing, DNS, and host bootstrap are stable.

### Phase 2: DNS and firewall integration

**Build:** private-view A/PTR records for LDAP/workstations; update DNS client resolver play to include new hosts; add router NFS policy and `ldap-01` masquerade exemption; open `636/tcp` and `2049/tcp` on `ldap-01`.  
**Verify:** `dig ldap.<STUID>.nasa @172.16.1.153` from DMZ resolves to `172.16.1.10`; workstations resolve their own names; DMZ can connect to `ldap-01:636` after service exists.  
**Avoids:** certificate hostname failures and NFS export source-IP surprises.

### Phase 3: OpenLDAP server

**Build:** `openldap` role: LDAPS-only server, OLC config, base DN, OUs, users, groups, ACLs, ppolicy, TOTP schema/data, Fortune schema/data, sssvlv.  
**Verify:** LDAPS search with CA trust; ACL checks for password read/write; ppolicy checks; Fortune sorting/pagination; no 389 exposure.  
**Research flag:** TOTP enforcement mechanics and password-quality character-class module need implementation validation on AlmaLinux packages.

### Phase 4: NFS home export

**Build:** `nfs` role server mode on `ldap-01`: `/u` tree, numeric ownership, NFSv4-only export, `nfs-server` enabled.  
**Verify:** `showmount`/NFSv4 mount test from a workstation; created files on one workstation appear on the other; ownership resolves after LDAP client config.  
**Avoids:** fake “sync” solutions and local-only home directories.

### Phase 5: Workstation LDAP clients

**Build:** `ldap-client` role on `workstation1`/`workstation2`: CA trust, SSSD, NSS/PAM, sshPublicKey lookup, sudo LDAP, host-specific access, TOTP password path.  
**Verify:** `generalta` SSH key and password+TOTP work on both; `stu` works on workstation1 only; `stu` denied on workstation2; sudo policy matches assignment; reboot retains auth and mounts.  
**Avoids:** configuring clients before LDAP/NFS are available.

### Phase 6: Mail LDAP integration

**Build:** set `mail_ldap_enabled: true`, wire mail variables to shared LDAP variables/cert, enforce TA-only mail users, keep local users working.  
**Verify:** `mailta` and `generalta` authenticate to SMTP/IMAP if required; `stu` does not; existing local `admin`/`test` and HW1-2 mail tests still pass.  
**Avoids:** breaking mail role while LDAP server/schema is still moving.

## New vs Modified Components

### New Components

| Component | Type | Responsibility |
|-----------|------|----------------|
| `ldap-01` | VM/inventory host | Private-zone OpenLDAP + NFS home server. |
| `workstation1`, `workstation2` | VM/inventory hosts | DMZ LDAP/NFS client workstations. |
| `ldap_servers`, `workstations`, `ldap_clients`, `nfs_servers`, `nfs_clients` | Inventory groups | Functional targeting while retaining topology groups. |
| `openldap` role | Ansible component role | Server-side LDAP service, schema, overlays, ACLs, data. |
| `ldap-client` role | Ansible component role | Workstation OS auth, SSH keys, sudo, TOTP. |
| `nfs` role | Ansible component role | NFSv4 export and client mounts. |
| `ldap_configure.yml` | Playbook | Runs OpenLDAP server configuration after DNS. |
| `nfs_configure.yml` | Playbook | Runs NFS server before NFS clients. |
| `workstation_configure.yml` | Playbook | Runs LDAP client auth after LDAP/NFS are available. |
| `group_vars/all/ldap.yml` | Shared vars | LDAP domain, base DN, users, groups, service FQDN, certificate public data. |
| `group_vars/all/nfs.yml` | Shared vars | `/u` paths, export clients, NFS protocol options. |
| `host_vars/ldap-01/secrets.example.yml` | Secret shape | Admin password hash, user password hash source, TOTP secret, TLS private key shape. |

### Modified Components

| Component | Modification | Why |
|-----------|--------------|-----|
| `ansible/inventory/hosts.yml` | Add new hosts under `internal`/`dmz`; add functional groups | Lets existing bootstrap pick up new VMs and new service playbooks target capabilities. |
| `ansible/playbooks/site.yml` | Import new playbooks between DNS and mail | Enforces DNS before services, LDAP before clients/mail, NFS server before mounts. |
| `ansible/playbooks/dns_configure.yml` | Include new hosts in DNS client resolver restoration, preferably via a reusable group rather than hardcoded host union | New hosts need final resolver `172.16.1.153` after DNS is live. |
| `host_vars/primary-ns-01/main.yml` | Add A/PTR records for LDAP/workstations | Existing BIND role remains DNS source of truth. |
| `host_vars/router-01/main.yml` | Add NFSv4 policy and `ldap-01` masquerade exemption; keep LDAPS policy | Workstations need DMZ→private LDAPS/NFS with correct source identity. |
| `host_vars/dmz-client-01/main.yml` / secrets | Flip `mail_ldap_enabled`, provide LDAP CA/bind vars if needed | Existing mail role becomes LDAP consumer after server exists. |
| `mail` role templates/asserts | Enforce TA group membership and avoid failing due to missing anonymous search if ACLs require service bind | HW1-2 LDAP requirements need `ta` mail users only. |
| Cloud-init seed generation process | Add three seed directories/ISOs following existing naming and `eth0` convention | New VMs must provision reproducibly. |

## Anti-Patterns

### Anti-Pattern 1: Reusing DNS or Agent Hosts for LDAP

**What people do:** Install slapd and NFS on `primary-ns-01`, `dns-01`, or `internal-agent-01` to avoid a VM.  
**Why it is wrong:** It couples identity secrets, schema churn, NFS exports, and package/firewall changes to previous-lab services that must keep passing.  
**Do this instead:** Add `ldap-01` in private zone and keep prior roles unchanged except for DNS/firewall integration.

### Anti-Pattern 2: Hiding NFS Inside the LDAP Role

**What people do:** Have `openldap` create `/u`, edit `/etc/exports`, and mount clients.  
**Why it is wrong:** NFS is a separate service with server and client responsibilities; hiding it makes ordering and verification unclear.  
**Do this instead:** Use a dedicated `nfs` component role with explicit server/client mode.

### Anti-Pattern 3: Configuring Workstations in Cloud-Init

**What people do:** Put SSSD, PAM, sudo, NFS mounts, or LDAP secrets into cloud-init user-data.  
**Why it is wrong:** It bypasses Ansible idempotency, leaks secret/config shape into provisioning, and makes rebuilds inconsistent with role behavior.  
**Do this instead:** Cloud-init only creates the VM network/admin bootstrap; all LDAP/NFS behavior belongs to Ansible.

### Anti-Pattern 4: Enabling Mail LDAP Before LDAP Is Verifiable

**What people do:** Set `mail_ldap_enabled: true` as soon as variables exist.  
**Why it is wrong:** The mail role already asserts LDAP reachability and CA presence; premature enablement can break previously passing mail tests.  
**Do this instead:** Flip mail LDAP only after LDAPS, CA trust, base DN, users, and TA group behavior pass direct LDAP verification.

### Anti-Pattern 5: Forgetting Router Masquerade Effects on NFS

**What people do:** Export `/u` only to `172.16.0.11/32` and `172.16.0.12/32` while the router still masquerades DMZ traffic to internal.  
**Why it is wrong:** The NFS server may see source `172.16.1.254` instead of the workstation IPs, causing export restrictions and logs to lie.  
**Do this instead:** Preserve source IPs for destination `ldap-01` or intentionally export to the observed router source with the risk documented. Preserving source is cleaner.

### Anti-Pattern 6: Treating TOTP as “Just an LDAP Attribute”

**What people do:** Store `oathSecret` in LDAP and assume SSH password logins now require TOTP.  
**Why it is wrong:** LDAP stores identity data; the SSH/PAM path enforces authentication factors. Public-key exemption also lives in the client auth flow.  
**Do this instead:** `openldap` owns schema/secret attributes; `ldap-client` owns PAM enforcement and must test password+TOTP vs SSH-key-only paths.

## Integration Points

### External Services

| Service | Integration Pattern | Notes |
|---------|---------------------|-------|
| Online Judge / TA VPN | Existing router/WireGuard/DNS path | Do not add public LDAP exposure unless OJ requires it. Workstation exposure should follow existing lab grading path, not ad hoc DNAT. |
| OJ Tools secrets | `host_vars/ldap-01/secrets.yml` | `TA_PASSWORD` and `TOTP_secret` are generated externally; commit only shape in `secrets.example.yml`. |
| AlmaLinux/RHEL packages | `openldap`, `sssd`, `nfs-utils`, `sudo`, PAM/TOTP package | Package names and module support need phase validation on the image actually used. |

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| DNS ↔ LDAP/NFS/workstations | Inventory variables into BIND zone records | DNS publishes names; service roles do not edit zone files. |
| Router firewall ↔ LDAP/NFS | Firewalld policies and masquerade exemptions | Existing LDAPS policy is reused; NFSv4 requires a new policy. |
| LDAP server ↔ Workstations | LDAPS 636, NFSv4 2049 | LDAP auth and home mounts cross DMZ→private boundary. |
| LDAP server ↔ Mail | LDAPS 636 | Mail is an LDAP consumer only; no full OS LDAP client role on mail host by default. |
| NFS ↔ LDAP identity | Shared UID/GID vars | NFS uses numeric ownership; LDAP/SSSD resolves names on clients. |
| Workstation sshd ↔ LDAP | SSSD/AuthorizedKeysCommand/PAM | SSH key auth must be exempt from TOTP; password auth must require TOTP for selected users. |

## Scaling Considerations

| Scale | Architecture Adjustments |
|-------|--------------------------|
| Course lab / 2 workstations | Single `ldap-01` with OpenLDAP + NFS is correct. Keep phase ordering and verification strict. |
| More lab clients | Keep one LDAP server; expand `ldap_clients`/`nfs_clients`; consider source-specific firewall/rich rules and NFS export generation from inventory. |
| Production-like environment | Split NFS from LDAP, add LDAP replication/backup, Kerberos or stronger NFS security, monitoring, and certificate lifecycle management. Out of scope for HW1-3. |

### Scaling Priorities

1. **First bottleneck:** configuration correctness, not performance. Validate LDAPS trust, ACLs, and PAM/NFS behavior after reboot.
2. **Second bottleneck:** NFS/firewall source-IP handling. Preserve source IPs before relying on per-workstation exports.
3. **Do not optimize early:** LDAP HA, Kerberos NFS, and multi-provider replication are unnecessary for this milestone and add grading risk.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Host placement | HIGH | Assignment and project context explicitly require LDAP private zone and workstations DMZ; new dedicated VM best preserves existing DNS/mail/agent services. |
| Role boundaries | HIGH | Matches repo convention: component roles (`base`, `firewall`, `network`, `bind9`, `mail`) and topology/functional inventory split. |
| Playbook ordering | HIGH | Existing `site.yml` and mail role assertions make dependency direction clear. |
| NFS server placement | HIGH | Synchronized homes across two workstations are best served by one private NFS server colocated with identity for lab scope. |
| OpenLDAP ppolicy/sssvlv/TLS | HIGH | Verified through OpenLDAP docs and assignment spec; implementation still needs package-level tests. |
| SSSD/PAM/TOTP exact implementation | MEDIUM | Architecture is sound, but package names/module semantics for password+TOTP and SSH-key exemption need phase-specific validation. |
| Mail TA-group LDAP filter | MEDIUM | Current mail scaffold connects correctly over LDAPS but needs final group-membership enforcement strategy. |

## Sources

- Project context: `.planning/PROJECT.md`, read 2026-05-28. Confidence: HIGH.
- Assignment spec: `lab/ldap.md`, read 2026-05-28. Confidence: HIGH.
- Existing repo architecture: `ansible/inventory/hosts.yml`, `ansible/playbooks/site.yml`, `bootstrap.yml`, `dns_configure.yml`, `mail_configure.yml`, `host_vars/router-01/main.yml`, `host_vars/primary-ns-01/main.yml`, `group_vars/all/dns_identity.yml`, `group_vars/all/mail_dns.yml`, mail role LDAP defaults/templates/asserts, and cloud-init examples, read 2026-05-28. Confidence: HIGH.
- Graphify project graph query: “How should HW1-3 LDAP integrate with existing DNS, firewall, mail, and Ansible playbooks?”, run 2026-05-28. Confidence: MEDIUM for navigation, verified against files above.
- OpenLDAP documentation via Context7 `/openldap/openldap`: TLS, access control, modules, MDB database, ppolicy examples, and integration patterns; includes OpenLDAP upstream source `https://github.com/openldap/openldap/blob/master/contrib/slapd-modules/ppm/ppm.md`, retrieved 2026-05-28. Confidence: HIGH for ppolicy/TLS/ACL concepts.
- Ansible documentation via Context7 `/ansible/ansible`: playbook roles and role `tasks/main.yml` loading conventions, retrieved 2026-05-28. Confidence: HIGH.
- Red Hat Enterprise Linux 9 documentation: “Deploying an NFS server”, `https://docs.redhat.com/en/documentation/red_hat_enterprise_linux/9/html/configuring_and_using_network_file_services/deploying-an-nfs-server_configuring-and-using-network-file-services`, retrieved 2026-05-28. Confidence: HIGH for NFSv4/NFS service/firewalld guidance.
- SSSD documentation via Context7 `/sssd/sssd`: LDAP provider, NSS/PAM services, sudoRole examples, retrieved 2026-05-28. Context7 source reputation LOW, so confidence MEDIUM and implementation should be validated against installed AlmaLinux man pages/packages.

---
*Architecture research for: HW1-3 LDAP Lab integration*  
*Researched: 2026-05-28*
