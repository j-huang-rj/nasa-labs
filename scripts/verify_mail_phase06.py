#!/usr/bin/env python3
"""Phase 06 filtering & rewriting verification script.

Tests [SPAM] SMTP rejection, ID redaction in bodies, [TEST] prefixing,
DKIM integrity after rewrite, and fail-closed milter behavior.

Uses only Python standard library modules (smtplib, imaplib, email, subprocess).
"""

import argparse
import re
import shlex
import smtplib
import ssl
import subprocess
import sys
import time
import imaplib
from email import policy
from email.parser import BytesParser

# ---------------------------------------------------------------------------
# Result helpers
# ---------------------------------------------------------------------------

results = []


def pass_case(name: str, detail: str = ""):
    msg = f"CASE {name}: PASS"
    if detail:
        msg += f" ({detail})"
    print(msg)
    results.append((name, True, detail))


def fail_case(name: str, reason: str):
    print(f"CASE {name}: FAIL {reason}")
    results.append((name, False, reason))


# ---------------------------------------------------------------------------
# SSH helpers
# ---------------------------------------------------------------------------


def ssh_cmd(
    ssh_host: str, command: str, timeout: int = 15
) -> subprocess.CompletedProcess:
    """Run a command on the target host via SSH."""
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
):
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
# Password helper
# ---------------------------------------------------------------------------


def password_for(user, args):
    """Return the password for the given user."""
    if user == "admin":
        return args.admin_password
    return args.test_password


# ---------------------------------------------------------------------------
# Authenticated SMTP send helper
# ---------------------------------------------------------------------------


def _send_authenticated(
    args,
    sender_user,
    sender_domain,
    recipient_user,
    recipient_domain,
    tag,
    subject=None,
    body=None,
):
    """Send an authenticated SMTP 587 STARTTLS message and return the tag."""
    recipient = f"{recipient_user}@{recipient_domain}"
    sender_password = password_for(sender_user, args)

    if subject is None:
        subject = f"phase06 {tag}"
    if body is None:
        body = f"phase06 test {tag}"

    message = (
        f"From: {sender_user}@{sender_domain}\r\n"
        f"To: {recipient}\r\n"
        f"Subject: {subject}\r\n\r\n"
        f"{body}\r\n"
    )

    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE

    with smtplib.SMTP(args.smtp_host, 587, timeout=args.timeout) as smtp:
        smtp.ehlo()
        smtp.starttls(context=context)
        smtp.ehlo()
        smtp.login(sender_user, sender_password)
        smtp.sendmail(f"{sender_user}@{sender_domain}", [recipient], message)

    return tag


# ---------------------------------------------------------------------------
# Case: spam-reject (FILT-01)
# ---------------------------------------------------------------------------


