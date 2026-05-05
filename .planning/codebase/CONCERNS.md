# Codebase Concerns

**Analysis Date:** 2026-05-05

## Tech Debt

**Firewall policy role — excessive `command` module usage:**
- Issue: The firewall policy reconciliation in `ansible/playbooks/roles/firewall/tasks/policy.yml` (546 lines) uses `ansible.builtin.command` with raw `firewall-cmd` invocations for every policy sub-operation (create, set-priority, set-target, add/remove ingress zones, add/remove egress zones, add/remove protocols, add/remove ports). This should use idempotent `ansible.posix.firewalld` or custom modules, but no such module exists for firewalld policies.
- Files: `ansible/playbooks/roles/firewall/tasks/policy.yml`
- Impact: Policy tasks report `changed_when: true` for every create/modify command, making playbook output noisy. The read-compute-apply pattern (query current state → compute diff → apply changes) compensates for idempotency but adds significant task count (~30+ tasks per playbook run just for policy reconciliation).
- Fix approach: Long-term — write a custom Ansible module or action plugin for `firewalld_policy` that provides true idempotent behavior. Short-term — tighten `changed_when` guards to compare registered current state against desired state so no-ops report `changed=false`.

**Firewall policy role — repetitive reconciliation pattern:**
- Issue: The same "query current → build maps → add missing → remove stale" pattern is copy-pasted five times in `policy.yml` for ingress zones, egress zones, protocols, policy ports, and zone ports. Each block duplicates the same Jinja2 map-building logic with only the attribute names changed.
- Files: `ansible/playbooks/roles/firewall/tasks/policy.yml` (lines 17–409)
- Impact: High maintenance burden. Adding a new reconcilable resource type requires duplicating ~80 lines of boilerplate. Bug fixes to the reconciliation pattern must be applied in 5+ places.
- Fix approach: Extract a reusable Ansible task file (e.g., `tasks/_reconcile_list.yml`) that accepts variable-driven parameters for `firewall-cmd` subcommands and desired/current lists, then `include_tasks` with `loop` or `vars` for each resource type. Alternatively, refactor into a custom filter plugin that computes the diff.

**WireGuard role lacks assertion validation:**
- Issue: The `wireguard` role has `meta/argument_specs.yml` declaring required variables, but has no `tasks/assert.yml` (unlike `firewall`, `docker`, and `network` roles which all have explicit assert task files). The `wireguard` role's `main.yml` jumps directly into `setup.yml` without an assertion gate.
- Files: `ansible/playbooks/roles/wireguard/tasks/main.yml`, `ansible/playbooks/roles/wireguard/meta/argument_specs.yml`
- Impact: If `wireguard_enabled: true` but required secrets are missing, the role will fail deep inside template rendering with a cryptic Jinja2 error rather than a clear assertion message at the top of the role.
- Fix approach: Add `tasks/assert.yml` to the wireguard role following the same pattern as other roles — import it before `setup.yml` in `main.yml`.

**`routing` role lacks assertion validation:**
- Issue: The `routing` role has no `meta/argument_specs.yml` and no `tasks/assert.yml`. The only task is `sysctl.yml` that sets `net.ipv4.ip_forward=1`, but there's no validation that the host actually needs routing enabled.
- Files: `ansible/playbooks/roles/routing/tasks/main.yml`, `ansible/playbooks/roles/routing/tasks/sysctl.yml`
- Impact: Running the routing role on an agent host would silently enable IP forwarding, which is incorrect for non-router hosts. The `bootstrap.yml` playbook only applies the `routing` role to `router` group hosts, but the role itself has no guard.
- Fix approach: Add `meta/argument_specs.yml` and `tasks/assert.yml` to validate that the role is being applied to a host that should have IP forwarding.

**base role assertion is minimal:**
- Issue: The `base` role's `assert.yml` only checks `os_family == 'RedHat'`. It does not validate other host requirements that subsequent roles depend on (e.g., NetworkManager being the network backend, `nmcli` being available, firewalld compatibility).
- Files: `ansible/playbooks/roles/base/tasks/assert.yml`
- Impact: Playbooks will fail with obscure errors on unsupported distros that pass the RedHat family check but lack NetworkManager or use a different firewall backend.
- Fix approach: Extend assertions to verify that `NetworkManager` is active and `nmcli` is available on the target host.

## Known Bugs

**No bugs confirmed — potential issues are documented under Fragile Areas.**

## Security Considerations

