---
id: SEED-001
status: dormant
planted: 2026-05-06
planted_during: Phase 01 — bind9-role-foundation (complete)
trigger_when: Phase 2 — Primary Authoritative Zones
scope: Small
---

# SEED-001: Add setype: named_zone_t for bind9 zone files

## Why This Matters

SELinux conventions require zone files under `/var/named` (the non-dynamic zone directory) to carry the `named_zone_t` type. The current bind9 role already sets `named_conf_t` on config paths and `named_cache_t` on the dynamic zone dir, but static zone files (which will be created in a future phase) need `named_zone_t` to avoid AVC denials when named reads them.

Without this, zone file reads will fail silently under enforcing mode.

## When to Surface

**Trigger:** Phase 2 — Primary Authoritative Zones

This seed should be presented during `/gsd-plan-phase 2` when planning
zone file tasks for the bind9 role. Specifically:
- When adding zone file template/copy tasks to `bind9/tasks/config.yml`
- When writing files to `bind9_zone_dir` (`/var/named`)
- When configuring authoritative forward or reverse zones

## Scope Estimate

**Small** — Adding `setype: named_zone_t` to the zone file task(s) is a one-line attribute per task, consistent with the pattern already established in quick task 260506-i20.

## Breadcrumbs

Related code and decisions found in the current codebase:

- `ansible/playbooks/roles/bind9/tasks/config.yml` — lines 29, 38, 47, 57, 67: existing `setype` attributes (`named_conf_t`, `named_cache_t`)
- `ansible/playbooks/roles/bind9/defaults/main.yml` — lines 11-12: `bind9_zone_dir` and `bind9_dynamic_zone_dir` defaults
- `ansible/playbooks/roles/bind9/templates/named.options.conf.j2` — line 5: references `bind9_zone_dir`
- Decision [Quick 260506-i20]: Use Ansible-native `setype` attributes (no restorecon handler, no sefcontext)

## Notes

This was identified during the SELinux setype quick task (260506-i20). The `named_zone_t` type was intentionally deferred because no zone file tasks exist yet — it should be applied when zone file template/copy tasks are added in Phase 2 (Primary Authoritative Zones).