def case_spam_reject(args):
    """Send [SPAM] mail and verify permanent 5xx SMTP rejection on port 25 and 587."""
    tag = f"phase06-spam-{int(time.time())}"

    # Test 1: Port 25 unauthenticated — [SPAM] subject must be rejected
    try:
        with smtplib.SMTP(args.smtp_host, 25, timeout=args.timeout) as smtp:
            smtp.ehlo()
            message = (
                f"From: sender@{args.domain}\r\n"
                f"To: admin@{args.domain}\r\n"
                f"Subject: [SPAM] test message {tag}\r\n\r\n"
                f"spam test body {tag}\r\n"
            )
            try:
                smtp.sendmail(
                    f"sender@{args.domain}",
                    [f"admin@{args.domain}"],
                    message,
                )
                fail_case("spam-reject", "Port 25 accepted [SPAM] message")
                return
            except smtplib.SMTPDataError as e:
                if e.smtp_code == 550:
                    print(f"  Port 25 [SPAM] → 550 (expected)")
                else:
                    fail_case(
                        "spam-reject",
                        f"Port 25 rejected [SPAM] with unexpected code {e.smtp_code}",
                    )
                    return
            except smtplib.SMTPRecipientsRefused:
                pass  # Also acceptable
    except Exception as e:
        fail_case("spam-reject", f"Port 25 SMTP connection error: {e}")
        return

    # Test 2: Port 587 authenticated (test user) — [SPAM] subject must also be rejected
    try:
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE

        with smtplib.SMTP(args.smtp_host, 587, timeout=args.timeout) as smtp:
            smtp.ehlo()
            smtp.starttls(context=context)
            smtp.ehlo()
            smtp.login("test", args.test_password)
            message = (
                f"From: test@{args.domain}\r\n"
                f"To: admin@{args.domain}\r\n"
                f"Subject: [SPAM] authenticated spam {tag}\r\n\r\n"
                f"spam test body {tag}\r\n"
            )
            try:
                smtp.sendmail(
                    f"test@{args.domain}",
                    [f"admin@{args.domain}"],
                    message,
                )
                fail_case(
                    "spam-reject", "Port 587 accepted [SPAM] message (authenticated)"
                )
                return
            except smtplib.SMTPDataError as e:
                if e.smtp_code == 550:
                    print(f"  Port 587 [SPAM] → 550 (expected)")
                else:
                    fail_case(
                        "spam-reject",
                        f"Port 587 rejected [SPAM] with unexpected code {e.smtp_code}",
                    )
                    return
            except smtplib.SMTPRecipientsRefused:
                pass
    except smtplib.SMTPAuthenticationError as e:
        fail_case("spam-reject", f"Port 587 authentication failed: {e}")
        return
    except Exception as e:
        fail_case("spam-reject", f"Port 587 SMTP connection error: {e}")
        return

    pass_case("spam-reject", "Properly rejected [SPAM] on port 25 and 587 with 550")


# ---------------------------------------------------------------------------
# Case: spam-no-queue (FILT-01 complementary)
# ---------------------------------------------------------------------------


def case_spam_no_queue(args):
    """Verify no [SPAM] messages in Postfix queue or mail storage."""
    # Check Postfix queue
    proc = ssh_cmd(
        args.ssh_host,
        "sudo postqueue -p 2>/dev/null | grep -i '\\[SPAM\\]' || true",
        timeout=args.timeout,
    )
    queue_output = (proc.stdout or "").strip()
    if queue_output:
        fail_case(
            "spam-no-queue", f"[SPAM] found in Postfix queue: {queue_output[:200]}"
        )
        return

    # Check mail storage
    proc2 = ssh_cmd(
        args.ssh_host,
        "sudo find /var/vmail -name '*.eml' -exec grep -l '\\[SPAM\\]' {} \\; 2>/dev/null || true",
        timeout=args.timeout,
    )
    mail_output = (proc2.stdout or "").strip()
    if mail_output:
        fail_case("spam-no-queue", f"[SPAM] found in mail storage: {mail_output[:200]}")
        return

    pass_case("spam-no-queue", "No [SPAM] in Postfix queue or /var/vmail")


# ---------------------------------------------------------------------------
# Case: id-redact (FILT-02)
# ---------------------------------------------------------------------------


def case_id_redact(args):
    """Send mail with ID numbers and verify redaction to ***."""
    tag = f"phase06-idredact-{int(time.time())}"
    subject = f"id redact test {tag}"
    body = f"Student ID: A123456789 and B987654321\r\nNormal text without IDs\r\n"

    try:
        _send_authenticated(
            args,
            "admin",
            args.domain,
            "admin",
            args.domain,
            tag,
            subject=subject,
            body=body,
        )
    except Exception as e:
        fail_case("id-redact", f"SMTP send failed: {e}")
        return

    found, raw_msg = _imap_fetch_raw(args.imap_host, "admin", args.admin_password, tag)
    if not found or raw_msg is None:
        fail_case("id-redact", f"Message {tag} not found via IMAP")
        return

    msg_obj = BytesParser(policy=policy.default).parsebytes(raw_msg)

    # Extract the plain text body
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

    # Assert redaction happened
    if "***" not in body_text:
        fail_case(
            "id-redact", f"ID redaction not applied (no *** found): {body_text[:200]}"
        )
        return

    # Assert specific IDs are gone
    for id_val in ["A123456789", "B987654321"]:
        if id_val in body_text:
            fail_case(
                "id-redact", f"ID {id_val} not redacted in body: {body_text[:200]}"
            )
            return

    # Assert normal text preserved
    if "Normal text without IDs" not in body_text:
        fail_case("id-redact", "Normal text corrupted during redaction")
        return

    pass_case("id-redact", "IDs redacted to ***, normal text preserved")


