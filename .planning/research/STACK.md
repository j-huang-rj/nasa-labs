# Stack Research

**Domain:** BIND9 DNS infrastructure on AlmaLinux with Ansible automation
**Researched:** 2026-05-05
**Confidence:** HIGH

## Recommended Stack

### Core Technologies

| Technology | Version | Purpose | Why Recommended | Confidence |
|------------|---------|---------|-----------------|------------|
| AlmaLinux | 9.x current repo line (9.7 AppStream metadata observed) | Base OS for all three DNS VMs | This is the lowest-risk baseline for the lab because the repo already targets Alma/RHEL conventions, firewalld, SELinux, and DNF. More importantly, AlmaLinux 9 AppStream ships the exact BIND feature set this assignment needs without custom packaging. | HIGH |
| BIND 9 | `9.16.23-34.el9_7.x` on AlmaLinux 9 AppStream | Authoritative primary, authoritative secondary, and internal recursive resolver | Use the distro-packaged BIND, not an upstream source build. The packaged line supports `view`, `update-policy`, TSIG-authenticated DDNS, `allow-transfer`/`also-notify`, `dnssec-policy`, inline-signing, and `rndc` journal workflows. That covers the lab's split-view DNS, DDNS, DNSSEC, and transfer requirements with the least integration risk. | HIGH |
| Ansible Core | `2.20.5` | Control-plane automation from the controller node | Use `ansible-core`, not the monolithic `ansible` bundle, so the controller environment stays explicit and reproducible. Core builtins are sufficient for package install, templating, validation, service management, and idempotent rollout. | HIGH |
| firewalld + Python bindings | `1.3.4-18.el9_7` + `python3-firewall 1.3.4-18.el9_7` | Expose DNS safely and constrain recursion/zone-transfer paths | The repository already standardizes on firewalld. Keeping DNS hosts on the same native firewall stack avoids one-off shell rules and fits the existing router-first playbook ordering. | HIGH |

### Supporting Libraries

| Library | Version | Purpose | When to Use | Confidence |
|---------|---------|---------|-------------|------------|
| `ansible.posix` | `2.1.0` | firewalld and SELinux-related Ansible modules | Use for host firewall state and any SELinux toggles. Even if the BIND role mostly uses builtins, this collection keeps DNS hosts aligned with the rest of the repo's firewalld approach. | HIGH |
| `community.general` | `12.6.0` | `nmcli` and general-purpose Linux helpers | Use when DNS hosts continue to rely on the existing NetworkManager-driven network role. This keeps DNS automation consistent with the repo's current component-role pattern instead of inventing a DNS-only network path. | HIGH |
| `ansible.utils` | `6.0.2` | IP/subnet filters for Jinja templating | Use when deriving ACLs, reverse-zone fragments, or RFC 2317 classless delegation values from the dynamic VPN subnet ID. This is the cleanest way to avoid hand-rolled string math in templates. | MEDIUM |
| `dnspython` | `2.8.0` | Controller-side DNS assertions and smoke tests | Use if you want automated verification beyond `dig`, especially for checking SOA/NS answers, view-specific responses, reverse-zone coverage, and DNSSEC AD-bit behavior from tests or helper scripts. | MEDIUM |

### Development Tools

| Tool | Purpose | Notes | Confidence |
|------|---------|-------|------------|
| `bind-utils` | Operational validation and troubleshooting | Keep the package version matched to the server package line. Use it for query testing, config/zone validation, and DDNS smoke tests before restarting `named`. | HIGH |
| `bind-dnssec-utils` | DNSSEC key and DS record operations | Install on at least the primary NS. It is the right companion package for DS extraction and DNSSEC troubleshooting, even if BIND handles inline signing automatically. | HIGH |
| `ansible-lint` | Playbook and role quality gate | Run it on the controller before applying the new `bind9` role. This repo already values idempotent, componentized roles; linting will catch the most common regressions early. | HIGH |

## Installation

```bash
# Controller node
python3 -m pip install \
  "ansible-core==2.20.5" \
  "ansible-lint==26.4.0" \
  "dnspython==2.8.0"

ansible-galaxy collection install \
  "ansible.posix:==2.1.0" \
  "community.general:==12.6.0" \
  "ansible.utils:==6.0.2"

# AlmaLinux 9 DNS hosts
sudo dnf install -y \
  bind-9.16.23-34.el9_7.1 \
  bind-utils-9.16.23-34.el9_7.1 \
  bind-dnssec-utils-9.16.23-34.el9_7.1 \
  firewalld-1.3.4-18.el9_7 \
  python3-firewall-1.3.4-18.el9_7
```

