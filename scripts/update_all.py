"""Run the migrated collectors, or sync their public data without exposing keys."""
import argparse
import datetime as dt
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parent.parent
SOURCES = {"business": "bizzsubsidy", "personal": "personalsubsidy"}
GROUPS = [
    ("business", "bizinfo", "BIZINFO_KEY", ["fetch_bizinfo.py"],
     ["notices.json", "programs.json", "status.json", "seen.json", "details.json"], 2700),
    ("personal", "gov24", "GOV24_KEY", ["fetch_api.py"], ["benefits.json"], 1200),
    ("personal", "bokjiro", "BOKJIRO_KEY", ["fetch_bokjiro.py", "fetch_local.py", "extract_details.py"],
     ["bokjiro.json", "local.json", "details.json"], 1800),
    ("personal", "youth", "YOUTH_KEY", ["fetch_youth.py"], ["youth.json"], 600),
]


def safe_log(value):
    value = str(value)
    for name in ("BIZINFO_KEY", "GOV24_KEY", "ODCLOUD_KEY", "BOKJIRO_KEY", "YOUTH_KEY"):
        secret = os.environ.get(name, "")
        if secret:
            value = value.replace(secret, "[REDACTED]")
    print(value, flush=True)


def run_script(folder, script, timeout):
    try:
        result = subprocess.run(
            [sys.executable, str(ROOT / folder / "scripts" / script)],
            cwd=ROOT / folder, capture_output=True, text=True, timeout=timeout,
        )
        safe_log(result.stdout)
        safe_log(result.stderr)
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        safe_log(f"{folder}/{script}: timed out; previous data retained")
        return False


def mirror(folder, files):
    ok = True
    for filename in files:
        url = f"https://raw.githubusercontent.com/jungs311311/{SOURCES[folder]}/main/data/{filename}"
        target = ROOT / folder / "data" / filename
        for attempt in range(3):
            try:
                request = urllib.request.Request(url, headers={"User-Agent": "subsidy-total-sync"})
                with urllib.request.urlopen(request, timeout=90) as response:
                    payload = response.read()
                json.loads(payload)  # Never replace valid cached data with an error page.
                tmp = target.with_suffix(".json.tmp")
                tmp.write_bytes(payload)
                tmp.replace(target)
                safe_log(f"Synced {folder}/data/{filename}")
                break
            except Exception as exc:
                if attempt == 2:
                    safe_log(f"Sync failed: {folder}/{filename}: {type(exc).__name__}")
                    ok = False
                else:
                    time.sleep(2 ** attempt)
    return ok


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["auto", "api", "mirror"], default="auto")
    args = parser.parse_args()
    os.environ["GOV24_KEY"] = os.environ.get("GOV24_KEY") or os.environ.get("ODCLOUD_KEY", "")
    os.environ["BOKJIRO_KEY"] = os.environ.get("BOKJIRO_KEY") or os.environ.get("GOV24_KEY", "")
    status = {"checked_at": dt.datetime.now(dt.timezone.utc).isoformat(), "mode": args.mode, "sources": {}}
    failures = []
    # Public condition sheets do not need API credentials. Keep prior values on failure.
    for folder, filename in [("business", "sheet.json"), ("personal", "manual.json")]:
        if args.mode == "mirror":
            sheet_ok = mirror(folder, [filename])
        else:
            sheet_ok = run_script(folder, "fetch_sheet.py", 180)
            if not sheet_ok:
                sheet_ok = mirror(folder, [filename])
        status["sources"][folder + "_sheet"] = {"ok": sheet_ok}
        if not sheet_ok:
            failures.append(folder + "_sheet")
    for folder, source, env_name, scripts, files, timeout in GROUPS:
        use_api = args.mode != "mirror" and bool(os.environ.get(env_name, "").strip())
        if args.mode == "api" and not use_api:
            status["sources"][source] = {"ok": False, "method": "missing_key", "required_secret": env_name}
            failures.append(source)
            safe_log(f"{source}: register Actions secret {env_name} before using api mode")
            continue
        api_ok = False
        if use_api:
            api_ok = True
            for script in scripts:
                if not run_script(folder, script, timeout):
                    api_ok = False
                    break
        if api_ok:
            status["sources"][source] = {"ok": True, "method": "api"}
        elif args.mode == "api":
            status["sources"][source] = {"ok": False, "method": "api_failed"}
            failures.append(source)
        else:
            mirror_ok = mirror(folder, files)
            status["sources"][source] = {
                "ok": mirror_ok, "method": "mirror", "reason": "api_failed" if use_api else "no_key"
            }
            if not mirror_ok:
                failures.append(source)
    (ROOT / "data").mkdir(exist_ok=True)
    (ROOT / "data" / "sync-status.json").write_text(
        json.dumps(status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    summary = ["## Subsidy data refresh", "", f"Mode: `{args.mode}`", ""]
    for name, item in status["sources"].items():
        summary.append(f"- {name}: {'OK' if item['ok'] else 'FAILED'} ({item.get('method', 'sheet')})")
    summary.append("\nmirror = public data from the original repositories; api = direct API collection.")
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as stream:
            stream.write("\n".join(summary) + "\n")
    safe_log("\n".join(summary))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
