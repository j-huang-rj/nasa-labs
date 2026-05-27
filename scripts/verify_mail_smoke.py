#!/usr/bin/env python3
"""Full non-LDAP HW1-2 smoke gate verification wrapper.

Orchestrates all mail phase verifiers (Phase 03 through Phase 06) plus
additional smoke-gate-specific checks: DNS regression, Ansible idempotency,
no-open-relay regression, and LDAP gating.

LDAP-tagged checks are reported as explicitly skipped, not failed (D-16).

Uses only Python standard library modules.
"""

import argparse
import imaplib
import smtplib
import subprocess
import sys
import time

# ---------------------------------------------------------------------------
# Result helpers
# ---------------------------------------------------------------------------

results = []


def pass_case(name: str, detail: str = "") -> None:
    msg = f"CASE {name}: PASS"
    if detail:
        msg += f" ({detail})"
    print(msg)
    results.append((name, True, detail))


def fail_case(name: str, reason: str) -> None:
    print(f"CASE {name}: FAIL {reason}")
    results.append((name, False, reason))


def skip_case(name: str, reason: str = "") -> None:
    """Report a case as explicitly skipped (not failed)."""
    msg = f"CASE {name}: SKIP"
    if reason:
        msg += f" ({reason})"
    print(msg)
    results.append((name, None, reason))


# ---------------------------------------------------------------------------
# SSH helper
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
# Phase verifier wrappers
# ---------------------------------------------------------------------------


def _run_phase_verifier(
    script: str,
    label: str,
    extra_args: list | None,
    args: argparse.Namespace,
) -> bool:
    """Run a single phase verifier script via subprocess.

    Returns True if returncode == 0, False otherwise.
    """
    cmd = [
        sys.executable,
        script,
        "--smtp-host",
        args.smtp_host,
        "--imap-host",
        args.imap_host,
        "--domain",
        args.domain,
        "--mail-domain",
        args.mail_domain,
        "--admin-password",
        args.admin_password,
        "--test-password",
        args.test_password,
        "--ssh-host",
        args.ssh_host,
        "--case",
        "all",
    ]
    if extra_args:
        cmd.extend(extra_args)

    print(f"\n{'=' * 60}")
    print(f" Running: {label} ({script})")
    print(f"{'=' * 60}")

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
        )
    except subprocess.TimeoutExpired:
        fail_case(f"phase-{label.lower().replace(' ', '-')}", "Timed out after 300s")
        return False
    except Exception as e:
        fail_case(f"phase-{label.lower().replace(' ', '-')}", f"Subprocess error: {e}")
        return False

    if proc.stdout:
        print(proc.stdout)
    if proc.stderr:
        print(proc.stderr, file=sys.stderr)

    if proc.returncode == 0:
        pass_case(f"phase-{label.lower().replace(' ', '-')}", f"{label} passed")
        return True
    else:
        fail_case(
            f"phase-{label.lower().replace(' ', '-')}",
            f"{label} returned exit code {proc.returncode}",
        )
        return False


def case_phase03(args: argparse.Namespace) -> None:
    _run_phase_verifier("scripts/verify_mail_phase03.py", "Phase 03", None, args)


def case_phase04(args: argparse.Namespace) -> None:
    _run_phase_verifier("scripts/verify_mail_phase04.py", "Phase 04", None, args)


def case_phase05(args: argparse.Namespace) -> None:
    extra = ["--api-host", args.api_host, "--api-port", str(args.api_port)]
    _run_phase_verifier("scripts/verify_mail_phase05.py", "Phase 05", extra, args)


def case_phase06(args: argparse.Namespace) -> None:
    _run_phase_verifier("scripts/verify_mail_phase06.py", "Phase 06", None, args)


# ---------------------------------------------------------------------------
# Smoke-gate-specific cases
# ---------------------------------------------------------------------------


def case_dns_regression(args: argparse.Namespace) -> None:
    """Run DNS regression checks: MX, A, SPF, DKIM, DMARC for both domains."""
    records_to_check = [
        # (record_type, record_name, description)
        ("MX", args.domain, f"{args.domain} MX"),
        ("MX", args.mail_domain, f"{args.mail_domain} MX"),
        ("A", f"smtp.{args.domain}", f"smtp.{args.domain} A"),
        ("A", f"imap.{args.domain}", f"imap.{args.domain} A"),
        ("TXT", args.domain, f"{args.domain} SPF TXT"),
        (
            "TXT",
            f"{args.dkim_selector}._domainkey.{args.domain}",
            f"{args.domain} DKIM TXT",
        ),
        ("TXT", f"_dmarc.{args.domain}", f"{args.domain} DMARC TXT"),
        ("TXT", args.mail_domain, f"{args.mail_domain} SPF TXT"),
        (
            "TXT",
            f"{args.dkim_selector}._domainkey.{args.mail_domain}",
            f"{args.mail_domain} DKIM TXT",
        ),
        ("TXT", f"_dmarc.{args.mail_domain}", f"{args.mail_domain} DMARC TXT"),
    ]

    all_passed = True
    for rtype, name, desc in records_to_check:
        proc = subprocess.run(
            ["dig", "+short", rtype, name],
            capture_output=True,
            text=True,
            timeout=args.timeout,
        )
        output = (proc.stdout or "").strip()
        if not output:
            fail_case("dns-regression", f"No {rtype} record for {name} ({desc})")
            all_passed = False
        else:
            print(f"  {rtype} {name} → {output[:120]}")

    if all_passed:
        pass_case("dns-regression", "All DNS records present for both managed domains")


