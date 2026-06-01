import pandas as pd

_SPIKE_THRESHOLD_CM = 300.0


def clean_data(data):
    df = pd.DataFrame(data)

    print("Kolom tersedia:", df.columns.tolist())

    # Rename biar konsisten
    df = df.rename(columns={
        "id_pintu_air": "id",
        "nama_pintu_air": "nama",
        "tinggi_air": "tinggi_air",
        "tinggi_air_sebelumnya": "tinggi_air_sebelumnya",
        "status_siaga": "status",
        "tanggal": "tanggal"
    })

    # Drop duplicate (pakai nama baru)
    if "id" in df.columns and "tanggal" in df.columns:
        df = df.drop_duplicates(subset=["id", "tanggal"])

    if "tinggi_air" in df.columns:
        df["tinggi_air"] = pd.to_numeric(df["tinggi_air"], errors="coerce")

    # Spike detection: exclude stations where water level jumped > 300 cm
    # since previous reading — likely a sensor error, not a real flood surge.
    spiked_stations = []
    if "tinggi_air" in df.columns and "tinggi_air_sebelumnya" in df.columns:
        df["tinggi_air_sebelumnya"] = pd.to_numeric(
            df["tinggi_air_sebelumnya"], errors="coerce"
        )
        has_prev = df["tinggi_air_sebelumnya"].notna() & df["tinggi_air"].notna()
        spike_mask = has_prev & (
            (df["tinggi_air"] - df["tinggi_air_sebelumnya"]).abs() > _SPIKE_THRESHOLD_CM
        )
        if spike_mask.any():
            spiked = df[spike_mask].copy()
            for _, row in spiked.iterrows():
                nama = row.get("nama", row.get("id", "?"))
                delta = abs(row["tinggi_air"] - row["tinggi_air_sebelumnya"])
                spiked_stations.append({
                    "nama": str(nama),
                    "tinggi_air": row["tinggi_air"],
                    "tinggi_air_sebelumnya": row["tinggi_air_sebelumnya"],
                    "delta_cm": round(delta, 1),
                })
            df = df[~spike_mask].copy()

    if spiked_stations:
        print(
            f"\n[DATA QUALITY] {len(spiked_stations)} station(s) excluded — "
            f"water level spike > {_SPIKE_THRESHOLD_CM:.0f} cm (likely sensor error):"
        )
        for s in spiked_stations:
            print(
                f"  - {s['nama']}: {s['tinggi_air_sebelumnya']} → {s['tinggi_air']} cm "
                f"(delta {s['delta_cm']} cm)"
            )
    else:
        print("[DATA QUALITY] No water level spikes detected.")

    return df
