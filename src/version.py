"""Project version derived from git tag, commit hash, or fallback VERSION file."""
import subprocess
import os

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_VERSION_FILE = os.path.join(_PROJECT_ROOT, "VERSION")

# Hardcoded fallback version. Updated at release time or by CI/CD.
_FALLBACK_VERSION = "1.0.0"


def get_version() -> str:
    """Return the project version string.

    Resolution order:
    1. Git describe (tag-based, e.g. "v1.2.3" or "v1.2.3-5-gabc1234")
    2. Git short commit hash (e.g. "bd8dfc9")
    3. VERSION file in project root (written during deployment)
    4. Hardcoded fallback constant

    This ensures a version is always available even after `git reset --hard`,
    on deployments that strip the .git directory, or on systems without git.
    """
    # Try git describe (tag-based version)
    version = _try_git_describe()
    if version:
        return version

    # Try git short hash
    version = _try_git_hash()
    if version:
        return version

    # Try VERSION file (written during deploy/install)
    version = _try_version_file()
    if version:
        return version

    # Ultimate fallback
    return _FALLBACK_VERSION


def _try_git_describe() -> str:
    """Try `git describe --tags --always` for a tag-based version."""
    try:
        result = subprocess.run(
            ["git", "describe", "--tags", "--always"],
            capture_output=True, text=True, timeout=5,
            cwd=_PROJECT_ROOT
        )
        if result.returncode == 0:
            tag = result.stdout.strip()
            if tag:
                # Strip leading 'v' prefix if present for cleaner display
                return tag.lstrip("v") if tag.startswith("v") else tag
    except Exception:
        pass
    return ""


def _try_git_hash() -> str:
    """Try `git rev-parse --short HEAD` for the commit hash."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=5,
            cwd=_PROJECT_ROOT
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return ""


def _try_version_file() -> str:
    """Try reading a VERSION file from the project root."""
    try:
        with open(_VERSION_FILE, "r", encoding="utf-8") as f:
            version = f.read().strip()
            if version:
                return version
    except (FileNotFoundError, OSError):
        pass
    return ""
