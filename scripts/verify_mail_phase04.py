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
# DKIM header verification helpers
# ---------------------------------------------------------------------------


def _send_authenticated(
    args, sender_user, sender_domain, recipient_user, recipient_domain, tag
):
    """Send an authenticated SMTP 587 STARTTLS message and return the tag
    on success, or raise on failure."""
    recipient = f"{recipient_user}@{recipient_domain}"
    msg_id = f"<{tag}@{args.domain}>"
    body = f"dkim test {tag}"

    sender_password = password_for(sender_user, args)
    message = (
        f"From: {sender_user}@{sender_domain}\r\n"
        f"To: {recipient}\r\n"
        f"Message-ID: {msg_id}\r\n"
        f"Subject: dkim {tag}\r\n\r\n"
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


def _check_dkim_header(raw_msg, expected_domain, selector):
    """Parse raw message bytes and assert DKIM-Signature contains the
    expected selector and d= domain.  Returns True if found."""
    if raw_msg is None:
        return False
    message_obj = BytesParser(policy=policy.default).parsebytes(raw_msg)
    dkim_headers = message_obj.get_all("DKIM-Signature", [])
    if not dkim_headers:
        return False
    for hdr in dkim_headers:
        if f"s={selector}" in hdr and f"d={expected_domain}" in hdr:
            return True
    return False


# ---------------------------------------------------------------------------
# Case: dkim-base
# ---------------------------------------------------------------------------


def case_dkim_base(args):
    """Send from admin@<domain> and verify DKIM-Signature with
    s=2026-na d=<domain>."""
    tag = f"phase04-dkim-base-{int(time.time())}"
    try:
        _send_authenticated(args, "admin", args.domain, "admin", args.domain, tag)
    except Exception as e:
        fail_case("dkim-base", f"SMTP send failed: {e}")
        return

    found, raw_msg = _imap_fetch_raw(args.imap_host, "admin", args.admin_password, tag)
    if not found or raw_msg is None:
        fail_case("dkim-base", f"Message {tag} not found via IMAP")
        return

    if not _check_dkim_header(raw_msg, args.domain, args.dkim_selector):
        # Try to provide detail
        msg_obj = BytesParser(policy=policy.default).parsebytes(raw_msg)
        dkim_hdrs = msg_obj.get_all("DKIM-Signature", [])
        detail = f"missing DKIM-Signature with s={args.dkim_selector} d={args.domain}"
        if dkim_hdrs:
            detail += f"; found: {dkim_hdrs[0][:120]}..."
        fail_case("dkim-base", detail)
        return

    pass_case(
        "dkim-base",
        f"DKIM-Signature present with s={args.dkim_selector} and d={args.domain}",
    )


# ---------------------------------------------------------------------------
# Case: dkim-mail
# ---------------------------------------------------------------------------


def case_dkim_mail(args):
    """Send from test@<mail-domain> and verify DKIM-Signature with
    s=2026-na d=<mail-domain>."""
    tag = f"phase04-dkim-mail-{int(time.time())}"
    try:
        _send_authenticated(
            args, "test", args.mail_domain, "test", args.mail_domain, tag
        )
    except Exception as e:
        fail_case("dkim-mail", f"SMTP send failed: {e}")
        return

    found, raw_msg = _imap_fetch_raw(args.imap_host, "test", args.test_password, tag)
    if not found or raw_msg is None:
        fail_case("dkim-mail", f"Message {tag} not found via IMAP")
        return

    if not _check_dkim_header(raw_msg, args.mail_domain, args.dkim_selector):
        msg_obj = BytesParser(policy=policy.default).parsebytes(raw_msg)
        dkim_hdrs = msg_obj.get_all("DKIM-Signature", [])
        detail = (
            f"missing DKIM-Signature with s={args.dkim_selector} d={args.mail_domain}"
        )
        if dkim_hdrs:
            detail += f"; found: {dkim_hdrs[0][:120]}..."
        fail_case("dkim-mail", detail)
        return

    pass_case(
        "dkim-mail",
        f"DKIM-Signature present with s={args.dkim_selector} and d={args.mail_domain}",
    )


# ---------------------------------------------------------------------------
# Case: dkim-key
# ---------------------------------------------------------------------------


def case_dkim_key(args):
    """Run opendkim-testkey over SSH for both managed domains."""
    for domain in [args.domain, args.mail_domain]:
        remote_cmd = (
            f"sudo opendkim-testkey -d {shlex.quote(domain)} "
            f"-s {shlex.quote(args.dkim_selector)} "
            f"-k {shlex.quote(args.dkim_key_path)} -vvv"
        )
        proc = ssh_cmd(args.ssh_host, remote_cmd, timeout=args.timeout)
        if proc.returncode != 0:
            fail_case(
                "dkim-key",
                f"opendkim-testkey failed for {domain}: "
                f"rc={proc.returncode} stderr={proc.stderr.strip()[:200]}",
            )
            return
        # opendkim-testkey may print "key OK" or similar on success
        output = (proc.stdout or "") + (proc.stderr or "")
        if "key OK" not in output and "key not secure" not in output:
            # "key not secure" is a warning, not a failure; treat as pass
            fail_case(
                "dkim-key",
                f"opendkim-testkey for {domain} did not report success: "
                f"{output.strip()[:200]}",
            )
            return
    pass_case("dkim-key", "opendkim-testkey passed for both managed domains")


# ---------------------------------------------------------------------------
# Case: spf-dmarc
# ---------------------------------------------------------------------------


def _dig_txt(record: str, timeout: int = 15) -> str:
    """Run dig +short TXT and return stdout as a single string."""
    proc = subprocess.run(
        ["dig", "+short", "TXT", record],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return (proc.stdout or "").strip()


def case_spf_dmarc(args):
    """Verify SPF and DMARC DNS TXT records for both managed domains."""
    # SPF expected (per-identity spec)
    expected_spf = "v=spf1 a:smtp."

    for domain in [args.domain, args.mail_domain]:
        # --- DKIM TXT: reject t=y ---
        dkim_record = f"{args.dkim_selector}._domainkey.{domain}"
        dkim_txt = _dig_txt(dkim_record, timeout=args.timeout)
        if not dkim_txt:
            fail_case(
                "spf-dmarc", f"DKIM TXT record {dkim_record} not found for {domain}"
            )
            return
        if "t=y" in dkim_txt:
            fail_case(
                "spf-dmarc",
                f"DKIM TXT for {domain} still contains t=y (testing mode) "
                f"in {dkim_record}",
            )
            return

        # --- SPF: require v=spf1 a:smtp.<domain> ~all ---
        spf_txt = _dig_txt(domain, timeout=args.timeout)
        if not spf_txt:
            fail_case("spf-dmarc", f"SPF TXT record not found for {domain}")
            return
        if expected_spf not in spf_txt or "~all" not in spf_txt:
            fail_case(
                "spf-dmarc",
                f"SPF record for {domain} missing '{expected_spf}' or '~all': "
                f"{spf_txt[:200]}",
            )
            return

        # --- DMARC: require p=quarantine and correct RUA ---
        dmarc_record = f"_dmarc.{domain}"
        dmarc_txt = _dig_txt(dmarc_record, timeout=args.timeout)
        if not dmarc_txt:
            fail_case("spf-dmarc", f"DMARC TXT record not found for {dmarc_record}")
            return
        # Expected DMARC policy shape: v=DMARC1; p=quarantine; rua=mailto:dmarc-report-rua@<domain>
        dmarc_clean = dmarc_txt.strip('"').strip("'")
        if "v=DMARC1" not in dmarc_clean or "p=quarantine" not in dmarc_clean:
            fail_case(
                "spf-dmarc",
                f"DMARC record for {domain} missing v=DMARC1 or p=quarantine: "
                f"{dmarc_clean[:200]}",
            )
            return
        expected_rua = f"rua=mailto:dmarc-report-rua@{args.domain}"
        if expected_rua not in dmarc_clean:
            fail_case(
                "spf-dmarc",
                f"DMARC RUA for {domain} does not point to {args.domain}: "
                f"{dmarc_clean[:200]}",
            )
            return

    pass_case("spf-dmarc", "SPF/DMARC/DKIM-t=y checks passed for both managed domains")


# ---------------------------------------------------------------------------
# Case: milter-order
# ---------------------------------------------------------------------------


def case_milter_order(args):
    """Verify Postfix milter ordering and tempfail behavior."""
    proc = ssh_cmd(
        args.ssh_host,
        "postconf -n smtpd_milters non_smtpd_milters "
        "milter_default_action milter_protocol",
        timeout=args.timeout,
    )
    if proc.returncode != 0:
        fail_case("milter-order", f"postconf -n failed: {proc.stderr.strip()[:200]}")
        return

    output = (proc.stdout or "").strip()
    # Parse key = value lines
    lines = output.splitlines()
    config = {}
    for line in lines:
        if "=" in line:
            key, _, value = line.partition("=")
            config[key.strip()] = value.strip()

    # milter_protocol must be 6
    if config.get("milter_protocol") != "6":
        fail_case(
            "milter-order",
            f"milter_protocol is {config.get('milter_protocol', 'missing')}, expected 6",
        )
        return

    # milter_default_action must be tempfail
    if config.get("milter_default_action") != "tempfail":
        fail_case(
            "milter-order",
            f"milter_default_action is {config.get('milter_default_action', 'missing')}, "
            f"expected tempfail",
        )
        return

    # Both smtpd_milters and non_smtpd_milters must end with inet:127.0.0.1:8891
    expected_socket = "inet:127.0.0.1:8891"
    for key in ["smtpd_milters", "non_smtpd_milters"]:
        value = config.get(key, "")
        if not value.endswith(expected_socket):
            fail_case(
                "milter-order",
                f"{key} does not end with {expected_socket}: {value[:200]}",
            )
            return

    pass_case(
        "milter-order",
        "milter_protocol=6, milter_default_action=tempfail, "
        "OpenDKIM last in smtpd_milters/non_smtpd_milters",
    )


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
    parser.add_argument(
        "--dkim-selector",
        default="2026-na",
        help="DKIM selector (default: 2026-na)",
    )
    parser.add_argument(
        "--dkim-key-path",
        default="/etc/opendkim/keys/2026-na.private",
        help="Path to DKIM private key on SSH target "
        "(default: /etc/opendkim/keys/2026-na.private)",
    )

    args = parser.parse_args()

    if not args.cases:
        parser.error(
            "At least one --case is required. Use --case all to run all cases."
        )

    print("=== Phase 04 Mail Security Verification ===")
    print(f"SMTP: {args.smtp_host}  IMAP: {args.imap_host}")
    print(f"Domain: {args.domain}  Mail domain: {args.mail_domain}")
    print(f"SSH host: {args.ssh_host}  DKIM selector: {args.dkim_selector}")
    print(f"Key path: {args.dkim_key_path}")
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
