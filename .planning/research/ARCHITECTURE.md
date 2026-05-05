# Architecture Research

**Domain:** BIND9 DNS infrastructure for authoritative + recursive service in a segmented lab network
**Researched:** 2026-05-05
**Confidence:** HIGH

## Standard Architecture

### System Overview

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Provisioning / Control Plane                        │
├─────────────────────────────────────────────────────────────────────────────┤
│  Ansible `bind9` role                                                      │
│  ├── package + service setup                                               │
│  ├── named.conf fragments (options / acl / keys / views / zones)           │
│  ├── zone file templates                                                   │
│  ├── TSIG secrets + DNSSEC policy wiring                                   │
│  └── verification (`named-checkconf`, `named-checkzone`, `dig`, `rndc`)   │
└─────────────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                            DNS Service Plane                               │
├──────────────────────────┬──────────────────────────┬───────────────────────┤
│ Primary NS               │ Secondary NS            │ Internal Resolver     │
│ 172.16.1.53              │ 172.16.0.53             │ 172.16.1.153          │
│                          │                         │                       │
│ - authoritative only     │ - authoritative only    │ - recursive only      │
│ - writable zone source   │ - read-only replica     │ - DNSSEC validation   │
│ - split views            │ - split views           │ - cache + forwarders  │
│ - TSIG update target     │ - AXFR/IXFR via TSIG    │ - conditional access  │
│ - DNSSEC signer          │ - public/VPN serving    │   to authoritative NS │
└──────────────┬───────────┴──────────────┬──────────┴─────────────┬─────────┘
               │                           │                        │
               ▼                           ▼                        ▼
┌──────────────────────────┐  ┌──────────────────────────┐  ┌──────────────────┐
│ Authoritative State      │  │ Replica State            │  │ Resolver State   │
│ - zone master files      │  │ - slave zone copies      │  │ - cache DB       │
│ - dynamic journals .jnl  │  │ - transfer journals      │  │ - managed-keys   │
│ - DNSSEC key directory   │  │ - mirrored signed data   │  │ - trust anchors  │
│ - TSIG key material      │  │ - TSIG key material      │  │ - forwarder cfg  │
└──────────────────────────┘  └──────────────────────────┘  └──────────────────┘
```

For this lab, the standard shape is **three separate BIND roles on three hosts**:

1. **Primary authoritative server** is the only writable source of truth.
2. **Secondary authoritative server** receives NOTIFY + AXFR/IXFR from the primary and serves replicated data.
3. **Recursive resolver** is isolated from authoritative write paths and only handles client recursion, caching, and DNSSEC validation.

That separation is the right architecture here. It matches how BIND9 is typically deployed in security-segmented environments and it fits the existing play order in this repo: router/network/firewall first, DNS role after host connectivity is stable.

### Component Responsibilities

| Component | Responsibility | Typical Implementation |
|-----------|----------------|------------------------|
| **Ansible bind9 role** | Owns package install, file layout, config generation, validation, service lifecycle | `tasks/main.yml` importing `assert.yml` + `setup.yml`, then phased task files and handlers |
| **Primary authoritative service** | Holds canonical zone data, accepts dynamic updates, signs zones, sends NOTIFY, permits transfers | `named` with `view`, `zone type primary`, `update-policy`/`allow-update`, `dnssec-policy`, `also-notify`, `allow-transfer` |
| **Secondary authoritative service** | Mirrors primary zones, serves public/internal answers read-only, never accepts updates | `named` with matching `view`, `zone type secondary`, `primaries { ...; }`, TSIG-authenticated transfers |
| **Internal resolver** | Provides recursion to internal clients, validates DNSSEC, caches answers, forwards non-local queries | `named` with `recursion yes`, `dnssec-validation auto`, forwarders, and conditional access to authoritative zones |
| **View / ACL layer** | Separates private vs public answers and limits who can recurse or transfer | `acl` blocks plus per-view `match-clients` rules |
| **Zone data layer** | Stores forward and reverse data for each view and zone type | text zone files for static records, `.jnl` for dynamic changes, secondary transfer databases |
| **Key management layer** | Authenticates updates/transfers and supports DNSSEC signing/validation | TSIG secrets, DNSSEC key directory, managed trust anchors |
| **Operations / control layer** | Reloads config safely and provides health checks | `named-checkconf`, `named-checkzone`, `rndc reload`, `rndc retransfer`, `dig`, `nsupdate` |

## Recommended Project Structure

```text
ansible/playbooks/roles/bind9/
├── defaults/main.yml                 # safe defaults, package/service names, paths
├── meta/argument_specs.yml           # variable schema for authoritative / resolver modes
├── tasks/
│   ├── main.yml                      # START/END + imports
│   ├── assert.yml                    # validate host mode, view definitions, zone schema
│   ├── setup.yml                     # phase orchestration
│   ├── install.yml                   # install bind + utilities
│   ├── config.yml                    # named.conf + include fragments
│   ├── keys.yml                      # TSIG material, DNSSEC directories, permissions
│   ├── zones.yml                     # zone templates, static files, dynamic file bootstrap
│   ├── service.yml                   # enable/reload/restart named
│   └── verify.yml                    # named-checkconf/checkzone + dig/nsupdate checks
├── handlers/main.yml                 # reload/restart named
├── templates/
│   ├── named.conf.j2                 # top-level includes
│   ├── named.options.conf.j2         # options / recursion / logging / dnssec-validation
│   ├── named.acl.conf.j2             # ACLs for internal, vpn, secondaries, updaters
│   ├── named.keys.conf.j2            # TSIG key declarations
│   ├── views/
│   │   ├── authoritative-view.j2     # private/public view blocks for NS hosts
│   │   └── resolver-view.j2          # recursive resolver view block if needed
│   └── zones/
│       ├── primary-zone.j2           # primary zone declarations
│       ├── secondary-zone.j2         # secondary zone declarations
│       ├── forward-zone.j2           # resolver forwarding for internal auth zones
│       └── db.*.j2                   # zone file templates
└── files/
    └── managed-keys/                 # optional static trust-anchor bootstrap if needed

