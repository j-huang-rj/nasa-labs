# Codebase Structure

**Analysis Date:** 2026-05-05

## Directory Layout

```
nasa-labs/
├── AGENTS.md                     # Agent instructions and project conventions
├── README.md                     # Repository overview
├── .gitignore                    # Excludes secrets, artifacts, generated files
├── ansible/                      # Ansible automation (primary IaC)
│   ├── ansible.cfg               # Ansible configuration (inventory path, SSH settings)
│   └── inventory/
│       ├── group_vars/
│       │   └── all.yml           # Global defaults and feature flags
│       ├── host_vars/            # Per-host variable directories
│       │   ├── router-01/
│       │   │   ├── main.yml      # Network, firewall, routing config
│       │   │   ├── secrets.example.yml  # WireGuard secret template (tracked)
│       │   │   └── secrets.yml   # WireGuard secrets (gitignored)
│       │   ├── dmz-agent-01/
│       │   │   ├── main.yml      # Network, firewall, docker config
│       │   │   ├── secrets.example.yml
│       │   │   └── secrets.yml
│       │   ├── internal-agent-01/
│       │   │   └── main.yml      # Network, firewall, docker config
│       │   ├── dns-01/
│       │   │   └── main.yml      # Network, firewall, BIND9 config
│       │   ├── primary-ns-01/
│       │   │   └── main.yml       # Network, firewall, BIND9 config
│       │   └── secondary-ns-01/
│       │       ├── main.yml       # Network, firewall, WireGuard, BIND9 config
│       │       ├── secrets.example.yml
│       │       └── secrets.yml
│       ├── hosts.example.yml      # Inventory template (tracked)
│       └── hosts.yml              # Actual inventory (gitignored)
├── ansible/playbooks/
│   ├── bootstrap.yml             # Main playbook: router-then-agents provisioning
│   └── roles/
│       ├── base/                 # System packages, upgrade, reboot
│       │   └── tasks/
│       │       ├── main.yml      # START → ping → assert → setup → END
│       │       ├── ping.yml      # SSH connectivity verification
│       │       ├── assert.yml    # RHEL family check
│       │       ├── setup.yml    # upgrade → install → reboot phases
│       │       ├── upgrade.yml   # Full system upgrade (gated by base_upgrade_enabled)
│       │       ├── install.yml   # EPEL, tools, kernel-modules-extra, qemu-guest-agent
│       │       └── reboot.yml    # Conditional reboot if kernel mismatch
│       ├── firewall/             # firewalld configuration
│       │   ├── handlers/
│       │   │   └── main.yml     # firewalld reload handler
│       │   ├── meta/
│       │   │   └── argument_specs.yml  # Variable schema validation
│       │   └── tasks/
│       │       ├── main.yml      # START → assert → setup → END
│       │       ├── assert.yml    # Zone uniqueness, overlap, reference validation
│       │       ├── install.yml   # Install firewalld + python3-firewall
│       │       ├── setup.yml     # install → policy → bind phases
│       │       ├── policy.yml    # Zones, policies, masquerade, DNAT, rich rules
│       │       └── bind.yml      # Interface-to-zone bindings (wg0)
│       ├── routing/              # Kernel IP forwarding
│       │   └── tasks/
│       │       ├── main.yml      # START → setup → END
│       │       └── setup.yml    # sysctl.yml import
│       │       └── sysctl.yml    # net.ipv4.ip_forward = 1
│       ├── network/              # NetworkManager connection management
│       │   ├── handlers/
│       │   │   └── main.yml     # Reactivate changed NM connections
│       │   ├── meta/
│       │   │   └── argument_specs.yml
│       │   └── tasks/
│       │       ├── main.yml      # START → assert → setup → END
│       │       ├── assert.yml    # Interface uniqueness, zone existence
│       │       ├── setup.yml     # nmcli.yml import
│       │       └── nmcli.yml     # Rename defaults, configure, activate
│       ├── wireguard/            # WireGuard VPN tunnels
│       │   ├── meta/
│       │   │   └── argument_specs.yml
│       │   ├── templates/
│       │   │   └── wg0.conf.j2   # WireGuard config template
│       │   └── tasks/
│       │       ├── main.yml      # START → setup → END (gated by wireguard_enabled)
│       │       ├── install.yml   # Install wireguard-tools
│       │       └── setup.yml     # Install → template → enable wg0
│       ├── docker/               # Docker CE + multiarch + workloads
│       │   ├── defaults/
│       │   │   └── main.yml      # docker_binfmt_image, docker_container_* defaults
│       │   ├── files/            # Docker image tar archives (gitignored)
│       │   ├── handlers/
│       │   │   └── main.yml     # Restart docker-binfmt-register service
│       │   ├── meta/
│       │   │   └── argument_specs.yml
│       │   ├── templates/
│       │   │   └── docker-binfmt-register.service.j2
│       │   └── tasks/
│       │       ├── main.yml      # START → assert → setup → END
│       │       ├── assert.yml    # Image archive, container, binfmt validation
│       │       ├── install.yml   # Docker CE repo, packages, group, systemd
│       │       ├── setup.yml     # install → multiarch → workloads phases
│       │       ├── multiarch.yml # binfmt registration, verification
│       │       └── workloads.yml # Image archives, containers, state assertions
│       └── bind9/                # BIND9 DNS server (stub)
│           └── tasks/
│               └── main.yml      # TODO: Implement for Lab 2 (DNS)
├── cloud-init/                   # VM seed data for initial boot
│   ├── iid-router-01/
│   │   ├── meta-data.yml         # instance-id + hostname
│   │   ├── network-config.yml    # NetworkManager v2 config (eth0 DHCP, eth1/eth2 unconfigured)
│   │   ├── user-data.yml         # User creation, SSH key, timezone
│   │   ├── meta-data             # Generated (gitignored)
│   │   ├── network-config        # Generated (gitignored)
│   │   ├── user-data             # Generated (gitignored)
│   │   └── seed.iso              # Generated (gitignored)
│   ├── iid-dmz-agent-01/         # DMZ agent cloud-init
│   ├── iid-internal-agent-01/    # Private agent cloud-init
│   ├── iid-dns-01/               # DNS resolver cloud-init
│   ├── iid-primary-ns-01/        # Primary NS cloud-init
│   └── iid-secondary-ns-01/      # Secondary NS cloud-init (DMZ side)
├── lab/                          # Assignment materials from course
│   ├── bootstrap.pdf
│   ├── dns.md                    # HW1-1 DNS assignment spec
│   └── dns.pdf
├── manual/                       # Step-by-step human-readable guides
│   ├── bootstrap.md              # Full manual bootstrap procedure
│   └── dns.md                    # DNS lab manual (empty placeholder)
└── .planning/                    # GSD planning documents
```

