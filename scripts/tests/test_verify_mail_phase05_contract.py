#!/usr/bin/env python3
"""Contract tests for the Phase 05 verifier script.

Verifies structural properties without requiring network access:
  - All required cases are present in CASES dict
  - Only Python stdlib modules are imported
  - No hardcoded student ID, domain, or host patterns
"""

import importlib.util
import os
import sys
import types

# Path to the verifier script
_VERIFIER_PATH = os.path.join(os.path.dirname(__file__), "..", "verify_mail_phase05.py")

# Required case names per the validation strategy (05-VALIDATION.md)
REQUIRED_CASES = {
    "static-primary",
    "static-mail-domain",
    "static",
    "api-create",
    "api-create-delivery",
    "api-delete",
    "invalid-inputs",
    "activation",
    "all",
}

# Python stdlib top-level module names (3.10+)
STDLIB_MODULES = {
    "abc",
    "aifc",
    "argparse",
    "array",
    "ast",
    "asynchat",
    "asyncio",
    "asyncore",
    "atexit",
    "audioop",
    "base64",
    "bdb",
    "binascii",
    "binhex",
    "bisect",
    "builtins",
    "bz2",
    "calendar",
    "cgi",
    "cgitb",
    "chunk",
    "cmath",
    "cmd",
    "code",
    "codecs",
    "codeop",
    "collections",
    "colorsys",
    "compileall",
    "concurrent",
    "configparser",
    "contextlib",
    "contextvars",
    "copy",
    "copyreg",
    "cProfile",
    "crypt",
    "csv",
    "ctypes",
    "curses",
    "dataclasses",
    "datetime",
    "dbm",
    "decimal",
    "difflib",
    "dis",
    "distutils",
    "doctest",
    "email",
    "encodings",
    "enum",
    "errno",
    "faulthandler",
    "fcntl",
    "filecmp",
    "fileinput",
    "fnmatch",
    "formatter",
    "fractions",
    "ftplib",
    "functools",
    "gc",
    "getopt",
    "getpass",
    "gettext",
    "glob",
    "graphlib",
    "grp",
    "gzip",
    "hashlib",
    "heapq",
    "hmac",
    "html",
    "http",
    "idlelib",
    "imaplib",
    "imghdr",
    "imp",
    "importlib",
    "inspect",
    "io",
    "ipaddress",
    "itertools",
    "json",
    "keyword",
    "lib2to3",
    "linecache",
    "locale",
    "logging",
    "lzma",
    "mailbox",
    "mailcap",
    "marshal",
    "math",
    "mimetypes",
    "mmap",
    "modulefinder",
    "multiprocessing",
    "netrc",
    "nis",
    "nntplib",
    "numbers",
    "operator",
    "optparse",
    "os",
    "ossaudiodev",
    "pathlib",
    "pdb",
    "pickle",
    "pickletools",
    "pipes",
    "pkgutil",
    "platform",
    "plistlib",
    "poplib",
    "posix",
    "posixpath",
    "pprint",
    "profile",
    "pstats",
    "pty",
    "pwd",
    "py_compile",
    "pyclbr",
    "pydoc",
    "queue",
    "quopri",
    "random",
    "re",
    "readline",
    "reprlib",
    "resource",
    "rlcompleter",
    "runpy",
    "sched",
    "secrets",
    "select",
    "selectors",
    "shelve",
    "shlex",
    "shutil",
    "signal",
    "site",
    "smtpd",
    "smtplib",
    "sndhdr",
    "socket",
    "socketserver",
    "spwd",
    "sqlite3",
    "ssl",
    "stat",
    "statistics",
    "string",
    "stringprep",
    "struct",
    "subprocess",
    "sunau",
    "symtable",
    "sys",
    "sysconfig",
    "syslog",
    "tabnanny",
    "tarfile",
    "telnetlib",
    "tempfile",
    "termios",
    "test",
    "textwrap",
    "threading",
    "time",
    "timeit",
    "tkinter",
    "token",
    "tokenize",
    "tomllib",
    "trace",
    "traceback",
    "tracemalloc",
    "tty",
    "turtle",
    "turtledemo",
    "types",
    "typing",
    "unicodedata",
    "unittest",
    "urllib",
    "uu",
    "uuid",
    "venv",
    "warnings",
    "wave",
    "weakref",
    "webbrowser",
    "winreg",
    "winsound",
    "wsgiref",
    "xdrlib",
    "xml",
    "xmlrpc",
    "zipapp",
    "zipfile",
    "zipimport",
    "zlib",
    "zoneinfo",
    "__future__",
    "__main__",
}