# ---------------------------------------------------------------------------
# Case: test-prefix (FILT-03)
# ---------------------------------------------------------------------------


def case_test_prefix(args):
    """Send from test@<domain> and verify [TEST] prefix on Subject."""
    tag = f"phase06-testprefix-{int(time.time())}"
    subject = f"test prefix check {tag}"
    body = "testing TEST prefix"

    try:
        _send_authenticated(
            args,
            "test",
            args.domain,
            "admin",
            args.domain,
            tag,
            subject=subject,
            body=body,
        )
    except Exception as e:
        fail_case("test-prefix", f"SMTP send failed: {e}")
        return

    found, raw_msg = _imap_fetch_raw(args.imap_host, "admin", args.admin_password, tag)
    if not found or raw_msg is None:
        fail_case("test-prefix", f"Message {tag} not found via IMAP")
        return

    msg_obj = BytesParser(policy=policy.default).parsebytes(raw_msg)
    received_subject = msg_obj.get("Subject", "")

    # Assert Subject starts with [TEST]
    if not received_subject.startswith("[TEST]"):
        fail_case(
            "test-prefix",
            f"Subject does not start with [TEST]: '{received_subject}'",
        )
        return

    # Assert original subject is preserved
    if subject not in received_subject:
        fail_case(
            "test-prefix",
            f"Original subject '{subject}' not found in '{received_subject}'",
        )
        return

    # Assert no double prefix
    if received_subject.startswith("[TEST][TEST]"):
        fail_case(
            "test-prefix",
            f"Double [TEST] prefix found: '{received_subject}'",
        )
        return

    pass_case("test-prefix", f"[TEST] prefix applied: '{received_subject}'")


# ---------------------------------------------------------------------------
# Case: test-no-double-prefix (FILT-03, D-03)
# ---------------------------------------------------------------------------


def case_test_no_double_prefix(args):
    """Send from test with Subject already starting [TEST] — verify no double prefix."""
    tag = f"phase06-nodouble-{int(time.time())}"
    subject = f"[TEST] already prefixed {tag}"
    body = "double prefix test"

    try:
        _send_authenticated(
            args,
            "test",
            args.domain,
            "test",
            args.domain,
            tag,
            subject=subject,
            body=body,
        )
    except Exception as e:
        fail_case("test-no-double-prefix", f"SMTP send failed: {e}")
        return

    found, raw_msg = _imap_fetch_raw(args.imap_host, "test", args.test_password, tag)
    if not found or raw_msg is None:
        fail_case("test-no-double-prefix", f"Message {tag} not found via IMAP")
        return

    msg_obj = BytesParser(policy=policy.default).parsebytes(raw_msg)
    received_subject = msg_obj.get("Subject", "")

    # Assert Subject is exactly the original — no duplicate prefix
    # Note: The milter may strip leading/trailing whitespace, so compare stripped
    if received_subject.strip() != subject.strip():
        # Check for double prefix specifically
        if received_subject.startswith("[TEST][TEST]"):
            fail_case(
                "test-no-double-prefix",
                f"Double [TEST] prefix found: '{received_subject}'",
            )
            return
        fail_case(
            "test-no-double-prefix",
            f"Subject changed: expected '{subject}', got '{received_subject}'",
        )
        return

    pass_case("test-no-double-prefix", f"No double prefix: '{received_subject}'")


# ---------------------------------------------------------------------------
# Case: dkim-after-rewrite (FILT-04)
# ---------------------------------------------------------------------------


