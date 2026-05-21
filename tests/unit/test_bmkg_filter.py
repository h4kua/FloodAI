from agents.perception_agent import PerceptionAgent
from services.bmkg_filter import filter_jakarta_bmkg_alerts, is_jakarta_bmkg_alert
from poskobanjir.services.parser import build_realtime_snapshot


def test_is_jakarta_bmkg_alert_uses_area_desc():
    assert is_jakarta_bmkg_alert({"area_desc": "DKI Jakarta"}) is True
    assert is_jakarta_bmkg_alert({"area_desc": "Jambi"}) is False


def test_filter_jakarta_bmkg_alerts_removes_national_noise():
    alerts = [
        {"headline": "Hujan Lebat di Jakarta Utara", "area_desc": "DKI Jakarta"},
        {"headline": "Hujan Lebat di Jambi", "area_desc": "Jambi"},
    ]

    filtered = filter_jakarta_bmkg_alerts(alerts)

    assert len(filtered) == 1
    assert filtered[0]["area_desc"] == "DKI Jakarta"


def test_build_realtime_snapshot_only_keeps_jakarta_alerts():
    snapshot = build_realtime_snapshot(
        poskobanjir_records=[],
        weather={"name": "Jakarta"},
        bmkg_feed=[],
        bmkg_alerts=[
            {"headline": "Jakarta Barat", "area_desc": "Jakarta Barat"},
            {"headline": "Sulawesi Selatan", "area_desc": "Sulawesi Selatan"},
        ],
    )

    assert snapshot["summary"]["total_bmkg_alerts"] == 1
    assert snapshot["bmkg_alerts"][0]["area_desc"] == "Jakarta Barat"


def test_perception_agent_filters_contaminated_snapshot_alerts_at_read_time():
    perception = PerceptionAgent().run(
        {
            "fetched_at_utc": "2026-05-17T00:00:00+00:00",
            "openweather": {},
            "poskobanjir": [],
            "bmkg_alerts": [
                {"headline": "Jakarta Barat", "area_desc": "Jakarta Barat"},
                {"headline": "Sulawesi Selatan", "area_desc": "Sulawesi Selatan"},
            ],
        }
    )

    assert len(perception.bmkg_alerts) == 1
    assert perception.bmkg_alerts[0]["area_desc"] == "Jakarta Barat"