ansible/inventory/host_vars/
├── primary-ns-01/main.yml            # authoritative-primary mode + zone ownership
├── secondary-ns-01/main.yml          # authoritative-secondary mode + transfer source
├── dns-01/main.yml                   # recursive-resolver mode + forwarders
└── */secrets.yml                     # TSIG secrets, uploaded DS/grade inputs if kept local
```

### Structure Rationale

- **Role phases mirror BIND lifecycle:** install → render config → place keys → place zones → validate → start/reload.
- **Mode-specific behavior should be data-driven:** one `bind9` component role, with host vars deciding whether a host is `authoritative_primary`, `authoritative_secondary`, or `resolver`.
- **Config fragments beat one giant `named.conf`:** views, ACLs, keys, and zone declarations change for different hosts; keeping them separate reduces mistakes.
- **Verification deserves its own phase:** DNS work fails in subtle ways; syntax checks and live `dig`/`nsupdate` tests should be first-class tasks, not ad hoc debugging.

## Architectural Patterns

### Pattern 1: Single writable primary, separate read-only secondary

**What:** Only the primary owns editable zone state. The secondary is a replica fed by NOTIFY and zone transfers.
**When to use:** Always for this lab. It matches the grading model and avoids split-brain writes.
**Trade-offs:** Slightly more config and key management, but much simpler failure boundaries and safer dynamic updates.

**Example:**
```namedconf
zone "example.com" IN {
    type primary;
    file "db/example.com.db";
    dnssec-policy default;
    allow-transfer { 192.168.1.2; };
    also-notify { 192.168.1.2; };
};

zone "example.com" IN {
    type secondary;
    file "db/example.com.db";
    primaries { 192.168.1.1; };
};
```

### Pattern 2: Split views at the authoritative tier

**What:** Public and private clients query the same zone names but receive different data through separate BIND `view` blocks.
**When to use:** Required here because `${ID}.nasa` and reverse zones have different internal/public behavior.
**Trade-offs:** Correct for split-horizon DNS, but it increases configuration duplication and makes transfer design more delicate.

**Example:**
```namedconf
view "internal" {
    match-clients { 10.0.0.0/8; };
    recursion yes;
    zone "example.com" {
      type primary;
      file "example-internal.db";
    };
};

