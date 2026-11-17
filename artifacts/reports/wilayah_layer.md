# Per-wilayah decision layer

Generated 2026-11-17T14:01:11+00:00 by `scripts/train_wilayah_layer.py` on cuda (1000 day resamples). Test (rain lag 1): years 2019, 2020, 2021, 2025, each trained on earlier years; levels read as alarm share / recall / precision; label = a BPBD flood in the wilayah that day.

15450 wilayah-snapshots, flood in the wilayah on 0.084.

- City layer copied to every wilayah: ROC-AUC 0.779 [0.742–0.81]; Waspada 0.359/0.755/0.178 · Siaga 0.064/0.285/0.376 · Bahaya 0.031/0.174/0.478.
- Wilayah layer, served (the city's chance thresholds): ROC-AUC 0.817 [0.786–0.845] (− city [0.026, 0.051]); Waspada 0.124/0.525/0.357 · Siaga 0.018/0.144/0.667 · Bahaya 0.011/0.085/0.673.
- Wilayah layer, volume-matched thresholds (not served): Waspada 0.467/0.853/0.154 · Siaga 0.073/0.383/0.441 · Bahaya 0.036/0.241/0.57; − city Waspada recall [0.065, 0.136], precision [-0.033, -0.014] · Siaga recall [0.066, 0.131], precision [0.02, 0.105] · Bahaya recall [0.033, 0.103], precision [0.015, 0.164].
- Served wilayah − city per level: Waspada recall [-0.269, -0.193], precision [0.149, 0.208] · Siaga recall [-0.183, -0.1], precision [0.204, 0.375] · Bahaya recall [-0.124, -0.057], precision [0.1, 0.282]

| Wilayah | Flood share | City: Waspada / Siaga / Bahaya (recall, precision) | Wilayah layer (served) |
|---|---|---|---|
| Jakarta Barat | 0.091 | 0.748, 0.19 / 0.294, 0.419 / 0.184, 0.547 | 0.479, 0.324 / 0.142, 0.714 / 0.078, 0.647 |
| Jakarta Pusat | 0.016 | 0.84, 0.038 / 0.52, 0.131 / 0.42, 0.221 | 0.42, 0.323 / 0.12, 0.333 / 0.12, 0.375 |
| Jakarta Selatan | 0.117 | 0.793, 0.26 / 0.284, 0.52 / 0.16, 0.611 | 0.606, 0.399 / 0.163, 0.728 / 0.094, 0.85 |
| Jakarta Timur | 0.118 | 0.844, 0.279 / 0.328, 0.606 / 0.186, 0.716 | 0.721, 0.379 / 0.199, 0.702 / 0.115, 0.75 |
| Jakarta Utara | 0.079 | 0.553, 0.122 / 0.164, 0.202 / 0.115, 0.295 | 0.184, 0.238 / 0.041, 0.435 / 0.029, 0.368 |

Served thresholds (flood chance per level): {'1': {'PRE_ALERT': 0.20148, 'WARNING': 0.64573, 'DANGER': 0.79996}, '2': {'PRE_ALERT': 0.21218, 'WARNING': 0.64613, 'DANGER': 0.80498}, '3': {'PRE_ALERT': 0.20842, 'WARNING': 0.65572, 'DANGER': 0.80653}}

Kecamatan flooded on the most days (BPBD 2013-2025):

- Jakarta Barat: Cengkareng (222), Kebon Jeruk (210), Kalideres (186)
- Jakarta Pusat: Tanah Abang (65), Kemayoran (25), Gambir (15)
- Jakarta Selatan: Pasar Minggu (308), Pancoran (211), Tebet (187)
- Jakarta Timur: Jatinegara (412), Kramat Jati (365), Makasar (171)
- Jakarta Utara: Penjaringan (307), Cilincing (150), Tanjung Priok (61)
