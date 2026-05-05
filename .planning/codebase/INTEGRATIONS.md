# External Integrations

**Analysis Date:** 2026-05-05

## APIs & External Services

**VPN / Remote Grading Access:**
- WireGuard — TA grades via WireGuard VPN tunnel (`wg0`)
  - SDK/Client: `wireguard-tools` package
  - Auth: Pre-shared key + public/private key pair (stored in `secrets.yml`)
  - Config: `ansible/playbooks/roles/wireguard/templates/wg0.conf.j2`
  - Endpoints: Defined per-host in `wireguard_peer_endpoint` (e.g., `vpn.example.edu:5000`)

**Docker Registry (Remote Pull):**
- Docker Hub (implicit) — `tonistiigi/binfmt:qemu-v10.0.4` and `alpine:3.23` pulled at runtime
  - SDK/Client: Docker CE (`community.docker` Ansible collection)
  - Auth: None (public images)

**Package Repositories:**
- EPEL (Fedora Project) — `epel-release` package installed by base role
  - Auth: None (public repo)
- Docker CE Stable Repository — `https://download.docker.com/linux/rhel/`
  - Auth: None (public repository, GPG key `https://download.docker.com/linux/rhel/gpg`)

**DNS Resolvers:**
- Google DNS (`8.8.8.8`) and Cloudflare DNS (`1.1.1.1`) — configured as upstream resolvers on agent and DNS host network interfaces
  - Config: `dns4` in `network_interfaces` entries in `host_vars/*/main.yml`

## Data Storage

**Databases:**
- None (infrastructure automation repo, no application databases)

**File Storage:**
- Local filesystem only — Ansible roles ship Docker image tar archives in `ansible/playbooks/roles/docker/files/`
- Cloud-init `seed.iso` files generated per VM (gitignored)

**Caching:**
- None

## Authentication & Identity

**Auth Provider:**
- SSH key-based authentication — cloud-init configures SSH authorized keys
  - Implementation: `cloud-init/iid-*/user-data.yml` → `ssh_authorized_keys`
  - Password auth disabled: `ssh_pwauth: false`
  - Root login disabled: `disable_root: true`
  - User `student` (configurable) with `wheel` group and passwordless sudo

**Ansible Control Node Auth:**
- SSH key authentication to target hosts
- ProxyJump through router for DMZ and internal zone hosts
- Config: `ansible_ssh_common_args` with `-o ProxyJump=...` in `ansible/inventory/hosts.yml`

**WireGuard Auth:**
- Pre-shared key (symmetric) + asymmetric key pair
- Variables: `wireguard_private_key`, `wireguard_peer_public_key`, `wireguard_preshared_key`
- Stored in gitignored `secrets.yml` per host

## Monitoring & Observability

**Error Tracking:**
- None (no external monitoring)

**Logs:**
- Ansible playbooks use structured debug logging with `PHASE [name : START]` / `PHASE [name : END]` and `START` / `END` role boundary markers
- Ansible log file gitignored (`ansible.log`)
- Target hosts: standard journald/syslog (not configured by Ansible roles)

## CI/CD & Deployment

**Hosting:**
- Local/target VM environment — no cloud hosting platform

**CI Pipeline:**
- None (no CI/CD pipeline detected)
- Manual execution: `ansible-playbook ansible/playbooks/bootstrap.yml`
- Suggested linting: `ansible-lint` (mentioned in AGENTS.md)

**Deployment Model:**
- Bootstrap playbook (`ansible/playbooks/bootstrap.yml`) runs against inventory groups
- Router play executes first (`base → firewall → routing → network → wireguard`)
- Zone hosts play follows (`base → firewall → network → wireguard → docker → bind9`)
- Roles are conditionally included via `when: <role>_enabled`

## Environment Configuration

**Required env vars:**
- None (Ansible uses inventory variables, not environment variables)

**Ansible inventory variables (per-host):**
- `ansible_user` — SSH user for target hosts
- `ansible_host` — SSH target IP
- `ansible_port` — SSH target port
- `ansible_ssh_common_args` — ProxyJump configuration for non-router hosts
- `network_interfaces` — NIC configuration (interface, zone, IP, gateway, DNS)
- `firewall_*` — Firewalld zones, policies, bindings, port forwards, rich rules, masquerade
- `wireguard_*` — WireGuard tunnel configuration
- `docker_*` — Docker container and image archive configuration
- `bind9_enabled` — BIND9 DNS server flag

**Secrets location:**
- `ansible/inventory/host_vars/*/secrets.yml` — WireGuard private keys, preshared keys, peer endpoint addresses
- `cloud-init/iid-*/user-data.yml` — SSH authorized public keys (placeholder values committed)

## Webhooks & Callbacks

**Incoming:**
- None

**Outgoing:**
- None

---

*Integration audit: 2026-05-05*