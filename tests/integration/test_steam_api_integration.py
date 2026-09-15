"""Integration tests for Steam API endpoints."""

import pytest
import requests


@pytest.mark.integration
@pytest.mark.parametrize(
    "path",
    ["GetAppList/v2/", "GetAppList/v2", "GetAppList/v0002/?format=json", "GetAppList/v1/"],
)
def test_steam_app_list_endpoint_is_gone(path):
    """Steam removed the endpoint SteamDatabase.sync() mirrors.

    This test used to assert the app list came back with game titles. It does
    not any more: every variant answers "Method 'GetAppList' not found in
    interface 'ISteamApps'". That is why the database is empty on a fresh
    install, and why discovery must not treat a failed name lookup as a reason
    to discard a folder.

    It fails if Valve ever restores the endpoint, which is the day this is
    worth revisiting.
    """
    response = requests.get(f"https://api.steampowered.com/ISteamApps/{path}", timeout=20)

    assert response.status_code == 404
    assert "GetAppList" in response.text

@pytest.mark.integration
def test_steam_api_endpoint_real():
    """Integration test that verifies Steam CDN API endpoints work."""
    test_game_id = 730
    base_url = "https://steamcdn-a.akamaihd.net"

    image_types = [
        "library_600x900_2x.jpg",
        "library_hero.jpg",
        "logo.png",
        "capsule_616x353.jpg",
    ]

    for img_type in image_types:
        url = f"{base_url}/steam/apps/{test_game_id}/{img_type}"
        response = requests.get(url, timeout=10)

        assert response.status_code == 200, f"Failed to fetch {img_type} from {url}"
        assert len(response.content) > 0, f"Empty response for {img_type}"

        content_type = response.headers.get("content-type", "")
        assert any(ct in content_type.lower() for ct in ["image", "jpeg", "png"]), (
            f"Invalid content type for {img_type}: {content_type}"
        )


@pytest.mark.integration
def test_steam_api_404_handling():
    """Test that Steam API properly returns error for non-existent games."""
    fake_game_id = 99999999
    base_url = "https://steamcdn-a.akamaihd.net"

    url = f"{base_url}/steam/apps/{fake_game_id}/logo.png"
    response = requests.get(url, timeout=10)

    assert response.status_code in [404, 502], f"Expected error status, got {response.status_code}"
