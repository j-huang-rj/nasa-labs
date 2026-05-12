#!/usr/bin/python

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
---
module: bind9_zone_state

short_description: Read current SOA serials and content hashes from BIND9 zone files

description:
  - Reads existing zone files on the target host and extracts the SOA serial
    and zone content hash for each file.

  - The content hash is read from a sidecar file C(<zone_file>.hash) that
    the role writes alongside the zone file. The sidecar is used because
    BIND rewrites zone files with C(update-policy) (DDNS) into its own
    canonical format whenever the journal is merged, which strips embedded
    comments. A separate hash file survives that rewrite and gives the
    role a stable change-detection marker.

  - For backward compatibility (and smoother migration), this module also
    falls back to a C(; zone-hash:) comment inside the zone file if no
    sidecar is found. Once the sidecar is in place the comment fallback
    is no longer used.

  - Returns a dict keyed by zone file path, with values containing 'serial'
    (int) and 'hash' (str).

  - For zone files that don't exist yet, returns serial=0 and hash=''.

  - Extracts the SOA serial structurally from the SOA record, supporting
    both parenthesized (multiline) and unparenthesized (single-line) SOA
    formats. This is more robust than relying on "; serial" comments.

  - Fails the task if a zone file exists but cannot be read or does not
    contain a parseable SOA record. This prevents silent serial regression.
    Only truly missing files (first deployment) return zero-state.

options:
  zone_dir:
    description:
      - The directory where zone files are stored on the target host.
      - Typically C(/var/named).
    type: str
    required: true

  zone_files:
    description:
      - List of zone file relative paths (e.g., C(private/db.42.nasa)).
      - Each path is relative to C(zone_dir).
    type: list
    elements: str
    required: true
"""

EXAMPLES = r"""
- name: Read current zone state
  bind9_zone_state:
    zone_dir: /var/named
    zone_files:
      - private/db.42.nasa
      - public/db.42.nasa
  register: zone_state

- name: Set zone current state fact
  ansible.builtin.set_fact:
    bind9_zone_current_state: "{{ zone_state.zone_state }}"
"""

RETURN = r"""
zone_state:
  description: Dict keyed by zone file path with serial and hash info.
  type: dict
  returned: always
  sample:
    private/db.42.nasa:
      serial: 2026050900
      hash: a1b2c3d4e5f6
    public/db.42.nasa:
      serial: 0
      hash: ''
"""

import os
import re

from ansible.module_utils.basic import AnsibleModule

# SOA serial extraction.
#
# BIND zone files put the serial in either of two SOA shapes:
#
#   1. Parenthesized (multiline or single-line):
#        @ IN SOA ns1.example. admin.example. (
#            2026050900  ; serial
#            ...
#        )
#
#   2. Unparenthesized (single-line):
#        @ IN SOA ns1.example. admin.example. 2026050900 3600 900 604800 86400
#
# We try the parenthesized form first (this role's own output), then fall
# back to the flat form for externally-written files.
_SOA_SERIAL_PAREN_RE = re.compile(
    r"\bSOA\b\s+\S+\s+\S+\s*\(\s*(\d+)", re.IGNORECASE | re.DOTALL
)
_SOA_SERIAL_FLAT_RE = re.compile(r"\bSOA\b\s+\S+\s+\S+\s+(\d+)", re.IGNORECASE)

# Legacy in-zone hash storage, kept only as a migration fallback.
# Current/preferred storage is the `<zone_file>.hash` sidecar.
_ZONE_HASH_RE = re.compile(r";\s*zone-hash:\s*(\S+)")

_MODULE_NAME = "bind9_zone_state"


def _extract_serial(content):
    """Return the SOA serial as an int, or None if no SOA record is found."""
    for pattern in (_SOA_SERIAL_PAREN_RE, _SOA_SERIAL_FLAT_RE):
        match = pattern.search(content)
        if match:
            return int(match.group(1))
    return None


def _read_file(module, path):
    """Read a file and return its contents, or None if it doesn't exist.

    Any error other than FileNotFoundError fails the task — silent
    degradation could regress serials.
    """
    try:
        with open(path, "r") as f:
            return f.read()
    except FileNotFoundError:
        return None
    except (IOError, OSError) as e:
        module.fail_json(msg=f"{_MODULE_NAME}: failed to read {path}: {e}")


def _read_hash(module, zone_path, zone_content):
    """Return the persisted content hash for a zone.

    Prefers the `<zone_file>.hash` sidecar (BIND will not rewrite it).
    Falls back to the legacy in-zone `; zone-hash:` comment for migration.
    Returns an empty string if neither source provides a hash.
    """
    sidecar = _read_file(module, zone_path + ".hash")
    if sidecar is not None:
        return sidecar.strip()

    legacy = _ZONE_HASH_RE.search(zone_content)
    return legacy.group(1) if legacy else ""


def _read_zone_state(module, zone_dir, zone_file):
    """Return {'serial': int, 'hash': str} for one zone file."""
    path = os.path.join(zone_dir, zone_file)
    content = _read_file(module, path)

    # Missing file = first deployment; report zero-state.
    if content is None:
        return {"serial": 0, "hash": ""}

    serial = _extract_serial(content)
    if serial is None:
        module.fail_json(
            msg=(
                f"{_MODULE_NAME}: could not extract SOA serial from {path} "
                f"-- the file may be corrupted or not a valid zone file"
            )
        )

    return {"serial": serial, "hash": _read_hash(module, path, content)}


def main():
    module = AnsibleModule(
        argument_spec=dict(
            zone_dir=dict(type="str", required=True),
            zone_files=dict(type="list", elements="str", required=True),
        ),
        supports_check_mode=True,
    )

    zone_dir = module.params["zone_dir"]
    zone_files = module.params["zone_files"]

    zone_state = {zf: _read_zone_state(module, zone_dir, zf) for zf in zone_files}

    module.exit_json(changed=False, zone_state=zone_state)


if __name__ == "__main__":
    main()
