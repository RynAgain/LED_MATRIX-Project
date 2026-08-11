"""Project version derived from git tag, commit hash, or fallback VERSION file."""
import re
import subprocess
import os

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_VERSION_FILE = os.path.join(_PROJECT_ROOT, "VERSION")

# Hardcoded fallback version. Updated at release time or by CI/CD.
_FALLBACK_VERSION = "1.1.0"


_cached_version = None


def get_version() -> str:
    """Return the project version string (cached after first call).

    Resolution order:
    1. Git describe (tag-based, e.g. "v1.2.3" or "v1.2.3-5-gabc1234")
    2. Git short commit hash (e.g. "bd8dfc9")
    3. VERSION file in project root (written during deployment)
    4. Hardcoded fallback constant

    This ensures a version is always available even after `git reset --hard`,
    on deployments that strip the .git directory, or on systems without git.
    """
    global _cached_version
    if _cached_version is not None:
        return _cached_version

    # Try git describe (tag-based version)
    version = _try_git_describe()
    if version:
        _cached_version = version
        return version

    # Try git short hash
    version = _try_git_hash()
    if version:
        _cached_version = version
        return version

    # Try VERSION file (written during deploy/install)
    version = _try_version_file()
    if version:
        _cached_version = version
        return version

    # Ultimate fallback
    _cached_version = _FALLBACK_VERSION
    return _FALLBACK_VERSION


def _describe_to_version(described: str) -> str:
    """Collapse `git describe` output into an auto-bumping version.

    Every commit bumps the visible version with zero release discipline:
    the commits-since-tag count becomes the PATCH number.

        "v1.1.0-18-g95c876a" -> "1.1.18"   (tag patch + 18 commits)
        "v1.1.0"             -> "1.1.0"    (exactly on the tag)
        "95c876a"            -> "95c876a"  (no tag at all: bare hash)

    Tagging a new release (e.g. v1.2.0) resets the count naturally.
    """
    text = described.lstrip("v")
    m = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)(?:-(\d+)-g[0-9a-f]+)?", text)
    if not m:
        return text
    major, minor, patch, commits = m.groups()
    total_patch = int(patch) + int(commits or 0)
    return f"{major}.{minor}.{total_patch}"


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
                return _describe_to_version(tag)
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
