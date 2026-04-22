#!/usr/bin/env python3
"""Test runner for Dema API tests.

Runs all tests, captures logs, and generates a detailed report with
pass/fail results and failure details for debugging.

Usage:
    python run_tests.py                  # Run all tests
    python run_tests.py --verbose        # Verbose output
    python run_tests.py --tests-only     # Only print the report, no extra logging
"""
import sys
import os
import time
import json
import subprocess
import argparse
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent
VENV_PYTHON = PROJECT_ROOT / ".venv" / "bin" / "python"
VENV_PIP = PROJECT_ROOT / ".venv" / "bin" / "pip"
TEST_DIR = PROJECT_ROOT / "tests"

# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def run_pytest(args, verbose=False):
    """Run pytest and return (returncode, stdout, stderr)."""
    cmd = [
        str(VENV_PYTHON), "-m", "pytest",
        str(TEST_DIR / "test_api.py"),
        "-v",
        "--tb=long",
        "--no-header",
        "--capture=no",
    ] + args

    print(f"$ {' '.join(cmd)}\n")
    result = subprocess.run(
        cmd,
        cwd=str(PROJECT_ROOT),
        capture_output=False,
        text=True,
    )
    return result.returncode


def run_pytest_junit(args):
    """Run pytest with JUnit XML output, return (returncode, xml_path)."""
    xml_path = PROJECT_ROOT / "test-results.xml"
    report_path = PROJECT_ROOT / "test-report.json"

    cmd = [
        str(VENV_PYTHON), "-m", "pytest",
        str(TEST_DIR / "test_api.py"),
        "-v",
        "--tb=long",
        "--junitxml", str(xml_path),
        "--json-report",
        "--json-report-file", str(report_path),
        "--json-report-omit=collectors,errors,tests",
    ] + args

    result = subprocess.run(
        cmd,
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
    )
    return result.returncode, xml_path, report_path


def generate_text_report(xml_path, report_path, output_path):
    """Generate a human-readable text report from JUnit XML and JSON report."""
    lines = []
    timestamp = datetime.now().isoformat()

    lines.append("=" * 80)
    lines.append("DEMA API TEST REPORT")
    lines.append(f"Generated: {timestamp}")
    lines.append("=" * 80)
    lines.append("")

    # Parse JUnit XML
    try:
        import xml.etree.ElementTree as ET
        tree = ET.parse(str(xml_path))
        root = tree.getroot()

        total = int(root.attrib.get("tests", 0))
        errors = int(root.attrib.get("errors", 0))
        failures = int(root.attrib.get("failures", 0))
        skipped = int(root.attrib.get("skipped", 0))
        passed = total - errors - failures - skipped

        lines.append(f"SUMMARY: {total} tests | {passed} passed | {failures} failed | {errors} errors | {skipped} skipped")
        lines.append("")

        # Group by class
        classes = {}
        for testcase in root.findall("testcase"):
            classname = testcase.attrib.get("classname", "Unknown")
            name = testcase.attrib.get("name", "Unknown")
            status = "PASS"

            failure = testcase.find("failure")
            error = testcase.find("error")
            skipped_el = testcase.find("skipped")

            if failure is not None:
                status = "FAIL"
                message = failure.attrib.get("message", "")
                detail = failure.text or ""
                lines.append(f"  FAIL: {classname}.{name}")
                lines.append(f"    Message: {message}")
                lines.append(f"    Details:\n{detail}")
                lines.append("")
            elif error is not None:
                status = "ERROR"
                message = error.attrib.get("message", "")
                detail = error.text or ""
                lines.append(f"  ERROR: {classname}.{name}")
                lines.append(f"    Message: {message}")
                lines.append(f"    Details:\n{detail}")
                lines.append("")
            elif skipped_el is not None:
                status = "SKIP"

            if classname not in classes:
                classes[classname] = {"pass": 0, "fail": 0, "error": 0, "skip": 0}
            classes[classname][status.lower()] += 1

        lines.append("-" * 80)
        lines.append("RESULTS BY TEST CLASS")
        lines.append("-" * 80)
        for cls_name, counts in sorted(classes.items()):
            cls_total = sum(counts.values())
            lines.append(f"  {cls_name}: {cls_total} tests | {counts['pass']} passed | {counts['fail']} failed | {counts['error']} errors | {counts['skip']} skipped")
        lines.append("")

    except Exception as e:
        lines.append(f"Warning: Could not parse JUnit XML: {e}")

    # Parse JSON report if available
    try:
        with open(report_path) as f:
            report = json.load(f)

        duration = report.get("summary", {}).get("duration", 0)
        lines.append(f"Total duration: {duration:.2f}s")
        lines.append("")

        # List all test durations
        lines.append("-" * 80)
        lines.append("TEST DURATIONS")
        lines.append("-" * 80)
        for test in report.get("tests", []):
            nodeid = test.get("nodeid", "")
            duration_s = test.get("duration", 0)
            outcome = test.get("outcome", "")
            lines.append(f"  [{outcome:>5}] {nodeid}  ({duration_s*1000:.1f}ms)")
        lines.append("")

    except Exception as e:
        lines.append(f"Warning: Could not parse JSON report: {e}")

    # Final verdict
    lines.append("=" * 80)
    if failures == 0 and errors == 0:
        lines.append("VERDICT: ALL TESTS PASSED")
    else:
        lines.append(f"VERDICT: {failures} failure(s) and {errors} error(s) detected")
        lines.append("See detailed logs above for debugging information.")
    lines.append("=" * 80)

    report_text = "\n".join(lines)

    with open(output_path, "w") as f:
        f.write(report_text)

    return report_text


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Run Dema API tests and generate report")
    parser.add_argument("--verbose", action="store_true", help="Verbose output")
    parser.add_argument("--no-report", action="store_true", help="Skip report generation")
    parser.add_argument("--output", default="test-report.txt", help="Report output file")
    args = parser.parse_args()

    print("=" * 80)
    print("DEMA API TEST SUITE")
    print("=" * 80)
    print()

    # Ensure pytest-json-report is available
    try:
        subprocess.run(
            [str(VENV_PIP), "install", "pytest-json-report", "-q"],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
        )
    except Exception:
        pass

    # Step 1: Run with JUnit + JSON report
    print("[1/2] Running tests with JUnit XML and JSON report...")
    start = time.time()
    rc, xml_path, report_path = run_pytest_junit([])
    elapsed = time.time() - start

    # Step 2: Run again for verbose output
    print("\n[2/2] Running tests with full output...")
    rc2 = run_pytest([], verbose=args.verbose)

    # Step 3: Generate report
    if not args.no_report:
        print("\nGenerating report...")
        report = generate_text_report(xml_path, report_path, args.output)
        print(f"\nReport written to: {args.output}")
        print()
        # Print the report to stdout as well
        print(report)

    # Return non-zero if any tests failed
    sys.exit(rc or rc2)


if __name__ == "__main__":
    main()
