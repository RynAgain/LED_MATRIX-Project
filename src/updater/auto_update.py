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

logger = logging.getLogger(__name__)

# Project root is three levels up from this file
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


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
        If fetch fails due to corrupt objects, attempts automatic repair.

        Returns:
            True if fetch succeeded, False otherwise.
        """
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
        """Backup config/*.json before git pull to prevent data loss."""
        import shutil
        config_dir = os.path.join(self.project_root, "config")
        backup_dir = os.path.join(self.project_root, "config", ".backup")
        os.makedirs(backup_dir, exist_ok=True)

        backed_up = 0
        for filename in os.listdir(config_dir):
            if filename.endswith(".json"):
                src = os.path.join(config_dir, filename)
                dst = os.path.join(backup_dir, filename + ".bak")
                try:
                    shutil.copy2(src, dst)
                    backed_up += 1
                except OSError as e:
                    logger.warning("Could not backup %s: %s", filename, e)

        if backed_up:
            logger.info("Backed up %d config files to config/.backup/", backed_up)

    def pull_updates(self):
        """
        Pull latest changes from remote.
        Backs up config files, stashes any local changes, then pulls, then pops stash.

        Returns:
            True if pull succeeded, False otherwise.
        """
        # Backup configs before pull
        self._backup_configs()

        # Stash any local changes (e.g., config edits)
        logger.info("Stashing local changes...")
        self._run_git(["stash", "push", "-m", "auto-update-stash"])

        # Pull changes
        logger.info("Pulling updates from origin/%s...", self.branch)
        result = self._run_git(["pull", "origin", self.branch, "--ff-only"])

        if result and result.returncode == 0:
            logger.info("Pull completed: %s", result.stdout.strip())

            # Try to restore stashed changes
            stash_result = self._run_git(["stash", "pop"])
            if stash_result and stash_result.returncode != 0:
                # Stash pop failed (conflict) or no stash exists
                if "No stash entries found" not in (stash_result.stderr or ""):
                    logger.warning("Stash pop had conflicts, dropping stash: %s", stash_result.stderr.strip())
                    self._run_git(["stash", "drop"])

            return True
        else:
            error = result.stderr.strip() if result else "git not available"
            logger.error("Pull failed: %s", error)

            # Restore stash even on failure
            self._run_git(["stash", "pop"])
            return False

    def install_dependencies(self):
        """
        Install/upgrade Python dependencies from requirements.txt.

        Uses --upgrade to ensure outdated packages are updated, not just
        missing ones installed. Falls back to installing without --upgrade
        if the first attempt fails (e.g., GitHub source for yt-dlp is
        unreachable). After installation, verifies critical imports.

        Returns:
            True if installation succeeded, False otherwise.
        """
        req_path = os.path.join(self.project_root, "requirements.txt")
        if not os.path.exists(req_path):
            logger.warning("requirements.txt not found, skipping dependency install")
            return True

        logger.info("Upgrading dependencies from requirements.txt...")
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
            logger.error("Dependency installation timed out")

        # Verify critical dependencies are importable
        self._verify_dependencies()

        return success

    def _verify_dependencies(self):
        """Check that critical Python packages are importable.

        Logs warnings for any missing packages so operators can see
        exactly what needs manual attention. Attempts to install missing
        critical packages individually as a last resort.
        """
        critical = {
            "flask": "Flask",
            "flask_sock": "flask-sock",
            "requests": "requests",
            "PIL": "Pillow",
            "psutil": "psutil",
            "qrcode": "qrcode",
        }
        optional = {
            "cv2": "opencv-python-headless",
            "numpy": "numpy",
            "yt_dlp": "yt-dlp @ https://github.com/yt-dlp/yt-dlp/archive/master.tar.gz",
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

    def restart_display_service(self):
        """
        Restart the LED matrix display and web services via systemd.

        Returns:
            True if restart commands succeeded, False otherwise.
        """
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

        # Restart web panel service (picks up new routes/templates)
        logger.info("Restarting led-matrix-web service...")
        try:
            result = subprocess.run(
                ["sudo", "systemctl", "restart", "led-matrix-web.service"],
                capture_output=True,
                text=True,
                timeout=30
            )
            if result.returncode == 0:
                logger.info("Web service restarted successfully")
            else:
                logger.error("Web service restart failed: %s", result.stderr.strip())
                success = False
        except (FileNotFoundError, subprocess.TimeoutExpired) as e:
            logger.error("Could not restart web service: %s", e)
            success = False

        return success

    def check_and_update(self):
        """
        Main update workflow: fetch, check, pull, install deps, restart.

        Returns:
            True if an update was applied, False if no update or failure.
        """
        logger.info("Starting update check...")

        # Step 1: Fetch
        if not self.fetch_remote():
            logger.error("Update check failed at fetch stage")
            return False

        # Step 2: Check for updates
        if not self.has_updates():
            logger.info("No updates available")
            return False

        # Step 3: Pull
        if not self.pull_updates():
            logger.error("Update check failed at pull stage")
            return False

        # Step 4: Install dependencies
        self.install_dependencies()

        # Step 5: Restart display service
        self.restart_display_service()

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