## Directory Purposes

**`ansible/`:**
- Purpose: All Ansible automation code — inventory, playbooks, and roles
- Contains: Inventory configuration, the bootstrap playbook, and seven component roles
- Key files: `playbooks/bootstrap.yml`, `inventory/host_vars/*/main.yml`, `inventory/group_vars/all.yml`

**`ansible/inventory/`:**
- Purpose: Host definitions, group variables, and per-host configuration data
- Contains: `hosts.yml` (gitignored, operator-specific), `hosts.example.yml` (tracked template), `group_vars/`, `host_vars/`
- Key files: `group_vars/all.yml` — global defaults and feature flags

**`ansible/inventory/host_vars/{host}/`:**
- Purpose: Per-host variable data driving role behavior
- Contains: `main.yml` (tracked, network + firewall + docker config) and optionally `secrets.yml` (gitignored, WireGuard keys)
- Key files: Each host's `main.yml` is the primary configuration document

**`ansible/playbooks/roles/{role}/`:**
- Purpose: Component role implementation
- Contains: `tasks/` (mandatory), `handlers/`, `meta/`, `defaults/`, `templates/`, `files/` as needed
- Key files: `tasks/main.yml` (entry point), `tasks/assert.yml` (validation), `meta/argument_specs.yml` (schema)