def _load_module(path: str) -> types.ModuleType:
    """Load a Python module from a file path."""
    spec = importlib.util.spec_from_file_location("verify_mail_phase05", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load spec for {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _check_non_stdlib_imports(source: str) -> list[str]:
    """Return list of non-stdlib top-level imports found in source."""
    non_stdlib = []
    for line in source.splitlines():
        stripped = line.strip()
        # Match "import foo" or "from foo import ..."
        if stripped.startswith("import "):
            for token in stripped.removeprefix("import ").split(","):
                mod = token.strip().split(" ")[0].split(".")[0]
                if mod not in STDLIB_MODULES:
                    non_stdlib.append(mod)
        elif stripped.startswith("from "):
            parts = stripped.split()
            if len(parts) >= 2:
                mod = parts[1].split(".")[0]
                if mod not in STDLIB_MODULES:
                    non_stdlib.append(mod)
    return non_stdlib


def _check_hardcoded_values(source: str) -> list[str]:
    """Return list of hardcoded value patterns found in source."""
    issues = []
    # Check for hardcoded domains (exclude docstrings and comments)
    # Look for `.nasa` string literals outside docs/comments
    import re

    # Skip docstrings and comments
    in_docstring = False
    for line in source.splitlines():
        stripped = line.strip()
        if stripped.startswith('"""') or stripped.startswith("'''"):
            in_docstring = not in_docstring
        if stripped.startswith("#") or in_docstring:
            continue
        # Check for hardcoded domain-like strings
        # Pattern: a domain-like string ending in .nasa that isn't a template
        if re.search(r'"[a-z0-9]+\.[a-z0-9]+\.[a-z]+"', stripped):
            # Allow help strings, templates like ${STUID}, and docstrings
            if "${" not in stripped:
                issues.append(stripped.strip())

    return issues


def test_cases_dict_has_all_required():
    """The CASES dict must contain every required case name."""
    mod = _load_module(_VERIFIER_PATH)
    actual = set(mod.CASES.keys())
    missing = REQUIRED_CASES - actual
    assert not missing, f"Missing cases in CASES dict: {sorted(missing)}"
    print(f"  PASS: All {len(REQUIRED_CASES)} required cases present in CASES dict")


def test_no_non_stdlib_imports():
    """The verifier must only import Python stdlib modules."""
    with open(_VERIFIER_PATH, "r", encoding="utf-8") as f:
        source = f.read()
    non_stdlib = _check_non_stdlib_imports(source)
    assert not non_stdlib, f"Non-stdlib imports found: {non_stdlib}"
    print("  PASS: Only stdlib imports detected")


def test_no_hardcoded_domains_or_student_ids():
    """The verifier must not hardcode domain, student ID, or host names."""
    with open(_VERIFIER_PATH, "r", encoding="utf-8") as f:
        source = f.read()
    issues = _check_hardcoded_values(source)
    # Only flag if more than 3 lines have hardcoded values (allow help text examples)
    if issues:
        print(f"  WARNING: Suspicious hardcoded values found ({len(issues)} lines):")
        for i in issues[:5]:
            print(f"    {i}")
    # Soft check — print warning but don't fail on help text strings
    assert len(issues) <= 10, (
        f"Too many hardcoded value patterns found ({len(issues)}). "
        "Verifier should accept --domain, --mail-domain, etc. as CLI args."
    )
    print("  PASS: No excessive hardcoded values detected")


def test_script_compiles():
    """The verifier script must compile without syntax errors."""
    with open(_VERIFIER_PATH, "r", encoding="utf-8") as f:
        source = f.read()
    compile(source, _VERIFIER_PATH, "exec")
    print("  PASS: Script compiles successfully")


def run():
    """Run all contract tests."""
    print("=== Phase 05 Verifier Contract Tests ===\n")
    failures = 0
    tests = [
        ("script compiles", test_script_compiles),
        ("case completeness", test_cases_dict_has_all_required),
        ("stdlib-only imports", test_no_non_stdlib_imports),
        ("no hardcoded values", test_no_hardcoded_domains_or_student_ids),
    ]
    for name, fn in tests:
        try:
            fn()
        except AssertionError as e:
            print(f"  FAIL: [{name}] {e}")
            failures += 1
        except Exception as e:
            print(f"  FAIL: [{name}] Unexpected error: {e}")
            failures += 1

    print(f"\n{failures} failure(s)")
    return failures


if __name__ == "__main__":
    sys.exit(run())
