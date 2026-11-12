"""Chronically high posts count one band lower for the city status; their own status is unchanged."""

from services.hydrology_analyzer import analyze_hydrology, status_siaga_level


def _post(name, level, s3=190.0, s2=270.0, s1=310.0):
    return {"nama_pintu_air": name, "tinggi_air": level, "siaga3": s3, "siaga2": s2, "siaga1": s1}


def test_cengkareng_drain_at_siaga_3_no_longer_raises_the_city_status():
    result = analyze_hydrology([_post("P.A. Cengkareng Drain", 195), _post("P.A. Manggarai 2", 600, 750, 850, 950)])
    drain = next(s for s in result.stations if "Cengkareng" in s.station_name)
    assert drain.siaga_level == "siaga3"            # the post still shows its official DSDA status
    assert drain.status_siaga_level == "normal"
    assert result.severity_score == 0.0 and result.dominant_siaga_level == "normal"


def test_a_chronic_post_still_warns_when_it_rises():
    siaga2 = analyze_hydrology([_post("Pompa Pasar Ikan 1", 280)])
    assert siaga2.dominant_siaga_level == "siaga3" and siaga2.severity_score == 0.5     # Waspada
    siaga1 = analyze_hydrology([_post("P.A. Marina Ancol 1 (Laut)", 320)])
    assert siaga1.dominant_siaga_level == "siaga2" and siaga1.severity_score == 0.75    # Siaga


def test_other_posts_are_unchanged():
    result = analyze_hydrology([_post("P.A. Manggarai 2", 760, 750, 850, 950), _post("P.A. Cengkareng Drain", 195)])
    assert result.dominant_station == "P.A. Manggarai 2"
    assert result.dominant_siaga_level == "siaga3" and result.severity_score == 0.5
    assert status_siaga_level("siaga1", "P.A. Karet 1") == "siaga1"
    assert status_siaga_level("siaga3", "P.A. Marina Ancol 1 (Kali)") == "siaga3"       # only the sea post is chronic


def test_the_list_can_be_overridden_or_switched_off(monkeypatch):
    monkeypatch.setenv("FLOOD_CHRONIC_POSTS", "")
    assert analyze_hydrology([_post("P.A. Cengkareng Drain", 195)]).dominant_siaga_level == "siaga3"
    monkeypatch.setenv("FLOOD_CHRONIC_POSTS", "karet")
    assert status_siaga_level("siaga3", "P.A. Karet 1") == "normal"