**`cloud-init/`:**
- Purpose: VM bootstrapping data for initial provisioning before Ansible
- Contains: One subdirectory per VM (`iid-{vm}/`) with `user-data.yml`, `meta-data.yml`, `network-config.yml`, and generated artifacts
- Key files: YAML templates are tracked; `seed.iso`, `user-data`, `meta-data`, `network-config` (no extension) are gitignored generated artifacts

**`lab/`:**
- Purpose: Course assignment materials (specs, PDFs)
- Contains: Assignment descriptions and grading criteria

**`manual/`:**
- Purpose: Human-readable step-by-step guides equivalent to the Ansible automation
- Contains: Markdown files with bash commands for manual execution
- Key convention: Uses `enp0s*` interface names (NOT `eth*`)

**`.planning/`:**
- Purpose: GSD (Get Stuff Done) planning and codebase analysis documents
- Contains: Codebase documentation generated by tooling

## Key File Locations

**Entry Points:**
- `ansible/playbooks/bootstrap.yml`: Main Ansible playbook
- `cloud-init/iid-{vm}/user-data.yml`: Per-VM boot initialization
- `manual/bootstrap.md`: Human-readable bootstrap guide

**Configuration:**
- `ansible/ansible.cfg`: Ansible runtime config (inventory path, SSH pipelining)
- `ansible/inventory/group_vars/all.yml`: Global defaults and feature flags
- `ansible/inventory/host_vars/*/main.yml`: Per-host configuration data
- `ansible/inventory/host_vars/*/secrets.example.yml`: Secret schema template
- `.gitignore`: Excludes secrets, generated artifacts, workspace files

**Core Logic:**
- `ansible/playbooks/roles/firewall/tasks/policy.yml`: Firewall policy reconciliation engine (largest single task file, ~546 lines)
- `ansible/playbooks/roles/network/tasks/nmcli.yml`: NetworkManager connection management
- `ansible/playbooks/roles/docker/tasks/workloads.yml`: Docker container deployment with state verification
- `ansible/playbooks/roles/docker/tasks/multiarch.yml`: QEMU binfmt registration and verification

**Templates:**
- `ansible/playbooks/roles/wireguard/templates/wg0.conf.j2`: WireGuard config template
- `ansible/playbooks/roles/docker/templates/docker-binfmt-register.service.j2`: systemd unit for binfmt registration

**Schemas:**
- `ansible/playbooks/roles/firewall/meta/argument_specs.yml`: Firewall variable schema
- `ansible/playbooks/roles/network/meta/argument_specs.yml`: Network variable schema
- `ansible/playbooks/roles/docker/meta/argument_specs.yml`: Docker variable schema
- `ansible/playbooks/roles/wireguard/meta/argument_specs.yml`: WireGuard variable schema

## Naming Conventions

**Files:**
- Role task files: `<phase>.yml` — e.g., `install.yml`, `setup.yml`, `assert.yml`, `nmcli.yml`
- Role handler files: `main.yml` inside `handlers/`
- Role defaults: `main.yml` inside `defaults/`
- Role schemas: `argument_specs.yml` inside `meta/`
- Templates: `<name>.j2` — e.g., `wg0.conf.j2`, `docker-binfmt-register.service.j2`
- Host variable directories: Match inventory hostname exactly — e.g., `router-01/`, `dmz-agent-01/`
- Cloud-init directories: `iid-<hostname>` — e.g., `iid-router-01/`, `iid-dmz-agent-01/`

