import io
import numpy as np
import pandas as pd
import streamlit as st
import matplotlib.pyplot as plt
import plotly.graph_objects as go
from scipy.interpolate import RegularGridInterpolator

st.set_page_config(page_title="Moisture-Triggered Seed Release Dashboard", layout="wide")

# ---------------------------------------------------------------------------
# fallback synthetic data (used if nothing is uploaded)
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# TASK 8: cache expensive functions so the dashboard loads/reruns faster
# ---------------------------------------------------------------------------
@st.cache_data
def generate_default_moisture_data(length_m=200, seed=42):
    rng = np.random.default_rng(seed)
    positions = np.arange(0, length_m, 1.0)
    base = 20 + 6 * np.sin(positions / 35) + 3 * np.sin(positions / 12 + 1.5)
    dry_zone = (positions > length_m * 0.35) & (positions < length_m * 0.5)
    wet_zone = (positions > length_m * 0.7) & (positions < length_m * 0.82)
    base[dry_zone] -= 5
    base[wet_zone] += 5
    noise = rng.normal(0, 0.8, size=len(positions))
    moisture = np.clip(base + noise, 8, 35)
    return pd.DataFrame({"distance_m": positions, "moisture_pct": np.round(moisture, 2)})


@st.cache_data
def generate_default_speed_profile(duration_s=140, seed=7):
    rng = np.random.default_rng(seed)
    t = np.arange(0, duration_s, 0.1)
    speed = np.piecewise(
        t,
        [t < 15, (t >= 15) & (t < 60), (t >= 60) & (t < 75), (t >= 75) & (t < 110), t >= 110],
        [lambda x: 0.5 + (x / 15) * 1.3, 1.8, lambda x: 1.8 - ((x - 60) / 15) * 1.3,
         lambda x: 0.5 + ((x - 75) / 35) * 2.2, 2.7]
    )
    speed += rng.normal(0, 0.03, len(t))
    speed = np.clip(speed, 0.3, None)
    return pd.DataFrame({"time_s": t, "speed_m_s": np.round(speed, 3)})


# ---------------------------------------------------------------------------
# TASK 1 (SEED-88): load client's real xlsx file directly, no conversion needed
# ---------------------------------------------------------------------------
@st.cache_data
def load_2d_moisture_grid(xlsx_file):
    raw = pd.read_excel(xlsx_file, skiprows=3, header=None)
    raw = raw.iloc[:, :4]
    raw.columns = ["distance_m", "moisture_0m", "moisture_15m", "moisture_30m"]
    raw = raw.dropna(subset=["distance_m"])
    distances = raw["distance_m"].values
    lateral_positions = np.array([0.0, 15.0, 30.0])
    moisture_grid = raw[["moisture_0m", "moisture_15m", "moisture_30m"]].values
    return distances, lateral_positions, moisture_grid


# ---------------------------------------------------------------------------
# TASK 2 (SEED-89): check moisture at any point across the field, not just
# the 3 measured lines
# ---------------------------------------------------------------------------
def build_field_interpolator(distances, lateral_positions, moisture_grid):
    return RegularGridInterpolator(
        (distances, lateral_positions), moisture_grid,
        bounds_error=False, fill_value=None
    )


def sample_moisture_along_path(interpolator, distances, lateral_offset_m):
    points = np.column_stack([distances, np.full_like(distances, lateral_offset_m)])
    return interpolator(points)


# ---------------------------------------------------------------------------
# TASK 9: stronger error handling for bad/missing uploaded files
# ---------------------------------------------------------------------------
def validate_moisture_dataframe(df):
    """Returns (is_valid, message). Catches empty files, wrong columns,
    non numeric data, and all missing values, so a bad upload gives a
    clear reason instead of a confusing crash further down the pipeline."""
    if df.empty:
        return False, "The uploaded file has no rows."
    if not {"distance_m", "moisture_pct"}.issubset(df.columns):
        return False, "Missing required columns: distance_m, moisture_pct."
    if df["distance_m"].isna().all() or df["moisture_pct"].isna().all():
        return False, "distance_m or moisture_pct is completely empty."
    if not pd.api.types.is_numeric_dtype(df["moisture_pct"]):
        return False, "moisture_pct column contains non numeric values."
    return True, ""


# ---------------------------------------------------------------------------
# control logic (placeholder - swap for Tony's module later)
# ---------------------------------------------------------------------------
def get_value_at(x, positions, values):
    return np.interp(x, positions, values)


