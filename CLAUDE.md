\# FloodAI



FastAPI backend + React frontend. Flood prediction system for Jakarta.



\## Stack

\- Backend: FastAPI + uvicorn, port 8080

\- Frontend: React + Vite

\- DB: Supabase/PostgreSQL + psycopg2

\- ML: XGBoost + scikit-learn 1.5.2

\- Deploy: Railway (backend) + Vercel (frontend)



\## Run

uvicorn api.main:app --host 0.0.0.0 --port 8080 --reload



\## Key paths

\- API: api/main.py

\- Decision engine: app/services/decision\_engine.py

\- Tests: tests/



\## Known issues

\- TMA scraper broken

\- Calibration step deactivated (ECE 0.3784)

\- BNPB district mapping gap (kecamatan write-back)