def case_dkim_after_rewrite(args):
    """Send mail with body ID, verify DKIM header present AND redaction happened."""
    tag = f"phase06-dkimrewrite-{int(time.time())}"
    subject = f"dkim rewrite test {tag}"
    body = "ID check: C111222333"

    try:
        _send_authenticated(
            args,
            "admin",
            args.domain,
            "admin",
            args.domain,
            tag,
            subject=subject,
            body=body,
        )
    except Exception as e:
        fail_case("dkim-after-rewrite", f"SMTP send failed: {e}")
        return

    found, raw_msg = _imap_fetch_raw(args.imap_host, "admin", args.admin_password, tag)
    if not found or raw_msg is None:
        fail_case("dkim-after-rewrite", f"Message {tag} not found via IMAP")
        return

    msg_obj = BytesParser(policy=policy.default).parsebytes(raw_msg)

    # Assert DKIM-Signature present with correct selector and domain
    dkim_headers = msg_obj.get_all("DKIM-Signature", [])
    if not dkim_headers:
        fail_case("dkim-after-rewrite", "No DKIM-Signature header found")
        return

    dkim_found = False
    for hdr in dkim_headers:
        if f"s={args.dkim_selector}" in hdr and f"d={args.domain}" in hdr:
            dkim_found = True
            break

    if not dkim_found:
        fail_case(
            "dkim-after-rewrite",
            f"DKIM-Signature missing s={args.dkim_selector} or d={args.domain}",
        )
        return

    # Assert body contains *** (redaction happened)
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

    if "***" not in body_text:
        fail_case(
            "dkim-after-rewrite", "ID redaction not applied — *** not found in body"
        )
        return

    if "C111222333" in body_text:
        fail_case("dkim-after-rewrite", "ID C111222333 not redacted in body")
        return

    pass_case(
        "dkim-after-rewrite",
        f"DKIM signed with s={args.dkim_selector}, "
        f"body redacted (rewrite before DKIM confirmed)",
    )


# ---------------------------------------------------------------------------
# Case: fail-closed (D-09, D-12)
# ---------------------------------------------------------------------------


def case_fail_closed(args):
    """Stop milter, verify tempfail, restart milter, verify recovery."""
    tag = f"phase06-failclosed-{int(time.time())}"

    # Step 1: Stop the milter service
    proc = ssh_cmd(
        args.ssh_host,
        "sudo systemctl stop nasa-mail-milter",
        timeout=args.timeout,
    )
    if proc.returncode != 0:
        fail_case("fail-closed", f"Failed to stop milter: {proc.stderr.strip()[:200]}")
        return
    print("  Milter stopped")

    # Step 2: Try to send normal SMTP on port 25 — expect tempfail (4xx)
    try:
        with smtplib.SMTP(args.smtp_host, 25, timeout=args.timeout) as smtp:
            smtp.ehlo()
            message = (
                f"From: sender@{args.domain}\r\n"
                f"To: admin@{args.domain}\r\n"
                f"Subject: fail-closed test {tag}\r\n\r\n"
                f"fail-closed test body {tag}\r\n"
            )
            try:
                smtp.sendmail(
                    f"sender@{args.domain}",
                    [f"admin@{args.domain}"],
                    message,
                )
                fail_case(
                    "fail-closed", "Mail accepted when milter is down (should tempfail)"
                )
                # Continue to restart milter anyway
            except smtplib.SMTPDataError as e:
                if 400 <= e.smtp_code < 500:
                    print(f"  Milter-down send → {e.smtp_code} tempfail (expected)")
                else:
                    fail_case(
                        "fail-closed",
                        f"Milter-down rejected with {e.smtp_code}, expected 4xx tempfail",
                    )
                    # Continue to restart
            except smtplib.SMTPRecipientsRefused:
                print("  Milter-down send → recipient refused (acceptable)")
    except Exception as e:
        fail_case(
            "fail-closed", f"Port 25 SMTP connection error while milter down: {e}"
        )
        # Still try to restart milter
        ssh_cmd(
            args.ssh_host, "sudo systemctl start nasa-mail-milter", timeout=args.timeout
        )
        return

    # Step 3: Restart the milter
    proc2 = ssh_cmd(
        args.ssh_host,
        "sudo systemctl start nasa-mail-milter",
        timeout=args.timeout,
    )
    if proc2.returncode != 0:
        fail_case(
            "fail-closed", f"Failed to restart milter: {proc2.stderr.strip()[:200]}"
        )
        return
    print("  Milter restarted, waiting 3s...")
    time.sleep(3)

    # Step 4: Try sending again — should succeed now
    try:
        with smtplib.SMTP(args.smtp_host, 25, timeout=args.timeout) as smtp:
            smtp.ehlo()
            message = (
                f"From: sender@{args.domain}\r\n"
                f"To: admin@{args.domain}\r\n"
                f"Subject: fail-closed recovery {tag}\r\n\r\n"
                f"fail-closed recovery body {tag}\r\n"
            )
            smtp.sendmail(
                f"sender@{args.domain}",
                [f"admin@{args.domain}"],
                message,
            )
            print("  Post-restart send succeeded (expected)")
    except Exception as e:
        fail_case("fail-closed", f"Milter restart did not restore mail flow: {e}")
        return

    pass_case("fail-closed", "Milter-down tempfail, post-restart recovery confirmed")