def moisture_to_depth(moisture, min_m, max_m, min_d, max_d):
    m = np.clip(moisture, min_m, max_m)
    t = (m - min_m) / (max_m - min_m)
    return max_d - t * (max_d - min_d)


def run_simulation(field_positions, field_moisture, speed_time, speed_values,
                    target_spacing_m, control_dt_s, actuator_tau_s,
                    min_moisture, max_moisture, min_depth, max_depth):
    t_max = speed_time.max()
    time_steps = np.arange(0, t_max, control_dt_s)

    position_m = 0.0
    next_release_position_m = 0.0
    actuator_depth_mm = None
    log_rows, release_rows = [], []

    for t in time_steps:
        speed = get_value_at(t, speed_time, speed_values)
        prev_position_m = position_m
        position_m += speed * control_dt_s

        moisture = get_value_at(position_m, field_positions, field_moisture)
        target_depth = moisture_to_depth(moisture, min_moisture, max_moisture, min_depth, max_depth)

        if actuator_depth_mm is None:
            actuator_depth_mm = target_depth
        alpha = control_dt_s / (actuator_tau_s + control_dt_s)
        actuator_depth_mm += alpha * (target_depth - actuator_depth_mm)

        while position_m >= next_release_position_m and speed > 0:
            frac = np.clip((next_release_position_m - prev_position_m) /
                            (position_m - prev_position_m + 1e-12), 0, 1)
            interp_time = t - control_dt_s + frac * control_dt_s
            release_rows.append({
                "time_s": interp_time,
                "position_m": next_release_position_m,
                "speed_m_s": speed,
                "moisture_pct": get_value_at(next_release_position_m, field_positions, field_moisture),
                "target_depth_mm": target_depth,
                "actuator_depth_mm": actuator_depth_mm,
            })
            next_release_position_m += target_spacing_m

        log_rows.append({
            "time_s": t, "position_m": position_m, "speed_m_s": speed,
            "moisture_pct": moisture, "target_depth_mm": target_depth,
            "actuator_depth_mm": actuator_depth_mm,
        })

    return pd.DataFrame(log_rows), pd.DataFrame(release_rows)


