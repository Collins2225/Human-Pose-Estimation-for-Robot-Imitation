#!/usr/bin/env python3
"""
================================================================
install_dependencies.py — HRI System Library Installer
================================================================
Run this script ONCE before starting the project.
It installs all required libraries with progress feedback
and verifies each one after installation.

Usage:
    python install_dependencies.py
================================================================
"""

import subprocess
import sys
import importlib


# ── Libraries to install ──────────────────────────────────────
# Format: (pip_package_name, import_name, friendly_name)
LIBRARIES = [
    ("opencv-python",  "cv2",        "OpenCV"),
    ("mediapipe",      "mediapipe",  "MediaPipe"),
    ("pybullet",       "pybullet",   "PyBullet"),
    ("numpy",          "numpy",      "NumPy"),
    ("matplotlib",     "matplotlib", "Matplotlib"),
]


def print_header():
    print("=" * 55)
    print("   HRI System — Dependency Installer")
    print("=" * 55)
    print(f"   Python version: {sys.version.split()[0]}")
    print(f"   Python path:    {sys.executable}")
    print("=" * 55 + "\n")


def check_python_version():
    """MediaPipe requires Python 3.8–3.11."""
    major = sys.version_info.major
    minor = sys.version_info.minor

    if major != 3 or minor < 8 or minor > 11:
        print(f"  WARNING: You are running Python {major}.{minor}")
        print("   MediaPipe officially supports Python 3.8 – 3.11.")
        print("   Proceeding anyway, but you may encounter issues.\n")
    else:
        print(f" Python {major}.{minor} — compatible\n")


def upgrade_pip():
    """Always upgrade pip first to avoid installation issues."""
    print("📦 Step 0: Upgrading pip...")
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "--upgrade", "pip"],
            check=True,
            capture_output=True
        )
        print("   pip upgraded successfully ✓\n")
    except subprocess.CalledProcessError:
        print("   pip upgrade failed (non-critical, continuing...)\n")


def install_library(pip_name: str, friendly_name: str) -> bool:
    """
    Install a single library using pip.

    Returns True if installation succeeded, False otherwise.
    """
    print(f"   Installing {friendly_name}...", end=" ", flush=True)
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", pip_name, "--quiet"],
            check=True,
            capture_output=True
        )
        print("✓")
        return True
    except subprocess.CalledProcessError as e:
        print("✗ FAILED")
        print(f"   Error: {e.stderr.decode().strip()}")
        return False


def verify_import(import_name: str, friendly_name: str) -> bool:
    """
    Verify a library can actually be imported after installation.
    Installation success ≠ import success (e.g., wrong Python version).

    Returns True if import works, False otherwise.
    """
    try:
        mod = importlib.import_module(import_name)

        # Print version if available
        version = getattr(mod, "__version__", "unknown")
        print(f"   {friendly_name:<12} imported  — version {version} ✓")
        return True
    except ImportError as e:
        print(f"   {friendly_name:<12} IMPORT FAILED — {e}")
        return False


def run_installation():
    """Install all libraries and report results."""
    print("📦 Step 1: Installing libraries...\n")

    failed_installs = []
    for pip_name, _, friendly_name in LIBRARIES:
        success = install_library(pip_name, friendly_name)
        if not success:
            failed_installs.append(friendly_name)

    return failed_installs


def run_verification():
    """Verify all libraries import correctly."""
    print("\n🔍 Step 2: Verifying imports...\n")

    failed_imports = []
    for _, import_name, friendly_name in LIBRARIES:
        success = verify_import(import_name, friendly_name)
        if not success:
            failed_imports.append(friendly_name)

    return failed_imports


def print_summary(failed_installs: list, failed_imports: list):
    """Print final summary and next steps."""
    print("\n" + "=" * 55)
    print("   Installation Summary")
    print("=" * 55)

    total = len(LIBRARIES)
    passed = total - len(failed_imports)

    print(f"   {passed}/{total} libraries ready\n")

    if not failed_installs and not failed_imports:
        print("✅ ALL LIBRARIES INSTALLED SUCCESSFULLY!")
        print("\n   You're ready to run the HRI system.")
        print("   Next step → run:  python main.py")

    else:
        if failed_installs:
            print(" Installation failed for:")
            for lib in failed_installs:
                print(f"     - {lib}")

        if failed_imports:
            print("\n Import failed for:")
            for lib in failed_imports:
                print(f"     - {lib}")

        print("\n💡 Troubleshooting tips:")
        print("   1. Make sure you are in the correct virtual environment")
        print("      → source hri_env/bin/activate   (Linux/Mac)")
        print("      → hri_env\\Scripts\\activate      (Windows)")
        print("   2. Try installing manually:")
        print("      → pip install <library-name>")
        print("   3. MediaPipe needs Python 3.8–3.11 (not 3.12+)")
        print("   4. On Linux, you may need:")
        print("      → sudo apt-get install python3-dev libgl1-mesa-glx")

    print("=" * 55)


# ── Entry Point ───────────────────────────────────────────────
if __name__ == "__main__":
    print_header()
    check_python_version()
    upgrade_pip()

    failed_installs = run_installation()
    failed_imports  = run_verification()

    print_summary(failed_installs, failed_imports)