**Note:** If your mirror exposes a newer errata suffix than the one above, keep all `bind*` packages on the same release family rather than mixing builds.

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| AlmaLinux 9 + AppStream BIND 9.16 | AlmaLinux 10 + AppStream BIND 9.18 (`9.18.33-10.el10_1.2`) | Use AlmaLinux 10 only if you are intentionally re-basing the VM images and are willing to revalidate the course environment. It is a cleaner long-term platform, but it is not the safest lab baseline. |
| `ansible-core==2.20.5` + pinned collections | `ansible` community package | Use the community package only if you value convenience over reproducibility. For coursework and CI, explicit controller + collection pinning is the better default. |
| Explicit `dnssec-policy` + inline-signing | Manual `dnssec-signzone` pipeline | Use manual signing only for static zones with no DDNS. This assignment requires DDNS and DNSSEC together, so BIND-managed inline signing is the standard choice. |

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| `bind-chroot` | It adds path, SELinux, journal-file, and key-directory complexity with no grading benefit. That is the wrong tradeoff for a three-VM course lab. | Standard `named` service with default AlmaLinux paths (`/etc/named.conf`, `/var/named/`) |
| Upstream BIND tarball/source builds on AlmaLinux | You lose distro integration and create a harder-to-debug systemd/SELinux/package-management story for zero course value. | AlmaLinux AppStream `bind`, `bind-utils`, and `bind-dnssec-utils` packages |
| Broad `allow-update` ACLs, especially `allow-update { any; };` | BIND's docs are clear that `update-policy` is the fine-grained, key-based control surface, and it cannot be combined with `allow-update`. Broad ACLs are both less secure and less precise. | `update-policy` rules tied to a TSIG key and the exact dynamic names/PTRs you intend to update |
| Manual `dnssec-signzone` cron jobs | They fight BIND's journaled dynamic-zone model and create brittle operational steps around DDNS changes. | `dnssec-policy` with explicit `ECDSAP256SHA256` keys and inline-signing |
| PowerDNS, NSD, Unbound, or mixed-daemon stacks | The assignment explicitly says BIND9 is the only guaranteed-tested implementation. Using anything else raises the risk of lab-specific incompatibilities. | BIND9 for all three roles |

## Stack Patterns by Variant

**If you are staying on the current lab baseline (recommended):**
- Use AlmaLinux 9 + AppStream BIND 9.16 + standard `named` service + firewalld + pinned `ansible-core` collections.
- Because it matches the repo's current assumptions and minimizes platform drift while still satisfying split views, DDNS, DNSSEC, and transfers.

**If you intentionally rebase the VM images for a fresher OS line:**
- Use AlmaLinux 10 + AppStream BIND 9.18.33 + the same Ansible stack.
- Because AlmaLinux 10 moves closer to current upstream-supported BIND trains, but it is a platform change and should be treated as one.

**If the zone is both dynamic and DNSSEC-signed (this lab):**
- Use an explicit `dnssec-policy` with algorithm `ecdsap256sha256`, plus inline-signing and `rndc sync/freeze/thaw` for operational edits.
- Because BIND's own KASP workflow is designed for exactly this combination; manual signing is not.

## Version Compatibility

| Package A | Compatible With | Notes |
|-----------|-----------------|-------|
| `bind-9.16.23-34.el9_7.x` | `bind-utils-9.16.23-34.el9_7.x`, `bind-dnssec-utils-9.16.23-34.el9_7.x` | Keep server and admin-tool packages on the same AppStream line. |
| `firewalld-1.3.4-18.el9_7` | `python3-firewall-1.3.4-18.el9_7` | Match userspace firewalld and Python bindings. |
| `ansible-core==2.20.5` | `ansible.posix==2.1.0`, `community.general==12.6.0`, `ansible.utils==6.0.2` | Pin these together in a controller virtualenv and commit a `requirements.yml` for collections. |
| `bind-9.18.33-10.el10_1.2` | matching `bind-utils` and `bind-dnssec-utils` on AlmaLinux 10 | Valid only for the AlmaLinux 10 variant. |

## Sources

- Context7 `/websites/bind9_readthedocs_io_en_stable` — verified `view`, `update-policy`, `allow-transfer`, `also-notify`, `dnssec-policy`, inline-signing, and `rndc` operational workflow. HIGH
- https://www.isc.org/download/ — verified current upstream BIND trains (`9.20.22`, `9.18.48`) to compare against distro-packaged lines. HIGH
- https://repo.almalinux.org/almalinux/9/AppStream/x86_64/os/repodata/repomd.xml — official AlmaLinux 9 repository metadata used to verify `bind`, `bind-utils`, `bind-dnssec-utils`, and `bind-chroot` package versions. HIGH
- https://repo.almalinux.org/almalinux/9/BaseOS/x86_64/os/repodata/repomd.xml — official AlmaLinux 9 repository metadata used to verify `firewalld` and `python3-firewall` versions. HIGH
- https://repo.almalinux.org/almalinux/10/AppStream/x86_64/os/repodata/repomd.xml — official AlmaLinux 10 repository metadata used to verify the rebase alternative (`bind 9.18.33`). HIGH
- https://docs.ansible.com/ansible/latest/reference_appendices/release_and_maintenance.html — verified maintained `ansible-core` release policy. HIGH
- https://pypi.org/pypi/ansible-core/json — verified current `ansible-core` version `2.20.5`. HIGH
- https://galaxy.ansible.com/api/v3/plugin/ansible/content/published/collections/index/ansible/posix/versions/ — verified `ansible.posix` version `2.1.0`. HIGH
- https://galaxy.ansible.com/api/v3/plugin/ansible/content/published/collections/index/community/general/versions/ — verified `community.general` version `12.6.0`. HIGH
- https://galaxy.ansible.com/api/v3/plugin/ansible/content/published/collections/index/ansible/utils/versions/ — verified `ansible.utils` version `6.0.2`. HIGH
- https://pypi.org/pypi/ansible-lint/json and https://pypi.org/pypi/dnspython/json — verified controller-side tool versions. HIGH

---
*Stack research for: BIND9 DNS infrastructure on AlmaLinux with Ansible automation*
*Researched: 2026-05-05*