**WireGuard secrets stored locally on disk:**
- Risk: WireGuard private keys and preshared keys are stored in plaintext in `host_vars/*/secrets.yml` files on the control machine.
- Files: `ansible/inventory/host_vars/router-01/secrets.yml`, `ansible/inventory/host_vars/dmz-agent-01/secrets.yml`, `ansible/inventory/host_vars/secondary-ns-01/secrets.yml`
- Current mitigation: `secrets.yml` files are gitignored (`ansible/inventory/host_vars/*/secrets.yml` is in `.gitignore`), so they are NOT committed to version control. `secrets.example.yml` files with placeholder values are committed instead.
- Recommendations: The current secret-split approach is adequate for a lab environment. For production hardening, consider Ansible Vault encryption for the `secrets.yml` files, or use a secrets manager (e.g., HashiCorp Vault) with `ansible.builtin.vault` lookups.

**SSH key placeholder in cloud-init:**
- Risk: `cloud-init` user-data files contain `ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIFAKEPLACEHOLDERKEYFORLOCALUSEONLY student@example.invalid` — this is clearly a placeholder, but it is committed to git.
- Files: `cloud-init/iid-*/user-data.yml`
- Current mitigation: The key string contains `FAKEPLACEHOLDERKEYFORLOCALUSEONLY` and `example.invalid` domain, making it unambiguous as a non-real key.
- Recommendations: No action needed for lab context. In production, use Ansible Vault or environment-variable substitution for real keys.

**SSH host key checking disabled:**
- Risk: `ansible.cfg` sets `host_key_checking = False`, which allows man-in-the-middle attacks during SSH connections.
- Files: `ansible/ansible.cfg` (line 4)
- Current mitigation: Acceptable for a lab environment with controlled networks.
- Recommendations: For production deployment, enable host key checking and distribute known hosts via `known_hosts` file.

**WireGuard config rendered with mode 0600 but template contains secrets:**
- Risk: The `wg0.conf.j2` template renders WireGuard private keys. The task correctly sets `mode: "0600"` and `owner/group: root`, but Ansible renders the file on the control node in a temp directory before transferring.
- Files: `ansible/playbooks/roles/wireguard/templates/wg0.conf.j2`, `ansible/playbooks/roles/wireguard/tasks/setup.yml`
- Current mitigation: Ansible's default temp directory is `/tmp` with sticky bit, which mitigates casual reading. The final file on the target has correct permissions.
- Recommendations: Use `ansible.builtin.template` with `decrypt: true` if using Vault, or confirm that Ansible's local temp file cleanup is sufficient for lab use.

**Docker container runs with `--network host`:**
- Risk: The `nap-agent` container on both `dmz-agent-01` and `internal-agent-01` is configured with `network_mode: host`, which bypasses Docker network isolation and gives the container full access to the host network stack.
- Files: `ansible/inventory/host_vars/dmz-agent-01/main.yml` (line 47), `ansible/inventory/host_vars/internal-agent-01/main.yml` (line 37)
- Current mitigation: This is by design per the lab requirements (AGENTS.md documents this explicitly).
- Recommendations: Intentional for the lab. If refactored for production, use Docker bridge networks with explicit port mappings instead.

**docker-binfmt-register service runs privileged container:**
- Risk: The `docker-binfmt-register.service.j2` template runs `docker run --privileged --rm {{ docker_binfmt_image }} --install all`, which is a privileged container execution at boot time.
- Files: `ansible/playbooks/roles/docker/templates/docker-binfmt-register.service.j2`
- Current mitigation: This is the standard method for registering QEMU binfmt handlers via Docker. The service only runs once at boot and the container exits immediately after registration.
- Recommendations: Acceptable for lab. For production, consider using `tonistiigi/binfmt` directly via systemd without Docker, or pre-register binfmt handlers in the VM image.

## Performance Bottlenecks

**Firewall policy reconciliation — O(n²) task execution:**
- Problem: Each policy resource type (ingress zones, egress zones, protocols, ports) requires 5-6 tasks: query current state, initialize maps, build desired map, build current map, add missing, remove stale. With 5 policies × 5 resource types, this produces ~30+ tasks even if nothing changes.
- Files: `ansible/playbooks/roles/firewall/tasks/policy.yml`
- Cause: Ansible's declarative modules (`ansible.posix.firewalld`) don't support firewalld policy objects, forcing a read-modify-write approach with `ansible.builtin.command`.
- Improvement path: Write a custom Ansible module for `firewalld_policy` that handles the full lifecycle in a single idempotent task.