**Task Names:**
- Role entry/exit: `START` and `END` (no `PHASE` prefix)
- Phase boundaries: `PHASE [<phase_name> : START]` and `PHASE [<phase_name> : END]`
- Functional tasks: `PHASE [<phase_name> : <description>]`
- Handler names: `PHASE [handler : <description>]` or `HANDLER [docker : <description>]`

**Variables:**
- Host-specific config: `network_interfaces`, `firewall_policies`, `firewall_zone_ports`, etc. (generic names, not host-prefixed)
- Feature flags: `<feature>_enabled` — e.g., `wireguard_enabled`, `docker_enabled`, `bind9_enabled`
- Firewall variable namespacing: `firewall_` prefix — e.g., `firewall_custom_zones`, `firewall_bindings`, `firewall_policies`
- Docker variable namespacing: `docker_` prefix — e.g., `docker_containers`, `docker_image_archives`, `docker_binfmt_enabled`
- Secrets: `wireguard_` prefix — e.g., `wireguard_address`, `wireguard_private_key`

## Where to Add New Code

**New Role (Component Role):**
- Create directory: `ansible/playbooks/roles/<role_name>/tasks/main.yml`
- Add `meta/argument_specs.yml` if the role takes variables
- Add `defaults/main.yml` for default values
- Follow the `START → assert → setup → END` pattern in `tasks/main.yml`
- Add role to `bootstrap.yml` with appropriate `when:` condition if it's conditional
- Add feature flag to `group_vars/all.yml` (e.g., `<role_name>_enabled: false`)

**New Host:**
- Create `ansible/inventory/host_vars/<hostname>/main.yml` with required variables
- Add `secrets.example.yml` and `secrets.yml` if WireGuard is needed
- Update `ansible/inventory/hosts.yml` (copy from `hosts.example.yml`)
- Create `cloud-init/iid-<hostname>/` with `user-data.yml`, `meta-data.yml`, `network-config.yml`

**New Firewall Policy:**
- Add policy definition to appropriate host's `host_vars/<host>/main.yml` under `firewall_policies`
- Ensure referenced zones exist in `firewall_builtin_zones` or `firewall_custom_zones`
- The reconciliation logic in `firewall/tasks/policy.yml` will handle creation, update, and stale entry removal

**New Docker Container:**
- Add container definition to host's `main.yml` under `docker_containers`
- If using a local image archive, add to `docker_image_archives` as well
- Place the image tar file in `ansible/playbooks/roles/docker/files/`

**New Lab Phase (e.g., Mail, LDAP):**
- Implement the corresponding role under `ansible/playbooks/roles/`
- Add feature flag to `group_vars/all.yml`
- Add condition to `bootstrap.yml`
- Document manual steps in `manual/<phase>.md`
- Add assignment materials to `lab/`

## Special Directories

**`ansible/playbooks/roles/docker/files/`:**
- Purpose: Docker image tar archives to be copied to remote hosts
- Generated: No — operator must place `.tar` files here
- Committed: `nap-agent.tar` is gitignored via `.gitignore` (`ansible/playbooks/roles/docker/files/nap-agent.tar`)

**`cloud-init/iid-{vm}/`:**
- Purpose: Per-VM cloud-init seed data
- Generated: `seed.iso`, `user-data`, `meta-data`, `network-config` (no extension) are generated from `.yml` templates and are gitignored
- Committed: Only `*.yml` source templates are tracked

**`ansible/inventory/hosts.yml`:**
- Purpose: Actual Ansible inventory with real host IPs and SSH config
- Generated: No — manually created by operator from `hosts.example.yml`
- Committed: No — gitignored because it contains operator-specific IPs and ports

**`ansible/inventory/host_vars/*/secrets.yml`:**
- Purpose: Real WireGuard secret values (private keys, peer endpoints)
- Generated: No — manually created by operator from `secrets.example.yml`
- Committed: No — gitignored to prevent secret leakage

---

*Structure analysis: 2026-05-05*