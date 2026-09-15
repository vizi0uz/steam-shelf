"""Integration tests for Steam API endpoints."""

import pytest
import requests


@pytest.mark.integration
def test_storefront_search_resolves_a_folder_name_to_an_appid():
    """The endpoint name resolution actually runs on.

    This replaced ISteamApps/GetAppList, which Valve removed: every variant of
    it now answers "Method 'GetAppList' not found in interface 'ISteamApps'".
    The storefront search needs no API key and does the fuzzy matching itself,
    which is why folder names no longer have to match Steam's exactly.
    """
    response = requests.get(
        "https://store.steampowered.com/api/storesearch/",
        params={"term": "STALKER2", "cc": "us", "l": "en"},
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) steam-shelf"},
        timeout=20,
    )

    assert response.status_code == 200

    payload = response.json()
    assert "items" in payload

    apps = [item for item in payload["items"] if item.get("type") == "app"]
    assert apps, "storefront search returned no apps"

    sample = apps[0]
    assert isinstance(sample["id"], int)
    assert isinstance(sample["name"], str)

    # The whole point of the fuzzy match: a folder named "STALKER2" finds the
    # game whose real title is "S.T.A.L.K.E.R. 2: Heart of Chornobyl".
    assert any("S.T.A.L.K.E.R. 2" in app["name"] for app in apps)



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