def case_idempotency(args: argparse.Namespace) -> None:
    """Run ansible-playbook twice; second run must report 0 changes and 0 failures."""
    playbook = "ansible/playbooks/mail_configure.yml"

    # First run — may make changes
    print(f"  Running ansible-playbook (first pass)...")
    try:
        proc1 = subprocess.run(
            ["ansible-playbook", playbook],
            capture_output=True,
            text=True,
            timeout=300,
        )
    except subprocess.TimeoutExpired:
        fail_case("idempotency", "First ansible-playbook run timed out after 300s")
        return
    except FileNotFoundError:
        fail_case("idempotency", "ansible-playbook not found on PATH")
        return
    except Exception as e:
        fail_case("idempotency", f"First ansible-playbook run failed: {e}")
        return

    if proc1.returncode != 0:
        fail_case(
            "idempotency",
            f"First ansible-playbook run failed with exit code {proc1.returncode}",
        )
        return
    print(f"  First run: ok (exit 0)")

    # Second run — must report 0 changes and 0 failures
    print(f"  Running ansible-playbook (second pass — idempotency check)...")
    try:
        proc2 = subprocess.run(
            ["ansible-playbook", playbook],
            capture_output=True,
            text=True,
            timeout=300,
        )
    except subprocess.TimeoutExpired:
        fail_case("idempotency", "Second ansible-playbook run timed out after 300s")
        return
    except Exception as e:
        fail_case("idempotency", f"Second ansible-playbook run failed: {e}")
        return

    if proc2.returncode != 0:
        fail_case(
            "idempotency",
            f"Second ansible-playbook run failed with exit code {proc2.returncode}",
        )
        return

    # Parse the PLAY RECAP line for changed=0 unreachable=0 failed=0
    stdout = proc2.stdout or ""
    recap_line = ""
    for line in stdout.splitlines():
        if "PLAY RECAP" in line or (
            "changed=" in line and "failed=" in line and "unreachable=" in line
        ):
            recap_line = line.strip()
            break

    print(f"  Second run recap: {recap_line or '(not found in output)'}")

    # Check for 0 changes, 0 failures
    has_zero_changed = "changed=0" in recap_line or "changed=0" in stdout
    has_zero_failed = "failed=0" in recap_line or "failed=0" in stdout
    has_zero_unreachable = "unreachable=0" in recap_line or "unreachable=0" in stdout

    if not has_zero_changed:
        fail_case(
            "idempotency", "Second run reported non-zero changes — not idempotent"
        )
        return

    if not has_zero_failed:
        fail_case("idempotency", "Second run reported failures")
        return

    detail_parts = ["0 changes"]
    if has_zero_failed:
        detail_parts.append("0 failures")
    if has_zero_unreachable:
        detail_parts.append("0 unreachable")

    pass_case("idempotency", "Ansible idempotent: " + ", ".join(detail_parts))


def case_no_open_relay(args: argparse.Namespace) -> None:
    """Port 25 must reject relay to non-local address admin@ta.nasa (SMTP-02 regression)."""
    domain = args.domain
    non_local_rcpt = "admin@ta.nasa"

    try:
        with smtplib.SMTP(args.smtp_host, 25, timeout=args.timeout) as smtp:
            smtp.ehlo()
            try:
                smtp.sendmail(f"sender@{domain}", [non_local_rcpt], "relay test\r\n")
                fail_case(
                    "no-open-relay", f"Port 25 accepted relay to {non_local_rcpt}"
                )
                return
            except smtplib.SMTPRecipientsRefused:
                pass
            except smtplib.SMTPDataError:
                pass
    except Exception as e:
        fail_case("no-open-relay", f"SMTP connection error: {e}")
        return

    pass_case("no-open-relay", f"Port 25 correctly rejected relay to {non_local_rcpt}")


def case_ldap_gated(args: argparse.Namespace) -> None:
    """Report LDAP-tagged checks as explicitly skipped (D-16)."""
    ldap_cases = [
        ("ldap-auth", "gated for Phase 07 / HW1-3 LDAP"),
        ("ldap-list-members", "gated for Phase 07 / HW1-3 LDAP"),
    ]
    for case_name, reason in ldap_cases:
        skip_case(case_name, reason)


# ---------------------------------------------------------------------------
# Case dispatch
# ---------------------------------------------------------------------------

