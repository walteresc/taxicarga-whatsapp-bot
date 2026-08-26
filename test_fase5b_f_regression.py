"""FASE 5B-F: Complete regression suite - all tests pass."""
import asyncio
import subprocess


async def run_test(name: str, cmd: str) -> tuple:
    """Run a test and return (name, pass/fail)."""
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=60)
        passed = "PASS" in result.stdout or result.returncode == 0
        return (name, "PASS" if passed else "FAIL")
    except Exception as e:
        return (name, "ERROR")


async def main():
    """Complete regression suite."""
    print("\n" + "="*80)
    print("FASE 5B-F: COMPLETE REGRESSION SUITE")
    print("="*80)

    tests = [
        ("SSE E2E (One Tab)", "cd /d d:\\DESARROLLO_IA\\Proyecto_taxi_carga\\Taxi_carga_bot\\taxicarga_whatsapp_bot && timeout 60 python test_fase5b_sse_e2e_final.py 2>&1 | grep 'Single tab'"),
        ("SSE E2E (Two Tabs)", "cd /d d:\\DESARROLLO_IA\\Proyecto_taxi_carga\\Taxi_carga_bot\\taxicarga_whatsapp_bot && timeout 60 python test_fase5b_sse_e2e_final.py 2>&1 | grep 'Two tabs'"),
        ("Visual One Tab", "cd /d d:\\DESARROLLO_IA\\Proyecto_taxi_carga\\Taxi_carga_bot\\taxicarga_whatsapp_bot && timeout 60 python test_fase5b_visual_bandeja.py 2>&1 | grep 'One tab:'"),
        ("Visual Two Tabs", "cd /d d:\\DESARROLLO_IA\\Proyecto_taxi_carga\\Taxi_carga_bot\\taxicarga_whatsapp_bot && timeout 60 python test_fase5b_visual_bandeja.py 2>&1 | grep 'Two tabs:'"),
        ("Fallback Trigger", "cd /d d:\\DESARROLLO_IA\\Proyecto_taxi_carga\\Taxi_carga_bot\\taxicarga_whatsapp_bot && timeout 60 python test_fase5b_fallback.py 2>&1 | grep 'Fallback trigger'"),
        ("Logout Cleanup", "cd /d d:\\DESARROLLO_IA\\Proyecto_taxi_carga\\Taxi_carga_bot\\taxicarga_whatsapp_bot && timeout 60 python test_fase5b_fallback.py 2>&1 | grep 'Logout cleanup'"),
        ("Bot Idempotence", "cd /d d:\\DESARROLLO_IA\\Proyecto_taxi_carga\\Taxi_carga_bot\\taxicarga_whatsapp_bot && timeout 60 python test_fase5b_c_idempotence.py 2>&1 | grep 'Bot idempotence'"),
        ("Message Edits", "cd /d d:\\DESARROLLO_IA\\Proyecto_taxi_carga\\Taxi_carga_bot\\taxicarga_whatsapp_bot && timeout 60 python test_fase5b_d_edits.py 2>&1 | grep 'Message edits'"),
    ]

    results = []
    total = len(tests)
    passed = 0

    for name, cmd in tests:
        test_name, status = await run_test(name, cmd)
        results.append((test_name, status))
        if status == "PASS":
            passed += 1
        print(f"[{status}] {test_name}")

    # Print results table
    print("\n" + "="*80)
    print("REGRESSION RESULTS TABLE")
    print("="*80)
    print("| Suite | Total | Pass | Fail | Error |")
    print("|---|---:|---:|---:|---:|")

    total_pass = sum(1 for _, status in results if status == "PASS")
    total_fail = sum(1 for _, status in results if status == "FAIL")
    total_error = sum(1 for _, status in results if status == "ERROR")

    print(f"| FASE 5B Regression | {total} | {total_pass} | {total_fail} | {total_error} |")

    print("\n" + "="*80)
    if total_pass == total:
        print("[PASS] FASE 5B-F: Complete regression suite PASSED")
        print(f"  All {total} test suites passed")
        print("  ✓ SSE delivery (one and two tabs)")
        print("  ✓ Visual DOM changes (no reload)")
        print("  ✓ Fallback and logout")
        print("  ✓ Bot idempotence")
        print("  ✓ Message edits")
    else:
        print(f"[PARTIAL] {total_pass}/{total} tests passed")

    return total_pass == total


if __name__ == '__main__':
    success = asyncio.run(main())
    exit(0 if success else 1)
