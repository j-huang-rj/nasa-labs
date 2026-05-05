<!-- refreshed: 2026-05-05 -->
# Architecture

**Analysis Date:** 2026-05-05

## System Overview

This is an infrastructure-as-code repository for a multi-VM network lab environment (NASA/Network Administration course). It provisions a router-based network topology with DMZ and Private security zones, WireGuard VPN tunnels, firewalld policies, Docker workloads, and BIND9 DNS servers — all managed through Ansible automation and cloud-init VM seeding.

```text
┌─────────────────────────────────────────────────────────────────────────┐
│                        Playbook Layer                                    │
│                  `ansible/playbooks/bootstrap.yml`                       │
│   Orchestrates role application across host groups in dependency order  │
├─────────────────────────────────────────────────────────────────────────┤
│                      Profile Role (bootstrap.yml)                        │
│  ┌────────────┐ ┌──────────┐ ┌─────────┐ ┌────────┐ ┌───────────┐    │
│  │   Router    │ │   DMZ    │ │Private  │ │  DNS   │ │   NS      │    │
│  │   Hosts     │ │  Hosts   │ │ Hosts   │ │ Hosts  │ │  Hosts    │    │
│  └─────┬──────┘ └────┬─────┘ └────┬────┘ └───┬────┘ └─────┬─────┘    │
│        │              │            │           │             │          │
│        │  Applies Component Roles in order:   │             │          │
│        │  base → firewall → routing →         │             │          │
│        │  network → wireguard                 │             │          │
├────────┴──────────────┴────────────┴───────────┴─────────────┴──────────┤
│                       Component Roles                                    │
│   `ansible/playbooks/roles/{base,firewall,routing,network,             │
│                             wireguard,docker,bind9}`                    │
│  Each role: assert → install → setup → (handler flush)                 │
├─────────────────────────────────────────────────────────────────────────┤
│                      Variable Layer (host_vars)                         │
│  `ansible/inventory/host_vars/{host}/main.yml`                          │
│  `ansible/inventory/host_vars/{host}/secrets.yml` (gitignored)         │
│  Generic variable names drive host-agnostic roles                       │
├─────────────────────────────────────────────────────────────────────────┤
│                     Cloud-Init Seeding Layer                             │
│  `cloud-init/iid-{vm}/` — user-data.yml, network-config.yml,           │
│  meta-data.yml → seed.iso for initial VM bootstrapping                 │
└─────────────────────────────────────────────────────────────────────────┘
```

## Component Responsibilities

