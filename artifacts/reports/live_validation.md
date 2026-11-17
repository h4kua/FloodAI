# Live validation

Generated 2026-11-17T13:15:43+00:00 by `scripts/live_validation.py`. Period 2026-11-05 to 2026-11-17 (13 days with snapshots). Flood days reported: none.

Each 15-minute snapshot replayed through the code now served (daily model + learned layer + Siaga 1 rule); rules = river-post status or the daily model's Waspada. News is a partial label.

Share of snapshots per level: learned {'Aman': 0.603, 'Waspada': 0.396, 'Siaga': 0.0, 'Bahaya': 0.001}; rules {'Aman': 0.577, 'Waspada': 0.422, 'Siaga': 0.0, 'Bahaya': 0.001}.

| Level (day's highest) | Approach | Warning days | Flood days | Warned flood days | Warning days without a report | Missed flood days |
|---|---|---|---|---|---|---|
| >= Waspada | learned | 7 | 0 | 0 | 7 | 0 |
| >= Siaga | learned | 1 | 0 | 0 | 1 | 0 |
| >= Bahaya | learned | 1 | 0 | 0 | 1 | 0 |
| >= Waspada | rules | 7 | 0 | 0 | 7 | 0 |
| >= Siaga | rules | 1 | 0 | 0 | 1 | 0 |
| >= Bahaya | rules | 1 | 0 | 0 | 1 | 0 |

| Day | Daily chance (lag) | Layer's highest chance | Learned | Rules | Flood reported |
|---|---|---|---|---|---|
| 2026-11-05 | 0.089 (1) | - | Aman | Aman | no |
| 2026-11-06 | 0.206 (1) | 0.155 | Aman | Waspada | no |
| 2026-11-07 | 0.135 (1) | 0.155 | Aman | Waspada | no |
| 2026-11-08 | 0.089 (1) | 0.155 | Aman | Aman | no |
| 2026-11-09 | 0.121 (1) | 0.299 | Waspada | Waspada | no |
| 2026-11-10 | 0.135 (1) | 0.506 | Waspada | Waspada | no |
| 2026-11-11 | 0.061 (1) | 0.215 | Waspada | Aman | no |
| 2026-11-12 | 0.061 (1) | 0.441 | Bahaya | Bahaya | no |
| 2026-11-13 | 0.135 (1) | 0.541 | Waspada | Waspada | no |
| 2026-11-14 | 0.084 (1) | 0.229 | Waspada | Aman | no |
| 2026-11-15 | 0.068 (1) | 0.144 | Aman | Aman | no |
| 2026-11-16 | 0.061 (1) | 0.205 | Aman | Waspada | no |
| 2026-11-17 | 0.071 (1) | 0.394 | Waspada | Aman | no |
