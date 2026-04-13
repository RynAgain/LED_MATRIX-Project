#!/usr/bin/env python3
"""
WiFi connection manager for Raspberry Pi.
Uses nmcli (NetworkManager) to manage WiFi connections.
Supports open/public WiFi networks and WPA/WPA2 secured networks.
"""

import json
import subprocess
import time
import logging
import urllib.request
import os

logger = logging.getLogger(__name__)


class WiFiManager:
    """Manages WiFi connections on Raspberry Pi using NetworkManager (nmcli)."""

    def __init__(self, config_path=None):
        """
        Initialize WiFiManager with configuration.

        Args:
            config_path: Path to wifi.json config file. 
                         Defaults to config/wifi.json relative to project root.
        """
        if config_path is None:
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            config_path = os.path.join(project_root, "config", "wifi.json")

        self.config_path = config_path
        self.config = self._load_config()
        self.networks = self.config.get("networks", [])
        self.connection_timeout = self.config.get("connection_timeout", 30)
        self.retry_attempts = self.config.get("retry_attempts", 3)
        self.retry_delay = self.config.get("retry_delay", 10)
        self.check_url = self.config.get("connectivity_check_url", "http://detectportal.firefox.com/success.txt")
        self.check_expected = self.config.get("connectivity_check_expected", "success")

    def _load_config(self):
        """Load WiFi configuration from JSON file."""
        try:
            with open(self.config_path, "r") as f:
                config = json.load(f)
            logger.info("Loaded WiFi config from %s", self.config_path)
            return config
        except FileNotFoundError:
            logger.warning("WiFi config not found at %s, using defaults", self.config_path)
            return {"networks": [], "connection_timeout": 30, "retry_attempts": 3, "retry_delay": 10}
        except json.JSONDecodeError as e:
            logger.error("Invalid JSON in WiFi config: %s", e)
            return {"networks": [], "connection_timeout": 30, "retry_attempts": 3, "retry_delay": 10}

    def _run_nmcli(self, args, timeout=30):
        """
        Run an nmcli command and return the result.

        Args:
            args: List of arguments to pass to nmcli.
            timeout: Command timeout in seconds.

        Returns:
            subprocess.CompletedProcess or None on failure.
        """
        cmd = ["nmcli"] + args
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            return result
        except FileNotFoundError:
            logger.error("nmcli not found. Is NetworkManager installed?")
            return None
        except subprocess.TimeoutExpired:
            logger.error("nmcli command timed out: %s", " ".join(cmd))
            return None

    def is_connected(self):
        """
        Check if currently connected to any WiFi network.

        Returns:
            True if connected to WiFi, False otherwise.
        """
        result = self._run_nmcli(["-t", "-f", "TYPE,STATE", "device"])
        if result and result.returncode == 0:
            for line in result.stdout.strip().split("\n"):
                parts = line.split(":", 1)
                if len(parts) >= 2 and parts[0] == "wifi" and parts[1] == "connected":
                    return True
        return False

    def get_current_ssid(self):
        """
        Get the SSID of the currently connected WiFi network.

        Returns:
            SSID string or None if not connected.
        """
        result = self._run_nmcli(["-t", "-f", "active,ssid", "dev", "wifi"])
        if result and result.returncode == 0:
            for line in result.stdout.strip().split("\n"):
                parts = line.split(":", 1)
                if len(parts) >= 2 and parts[0] == "yes":
                    return parts[1]
        return None

    def scan_networks(self):
        """
        Scan for available WiFi networks.

        Returns:
            List of available SSIDs.
        """
        # Trigger a rescan
        self._run_nmcli(["dev", "wifi", "rescan"])
        time.sleep(2)

        result = self._run_nmcli(["-t", "-f", "SSID,SIGNAL,SECURITY", "dev", "wifi", "list"])
        networks = []
        if result and result.returncode == 0:
            for line in result.stdout.strip().split("\n"):
                parts = line.rsplit(":", 2)
                if len(parts) >= 3 and parts[0]:
                    networks.append({
                        "ssid": parts[0],
                        "signal": int(parts[1]) if parts[1].isdigit() else 0,
                        "security": parts[2]
                    })
        return networks

    def _connection_profile_name(self, ssid):
        """Return a deterministic NM connection profile name for the given SSID."""
        return f"led-matrix-{ssid}"

    def connect_to_network(self, ssid, password="", hidden=False):
        """
        Connect to a specific WiFi network.

        Uses a NetworkManager connection profile so the password is stored in
        NM's secure keyring rather than being persistently visible on the
        command line (e.g. in ``/proc/<pid>/cmdline`` or ``ps aux`` output).

        On the first connection the profile is created with ``nmcli connection add``;
        subsequent connections reuse the existing profile via ``nmcli connection up``.

        Args:
            ssid: Network SSID.
            password: Network password (empty string for open networks).
            hidden: Whether the network is hidden.

        Returns:
            True if connection successful, False otherwise.
        """
        logger.info("Attempting to connect to '%s'...", ssid)

        con_name = self._connection_profile_name(ssid)

        # --- Open (no-password) networks: use the simple one-shot command ---
        if not password:
            args = ["dev", "wifi", "connect", ssid]
            if hidden:
                args.extend(["hidden", "yes"])
            result = self._run_nmcli(args, timeout=self.connection_timeout)
            if result and result.returncode == 0:
                logger.info("Successfully connected to open network '%s'", ssid)
                return True
            error_msg = result.stderr.strip() if result else "nmcli not available"
            logger.warning("Failed to connect to '%s': %s", ssid, error_msg)
            return False

        # --- Secured networks: use a stored connection profile ---
        # Check whether a profile already exists for this SSID.
        check = self._run_nmcli(
            ["-t", "-f", "NAME", "connection", "show"],
            timeout=10,
        )
        profile_exists = False
        if check and check.returncode == 0:
            profile_exists = con_name in check.stdout.strip().split("\n")

        if profile_exists:
            # Update the existing profile's password (in case it changed)
            self._run_nmcli(
                ["connection", "modify", con_name,
                 "wifi-sec.psk", password],
                timeout=10,
            )
        else:
            # Create a new connection profile.  The password is briefly on
            # the command line during ``add`` but is then stored securely
            # inside NetworkManager and never exposed again.
            add_args = [
                "connection", "add",
                "type", "wifi",
                "con-name", con_name,
                "ssid", ssid,
                "wifi-sec.key-mgmt", "wpa-psk",
                "wifi-sec.psk", password,
            ]
            if hidden:
                add_args.extend(["802-11-wireless.hidden", "yes"])

            add_result = self._run_nmcli(add_args, timeout=self.connection_timeout)
            if not add_result or add_result.returncode != 0:
                error_msg = add_result.stderr.strip() if add_result else "nmcli not available"
                logger.warning("Failed to create connection profile for '%s': %s",
                               ssid, error_msg)
                return False
            logger.info("Created NM connection profile '%s'", con_name)

        # Activate the profile (password is NOT on the command line here)
        up_result = self._run_nmcli(
            ["connection", "up", con_name],
            timeout=self.connection_timeout,
        )

        if up_result and up_result.returncode == 0:
            logger.info("Successfully connected to '%s'", ssid)
            return True

        error_msg = up_result.stderr.strip() if up_result else "nmcli not available"
        logger.warning("Failed to activate connection '%s': %s", con_name, error_msg)
        return False

    def check_internet_connectivity(self):
        """
        Verify actual internet connectivity by making an HTTP request.

        Returns:
            True if internet is reachable, False otherwise.
        """
        try:
            response = urllib.request.urlopen(self.check_url, timeout=10)
            content = response.read().decode("utf-8").strip()
            if self.check_expected in content:
                logger.debug("Internet connectivity confirmed")
                return True
            else:
                logger.warning("Connectivity check returned unexpected content: %s", content[:100])
                portal = self.detect_captive_portal()
                if portal['detected']:
                    portal_url = portal['portal_url'] or 'unknown'
                    logger.warning(
                        "Connected to WiFi but behind a captive portal at %s. Manual login may be required.",
                        portal_url
                    )
                return False
        except Exception as e:
            logger.debug("No internet connectivity: %s", e)
            portal = self.detect_captive_portal()
            if portal['detected']:
                portal_url = portal['portal_url'] or 'unknown'
                logger.warning(
                    "Connected to WiFi but behind a captive portal at %s. Manual login may be required.",
                    portal_url
                )
            return False

    def detect_captive_portal(self):
        """
        Detect if the current network has a captive portal.

        Returns:
            dict with keys:
                - 'detected': bool - True if captive portal detected
                - 'portal_url': str or None - URL of the portal if detected
                - 'message': str - Human-readable status
        """
        import urllib.request
        import urllib.error

        result = {
            'detected': False,
            'portal_url': None,
            'message': 'No captive portal detected'
        }

        try:
            # Use a custom opener that does NOT follow redirects
            class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
                def redirect_request(self, req, fp, code, msg, headers, newurl):
                    raise urllib.error.HTTPError(
                        req.full_url, code, msg, headers, fp
                    )

            opener = urllib.request.build_opener(NoRedirectHandler)
            request = urllib.request.Request(
                self.check_url,
                headers={'User-Agent': 'CaptivePortalDetect/1.0'}
            )

            response = opener.open(request, timeout=10)
            content = response.read().decode('utf-8', errors='replace').strip()

            if self.check_expected in content:
                # Got expected content - no captive portal
                result['message'] = 'Internet access confirmed, no captive portal'
            else:
                # Got unexpected content - likely captive portal serving custom page
                result['detected'] = True
                result['message'] = 'Captive portal detected: unexpected response content'
                logger.warning("Captive portal detected: response content does not match expected")

        except urllib.error.HTTPError as e:
            if e.code in (301, 302, 303, 307, 308):
                # Redirect detected - this is a captive portal
                portal_url = e.headers.get('Location', 'unknown')
                result['detected'] = True
                result['portal_url'] = portal_url
                result['message'] = f'Captive portal detected: redirect to {portal_url}'
                logger.warning("Captive portal detected: redirect to %s", portal_url)
            else:
                result['message'] = f'HTTP error {e.code} during portal check'
                logger.debug("HTTP error during captive portal check: %s", e)
        except Exception as e:
            result['message'] = f'Portal check failed: {e}'
            logger.debug("Captive portal check failed: %s", e)

        return result

    def ensure_connection(self):
        """
        Main method: ensure WiFi is connected with internet access.
        Tries configured networks in priority order with retry logic.

        Returns:
            True if connected with internet access, False if all attempts failed.
        """
        # Check if already connected with internet
        if self.is_connected() and self.check_internet_connectivity():
            current = self.get_current_ssid()
            logger.info("Already connected to '%s' with internet access", current)
            return True

        # Sort networks by priority (lower number = higher priority)
        sorted_networks = sorted(self.networks, key=lambda n: n.get("priority", 99))

        if not sorted_networks:
            logger.warning("No WiFi networks configured in %s", self.config_path)
            return False

        # Scan for available networks
        available = self.scan_networks()
        available_ssids = {n["ssid"] for n in available}

        for network in sorted_networks:
            ssid = network.get("ssid", "")
            password = network.get("password", "")
            hidden = network.get("hidden", False)

            if not ssid:
                continue

            # Skip networks that aren't available (unless hidden)
            if not hidden and ssid not in available_ssids:
                logger.info("Network '%s' not in range, skipping", ssid)
                continue

            # Try connecting with retries
            for attempt in range(1, self.retry_attempts + 1):
                logger.info("Connection attempt %d/%d for '%s'", attempt, self.retry_attempts, ssid)

                if self.connect_to_network(ssid, password, hidden):
                    # Wait a moment for connection to stabilize
                    time.sleep(3)

                    if self.check_internet_connectivity():
                        logger.info("Connected to '%s' with internet access", ssid)
                        return True
                    else:
                        logger.warning("Connected to '%s' but no internet access", ssid)
                        portal = self.detect_captive_portal()
                        if portal['detected']:
                            portal_url = portal['portal_url'] or 'unknown'
                            logger.warning(
                                "Connected to WiFi but behind a captive portal at %s. Manual login may be required.",
                                portal_url
                            )

                if attempt < self.retry_attempts:
                    logger.info("Retrying in %d seconds...", self.retry_delay)
                    time.sleep(self.retry_delay)

        logger.error("Failed to connect to any configured WiFi network")
        return False

    def disconnect(self):
        """Disconnect from current WiFi network."""
        result = self._run_nmcli(["dev", "disconnect", "wlan0"])
        if result and result.returncode == 0:
            logger.info("Disconnected from WiFi")
            return True
        return False


