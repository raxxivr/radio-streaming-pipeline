import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent

PIPELINE_STEPS = [
    ("1. EXTRACT DATA", [sys.executable, "-u", "-m", "scripts.extract"]),
    ("2. TRANSFORM & LOAD DATA", [sys.executable, "-u", "-m", "scripts.load"]),
    ("3. RUN ANALYTICS", [sys.executable, "-u", "-m", "scripts.run_analytics"]),
    ("4. RUN TESTS", [sys.executable, "-u", "-m", "pytest", "-q"]),
]


def run_pipeline():
    print("=" * 60, flush=True)
    print("STARTING RADIO STREAMING DATA PIPELINE", flush=True)
    print("=" * 60, flush=True)

    for step_title, command in PIPELINE_STEPS:
        print(f"\n>>> {step_title}", flush=True)
        print(f"Executing: {' '.join(command[1:])}", flush=True)
        print("-" * 40, flush=True)

        result = subprocess.run(command, cwd=REPO_ROOT)

        if result.returncode != 0:
            print("\n" + "=" * 60, flush=True)
            print(f"PIPELINE EXECUTION FAILED AT STEP: {step_title}", flush=True)
            print(f"Command exited with code {result.returncode}.", flush=True)
            print("=" * 60, flush=True)
            sys.exit(result.returncode)

    print("\n" + "=" * 60, flush=True)
    print("SUCCESS: PIPELINE AND TESTS COMPLETED!", flush=True)
    print("=" * 60, flush=True)


if __name__ == "__main__":
    run_pipeline()
