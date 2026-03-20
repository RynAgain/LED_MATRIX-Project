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

    def fetch_remote(self):
        """
        Fetch latest changes from remote without applying them.

        Returns:
            True if fetch succeeded, False otherwise.
        """
        logger.info("Fetching remote changes...")
        result = self._run_git(["fetch", "origin", self.branch])
        if result and result.returncode == 0:
            logger.info("Fetch completed successfully")
            return True
        else:
            error = result.stderr.strip() if result else "git not available"
            logger.error("Fetch failed: %s", error)
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

    def pull_updates(self):
        """
        Pull latest changes from remote.
        Stashes any local changes first, then pulls, then pops stash.

        Returns:
            True if pull succeeded, False otherwise.
        """
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
        Install/update Python dependencies from requirements.txt.

        Returns:
            True if installation succeeded, False otherwise.
        """
        req_path = os.path.join(self.project_root, "requirements.txt")
        if not os.path.exists(req_path):
            logger.warning("requirements.txt not found, skipping dependency install")
            return True

        logger.info("Installing dependencies from requirements.txt...")
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", "-r", req_path, "--quiet"],
                cwd=self.project_root,
                capture_output=True,
                text=True,
                timeout=300
            )
            if result.returncode == 0:
                logger.info("Dependencies installed successfully")
                return True
            else:
                logger.error("Dependency install failed: %s", result.stderr.strip())
                return False
        except subprocess.TimeoutExpired:
            logger.error("Dependency installation timed out")
            return False

    def restart_display_service(self):
        """
        Restart the LED matrix display service via systemd.

        Returns:
            True if restart command succeeded, False otherwise.
        """
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
                return True
            else:
                logger.error("Service restart failed: %s", result.stderr.strip())
                return False
        except (FileNotFoundError, subprocess.TimeoutExpired) as e:
            logger.error("Could not restart service: %s", e)
            return False

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