**Docker image archive copy is unconditionally slow:**
- Problem: `ansible.builtin.copy` in `workloads.yml` copies the full Docker image tar (252 MB for `nap-agent.tar`) to the remote host on every playbook run, even if the file hasn't changed.
- Files: `ansible/playbooks/roles/docker/tasks/workloads.yml` (line 18–27)
- Cause: `ansible.builtin.copy` always computes checksums for large files, and the 252 MB `nap-agent.tar` file is slow to transfer. Ansible's `copy` module does checksum comparison but still has to read the entire file on both sides.
- Improvement path: Use `ansible.builtin.synchronize` (rsync-based) for large file transfers, or better yet, host the image on a registry and pull it with `docker_image_pull` instead of local tar copy + `docker_image_load`.

**Full system upgrade on every bootstrap:**
- Problem: The `base` role runs `dnf name="*" state=latest` as a default-enabled task (controlled by `base_upgrade_enabled` which defaults to `false` in `group_vars/all.yml` but `true` in the task unless explicitly overridden). Each run can add significant time.
- Files: `ansible/playbooks/roles/base/tasks/upgrade.yml`, `ansible/inventory/group_vars/all.yml`
- Cause: System upgrades can take 5-15 minutes depending on pending updates. The default `base_upgrade_enabled: false` in group vars mitigates this for re-runs, but fresh bootstraps that don't set this variable will default to the task's `default(true)`.
- Improvement path: The `group_vars/all.yml` correctly sets `base_upgrade_enabled: false`, which overrides the task default. This is acceptable but could be confusing. Consider making the task follow the group_vars default by using `default(false)` in the task itself.

## Fragile Areas

**NetworkManager zone binding "stickiness":**
- Files: `ansible/inventory/host_vars/*/main.yml`, `ansible/playbooks/roles/network/tasks/nmcli.yml`
- Why fragile: AGENTS.md explicitly documents that "Removing `network_interfaces[].zone` later does not automatically clear an already-written NetworkManager `connection.zone`." This means if you assign a zone to an interface via Ansible and later remove it from the config, the old zone assignment persists on the host. The `assert.yml` in the network role doesn't check for orphaned zone bindings.
- Safe modification: When removing a zone from `network_interfaces[]`, you must separately clear the NM connection zone with `nmcli connection modify <conn> connection.zone ""` or add a reconciliation step that removes stale zone assignments.
- Test coverage: No automated tests. Manual verification required by connecting to the host and running `nmcli -g connection.zone connection show <conn>`.

**Firewall policy reconciliation depends on correct `firewall_builtin_zones` list:**
- Files: `ansible/inventory/group_vars/all.yml`, `ansible/playbooks/roles/firewall/tasks/assert.yml`
- Why fragile: The `firewall_builtin_zones` list is hardcoded in `group_vars/all.yml` as `[public, trusted, home, work, internal, external, dmz, block, drop]`. If the target OS has a different set of built-in firewalld zones (e.g., different RHEL/AlmaLinux version), the `assert.yml` zone-reference validation will produce false failures.
- Safe modification: Keep the `firewall_builtin_zones` list synchronized with the target OS version. Consider dynamically querying available zones via `ansible.builtin.command: firewall-cmd --permanent --get-zones` at the start of the firewall role.
- Test coverage: No automated tests.

**Router-first bootstrap ordering assumption:**
- Files: `ansible/playbooks/bootstrap.yml`
- Why fragile: The playbook runs the router play first, then the zone hosts. Agent hosts use `ProxyJump` through the router for SSH. If the router play fails partway through (e.g., after changing network config but before completing firewall setup), the agents become unreachable and the playbook cannot recover without manual intervention.
- Safe modification: Ensure the router's network, firewall, and WireGuard configuration is fully idempotent before running agent plays. Consider adding a connectivity check between the router and agent plays.
- Test coverage: No health-check gate between plays.

**WireGuard `wg0.conf.j2` template — no idempotent file management:**
- Files: `ansible/playbooks/roles/wireguard/templates/wg0.conf.j2`, `ansible/playbooks/roles/wireguard/tasks/setup.yml`
- Why fragile: The WireGuard setup uses `ansible.builtin.template` to write the config and then `ansible.builtin.systemd` to start/enable `wg-quick@wg0`. If the config changes, the service needs to be restarted, but there's no handler to restart WireGuard when the template changes. The systemd task uses `state: started` which won't reload a running service.
- Safe modification: Add a handler that restarts `wg-quick@wg0` when `wg0.conf.j2` produces a changed result, and add `restart: true` or use handler-based restart logic.
- Test coverage: No automated tests.