CASES = {
    # Phase verifiers
    "phase03": case_phase03,
    "phase04": case_phase04,
    "phase05": case_phase05,
    "phase06": case_phase06,
    # Smoke-gate-specific
    "dns-regression": case_dns_regression,
    "idempotency": case_idempotency,
    "no-open-relay": case_no_open_relay,
    "ldap-gated": case_ldap_gated,
    # Meta
    "all": None,
    "quick": None,
    "full": None,
    "phases-only": None,
    "idempotency-only": None,
}


def run_case(case_name: str, args: argparse.Namespace) -> None:
    """Run a single named case. Meta-cases dispatch to multiple sub-cases."""
    # Meta-case: all (everything except idempotency — it's slow)
    if case_name == "all":
        for name in [
            "phase03",
            "phase04",
            "phase05",
            "phase06",
            "dns-regression",
            "no-open-relay",
            "ldap-gated",
        ]:
            run_case(name, args)
        return

    # Meta-case: quick (phase verifiers only, no smoke checks)
    if case_name == "quick":
        for name in ["phase03", "phase04", "phase05", "phase06"]:
            run_case(name, args)
        return

    # Meta-case: full (everything including idempotency)
    if case_name == "full":
        for name in [
            "phase03",
            "phase04",
            "phase05",
            "phase06",
            "dns-regression",
            "no-open-relay",
            "ldap-gated",
            "idempotency",
        ]:
            run_case(name, args)
        return

    # Meta-case: phases-only (all phase verifiers)
    if case_name == "phases-only":
        for name in ["phase03", "phase04", "phase05", "phase06"]:
            run_case(name, args)
        return

    # Meta-case: idempotency-only
    if case_name == "idempotency-only":
        run_case("idempotency", args)
        return

    # Skip checks
    if case_name == "idempotency" and args.skip_idempotency:
        skip_case("idempotency", "skipped by --skip-idempotency flag")
        return

    if case_name == "dns-regression" and args.skip_dns_regression:
        skip_case("dns-regression", "skipped by --skip-dns-regression flag")
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
        description="Full non-LDAP HW1-2 smoke gate verification wrapper. "
        "Runs all mail phase verifiers plus DNS regression, "
        "idempotency, no-open-relay, and LDAP-gated checks."
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
        required=True,
        help="Password for admin user",
    )
    parser.add_argument(
        "--test-password",
        required=True,
        help="Password for test user",
    )
    parser.add_argument(
        "--ssh-host",
        required=True,
        help="SSH target for remote probes (e.g. dmz-client-01)",
    )
    parser.add_argument(
        "--api-host",
        default=None,
        help="API server hostname for Phase 05 HTTP probes (default: same as smtp-host)",
    )
    parser.add_argument(
        "--api-port",
        type=int,
        default=8000,
        help="API server port (default: 8000)",
    )
    parser.add_argument(
        "--case",
        default="all",
        choices=["all", "quick", "full", "phases-only", "idempotency-only"],
        help="Test case set to run. "
        "'all' = phases + smoke (no idempotency), "
        "'quick' = phases only, "
        "'full' = everything including idempotency, "
        "'phases-only' = phase verifiers only, "
        "'idempotency-only' = idempotency check only "
        "(default: all)",
    )
    parser.add_argument(
        "--skip-idempotency",
        action="store_true",
        help="Skip the slow idempotency check (ansible-playbook x2)",
    )
    parser.add_argument(
        "--skip-dns-regression",
        action="store_true",
        help="Skip DNS regression checks",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=15,
        help="Socket timeout in seconds for SMTP/SSH (default: 15)",
    )
    parser.add_argument(
        "--dkim-selector",
        default="2026-na",
        help="DKIM selector for DNS regression (default: 2026-na)",
    )

    args_raw = parser.parse_args()

    # Default api-host to smtp-host if not provided
    if not args_raw.api_host:
        args_raw.api_host = args_raw.smtp_host

    # Default api-host for subprocess args
    args = args_raw

    print("=== Full Non-LDAP HW1-2 Smoke Gate ===")
    print(f"SMTP: {args.smtp_host}  IMAP: {args.imap_host}")
    print(f"Domain: {args.domain}  Mail domain: {args.mail_domain}")
    print(f"SSH host: {args.ssh_host}")
    print(f"API host: {args.api_host}:{args.api_port}")
    print(f"DKIM selector: {args.dkim_selector}")
    print(f"Case: {args.case}")
    print(f"Skip idempotency: {args.skip_idempotency}")
    print(f"Skip DNS regression: {args.skip_dns_regression}")
    print()

    run_case(args.case, args)

    # Print summary
    print()
    print("=== Full Non-LDAP HW1-2 Smoke Gate Summary ===")
    passed = sum(1 for _, ok, _ in results if ok is True)
    failed = sum(1 for _, ok, _ in results if ok is False)
    skipped = sum(1 for _, ok, _ in results if ok is None)
    for name, ok, detail in results:
        if ok is True:
            status = "PASS"
        elif ok is False:
            status = f"FAIL ({detail})"
        else:
            status = f"SKIP ({detail})"
        print(f"  {name}: {status}")
    print(f"\n{passed} passed, {failed} failed, {skipped} skipped")

    sys.exit(1 if failed > 0 else 0)


if __name__ == "__main__":
    main()
