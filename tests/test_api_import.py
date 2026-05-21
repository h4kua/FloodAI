def test_api_import():
    import api.main  # noqa: F401


def test_inference_import():
    from realtime_native import inference  # noqa: F401
