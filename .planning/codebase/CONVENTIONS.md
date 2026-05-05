# Coding Conventions

**Analysis Date:** 2026-05-05

## Naming Patterns

**Files:**
- Ansible playbooks: `snake_case.yml` (e.g., `bootstrap.yml`)
- Role task files: `snake_case.yml` named after phases (e.g., `assert.yml`, `install.yml`, `configure.yml`)
- Role directories: `snake_case` (e.g., `wireguard`, `bind9`)
- Inventory files: `snake_case.yml` (e.g., `hosts.example.yml`, `main.yml`, `secrets.example.yml`)
- Cloud-init files: `user-data-<hostname>.yml` and `meta-data-<hostname>.yml`

**Ansible Task Names:**
- Functional tasks: `PHASE [<phase_name> : <description>]`
  - Example: `PHASE [install : Install Docker packages]`
  - Example: `PHASE [configure : Set daemon configuration]`
- Boundary markers: `START` and `END` debug tasks for roles and phases
  - Example: `START - Docker role`
  - Example: `END - Docker role`
  - Example: `PHASE [install : START]`, `PHASE [install : END]`
- Handler names: `PHASE [handler : <description>]` or `HANDLER [<role> : <description>]`
  - Example: `PHASE [handler : Reload firewalld]`
  - Example: `HANDLER [docker : Restart Docker service]`

**Variables:**
- snake_case with role prefix for role-scoped variables
- Examples: `docker_binfmt_enabled`, `firewall_builtin_zones`, `network_interfaces`, `wireguard_enabled`
- Feature flags: boolean variables suffixed with `_enabled` (e.g., `wireguard_enabled`, `docker_enabled`, `bind9_enabled`, `base_upgrade_enabled`)
- Secrets: stored separately in `secrets.yml` (gitignored), with `secrets.example.yml` (committed, commented-out) as template

**Group/Host Variables:**
- `host_vars/<hostname>/main.yml` — non-secret host configuration
- `host_vars/<hostname>/secrets.yml` — gitignored secrets
- `group_vars/<group>/main.yml` — group-level configuration

## Code Style

**Formatting:**
- No `.editorconfig` or `.prettierrc` detected
- YAML indent: 2 spaces (consistent across all files)
- Ansible module arguments: one per line in task definitions
- Lists in YAML: use `- item` format with consistent indentation

**Linting:**
- No `.ansible-lint` config file found (project root or `ansible/`)
- No `.yamllint` config found
- No `.pre-commit-config.yaml` found
- AGENTS.md references running `ansible-lint` as a requirement but no config exists yet
- **Recommendation:** Add `.ansible-lint` configuration file to enforce conventions programmatically

**FQCN (Fully Qualified Collection Names):**
- All Ansible modules use fully qualified names
- `ansible.builtin.*` for built-in modules (e.g., `ansible.builtin.debug`, `ansible.builtin.assert`, `ansible.builtin.template`)
- `ansible.posix.*` for POSIX modules (e.g., `ansible.posix.firewalld`, `ansible.posix.sysctl`)
- `community.general.*` for community modules (e.g., `community.general.ini_file`)
- `community.docker.*` for Docker modules (e.g., `community.docker.docker_container`)
- **Always use FQCN** — never use short module names

## Import Organization

**Role task includes:**
- `tasks/main.yml` is the orchestrator that includes phase-specific task files
- Include pattern uses `ansible.builtin.include_tasks` with conditional tags
- Example from `docker/tasks/main.yml`:
  ```yaml
  - ansible.builtin.include_tasks: assert.yml
  - ansible.builtin.include_tasks: install.yml
  - ansible.builtin.include_tasks: configure.yml
  ```

**Playbook structure:**
- Single playbook file `playbooks/bootstrap.yml`
- Two plays: router play (runs first), then agent play (runs after router)
- Role inclusion uses `ansible.builtin.include_role` with `when` conditions for feature flags

**Variable precedence:**
- Role defaults → `defaults/main.yml` (lowest priority)
- Group vars → `group_vars/<group>/main.yml`
- Host vars → `host_vars/<hostname>/main.yml`
- Host secrets → `host_vars/<hostname>/secrets.yml` (highest priority for secrets)

## Error Handling