# ---------------------------------------------------------------------------
# TASK 5 (SEED-92): animated view of the wheel moving across the field
# ---------------------------------------------------------------------------
def build_field_animation(log_df, releases_df, max_depth_mm, n_frames=80, max_visible_seeds=40):
    idx = np.linspace(0, len(log_df) - 1, n_frames).astype(int)
    frame_times = log_df["time_s"].values[idx]
    frame_positions = log_df["position_m"].values[idx]

    # real spacing produces thousands of release events, which render as a
    # solid smear instead of discrete seed markers if all shown at once.
    total_releases = len(releases_df)
    if total_releases > max_visible_seeds:
        step = max(1, total_releases // max_visible_seeds)
        display_releases = releases_df.iloc[::step].reset_index(drop=True)
    else:
        display_releases = releases_df

    frames = []
    for i, ft in enumerate(frame_times):
        visible_seeds = display_releases[display_releases["time_s"] <= ft]
        frames.append(go.Frame(
            data=[
                go.Scatter(  # seeds dropped so far
                    x=visible_seeds["position_m"], y=-visible_seeds["target_depth_mm"],
                    mode="markers",
                    marker=dict(size=10, color=visible_seeds["moisture_pct"],
                                colorscale="Brwnyl_r", cmin=releases_df["moisture_pct"].min(),
                                cmax=releases_df["moisture_pct"].max()),
                    name="Seeds",
                ),
                go.Scatter(  # the wheel itself
                    x=[frame_positions[i]], y=[5],
                    mode="markers", marker=dict(size=22, color="#333333", symbol="circle"),
                    name="Wheel",
                ),
            ],
            name=str(i),
        ))

    fig = go.Figure(
        data=frames[0].data,
        frames=frames,
        layout=go.Layout(
            xaxis=dict(title="Field position (m)", range=[0, log_df["position_m"].max()]),
            yaxis=dict(title="Depth (mm)", range=[-max_depth_mm - 5, 15]),
            height=420,
            margin=dict(l=40, r=20, t=30, b=40),
            updatemenus=[dict(
                type="buttons", showactive=False, y=1.15, x=0,
                buttons=[
                    dict(label="▶ Play", method="animate",
                         args=[None, {"frame": {"duration": 60, "redraw": True}, "fromcurrent": True}]),
                    dict(label="⏸ Pause", method="animate",
                         args=[[None], {"frame": {"duration": 0}, "mode": "immediate"}]),
                ],
            )],
            sliders=[dict(
                steps=[dict(method="animate", args=[[str(i)], {"frame": {"duration": 0, "redraw": True}}],
                            label=f"{frame_times[i]:.0f}s") for i in range(len(frames))],
                x=0, y=-0.05, len=1.0,
            )],
        ),
    )
    return fig


# ---------------------------------------------------------------------------
# SIDE VIEW: seeder opener arm moving over green soil, seeds land at the
# depth the control logic commanded
# ---------------------------------------------------------------------------
def build_side_view_animation(log_df, releases_df, max_depth_mm, n_frames=80, max_visible_seeds=40):
    idx = np.linspace(0, len(log_df) - 1, n_frames).astype(int)
    frame_times = log_df["time_s"].values[idx]
    frame_positions = log_df["position_m"].values[idx]
    frame_depths = log_df["actuator_depth_mm"].values[idx]
    max_position = log_df["position_m"].max()

    # only show about 40 seeds, thousands of markers just look like a solid line
    total_releases = len(releases_df)
    if total_releases > max_visible_seeds:
        step = max(1, total_releases // max_visible_seeds)
        display_releases = releases_df.iloc[::step].reset_index(drop=True)
    else:
        display_releases = releases_df

    def seeds_trace(ft):
        vis = display_releases[display_releases["time_s"] <= ft]
        return go.Scatter(x=vis["position_m"], y=-vis["target_depth_mm"], mode="markers",
                          marker=dict(size=9, color="#5b3a1e"), name="Seeds")

    def arm_trace(i):
        return go.Scatter(x=[frame_positions[i]] * 2, y=[18, -frame_depths[i]],
                          mode="lines+markers", line=dict(color="#444444", width=4),
                          marker=dict(size=[1, 12], color="red", symbol=["circle", "triangle-down"]),
                          name="Opener")

    ground = go.Scatter(x=[0, max_position], y=[0, 0], mode="lines",
                        line=dict(color="#6b4a2b", width=3), name="Ground", hoverinfo="skip")

    frames = [go.Frame(data=[seeds_trace(frame_times[i]), arm_trace(i)], traces=[1, 2], name=str(i))
              for i in range(n_frames)]

    fig = go.Figure(
        data=[ground, seeds_trace(frame_times[0]), arm_trace(0)],
        frames=frames,
        layout=go.Layout(
            xaxis=dict(title="Field position (m)", range=[0, max_position]),
            yaxis=dict(title="Depth (mm)", range=[-max_depth_mm - 10, 25]),
            height=420, margin=dict(l=40, r=20, t=30, b=40), showlegend=False,
            shapes=[dict(type="rect", x0=0, x1=max_position, y0=-max_depth_mm - 10, y1=0,
                         fillcolor="rgba(60, 140, 60, 0.35)", line=dict(width=0), layer="below")],
            updatemenus=[dict(
                type="buttons", showactive=False, y=1.15, x=0,
                buttons=[
                    dict(label="▶ Play", method="animate",
                         args=[None, {"frame": {"duration": 60, "redraw": True}, "fromcurrent": True}]),
                    dict(label="⏸ Pause", method="animate",
                         args=[[None], {"frame": {"duration": 0}, "mode": "immediate"}]),
                ],
            )],
            sliders=[dict(
                steps=[dict(method="animate", args=[[str(i)], {"frame": {"duration": 0, "redraw": True}}],
                            label=f"{frame_times[i]:.0f}s") for i in range(n_frames)],
                x=0, y=-0.05, len=1.0,
            )],
        ),
    )
    return fig


# ===========================================================================
# SIDEBAR: DATA INPUT
# ===========================================================================
st.sidebar.header("1. Data Input")
moisture_file = st.sidebar.file_uploader(
    "Moisture file - upload client's XLSX as-is, or a simple CSV",
    type=["csv", "xlsx"], key="moisture_upload"
)

using_field_data = False
lateral_offset_m = 15.0

if moisture_file is not None:
    try:
        if moisture_file.name.endswith(".xlsx"):
            distances, lateral_positions, moisture_grid = load_2d_moisture_grid(moisture_file)
            interpolator = build_field_interpolator(distances, lateral_positions, moisture_grid)
            using_field_data = True

            # -----------------------------------------------------------
            # TASK 3 (SEED-90): slider to pick where across the field the
            # seeder is driving
            # -----------------------------------------------------------
            st.sidebar.subheader("Field Position")
            lateral_offset_m = st.sidebar.slider(
                "Where across the field is the seeder driving? (m)",
                float(lateral_positions.min()), float(lateral_positions.max()), 15.0, step=0.5
            )
            field_positions = distances
            field_moisture = sample_moisture_along_path(interpolator, distances, lateral_offset_m)
        else:
            field_df = pd.read_csv(moisture_file)
            is_valid, msg = validate_moisture_dataframe(field_df)
            if not is_valid:
                st.sidebar.warning(f"Upload issue: {msg} Using default dataset instead.")
                field_df = generate_default_moisture_data()
            field_positions = field_df["distance_m"].values
            field_moisture = field_df["moisture_pct"].values
    except Exception as e:
        st.sidebar.error(f"Could not read file: {e}. Using default dataset.")
        field_df = generate_default_moisture_data()
        field_positions = field_df["distance_m"].values
        field_moisture = field_df["moisture_pct"].values
else:
    field_df = generate_default_moisture_data()
    field_positions = field_df["distance_m"].values
    field_moisture = field_df["moisture_pct"].values

speed_file = st.sidebar.file_uploader(
    "Speed profile CSV (time_s, speed_m_s)", type="csv", key="speed_upload"
)
if speed_file is not None:
    try:
        speed_df = pd.read_csv(speed_file)
        if not {"time_s", "speed_m_s"}.issubset(speed_df.columns):
            st.sidebar.warning("Missing required columns. Using default profile.")
            speed_df = generate_default_speed_profile()
    except Exception as e:
        st.sidebar.error(f"Could not read file: {e}. Using default profile.")
        speed_df = generate_default_speed_profile()
else:
    speed_df = generate_default_speed_profile()

# ===========================================================================
# SIDEBAR: PARAMETERS
# ===========================================================================
st.sidebar.header("2. Control Parameters")
target_spacing_mm = st.sidebar.slider("Target seed spacing (mm)", 10, 60, 30, step=1)
depth_range = st.sidebar.slider("Depth range (mm)", 5, 60, (15, 40), step=1)
moisture_range = st.sidebar.slider(
    "Moisture range mapped to depth (%)",
    float(np.floor(field_moisture.min())), float(np.ceil(field_moisture.max())),
    (float(np.floor(field_moisture.min())), float(np.ceil(field_moisture.max()))),
)
actuator_tau_ms = st.sidebar.slider("Actuator response time constant (ms)", 10, 500, 150, step=10)
control_dt_ms = st.sidebar.slider("Control loop time step (ms)", 5, 100, 10, step=5)

# ===========================================================================
# MAIN PAGE
# ===========================================================================
st.title("Dynamic Moisture-Triggered Seed Release — Dashboard")
if using_field_data:
    st.caption(f"Using real client data — checking moisture at {lateral_offset_m}m across the field")
else:
    st.caption("Using CSV / synthetic data")

with st.expander("ℹ️ How to use this dashboard"):
    st.markdown(
        "1. **Upload data** in the sidebar — the client's real XLSX file, a simple CSV, "
        "or leave it blank to use generated sample data.\n"
        "2. **Set parameters** — seed spacing, depth range, and how fast the actuator "
        "responds to changes.\n"
        "3. **Click Run Simulation** in the sidebar.\n"
        "4. **Review results** — animations, accuracy metrics, and charts appear below. "
        "The release log can be downloaded as a CSV from the Raw Data tab."
    )

col1, col2 = st.columns(2)
with col1:
    st.subheader("Moisture Data")
    fig, ax = plt.subplots(figsize=(6, 2.5))
    ax.plot(field_positions, field_moisture, color="tab:green")
    ax.set_xlabel("Distance (m)"); ax.set_ylabel("Moisture (%)"); ax.grid(alpha=0.3)
    st.pyplot(fig)
with col2:
    st.subheader("Speed Profile")
    fig2, ax2 = plt.subplots(figsize=(6, 2.5))
    ax2.plot(speed_df["time_s"], speed_df["speed_m_s"], color="tab:purple")
    ax2.set_xlabel("Time (s)"); ax2.set_ylabel("Speed (m/s)"); ax2.grid(alpha=0.3)
    st.pyplot(fig2)

# ---------------------------------------------------------------------------
# TASK 4 (SEED-91): check the field-position feature gives correct results
# ---------------------------------------------------------------------------
if using_field_data:
    with st.expander("✅ Check: does the field-position slider give correct results?"):
        st.write(
            "At lateral = 0m, values should exactly match the client's original "
            "0m column. At lateral = 15m, they should match the 15m column. "
            "Anything in between should sit between those two values."
        )
        check_points = [0.0, 15.0, 30.0]
        check_df = pd.DataFrame({"distance_m": distances[:5]})
        for lp in check_points:
            check_df[f"moisture_at_{lp}m"] = sample_moisture_along_path(
                interpolator, distances[:5], lp
            )
        st.dataframe(check_df, use_container_width=True)

if st.sidebar.button("Run Simulation", type="primary"):
    with st.spinner("Running simulation..."):
        log, releases = run_simulation(
            field_positions, field_moisture,
            speed_df["time_s"].values, speed_df["speed_m_s"].values,
            target_spacing_mm / 1000, control_dt_ms / 1000, actuator_tau_ms / 1000,
            moisture_range[0], moisture_range[1], depth_range[0], depth_range[1],
        )
    st.session_state["log"] = log
    st.session_state["releases"] = releases
    st.session_state["depth_range"] = depth_range

if "releases" in st.session_state:
    log = st.session_state["log"]
    releases = st.session_state["releases"]

    # -----------------------------------------------------------------
    # TASK 5 (SEED-92): animated view of the wheel moving across the field
    # -----------------------------------------------------------------
    st.divider()
    st.subheader("🎬 Seeder Animation (Depth View)")
    anim_fig = build_field_animation(log, releases, st.session_state["depth_range"][1])
    st.plotly_chart(anim_fig, use_container_width=True)

    st.divider()
    st.subheader("⚙️ Seeder Animation (Side View)")
    st.caption(
        "A mechanical side view: the opener arm rises and falls in real time "
        "to match the actual actuator depth as the seeder moves."
    )
    side_view_fig = build_side_view_animation(log, releases, st.session_state["depth_range"][1])
    st.plotly_chart(side_view_fig, use_container_width=True)

    st.divider()
    st.header("Results")

    spacing_actual_mm = releases["position_m"].diff().dropna() * 1000
    depth_error_mm = releases["actuator_depth_mm"] - releases["target_depth_mm"]

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total release events", f"{len(releases):,}")
    m2.metric("Mean spacing", f"{spacing_actual_mm.mean():.2f} mm", f"target {target_spacing_mm} mm")
    m3.metric("Spacing std dev", f"{spacing_actual_mm.std():.3f} mm")
    m4.metric("Max depth error", f"{depth_error_mm.abs().max():.2f} mm")

    tab1, tab2, tab3 = st.tabs(["Depth Response", "Release Rate", "Raw Data"])
    with tab1:
        fig3, ax3 = plt.subplots(figsize=(11, 3.5))
        ax3.plot(log["time_s"], log["target_depth_mm"], label="Target depth", color="tab:orange")
        ax3.plot(log["time_s"], log["actuator_depth_mm"], label="Actuator depth",
                 color="tab:red", linestyle="--", linewidth=0.8)
        ax3.invert_yaxis(); ax3.set_xlabel("Time (s)"); ax3.set_ylabel("Depth (mm)")
        ax3.legend(); ax3.grid(alpha=0.3)
        st.pyplot(fig3)
    with tab2:
        bin_width = 1.0
        bins = np.arange(0, log["time_s"].max() + bin_width, bin_width)
        rate, _ = np.histogram(releases["time_s"], bins=bins)
        fig4, ax4 = plt.subplots(figsize=(11, 3.5))
        ax4.bar(bins[:-1], rate / bin_width, width=bin_width * 0.9, color="tab:brown")
        ax4.set_xlabel("Time (s)"); ax4.set_ylabel("Releases / s"); ax4.grid(alpha=0.3)
        st.pyplot(fig4)
    with tab3:
        st.dataframe(releases, use_container_width=True, height=300)
        csv_buf = io.StringIO()
        releases.to_csv(csv_buf, index=False)
        st.download_button("Download release log (CSV)", csv_buf.getvalue(),
                            file_name="release_log.csv", mime="text/csv")
else:
    st.info("Click **Run Simulation** in the sidebar to see the animation and results.")