**NetworkManager connection rename — non-idempotent:**
- Files: `ansible/playbooks/roles/network/tasks/nmcli.yml` (lines 17–51)
- Why fragile: The NM connection rename logic queries all connection names, then renames default connections (like `cloud-init eth0`) to the desired name (like `dmz-static`). This works on first run but on subsequent runs, if the default connection name no longer exists (because it was already renamed), the `when` condition skips silently. However, if a connection with the target name already exists that is NOT managed by Ansible, renaming may conflict.
- Safe modification: The `when` guards (`item.default_conn_name in network_conn_names.stdout_lines` and `item.conn_name not in network_conn_names.stdout_lines`) correctly handle idempotency, but edge cases like manually-created connections with the same name could cause issues. Consider adding an assertion that the resulting connection exists after configuration.
- Test coverage: No automated tests.

**Docker binfmt registration — ordering dependency on Docker daemon:**
- Files: `ansible/playbooks/roles/docker/templates/docker-binfmt-register.service.j2`, `ansible/playbooks/roles/docker/tasks/multiarch.yml`
- Why fragile: The systemd unit `docker-binfmt-register.service` has `After=docker.service` and `Requires=proc-sys-fs-binfmt_misc.mount`, plus a 10-iteration polling loop for Docker readiness. If Docker isn't ready within 10 seconds or the binfmt mount isn't available, the service fails. The multiarch role then runs a verification container — if binfmt registration failed silently, the assertion `docker_binfmt_test.stdout == 'x86_64'` catches it.
- Safe modification: The current retry logic is reasonable for lab context. For production, increase the Docker readiness retry count or add a more robust health check.
- Test coverage: Runtime assertion in `multiarch.yml` verifies `x86_64` output.

## Scaling Limits

**Single-router architecture:**
- Current capacity: 1 router VM handling all inter-zone traffic, NAT, and WireGuard VPN tunnel
- Limit: No redundancy. Router failure isolates all agent VMs and breaks VPN connectivity.
- Scaling path: Not applicable for lab context. For production, consider HA router pair with VRRP and conntrackd.

**Serial playbook execution:**
- Current capacity: `bootstrap.yml` runs router play first, then the zone hosts play sequentially for all hosts in `dmz` and `internal` groups.
- Limit: No parallelism between router and agents (intentional due to ProxyJump dependency). Agents within the same group could be parallelized but Ansible's default `serial: 1` isn't used — all agents run in parallel by default.
- Scaling path: For larger fleets, add `serial: 1` or batching to the agent play to avoid overwhelming the router's connection handling.

**Large Docker image in gitignored local file:**
- Current capacity: `ansible/playbooks/roles/docker/files/nap-agent.tar` is 252 MB, gitignored and replaced in tracked files by a 1 KB placeholder `nap-agent.example.tar`.
- Limit: Each developer/operator must manually obtain the real tar file. No integrity verification (checksum).
- Scaling path: Host the image in a container registry and use `community.docker.docker_image_pull` instead of local tar distribution.

## Dependencies at Risk

**`tonistiigi/binfmt:qemu-v10.0.4` — pinned third-party image:**
- Risk: Pinned to a specific version tag. If Docker Hub removes or retags this image, multiarch support breaks.
- Impact: amd64 containers on arm64 hosts will fail to run.
- Migration plan: Periodically update the version pin in `ansible/playbooks/roles/docker/defaults/main.yml`. The `docker_binfmt_image` default uses a specific tag (`qemu-v10.0.4`) while `argument_specs.yml` defaults to `latest` — this inconsistency can cause unexpected behavior.

**`alpine:3.23` vs `alpine:3.22` version inconsistency:**
- Risk: The `docker/defaults/main.yml` uses `docker_binfmt_test_image: alpine:3.23` but `docker/meta/argument_specs.yml` defaults to `alpine:3.22`. These should be the same value.
- Impact: If the role falls through to `argument_specs.yml` defaults, the test image version will differ from what developers expect based on `defaults/main.yml`.
- Migration plan: Align the versions. Use `defaults/main.yml` as the single source of truth and remove the redundant defaults from `argument_specs.yml`, or keep both in sync.

