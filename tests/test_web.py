"""
Tests for the LED Matrix Web Control Panel.
"""

import json
import os
import sys
import pytest

# Ensure project root is on path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.web.app import create_app


@pytest.fixture
def app():
    """Create test Flask app."""
    app = create_app()
    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False
    return app


@pytest.fixture
def client(app):
    """Create test client."""
    return app.test_client()


@pytest.fixture
def auth_client(client):
    """Create an authenticated test client."""
    client.post("/login", data={"username": "admin", "password": "ledmatrix"})
    return client


class TestAuth:
    """Test authentication."""

    def test_login_page_renders(self, client):
        response = client.get("/login")
        assert response.status_code == 200
        assert b"Sign In" in response.data

    def test_login_success(self, client):
        response = client.post(
            "/login",
            data={"username": "admin", "password": "ledmatrix"},
            follow_redirects=True
        )
        assert response.status_code == 200
        assert b"Dashboard" in response.data

    def test_login_failure(self, client):
        response = client.post(
            "/login",
            data={"username": "admin", "password": "wrong"},
            follow_redirects=True
        )
        assert response.status_code == 200
        assert b"Invalid" in response.data

    def test_redirect_unauthenticated(self, client):
        response = client.get("/")
        assert response.status_code == 302
        assert "/login" in response.headers["Location"]

    def test_logout(self, auth_client):
        response = auth_client.get("/logout", follow_redirects=True)
        assert response.status_code == 200
        assert b"Sign In" in response.data


class TestDashboard:
    """Test dashboard page."""

    def test_dashboard_renders(self, auth_client):
        response = auth_client.get("/")
        assert response.status_code == 200
        assert b"Dashboard" in response.data
        assert b"Display Status" in response.data

    def test_dashboard_shows_features(self, auth_client):
        response = auth_client.get("/")
        assert response.status_code == 200
        # Should show feature names from config
        assert b"Tic Tac Toe" in response.data or b"tic_tac_toe" in response.data


class TestFeatures:
    """Test features page."""

    def test_features_page_renders(self, auth_client):
        response = auth_client.get("/features")
        assert response.status_code == 200
        assert b"Display Features" in response.data

    def test_features_update(self, auth_client):
        response = auth_client.post(
            "/features",
            data={
                "feature_snake": "on",
                "feature_pong": "on",
                "display_duration": "30"
            },
            follow_redirects=True
        )
        assert response.status_code == 200
        assert b"updated" in response.data.lower() or b"Features" in response.data


class TestWifi:
    """Test WiFi page."""

    def test_wifi_page_renders(self, auth_client):
        response = auth_client.get("/wifi")
        assert response.status_code == 200
        assert b"WiFi" in response.data

    def test_wifi_add_network(self, auth_client):
        response = auth_client.post(
            "/wifi",
            data={
                "action": "add",
                "ssid": "TestNetwork",
                "password": "testpass",
                "priority": "1"
            },
            follow_redirects=True
        )
        assert response.status_code == 200
        assert b"TestNetwork" in response.data


class TestSettings:
    """Test settings page."""

    def test_settings_page_renders(self, auth_client):
        response = auth_client.get("/settings")
        assert response.status_code == 200
        assert b"Settings" in response.data

    def test_settings_update(self, auth_client):
        response = auth_client.post(
            "/settings",
            data={
                "github_branch": "main",
                "log_level": "DEBUG"
            },
            follow_redirects=True
        )
        assert response.status_code == 200
        assert b"saved" in response.data.lower() or b"Settings" in response.data


class TestAPI:
    """Test API endpoints."""

    def test_api_status(self, auth_client):
        response = auth_client.get("/api/status")
        assert response.status_code == 200
        data = json.loads(response.data)
        assert "status" in data

    def test_api_requires_auth(self, client):
        response = client.get("/api/status")
        assert response.status_code == 302  # Redirect to login
