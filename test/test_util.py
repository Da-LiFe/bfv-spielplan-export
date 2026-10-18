import util

# --------------------------------------------------------------- place_text()


def test_place_text_joins_parts_and_drops_empties():
    assert util.place_text("Sportpark |  12345 Testfeld | ") == (
        "Sportpark, 12345 Testfeld"
    )
    assert util.place_text(" |  ") == ""
    assert util.place_text("") == ""


# ------------------------------------------------------------------ maps_url()


def test_maps_url_empty():
    assert util.maps_url("") == ""


def test_maps_url_quotes_and_joins():
    url = util.maps_url("Sportpark | Testfeld")
    assert url.startswith("https://www.google.com/maps/search/?api=1&query=")
    assert "%2C" in url


def test_maps_url_ignores_separator_only_location():
    assert util.maps_url(" |  ") == ""