view "external" {
    match-clients { any; };
    recursion no;
    zone "example.com" {
      type primary;
      file "example-external.db";
    };
};
```

**Lab implication:** both primary and secondary need the **same view inventory**, not just the same zone names. Treat `private/public view definitions` as shared schema, not host-local improvisation.

**Research flag:** when the **same zone name exists in multiple views**, the secondary's transfer path has to land in the correct primary view. In practice this usually means distinguishing the replication identity per view (for example by source/addressing strategy or TSIG-based matching). Validate this explicitly during implementation; do not assume a flat transfer stanza is enough.

### Pattern 3: Keep recursion on a dedicated resolver

**What:** The resolver answers recursive client queries, validates DNSSEC, caches results, and delegates authoritative questions to the authoritative tier.
**When to use:** Always here. Do not make the primary or secondary public resolvers.
**Trade-offs:** One extra host and one extra config path, but much cleaner security posture and much easier debugging.

**Example:**
```namedconf
options {
    recursion yes;
    dnssec-validation auto;
    forwarders { 1.1.1.1; };
};
```

**Recommendation for this lab:** have the resolver use **conditional forwarding or stub-style delegation** for course-owned authoritative zones, and use public forwarders only for everything else. That avoids duplicating authoritative zone files onto the resolver.

### Pattern 4: Dynamic updates terminate on the primary, not in Git-managed files

**What:** `nsupdate` sends TSIG-authenticated changes to the primary; BIND writes `.jnl` journals and then propagates the updated signed zone to secondaries.
**When to use:** Required because the assignment expects TSIG dynamic updates.
**Trade-offs:** Manual file editing becomes unsafe unless the zone is frozen first, but the update path becomes deterministic and auditable.

**Example:**
```bind
zone "example.com" {
    type master;
    file "zones/db.example.com";
    allow-update { key "my-rndc-key"; };
};
```

## Data Flow

### Authoritative Publish Flow

```text
Ansible templates + secrets
    ↓
Primary NS config + zone master files
    ↓ (named loads config)
Primary serves authoritative answers
    ↓ (zone change)
NOTIFY → Secondary requests IXFR/AXFR via TSIG
    ↓
Secondary updates replica files
    ↓
VPN/public/internal clients receive authoritative answers
```

### Dynamic Update Flow

```text
nsupdate client / grading tool
    ↓ (TSIG signed update)
Primary NS writable view
    ↓
Zone journal (.jnl) updated
    ↓
DNSSEC signer updates signed data
    ↓
NOTIFY to secondary
    ↓
Secondary transfers new zone contents
```

### Recursive Resolution Flow

```text
Internal client
    ↓
Internal Resolver
    ├── if zone is `${ID}.nasa` or course reverse zone
    │      ↓
    │   authoritative NS tier (private view)
    │      ↓
    │   authoritative answer returned
    │
    └── if zone is everything else
           ↓
        public forwarder / upstream
           ↓
        DNSSEC validation
           ↓
        cached answer returned to client
```

### State Management

```text
Primary state
  master zone files + .jnl + DNSSEC key dir
      ↓ transfer/sign
Secondary state
  slave copies + transfer metadata

Resolver state
  cache + managed-keys / trust anchors
