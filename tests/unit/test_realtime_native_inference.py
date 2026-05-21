from types import SimpleNamespace

from realtime_native import inference


def test_load_thresholds_uses_runtime_bundle_thresholds(monkeypatch):
    monkeypatch.setattr(
        inference,
        "load_runtime_bundle",
        lambda: SimpleNamespace(
            thresholds={
                "pre_alert": 0.20,
                "warning": 0.30,
                "danger": 0.45,
                "source": "threshold.json",
                "model_variant": "realtime_native",
            }
        ),
    )

    thresholds = inference._load_thresholds()

    assert thresholds["pre_alert"] == 0.20
    assert thresholds["warning"] == 0.30
    assert thresholds["danger"] == 0.45
    assert thresholds["source"] == "threshold.json"
    assert thresholds["model_variant"] == "realtime_native"