**Patterns:**
- **Assertions:** Every role that accepts variables has `assert.yml` with `ansible.builtin.assert` tasks
  - `quiet: true` suppresses verbose output on success
  - Custom `fail_msg` strings provide actionable error messages
  - Example:
    ```yaml
    - name: "PHASE [assert : Validate network_interfaces is defined]"
      ansible.builtin.assert:
        that:
          - network_interfaces is defined
          - network_interfaces | length > 0
        quiet: true
        fail_msg: "network_interfaces must be defined and non-empty"
    ```
- **Argument specs:** `meta/argument_specs.yml` validates role entry arguments before task execution
  - Used by: docker, firewall, network, wireguard roles
  - Example from `firewall/meta/argument_specs.yml`:
    ```yaml
    argument_specs:
      main:
        short_description: Firewall configuration
        options:
          firewall_builtin_zones:
            type: "list"
            elements: "dict"
            required: true
    ```
- **Conditional execution:** Feature flags (`when: wireguard_enabled`, `when: docker_enabled`) prevent roles from running when not applicable
- **become_privilege:** `become: false` on debug and assert tasks; default `become: true` at playbook level

**Handler restarts:**
- Handlers use `listen` to group related restart triggers
- Example: Docker handler listens for `"PHASE [handler : Restart Docker service]"`

## Logging

**Framework:** Ansible built-in debug module

**Patterns:**
- Role boundary logging: `START` and `END` debug messages at role beginning and end
- Phase boundary logging: `PHASE [<phase> : START]` and `PHASE [<phase> : END]` debug messages
- Example:
  ```yaml
  - name: START - Firewall role
    ansible.builtin.debug:
      msg: "Starting firewall role"
  ```
- Verbosity: `ansible.builtin.debug` with `verbosity:` parameter for conditional output

## Comments

**When to Comment:**
- YAML schema hints: `# yaml-language-server: $schema=...` at top of cloud-init and inventory files
- TODO markers for future work (only one found: `bind9/tasks/main.yml` has a TODO for Lab 2)
- Variable documentation in `main.yml` files via inline comments

**JSDoc/TSDoc:**
- Not applicable (YAML/Ansible project, not TypeScript)

## Function Design

**Size:** 
- Role task files are phase-scoped and typically under 100 lines each
- `tasks/main.yml` files are orchestrators (typically 10-30 lines)
- Actual logic lives in phase-specific files (`install.yml`, `configure.yml`, `assert.yml`)

**Parameters:** 
- Role parameters defined in `meta/argument_specs.yml` with type validation
- Variables passed through `host_vars`/`group_vars` with defaults in `defaults/main.yml`

**Return Values:** 
- Ansible tasks register variables when needed for downstream conditional logic
- Example: `register: docker_add_repo_result` followed by conditional task

## Module Design

**Exports:**
- Each role exposes a `tasks/main.yml` as the single entry point
- Roles are self-contained component units, not system roles
- **Component Roles pattern:** Roles are functional components (`base`, `docker`, `firewall`, `network`, `routing`, `wireguard`, `bind9`), NOT host-mapped system roles (no `router` or `agent` role)

**Barrel Files:**
- `tasks/main.yml` acts as the barrel/orchestrator for each role
- `inventory/group_vars/` and `inventory/host_vars/` organize variables by host/group

## Ansible-Specific Conventions

**Loop discipline:**
- All loops use `loop_control: label:` with meaningful identifiers
- Example:
  ```yaml
  loop: "{{ network_interfaces }}"
  loop_control:
    label: "{{ item.name }}"
  ```

**Zone ownership split:**
- NetworkManager-managed interfaces declare their firewalld zones in `network_interfaces[].zone`
- `firewall_bindings[].ifname` is reserved for interfaces outside NetworkManager lifecycle (currently only `wg0`)

**Secret management:**
- Commit `host_vars/*/main.yml` and `secrets.example.yml`
- Keep real local values in gitignored `host_vars/*/secrets.yml`
- Never commit actual secret values

**Play ordering (Router-First):**
- `bootstrap.yml` completes the router play before starting agent plays
- Inside router play, role order is: `base → firewall → routing → network → wireguard`
- This ensures firewalld policy, NAT, DNAT, and IP forwarding are prepared before managed interfaces come up

**Feature flag pattern:**
- Boolean variables (`*_enabled`) control optional role inclusion
- `when: <feature>_enabled` on `include_role` tasks
- This allows the same playbook to provision different host types conditionally