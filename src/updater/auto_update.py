#!/usr/bin/env python3
"""
Auto-update system for LED Matrix Project.
Checks GitHub for changes and updates the local installation.
Designed to run as a separate systemd service/timer.
"""

import json
import subprocess
import logging
import os
import sys
import time

logger = logging.getLogger(__name__)

# Project root is three levels up from this file
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Failure counter file path
FAILURE_COUNTER_FILE = os.path.join(PROJECT_ROOT, ".update_failures")


class AutoUpdater:
    """Handles checking for and applying updates from GitHub."""

    def __init__(self, config_path=None):
        """
        Initialize AutoUpdater.

        Args:
            config_path: Path to config.json. Defaults to config/config.json in project root.
        """
        if config_path is None:
            config_path = os.path.join(PROJECT_ROOT, "config", "config.json")

        self.config_path = config_path
        self.project_root = PROJECT_ROOT
        self.config = self._load_config()
        self.branch = self.config.get("github_branch", "main")

    def _load_config(self):
        """Load configuration from JSON file."""
        try:
            with open(self.config_path, "r") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.warning("Could not load config: %s. Using defaults.", e)
            return {"github_branch": "main", "update_interval": 1800}

    def _run_git(self, args, timeout=60):
        """
        Run a git command in the project root.

        Args:
            args: List of git arguments.
            timeout: Command timeout in seconds.

        Returns:
            subprocess.CompletedProcess or None on failure.
        """
        cmd = ["git"] + args
        try:
            result = subprocess.run(
                cmd,
                cwd=self.project_root,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            return result
        except FileNotFoundError:
            logger.error("git not found. Is git installed?")
            return None
        except subprocess.TimeoutExpired:
            logger.error("git command timed out: %s", " ".join(cmd))
            return None

    def _clean_git_lock(self):
        """Remove stale .git/index.lock files older than 10 minutes.

        A stale lock file can permanently block all git operations if a
        previous git process was killed (e.g., due to power loss or OOM).
        """
        lock_file = os.path.join(self.project_root, ".git", "index.lock")
        if not os.path.exists(lock_file):
            return

        try:
            lock_age = time.time() - os.path.getmtime(lock_file)
            if lock_age > 600:  # 10 minutes
                os.remove(lock_file)
                logger.warning("Removed stale git lock file (age: %.0fs)", lock_age)
            else:
                logger.info("Git lock file exists but is recent (age: %.0fs), leaving it", lock_age)
        except OSError as e:
            logger.warning("Could not check/remove git lock file: %s", e)

    def _get_failure_count(self):
        """Read the consecutive failure counter from disk.

        Returns:
            Integer count of consecutive failures.
        """
        try:
            with open(FAILURE_COUNTER_FILE, "r") as f:
                return int(f.read().strip())
        except (FileNotFoundError, ValueError):
            return 0

    def _set_failure_count(self, count):
        """Write the consecutive failure counter to disk.

        Args:
            count: Integer failure count to persist.
        """
        try:
            with open(FAILURE_COUNTER_FILE, "w") as f:
                f.write(str(count))
        except OSError as e:
            logger.warning("Could not write failure counter: %s", e)

    def _clear_failure_count(self):
        """Reset the failure counter to zero (on successful update)."""
        try:
            if os.path.exists(FAILURE_COUNTER_FILE):
                os.remove(FAILURE_COUNTER_FILE)
        except OSError:
            pass

    def _increment_failure_count(self):
        """Increment and return the new failure count."""
        count = self._get_failure_count() + 1
        self._set_failure_count(count)
        logger.warning("Consecutive update failures: %d", count)
        return count

    def _nuclear_recovery(self):
        """Perform a nuclear recovery: fetch and hard reset to remote branch.

        This is the last resort when normal pull/reset strategies have failed
        repeatedly. It guarantees the local repo matches the remote exactly.

        Returns:
            True if recovery succeeded, False otherwise.
        """
        logger.warning("NUCLEAR RECOVERY: Performing full fetch + hard reset...")

        # Force remove lock file regardless of age
        lock_file = os.path.join(self.project_root, ".git", "index.lock")
        if os.path.exists(lock_file):
            try:
                os.remove(lock_file)
                logger.warning("Removed git lock file during nuclear recovery")
            except OSError:
                pass

        result = self._run_git(["fetch", "origin", self.branch, "--force"], timeout=120)
        if not result or result.returncode != 0:
            logger.error("Nuclear recovery fetch failed: %s",
                         result.stderr.strip() if result else "git not available")
            return False

        result = self._run_git(["reset", "--hard", f"origin/{self.branch}"])
        if result and result.returncode == 0:
            logger.info("Nuclear recovery succeeded: reset to origin/%s", self.branch)
            return True
        else:
            logger.error("Nuclear recovery reset failed: %s",
                         result.stderr.strip() if result else "git not available")
            return False

    def _repair_git(self):
        """Attempt to repair a corrupted git repository.

        Fixes corrupt loose objects by running fsck + prune, then
        re-fetching from the remote. This handles the common case where
        a power loss corrupts .git/objects/ files.

        Returns:
            True if repair succeeded, False otherwise.
        """
        logger.warning("Attempting git repository repair...")

        # Remove corrupt loose objects
        self._run_git(["prune"])
        self._run_git(["gc", "--auto"])

        # If that's not enough, do a more aggressive repair
        result = self._run_git(["fsck", "--no-dangling"], timeout=120)
        if result and result.returncode != 0:
            logger.warning("fsck found issues: %s", result.stderr.strip()[:500])
            # Nuclear option: re-fetch all objects from remote
            logger.warning("Re-fetching all objects from remote...")
            self._run_git(["fetch", "--all", "--prune"], timeout=120)

        # Verify we can read HEAD now
        result = self._run_git(["rev-parse", "HEAD"])
        if result and result.returncode == 0:
            logger.info("Git repository repair succeeded")
            return True
        else:
            logger.error("Git repository repair failed. Manual intervention needed: "
                         "cd %s && rm -rf .git && git clone <url> .", self.project_root)
            return False

    def fetch_remote(self):
        """
        Fetch latest changes from remote without applying them.
        Cleans stale git lock files before fetching.
        If fetch fails due to corrupt objects, attempts automatic repair.

        Returns:
            True if fetch succeeded, False otherwise.
        """
        # Clean stale lock files before any git operations
        self._clean_git_lock()

        logger.info("Fetching remote changes...")
        result = self._run_git(["fetch", "origin", self.branch])
        if result and result.returncode == 0:
            logger.info("Fetch completed successfully")
            return True

        error = result.stderr.strip() if result else "git not available"
        logger.error("Fetch failed: %s", error)

        # Detect corrupt git objects and attempt repair
        if result and ("corrupt" in error.lower() or "inflate" in error.lower()
                       or "unable to unpack" in error.lower()):
            logger.warning("Corrupt git objects detected, attempting repair...")
            if self._repair_git():
                # Retry fetch after repair
                result = self._run_git(["fetch", "origin", self.branch])
                if result and result.returncode == 0:
                    logger.info("Fetch succeeded after repair")
                    return True

        return False

    def has_updates(self):
        """
        Check if there are new commits on the remote branch.

        Returns:
            True if remote has new commits, False otherwise.
        """
        # Get local HEAD
        local = self._run_git(["rev-parse", "HEAD"])
        if not local or local.returncode != 0:
            logger.error("Could not get local HEAD")
            return False

        # Get remote HEAD
        remote = self._run_git(["rev-parse", f"origin/{self.branch}"])
        if not remote or remote.returncode != 0:
            logger.error("Could not get remote HEAD for origin/%s", self.branch)
            return False

        local_hash = local.stdout.strip()
        remote_hash = remote.stdout.strip()

        if local_hash != remote_hash:
            logger.info("Update available: local=%s remote=%s", local_hash[:8], remote_hash[:8])
            return True
        else:
            logger.info("Already up to date: %s", local_hash[:8])
            return False

    def _backup_configs(self):
        """Backup config/*.json to a temp directory outside git's reach.

        Returns the temp directory path so pull_updates() can restore from it,
        completely bypassing git merge logic for config files.
        """
        import shutil
        import tempfile
        config_dir = os.path.join(self.project_root, "config")

        # Also keep the in-tree .backup/ for manual recovery
        backup_dir = os.path.join(config_dir, ".backup")
        os.makedirs(backup_dir, exist_ok=True)

        # Create a temp directory outside the repo for safe restoration
        tmp_dir = tempfile.mkdtemp(prefix="ledmatrix-config-")

        backed_up = 0
        for filename in os.listdir(config_dir):
            if filename.endswith(".json"):
                src = os.path.join(config_dir, filename)
                try:
                    shutil.copy2(src, os.path.join(backup_dir, filename + ".bak"))
                    shutil.copy2(src, os.path.join(tmp_dir, filename))
                    backed_up += 1
                except OSError as e:
                    logger.warning("Could not backup %s: %s", filename, e)

        if backed_up:
            logger.info("Backed up %d config files to %s", backed_up, tmp_dir)

        return tmp_dir

    def _restore_configs(self, tmp_dir):
        """Restore config/*.json from the temp backup directory.

        This overwrites whatever git merge produced (including conflict markers)
        with the user's original local config files.

        Args:
            tmp_dir: Path to temp directory containing the pre-pull config files.
        """
        import shutil
        config_dir = os.path.join(self.project_root, "config")
        restored = 0

        if not os.path.isdir(tmp_dir):
            logger.warning("Config backup dir %s missing, cannot restore", tmp_dir)
            return

        for filename in os.listdir(tmp_dir):
            if filename.endswith(".json"):
                src = os.path.join(tmp_dir, filename)
                dst = os.path.join(config_dir, filename)
                try:
                    shutil.copy2(src, dst)
                    restored += 1
                except OSError as e:
                    logger.warning("Could not restore %s: %s", filename, e)

        if restored:
            logger.info("Restored %d config files from pre-pull backup", restored)

        # Clean up temp directory
        try:
            shutil.rmtree(tmp_dir)
        except OSError:
            pass

    @staticmethod
    def _has_conflict_markers(filepath):
        """Check if a file contains git merge conflict markers."""
        try:
            with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            return "<<<<<<< " in content or ">>>>>>> " in content
        except OSError:
            return False

    def pull_updates(self):
        """
        Apply latest changes from remote to the working tree.

        Strategy:
        1. Backup config/*.json to a temp dir (user customizations)
        2. git reset --hard origin/{branch} (guaranteed clean sync)
        3. Restore config files from backup (preserves user settings)

        We intentionally do NOT use git pull or stash -- hard reset is
        deterministic and cannot fail due to merge conflicts, diverged
        branches, or modified tracked files. This matches the update.sh
        approach and eliminates the most common failure modes.

        Returns:
            True if update succeeded, False otherwise.
        """
        # Backup configs to temp dir BEFORE any git operations
        config_tmp = self._backup_configs()

        # Hard reset to remote -- guaranteed to sync regardless of local state
        logger.info("Resetting to origin/%s (hard reset)...", self.branch)
        result = self._run_git(["reset", "--hard", f"origin/{self.branch}"])

        if result and result.returncode == 0:
            logger.info("Reset succeeded: now at origin/%s", self.branch)

            # Clean untracked files that might conflict, but preserve user dirs
            clean_result = self._run_git([
                "clean", "-fd",
                "--exclude=config/",
                "--exclude=logs/",
                "--exclude=venv/",
                "--exclude=downloaded_videos/",
                "--exclude=.update_failures",
            ])
            if clean_result and clean_result.returncode == 0:
                logger.debug("Cleaned untracked files")

            # Restore config files from pre-reset backup
            # This preserves user's carousel toggles, API keys, WiFi config, etc.
            self._restore_configs(config_tmp)
            return True
        else:
            error = result.stderr.strip() if result else "git not available"
            logger.error("Hard reset failed: %s", error)

            # Last resort: try removing index and retrying
            logger.warning("Attempting index removal recovery...")
            lock_file = os.path.join(self.project_root, ".git", "index.lock")
            index_file = os.path.join(self.project_root, ".git", "index")
            for f in [lock_file, index_file]:
                if os.path.exists(f):
                    try:
                        os.remove(f)
                    except OSError:
                        pass

            # Retry reset
            result = self._run_git(["reset", "--hard", f"origin/{self.branch}"])
            if result and result.returncode == 0:
                logger.info("Recovery reset succeeded")
                self._restore_configs(config_tmp)
                return True

            # Truly failed -- clean up temp dir
            logger.error("All reset attempts failed. Manual intervention required.")
            import shutil
            try:
                shutil.rmtree(config_tmp)
            except OSError:
                pass
            return False

    def install_dependencies(self):
        """
        Install/upgrade Python dependencies from requirements.txt.

        Uses --upgrade to ensure outdated packages are updated, not just
        missing ones installed. Falls back to installing without --upgrade
        if the first attempt fails (e.g., GitHub source for yt-dlp is
        unreachable). After installation, verifies critical imports.

        This method is designed to never crash the updater — all exceptions
        are caught and logged so the service restart can still proceed.

        Returns:
            True if installation succeeded, False otherwise.
        """
        req_path = os.path.join(self.project_root, "requirements.txt")
        if not os.path.exists(req_path):
            logger.warning("requirements.txt not found, skipping dependency install")
            return True

        logger.info("Installing/upgrading dependencies from requirements.txt...")
        success = False
        try:
            # First pass: install with --upgrade to catch outdated packages
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", "--upgrade",
                 "-r", req_path, "--quiet"],
                cwd=self.project_root,
                capture_output=True,
                text=True,
                timeout=300
            )
            if result.returncode == 0:
                logger.info("Dependencies upgraded successfully")
                success = True
            else:
                logger.warning("Dependency upgrade failed: %s", result.stderr.strip()[:500])
                # Fallback: install without --upgrade (satisfies missing deps only)
                logger.info("Retrying without --upgrade...")
                result = subprocess.run(
                    [sys.executable, "-m", "pip", "install",
                     "-r", req_path, "--quiet"],
                    cwd=self.project_root,
                    capture_output=True,
                    text=True,
                    timeout=300
                )
                if result.returncode == 0:
                    logger.info("Dependencies installed (without upgrade)")
                    success = True
                else:
                    logger.error("Dependency install also failed: %s",
                                 result.stderr.strip()[:500])
        except subprocess.TimeoutExpired:
            logger.error("Dependency installation timed out (300s limit)")
        except Exception as e:
            logger.error("Unexpected error during dependency installation: %s", e)

        # Verify critical dependencies are importable regardless of pip outcome
        self._verify_dependencies()

        return success

    def _verify_dependencies(self):
        """Check that critical Python packages are importable.

        Logs warnings for any missing packages so operators can see
        exactly what needs manual attention. Attempts to install missing
        critical packages individually as a last resort.
        """
        critical = {
            "requests": "requests",
            "PIL": "Pillow",
            "psutil": "psutil",
            "qrcode": "qrcode",
            "pygame": "pygame",
        }
        optional = {
            "cv2": "opencv-python-headless",
            "numpy": "numpy",
            "yt_dlp": "yt-dlp @ https://github.com/yt-dlp/yt-dlp/archive/refs/tags/2025.03.31.tar.gz",
        }

        for module, package in critical.items():
            try:
                __import__(module)
            except ImportError:
                logger.warning("Critical dependency missing: %s (pip install %s)", module, package)
                self._pip_install_single(package)

        for module, package in optional.items():
            try:
                __import__(module)
            except ImportError:
                logger.info("Optional dependency not available: %s", module)

    def _pip_install_single(self, package):
        """Attempt to install a single package as a last-resort fix."""
        logger.info("Attempting to install: %s", package)
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", "--quiet", package],
                capture_output=True, text=True, timeout=120
            )
            if result.returncode == 0:
                logger.info("Installed %s successfully", package)
            else:
                logger.error("Failed to install %s: %s", package,
                             result.stderr.strip()[:200])
        except subprocess.TimeoutExpired:
            logger.error("Timed out installing %s", package)

    def _reinstall_service_files(self):
        """Re-install systemd service files from the repo if they've changed.

        Copies service/timer files to /etc/systemd/system/ with path
        substitution for the actual project root and current user.
        This ensures service file updates in the repo take effect.
        """
        import getpass
        import shutil

        services_dir = os.path.join(self.project_root, "services")
        if not os.path.isdir(services_dir):
            return

        actual_user = os.environ.get("USER", getpass.getuser())
        service_files = [
            "led-matrix.service",
            "led-matrix-updater.service",
            "led-matrix-updater.timer",
        ]

        for svc_file in service_files:
            src_path = os.path.join(services_dir, svc_file)
            dst_path = f"/etc/systemd/system/{svc_file}"

            if not os.path.exists(src_path):
                continue

            try:
                # Read template
                with open(src_path, "r") as f:
                    content = f.read()

                # Substitute paths and user
                content = content.replace("/home/ryn/LED_MATRIX-Project", self.project_root)
                content = content.replace("User=ryn", f"User={actual_user}")
                content = content.replace("Group=ryn", f"Group={actual_user}")

                # Check if it differs from installed version
                try:
                    with open(dst_path, "r") as f:
                        current = f.read()
                    if current == content:
                        continue  # No change needed
                except (FileNotFoundError, PermissionError):
                    pass

                # Write updated service file
                with open(dst_path, "w") as f:
                    f.write(content)
                logger.info("Updated service file: %s", svc_file)

            except PermissionError:
                # Try with sudo
                try:
                    proc = subprocess.run(
                        ["sudo", "cp", src_path, dst_path],
                        capture_output=True, text=True, timeout=10
                    )
                    if proc.returncode == 0:
                        # Apply sed substitutions via sudo
                        subprocess.run(
                            ["sudo", "sed", "-i",
                             f"s|/home/ryn/LED_MATRIX-Project|{self.project_root}|g",
                             dst_path],
                            capture_output=True, text=True, timeout=10
                        )
                        subprocess.run(
                            ["sudo", "sed", "-i",
                             f"s|User=ryn|User={actual_user}|g",
                             dst_path],
                            capture_output=True, text=True, timeout=10
                        )
                        subprocess.run(
                            ["sudo", "sed", "-i",
                             f"s|Group=ryn|Group={actual_user}|g",
                             dst_path],
                            capture_output=True, text=True, timeout=10
                        )
                        logger.info("Updated service file (via sudo): %s", svc_file)
                except Exception as e:
                    logger.warning("Could not update service file %s: %s", svc_file, e)
            except Exception as e:
                logger.warning("Could not update service file %s: %s", svc_file, e)

        # Reload systemd daemon to pick up changes
        try:
            subprocess.run(
                ["sudo", "systemctl", "daemon-reload"],
                capture_output=True, text=True, timeout=15
            )
            logger.info("Systemd daemon reloaded")
        except Exception as e:
            logger.warning("Could not reload systemd daemon: %s", e)

    def restart_display_service(self):
        """
        Restart the LED matrix display service via systemd.
        Also re-installs service files if they've changed.

        Returns:
            True if restart commands succeeded, False otherwise.
        """
        # Re-install service files first (picks up path/user changes)
        self._reinstall_service_files()

        success = True

        # Restart display service
        logger.info("Restarting led-matrix display service...")
        try:
            result = subprocess.run(
                ["sudo", "systemctl", "restart", "led-matrix.service"],
                capture_output=True,
                text=True,
                timeout=30
            )
            if result.returncode == 0:
                logger.info("Display service restarted successfully")
            else:
                logger.error("Display service restart failed: %s", result.stderr.strip())
                success = False
        except (FileNotFoundError, subprocess.TimeoutExpired) as e:
            logger.error("Could not restart display service: %s", e)
            success = False

        return success

    def _clean_old_stashes(self):
        """Drop any legacy stashes left from the old stash-based update strategy.

        The current update strategy uses hard reset + config backup/restore,
        so stashes are never created. This cleans up any that exist from before.
        """
        result = self._run_git(["stash", "list"])
        if not result or result.returncode != 0:
            return

        stash_lines = [line for line in result.stdout.strip().split("\n") if line]
        if stash_lines:
            logger.info("Clearing %d legacy stashes...", len(stash_lines))
            self._run_git(["stash", "clear"])
            logger.info("Legacy stashes cleared")

    def check_and_update(self):
        """
        Main update workflow: fetch, check, pull, install deps, restart.
        Includes failure counting with nuclear recovery for persistent failures.

        Returns:
            True if an update was applied, False if no update or failure.
        """
        logger.info("Starting update check...")

        # Check failure counter for nuclear recovery thresholds
        failure_count = self._get_failure_count()
        if failure_count >= 20:
            # After 20 failures, force-remove lock file and try nuclear recovery
            logger.warning("20+ consecutive failures detected, forcing lock removal + nuclear recovery")
            lock_file = os.path.join(self.project_root, ".git", "index.lock")
            if os.path.exists(lock_file):
                try:
                    os.remove(lock_file)
                    logger.warning("Force-removed git lock file after 20 failures")
                except OSError:
                    pass
            if self._nuclear_recovery():
                self._clear_failure_count()
                self.install_dependencies()
                self.restart_display_service()
                logger.info("Nuclear recovery (20+ failures) applied successfully")
                self._clean_old_stashes()
                return True
            else:
                self._increment_failure_count()
                return False
        elif failure_count >= 10:
            # After 10 failures, try nuclear recovery (fetch + hard reset)
            logger.warning("10+ consecutive failures detected, attempting nuclear recovery")
            if self._nuclear_recovery():
                self._clear_failure_count()
                self.install_dependencies()
                self.restart_display_service()
                logger.info("Nuclear recovery (10+ failures) applied successfully")
                self._clean_old_stashes()
                return True
            else:
                self._increment_failure_count()
                return False

        # Step 1: Fetch
        if not self.fetch_remote():
            logger.error("Update check failed at fetch stage")
            self._increment_failure_count()
            return False

        # Step 2: Check for updates
        if not self.has_updates():
            logger.info("No updates available")
            # No update needed is not a failure — clear counter
            self._clear_failure_count()
            return False

        # Step 3: Pull
        if not self.pull_updates():
            logger.error("Update check failed at pull stage")
            self._increment_failure_count()
            return False

        # Step 4: Install dependencies
        self.install_dependencies()

        # Step 5: Restart display service
        self.restart_display_service()

        # Success — clear failure counter and clean stashes
        self._clear_failure_count()
        self._clean_old_stashes()

        logger.info("Update applied successfully")
        return True


def main():
    """CLI entry point for the auto-updater."""
    # Ensure logs directory exists BEFORE setting up file handler
    os.makedirs(os.path.join(PROJECT_ROOT, "logs"), exist_ok=True)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(
                os.path.join(PROJECT_ROOT, "logs", "updater.log"),
                mode="a"
            )
        ]
    )

    updater = AutoUpdater()

    if len(sys.argv) > 1:
        command = sys.argv[1]
        if command == "check":
            updater.fetch_remote()
            has = updater.has_updates()
            print(f"Updates available: {has}")
            sys.exit(0 if not has else 2)
        elif command == "update":
            updated = updater.check_and_update()
            sys.exit(0 if updated else 1)
        else:
            print(f"Unknown command: {command}")
            print("Usage: python -m src.updater.auto_update [check|update]")
            sys.exit(1)
    else:
        # Default: check and update
        updated = updater.check_and_update()
        sys.exit(0 if updated else 1)


if __name__ == "__main__":
    main()
