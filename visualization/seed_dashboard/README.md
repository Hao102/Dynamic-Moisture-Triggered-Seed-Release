# Moisture-Triggered Seed Release Dashboard

## Setup (Python 3.10+)
    python -m venv venv
    venv\Scripts\activate          (Windows)   |   source venv/bin/activate   (Mac/Linux)
    pip install -r requirements.txt

## Run
    streamlit run app.py
(Do not use `python app.py`, it gives ScriptRunContext warnings.) Opens at http://localhost:8501

## Using it
1. Upload `soil_moisture_dataset_expanded.xlsx` in the sidebar (or a CSV with `distance_m, moisture_pct`, or leave empty for generated data).
2. Set parameters, click **Run Simulation**.
3. Animations (depth view, side view), metrics and charts appear. The release log downloads from the Raw Data tab.

## Known limits
- Control logic is a placeholder (moisture to depth mapping + actuator lag), Tony's RxPY module is not integrated yet.
- Speed profile is synthetic unless a speed CSV (`time_s, speed_m_s`) is uploaded.
- Lateral (field position) slider needs the XLSX file.
- Animations show about 40 sample seeds for readability; metrics use all releases.
