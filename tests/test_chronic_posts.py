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


# --- Rapid rise must come from a post that is itself high (25 Nov 2026 false Bahaya) ---------------------

def test_a_small_rise_at_a_near_empty_weir_is_not_a_rapid_escalation():
    # Katulampa 10.6 -> 33.6 cm is 0.115 of its Siaga 1 (200 cm), but the post is Normal; Cengkareng Drain is
    # chronically at Siaga 2 (counted as Siaga 3) and not rising. The old rule paired the two and said Bahaya.
    posts = [_post("Bendung Katulampa", 33.6, 80, 150, 200), _post("P.A. Cengkareng Drain", 288)]
    deltas = {"Bendung Katulampa": 0.115, "P.A. Cengkareng Drain": 0.0097}
    result = analyze_hydrology(posts, water_level_delta=0.115, station_deltas=deltas)
    assert result.rapid_escalation is False
    assert analyze_hydrology(posts, water_level_delta=0.115).rapid_escalation is True  # the old global behaviour


def test_a_high_post_rising_fast_is_still_a_rapid_escalation():
    posts = [_post("P.A. Manggarai 2", 780, 750, 850, 950), _post("Bendung Katulampa", 33.6, 80, 150, 200)]
    result = analyze_hydrology(posts, station_deltas={"P.A. Manggarai 2": 0.12, "Bendung Katulampa": 0.0})
    assert result.rapid_escalation is True
    assert "P.A. Manggarai 2" in result.overall_explanation


def test_a_fast_rise_at_a_normal_post_stays_calm_even_if_others_are_high():
    posts = [_post("P.A. Manggarai 2", 780, 750, 850, 950), _post("P.A. Karet 1", 100, 200, 300, 400)]
    result = analyze_hydrology(posts, station_deltas={"P.A. Manggarai 2": 0.01, "P.A. Karet 1": 0.2})
    assert result.rapid_escalation is False


def test_without_per_post_deltas_the_overall_delta_still_decides():
    posts = [_post("P.A. Manggarai 2", 760, 750, 850, 950)]
    assert analyze_hydrology(posts, water_level_delta=0.25, station_deltas={"P.A. Manggarai 2": None}).rapid_escalation is True
