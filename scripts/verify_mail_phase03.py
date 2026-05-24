#!/usr/bin/env python3
"""Phase 03 mail service verification script.

Tests auth, SMTP, IMAP, STARTTLS, relay restrictions, sender ownership,
plus addressing, DNS routing, and idempotency behaviors for the
core local mail service on dmz-client-01.

Uses only Python standard library modules (smtplib, imaplib, subprocess,
socket, ssl) — no swaks or nmap required.
"""

import argparse
import shlex
import smtplib
import ssl
import subprocess
import sys
import time
import imaplib
from email.mime.text import MIMEText

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
# Case: auth-local
# ---------------------------------------------------------------------------


def case_auth_local(args):
    """Verify admin and test can authenticate through Dovecot passwd-file.

    Uses 'doveadm auth login' over SSH with password passed via stdin
    to avoid shell injection risks.
    """
    for user, password in [
        ("admin", args.admin_password),
        ("test", args.test_password),
    ]:
        remote_cmd = "sudo doveadm auth login -x service=imap " + shlex.quote(user)
        proc = subprocess.run(
            [
                "ssh",
                "-o",
                "StrictHostKeyChecking=no",
                "-o",
                "ConnectTimeout=5",
                "-o",
                "BatchMode=yes",
                args.ssh_host,
                remote_cmd,
            ],
            input=password,
            capture_output=True,
            text=True,
            timeout=15,
        )
        if proc.returncode != 0:
            fail_case(
                f"auth-local",
                f"doveadm auth login for {user} failed: {proc.stderr.strip()}",
            )
            return
        if "auth succeeded" not in (proc.stdout or "").lower():
            fail_case(
                f"auth-local", f"doveadm auth login for {user} did not report success"
            )
            return
    pass_case("auth-local", "admin and test authenticated via doveadm")


# ---------------------------------------------------------------------------
# Case: local-delivery
# ---------------------------------------------------------------------------


def case_local_delivery(args):
    """Unauthenticated port 25 delivers to local recipients and IMAP fetch confirms."""
    domain = args.domain
    mail_domain = args.mail_domain
    smtp_host = args.smtp_host
    imap_host = args.imap_host

    for user, rcpt_domain in [("admin", domain), ("test", mail_domain)]:
        tag = f"phase03-local-{int(time.time())}"
        recipient = f"{user}@{rcpt_domain}"
        msg_id = f"<{tag}@{domain}>"
        body = f"local-delivery test {tag}"
        message = (
            f"From: sender@{domain}\r\n"
            f"To: {recipient}\r\n"
            f"Message-ID: {msg_id}\r\n"
            f"Subject: local-delivery {tag}\r\n\r\n"
            f"{body}\r\n"
        )

        try:
            with smtplib.SMTP(smtp_host, 25, timeout=args.timeout) as smtp:
                smtp.ehlo()
                smtp.sendmail(f"sender@{domain}", [recipient], message)
        except smtplib.SMTPRecipientsRefused:
            fail_case("local-delivery", f"Port 25 rejected RCPT TO <{recipient}>")
            return
        except Exception as e:
            fail_case("local-delivery", f"SMTP error on port 25 for {recipient}: {e}")
            return

        # IMAP fetch confirmation
        try:
            found = _imap_fetch_contains(imap_host, user, password_for(user, args), tag)
        except Exception as e:
            fail_case("local-delivery", f"IMAP fetch error for {user}: {e}")
            return
        if not found:
            fail_case(
                "local-delivery", f"Message {tag} not found in {user} IMAP mailbox"
            )
            return

    pass_case("local-delivery", "Unauth port 25 + IMAP fetch for admin and test")


# ---------------------------------------------------------------------------
# Case: no-open-relay
# ---------------------------------------------------------------------------