| Component | Responsibility | File |
|-----------|----------------|------|
| **bootstrap.yml** | Top-level playbook; maps component roles to host groups | `ansible/playbooks/bootstrap.yml` |
| **base role** | SSH connectivity check, OS assertion (RHEL family), system upgrade, package install, reboot checkpoint | `ansible/playbooks/roles/base/` |
| **firewall role** | Install firewalld, create custom zones, reconcile policies (ingress/egress zones, ports, protocols), masquerade, forward ports, rich rules, zone-to-interface bindings | `ansible/playbooks/roles/firewall/` |
| **routing role** | Enable kernel IPv4 forwarding via sysctl | `ansible/playbooks/roles/routing/` |
| **network role** | Configure NetworkManager connections (nmcli), rename default connections, assign firewalld zones, activate interfaces | `ansible/playbooks/roles/network/` |
| **wireguard role** | Install wireguard-tools, template `wg0.conf`, enable WireGuard tunnel | `ansible/playbooks/roles/wireguard/` |
| **docker role** | Install Docker CE, configure binfmt multi-arch emulation, load image archives, deploy containers | `ansible/playbooks/roles/docker/` |
| **bind9 role** | BIND9 DNS server configuration (stub — not yet implemented) | `ansible/playbooks/roles/bind9/` |
| **hosts.yml** | Inventory with SSH connection details and ProxyJump configuration | `ansible/inventory/hosts.yml` |
| **group_vars/all.yml** | Global defaults: feature flags, built-in zone list | `ansible/inventory/group_vars/all.yml` |
| **host_vars/{host}/main.yml** | Per-host network interfaces, firewall policies, docker workloads | `ansible/inventory/host_vars/*/main.yml` |
| **host_vars/{host}/secrets.yml** | Per-host WireGuard secrets (gitignored) | `ansible/inventory/host_vars/*/secrets.yml` |
| **cloud-init/** | VM seed data (user-data, meta-data, network-config) for each VM | `cloud-init/iid-*/` |
| **manual/** | Step-by-step human-readable guides equivalent to the Ansible automation | `manual/bootstrap.md`, `manual/dns.md` |
| **lab/** | Assignment PDFs and specs from the course | `lab/` |

## Pattern Overview

**Overall:** Ansible-driven declarative infrastructure-as-code with idempotent component roles

**Key Characteristics:**
- **Component Role pattern:** Each role is a self-contained, host-agnostic unit controlled by variables. No "router role" or "agent role" — behavior is driven entirely by `host_vars` data.
- **Variable-driven host specificity:** Generic variable names (`network_interfaces`, `firewall_policies`, etc.) ensure roles work on any host. The host's `main.yml` dictates what gets configured.
- **Feature flags:** `wireguard_enabled`, `docker_enabled`, `bind9_enabled`, `base_upgrade_enabled` in `group_vars/all.yml` and per-host `main.yml` control which roles execute.
- **Secret split:** Per-host secrets are separated into gitignored `secrets.yml` files, tracked as `secrets.example.yml` templates.
- **Reconciliation pattern:** The firewall role queries current state before applying changes and removes stale entries (zones, ports, policies), achieving idempotency rather than additive-only configuration.
- **Logging convention:** Every role and phase uses `START`/`END` and `PHASE [<name> : START/END]` debug markers.
- **Cloud-init + Ansible split:** VM initial provisioning (user, SSH key, hostname, basic network) is handled by cloud-init seed ISOs. Ansible takes over after SSH is available.

## Layers

**Playbook Layer:**
- Purpose: Define execution order and host-to-role mapping
- Location: `ansible/playbooks/bootstrap.yml`
- Contains: Two plays — "Router Bootstrap" (router group) and "Zone Hosts Bootstrap" (dmz + internal groups)
- Depends on: All component roles
- Used by: Operator runs `ansible-playbook bootstrap.yml`

**Role Layer:**
- Purpose: Encapsulate host-agnostic configuration logic for one subsystem
- Location: `ansible/playbooks/roles/`
- Contains: `base/`, `firewall/`, `routing/`, `network/`, `wireguard/`, `docker/`, `bind9/`
- Depends on: Per-host variables from inventory
- Used by: Playbook layer

**Variable Layer:**
- Purpose: Supply host-specific data that drives role behavior
- Location: `ansible/inventory/host_vars/{host}/main.yml`, `ansible/inventory/group_vars/all.yml`
- Contains: Network interface definitions, firewall policies, docker workloads, WireGuard config
- Depends on: Role argument specs define expected schema
- Used by: Role layer reads these variables

**Cloud-Init Layer:**
- Purpose: Create initial VM state (user accounts, SSH keys, basic network config, hostname) before Ansible can reach the host
- Location: `cloud-init/iid-*/`
- Contains: `user-data.yml`, `meta-data.yml`, `network-config.yml` per VM, plus generated `seed.iso`
- Depends on: Virtualization platform (UTM/QEMU)
- Used by: Boot-time VM initialization

**Documentation Layer:**
- Purpose: Human-readable procedures mirroring the Ansible automation
- Location: `manual/`
- Contains: Step-by-step bash commands for manual setup (`bootstrap.md`)
- Depends on: Manual context uses `enp0s*` interface names (not `eth*`)
- Used by: Operators who prefer manual setup or want to understand the automation

## Data Flow

### Primary Bootstrap Flow

1. **Cloud-init seeds VM** — `cloud-init/iid-{vm}/user-data.yml` creates user, sets SSH key (`cloud-init/iid-{vm}/user-data.yml:1`)
2. **Operator builds seed ISO** — `cloud-init/iid-{vm}/seed.iso` is generated from the YAML templates
3. **Ansible connects** — SSH via `ansible/inventory/hosts.yml` (router direct, agents via ProxyJump) (`ansible/inventory/hosts.example.yml:1`)
4. **Router play executes** — `base → firewall → routing → network → wireguard` in order (`ansible/playbooks/bootstrap.yml:2-12`)
5. **Agent plays execute** — `base → firewall → network → wireguard → docker` for each agent (`ansible/playbooks/bootstrap.yml:14-27`)

### Firewall Configuration Flow

1. **Role asserts** validate variable schema (`ansible/playbooks/roles/firewall/tasks/assert.yml`)
2. **Install phase** installs `firewalld` and `python3-firewall`, starts the service (`ansible/playbooks/roles/firewall/tasks/install.yml`)
3. **Policy phase** creates zones, policies (with ingress/egress, ports, protocols reconciled), masquerade, forward ports, rich rules (`ansible/playbooks/roles/firewall/tasks/policy.yml`)
4. **Bind phase** binds non-NetworkManager interfaces (wg0) to zones (`ansible/playbooks/roles/firewall/tasks/bind.yml`)
5. **Handler reload** — firewalld reloads only after all changes are staged (`ansible/playbooks/roles/firewall/handlers/main.yml`)

### Network Configuration Flow

1. **Role asserts** validate interface uniqueness and zone existence (`ansible/playbooks/roles/network/tasks/assert.yml`)
2. **NMCLI phase** renames default cloud-init connections, configures new connections per `network_interfaces`, assigns firewalld zones, and activates (`ansible/playbooks/roles/network/tasks/nmcli.yml`)
3. **Handler** reactivates changed connections (`ansible/playbooks/roles/network/handlers/main.yml`)

**State Management:**
- Ansible host facts are gathered per-play (`gather_facts: true`)
- Runtime state is tracked via registered variables and `set_fact` (e.g., `firewall_policy_*_map` dicts for reconciliation)
- Feature flags (`wireguard_enabled`, `docker_enabled`, etc.) control conditional role execution
- NetworkManager zone stickiness: once assigned via `connection.zone`, removing the zone variable does NOT clear the NM setting. This is a known architectural constraint documented in `AGENTS.md`.

## Key Abstractions

**Component Role:**
- Purpose: Self-contained, data-driven Ansible role for one infrastructure subsystem
- Examples: `ansible/playbooks/roles/firewall/`, `ansible/playbooks/roles/network/`, `ansible/playbooks/roles/docker/`
- Pattern: `tasks/main.yml` → `assert.yml` → `setup.yml` → `install.yml` → sub-phases → handlers flush. Each task named with `PHASE [<phase> : <task>]`.

**Host Variable Schema (per role):**
- Purpose: Define expected variable shape via `meta/argument_specs.yml`
- Examples: `ansible/playbooks/roles/firewall/meta/argument_specs.yml`, `ansible/playbooks/roles/network/meta/argument_specs.yml`, `ansible/playbooks/roles/docker/meta/argument_specs.yml`
- Pattern: Each role declares its required and optional variables with types and defaults. The `assert.yml` task file then validates them at runtime.

**Feature Flag:**
- Purpose: Conditionally enable or disable roles within a play
- Examples: `wireguard_enabled`, `docker_enabled`, `bind9_enabled`, `base_upgrade_enabled` in `group_vars/all.yml` and per-host `main.yml`
- Pattern: `when: <flag>` conditional on the role import in `bootstrap.yml`

**Secret Split:**
- Purpose: Keep WireGuard private keys and endpoint info out of version control
- Examples: `ansible/inventory/host_vars/router-01/secrets.example.yml`, `ansible/inventory/host_vars/dmz-agent-01/secrets.example.yml`
- Pattern: `secrets.yml` (gitignored) contains actual values; `secrets.example.yml` (tracked) shows the schema with placeholders.

## Entry Points

**Bootstrap Playbook:**
- Location: `ansible/playbooks/bootstrap.yml`
- Triggers: Operator runs `ansible-playbook bootstrap.yml`
- Responsibilities: Orchestrates full environment provisioning across all VMs in dependency order

**Cloud-Init Seed ISO:**
- Location: `cloud-init/iid-{vm}/seed.iso`
- Triggers: VM boot from initialized disk
- Responsibilities: Initial user creation, SSH key injection, hostname, basic network config

**Manual Bootstrap:**
- Location: `manual/bootstrap.md`
- Triggers: Operator follows step-by-step commands
- Responsibilities: Equivalent to the Ansible automation but for manual execution on each VM

## Architectural Constraints

- **Play ordering:** Router play MUST complete before agent plays begin. This is enforced by Ansible play ordering in `bootstrap.yml`.
- **Role ordering within router:** `base → firewall → routing → network → wireguard`. Firewalld policies and NAT must be in place BEFORE NetworkManager activates interfaces (so zones and policies take effect immediately).
- **Zone ownership split:** NetworkManager-managed interfaces declare their firewalld zone via `network_interfaces[].zone` (which sets `connection.zone`). Only non-NM interfaces (currently `wg0`) use `firewall_bindings[].ifname`. Mixing these up causes zone assignment failures.
- **Sticky NetworkManager zones:** Once a `connection.zone` is written to NM, removing the `zone` key from `network_interfaces` will NOT clear it. Zone changes require explicit migration.
- **Single inventory file:** `hosts.yml` is gitignored; `hosts.example.yml` is the tracked template. Operators must copy and customize.
- **Secrets must be local:** `secrets.yml` files are gitignored. WireGuard configuration is impossible without them.
- **Threading model:** Ansible executes sequentially per play (no parallelism within a play). The `internal` and `dmz` groups run in the same play but Ansible batches across hosts.
- **Global state:** `group_vars/all.yml` defines `firewall_builtin_zones` which is consumed by the firewall role's assertion logic. This must be updated if firewalld's built-in zone list changes.
- **cloud-init/Ansible handoff:** cloud-init handles initial provisioning (user, SSH, hostname). Ansible handles everything after SSH is reachable. The two MUST agree on the `student` username and interface naming (`eth*` in cloud-init/Ansible vs `enp0s*` in manual docs).
- **No import/playbook reuse:** The `bind9` role is a stub (`TODO: Implement for Lab 2 (DNS)`) and is gated by `bind9_enabled` defaulting to `false`.

## Anti-Patterns

### System Roles Instead of Component Roles

**What happens:** Creating a "router" or "agent" role that contains all host-specific logic.
**Why it's wrong:** Creates role duplication and makes the codebase harder to extend. The router vs agent behavior difference is data, not logic.
**Do this instead:** Use component roles (`base`, `firewall`, `network`, etc.) driven by `host_vars` data. The `bootstrap.yml` playbook acts as the profile, mapping roles to groups. See `AGENTS.md` and `ansible/playbooks/bootstrap.yml`.

### Using `agents` as Inventory Group

**What happens:** Grouping all agent VMs under an `agents` inventory group.
**Why it's wrong:** DMZ and Private agents have different network zones, firewall policies, and connectivity requirements. They are not interchangeable.
**Do this instead:** Use network-topology groups: `router`, `dmz`, `internal`. See `ansible/inventory/hosts.example.yml`.

### Using Host-Specific Variable Names

**What happens:** Naming variables like `router_interfaces` or `agent_firewall_policies`.
**Why it's wrong:** Forces roles to have host-branching logic, defeating the component role pattern.
**Do this instead:** Use generic variable names (`network_interfaces`, `firewall_policies`) so roles can consume them uniformly regardless of host. See `ansible/inventory/host_vars/router-01/main.yml` and `ansible/inventory/host_vars/dmz-agent-01/main.yml`.

### Conflating Manual and Automation Interface Names

**What happens:** Using `eth0` in manual docs or `enp0s1` in Ansible/cloud-init.
**Why it's wrong:** The automation path renames interfaces via cloud-init to `eth*`, while the manual path assumes standard AlmaLinux predictable names `enp0s*`.
**Do this instead:** Keep `enp0s*` naming in `manual/` files and `eth*` naming in `cloud-init/` and `ansible/`. See `AGENTS.md` section "Network Interface Naming Convention".

### Adding firewalld Zone Changes Without Reconciliation

**What happens:** Only adding new zones/ports/policies without removing stale ones.
**Why it's wrong:** Firewalld is additive by default. Over time, orphaned rules accumulate and cause unexpected behavior.
**Do this instead:** The firewall role already implements reconciliation ( querying current state and removing stale entries in `policy.yml`). New firewall changes should follow this pattern. See `ansible/playbooks/roles/firewall/tasks/policy.yml`.

## Error Handling

**Strategy:** Fail-fast with descriptive assertion messages

**Patterns:**
- **Role argument validation:** Each role with `meta/argument_specs.yml` validates variable shapes before execution. Missing required variables cause immediate failure with clear messages.
- **Runtime assertions:** `assert.yml` task files in each role check semantic correctness (e.g., zone references exist, interface names are unique, Docker image tags include explicit tags).
- **Connectivity check:** The `base` role starts with a `ping` task that verifies SSH reachability before any other work.
- **Reboot checkpoint:** The `base` role checks kernel version mismatch and conditionally reboots, then refreshes facts — preventing "wrong kernel" failures in subsequent roles.
- **Docker verification:** The `docker` role verifies container state after deployment (`docker_container_info` + assert running) and validates binfmt emulation with a test container.
- **Handler flush pattern:** Firewall and network roles call `meta: flush_handlers` at strategic points to ensure changes are applied before dependent steps.

## Cross-Cutting Concerns

**Logging:** All role boundaries use `START`/`END` debug tasks. Phase boundaries use `PHASE [<name> : START]`/`PHASE [<name> : END]`. Functional tasks are named `PHASE [<phase> : <description>]`. This produces a structured, grep-able Ansible output log.

**Validation:** The argument specs pattern (`meta/argument_specs.yml`) provides schema validation at role entry. Runtime assertions in `assert.yml` check semantic constraints that schema alone can't express (e.g., zone reference consistency, variable overlap between `network_interfaces` and `firewall_bindings`).

**Authentication:** SSH key-based. Cloud-init injects the public key; Ansible connects as `student` user with `become: true`. Router is reached directly (or via port forward); agents are reached via `ProxyJump` through the router.

**Configuration Reconciliation:** The firewall role implements state reconciliation — it queries existing state, builds desired-state maps, adds missing entries, and removes stale ones. This pattern should be followed for any future idempotent configuration tasks.

---

*Architecture analysis: 2026-05-05*