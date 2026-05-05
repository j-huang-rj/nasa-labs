# Testing Patterns

**Analysis Date:** 2026-05-05

## Test Framework

**Runner:**
- No automated test framework detected
- No Molecule, pytest, ansible-test, or testinfra infrastructure
- No CI runner or pipeline

**Assertion Library:**
- Ansible built-in `ansible.builtin.assert` module for runtime validation
- `meta/argument_specs.yml` for role entry-point argument validation

**Run Commands:**
```bash
# No test command exists. Validation happens at playbook runtime:
ansible-playbook playbooks/bootstrap.yml

# Lint (mentioned in AGENTS.md but no config exists yet):
ansible-lint

# Manual verification steps documented in:
manual/1-0.md
```

## Test File Organization

**Location:**
- No dedicated test directory or files
- Inline validation within role task files

**Naming:**
- `assert.yml` — role assertion/validations task file in each role that takes variables
- `meta/argument_specs.yml` — role argument specification
- `manual/<lab>.md` — human verification walkthroughs

**Structure:**
```
ansible/playbooks/roles/<role>/
├── tasks/
│   ├── main.yml          # Orchestrator (includes phase files)
│   ├── assert.yml        # Runtime assertions (validation)
│   ├── install.yml       # Install phase tasks
│   └── configure.yml     # Configure phase tasks
├── meta/
│   └── argument_specs.yml  # Role argument validation
├── handlers/
│   └── main.yml           # Service handlers
├── defaults/
│   └── main.yml           # Role defaults
└── templates/             # Jinja2 templates
```

## Test Structure

**Suite Organization:**
- No formal test suites. Validation is embedded in role task flows.
- Each role includes an `assert.yml` that runs before functional tasks.

**Argument Specs (pre-task validation):**
```yaml
# ansible/playbooks/roles/firewall/meta/argument_specs.yml
argument_specs:
  main:
    short_description: Firewall configuration
    options:
      firewall_builtin_zones:
        type: "list"
        elements: "dict"
        required: true
```

**Assertion Tasks (runtime validation):**
```yaml
# ansible/playbooks/roles/network/tasks/assert.yml
- name: "PHASE [assert : Validate network_interfaces is defined]"
  ansible.builtin.assert:
    that:
      - network_interfaces is defined
      - network_interfaces | length > 0
    quiet: true
    fail_msg: "network_interfaces must be defined and non-empty"
```

**Patterns:**
- **Pre-flight validation:** `assert.yml` runs first in `tasks/main.yml` to fail fast on invalid configuration
- **Argument specs:** `meta/argument_specs.yml` validates role parameters before any task executes
- **Post-action verification:** Some roles verify results after applying changes (e.g., Docker role checks QEMU registration, container states)
- **Custom fail messages:** Every `assert` task includes a `fail_msg` string explaining what went wrong

## Mocking

**Framework:** Not applicable — infrastructure-as-code project

**Patterns:**
- No mocking framework or mocking patterns
- Dry-run validation is available via `ansible-playbook --check` (check mode)
- Check mode does not apply to all modules (e.g., templating, service restarts)

**What to Mock:**
- Not applicable — no unit tests exist

**What NOT to Mock:**
- Not applicable — no unit tests exist

## Fixtures and Factories

**Test Data:**
- `inventory/host_vars/*/secrets.example.yml` — committed template with commented-out placeholders for secret values
- `ansible/inventory/hosts.example.yml` — example inventory with schema annotation

**Location:**
- No fixtures directory or factory patterns

## Coverage

**Requirements:** None enforced

**View Coverage:**
- No coverage tooling
- Ansible check mode (`--check`) can validate playbook syntax and dry-run execution
- `ansible-playbook --syntax-check` validates YAML/Ansible syntax

## Test Types

**Unit Tests:**
- Not used. No unit test files or framework.

**Integration Tests:**
- Not used. No Molecule or testinfra integration tests.

**E2E Tests:**
- Not used. No automated E2E framework.

**Manual Tests:**
- `manual/` directory contains step-by-step writeups for human verification
- Example: `manual/1-0.md` — walkthrough for Lab 1-0 setup with expected command outputs

**Runtime Validation:**
- `ansible.builtin.assert` tasks in `assert.yml` files validate configuration before applying
- `meta/argument_specs.yml` validates role arguments before any task runs
- Feature flags (`when: wireguard_enabled`) conditionally skip roles, reducing unnecessary execution
- Handler notifications verify service state after configuration changes

## Common Patterns

**Async Testing:**
- Not applicable — Ansible handles async natively via modules

**Error Testing:**
```yaml
# Assert tasks test for invalid input:
- name: "PHASE [assert : Validate firewall_bindings]"
  ansible.builtin.assert:
    that:
      - firewall_bindings is defined
      - firewall_bindings | selectattr('ifname', 'defined') | list | length > 0
    quiet: true
    fail_msg: "firewall_bindings must contain items with ifname defined"
```

**Post-action verification:**
```yaml
# Docker role verifies multiarch support after setup:
- name: "PHASE [configure : Verify QEMU binfmt registration]"
  ansible.builtin.assert:
    that:
      - binfmt_check.stderr is defined
    quiet: true
    fail_msg: "QEMU binfmt registration not found"
```

## Testing Gaps

**No Automated Testing:**
- The project has zero automated tests — no Molecule scenarios, no pytest, no CI pipeline
- All verification is manual via `manual/` writeups or runtime assertions

**No CI/CD:**
- No GitHub Actions, GitLab CI, or any CI pipeline exists
- No automated linting or syntax checking on commit

**Missing Config:**
- AGENTS.md references `ansible-lint` but no `.ansible-lint` configuration file exists
- No `.yamllint` configuration
- No `.pre-commit-config.yaml` for pre-commit hooks

**Recommendation — Add Molecule:**
- Molecule is the standard Ansible testing framework
- Suggested structure:
  ```
  ansible/playbooks/roles/<role>/molecule/default/
  ├── converge.yml        # Playbook that runs the role
  ├── verify.yml           # Post-convergence assertions
  ├── molecule.yml         # Driver and platform config
  └── tests/
      └── test_default.py  # Testinfra tests
  ```

**Recommendation — Add ansible-lint config:**
- Create `.ansible-lint` with rules matching project conventions:
  - Enforce FQCN for all modules (already used in practice)
  - Enforce `quiet: true` on assert tasks
  - Enforce `loop_control: label:` on all loops
  - Enforce task naming: `PHASE [...]` pattern
  - Enforce `become: false` on debug/assert tasks

---

*Testing analysis: 2026-05-05*