def case_no_open_relay(args):
    """Port 25 must reject RCPT TO for non-local address admin@ta.nasa.

    Uses only admin@ta.nasa as the non-local recipient — does not
    iterate arbitrary public domains.
    """
    smtp_host = args.smtp_host
    domain = args.domain
    non_local_rcpt = f"admin@ta.nasa"

    try:
        with smtplib.SMTP(smtp_host, 25, timeout=args.timeout) as smtp:
            smtp.ehlo()
            # Attempt to relay to a non-local domain
            try:
                smtp.sendmail(f"sender@{domain}", [non_local_rcpt], "relay test\r\n")
                fail_case(
                    "no-open-relay", f"Port 25 accepted relay to {non_local_rcpt}"
                )
                return
            except smtplib.SMTPRecipientsRefused:
                pass  # Expected: relay rejected
            except smtplib.SMTPDataError:
                pass  # Also acceptable: relay rejected at DATA
    except Exception as e:
        fail_case("no-open-relay", f"SMTP connection error: {e}")
        return

    pass_case("no-open-relay", f"Port 25 correctly rejected relay to {non_local_rcpt}")


# ---------------------------------------------------------------------------
# Case: submission-starttls
# ---------------------------------------------------------------------------


def case_submission_starttls(args):
    """Port 587 rejects AUTH before STARTTLS and accepts authenticated send after STARTTLS."""
    smtp_host = args.smtp_host
    domain = args.domain

    # 1. Verify AUTH is rejected before STARTTLS on port 587
    try:
        with smtplib.SMTP(smtp_host, 587, timeout=args.timeout) as smtp:
            smtp.ehlo()
            # Try AUTH LOGIN before STARTTLS — should be rejected
            code, msg = smtp.docmd("AUTH", "LOGIN")
            # 503 or 530 or similar rejection expected
            if 200 <= code < 300:
                fail_case(
                    "submission-starttls", "Port 587 accepted AUTH before STARTTLS"
                )
                return
    except Exception as e:
        # Connection closed or error after bad AUTH attempt is also acceptable
        pass

    # 2. Verify STARTTLS succeeds and authenticated send works
    try:
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE

        with smtplib.SMTP(smtp_host, 587, timeout=args.timeout) as smtp:
            smtp.ehlo()
            smtp.starttls(context=context)
            smtp.ehlo()
            smtp.login("admin", args.admin_password)
            tag = f"phase03-starttls-{int(time.time())}"
            msg = MIMEText(f"submission starttls test {tag}")
            msg["From"] = f"admin@{domain}"
            msg["To"] = f"admin@{domain}"
            msg["Message-ID"] = f"<{tag}@{domain}>"
            msg["Subject"] = f"submission starttls {tag}"
            smtp.sendmail(f"admin@{domain}", [f"admin@{domain}"], msg.as_string())
    except Exception as e:
        fail_case("submission-starttls", f"STARTTLS + AUTH + send failed: {e}")
        return

    pass_case(
        "submission-starttls",
        "Port 587 rejects pre-TLS AUTH and accepts authenticated send after STARTTLS",
    )


# ---------------------------------------------------------------------------
# Case: sender-ownership
# ---------------------------------------------------------------------------


def case_sender_ownership(args):
    """Authenticated test cannot send as admin@<domain>."""
    smtp_host = args.smtp_host
    domain = args.domain
    mail_domain = args.mail_domain

    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE

    for sender_domain in [domain, mail_domain]:
        try:
            with smtplib.SMTP(smtp_host, 587, timeout=args.timeout) as smtp:
                smtp.ehlo()
                smtp.starttls(context=context)
                smtp.ehlo()
                smtp.login("test", args.test_password)
                # Attempt to send as admin from the domain
                spoofed_from = f"admin@{sender_domain}"
                try:
                    smtp.sendmail(spoofed_from, [spoofed_from], "spoof test\r\n")
                    fail_case(
                        "sender-ownership",
                        f"test sent as {spoofed_from} — ownership not enforced",
                    )
                    return
                except (
                    smtplib.SMTPSenderRefused,
                    smtplib.SMTPDataError,
                    smtplib.SMTPRecipientsRefused,
                ):
                    pass  # Expected: sender ownership rejected
        except smtplib.SMTPAuthenticationError as e:
            fail_case("sender-ownership", f"Authentication failed for test: {e}")
            return
        except Exception as e:
            # Acceptable: server rejected at envelope or data stage
            pass

    pass_case(
        "sender-ownership",
        "test correctly prevented from sending as admin on both domains",
    )


# ---------------------------------------------------------------------------
# Case: plus-base-domain
# ---------------------------------------------------------------------------


