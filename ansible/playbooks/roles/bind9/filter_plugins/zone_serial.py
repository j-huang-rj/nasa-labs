#!/usr/bin/python

"""Custom Ansible filter plugin for computing SOA serials using read-and-bump strategy."""

import hashlib
import json

DOCUMENTATION = """
    name: bind9_zone_serial

    short_description: Compute SOA serial using read-and-bump strategy

    description:
      - Produces a monotonic SOA serial that bumps only when zone content
        changes, using a read-and-bump strategy.

      - Accepts the current serial and content hash from the existing zone
        file (read by the bind9_zone_state module). If the content hash
        matches, the current serial is preserved (idempotent). If the
        content hash differs, the serial is bumped to
        max(current_serial + 1, YYYYMMDD00).

      - For first deployment (current_serial=0), the serial starts at
        YYYYMMDD00.

      - The content hash covers zone name, default TTL ($TTL), SOA fields
        (minus serial), NS records, resource records, and the primary MNAME —
        everything that appears in the rendered zone file.

      - Returns a dict with 'serial' (int) and 'hash' (str) keys. The
        'hash' value is persisted in a C(<zone_file>.hash) sidecar file
        alongside the zone (BIND does not touch the sidecar, so the hash
        survives the canonical rewrite that BIND performs on zones with
        update-policy whenever the journal is merged).

    notes:
      - This strategy guarantees monotonicity: the serial always increases
        when content changes, and never decreases.

      - Dynamic (DDNS) zones: the hash reflects the static inventory model,
        not live dynamic updates. Because the role gates re-render on
        hash equality, an unchanged inventory leaves the live journal
        alone — but any inventory change to a DDNS zone WILL discard the
        journal and overwrite live dynamic records with the static model.
        DDNS zones should be seeded once and then excluded from ongoing
        templating, or managed separately.
"""

EXAMPLES = """
    # In a Jinja2 template:
    {% set result = item | bind9_zone_serial(
        primary_mname=bind9_primary_mname,
        date_prefix=bind9_soa_serial_date,
        current_serial=bind9_zone_current_state.get(item.file, {}).get('serial', 0),
        current_hash=bind9_zone_current_state.get(item.file, {}).get('hash', '')
    ) %}
    ; zone-hash: {{ result.hash }}
    {{ result.serial }} ; serial
"""

RETURN = """
    value:
        description: A dict with 'serial' (int) and 'hash' (str) keys.
        type: dict
"""


def _compute_content_hash(zone, primary_mname="", ttl=86400):
    """Compute a deterministic SHA-256 hash of zone content.

    Uses a whitelist of zone-file-relevant fields so that config-only
    changes (view, allow_transfer, etc.) don't spuriously bump the serial.

    Args:
        zone: A dict representing a BIND9 zone definition.
        primary_mname: The primary nameserver FQDN (MNAME in SOA).
        ttl: The default TTL value rendered in the zone file ($TTL directive).

    Returns:
        A hex string (first 12 chars of SHA-256 digest).
    """
    soa = dict(zone["soa"])
    soa.pop("serial", None)

    hash_input = {
        "name": zone["name"],
        "primary_mname": primary_mname,
        "ttl": ttl,
        "soa": soa,
        "ns": zone["ns"],
        "records": zone["records"],
    }

    content = json.dumps(hash_input, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(content.encode()).hexdigest()[:12]


def _validate_zone(zone):
    """Validate the zone dict shape required for serial computation."""
    if not isinstance(zone, dict):
        raise TypeError(f"bind9_zone_serial expects a dict, got {type(zone).__name__}")

    required_keys = ("name", "soa", "ns", "records")
    missing = [k for k in required_keys if k not in zone]
    if missing:
        raise ValueError(
            f"bind9_zone_serial: zone dict missing required keys: {missing}"
        )

    if not isinstance(zone["soa"], dict):
        raise ValueError(
            f"bind9_zone_serial: zone['soa'] must be a dict, "
            f"got {type(zone['soa']).__name__}"
        )


def _validate_date_prefix(date_prefix):
    """Validate that date_prefix is an 8-digit YYYYMMDD string."""
    if not date_prefix:
        raise ValueError(
            "bind9_zone_serial: date_prefix is required "
            "(pass YYYYMMDD from ansible_facts)"
        )
    if len(date_prefix) != 8 or not date_prefix.isdigit():
        raise ValueError(
            f"bind9_zone_serial: date_prefix must be 8 digits (YYYYMMDD), "
            f"got '{date_prefix}'"
        )


def _validate_current_serial(current_serial):
    """Validate that current_serial is a non-negative int."""
    if not isinstance(current_serial, int):
        raise TypeError(
            f"bind9_zone_serial: current_serial must be an int, "
            f"got {type(current_serial).__name__}"
        )
    if current_serial < 0:
        raise ValueError(
            f"bind9_zone_serial: current_serial must be >= 0, got {current_serial}"
        )


def bind9_zone_serial(
    zone, primary_mname="", date_prefix="", current_serial=0, current_hash="", ttl=86400
):
    """Compute SOA serial using read-and-bump strategy.

    Produces a monotonic serial that only increases when zone content
    changes. The strategy is:

    1. Compute a content hash from the zone data.
    2. If the content hash matches current_hash (content unchanged),
       return the current serial unchanged (idempotent).
    3. If the content hash differs (content changed), bump the serial:
       new_serial = max(current_serial + 1, YYYYMMDD00)
    4. For first deployment (current_serial=0), start at YYYYMMDD00.

    Args:
        zone: A dict representing a BIND9 zone definition. Must contain
              at least 'name', 'soa', 'ns', and 'records' keys.
        primary_mname: The primary nameserver FQDN (MNAME field in SOA).
                       Included in the hash because it appears in the
                       rendered zone file but is not part of the zone dict.
        date_prefix: A YYYYMMDD string from the playbook run date. Used as
                     the date floor when bumping the serial.
        current_serial: The current SOA serial from the existing zone file
                        (0 if the file doesn't exist yet).
        current_hash: The content hash from the existing zone file
                      (empty string if the file doesn't exist or has no
                      hash comment).
        ttl: The default TTL value rendered in the zone file ($TTL directive).
             Included in the hash so that TTL changes trigger a serial bump.
             Defaults to 86400 to match the template's hardcoded value.

    Returns:
        A dict with 'serial' (int) and 'hash' (str) keys.

    Raises:
        TypeError: If zone is not a dict.
        ValueError: If zone is missing required keys or date_prefix is invalid.
    """
    _validate_zone(zone)
    _validate_date_prefix(date_prefix)
    _validate_current_serial(current_serial)

    content_hash = _compute_content_hash(zone, primary_mname, ttl)

    # Hash matches: content unchanged, preserve serial (idempotent).
    if current_hash and current_hash == content_hash:
        return {"serial": current_serial, "hash": content_hash}

    # Content changed (or first deployment): bump the serial.
    date_floor = int(date_prefix) * 100  # YYYYMMDD00

    if current_serial == 0:
        new_serial = date_floor
    else:
        new_serial = max(current_serial + 1, date_floor)

    return {"serial": new_serial, "hash": content_hash}


class FilterModule:
    """Ansible filter plugin for BIND9 zone serial computation."""

    def filters(self):
        return {
            "bind9_zone_serial": bind9_zone_serial,
        }
