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


@pytest.fixture(autouse=True)
def _clear_login_attempts():
    """Reset the global rate-limiter state between tests so that failed-login
    counts from one test do not leak into the next."""
    from src.web.app import _login_attempts
    _login_attempts.clear()
    yield
    _login_attempts.clear()


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
        response = auth_client.post("/logout", follow_redirects=True)
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
        assert b"updated" in response.data.lower()


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
        assert b"saved" in response.data.lower()


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


class TestNewPages:
    """Test new web pages."""

    def test_youtube_page(self, auth_client):
        response = auth_client.get("/youtube")
        assert response.status_code == 200

    def test_messages_page(self, auth_client):
        response = auth_client.get("/messages")
        assert response.status_code == 200

    def test_stocks_page(self, auth_client):
        response = auth_client.get("/stocks")
        assert response.status_code == 200

    def test_countdown_page(self, auth_client):
        response = auth_client.get("/countdown")
        assert response.status_code == 200

    def test_qr_page(self, auth_client):
        response = auth_client.get("/qr")
        assert response.status_code == 200

    def test_pixel_editor(self, auth_client):
        response = auth_client.get("/pixel-editor")
        assert response.status_code == 200

    def test_change_password_page(self, auth_client):
        response = auth_client.get("/change-password")
        assert response.status_code == 200


class TestNewAPIs:
    """Test new API endpoints."""

    def test_brightness_api(self, auth_client):
        response = auth_client.post(
            "/api/brightness",
            json={"brightness": 50}
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True

    def test_preview_api(self, auth_client):
        response = auth_client.get("/api/preview")
        assert response.status_code == 200

    def test_countdown_api(self, auth_client):
        response = auth_client.post(
            "/api/countdown",
            json={"seconds": 60, "label": "Test"}
        )
        assert response.status_code == 200

    def test_qr_api(self, auth_client):
        response = auth_client.post(
            "/api/qr",
            json={"content": "https://example.com", "label": "Test"}
        )
        assert response.status_code == 200

    def test_play_video_api(self, auth_client):
        response = auth_client.post(
            "/api/play",
            json={"url": "https://youtube.com/watch?v=test", "title": "Test"}
        )
        assert response.status_code == 200


class TestNewFeatureAPIs:
    """Test newly added feature APIs."""

    def test_reorder_features_api(self, auth_client):
        """Test feature reorder endpoint."""
        response = auth_client.post('/api/reorder-features',
            data=json.dumps({"order": ["snake", "pong", "fire"]}),
            content_type='application/json')
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True

    def test_schedule_settings_with_schedules(self, auth_client):
        """Test saving feature schedules."""
        response = auth_client.post('/settings', data={
            'section': 'schedule',
            'night_enabled': '',
            'night_start': '22',
            'night_end': '7',
            'night_brightness': '20',
            'schedule_count': '1',
            'sched_0_name': 'Test Schedule',
            'sched_0_start': '9',
            'sched_0_end': '17',
            'sched_0_features': ['snake', 'pong'],
        }, follow_redirects=True)
        assert response.status_code == 200

    def test_schedule_delete(self, auth_client):
        """Test deleting a feature schedule."""
        response = auth_client.post('/settings', data={
            'section': 'schedule_delete',
            'index': '0',
        }, follow_redirects=True)
        assert response.status_code == 200

    def test_https_settings(self, auth_client):
        """Test saving HTTPS settings."""
        response = auth_client.post('/settings', data={
            'section': 'https',
            'https_enabled': 'on',
        }, follow_redirects=True)
        assert response.status_code == 200


class TestSecurity:
    """Test security features."""

    def test_rate_limiting(self, client):
        """After 5 failed attempts, should be locked out."""
        for i in range(5):
            client.post("/login", data={"username": "admin", "password": "wrong"})
        
        response = client.post(
            "/login",
            data={"username": "admin", "password": "wrong"},
            follow_redirects=True
        )
        assert b"Too many" in response.data

    def test_password_change_wrong_current(self, client):
        # Log in fresh
        client.post("/login", data={"username": "admin", "password": "ledmatrix"})
        
        response = client.post(
            "/change-password",
            data={
                "current_password": "wrongpassword",
                "new_password": "newpass",
                "confirm_password": "newpass"
            },
            follow_redirects=True
        )
        assert b"incorrect" in response.data.lower()


class TestCSRF:
    """Test CSRF protection."""

    def test_csrf_blocks_post_without_token(self):
        """POST without CSRF token should be rejected when CSRF is enabled."""
        app = create_app()
        app.config["TESTING"] = True
        # Leave WTF_CSRF_ENABLED at default (True)
        client = app.test_client()
        # Log in first (login is exempt from CSRF)
        client.post("/login", data={"username": "admin", "password": "ledmatrix"})
        # Now try a POST to features without CSRF token
        response = client.post(
            "/features",
            data={"display_duration": "30"},
        )
        assert response.status_code == 403

    def test_csrf_allows_post_with_valid_token(self):
        """POST with valid CSRF token should succeed."""
        app = create_app()
        app.config["TESTING"] = True
        client = app.test_client()
        # Log in
        client.post("/login", data={"username": "admin", "password": "ledmatrix"})
        # GET the features page to generate a CSRF token in the session
        response = client.get("/features")
        assert response.status_code == 200
        # Extract the CSRF token from the rendered HTML
        import re
        match = re.search(
            rb'name="_csrf_token"\s+value="([^"]+)"', response.data
        )
        assert match, "CSRF token not found in rendered form"
        csrf_token = match.group(1).decode()
        # POST with the token
        response = client.post(
            "/features",
            data={"display_duration": "30", "_csrf_token": csrf_token},
            follow_redirects=True,
        )
        assert response.status_code == 200

    def test_csrf_skips_json_api(self):
        """JSON API endpoints should not require CSRF tokens."""
        app = create_app()
        app.config["TESTING"] = True
        client = app.test_client()
        client.post("/login", data={"username": "admin", "password": "ledmatrix"})
        response = client.post(
            "/api/brightness",
            json={"brightness": 50},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True

    def test_csrf_skips_login(self):
        """Login POST should not require CSRF token."""
        app = create_app()
        app.config["TESTING"] = True
        client = app.test_client()
        response = client.post(
            "/login",
            data={"username": "admin", "password": "ledmatrix"},
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert b"Dashboard" in response.data


class TestSecretKeyAndPasswordMigration:
    """Test auto-generation and migration features."""

    def test_hash_password_format(self):
        """Hashed passwords should use salt:hash format."""
        from src.web.app import _hash_password, _verify_password
        hashed = _hash_password("testpass")
        assert ":" in hashed
        assert len(hashed) > 40
        assert _verify_password("testpass", hashed)
        assert not _verify_password("wrongpass", hashed)

    def test_plaintext_password_still_works_after_migration(self):
        """After migration, the original plaintext password should verify."""
        from src.web.app import _hash_password, _verify_password
        original = "ledmatrix"
        hashed = _hash_password(original)
        assert _verify_password(original, hashed)
