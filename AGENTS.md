# OpenCode Agent Instructions

This repository contains incremental environment setup and documentation for NASA/Network Administration course labs.
Work is phase-organized under `lab/` (assignment materials) and `manual/` (writeups/manual steps).

## Network Interface Naming Convention
- **Manual path (`manual/1-0.md`):** assume a standard AlmaLinux minimal ISO install with predictable interface names such as `enp0s1`, `enp0s2`, `enp0s3`, plus default NetworkManager profiles like `Wired connection 1`.
- **Project automation path:** cloud-init renames the managed interfaces to `eth0`, `eth1`, `eth2`, and the Ansible inventory/roles are written against those names.
- Do **NOT** conflate the two contexts. When updating `manual/1-0.md`, keep the standard ISO assumptions. When updating cloud-init, inventory, or Ansible automation, use the `eth*` naming that the project actually provisions.

## VM Architecture Overview
- **Router VM:** 3 Network Adapters (Shared/VLAN, DMZ VLAN 1, Private VLAN 2). Acts as NAT engine and firewall (`firewalld`). Requires kernel IP forwarding (`sysctl`).
- **DMZ Agent VM:** 1 Network Adapter (DMZ VLAN 1). IP: `172.16.0.123`.
- **Private Agent VM:** 1 Network Adapter (Private VLAN 2). IP: `172.16.1.123`.

## Key Operational Quirks
- **WireGuard VPN:** The TA grades via a WireGuard VPN (`wg0`). The Router and DMZ Agent both require tunnels.
- **Local secret split:** Commit `host_vars/*/main.yml` and `secrets.example.yml`, but keep real local values in gitignored `host_vars/*/secrets.yml`.
- **Docker on Agents:** Docker containers run using `--network host`. Because the TA-provided image is `amd64`, the host VMs require QEMU emulators registered in the Linux kernel via Docker (`tonistiigi/binfmt`) to run them.
- **Firewall:** `firewalld` is used extensively for zone bindings, NAT (SNAT/DNAT), and cross-zone routing policies. The `firewall` role is host-agnostic and driven by variables in `host_vars`.

## Firewall & Routing Requirements (Router VM)
- **Default Policies:** Reject connections from other zones to Private zone. Reject connections from Private zone to VPN zone.
- **Allowed Traffic:**
  - DMZ to Private zone on port `55688`.
  - ICMP from anywhere to anywhere.
  - Internet connection for both DMZ and Private zones.
  - SSH from Router to both Agents.
- **Blocked Traffic:** SSH from VPN zone to Router.
- **NAT/DNAT:**
  - Masquerade is enabled on the `dmz`, `internal`, and `vpn` zones. This covers outbound Internet access for both agent zones and the VPN-side SNAT needed for DNAT return traffic.
  - Router port `10001` -> DMZ Agent port `2222`.
  - Router port `10002` -> Private Agent port `2222`.
- **Firewall bootstrap posture:** Keep firewalld policy and permanent non-NetworkManager bindings in place before interfaces come up. NetworkManager-managed links must rely on `connection.zone`, while non-NetworkManager links such as `wg0` may be pre-bound through permanent firewalld configuration.

## Grading Checkpoints (Online Judge)
The system is evaluated against these criteria:
1. Router's VPN connection is active.
2. Router's DNAT to Agents in both zones is functional.
3. Both Agents have Internet connectivity.
4. Trace route from Agent in Private zone works.
5. Firewall rules for Router are correctly configured.
6. Firewall rules for Private zone are correctly configured.

## Linting & Syntax Checking
- Run `ansible-lint` on playbooks and roles to ensure best practices and avoid common issues.
- Run `ansible-playbook --syntax-check` with the inventory file to avoid false warnings about unresolved host groups:
  ```
  ansible-playbook --syntax-check -i ansible/inventory/hosts.yml ansible/playbooks/bootstrap.yml
  ansible-playbook --syntax-check -i ansible/inventory/hosts.yml ansible/playbooks/dns.yml
  ansible-playbook --syntax-check -i ansible/inventory/hosts.yml ansible/playbooks/site.yml
  ```

## Ansible Architecture & Conventions
- **Component Roles vs System Roles:** We strictly use Component Roles (`base`, `docker`, `routing`, `network`, `firewall`, `wireguard`, `bind9`). Do NOT create System Roles (like `agent` or `router`).
- **Playbook Architecture:** `bootstrap.yml` handles infrastructure substrate only (base, firewall, routing, network, wireguard, docker). Service roles (`bind9`, and future mail/ldap) have their own playbooks (`dns.yml`, etc.). `site.yml` is the full converge entry point that imports all playbooks in order.
- **Inventory Structure:** Hosts are grouped by network topology: `router`, `dmz`, and `internal`. Functional overlay groups (e.g., `dns`) target service-specific playbooks and are NOT generic groups like `agents`. Overlay group hosts inherit connection vars from their topology groups.
- **Variable Scoping:** Use generic variable names in `host_vars` (e.g., `network_interfaces` instead of `agent_interfaces` or `router_interfaces`) so component roles can be host-agnostic.
- **Zone Ownership Split:** NetworkManager-managed interfaces must declare their firewalld zones in `network_interfaces[].zone` (manual equivalent: `nmcli connection.zone`). `firewall_bindings[].ifname` is reserved for interfaces outside the NetworkManager lifecycle (currently `wg0`; manual equivalent: permanent `firewall-cmd --zone=<zone> --change-interface=wg0`).
- **Play Ordering (Router-First):** `bootstrap.yml` completes the router play before starting the `dmz` and `internal` play. Inside the router play, role order is `base -> firewall -> routing -> network -> wireguard`, so firewalld policy, NAT, DNAT, and IP forwarding are prepared before managed interfaces are brought up. The agent play starts only after the router is fully provisioned.
- **Sticky NetworkManager zone behavior:** Removing `network_interfaces[].zone` later does not automatically clear an already-written NetworkManager `connection.zone`. If a zone must be removed or reassigned, treat it as an explicit migration rather than expecting the current clean-VM bootstrap path to reconcile old state automatically.
- **WireGuard Execution:** WireGuard is controlled by an explicit flag (`wireguard_enabled: true`) in `host_vars`, not by checking if the address is defined.
- **Logging Convention:** 
  - Role boundaries in `tasks/main.yml` must use `START` and `END` debug tasks.
  - Phase boundaries in task files must use `PHASE [<phase_name> : START]` and `PHASE [<phase_name> : END]`.
  - Functional tasks inside phase files must be named `PHASE [<phase_name> : <original task name>]`.
