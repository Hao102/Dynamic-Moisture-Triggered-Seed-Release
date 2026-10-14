from __future__ import annotations

from pathlib import Path
import pandas as pd

from interface import DEFAULT_CONFIG
from prediction_control.dataset_pipeline import load_project_dataset, run_dataset_pipeline
from prediction_control.hao_model_runtime import HaoMixtureGPRRuntime

ROOT = Path(__file__).resolve().parent
DATASET = ROOT / "data" / "integration" / "final_semi_synthetic_winter_wheat_v2.csv"
MODEL = ROOT / "models" / "hao_mixture_gpr_runtime.joblib"
OUTPUT_DIR = ROOT / "outputs"


def load_or_train_model(df: pd.DataFrame) -> HaoMixtureGPRRuntime:
    if MODEL.exists():
        return HaoMixtureGPRRuntime.load(MODEL)
    model = HaoMixtureGPRRuntime().fit(df)
    model.save(MODEL)
    return model


def main() -> None:
    df = load_project_dataset(DATASET)
    model = load_or_train_model(df)
    config = dict(DEFAULT_CONFIG)

    control_log, releases = run_dataset_pipeline(
        df, model, config,
        lateral_m=15.0,
        depth_cm=config["model_depth_cm"],
    )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    control_log.to_csv(OUTPUT_DIR / "control_log.csv", index=False)
    releases.to_csv(OUTPUT_DIR / "release_events.csv", index=False)

    print("DMTSRS pipeline completed")
    print(f"Dataset rows: {len(df):,}")
    print(f"Control samples: {len(control_log):,}")
    print(f"Release events: {len(releases):,}")
    if len(releases):
        print(f"Mean actual spacing: {releases['position_m'].diff().dropna().mean() * 1000:.3f} mm")
        print(f"Max compensation error: {releases['compensation_error_m'].abs().max() * 1000:.3f} mm")
        print("First release event:")
        print(releases.iloc[0].to_dict())
    print(f"Outputs: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
