#!/usr/bin/env python3
"""Phase 07 LDAP integration verification script.

Tests LDAP-disabled regression (zero LDAP footprint), LDAP-enabled SMTP auth,
sender ownership restrictions, IMAP delivery, list membership, and explicit
enablement flag behavior.

Uses only Python standard library modules (smtplib, imaplib, subprocess,
urllib, ssl, argparse, re, email) — no swaks, nmap, or requests required.

Environment variable fallbacks:
  MAIL_ADMIN_PASSWORD  — fallback for --admin-password
  MAIL_TEST_PASSWORD   — fallback for --test-password
  LDAP_TEST_PASSWORD   — fallback for --ldap-password
"""

from __future__ import annotations

import argparse
import imaplib
import json
import os
import random
import smtplib
import ssl
import string
import subprocess
import sys
import time
import urllib.error
import urllib.request
from email import policy
from email.parser import BytesParser

# ---------------------------------------------------------------------------
# Result helpers
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
# SSH helpers
# ---------------------------------------------------------------------------


def ssh_cmd(
    ssh_host: str,
    command: str,
    timeout: int = 15,
    port: int | None = None,
    proxy_jump: str | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run a command on the target host via SSH."""
    cmd = [
        "ssh",
        "-o",
        "StrictHostKeyChecking=no",
        "-o",
        "ConnectTimeout=5",
        "-o",
        "BatchMode=yes",
    ]
    if port is not None:
        cmd.extend(["-p", str(port)])
    if proxy_jump:
        cmd.extend(["-J", proxy_jump])
    cmd.extend([ssh_host, command])
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


# ---------------------------------------------------------------------------
# IMAP fetch helper (raw message)
# ---------------------------------------------------------------------------


def _imap_fetch_raw(
    imap_host: str,
    user: str,
    password: str,
    tag: str,
    retries: int = 5,
    delay: float = 2.0,
) -> tuple[bool, bytes | None]:
    """Login to IMAP with STARTTLS and fetch the raw message bytes containing tag."""
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE

    for attempt in range(retries):
        try:
            conn = imaplib.IMAP4(imap_host, 143)
            conn.starttls(ssl_context=context)
            conn.login(user, password)
            conn.select("INBOX")
            status, data = conn.search(None, f'TEXT "{tag}"')
            if status == "OK" and data[0]:
                msg_ids = data[0].split()
                if msg_ids:
                    fetch_status, fetch_data = conn.fetch(msg_ids[-1], "(RFC822)")
                    if fetch_status == "OK" and fetch_data[0]:
                        raw = fetch_data[0][1]
                        if isinstance(raw, bytes):
                            conn.logout()
                            return True, raw
                        elif isinstance(raw, str):
                            conn.logout()
                            return True, raw.encode("utf-8", errors="replace")
            conn.logout()
        except Exception as e:
            if attempt < retries - 1:
                print(f"  NOTE: IMAP fetch attempt {attempt + 1}/{retries} failed: {e}")
            else:
                return False, None

        if attempt < retries - 1:
            backoff = delay * (2**attempt)
            print(
                f"  NOTE: IMAP fetch attempt {attempt + 1}/{retries}: "
                f"message not yet delivered; retrying in {backoff:.0f}s"
            )
            time.sleep(backoff)

    return False, None


# ---------------------------------------------------------------------------
# Unique tag generator
# ---------------------------------------------------------------------------


def _unique_tag(prefix: str = "p07") -> str:
    suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
    ts = int(time.time())
    return f"{prefix}-{ts}-{suffix}"


# ---------------------------------------------------------------------------
# Domain derivation
# ---------------------------------------------------------------------------


def _derive_domain(
    ssh_host: str,
    timeout: int = 15,
    port: int | None = None,
    proxy_jump: str | None = None,
) -> str:
    """SSH to target and run hostname -d to get the managed domain."""
    proc = ssh_cmd(
        ssh_host, "hostname -d", timeout=timeout, port=port, proxy_jump=proxy_jump
    )
    if proc.returncode != 0:
        raise RuntimeError(f"Failed to derive domain via SSH: {proc.stderr.strip()}")
    domain = (proc.stdout or "").strip()
    if not domain:
        raise RuntimeError("SSH hostname -d returned empty domain")
    return domain


def _resolve_service_host(
    service_host_override: str | None, domain: str, prefix: str
) -> str:
    """Return the override if set, otherwise derive from domain."""
    if service_host_override:
        return service_host_override
    return f"{prefix}.{domain}"


# ---------------------------------------------------------------------------
# Password helpers
# ---------------------------------------------------------------------------


def _admin_password(args: argparse.Namespace) -> str:
    pw = args.admin_password or os.environ.get("MAIL_ADMIN_PASSWORD", "")
    if not pw:
        raise ValueError(
            "Admin password not set. Use --admin-password or MAIL_ADMIN_PASSWORD env var."
        )
    return pw


def _test_password(args: argparse.Namespace) -> str:
    pw = args.test_password or os.environ.get("MAIL_TEST_PASSWORD", "")
    if not pw:
        raise ValueError(
            "Test password not set. Use --test-password or MAIL_TEST_PASSWORD env var."
        )
    return pw


def _ldap_password(args: argparse.Namespace) -> str:
    pw = args.ldap_password or os.environ.get("LDAP_TEST_PASSWORD", "")
    if not pw:
        raise ValueError(
            "LDAP password not set. Use --ldap-password or LDAP_TEST_PASSWORD env var."
        )
    return pw


# ---------------------------------------------------------------------------
# SMTP authenticated send helper (port 587, STARTTLS)
# ---------------------------------------------------------------------------


def _smtp_auth_send(
    smtp_host: str,
    user: str,
    password: str,
    sender: str,
    recipient: str,
    subject: str,
    body: str,
    timeout: int = 15,
) -> None:
    """Authenticate to SMTP on port 587 with STARTTLS and send a message."""

    message = (
        f"From: {sender}\r\nTo: {recipient}\r\nSubject: {subject}\r\n\r\n{body}\r\n"
    )

    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE

    with smtplib.SMTP(smtp_host, 587, timeout=timeout) as smtp:
        smtp.ehlo()
        smtp.starttls(context=context)
        smtp.ehlo()
        smtp.login(user, password)
        smtp.sendmail(sender, [recipient], message)


def _smtp_auth_send_expect_reject(
    smtp_host: str,
    user: str,
    password: str,
    sender: str,
    recipient: str,
    subject: str,
    body: str,
    timeout: int = 15,
) -> tuple[bool, str]:
    """Attempt authenticated SMTP send and return whether it was rejected.

    Returns (was_rejected, reason_string).
    """
    message = (
        f"From: {sender}\r\nTo: {recipient}\r\nSubject: {subject}\r\n\r\n{body}\r\n"
    )

    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE

    try:
        with smtplib.SMTP(smtp_host, 587, timeout=timeout) as smtp:
            smtp.ehlo()
            smtp.starttls(context=context)
            smtp.ehlo()
            smtp.login(user, password)
            try:
                smtp.sendmail(sender, [recipient], message)
                return False, "message accepted (expected rejection)"
            except smtplib.SMTPDataError as e:
                return (
                    True,
                    f"SMTP {e.smtp_code}: {e.smtp_error.decode() if isinstance(e.smtp_error, bytes) else e.smtp_error}",
                )
            except smtplib.SMTPRecipientsRefused as e:
                return True, f"recipient refused: {e}"
            except smtplib.SMTPSenderRefused as e:
                return True, f"sender refused: {e}"
    except smtplib.SMTPAuthenticationError as e:
        raise  # Auth failure is a test error, not expected rejection
    except Exception as e:
        raise


# ---------------------------------------------------------------------------
# HTTP API request helper
# ---------------------------------------------------------------------------


def _api_request(
    api_host: str,
    api_port: int,
    method: str,
    path: str,
    body: bytes | None = None,
    timeout: int = 15,
) -> tuple[int, str]:
    """Make an HTTP request to the list API and return (status_code, response_body)."""
    url = f"http://{api_host}:{api_port}{path}"
    req = urllib.request.Request(url, data=body, method=method)
    if body is not None:
        req.add_header("Content-Type", "application/json")
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
# Case: ldap-flag-check (LDAP-05)
# ===================================================================


def case_ldap_flag_check(args: argparse.Namespace) -> None:
    """Verify explicit enablement: when mail_ldap_enabled=false, zero LDAP footprint.

    Checks: no dovecot-ldap package installed, no dovecot-ldap.conf.ext config,
    no LDAP users in valid_users.txt.
    """
    host = args.host

    # 1. Check dovecot-ldap package is NOT installed
    proc = ssh_cmd(
        host,
        "rpm -q dovecot-ldap 2>&1; echo RPM_EXIT:$?",
        timeout=args.timeout,
        port=args.port,
        proxy_jump=args.proxy_jump,
    )
    rpm_output = (proc.stdout or "").strip()
    print(f"  rpm -q dovecot-ldap: {rpm_output}")
    if (
        "is not installed" not in rpm_output
        and "package dovecot-ldap is not installed" not in rpm_output
    ):
        if "RPM_EXIT:0" in rpm_output or "dovecot-ldap-" in rpm_output:
            fail_case(
                "ldap-flag-check",
                f"dovecot-ldap package is installed: {rpm_output}",
            )
            return

    # 2. Check openldap-clients package is NOT installed (further proof)
    proc2 = ssh_cmd(
        host,
        "rpm -q openldap-clients 2>&1; echo RPM_EXIT:$?",
        timeout=args.timeout,
        port=args.port,
        proxy_jump=args.proxy_jump,
    )
    rpm2_output = (proc2.stdout or "").strip()
    print(f"  rpm -q openldap-clients: {rpm2_output}")
    if "RPM_EXIT:0" in rpm2_output or "openldap-clients-" in rpm2_output:
        fail_case(
            "ldap-flag-check",
            f"openldap-clients package is installed: {rpm2_output}",
        )
        return

    # 3. Check dovecot-ldap.conf.ext does NOT exist
    proc3 = ssh_cmd(
        host,
        "stat /etc/dovecot/dovecot-ldap.conf.ext 2>&1; echo STAT_EXIT:$?",
        timeout=args.timeout,
        port=args.port,
        proxy_jump=args.proxy_jump,
    )
    stat_output = (proc3.stdout or "").strip()
    print(f"  stat dovecot-ldap.conf.ext: {stat_output[:120]}")
    if "STAT_EXIT:0" in stat_output:
        fail_case("ldap-flag-check", "dovecot-ldap.conf.ext exists (should not)")
        return

    # 4. Check valid_users.txt has no LDAP users (mailta, generalta)
    proc4 = ssh_cmd(
        host,
        "grep -E '^(mailta|generalta)$' /etc/postfix/valid_users.txt 2>/dev/null || true",
        timeout=args.timeout,
        port=args.port,
        proxy_jump=args.proxy_jump,
    )
    vu_output = (proc4.stdout or "").strip()
    print(
        f"  grep LDAP users in valid_users.txt: {vu_output if vu_output else '(none)'}"
    )
    if vu_output:
        fail_case(
            "ldap-flag-check",
            f"LDAP users found in valid_users.txt: {vu_output}",
        )
        return

    pass_case("ldap-flag-check", "Zero LDAP footprint confirmed (explicit enablement)")


# ===================================================================
# Case: ldap-disabled-regression (D-09, D-12)
# ===================================================================


def case_ldap_disabled_regression(args: argparse.Namespace) -> None:
    """Verify LDAP-disabled mode produces identical behavior to Phase 06.

    Checks: no LDAP config, no LDAP passdb in 10-auth.conf, no LDAP users in
    valid_users.txt, and local admin/test SMTP auth still works.
    """
    host = args.host

    # Derive domain and SMTP/IMAP hosts
    try:
        domain = _derive_domain(
            host, timeout=args.timeout, port=args.port, proxy_jump=args.proxy_jump
        )
        print(f"  Derived domain: {domain}")
    except Exception as e:
        fail_case("ldap-disabled-regression", f"Domain derivation failed: {e}")
        return

    smtp_host = _resolve_service_host(args.service_host, domain, "smtp")
    imap_host = _resolve_service_host(args.service_host, domain, "imap")

    # 1. dovecot-ldap.conf.ext must NOT exist
    proc = ssh_cmd(
        host,
        "stat /etc/dovecot/dovecot-ldap.conf.ext 2>&1; echo EXIT:$?",
        timeout=args.timeout,
        port=args.port,
        proxy_jump=args.proxy_jump,
    )
    stat_out = (proc.stdout or "").strip()
    if "EXIT:0" in stat_out:
        fail_case(
            "ldap-disabled-regression",
            "dovecot-ldap.conf.ext exists (zero-footprint violated)",
        )
        return
    print(f"  dovecot-ldap.conf.ext: absent (OK)")

    # 2. 10-auth.conf must NOT contain LDAP passdb block
    proc2 = ssh_cmd(
        host,
        "grep -c 'driver = ldap' /etc/dovecot/conf.d/10-auth.conf 2>/dev/null || echo 0",
        timeout=args.timeout,
        port=args.port,
        proxy_jump=args.proxy_jump,
    )
    ldap_count_str = (proc2.stdout or "0").strip()
    try:
        ldap_count = int(ldap_count_str)
    except ValueError:
        ldap_count = 0
    print(f"  LDAP passdb blocks in 10-auth.conf: {ldap_count}")
    if ldap_count > 0:
        fail_case(
            "ldap-disabled-regression",
            f"LDAP passdb found in 10-auth.conf ({ldap_count} blocks)",
        )
        return

    # 3. valid_users.txt must NOT contain LDAP users
    proc3 = ssh_cmd(
        host,
        "grep -cE '^(mailta|generalta)$' /etc/postfix/valid_users.txt 2>/dev/null || echo 0",
        timeout=args.timeout,
        port=args.port,
        proxy_jump=args.proxy_jump,
    )
    ldap_vu_str = (proc3.stdout or "0").strip()
    try:
        ldap_vu_count = int(ldap_vu_str)
    except ValueError:
        ldap_vu_count = 0
    print(f"  LDAP users in valid_users.txt: {ldap_vu_count}")
    if ldap_vu_count > 0:
        fail_case(
            "ldap-disabled-regression",
            f"LDAP users found in valid_users.txt ({ldap_vu_count} entries)",
        )
        return

    # 4. Admin user SMTP auth must still work
    try:
        admin_pw = _admin_password(args)
    except ValueError as e:
        fail_case("ldap-disabled-regression", f"Admin password: {e}")
        return

    tag_admin = _unique_tag("p07-reg-admin")
    try:
        _smtp_auth_send(
            smtp_host,
            "admin",
            admin_pw,
            f"admin@{domain}",
            f"admin@{domain}",
            f"phase07 regression admin auth {tag_admin}",
            f"regression test admin {tag_admin}",
            timeout=args.timeout,
        )
        print(f"  Admin SMTP auth: OK")
    except smtplib.SMTPAuthenticationError as e:
        fail_case(
            "ldap-disabled-regression",
            f"Admin SMTP auth failed (regression): {e}",
        )
        return
    except Exception as e:
        fail_case(
            "ldap-disabled-regression",
            f"Admin SMTP send failed: {e}",
        )
        return

    # 5. Test user SMTP auth must still work
    try:
        test_pw = _test_password(args)
    except ValueError as e:
        fail_case("ldap-disabled-regression", f"Test password: {e}")
        return

    tag_test = _unique_tag("p07-reg-test")
    try:
        _smtp_auth_send(
            smtp_host,
            "test",
            test_pw,
            f"test@{domain}",
            f"test@{domain}",
            f"phase07 regression test auth {tag_test}",
            f"regression test body {tag_test}",
            timeout=args.timeout,
        )
        print(f"  Test SMTP auth: OK")
    except smtplib.SMTPAuthenticationError as e:
        fail_case(
            "ldap-disabled-regression",
            f"Test SMTP auth failed (regression): {e}",
        )
        return
    except Exception as e:
        fail_case(
            "ldap-disabled-regression",
            f"Test SMTP send failed: {e}",
        )
        return

    # 6. Verify admin received own message via IMAP
    found, raw = _imap_fetch_raw(imap_host, "admin", admin_pw, tag_admin)
    if not found:
        fail_case(
            "ldap-disabled-regression",
            f"Admin IMAP: message {tag_admin} not delivered",
        )
        return
    print(f"  Admin IMAP delivery: OK")

    # 7. Verify test received own message via IMAP
    found2, raw2 = _imap_fetch_raw(imap_host, "test", test_pw, tag_test)
    if not found2:
        fail_case(
            "ldap-disabled-regression",
            f"Test IMAP: message {tag_test} not delivered",
        )
        return
    print(f"  Test IMAP delivery: OK")

    pass_case(
        "ldap-disabled-regression",
        "LDAP-disabled mode: zero LDAP footprint, local admin/test auth intact",
    )


# ===================================================================
# Case: ldap-smtp-auth (LDAP-01)
# ===================================================================


def case_ldap_smtp_auth(args: argparse.Namespace) -> None:
    """LDAP-01: LDAP ta user can authenticate to SMTP via LDAPS.

    Connects to SMTP submission (port 587) with STARTTLS, authenticates as
    mailta with LDAP password, and sends a test message.
    """
    host = args.host

    try:
        domain = _derive_domain(
            host, timeout=args.timeout, port=args.port, proxy_jump=args.proxy_jump
        )
    except Exception as e:
        fail_case("ldap-smtp-auth", f"Domain derivation failed: {e}")
        return

    smtp_host = _resolve_service_host(args.service_host, domain, "smtp")
    ldap_user = args.ldap_user

    try:
        ldap_pw = _ldap_password(args)
    except ValueError as e:
        fail_case("ldap-smtp-auth", f"LDAP password: {e}")
        return

    tag = _unique_tag("p07-auth")
    subject = f"phase07 LDAP auth test {tag}"
    body = f"LDAP SMTP auth verification {tag}"
    sender = f"{ldap_user}@{domain}"
    recipient = sender

    # Attempt SMTP auth as LDAP user
    try:
        _smtp_auth_send(
            smtp_host,
            ldap_user,
            ldap_pw,
            sender,
            recipient,
            subject,
            body,
            timeout=args.timeout,
        )
        print(f"  LDAP SMTP auth ({ldap_user}): OK")
    except smtplib.SMTPAuthenticationError as e:
        fail_case(
            "ldap-smtp-auth",
            f"LDAP user {ldap_user} SMTP auth failed (LDAPS may be unreachable): {e}",
        )
        return
    except Exception as e:
        fail_case("ldap-smtp-auth", f"LDAP SMTP send failed: {e}")
        return

    pass_case(
        "ldap-smtp-auth", f"LDAP user {ldap_user} authenticated to SMTP via LDAPS"
    )


# ===================================================================
# Case: ldap-sender-restrict (LDAP-02)
# ===================================================================


def case_ldap_sender_restrict(args: argparse.Namespace) -> None:
    """LDAP-02: LDAP ta user can send only as own address.

    Authenticate as mailta, attempt to send as mailta@domain (should succeed),
    then attempt to send as admin@domain (should fail with 550/553).
    """
    host = args.host

    try:
        domain = _derive_domain(
            host, timeout=args.timeout, port=args.port, proxy_jump=args.proxy_jump
        )
    except Exception as e:
        fail_case("ldap-sender-restrict", f"Domain derivation failed: {e}")
        return

    smtp_host = _resolve_service_host(args.service_host, domain, "smtp")
    ldap_user = args.ldap_user

    try:
        ldap_pw = _ldap_password(args)
    except ValueError as e:
        fail_case("ldap-sender-restrict", f"LDAP password: {e}")
        return

    # Test 1: Send as own address — must succeed
    tag_ok = _unique_tag("p07-sender-ok")
    subject_ok = f"phase07 sender ok {tag_ok}"
    body_ok = f"LDAP sender restrict test ok {tag_ok}"

    try:
        _smtp_auth_send(
            smtp_host,
            ldap_user,
            ldap_pw,
            f"{ldap_user}@{domain}",
            f"{ldap_user}@{domain}",
            subject_ok,
            body_ok,
            timeout=args.timeout,
        )
        print(f"  Send as {ldap_user}@{domain}: OK")
    except smtplib.SMTPAuthenticationError as e:
        fail_case("ldap-sender-restrict", f"LDAP auth failed: {e}")
        return
    except Exception as e:
        fail_case("ldap-sender-restrict", f"Send as own address failed: {e}")
        return

    # Test 2: Send as admin@domain — must be REJECTED
    tag_bad = _unique_tag("p07-sender-bad")
    subject_bad = f"phase07 sender bad {tag_bad}"
    body_bad = f"LDAP sender restrict test bad {tag_bad}"

    try:
        rejected, reason = _smtp_auth_send_expect_reject(
            smtp_host,
            ldap_user,
            ldap_pw,
            f"admin@{domain}",
            f"admin@{domain}",
            subject_bad,
            body_bad,
            timeout=args.timeout,
        )
    except smtplib.SMTPAuthenticationError as e:
        fail_case("ldap-sender-restrict", f"LDAP auth failed on reject test: {e}")
        return
    except Exception as e:
        fail_case("ldap-sender-restrict", f"Sender restrict test exception: {e}")
        return

    if not rejected:
        fail_case(
            "ldap-sender-restrict",
            f"Send as admin@{domain} was NOT rejected (sender ownership broken)",
        )
        return

    print(f"  Send as admin@{domain}: REJECTED ({reason})")

    # Verify the rejection code is 5xx (permanent), not 4xx (temporary)
    if "SMTP 5" not in reason and "550" not in reason and "553" not in reason:
        fail_case(
            "ldap-sender-restrict",
            f"Sender rejection was not 550/553: {reason}",
        )
        return

    pass_case(
        "ldap-sender-restrict",
        f"LDAP user {ldap_user} can only send as own address (admin@{domain} rejected)",
    )


# ===================================================================
# Case: ldap-imap-delivery (LDAP-03)
# ===================================================================


def case_ldap_imap_delivery(args: argparse.Namespace) -> None:
    """LDAP-03: LDAP ta user can receive and read mail via IMAP.

    Sends mail to mailta@domain via SMTP (authenticated as admin or test),
    then IMAP logs in as mailta and fetches the message.
    """
    host = args.host

    try:
        domain = _derive_domain(
            host, timeout=args.timeout, port=args.port, proxy_jump=args.proxy_jump
        )
    except Exception as e:
        fail_case("ldap-imap-delivery", f"Domain derivation failed: {e}")
        return

    smtp_host = _resolve_service_host(args.service_host, domain, "smtp")
    imap_host = _resolve_service_host(args.service_host, domain, "imap")
    ldap_user = args.ldap_user

    try:
        ldap_pw = _ldap_password(args)
    except ValueError as e:
        fail_case("ldap-imap-delivery", f"LDAP password: {e}")
        return

    # Use admin to send to LDAP user (avoids needing LDAP SMTP auth for delivery test)
    try:
        admin_pw = _admin_password(args)
    except ValueError as e:
        fail_case("ldap-imap-delivery", f"Admin password: {e}")
        return

    tag = _unique_tag("p07-imap")
    subject = f"phase07 LDAP IMAP delivery {tag}"
    body = f"LDAP IMAP delivery verification {tag}"
    sender = f"admin@{domain}"
    recipient = f"{ldap_user}@{domain}"

    # Step 1: Send mail to LDAP user via SMTP (authenticated as admin)
    try:
        _smtp_auth_send(
            smtp_host,
            "admin",
            admin_pw,
            sender,
            recipient,
            subject,
            body,
            timeout=args.timeout,
        )
        print(f"  SMTP send to {recipient}: OK")
    except Exception as e:
        fail_case("ldap-imap-delivery", f"SMTP send to {recipient} failed: {e}")
        return

    # Step 2: IMAP login as LDAP user and fetch
    found, raw_msg = _imap_fetch_raw(imap_host, ldap_user, ldap_pw, tag)
    if not found or raw_msg is None:
        fail_case(
            "ldap-imap-delivery",
            f"Message {tag} not found via IMAP as {ldap_user}",
        )
        return

    # Step 3: Verify message content
    try:
        msg_obj = BytesParser(policy=policy.default).parsebytes(raw_msg)
    except Exception as e:
        fail_case("ldap-imap-delivery", f"Failed to parse delivered message: {e}")
        return

    body_text = ""
    if msg_obj.is_multipart():
        for part in msg_obj.walk():
            content_type = part.get_content_type()
            if content_type == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    body_text = payload.decode("utf-8", errors="replace")
                    break
    else:
        payload = msg_obj.get_payload(decode=True)
        if payload:
            body_text = payload.decode("utf-8", errors="replace")

    expected_phrase = f"LDAP IMAP delivery verification {tag}"
    if expected_phrase not in body_text:
        fail_case(
            "ldap-imap-delivery",
            f"Expected body content not found: '{expected_phrase[:80]}'",
        )
        return

    received_to = msg_obj.get("To", "")
    if ldap_user not in received_to:
        fail_case(
            "ldap-imap-delivery",
            f"To header mismatch: expected {ldap_user}, got '{received_to}'",
        )
        return

    print(f"  IMAP fetch: message verified (To: {received_to})")

    pass_case(
        "ldap-imap-delivery",
        f"LDAP user {ldap_user} received and read mail via IMAP",
    )


# ===================================================================
# Case: ldap-list-member (LDAP-04)
# ===================================================================


def case_ldap_list_member(args: argparse.Namespace) -> None:
    """LDAP-04: LDAP ta user can be a mailing list member.

    POST to list API creating a list with mailta as member, send mail to the
    list address, verify mailta receives via IMAP, then DELETE the list.
    """
    host = args.host

    try:
        domain = _derive_domain(
            host, timeout=args.timeout, port=args.port, proxy_jump=args.proxy_jump
        )
    except Exception as e:
        fail_case("ldap-list-member", f"Domain derivation failed: {e}")
        return

    smtp_host = _resolve_service_host(args.service_host, domain, "smtp")
    imap_host = _resolve_service_host(args.service_host, domain, "imap")
    api_host = smtp_host  # List API runs on the mail server
    api_port = 8000
    ldap_user = args.ldap_user

    try:
        ldap_pw = _ldap_password(args)
    except ValueError as e:
        fail_case("ldap-list-member", f"LDAP password: {e}")
        return

    try:
        admin_pw = _admin_password(args)
    except ValueError as e:
        fail_case("ldap-list-member", f"Admin password: {e}")
        return

    # Step 1: Create a test list with LDAP user as member
    list_suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
    list_name = f"ldaptest{list_suffix}"
    members = ["admin", ldap_user]
    payload = json.dumps({"name": list_name, "members": members}).encode("utf-8")

    try:
        status, body = _api_request(
            api_host, api_port, "POST", "/list/create", payload, timeout=args.timeout
        )
    except ConnectionError as e:
        fail_case("ldap-list-member", f"API connection failed: {e}")
        return
    except Exception as e:
        fail_case("ldap-list-member", f"HTTP create failed: {e}")
        return

    print(f"  POST /list/create ({list_name}) → {status}")
    if not (200 <= status < 300):
        fail_case(
            "ldap-list-member",
            f"List creation failed: HTTP {status} — {body[:200]}",
        )
        return

    # Wait for Postfix reload
    time.sleep(1.5)

    # Step 2: Send mail to the list address
    tag = _unique_tag("p07-list")
    subject = f"phase07 LDAP list test {tag}"
    body_text = f"LDAP list member delivery {tag}"
    list_addr = f"{list_name}@{domain}"

    try:
        _smtp_auth_send(
            smtp_host,
            "admin",
            admin_pw,
            f"admin@{domain}",
            list_addr,
            subject,
            body_text,
            timeout=args.timeout,
        )
        print(f"  SMTP send to {list_addr}: OK")
    except Exception as e:
        # Attempt cleanup on failure
        try:
            _api_request(api_host, api_port, "DELETE", f"/list/{list_name}")
        except Exception:
            pass
        fail_case("ldap-list-member", f"SMTP send to list failed: {e}")
        return

    # Step 3: Verify LDAP user received the message via IMAP
    found, raw_msg = _imap_fetch_raw(imap_host, ldap_user, ldap_pw, tag)
    if not found:
        fail_case(
            "ldap-list-member",
            f"LDAP user {ldap_user} did not receive list message {tag}",
        )
        # Attempt cleanup
        try:
            _api_request(api_host, api_port, "DELETE", f"/list/{list_name}")
        except Exception:
            pass
        return

    print(f"  LDAP user {ldap_user} received list message via IMAP: OK")

    # Step 4: DELETE the list
    try:
        status_del, body_del = _api_request(
            api_host, api_port, "DELETE", f"/list/{list_name}", timeout=args.timeout
        )
    except Exception as e:
        fail_case("ldap-list-member", f"List DELETE failed (cleanup): {e}")
        return

    print(f"  DELETE /list/{list_name} → {status_del}")
    if not (200 <= status_del < 300):
        fail_case(
            "ldap-list-member",
            f"List DELETE failed: HTTP {status_del} — {body_del[:200]}",
        )
        return

    pass_case(
        "ldap-list-member",
        f"LDAP user {ldap_user} is list member — created list '{list_name}', "
        f"delivered message, deleted list",
    )


# ---------------------------------------------------------------------------
# Case dispatch
# ---------------------------------------------------------------------------

CASES: dict[str, object] = {
    "ldap-flag-check": case_ldap_flag_check,
    "ldap-disabled-regression": case_ldap_disabled_regression,
    "ldap-smtp-auth": case_ldap_smtp_auth,
    "ldap-sender-restrict": case_ldap_sender_restrict,
    "ldap-imap-delivery": case_ldap_imap_delivery,
    "ldap-list-member": case_ldap_list_member,
    "all": None,
}

QUICK_CASES = ["ldap-flag-check", "ldap-disabled-regression"]
FULL_CASES = [
    "ldap-flag-check",
    "ldap-disabled-regression",
    "ldap-smtp-auth",
    "ldap-sender-restrict",
    "ldap-imap-delivery",
    "ldap-list-member",
]


def run_case(case_name: str, args: argparse.Namespace) -> None:
    """Run a single named case. 'all' dispatches every case."""
    if case_name == "all":
        for name in FULL_CASES:
            run_case(name, args)
        return

    fn = CASES.get(case_name)
    if fn is None or not callable(fn):
        print(f"ERROR: unknown case '{case_name}'", file=sys.stderr)
        sys.exit(1)
    try:
        fn(args)  # type: ignore[operator]
    except Exception as e:
        fail_case(case_name, f"Unexpected exception: {e.__class__.__name__}: {e}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Phase 07 LDAP integration verification script. "
            "Tests LDAP-disabled regression, LDAP-enabled SMTP auth, "
            "sender ownership, IMAP delivery, list membership, and "
            "explicit enablement flag behavior."
        )
    )
    parser.add_argument(
        "--host",
        required=True,
        help="SSH target for remote probes (e.g., dmz-client-01). "
        "SMTP/IMAP hostnames are derived from the target's domain.",
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
        "--quick",
        action="store_true",
        help="Run quick smoke subset: ldap-flag-check + ldap-disabled-regression. "
        "No LDAP server required.",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Run all 6 cases. Requires LDAP server with mailta user in ta group.",
    )
    parser.add_argument(
        "--ldap-user",
        default="mailta",
        help="LDAP test user name (default: mailta)",
    )
    parser.add_argument(
        "--ldap-password",
        default=None,
        help="Password for LDAP test user (env: LDAP_TEST_PASSWORD)",
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
        "--timeout",
        type=int,
        default=15,
        help="Socket and SSH timeout in seconds (default: 15)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="SSH port for the target host (default: standard SSH port)",
    )
    parser.add_argument(
        "--proxy-jump",
        default=None,
        help="SSH ProxyJump host (e.g., user@router:port) for reaching the target",
    )
    parser.add_argument(
        "--service-host",
        default=None,
        help="Override hostname for SMTP/IMAP/API connections "
        "(use when DNS-derived hostnames are not reachable, e.g., 127.0.0.1 with tunnels)",
    )

    args = parser.parse_args()

    # Determine which cases to run
    if args.quick and args.full:
        parser.error("--quick and --full are mutually exclusive")
    if args.cases and (args.quick or args.full):
        parser.error("--case cannot be combined with --quick or --full")
    if args.cases:
        cases_to_run = args.cases
    elif args.quick:
        cases_to_run = QUICK_CASES
    elif args.full:
        cases_to_run = FULL_CASES
    else:
        parser.error(
            "Specify --case, --quick, or --full. Use --case all to run every case."
        )

    # Sanitize password display
    admin_set = bool(args.admin_password or os.environ.get("MAIL_ADMIN_PASSWORD"))
    test_set = bool(args.test_password or os.environ.get("MAIL_TEST_PASSWORD"))
    ldap_set = bool(args.ldap_password or os.environ.get("LDAP_TEST_PASSWORD"))

    print("=== Phase 07 LDAP Integration Verification ===")
    print(f"Host (SSH target): {args.host}")
    if args.port:
        print(f"SSH port: {args.port}")
    if args.proxy_jump:
        print(f"ProxyJump: {args.proxy_jump}")
    if args.service_host:
        print(f"Service host override: {args.service_host}")
    print(f"LDAP user: {args.ldap_user}")
    print(f"Admin password: {'set' if admin_set else 'NOT SET'}")
    print(f"Test password:  {'set' if test_set else 'NOT SET'}")
    print(f"LDAP password:  {'set' if ldap_set else 'NOT SET'}")
    print(f"Cases: {cases_to_run}")
    print()

    for case_name in cases_to_run:
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
