#!/usr/bin/env python3
"""Phase 04 mail security signing verification script.

Tests DKIM signing, SPF/DMARC DNS alignment, and milter-order readiness
for managed-domain outbound mail on dmz-client-01.

Uses only Python standard library modules (smtplib, imaplib, email, subprocess).
"""

import argparse
import shlex
import smtplib
import ssl
import subprocess
import sys
import time
import imaplib
from email import policy
from email.parser import BytesParser
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
                # Get the raw message for the first match
                msg_ids = data[0].split()
                if msg_ids:
                    fetch_status, fetch_data = conn.fetch(msg_ids[-1], "(RFC822)")
                    if fetch_status == "OK" and fetch_data[0]:
                        # Extract bytes from the fetch response
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
                time.sleep(delay)
            else:
                return False, None
        else:
            time.sleep(delay)

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
# Cases (stubs for RED phase)
# ---------------------------------------------------------------------------


def case_dkim_base(args):
    """Send from admin@<domain> and verify DKIM-Signature header."""
    # TODO: implement in Task 2
    fail_case("dkim-base", "not yet implemented")


def case_dkim_mail(args):
    """Send from test@<mail-domain> and verify DKIM-Signature header."""
    # TODO: implement in Task 2
    fail_case("dkim-mail", "not yet implemented")


def case_dkim_key(args):
    """Run opendkim-testkey over SSH for both managed domains."""
    # TODO: implement in Task 2
    fail_case("dkim-key", "not yet implemented")


def case_spf_dmarc(args):
    """Verify SPF and DMARC DNS TXT records for both managed domains."""
    # TODO: implement in Task 2
    fail_case("spf-dmarc", "not yet implemented")


def case_milter_order(args):
    """Verify Postfix milter ordering and tempfail behavior."""
    # TODO: implement in Task 2
    fail_case("milter-order", "not yet implemented")


# ---------------------------------------------------------------------------
# Case dispatch
# ---------------------------------------------------------------------------

CASES = {
    "dkim-base": case_dkim_base,
    "dkim-mail": case_dkim_mail,
    "dkim-key": case_dkim_key,
    "spf-dmarc": case_spf_dmarc,
    "milter-order": case_milter_order,
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
        description="Phase 04 mail security signing verification script. "
        "Tests DKIM signing, SPF/DMARC DNS alignment, and milter-order readiness."
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
        help="SSH target for opendkim-testkey/postconf checks (e.g. dmz-client-01)",
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
    # NOTE: deliberately missing --dkim-key-path and --dkim-selector for RED phase
    # These will be added in GREEN phase.

    args = parser.parse_args()

    if not args.cases:
        parser.error(
            "At least one --case is required. Use --case all to run all cases."
        )

    print("=== Phase 04 Mail Security Verification ===")
    print(f"SMTP: {args.smtp_host}  IMAP: {args.imap_host}")
    print(f"Domain: {args.domain}  Mail domain: {args.mail_domain}")
    print(f"SSH host: {args.ssh_host}")
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