def main():
    """CLI entry point for testing WiFi connectivity."""
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )

    manager = WiFiManager()

    if len(sys.argv) > 1:
        command = sys.argv[1]
        if command == "status":
            connected = manager.is_connected()
            ssid = manager.get_current_ssid()
            internet = manager.check_internet_connectivity()
            print(f"WiFi Connected: {connected}")
            print(f"Current SSID:   {ssid or 'N/A'}")
            print(f"Internet:       {internet}")
        elif command == "scan":
            networks = manager.scan_networks()
            print("Available networks:")
            for net in networks:
                print(f"  {net['ssid']:30s} Signal: {net['signal']}%  Security: {net['security']}")
        elif command == "connect":
            success = manager.ensure_connection()
            sys.exit(0 if success else 1)
        elif command == "disconnect":
            manager.disconnect()
        elif command == "portal":
            portal = manager.detect_captive_portal()
            print(f"Captive Portal: {portal['detected']}")
            if portal['portal_url']:
                print(f"Portal URL:     {portal['portal_url']}")
            print(f"Details:        {portal['message']}")
        else:
            print(f"Unknown command: {command}")
            print("Usage: python -m src.wifi.manager [status|scan|connect|disconnect|portal]")
            sys.exit(1)
    else:
        # Default: ensure connection
        success = manager.ensure_connection()
        sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
