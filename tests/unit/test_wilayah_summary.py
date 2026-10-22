"""wilayah_summary must recognise DSDADKI's "KOTA JAKARTA …" names."""

from realtime_native.inference import _build_wilayah_summary


def _by_wilayah(records):
    return {w["wilayah"]: w for w in _build_wilayah_summary(records, {})}


def test_dsdadki_kota_names_are_counted():
    summary = _by_wilayah([
        {"nama_pintu_air": "P.A. Cengkareng Drain", "file_export": "KOTA JAKARTA BARAT", "status_siaga": "Status : Siaga 3"},
        {"nama_pintu_air": "P.A. Manggarai 2", "file_export": "KOTA JAKARTA SELATAN", "status_siaga": "Status : Normal"},
        {"nama_pintu_air": "P.S. Depok 2", "file_export": "KOTA DEPOK", "status_siaga": "Status : Siaga 2"},
    ])
    assert summary["Jakarta Barat"]["tma_count"] == 1
    assert summary["Jakarta Barat"]["worst_status"] == "Siaga 3"
    assert summary["Jakarta Selatan"]["tma_count"] == 1
    # Upstream posts are not counted toward any Jakarta wilayah
    assert sum(w["tma_count"] for w in summary.values()) == 2


def test_canonical_names_still_work():
    summary = _by_wilayah([{"file_export": "Jakarta Selatan", "status_siaga": "Status : Siaga 1"}])
    assert summary["Jakarta Selatan"]["siaga1_count"] == 1


def test_misfiled_posts_are_moved_to_their_real_wilayah():
    summary = _by_wilayah([
        {"nama_pintu_air": "P.A. Hek Kramat Jati 1", "file_export": "KOTA JAKARTA UTARA", "status_siaga": "Status : Normal"},
        {"nama_pintu_air": "P.A. Kaliduri 1", "file_export": "KOTA JAKARTA UTARA", "status_siaga": "Status : Normal"},
    ])
    assert summary["Jakarta Utara"]["tma_count"] == 0
    assert summary["Jakarta Timur"]["tma_count"] == 1
    assert summary["Jakarta Barat"]["tma_count"] == 1