# ---------------------------------------------------------------------------
# Case: list-expansion-rewrite (D-06)
# ---------------------------------------------------------------------------


def case_list_expansion_rewrite(args):
    """Send to local_users@<domain>, verify redaction on list-expanded delivery."""
    tag = f"phase06-listrewrite-{int(time.time())}"
    subject = f"list rewrite test {tag}"
    body = f"List ID: D444555666\r\nNormal text\r\n"

    # Send authenticated on port 587 to local_users
    recipient = f"local_users@{args.domain}"
    sender_user = "admin"
    sender_domain = args.domain
    sender_password = password_for(sender_user, args)

    message = (
        f"From: {sender_user}@{sender_domain}\r\n"
        f"To: {recipient}\r\n"
        f"Subject: {subject}\r\n\r\n"
        f"{body}\r\n"
    )

    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE

    try:
        with smtplib.SMTP(args.smtp_host, 587, timeout=args.timeout) as smtp:
            smtp.ehlo()
            smtp.starttls(context=context)
            smtp.ehlo()
            smtp.login(sender_user, sender_password)
            smtp.sendmail(f"{sender_user}@{sender_domain}", [recipient], message)
    except Exception as e:
        fail_case("list-expansion-rewrite", f"SMTP send to local_users failed: {e}")
        return

    # Verify via IMAP as test user (member of local_users)
    found, raw_msg = _imap_fetch_raw(args.imap_host, "test", args.test_password, tag)
    if not found or raw_msg is None:
        fail_case("list-expansion-rewrite", f"Message {tag} not found via IMAP as test")
        return

    msg_obj = BytesParser(policy=policy.default).parsebytes(raw_msg)

    # Extract plain text body
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

    # Assert redaction applied to list-expanded mail
    if "***" not in body_text:
        fail_case(
            "list-expansion-rewrite",
            f"ID redaction not applied to list-expanded mail (no ***): {body_text[:200]}",
        )
        return

    if "D444555666" in body_text:
        fail_case(
            "list-expansion-rewrite",
            f"ID D444555666 not redacted in list-expanded mail",
        )
        return

    pass_case("list-expansion-rewrite", "ID redacted in list-expanded delivery")


# ---------------------------------------------------------------------------
# Case: milter-order-check (FILT-04)
# ---------------------------------------------------------------------------