**Ansible `ansible.posix` and `community.general` collections:**
- Risk: The project depends on `ansible.posix.sysctl`, `ansible.posix.firewalld`, `community.general.nmcli`, `community.docker.docker_image_pull`, `community.docker.docker_image_load`, `community.docker.docker_container`, and `community.docker.docker_container_info`. No `requirements.yml` file exists to pin collection versions.
- Impact: Breaking changes in future collection versions could break the playbook.
- Migration plan: Add a `requirements.yml` file pinning exact collection versions (e.g., `ansible.posix:>=1.5.0,<2.0.0`).

## Missing Critical Features

**`bind9` role is unimplemented:**
- Problem: The `bind9` role exists in the role directory but contains only a TODO comment: `# TODO: Implement for Lab 2 (DNS)`.
- Files: `ansible/playbooks/roles/bind9/tasks/main.yml`
- Blocks: DNS server deployment for `primary-ns-01`, `secondary-ns-01`, and `dns-01` hosts, which have `bind9_enabled: true` set in their `host_vars`.

**No integration or smoke tests:**
- Problem: There are no test playbooks, Molecule scenarios, or verification scripts to validate that the bootstrap configuration produces the expected network topology, firewall rules, and WireGuard connectivity.
- Blocks: Confident refactoring. Any change to roles, variable structures, or host configurations requires manual testing against live VMs.
- Priority: High — adding Molecule or Testinfra tests for the firewall and network roles would catch regressions.

**No `requirements.yml` for Ansible collections or Galaxy roles:**
- Problem: The project uses multiple Ansible collections (`ansible.posix`, `community.general`, `community.docker`) but has no `requirements.yml` to declare version constraints.
- Blocks: Reproducible playbook runs across different environments. Ansible might pick up incompatible collection versions.
- Priority: Medium — `requirements.yml` is quick to add and prevents subtle failures.

**No health-check gate between router and agent plays:**
- Problem: `bootstrap.yml` doesn't verify that the router's firewall, network, and WireGuard are fully operational before starting the agent play. Agent hosts depend on the router for SSH ProxyJump.
- Blocks: Automatic error recovery. If the router play partially fails, the agent play will hang on unreachable SSH connections.
- Priority: Medium — add a `wait_for` or custom assertion task between plays.

**Cloud-init configs are not generated from Ansible variables:**
- Problem: Cloud-init network configurations in `cloud-init/iid-*/network-config.yml` duplicate IP addresses, gateway settings, and DNS server values that also exist in Ansible `host_vars/*/main.yml`. Changes must be synchronized manually across both sources.
- Blocks: Single-source-of-truth for VM network configuration. Risk of configuration drift between cloud-init and Ansible.
- Priority: Low for lab context. Could be addressed with a template engine that generates cloud-init configs from shared variable files.

## Test Coverage Gaps

**Entire Ansible codebase — no automated tests:**
- What's not tested: All roles (`base`, `firewall`, `routing`, `network`, `wireguard`, `docker`, `bind9`), the `bootstrap.yml` playbook, host variable assertions, and cross-host connectivity.
- Files: No `tests/`, `molecule/`, or `test_*.yml` files exist anywhere in the repository.
- Risk: Refactoring or variable changes can break the entire lab setup silently. The only testing method is running the full playbook against live VMs and manually verifying.
- Priority: High — even basic assertion-only test playbooks would catch variable misconfigurations.

**Cloud-init → Ansible configuration drift:**
- What's not tested: Consistency between cloud-init network configs (`cloud-init/iid-*/network-config.yml`) and Ansible host variables (`ansible/inventory/host_vars/*/main.yml`). The cloud-init uses `eth0` naming and static IPs that must match what Ansible expects.
- Files: All cloud-init and host_vars files
- Risk: IP address or gateway mismatches between cloud-init and Ansible would cause networking failures.
- Priority: Medium — a simple diff script or template generator could validate consistency.

**Firewall policy reconciliation correctness:**
- What's not tested: The complex query-diff-apply logic in `policy.yml` for adding/removing firewalld policy ingress zones, egress zones, protocols, and ports. Edge cases like empty lists, overlapping zone references, and policy name collisions with zone names are only validated by the `assert.yml` checks.
- Files: `ansible/playbooks/roles/firewall/tasks/policy.yml` (546 lines)
- Risk: Refactoring the reconciliation pattern can introduce regressions that allow stale rules to persist or required rules to be silently skipped.
- Priority: Medium — this is the most complex task file in the repository.

---

*Concerns audit: 2026-05-05*