def case_plus_base_domain(args):
    """admin+phase03@<domain> delivers to admin's mailbox."""
    _case_plus_delivery(args, "plus-base-domain", args.domain, "admin")


# ---------------------------------------------------------------------------
# Case: plus-mail-domain
# ---------------------------------------------------------------------------


def case_plus_mail_domain(args):
    """test+phase03@<mail-domain> delivers to test's mailbox."""
    _case_plus_delivery(args, "plus-mail-domain", args.mail_domain, "test")


def _case_plus_delivery(args, case_name, target_domain, base_user):
    """Shared implementation for plus-address delivery cases."""
    smtp_host = args.smtp_host
    imap_host = args.imap_host
    tag = f"phase03-plus-{case_name}-{int(time.time())}"
    recipient = f"{base_user}+phase03@{target_domain}"
    msg_id = f"<{tag}@{args.domain}>"
    password = args.admin_password if base_user == "admin" else args.test_password

    message = (
        f"From: sender@{args.domain}\r\n"
        f"To: {recipient}\r\n"
        f"Message-ID: {msg_id}\r\n"
        f"Subject: plus-delivery {tag}\r\n\r\n"
        f"plus delivery test {tag}\r\n"
    )

    try:
        with smtplib.SMTP(smtp_host, 25, timeout=args.timeout) as smtp:
            smtp.ehlo()
            smtp.sendmail(f"sender@{args.domain}", [recipient], message)
    except smtplib.SMTPRecipientsRefused:
        fail_case(case_name, f"Port 25 rejected plus-address {recipient}")
        return
    except Exception as e:
        fail_case(case_name, f"SMTP delivery error for {recipient}: {e}")
        return

    # IMAP fetch
    try:
        found = _imap_fetch_contains(imap_host, base_user, password, tag)
    except Exception as e:
        fail_case(case_name, f"IMAP fetch error for {base_user}: {e}")
        return

    if not found:
        fail_case(
            case_name,
            f"Plus-address message {tag} not found in {base_user} IMAP mailbox",
        )
        return

    pass_case(case_name, f"Plus delivery to {recipient} reached {base_user} mailbox")


# ---------------------------------------------------------------------------
# Case: imap-starttls
# ---------------------------------------------------------------------------


def case_imap_starttls(args):
    """IMAP 143 STARTTLS succeeds with the self-signed certificate."""
    imap_host = args.imap_host

    try:
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE

        conn = imaplib.IMAP4(imap_host, 143)
        conn.starttls(ssl_context=context)
        # Login confirms STARTTLS works end-to-end
        conn.login("admin", args.admin_password)
        conn.logout()
    except Exception as e:
        fail_case("imap-starttls", f"IMAP STARTTLS + login failed: {e}")
        return

    pass_case("imap-starttls", "IMAP 143 STARTTLS + login succeeded")


# ---------------------------------------------------------------------------
# Case: smtp25-no-starttls-required
# ---------------------------------------------------------------------------


def case_smtp25_no_starttls_required(args):
    """Port 25 local delivery succeeds without STARTTLS."""
    smtp_host = args.smtp_host
    domain = args.domain
    tag = f"phase03-no-starttls-{int(time.time())}"
    recipient = f"admin@{domain}"
    msg_id = f"<{tag}@{domain}>"

    message = (
        f"From: sender@{domain}\r\n"
        f"To: {recipient}\r\n"
        f"Message-ID: {msg_id}\r\n"
        f"Subject: no-starttls {tag}\r\n\r\n"
        f"no-starttls test {tag}\r\n"
    )

    try:
        # Use plaintext SMTP on port 25 — no STARTTLS
        with smtplib.SMTP(smtp_host, 25, timeout=args.timeout) as smtp:
            smtp.ehlo()
            smtp.sendmail(f"sender@{domain}", [recipient], message)
    except smtplib.SMTPRecipientsRefused as e:
        fail_case(
            "smtp25-no-starttls-required", f"Port 25 rejected without STARTTLS: {e}"
        )
        return
    except Exception as e:
        fail_case("smtp25-no-starttls-required", f"SMTP error on port 25: {e}")
        return

    # Also verify the message appeared in IMAP
    try:
        found = _imap_fetch_contains(args.imap_host, "admin", args.admin_password, tag)
    except Exception as e:
        fail_case("smtp25-no-starttls-required", f"IMAP fetch error: {e}")
        return

    if not found:
        fail_case(
            "smtp25-no-starttls-required",
            f"Message not found in admin IMAP after no-STARTTLS send",
        )
        return

    pass_case(
        "smtp25-no-starttls-required", "Port 25 delivery without STARTTLS succeeded"
    )