```

### Key Data Flows

1. **Primary → Secondary replication:** zone changes move via NOTIFY, then IXFR/AXFR, authenticated by TSIG.
2. **Updater → Primary write path:** dynamic records must flow into the primary only; the secondary never accepts updates.
3. **Resolver → Authoritative path:** internal recursive queries for course-owned zones should resolve through the authoritative tier, not a duplicated local zone database.
4. **Resolver → Internet path:** non-course domains flow to upstream forwarders and are DNSSEC-validated before being returned.

## Build Order Implications

Recommended implementation order for the roadmap:

1. **Shared role skeleton + variable schema**
   - Define host modes, views, zone declarations, TSIG secret inputs, and verification toggles.
   - Reason: every later phase depends on consistent data shape.

2. **Primary authoritative static path**
   - Install BIND, render base config, create private/public views, and load static forward/reverse zones.
   - Reason: the primary is the source of truth for every downstream DNS component.

3. **Transfer and update security layer**
   - Add TSIG declarations, `allow-transfer`, `also-notify`, and dynamic update policy.
   - Reason: secondary replication and grading updates depend on authenticated write/replication paths.

4. **DNSSEC signing on the primary**
   - Enable `dnssec-policy` / signing for the graded forward + VPN reverse zones.
   - Reason: the resolver and Online Judge both depend on signed authoritative data existing first.

5. **Secondary replica**
   - Mirror the view structure, configure `type secondary` zones, and verify transfer convergence.
   - Reason: the secondary cannot be validated until the primary serves stable, signed zones.

6. **Internal resolver**
   - Enable recursion, forwarders, DNSSEC validation, and conditional routing for authoritative zones.
   - Reason: resolver behavior only makes sense after authoritative servers answer correctly.

7. **End-to-end verification**
   - Test `dig` against private/public views, `nsupdate` propagation, IXFR/AXFR, AD bit, and reverse lookups.
   - Reason: BIND failures are often cross-component, not local syntax errors.

## Scaling Considerations

| Scale | Architecture Adjustments |
|-------|--------------------------|
| **Course lab / tens of clients** | Keep exactly this three-node design. No need for catalog zones, anycast, or hidden-primary extras beyond the current topology. |
| **Hundreds to low thousands of queries** | Add another secondary before touching the primary. Caching on the resolver absorbs most growth. |
| **Large public deployment** | Move toward a hidden primary, multiple public secondaries, tighter transfer topology, and more explicit monitoring/automation around DNSSEC rollover. |

### Scaling Priorities

1. **First bottleneck:** mis-modeled configuration, not raw throughput. Split views, TSIG, and DNSSEC mistakes are more likely than CPU limits.
2. **Second bottleneck:** operational safety. Manual edits to dynamic/signed zones become the main source of outages before query volume does.

## Anti-Patterns

### Anti-Pattern 1: Mixing authoritative writes and recursion on the same exposed server

**What people do:** Turn the primary or secondary into a recursive resolver for convenience.
**Why it's wrong:** Blurs security boundaries, complicates view logic, and makes debugging graded behavior much harder.
**Do this instead:** Keep the authoritative tier authoritative-only and use the dedicated internal resolver for recursion.

### Anti-Pattern 2: Treating split views as only a query-time concern

**What people do:** Define private/public views on the primary, then configure a flat secondary.
**Why it's wrong:** The secondary will not mirror the same answer space, and transfer behavior for same-name zones becomes ambiguous.
**Do this instead:** Model view structure as a first-class shared component across both authoritative servers.

### Anti-Pattern 3: Editing dynamic zone files directly after enabling updates

**What people do:** Keep templating or hand-editing zone files as if they were static even after dynamic updates are enabled.
**Why it's wrong:** BIND writes updates to journals; direct edits drift from runtime state unless you freeze/thaw or sync deliberately.
**Do this instead:** Use `nsupdate` for live changes and reserve file templating for initial static bootstrap only.

## Integration Points

### External Services

| Service | Integration Pattern | Notes |
|---------|---------------------|-------|
| **Router / firewalld** | network path + port exposure for TCP/UDP 53 and transfer/update flows | Already provisioned before `bind9`; DNS design should assume router/firewall are prerequisites, not bind9 responsibilities |
| **Course root / upstream authoritative path (`192.168.255.1`)** | resolver reaches course namespace through upstream delegation path | Needed for graded recursive resolution of `nasa.` / `168.192.in-addr.arpa` |
| **Cloudflare `1.1.1.1`** | resolver forwarder for non-course Internet names | Keep this only on the recursive resolver, not the authoritative servers |
| **Online Judge / grading tooling** | `dig`, `nsupdate`, DS submission, TSIG submission | Treat grader-facing behavior as external contract; verify public/VPN path explicitly |

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| **Ansible role ↔ host_vars** | variable-driven configuration | One role should support three host modes; avoid separate "primary role" / "resolver role" forks |
| **Primary ↔ Secondary** | NOTIFY + AXFR/IXFR over TCP/53, authenticated with TSIG | This is the authoritative replication boundary |
| **Updater ↔ Primary** | dynamic update over DNS message flow, authenticated with TSIG | Only primary crosses this boundary |
| **Resolver ↔ Authoritative servers** | recursive lookup boundary, ideally conditional forwarding/stub for lab-owned zones | Keep resolver stateless with respect to authoritative source data except cache |
| **Clients ↔ Resolver / Secondary** | normal DNS query traffic over UDP/TCP 53 | Internal clients should prefer resolver; VPN/public checks should hit secondary authoritative service |

## Sources

- ISC BIND 9 Administrator Reference Manual / reference docs — views, `also-notify`, zone configuration: https://bind9.readthedocs.io/en/stable/reference
- ISC BIND 9 DNSSEC Guide — `dnssec-policy` on primary zones and `dnssec-validation auto`: https://bind9.readthedocs.io/en/stable/dnssec-guide
- ISC BIND 9 documentation — dynamic update with TSIG / `nsupdate`: https://bind9.readthedocs.io/en/stable/chapter7
- ISC BIND 9 documentation — `rndc freeze`, `thaw`, `sync` for dynamic zones: https://bind9.readthedocs.io/en/stable/chapter6
- Repository context: `.planning/PROJECT.md`, `.planning/codebase/ARCHITECTURE.md`, `ansible/playbooks/bootstrap.yml`, and current host vars for `primary-ns-01`, `secondary-ns-01`, `dns-01`, `router-01`

---
*Architecture research for: BIND9 DNS infrastructure (HW1-1)*
*Researched: 2026-05-05*