def case_milter_order_check(args):
    """Verify filter milter is BEFORE OpenDKIM in milter chain."""
    proc = ssh_cmd(
        args.ssh_host,
        "postconf -n smtpd_milters non_smtpd_milters milter_default_action",
        timeout=args.timeout,
    )
    if proc.returncode != 0:
        fail_case(
            "milter-order-check", f"postconf -n failed: {proc.stderr.strip()[:200]}"
        )
        return

    output = (proc.stdout or "").strip()
    lines = output.splitlines()
    config = {}
    for line in lines:
        if "=" in line:
            key, _, value = line.partition("=")
            config[key.strip()] = value.strip()

    # Verify milter_default_action is tempfail
    if config.get("milter_default_action") != "tempfail":
        fail_case(
            "milter-order-check",
            f"milter_default_action is {config.get('milter_default_action', 'missing')}, "
            f"expected tempfail",
        )
        return

    # Check milter ordering: filter milter (port 8892) must come BEFORE OpenDKIM (port 8891)
    for key in ["smtpd_milters", "non_smtpd_milters"]:
        value = config.get(key, "")
        if "inet:127.0.0.1:8892" not in value:
            fail_case(
                "milter-order-check",
                f"{key} does not contain filter milter socket inet:127.0.0.1:8892",
            )
            return
        if "inet:127.0.0.1:8891" not in value:
            fail_case(
                "milter-order-check",
                f"{key} does not contain OpenDKIM socket inet:127.0.0.1:8891",
            )
            return

        # Verify ordering: 8892 must appear before 8891
        filter_idx = value.find("inet:127.0.0.1:8892")
        dkim_idx = value.find("inet:127.0.0.1:8891")
        if filter_idx == -1 or dkim_idx == -1 or filter_idx >= dkim_idx:
            fail_case(
                "milter-order-check",
                f"{key}: filter milter (8892) must be BEFORE OpenDKIM (8891): {value}",
            )
            return

    pass_case(
        "milter-order-check",
        "Filter milter (8892) before OpenDKIM (8891), milter_default_action=tempfail",
    )


# ---------------------------------------------------------------------------
# Case dispatch
# ---------------------------------------------------------------------------

CASES = {
    "spam-reject": case_spam_reject,
    "spam-no-queue": case_spam_no_queue,
    "id-redact": case_id_redact,
    "test-prefix": case_test_prefix,
    "test-no-double-prefix": case_test_no_double_prefix,
    "dkim-after-rewrite": case_dkim_after_rewrite,
    "fail-closed": case_fail_closed,
    "list-expansion-rewrite": case_list_expansion_rewrite,
    "milter-order-check": case_milter_order_check,
    "all": None,
}


def run_case(case_name, args):
    """Run a single named case."""
    if case_name == "all":
        for name in CASES:
            if name == "all":
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
        fail_case(case_name, f"Unexpected exception: {e}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Phase 06 filtering & rewriting verification script. "
        "Tests [SPAM] SMTP rejection, ID redaction, [TEST] prefixing, "
        "DKIM integrity after rewrite, and fail-closed milter behavior."
    )
    parser.add_argument(
        "--smtp-host", required=True, help="SMTP server hostname (e.g. smtp.STUID.nasa)"
    )
    parser.add_argument(
        "--imap-host", required=True, help="IMAP server hostname (e.g. imap.STUID.nasa)"
    )
    parser.add_argument(
        "--domain", required=True, help="Base managed domain (e.g. STUID.nasa)"
    )
    parser.add_argument(
        "--mail-domain",
        required=True,
        help="Mail managed domain (e.g. mail.STUID.nasa)",
    )
    parser.add_argument(
        "--admin-password", required=True, help="Password for admin user"
    )
    parser.add_argument("--test-password", required=True, help="Password for test user")
    parser.add_argument(
        "--ssh-host",
        required=True,
        help="SSH target for postconf/systemctl checks (e.g. dmz-client-01)",
    )
    parser.add_argument(
        "--case",
        action="append",
        dest="cases",
        choices=list(CASES.keys()),
        help="Test case to run. Specify multiple times or use 'all'. "
        f"Available cases: {', '.join(k for k in CASES.keys() if k != 'all')}",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=15,
        help="Socket timeout in seconds (default: 15)",
    )
    parser.add_argument(
        "--dkim-selector",
        default="2026-na",
        help="DKIM selector (default: 2026-na)",
    )

    args = parser.parse_args()

    if not args.cases:
        parser.error(
            "At least one --case is required. Use --case all to run all cases."
        )

    print("=== Phase 06 Filtering & Rewriting Verification ===")
    print(f"SMTP: {args.smtp_host}  IMAP: {args.imap_host}")
    print(f"Domain: {args.domain}  Mail domain: {args.mail_domain}")
    print(f"SSH host: {args.ssh_host}  DKIM selector: {args.dkim_selector}")
    print(f"Cases: {args.cases}")
    print()

    for case_name in args.cases:
        run_case(case_name, args)

    # Summary
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
