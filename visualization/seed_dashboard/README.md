Final Dashboard

Windows: double click run_windows.bat (the first time it sets up the packages)

Or by hand:
  python -m venv .venv
  .venv\Scripts\activate
  pip install -r requirements.txt
  streamlit run final_dashboard.py

The default dataset is in data/integration and the saved model is in models.
You can upload a different dataset CSV in the sidebar (the model is trained again from it, about 10 seconds).
