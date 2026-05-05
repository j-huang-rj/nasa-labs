# Technology Stack

**Analysis Date:** 2026-05-05

## Languages

**Primary:**
- YAML - Infrastructure-as-code definitions (Ansible playbooks, roles, inventory, cloud-init configs, argument specs)

**Secondary:**
- Jinja2 - Ansible templates (`ansible/playbooks/roles/wireguard/templates/wg0.conf.j2`, `ansible/playbooks/roles/docker/templates/docker-binfmt-register.service.j2`)
- Bash (implicit) - Used via `ansible.builtin.command` tasks invoking `nmcli`, `firewall-cmd`, `docker`, etc.

## Runtime

**Environment:**
- AlmaLinux Minimal (RHEL family) - Target VM operating system, asserted by `ansible/playbooks/roles/base/tasks/assert.yml`
- Linux (kernel) - Kernel IP forwarding, sysctl, binfmt emulation

**Package Manager:**
- DNF (`ansible.builtin.dnf`) - Package management on target hosts
- Ansible Galaxy / Collections - Ansible dependency management
- Lockfile: Not present (no `requirements.yml` or `galaxy.yml` detected)

## Frameworks

**Core:**
- Ansible (automation framework) - All infrastructure provisioning and configuration

**Ansible Collections (used):**
- `ansible.builtin` - Core modules (`dnf`, `yum_repository`, `systemd`, `user`, `template`, `command`, `assert`, `set_fact`, `debug`, `ping`, `reboot`, `setup`, `meta`, `file`, `copy`)
- `ansible.posix` - `sysctl`, `firewalld`
- `community.general` - `nmcli`
- `community.docker` - `docker_image_info`, `docker_image_load`, `docker_image_pull`, `docker_container`, `docker_container_info`

**Cloud-Init:**
- cloud-init (Canonical) - VM initial provisioning (user creation, SSH keys, network config)

**Container Runtime:**
- Docker CE - Container runtime on agent hosts
- containerd.io - Container runtime dependency
- Docker Buildx plugin - Multi-arch builds
- Docker Compose plugin - Compose support

## Key Dependencies

**Target Host Packages:**
- `epel-release` - Extra Packages for Enterprise Linux
- `dnf-plugins-core` - DNF repository management
- `qemu-guest-agent` - VM hypervisor integration
- `bind-utils`, `traceroute`, `mtr` - DNS and network diagnostics
- `nmap`, `nmap-ncat`, `wireshark-cli`, `whois` - Network scanning and capture
- `wget`, `git`, `vim`, `fastfetch` - General utilities
- `kernel-modules-extra` - Additional kernel modules
- `firewalld`, `python3-firewall` - Firewall management
- `wireguard-tools` - WireGuard VPN tunneling
- `docker-ce`, `docker-ce-cli`, `docker-buildx-plugin`, `docker-compose-plugin` - Docker CE stack

**Docker Images:**
- `tonistiigi/binfmt:qemu-v10.0.4` - QEMU multi-arch emulation registration (pulled, not shipped)
- `alpine:3.23` (default) / `alpine:3.22` (argument_specs default) - amd64 emulation test image
- `nap-agent:latest` - TA-provided course Docker image (shipped as tar archive)

**Ansible Collections (implicit from module usage):**
- `ansible.posix` ≥ 1.x - `sysctl`, `firewalld` modules
- `community.general` ≥ 7.x - `nmcli` module
- `community.docker` ≥ 3.x - Docker modules

## Configuration

**Environment:**
- Ansible inventory: `ansible/inventory/hosts.yml` (gitignored, example at `ansible/inventory/hosts.example.yml`)
- Host variables: `ansible/inventory/host_vars/<hostname>/main.yml` — per-host config (network, firewall, docker, wireguard)
- Secrets: `ansible/inventory/host_vars/<hostname>/secrets.yml` (gitignored, template at `secrets.example.yml`)
- Group variables: `ansible/inventory/group_vars/all.yml` — global defaults
- Ansible config: `ansible/ansible.cfg`
- Cloud-init: `cloud-init/iid-<hostname>/user-data.yml`, `network-config.yml`, `meta-data.yml`

**Key configs required:**
- `ansible/inventory/hosts.yml` — SSH connection details per host
- `ansible/inventory/host_vars/router-01/secrets.yml` — WireGuard credentials (address, private key, peer public key, preshared key, allowed IPs, peer endpoint)
- `ansible/inventory/host_vars/dmz-agent-01/secrets.yml` — WireGuard credentials (same structure)
- `ansible/inventory/host_vars/secondary-ns-01/secrets.yml` — WireGuard credentials
- Cloud-init SSH authorized keys — placeholder keys in `user-data.yml` must be replaced

**Build:**
- `ansible/ansible.cfg` — Ansible runtime configuration (inventory path, roles path, SSH pipelining, host key checking disabled)

**Secrets Management:**
- Local secret split: `secrets.yml` files are gitignored; `secrets.example.yml` templates are committed with commented placeholder values
- WireGuard private keys, preshared keys, and VPN endpoint addresses are stored in `secrets.yml` per host

## Platform Requirements

**Development:**
- Ansible control node with access to target VMs over SSH
- SSH connectivity to router-01 (port 2787 by default) and proxied access to DMZ/Internal hosts via ProxyJump through router
- Cloud-init `seed.iso` generation tooling (e.g., `genisoimage` or `cloud-localds`)
- Docker image tar archive (`nap-agent.tar`) in `ansible/playbooks/roles/docker/files/`

**Production (Target VMs):**
- AlmaLinux Minimal (RHEL family) VMs
- Router VM: 3 NICs (Shared/VLAN, DMZ VLAN 1, Private VLAN 2)
- DMZ Agent VM: 1 NIC (DMZ VLAN 1)
- Private Agent VM: 1 NIC (Private VLAN 2)
- DNS Server VM(s): 1 NIC each
- QEMU emulator for amd64 container execution on ARM hosts (via `tonistiigi/binfmt`)

---

*Stack analysis: 2026-05-05*