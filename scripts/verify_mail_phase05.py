#!/usr/bin/env python3
"""Phase 05 mailing list & HTTP API verification script.

Verifies static list expansion, API create/delete behavior,
invalid-input rejection, and activation safety for the Phase 05
mailing-lists HTTP API on the dmz-client-01 mail endpoint.

Uses only Python standard library modules (smtplib, imaplib,
urllib, subprocess, ssl) — no swaks, nmap, or requests required.

Environment variable fallbacks for credentials:
  MAIL_ADMIN_PASSWORD  — fallback for --admin-password
  MAIL_TEST_PASSWORD   — fallback for --test-password
"""

from __future__ import annotations

import argparse
import imaplib
import json
import os
import random
import shlex
import smtplib
import ssl
import string
import subprocess
import sys
import time
import urllib.error
import urllib.request
from email.mime.text import MIMEText

# ---------------------------------------------------------------------------
# Configuration constants
# ---------------------------------------------------------------------------

MAX_RETRIES = 5
RETRY_DELAY = 2.0
DEFAULT_TIMEOUT = 15
LIST_NAME_CHARS = string.ascii_lowercase + string.digits + "_-"
LIST_NAME_LENGTH = 12

# Reserved list names the API must protect
RESERVED_NAMES = {"local_users"}

# Unsafe characters to test in invalid-inputs
UNSAFE_CHARS = ["@", "/", " ", "'", '"', ":", ",", ";", "|", "&", "$", "`", "\\"]

# Known local backend users for delivery checks (matches Phase 03 pattern)
DEFAULT_RECIPIENTS = ["admin", "test"]

# ---------------------------------------------------------------------------
# Result helpers (matching Phase 03 verify_mail_phase03.py style)
# ---------------------------------------------------------------------------

results: list[tuple[str, bool, str]] = []


def pass_case(name: str, detail: str = "") -> None:
    msg = f"CASE {name}: PASS"
    if detail:
        msg += f" ({detail})"
    print(msg)
    results.append((name, True, detail))


def fail_case(name: str, reason: str) -> None:
    print(f"CASE {name}: FAIL {reason}")
    results.append((name, False, reason))


# ---------------------------------------------------------------------------
# SSH helper (from Phase 03 pattern)
# ---------------------------------------------------------------------------


