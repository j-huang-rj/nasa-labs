#!/usr/bin/env python3
"""Phase 05 mailing list & HTTP API verification script.

Verifies static list expansion, API create/delete behavior,
invalid-input rejection, and activation safety.

Uses only Python standard library modules.
"""

from __future__ import annotations

import argparse
import sys

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
# Case dispatch
# ---------------------------------------------------------------------------

CASES: dict[str, object] = {
    "all": None,
}


def run_case(case_name: str, args: argparse.Namespace) -> None:
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
        fn(args)  # type: ignore[operator]
    except Exception as e:
        fail_case(case_name, f"Unexpected exception: {e}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Phase 05 mailing lists & HTTP API verification script."
    )
    parser.add_argument(
        "--smtp-host", required=True, help="SMTP server hostname (e.g. smtp.STUID.nasa)"
    )
    parser.add_argument(
        "--imap-host", required=True, help="IMAP server hostname (e.g. imap.STUID.nasa)"
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
        "--domain", required=True, help="Base managed domain (e.g. STUID.nasa)"
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
        help="SSH target for remote probes (e.g. dmz-client-01)",
    )
    parser.add_argument(
        "--case",
        action="append",
        dest="cases",
        choices=list(CASES.keys()),
        help="Test case to run. Specify multiple times or use 'all'.",
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

    print("=== Phase 05 Mailing Lists & HTTP API Verification ===")
    print(f"SMTP: {args.smtp_host}  IMAP: {args.imap_host}")
    print(f"Domain: {args.domain}  Mail domain: {args.mail_domain}")
    print(f"SSH host: {args.ssh_host or '(not set)'}")
    print(f"Cases: {args.cases}")
    print()

    for case_name in args.cases:
        run_case(case_name, args)

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