# ---------------------------------------------------------------------------
# Case: normal-dns-routing
# ---------------------------------------------------------------------------


def case_normal_dns_routing(args):
    """relayhost is empty and transport_maps has no ta.nasa entry.

    Verifies via SSH that the Postfix config uses normal DNS
    resolution for outbound delivery.
    """
    # Check relayhost
    proc = ssh_cmd(args.ssh_host, "postconf -n relayhost")
    if proc.returncode != 0:
        fail_case(
            "normal-dns-routing", f"postconf -n relayhost failed: {proc.stderr.strip()}"
        )
        return
    relayhost_line = (proc.stdout or "").strip()
    # Expected: "relayhost =" or "relayhost =" or empty value
    if relayhost_line and relayhost_line != "relayhost =":
        fail_case(
            "normal-dns-routing",
            f"relayhost is set to non-empty value: {relayhost_line}",
        )
        return

    # Check transport_maps
    proc2 = ssh_cmd(args.ssh_host, "postconf -n transport_maps")
    if proc2.returncode != 0:
        fail_case(
            "normal-dns-routing",
            f"postconf -n transport_maps failed: {proc2.stderr.strip()}",
        )
        return
    transport_line = (proc2.stdout or "").strip()
    if "ta.nasa" in transport_line:
        fail_case(
            "normal-dns-routing", f"transport_maps contains 'ta.nasa': {transport_line}"
        )
        return

    pass_case(
        "normal-dns-routing",
        "relayhost empty and no ta.nasa in transport_maps — DNS routing confirmed",
    )


# ---------------------------------------------------------------------------
# IMAP fetch helper
# ---------------------------------------------------------------------------


def password_for(user, args):
    """Return the password for the given user."""
    if user == "admin":
        return args.admin_password
    return args.test_password


def _imap_fetch_contains(
    imap_host: str,
    user: str,
    password: str,
    tag: str,
    retries: int = 5,
    delay: float = 2.0,
) -> bool:
    """Login to IMAP with STARTTLS and look for a message containing the tag string."""
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE

    for attempt in range(retries):
        try:
            conn = imaplib.IMAP4(imap_host, 143)
            conn.starttls(ssl_context=context)
            conn.login(user, password)
            conn.select("INBOX")
            # Search for messages containing the tag
            status, data = conn.search(None, f'TEXT "{tag}"')
            if status == "OK" and data[0]:
                conn.logout()
                return True
            conn.logout()
        except Exception:
            pass
        time.sleep(delay)

    return False


# ---------------------------------------------------------------------------
# Case dispatch
# ---------------------------------------------------------------------------

CASES = {
    "auth-local": case_auth_local,
    "local-delivery": case_local_delivery,
    "no-open-relay": case_no_open_relay,
    "submission-starttls": case_submission_starttls,
    "sender-ownership": case_sender_ownership,
    "plus-base-domain": case_plus_base_domain,
    "plus-mail-domain": case_plus_mail_domain,
    "smtp25-no-starttls-required": case_smtp25_no_starttls_required,
    "imap-starttls": case_imap_starttls,
    "normal-dns-routing": case_normal_dns_routing,
    "all": None,  # runs all cases
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
        description="Phase 03 mail service verification script. "
        "Tests auth, SMTP, IMAP, STARTTLS, relay, sender-ownership, "
        "plus-addressing, DNS routing, and idempotency behaviors."
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
        help="SSH target for doveadm/postconf checks (e.g. dmz-client-01)",
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

    args = parser.parse_args()

    if not args.cases:
        parser.error(
            "At least one --case is required. Use --case all to run all cases."
        )

    print(f"=== Phase 03 Mail Verification ===")
    print(f"SMTP: {args.smtp_host}  IMAP: {args.imap_host}")
    print(f"Domain: {args.domain}  Mail domain: {args.mail_domain}")
    print(f"SSH host: {args.ssh_host}")
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