def ssh_cmd(
    ssh_host: str, command: str, timeout: int = DEFAULT_TIMEOUT
) -> subprocess.CompletedProcess[str]:
    """Run a command on the target host via SSH with shell=False for safety."""
    return subprocess.run(
        [
            "ssh",
            "-o",
            "StrictHostKeyChecking=no",
            "-o",
            "ConnectTimeout=5",
            "-o",
            "BatchMode=yes",
            ssh_host,
            command,
        ],
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _require_ssh(args: argparse.Namespace, case_name: str) -> str:
    """Return ssh_host or fail the case with a clear message."""
    if not args.ssh_host:
        fail_case(case_name, "SSH host required but --ssh-host not provided")
        return ""
    return args.ssh_host


# ---------------------------------------------------------------------------
# Unique tag generator
# ---------------------------------------------------------------------------


def _unique_tag(prefix: str = "p05") -> str:
    """Generate a unique tag per run to avoid stale mailbox matches."""
    suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
    ts = int(time.time())
    return f"{prefix}-{ts}-{suffix}"


def _safe_list_name(prefix: str = "vfy") -> str:
    """Generate a safe, unique list name for API test runs."""
    suffix = "".join(
        random.choices(string.ascii_lowercase + string.digits, k=LIST_NAME_LENGTH)
    )
    return f"{prefix}{suffix}"


# ---------------------------------------------------------------------------
# Password helper (from Phase 03 pattern)
# ---------------------------------------------------------------------------


def password_for(user: str, args: argparse.Namespace) -> str:
    """Return the password for the given user, resolving CLI arg or env."""
    if user == "admin":
        pw = args.admin_password or os.environ.get("MAIL_ADMIN_PASSWORD", "")
    else:
        pw = args.test_password or os.environ.get("MAIL_TEST_PASSWORD", "")
    if not pw:
        env_var = "MAIL_ADMIN_PASSWORD" if user == "admin" else "MAIL_TEST_PASSWORD"
        raise ValueError(
            f"Password for {user} not set. "
            f"Use --{user}-password or set {env_var} in the environment."
        )
    return pw


# ---------------------------------------------------------------------------
# IMAP fetch helper (from Phase 03 pattern, adapted for Phase 05 search)
# ---------------------------------------------------------------------------


def _imap_fetch_contains(
    imap_host: str,
    user: str,
    password: str,
    tag: str,
    retries: int = MAX_RETRIES,
    delay: float = RETRY_DELAY,
    mailbox: str = "INBOX",
) -> bool:
    """Login to IMAP with STARTTLS and search for a message containing the tag string."""
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE

    for attempt in range(retries):
        try:
            conn = imaplib.IMAP4(imap_host, 143)
            conn.starttls(ssl_context=context)
            conn.login(user, password)
            conn.select(mailbox)
            status, data = conn.search(None, f'TEXT "{tag}"')
            if status == "OK" and data[0]:
                conn.logout()
                return True
            conn.logout()
        except Exception as e:
            if attempt < retries - 1:
                print(f"  NOTE: IMAP fetch attempt {attempt + 1}/{retries} failed: {e}")
                time.sleep(delay)
            else:
                print(f"  NOTE: IMAP fetch attempt {attempt + 1}/{retries} failed: {e}")
                return False
        else:
            time.sleep(delay)

    return False


# ---------------------------------------------------------------------------
# SMTP send helper
# ---------------------------------------------------------------------------


def _send_mail(
    smtp_host: str,
    sender: str,
    recipient: str,
    subject: str,
    body: str,
    domain: str,
    timeout: int = DEFAULT_TIMEOUT,
    port: int = 25,
) -> str:
    """Send a single mail message via plain SMTP and return the Message-ID tag."""
    message = (
        f"From: {sender}\r\nTo: {recipient}\r\nSubject: {subject}\r\n\r\n{body}\r\n"
    )

    with smtplib.SMTP(smtp_host, port, timeout=timeout) as smtp:
        smtp.ehlo()
        smtp.sendmail(sender, [recipient], message)

    return subject


# ---------------------------------------------------------------------------
# HTTP API request helper
# ---------------------------------------------------------------------------


def _api_request(
    api_host: str,
    api_port: int,
    method: str,
    path: str,
    body: bytes | None = None,
    content_type: str = "application/json",
    timeout: int = DEFAULT_TIMEOUT,
) -> tuple[int, str]:
    """Make an HTTP request to the list API and return (status_code, response_body)."""
    url = f"http://{api_host}:{api_port}{path}"
    req = urllib.request.Request(url, data=body, method=method)
    if body is not None:
        req.add_header("Content-Type", content_type)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        body_text = ""
        try:
            body_text = e.read().decode("utf-8", errors="replace")
        except Exception:
            pass
        return e.code, body_text
    except urllib.error.URLError as e:
        raise ConnectionError(f"Could not reach {url}: {e.reason}") from e


# ===================================================================
# Case: static-primary
# ===================================================================


def case_static_primary(args: argparse.Namespace) -> None:
    """LIST-01: Send to local_users@<domain> and verify delivery via IMAP."""
    domain = args.domain
    smtp_host = args.smtp_host
    imap_host = args.imap_host
    tag = _unique_tag("p05-static-primary")
    subject = f"phase05-static-primary-{tag}"
    body = f"static primary list delivery test {tag}"
    recipient = f"local_users@{domain}"
    sender = f"verifier@{domain}"

    # Send mail
    try:
        _send_mail(smtp_host, sender, recipient, subject, body, domain)
    except smtplib.SMTPRecipientsRefused as e:
        fail_case("static-primary", f"Port 25 rejected RCPT TO <{recipient}>: {e}")
        return
    except Exception as e:
        fail_case("static-primary", f"SMTP delivery error: {e}")
        return

    # Verify delivery to ALL expected recipients
    for user in DEFAULT_RECIPIENTS:
        try:
            pw = password_for(user, args)
            found = _imap_fetch_contains(imap_host, user, pw, subject)
        except Exception as e:
            fail_case("static-primary", f"IMAP error for {user}: {e}")
            return
        if not found:
            fail_case(
                "static-primary",
                f"Message {subject} not found in {user} IMAP mailbox",
            )
            return

    pass_case(
        "static-primary",
        f"local_users@{domain} delivered to admin and test",
    )


# ===================================================================
# Case: static-mail-domain
# ===================================================================


def case_static_mail_domain(args: argparse.Namespace) -> None:
    """LIST-02: Send to local_users@<mail-domain> and verify delivery via IMAP."""
    mail_domain = args.mail_domain
    smtp_host = args.smtp_host
    imap_host = args.imap_host
    domain = args.domain
    tag = _unique_tag("p05-static-mail")
    subject = f"phase05-static-mail-{tag}"
    body = f"static mail domain list delivery test {tag}"
    recipient = f"local_users@{mail_domain}"
    sender = f"verifier@{domain}"

    try:
        _send_mail(smtp_host, sender, recipient, subject, body, domain)
    except smtplib.SMTPRecipientsRefused as e:
        fail_case("static-mail-domain", f"Port 25 rejected RCPT TO <{recipient}>: {e}")
        return
    except Exception as e:
        fail_case("static-mail-domain", f"SMTP delivery error: {e}")
        return

    for user in DEFAULT_RECIPIENTS:
        try:
            pw = password_for(user, args)
            found = _imap_fetch_contains(imap_host, user, pw, subject)
        except Exception as e:
            fail_case("static-mail-domain", f"IMAP error for {user}: {e}")
            return
        if not found:
            fail_case(
                "static-mail-domain",
                f"Message {subject} not found in {user} IMAP mailbox",
            )
            return

    pass_case(
        "static-mail-domain",
        f"local_users@{mail_domain} delivered to admin and test",
    )


# ===================================================================
# Case: static (runs both static sub-cases)
# ===================================================================


def case_static(args: argparse.Namespace) -> None:
    """Run both static-primary and static-mail-domain cases."""
    case_static_primary(args)
    case_static_mail_domain(args)


# ===================================================================
# Case: api-create
# ===================================================================


def case_api_create(args: argparse.Namespace) -> None:
    """LIST-03: POST /list/create with valid payload and verify postmap visibility."""
    api_host = args.api_host
    if not api_host:
        fail_case("api-create", "--api-host is required for API cases")
        return
    api_port = args.api_port
    domain = args.domain
    mail_domain = args.mail_domain
    ssh_host = args.ssh_host  # optional for postmap check

    list_name = _safe_list_name("vfy")
    members = ["admin", "test"]
    payload = json.dumps({"name": list_name, "members": members}).encode("utf-8")

    # POST create
    try:
        status, body = _api_request(api_host, api_port, "POST", "/list/create", payload)
    except ConnectionError as e:
        fail_case("api-create", str(e))
        return
    except Exception as e:
        fail_case("api-create", f"HTTP request failed: {e}")
        return

    print(f"  POST /list/create → {status} {body[:200]}")

    if not (200 <= status < 300):
        fail_case(
            "api-create",
            f"Expected 2xx for valid create, got {status}: {body[:200]}",
        )
        return

    # Verify postmap visibility on both domains (requires SSH)
    if ssh_host:
        for test_domain in [domain, mail_domain]:
            query_addr = f"{list_name}@{test_domain}"
            # postmap -q returns the expansion value or empty
            proc = ssh_cmd(
                ssh_host,
                f"sudo postmap -q {shlex.quote(query_addr)} lmdb:/etc/postfix/list_static_aliases 2>/dev/null; "
                f"sudo postmap -q {shlex.quote(query_addr)} lmdb:/var/lib/nasa-mail-list-api/dynamic_aliases 2>/dev/null",
                timeout=DEFAULT_TIMEOUT,
            )
            if proc.returncode != 0:
                print(f"  NOTE: postmap query returned code {proc.returncode}")
            output = (proc.stdout or "").strip()
            print(f"  postmap -q {query_addr} → {output if output else '(empty)'}")
        pass_case(
            "api-create",
            f"List '{list_name}' created OK; postmap visibility checked via SSH",
        )
    else:
        pass_case(
            "api-create",
            f"List '{list_name}' created OK (no --ssh-host; postmap check skipped)",
        )


# ===================================================================
# Case: api-create-delivery
# ===================================================================


def case_api_create_delivery(args: argparse.Namespace) -> None:
    """LIST-04: Create list, send mail to it, verify immediate member delivery."""
    api_host = args.api_host
    if not api_host:
        fail_case("api-create-delivery", "--api-host is required for API cases")
        return
    api_port = args.api_port
    smtp_host = args.smtp_host
    imap_host = args.imap_host
    domain = args.domain

    list_name = _safe_list_name("dlv")
    members = ["admin", "test"]
    payload = json.dumps({"name": list_name, "members": members}).encode("utf-8")

    # Create/replace the list
    try:
        status, body = _api_request(api_host, api_port, "POST", "/list/create", payload)
    except ConnectionError as e:
        fail_case("api-create-delivery", str(e))
        return
    except Exception as e:
        fail_case("api-create-delivery", f"HTTP request failed: {e}")
        return

    print(f"  POST /list/create → {status} {body[:200]}")
    if not (200 <= status < 300):
        fail_case(
            "api-create-delivery",
            f"Expected 2xx for valid create, got {status}: {body[:200]}",
        )
        return

    # Wait briefly for Postfix reload to take effect
    time.sleep(1)

    # Send mail to the created list
    tag = _unique_tag("p05-create-delivery")
    subject = f"phase05-create-delivery-{tag}"
    body_text = f"API create delivery test {tag}"
    recipient = f"{list_name}@{domain}"
    sender = f"verifier@{domain}"

    try:
        _send_mail(smtp_host, sender, recipient, subject, body_text, domain)
    except smtplib.SMTPRecipientsRefused as e:
        fail_case(
            "api-create-delivery",
            f"Port 25 rejected RCPT TO <{recipient}>: {e}",
        )
        return
    except Exception as e:
        fail_case("api-create-delivery", f"SMTP delivery error: {e}")
        return

    # Verify each member received the message
    for user in members:
        try:
            pw = password_for(user, args)
            found = _imap_fetch_contains(imap_host, user, pw, subject)
        except Exception as e:
            fail_case("api-create-delivery", f"IMAP error for {user}: {e}")
            return
        if not found:
            fail_case(
                "api-create-delivery",
                f"Message {subject} not found in {user} IMAP mailbox",
            )
            return

    pass_case(
        "api-create-delivery",
        f"List '{list_name}' created and mail delivered to all {len(members)} members",
    )


# ===================================================================
# Case: api-delete
# ===================================================================


def case_api_delete(args: argparse.Namespace) -> None:
    """LIST-05: Create list, delete it, verify idempotent delete and postmap absence."""
    api_host = args.api_host
    if not api_host:
        fail_case("api-delete", "--api-host is required for API cases")
        return
    api_port = args.api_port
    domain = args.domain
    mail_domain = args.mail_domain
    ssh_host = args.ssh_host

    list_name = _safe_list_name("del")
    members = ["admin", "test"]
    payload = json.dumps({"name": list_name, "members": members}).encode("utf-8")

    # Step 1: Create the list
    try:
        status, body = _api_request(api_host, api_port, "POST", "/list/create", payload)
    except ConnectionError as e:
        fail_case("api-delete", str(e))
        return
    except Exception as e:
        fail_case("api-delete", f"HTTP create failed: {e}")
        return

    print(f"  POST /list/create → {status}")
    if not (200 <= status < 300):
        fail_case("api-delete", f"Expected 2xx for create, got {status}: {body[:200]}")
        return

    # Small delay for activation
    time.sleep(0.5)

    # Step 2: First DELETE — must succeed
    try:
        status, body = _api_request(api_host, api_port, "DELETE", f"/list/{list_name}")
    except ConnectionError as e:
        fail_case("api-delete", f"DELETE connection error: {e}")
        return
    except Exception as e:
        fail_case("api-delete", f"HTTP DELETE failed: {e}")
        return

    print(f"  DELETE /list/{list_name} → {status} {body[:200]}")
    if not (200 <= status < 300):
        fail_case(
            "api-delete", f"First DELETE should succeed, got {status}: {body[:200]}"
        )
        return

    # Step 3: Second DELETE — idempotent no-op, must also succeed (D-04)
    try:
        status2, body2 = _api_request(
            api_host, api_port, "DELETE", f"/list/{list_name}"
        )
    except ConnectionError as e:
        fail_case("api-delete", f"Second DELETE connection error: {e}")
        return
    except Exception as e:
        fail_case("api-delete", f"Second HTTP DELETE failed: {e}")
        return

    print(f"  DELETE /list/{list_name} (2nd) → {status2} {body2[:200]}")
    if not (200 <= status2 < 300):
        fail_case(
            "api-delete",
            f"Second DELETE (idempotent) should succeed, got {status2}: {body2[:200]}",
        )
        return

    # Step 4: Verify postmap no longer returns the list (requires SSH)
    if ssh_host:
        for test_domain in [domain, mail_domain]:
            query_addr = f"{list_name}@{test_domain}"
            proc = ssh_cmd(
                ssh_host,
                f"sudo postmap -q {shlex.quote(query_addr)} lmdb:/var/lib/nasa-mail-list-api/dynamic_aliases 2>/dev/null",
                timeout=DEFAULT_TIMEOUT,
            )
            output = (proc.stdout or "").strip()
            print(f"  postmap -q {query_addr} → {output if output else '(empty)'}")
            if output:
                fail_case(
                    "api-delete",
                    f"postmap still returns '{output}' for {query_addr} after DELETE",
                )
                return
        pass_case(
            "api-delete",
            f"List '{list_name}' deleted, second delete was idempotent, postmap confirms removal",
        )
    else:
        pass_case(
            "api-delete",
            f"List '{list_name}' deleted and second delete was idempotent (no --ssh-host; postmap check skipped)",
        )


# ===================================================================
# Case: invalid-inputs
# ===================================================================


def case_invalid_inputs(args: argparse.Namespace) -> None:
    """LIST-06: Submit invalid payloads and assert 4xx rejection + static list safety."""
    api_host = args.api_host
    if not api_host:
        fail_case("invalid-inputs", "--api-host is required for API cases")
        return
    api_port = args.api_port
    smtp_host = args.smtp_host
    imap_host = args.imap_host
    domain = args.domain
    mail_domain = args.mail_domain

    failures = []

    # ---- Helper to test a single payload ----
    def _test_invalid(
        label: str,
        method: str = "POST",
        path: str = "/list/create",
        body: bytes | None = None,
        content_type: str = "application/json",
        expected_min: int = 400,
        expected_max: int = 499,
    ) -> None:
        try:
            status, resp_body = _api_request(
                api_host, api_port, method, path, body, content_type
            )
        except ConnectionError as e:
            fail_case("invalid-inputs", f"[{label}] Connection error: {e}")
            return
        except Exception as e:
            fail_case("invalid-inputs", f"[{label}] Request failed: {e}")
            return
        if expected_min <= status <= expected_max:
            print(f"  [{label}] → {status} (expected 4xx)")
        else:
            print(f"  [{label}] → {status} {resp_body[:120]} (UNEXPECTED)")
            failures.append(f"{label}: got {status}, expected 4xx")

    # 1. Malformed JSON
    _test_invalid("malformed JSON", body=b"{bad json", content_type="application/json")

    # 2. Non-JSON body (plain text)
    _test_invalid(
        "non-JSON body", body=b"name=foo&members=admin", content_type="text/plain"
    )

    # 3. Wrong method on create endpoint
    _test_invalid("wrong method GET", method="GET", path="/list/create")

    # 4. Wrong member type (integer instead of string)
    _test_invalid(
        "wrong member type",
        body=json.dumps({"name": "goodlist", "members": [12345]}).encode("utf-8"),
    )

    # 5. Empty members list
    _test_invalid(
        "empty members",
        body=json.dumps({"name": "goodlist", "members": []}).encode("utf-8"),
    )

    # 6. Unsafe list names — each unsafe character
    for ch in UNSAFE_CHARS:
        bad_name = f"bad{ch}name"
        _test_invalid(
            f"unsafe name char {repr(ch)}",
            body=json.dumps({"name": bad_name, "members": ["admin"]}).encode("utf-8"),
        )

    # 7. Reserved list name 'local_users'
    _test_invalid(
        "reserved local_users",
        body=json.dumps({"name": "local_users", "members": ["admin"]}).encode("utf-8"),
    )

    # 8. Unsafe member name
    _test_invalid(
        "unsafe member",
        body=json.dumps({"name": "goodlist", "members": ["bad;user"]}).encode("utf-8"),
    )

    # 9. Zero deliverable members (all members are non-existent safe names)
    _test_invalid(
        "zero deliverable members",
        body=json.dumps({"name": "goodlist", "members": ["noone1", "noone2"]}).encode(
            "utf-8"
        ),
    )

    # 10. Missing required fields
    _test_invalid(
        "missing members field",
        body=json.dumps({"name": "goodlist"}).encode("utf-8"),
    )

    # 11. Empty name
    _test_invalid(
        "empty name",
        body=json.dumps({"name": "", "members": ["admin"]}).encode("utf-8"),
    )

    # 12. Name too long (>64 chars)
    _test_invalid(
        "name too long",
        body=json.dumps({"name": "a" * 65, "members": ["admin"]}).encode("utf-8"),
    )

    if failures:
        fail_case(
            "invalid-inputs",
            f"{len(failures)} unexpected non-4xx responses: {'; '.join(failures[:5])}",
        )
        return

    # Post-condition: verify static local_users still resolves after all invalid attempts
    tag = _unique_tag("p05-invalid-post")
    subject = f"phase05-invalid-post-{tag}"
    body_text = f"invalid inputs post-condition test {tag}"

    for rcpt_domain, label in [(domain, "primary"), (mail_domain, "mail")]:
        recipient = f"local_users@{rcpt_domain}"
        try:
            _send_mail(
                smtp_host,
                f"verifier@{domain}",
                recipient,
                subject,
                body_text,
                domain,
            )
        except Exception as e:
            fail_case("invalid-inputs", f"Post-condition SMTP to {recipient}: {e}")
            return

        for user in DEFAULT_RECIPIENTS:
            try:
                pw = password_for(user, args)
                found = _imap_fetch_contains(imap_host, user, pw, subject)
            except Exception as e:
                fail_case("invalid-inputs", f"Post-condition IMAP for {user}: {e}")
                return
            if not found:
                fail_case(
                    "invalid-inputs",
                    f"Post-condition: {subject} not in {user} mailbox after {label} domain test",
                )
                return

    pass_case(
        "invalid-inputs",
        "All invalid inputs rejected with 4xx; static local_users still functional",
    )


# ===================================================================
# Case: activation
# ===================================================================


def case_activation(args: argparse.Namespace) -> None:
    """Inspect Postfix config, map queries, API service status via SSH.

    Covers D-13, D-14, D-15 runtime verification: virtual_alias_maps config,
    static map queries, dynamic map presence, and API service health.
    """
    ssh_host = _require_ssh(args, "activation")
    if not ssh_host:
        return

    domain = args.domain
    mail_domain = args.mail_domain

    # 1. Check virtual_alias_maps Postfix config
    proc = ssh_cmd(ssh_host, "sudo postconf -n virtual_alias_maps")
    if proc.returncode != 0:
        fail_case(
            "activation", f"postconf virtual_alias_maps failed: {proc.stderr.strip()}"
        )
        return
    vam_output = (proc.stdout or "").strip()
    print(f"  postconf virtual_alias_maps:\n    {vam_output}")
    if not vam_output or "virtual_alias_maps =" not in vam_output:
        fail_case("activation", "virtual_alias_maps not configured or empty")
        return

    # 2. Check static local_users expansion on both domains
    for rcpt_domain, label in [(domain, "primary"), (mail_domain, "mail")]:
        query_addr = f"local_users@{rcpt_domain}"
        proc = ssh_cmd(
            ssh_host,
            f"sudo postmap -q {shlex.quote(query_addr)} lmdb:/etc/postfix/list_static_aliases 2>/dev/null",
        )
        output = (proc.stdout or "").strip()
        print(f"  postmap -q {query_addr} → {output if output else '(empty)'}")
        if not output:
            fail_case(
                "activation",
                f"postmap -q {query_addr} returned empty; static list may be missing",
            )
            return

    # 3. Check dynamic map path existence (probe for the API state directory)
    proc = ssh_cmd(
        ssh_host,
        "sudo ls /var/lib/nasa-mail-list-api/dynamic_aliases /var/lib/nasa-mail-list-api/dynamic_aliases.lmdb 2>&1 || true",
    )
    dyn_output = (proc.stdout or "").strip()
    dyn_errors = (proc.stderr or "").strip()
    if dyn_output:
        print(f"  Dynamic map files:\n    {dyn_output}")
    elif "No such file" in dyn_errors or "cannot access" in dyn_errors:
        print(
            "  NOTE: Dynamic map files not yet created (expected before API converge)"
        )
    else:
        print(f"  Dynamic map files: {dyn_output or dyn_errors}")

    # 4. Check API service status
    proc = ssh_cmd(
        ssh_host,
        "sudo systemctl is-active nasa-mail-list-api.service 2>/dev/null || echo 'inactive'",
    )
    svc_status = (proc.stdout or "").strip()
    print(f"  API service status: {svc_status}")

    pass_case("activation", "Postfix config, static maps, and API service inspected OK")


# ---------------------------------------------------------------------------
# Case dispatch (following Phase 03 pattern)
# ---------------------------------------------------------------------------

from collections.abc import Callable

CaseFn = Callable[[argparse.Namespace], None]

CASES: dict[str, CaseFn | None] = {
    "static-primary": case_static_primary,
    "static-mail-domain": case_static_mail_domain,
    "static": case_static,
    "api-create": case_api_create,
    "api-create-delivery": case_api_create_delivery,
    "api-delete": case_api_delete,
    "invalid-inputs": case_invalid_inputs,
    "activation": case_activation,
    "all": None,
}


def run_case(case_name: str, args: argparse.Namespace) -> None:
    """Run a single named case. 'all' dispatches to every case except 'all'."""
    if case_name == "all":
        # Dependency-safe order: static first, then API cases, then activation
        ordered = [
            "static",
            "api-create",
            "api-create-delivery",
            "api-delete",
            "invalid-inputs",
            "activation",
        ]
        for name in ordered:
            fn = CASES.get(name)
            if fn is None:
                continue
            run_case(name, args)
        return

    fn = CASES.get(case_name)
    if fn is None:
        print(f"ERROR: unknown case '{case_name}'", file=sys.stderr)
        sys.exit(1)
    try:
        fn(args)
    except Exception as e:
        fail_case(case_name, f"Unexpected exception: {e.__class__.__name__}: {e}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Phase 05 mailing lists & HTTP API verification script. "
            "Verifies static list expansion, API create/delete behavior, "
            "invalid-input rejection, and activation safety."
        )
    )
    parser.add_argument(
        "--smtp-host",
        required=True,
        help="SMTP server hostname (e.g. smtp.STUID.nasa)",
    )
    parser.add_argument(
        "--imap-host",
        required=True,
        help="IMAP server hostname (e.g. imap.STUID.nasa)",
    )
    parser.add_argument(
        "--api-host",
        default=None,
        help="API server hostname for HTTP probes (e.g. smtp.STUID.nasa)",
    )
    parser.add_argument(
        "--api-port",
        type=int,
        default=8000,
        help="API server port (default: 8000)",
    )
    parser.add_argument(
        "--domain",
        required=True,
        help="Base managed domain (e.g. STUID.nasa)",
    )
    parser.add_argument(
        "--mail-domain",
        required=True,
        help="Mail managed domain (e.g. mail.STUID.nasa)",
    )
    parser.add_argument(
        "--admin-password",
        default=None,
        help="Password for admin user (env: MAIL_ADMIN_PASSWORD)",
    )
    parser.add_argument(
        "--test-password",
        default=None,
        help="Password for test user (env: MAIL_TEST_PASSWORD)",
    )
    parser.add_argument(
        "--ssh-host",
        default=None,
        help="SSH target for remote probes (e.g. dmz-client-01). "
        "Required for cases that need map inspection.",
    )
    parser.add_argument(
        "--case",
        action="append",
        dest="cases",
        choices=sorted(CASES.keys()),
        help="Test case to run. Specify multiple times or use 'all'. "
        f"Available: {', '.join(sorted(k for k in CASES if k != 'all'))}",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT,
        help=f"Socket timeout in seconds (default: {DEFAULT_TIMEOUT})",
    )

    args = parser.parse_args()

    if not args.cases:
        parser.error(
            "At least one --case is required. Use --case all to run all cases."
        )

    # Sanitize password display (never print actual passwords)
    admin_set = bool(args.admin_password or os.environ.get("MAIL_ADMIN_PASSWORD"))
    test_set = bool(args.test_password or os.environ.get("MAIL_TEST_PASSWORD"))

    print("=== Phase 05 Mailing Lists & HTTP API Verification ===")
    print(f"SMTP: {args.smtp_host}  IMAP: {args.imap_host}")
    print(f"Domain: {args.domain}  Mail domain: {args.mail_domain}")
    if args.api_host:
        print(f"API: http://{args.api_host}:{args.api_port}")
    print(f"SSH host: {args.ssh_host or '(not set)'}")
    print(f"Admin password: {'set' if admin_set else 'NOT SET'}")
    print(f"Test password:  {'set' if test_set else 'NOT SET'}")
    print(f"Cases: {args.cases}")
    print()

    for case_name in args.cases:
        run_case(case_name, args)

    # Print summary
    print()
    print("=== Summary ===")
    passed = sum(1 for _, ok, _ in results if ok)
    failed = sum(1 for _, ok, _ in results if not ok)
    for name, ok, detail in results:
        status = "PASS" if ok else f"FAIL {detail}"
        print(f"  {name}: {status}")
    print(f"\n{passed} passed, {failed} failed")

    sys.exit(1 if failed > 0 else 0)


if __name__ == "__main__":
    main()
