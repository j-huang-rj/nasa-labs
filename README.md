# Network Administration Lab Environment

This repository tracks incremental NASA (Network Administration) course labs.

- `lab/` contains assignment materials organized by phase.
- `manual/` contains writeups/manual steps organized by phase.
- For local Ansible WireGuard secrets, copy `ansible/inventory/host_vars/*/secrets.example.yml` to `secrets.yml` and fill in local values.
- `cloud-init/**/user-data.yml`, `meta-data.yml`, and `network-config.yml` are tracked templates; customize them locally before use.
- Keep the generic `student` username aligned between `cloud-init` templates and `ansible/inventory/hosts.yml`, or change both together for your local environment.
- The course Docker image tarball is intentionally tracked in this repository.
