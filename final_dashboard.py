# Final dashboard for the moisture triggered seed release project
# run it with: streamlit run final_dashboard.py
import hashlib
import io
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from scipy.interpolate import interp1d

# make sure python can find our other folders
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from interface import DEFAULT_CONFIG
import prediction_control.dashboard_bridge as bridge
from prediction_control.dashboard_bridge import run_simulation
from prediction_control.dataset_pipeline import REQUIRED_DATA_COLUMNS, build_path_dataframe
from prediction_control.hao_model_runtime import HaoMixtureGPRRuntime

st.set_page_config(page_title="Seed Release Dashboard", layout="wide")

# these get filled in once the data is loaded
LATERAL_LINES = None
LATERAL_GRID = None
DEPTHS_CM = None


# keeps the loaded data and model so we dont reload them on every click
@st.cache_resource
def store():
    return {}


# gets the data and model for the file we are using
def get_data(key):
    return store()[key]


# moisture across the field at the shallow depth, for every lateral line
@st.cache_data(show_spinner=False)
def base_rows(key):
    df, model = get_data(key)
    lines = []
    for lat in LATERAL_LINES:
        rows = df[(np.isclose(df.depth_cm, 5)) & (np.isclose(df.lateral_distance_m, lat))]
        rows = rows.sort_values("longitudinal_distance_m")
        lines.append(rows["provided_moisture_vwc_pct"].to_numpy())
    lines = np.vstack(lines)
    out = np.empty((len(LATERAL_GRID), lines.shape[1]))
    # fill in the lines between the measured ones
    for i, lat in enumerate(LATERAL_GRID):
        for j in range(lines.shape[1]):
            out[i, j] = np.interp(lat, LATERAL_LINES, lines[:, j])
    return out


# predicted moisture along the seeder line at every depth
@st.cache_data(show_spinner=False)
def moisture_section(key, lateral_m):
    df, model = get_data(key)
    path = build_path_dataframe(df, lateral_m, 5.0)
    pos = path["longitudinal_distance_m"].to_numpy(float)
    base = path["provided_moisture_vwc_pct"].to_numpy(float)
    D, P = np.meshgrid(DEPTHS_CM, pos, indexing="ij")
    X = np.column_stack([P.ravel(), np.full(P.size, lateral_m), D.ravel(), np.tile(base, len(DEPTHS_CM))])
    pred, dom, w = model.predict_batch(X)
    return pos, pred.reshape(D.shape)


# predicted moisture for the whole block, only every 8th position so it stays fast
@st.cache_data(show_spinner=False)
def moisture_volume(key, step=8):
    df, model = get_data(key)
    pos_all = np.sort(df["longitudinal_distance_m"].unique())
    pos = pos_all[np.arange(0, len(pos_all), step)]
    base = base_rows(key)[:, np.arange(0, len(pos_all), step)]
    D, L, P = np.meshgrid(DEPTHS_CM, LATERAL_GRID, pos, indexing="ij")
    X = np.column_stack([P.ravel(), L.ravel(), D.ravel(), np.broadcast_to(base, D.shape).ravel()])
    pred, dom, w = model.predict_batch(X)
    return pos, pred.reshape(D.shape)


# runs the seeder along the field using the control logic
@st.cache_data(show_spinner=False)
def run_pass(
    key,
    lateral_m,
    spacing_m,
    dt_s,
    tau_s,
    min_m,
    max_m,
    min_d,
    max_d,
    sensor_offset_m,
):
    df, model = get_data(key)

    bridge._DATASET, bridge._MODEL = df, model
    bridge._estimate_lateral = lambda *a, **k: float(lateral_m)

    path = build_path_dataframe(df, lateral_m, 5.0)
    speed = path["tractor_speed_kmh"].to_numpy(float) / 3.6

    log, rel = run_simulation(
        path["longitudinal_distance_m"].to_numpy(float),
        path["provided_moisture_vwc_pct"].to_numpy(float),
        path["time_s"].to_numpy(float),
        speed,
        spacing_m,
        dt_s,
        tau_s,
        min_m,
        max_m,
        min_d,
        max_d,
        sensor_offset_m,
    )

    log["error_mm"] = log["actuator_depth_mm"] - log["target_depth_mm"]
    rel["error_mm"] = rel["actuator_depth_mm"] - rel["target_depth_mm"]

    return log, rel


# works out the depth error and the horizontal error for a sample of seeds
def seeding_errors(rel, pos, prof, target, min_d_mm, max_d_mm, margin_m, max_seeds=1200):
    # take every nth seed so it doesnt take too long
    r = rel.iloc[::max(1, len(rel) // max_seeds)].copy()
    cols = np.clip(np.searchsorted(pos, r["position_m"].to_numpy()), 0, len(pos) - 1)
    seed_depth = np.clip(r["target_depth_mm"].to_numpy() / 10.0, DEPTHS_CM[0], DEPTHS_CM[-1])
    f = interp1d(DEPTHS_CM, prof[:, cols], axis=0)
    # moisture where each seed actually goes
    m_seed = np.array([float(np.interp(seed_depth[k], DEPTHS_CM, prof[:, cols[k]])) for k in range(len(cols))])
    # best depth = the depth where moisture is closest to the target
    lo = max(DEPTHS_CM[0], min_d_mm / 10.0)
    hi = min(DEPTHS_CM[-1], max_d_mm / 10.0)
    fine = np.linspace(lo, hi, 41) if hi > lo else np.array([lo])
    best_depth_mm = fine[np.argmin(np.abs(f(fine) - target), axis=0)] * 10.0
    # horizontal error = how far we move along the field (inside the margin) to get closest to the target
    step_m = float(np.median(np.diff(pos)))
    w = max(1, int(round(margin_m / step_m)))
    shift = np.zeros(len(cols))
    m_after = m_seed.copy()
    for k, c in enumerate(cols):
        a = max(0, c - w)
        b = min(len(pos), c + w + 1)
        window = np.array([np.interp(seed_depth[k], DEPTHS_CM, prof[:, j]) for j in range(a, b)])
        j = int(np.argmin(np.abs(window - target)))
        shift[k] = pos[a + j] - pos[c]
        m_after[k] = window[j]
    r["moisture_gap"] = m_seed - target
    r["best_depth_mm"] = best_depth_mm
    r["depth_error_mm"] = r["target_depth_mm"].to_numpy() - best_depth_mm
    r["horizontal_shift_m"] = shift
    r["moisture_gap_after_shift"] = m_after - target
    return r


# rounds a list of numbers so the json stays small
def rnd(a, k=2):
    return [round(float(v), k) for v in a]


# data sent to the animation
def build_payload(log, se, rel_t, pos, sec, top, vol, lateral_m):
    # only send 800 points of the log, the rest is not needed to draw it
    idx = np.linspace(0, len(log) - 1, 800).astype(int)
    vmin = float(min(sec.min(), top.min(), vol.min()))
    vmax = float(max(sec.max(), top.max(), vol.max()))
    return {
        "T": float(log["time_s"].max()), "xmax": float(pos.max()), "lat": float(lateral_m),
        "vmin": vmin, "vmax": vmax, "npos": int(len(pos)), "ndepth": int(sec.shape[0]),
        "depth0": float(DEPTHS_CM[0] * 10), "depth1": float(DEPTHS_CM[-1] * 10),
        "t": rnd(log["time_s"].to_numpy()[idx], 3), "x": rnd(log["position_m"].to_numpy()[idx], 3),
        "tgt": rnd(log["target_depth_mm"].to_numpy()[idx]), "act": rnd(log["actuator_depth_mm"].to_numpy()[idx]),
        "pm": rnd(log["predicted_moisture_pct"].to_numpy()[idx]), "mm": rnd(log["measured_moisture_pct"].to_numpy()[idx]),
        "rel_t": rnd(rel_t, 3),
        "sd_t": rnd(se["time_s"].to_numpy(), 3), "sd_x": rnd(se["position_m"].to_numpy(), 3),
        "sd_tgt": rnd(se["target_depth_mm"].to_numpy()), "sd_act": rnd(se["actuator_depth_mm"].to_numpy()),
        "sd_gap": rnd(se["moisture_gap"].to_numpy(), 3), "sd_best": rnd(se["best_depth_mm"].to_numpy()),
        "sd_shift": rnd(se["horizontal_shift_m"].to_numpy(), 3),
        "sec": rnd(sec.ravel()), "top": rnd(top.ravel()), "toprows": int(top.shape[0]),
    }


# data sent to the 3d model
def build_payload3d(se, vpos, vol, lateral_m, target):
    return {
        "target": float(target), "vmin": float(vol.min()), "vmax": float(vol.max()),
        "xmax": float(vpos.max()), "lat": float(lateral_m),
        "nd": int(vol.shape[0]), "nlat": int(vol.shape[1]), "nx": int(vol.shape[2]),
        "latmax": float(LATERAL_GRID[-1]), "depth0": float(DEPTHS_CM[0] * 10), "depth1": float(DEPTHS_CM[-1] * 10),
        "vpos": rnd(vpos, 2), "vol": rnd(vol.ravel()),
        "sx": rnd(se["position_m"].to_numpy(), 2), "sz": rnd(se["actuator_depth_mm"].to_numpy(), 1),
        "sbest": rnd(se["best_depth_mm"].to_numpy(), 1), "sshift": rnd(se["horizontal_shift_m"].to_numpy(), 2),
        "sgap": rnd(se["moisture_gap"].to_numpy(), 2),
    }


# shows an html page inside streamlit (older versions dont have st.iframe)
def show_page(page, height):
    if hasattr(st, "iframe"):
        st.iframe(page, height=height)
    else:
        components.html(page, height=height, scrolling=False)


# the html and javascript for the animation and the 3d model
HTML = r"""
<!doctype html><html><head><meta charset="utf-8">
<style>
/* colours for light and dark mode */
:root{--fg:#1f2430;--card:#f1effb;--muted:#667;--sky:#e6f1fb;--panel:#ffffff;--line:#d9d6ea}
@media (prefers-color-scheme: dark){:root{--fg:#e8e8ee;--card:#232736;--muted:#a0a4b5;--sky:#1d2733;--panel:#171a24;--line:#363a4d}}
body{margin:0;font-family:"Source Sans Pro",Arial,sans-serif;color:var(--fg);background:transparent}
/* layout of the buttons, canvases and boxes */
.bar{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:8px}
button,select{font:inherit;padding:5px 12px;border-radius:8px;border:1px solid var(--line);background:var(--card);color:var(--fg);cursor:pointer}
button.on{background:#6b5cf0;color:#fff;border-color:#6b5cf0}
input[type=range]{flex:1;min-width:160px}
canvas{width:100%;display:block;border-radius:10px;background:var(--panel)}
.cards{display:grid;grid-template-columns:repeat(6,1fr);gap:8px;margin:8px 0}
.card{background:var(--card);border-radius:10px;padding:6px 10px}
.card small{color:var(--muted);display:block;font-size:12px}
.card b{font-size:20px}
.key{display:flex;gap:16px;flex-wrap:wrap;font-size:13px;color:var(--muted);margin:6px 2px}
.dot{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:5px;vertical-align:middle}
@media (max-width:760px){.cards{grid-template-columns:repeat(3,1fr)}}
</style></head><body>
<div class="bar">
  <button id="play">Pause</button><button id="restart">Restart</button>
  <label>Speed <select id="speed"><option value="2">2×</option><option value="8" selected>8×</option><option value="20">20×</option><option value="50">50×</option></select></label>
  <button id="v3d" class="on">3D block</button><button id="vside">Side view</button>
  <input id="scrub" type="range" min="0" max="1000" value="0"><span id="clock"></span>
</div>
<canvas id="main"></canvas>
<canvas id="over" style="margin-top:6px"></canvas>
<div class="cards">
  <div class="card"><small>Distance</small><b id="c_x">-</b></div>
  <div class="card"><small>Soil moisture (predicted)</small><b id="c_m">-</b></div>
  <div class="card"><small>Depth the controller asks for</small><b id="c_t" style="color:#2e9e4f">-</b></div>
  <div class="card"><small>Where the actuator is</small><b id="c_a" style="color:#e0392b">-</b></div>
  <div class="card"><small>Gap (actuator - asked)</small><b id="c_g">-</b></div>
  <div class="card"><small>Seeds dropped</small><b id="c_s">-</b></div>
</div>
<div class="key">
  <span><span class="dot" style="background:#5b3a1e"></span>seed (where it landed)</span>
  <span><span class="dot" style="background:#e0392b"></span>actuator tip</span>
  <span><span class="dot" style="background:#2e9e4f"></span>depth the controller asked for</span>
  <span>Soil colour: <span style="color:#c6e6a8">dry</span> to <span style="color:#1d5fa8">wet</span></span>
</div>
<canvas id="charts"></canvas>
<script>
// all the numbers from python come in here
const D = __DATA__;
// basic values and the state of the animation
const N = D.t.length, T = D.T, X = D.xmax;
let now = 0, playing = true, speed = 8, mode = '3d', lastTs = null;
// short way to get an element
const $ = id => document.getElementById(id);
// the three canvases and their drawing tools
const main = $('main'), over = $('over'), charts = $('charts');
const mc = main.getContext('2d'), oc = over.getContext('2d'), cc = charts.getContext('2d');
// height of each canvas in pixels
const H = {main: 400, over: 44, charts: 180};
let W = 800, dpr = 1;
// soil colours, light for dry and dark blue for wet
const STOPS = [[255,255,217],[199,233,180],[127,205,187],[65,182,196],[29,145,192],[34,94,168],[12,44,132]];
// turns a moisture value into a colour
function colour(v){
  let t = (v - D.vmin) / (D.vmax - D.vmin); t = Math.max(0, Math.min(1, t)) * (STOPS.length - 1);
  const i = Math.min(STOPS.length - 2, Math.floor(t)), f = t - i, a = STOPS[i], b = STOPS[i+1];
  return [a[0] + (b[0]-a[0])*f, a[1] + (b[1]-a[1])*f, a[2] + (b[2]-a[2])*f];
}
// makes a small picture from the moisture numbers
function makeImage(values, w, h){
  const c = document.createElement('canvas'); c.width = w; c.height = h;
  const g = c.getContext('2d'), im = g.createImageData(w, h);
  for (let i = 0; i < w*h; i++){ const k = colour(values[i]); im.data[4*i] = k[0]; im.data[4*i+1] = k[1]; im.data[4*i+2] = k[2]; im.data[4*i+3] = 255; }
  g.putImageData(im, 0, 0); return c;
}
// the side cut of the soil and the top of the field as pictures
const secImg = makeImage(D.sec, D.npos, D.ndepth);
const topImg = makeImage(D.top, D.npos, D.toprows);
// which row of the top picture is the seeder line
const latIndex = Math.round(D.lat / 2.5);
// get the theme colours so it works in dark mode too
function fg(){ return getComputedStyle(document.body).color; }
function muted(){ return getComputedStyle(document.documentElement).getPropertyValue('--muted'); }
function skyCol(){ return getComputedStyle(document.documentElement).getPropertyValue('--sky'); }
// finds the data row for a time
function idxAt(t){ return Math.max(0, Math.min(N - 1, Math.round(t / T * (N - 1)))); }
// counts how many seeds have dropped by a time
function countDropped(t){ let lo = 0, hi = D.rel_t.length; while (lo < hi){ const m = (lo + hi) >> 1; if (D.rel_t[m] <= t) lo = m + 1; else hi = m; } return lo; }

// sets the canvas sizes
function resize(){
  dpr = window.devicePixelRatio || 1; W = document.body.clientWidth || 800;
  for (const [cv, ctx, h] of [[main, mc, H.main], [over, oc, H.over], [charts, cc, H.charts]]){
    cv.width = W * dpr; cv.height = h * dpr; cv.style.height = h + 'px'; ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }
  draw();
}

// draws the soil block, the seeds and the seeder arm
function drawMain(){
  const ctx = mc, i = idxAt(now), xnow = D.x[i], is3d = mode === '3d';
  const viewW = Math.min(40, X), x0 = Math.max(0, Math.min(X - viewW, xnow - viewW / 2));
  const left = 56, dx3 = is3d ? 90 : 0, dy3 = is3d ? 80 : 0;
  const Wpx = W - left - 20 - dx3, groundY = 100 + dy3 / 2, soilH = 230;
  const px = x => left + (x - x0) / viewW * Wpx;
  const py = d => groundY + d / D.depth1 * soilH * 0.98;
  ctx.clearRect(0, 0, W, H.main);
  ctx.fillStyle = skyCol(); ctx.fillRect(0, 0, W, groundY);
  // top face (the surface of the field, seen from the side of the block)
  const sx = x0 / X * D.npos, sw = viewW / X * D.npos;
  if (is3d && latIndex < D.toprows - 1){
    const rows = D.toprows - latIndex;
    ctx.save();
    ctx.beginPath(); ctx.moveTo(left, groundY); ctx.lineTo(left + Wpx, groundY); ctx.lineTo(left + Wpx + dx3, groundY - dy3); ctx.lineTo(left + dx3, groundY - dy3); ctx.closePath(); ctx.clip();
    ctx.transform(Wpx / sw, 0, dx3 / rows, -dy3 / rows, left, groundY);
    ctx.imageSmoothingEnabled = false;
    ctx.drawImage(topImg, sx, latIndex, sw, rows, 0, 0, sw, rows);
    ctx.restore();
    ctx.strokeStyle = 'rgba(0,0,0,.35)'; ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(left, groundY); ctx.lineTo(left + dx3, groundY - dy3); ctx.lineTo(left + Wpx + dx3, groundY - dy3); ctx.lineTo(left + Wpx, groundY); ctx.stroke();
    ctx.fillStyle = muted(); ctx.font = '12px Arial'; ctx.textAlign = 'left';
    ctx.fillText('field surface, across the field', left + dx3 + 8, groundY - dy3 + 14);
  }
  // soil: front face is a cut through the field along the seeder's line
  ctx.save(); ctx.beginPath(); ctx.rect(left, groundY, Wpx, soilH); ctx.clip(); ctx.imageSmoothingEnabled = true;
  const yTop = py(0), y1 = py(D.depth0 - 5), y2 = py(D.depth1 + 5), yB = groundY + soilH;
  ctx.drawImage(secImg, sx, 0, sw, 1, left, yTop, Wpx, y1 - yTop);
  ctx.drawImage(secImg, sx, 0, sw, D.ndepth, left, y1, Wpx, y2 - y1);
  ctx.drawImage(secImg, sx, D.ndepth - 1, sw, 1, left, y2, Wpx, yB - y2);
  ctx.restore();
  ctx.strokeStyle = '#6b4a2b'; ctx.lineWidth = 3; ctx.beginPath(); ctx.moveTo(left, groundY); ctx.lineTo(left + Wpx, groundY); ctx.stroke();
  ctx.strokeStyle = 'rgba(0,0,0,.35)'; ctx.lineWidth = 1; ctx.strokeRect(left, groundY, Wpx, soilH);
  // depth axis
  ctx.fillStyle = fg(); ctx.font = '12px Arial'; ctx.textAlign = 'right';
  for (const d of [0, 50, 100, 150]){ const y = py(d); ctx.fillText(d + ' mm', left - 6, y + 4); ctx.strokeStyle = 'rgba(255,255,255,.35)'; ctx.beginPath(); ctx.moveTo(left, y); ctx.lineTo(left + 6, y); ctx.stroke(); }
  ctx.textAlign = 'center';
  const tick = viewW > 30 ? 10 : 5;
  for (let m = Math.ceil(x0 / tick) * tick; m <= x0 + viewW; m += tick){ ctx.fillText(m + ' m', px(m), groundY + soilH + 16); }
  // seeds
  for (let k = 0; k < D.sd_t.length; k++){
    if (D.sd_t[k] > now) break;
    const x = D.sd_x[k]; if (x < x0 - 1 || x > x0 + viewW + 1) continue;
    const X1 = px(x), ya = py(D.sd_act[k]), yt = py(D.sd_tgt[k]);
    if (Math.abs(ya - yt) > 1.5){ ctx.strokeStyle = '#2e9e4f'; ctx.lineWidth = 2; ctx.beginPath(); ctx.moveTo(X1, ya); ctx.lineTo(X1, yt); ctx.stroke(); }
    ctx.fillStyle = '#5b3a1e'; ctx.strokeStyle = '#fff'; ctx.lineWidth = 1.5; ctx.beginPath(); ctx.arc(X1, ya, 4.5, 0, 6.3); ctx.fill(); ctx.stroke();
  }
  // opener arm, wheel, markers
  const ax = px(xnow), tipY = py(D.act[i]), tgtY = py(D.tgt[i]);
  ctx.strokeStyle = '#333'; ctx.lineWidth = 6; ctx.lineCap = 'round'; ctx.beginPath(); ctx.moveTo(ax, groundY - 62); ctx.lineTo(ax, tipY); ctx.stroke();
  ctx.fillStyle = '#444'; ctx.beginPath(); ctx.arc(ax, groundY - 62, 15, 0, 6.3); ctx.fill();
  ctx.fillStyle = '#bbb'; ctx.beginPath(); ctx.arc(ax, groundY - 62, 5, 0, 6.3); ctx.fill();
  ctx.fillStyle = '#e0392b'; ctx.beginPath(); ctx.moveTo(ax - 9, tipY - 2); ctx.lineTo(ax + 9, tipY - 2); ctx.lineTo(ax, tipY + 14); ctx.closePath(); ctx.fill();
  ctx.strokeStyle = '#2e9e4f'; ctx.lineWidth = 3; ctx.beginPath(); ctx.arc(ax, tgtY, 9, 0, 6.3); ctx.stroke();
  ctx.strokeStyle = 'rgba(46,158,79,.7)'; ctx.setLineDash([5, 4]); ctx.lineWidth = 1.5; ctx.beginPath(); ctx.moveTo(left, tgtY); ctx.lineTo(left + Wpx, tgtY); ctx.stroke(); ctx.setLineDash([]);
  ctx.font = 'bold 12px Arial'; ctx.textAlign = 'left';
  ctx.fillStyle = '#2e9e4f'; ctx.fillText('asked for ' + D.tgt[i].toFixed(0) + ' mm', ax + 14, tgtY - 8);
  ctx.fillStyle = '#e0392b'; ctx.fillText('actuator ' + D.act[i].toFixed(0) + ' mm', ax + 14, tipY + 18);
  ctx.fillStyle = fg(); ctx.font = '13px Arial'; ctx.textAlign = 'right';
  ctx.fillText('Seeder moving right (showing a ' + viewW.toFixed(0) + ' m window)', W - 14, 20);
}

// draws the bar under the picture that shows the whole field
function drawOver(){
  const ctx = oc; ctx.clearRect(0, 0, W, H.over);
  const left = 56, Wpx = W - left - 20;
  ctx.imageSmoothingEnabled = false; ctx.drawImage(secImg, 0, 0, D.npos, 1, left, 8, Wpx, 20);
  const i = idxAt(now), xnow = D.x[i], viewW = Math.min(40, X), x0 = Math.max(0, Math.min(X - viewW, xnow - viewW / 2));
  ctx.strokeStyle = fg(); ctx.lineWidth = 1.5; ctx.strokeRect(left + x0 / X * Wpx, 6, viewW / X * Wpx, 24);
  ctx.fillStyle = '#e0392b'; ctx.fillRect(left + xnow / X * Wpx - 1.5, 4, 3, 28);
  ctx.fillStyle = muted(); ctx.font = '12px Arial'; ctx.textAlign = 'left'; ctx.fillText('Whole pass (0 to ' + X.toFixed(0) + ' m): surface moisture. Click to jump.', left, 41);
}

// draws one small line chart
function panel(ctx, x, y, w, h, title, xs, series, xmax, ymin, ymax, cursorX, flip, unit){
  ctx.fillStyle = fg(); ctx.font = 'bold 13px Arial'; ctx.textAlign = 'left'; ctx.fillText(title, x, y - 6);
  ctx.strokeStyle = 'rgba(128,128,128,.35)'; ctx.lineWidth = 1; ctx.strokeRect(x, y, w, h);
  const X_ = v => x + v / xmax * w, Y_ = v => flip ? y + (v - ymin) / (ymax - ymin) * h : y + h - (v - ymin) / (ymax - ymin) * h;
  ctx.fillStyle = muted(); ctx.font = '11px Arial'; ctx.textAlign = 'right';
  ctx.fillText(flip ? ymax.toFixed(0) : ymax.toFixed(1), x - 4, y + 10); ctx.fillText(flip ? ymin.toFixed(0) : ymin.toFixed(1), x - 4, y + h);
  ctx.textAlign = 'center'; ctx.fillText(unit, x + w / 2, y + h + 14);
  if (ymin < 0 && ymax > 0){ ctx.strokeStyle = 'rgba(128,128,128,.6)'; ctx.beginPath(); ctx.moveTo(x, Y_(0)); ctx.lineTo(x + w, Y_(0)); ctx.stroke(); }
  for (const s of series){
    for (const pass of [0, 1]){
      ctx.save(); if (pass){ ctx.beginPath(); ctx.rect(x, y, X_(cursorX) - x, h); ctx.clip(); }
      ctx.strokeStyle = s.col; ctx.globalAlpha = pass ? 1 : 0.28; ctx.lineWidth = pass ? 1.8 : 1.2; ctx.beginPath();
      for (let k = 0; k < xs.length; k++){ const px_ = X_(xs[k]), py_ = Y_(s.v[k]); if (k) ctx.lineTo(px_, py_); else ctx.moveTo(px_, py_); }
      ctx.stroke(); ctx.restore();
    }
  }
  ctx.strokeStyle = '#e0392b'; ctx.lineWidth = 1.5; ctx.beginPath(); ctx.moveTo(X_(cursorX), y); ctx.lineTo(X_(cursorX), y + h); ctx.stroke();
}
// works out the gap and the chart limits once
let gapArr = null, dMin, dMax, gMax, mMin, mMax;
function prep(){
  gapArr = D.act.map((a, k) => a - D.tgt[k]);
  const all = D.tgt.concat(D.act); dMin = Math.min(...all) - 2; dMax = Math.max(...all) + 2;
  gMax = Math.max(1, Math.max(...gapArr.map(Math.abs))); const mm = D.pm.concat(D.mm); mMin = Math.min(...mm); mMax = Math.max(...mm);
}
// draws the three charts at the bottom
function drawCharts(){
  const ctx = cc, i = idxAt(now); ctx.clearRect(0, 0, W, H.charts);
  const gap = 46, pw = (W - 3 * gap - 10) / 3, y = 26, h = 112;
  panel(ctx, gap, y, pw, h, 'Depth: asked for (green) vs actuator (red)', D.t, [{v: D.tgt, col: '#2e9e4f'}, {v: D.act, col: '#e0392b'}], T, dMin, dMax, D.t[i], true, 'time (s), depth in mm, deeper is lower');
  panel(ctx, 2 * gap + pw, y, pw, h, 'Gap: actuator minus asked-for depth', D.t, [{v: gapArr, col: '#6b5cf0'}], T, -gMax, gMax, D.t[i], false, 'time (s), gap in mm');
  panel(ctx, 3 * gap + 2 * pw, y, pw, h, 'Moisture: base (grey) vs predicted (blue)', D.x, [{v: D.mm, col: '#999999'}, {v: D.pm, col: '#2a6fd0'}], X, mMin, mMax, D.x[i], false, 'distance (m), moisture %');
}
// updates the numbers in the boxes
function cards(){
  const i = idxAt(now), g = D.act[i] - D.tgt[i];
  $('c_x').textContent = D.x[i].toFixed(1) + ' m'; $('c_m').textContent = D.pm[i].toFixed(2) + ' %';
  $('c_t').textContent = D.tgt[i].toFixed(1) + ' mm'; $('c_a').textContent = D.act[i].toFixed(1) + ' mm';
  $('c_g').textContent = (g > 0 ? '+' : '') + g.toFixed(2) + ' mm'; $('c_s').textContent = countDropped(now).toLocaleString();
  $('clock').textContent = now.toFixed(0) + ' / ' + T.toFixed(0) + ' s'; $('scrub').value = Math.round(now / T * 1000);
}
// redraws everything
function draw(){ drawMain(); drawOver(); drawCharts(); cards(); }
// animation loop, time moves forward when it is playing
function frame(ts){
  if (lastTs === null) lastTs = ts; const dt = (ts - lastTs) / 1000; lastTs = ts;
  if (playing){ now += dt * speed; if (now >= T){ now = T; playing = false; $('play').textContent = 'Play'; } draw(); }
  requestAnimationFrame(frame);
}
// buttons and the slider
$('play').onclick = () => { if (now >= T) now = 0; playing = !playing; $('play').textContent = playing ? 'Pause' : 'Play'; };
$('restart').onclick = () => { now = 0; playing = true; $('play').textContent = 'Pause'; draw(); };
$('speed').onchange = e => { speed = +e.target.value; };
$('scrub').oninput = e => { now = +e.target.value / 1000 * T; draw(); };
$('v3d').onclick = () => { mode = '3d'; $('v3d').className = 'on'; $('vside').className = ''; draw(); };
$('vside').onclick = () => { mode = 'side'; $('vside').className = 'on'; $('v3d').className = ''; draw(); };
// click on the bar to jump along the field
over.onclick = e => { const r = over.getBoundingClientRect(), f = (e.clientX - r.left - 56) / (r.width - 76); const xx = Math.max(0, Math.min(1, f)) * X; let b = 0; for (let k = 0; k < N; k++) if (Math.abs(D.x[k] - xx) < Math.abs(D.x[b] - xx)) b = k; now = D.t[b]; draw(); };
// start the animation
window.addEventListener('resize', resize);
prep(); resize(); requestAnimationFrame(frame);
</script></body></html>
"""

HTML3D = r"""
<!doctype html><html><head><meta charset="utf-8">
<style>
/* colours for light and dark mode */
:root{--fg:#1f2430;--card:#f1effb;--muted:#667;--panel:#ffffff;--line:#d9d6ea}
@media (prefers-color-scheme: dark){:root{--fg:#e8e8ee;--card:#232736;--muted:#a0a4b5;--panel:#171a24;--line:#363a4d}}
body{margin:0;font-family:"Source Sans Pro",Arial,sans-serif;color:var(--fg);background:transparent}
/* layout of the controls and boxes */
.bar{display:flex;gap:12px 16px;align-items:center;flex-wrap:wrap;margin-bottom:8px;font-size:14px}
.bar label{display:flex;gap:6px;align-items:center}
button{font:inherit;padding:5px 12px;border-radius:8px;border:1px solid var(--line);background:var(--card);color:var(--fg);cursor:pointer}
input[type=range]{width:120px}
canvas{width:100%;display:block;border-radius:10px;background:var(--panel);cursor:grab}
#info{min-height:40px;font-size:14px;margin:6px 2px}
#stat{display:flex;gap:10px;flex-wrap:wrap;margin:8px 0}
.st{background:var(--card);border-radius:10px;padding:6px 12px;font-size:13px;color:var(--muted)}
.st b{display:block;font-size:20px;color:var(--fg)}
.key{display:flex;gap:16px;flex-wrap:wrap;font-size:13px;color:var(--muted);margin:4px 2px}
.dot{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:5px;vertical-align:middle}
</style></head><body>
<div class="bar">
  <label>Field from <input id="x0" type="range" min="0" max="1000" value="0"><span id="x0v"></span></label>
  <label>to <input id="x1" type="range" min="0" max="1000" value="252"><span id="x1v"></span></label>
  <label><input id="px" type="checkbox" checked> Cut across the field at <input id="xc" type="range" min="0" max="1000" value="1000"><span id="xcv"></span></label>
  <label><input id="py" type="checkbox" checked> Cut along the field at line <input id="yc" type="range" min="0" max="1000" value="500"><span id="ycv"></span></label>
  <label><input id="pz" type="checkbox" checked> Horizontal slice at depth <input id="zc" type="range" min="0" max="1000" value="1000"><span id="zcv"></span></label>
</div>
<div class="bar">
  <label><input id="hl" type="checkbox"> Highlight soil near the target moisture (±<span id="tolv"></span>%) <input id="tol" type="range" min="1" max="30" value="8"></label>
  <label><input id="sd" type="checkbox" checked> seeds</label>
  <label><input id="er" type="checkbox" checked> error lines</label>
  <button id="r_iso">3D view</button><button id="r_top">Top</button><button id="r_side">Side (along)</button><button id="r_front">Front (across)</button>
  <span style="color:var(--muted)">Drag to rotate, scroll to zoom, hover a seed.</span>
</div>
<div id="stat"></div>
<canvas id="c"></canvas>
<div id="info">Hover over a seed dot.</div>
<div class="key">
  <span>Colour = moisture, brown is dry and blue-green is wet.</span>
  <span><span class="dot" style="background:#fff;border:2px solid #111"></span>seed where it landed</span>
  <span><span class="dot" style="background:#ff8a00"></span>depth error (to the best depth)</span>
  <span><span class="dot" style="background:#e0399b"></span>horizontal error (shift to the best spot)</span>
</div>
<script>
// all the numbers from python come in here
const D = __DATA__;
// short way to get an element
const $ = id => document.getElementById(id);
// the canvas and its drawing tool
const cv = $('c'), g = cv.getContext('2d'), dpr = window.devicePixelRatio || 1;
// sizes of the moisture grid
const nd = D.nd, nl = D.nlat, nx = D.nx, dx = D.vpos[1] - D.vpos[0];
let W = 900, H = 660, yaw = -0.7, pitch = 0.62, zoom = 1, drag = null, hover = -1, hov = null;
// shape of the box on the screen
const AX = 1.7, AY = 0.75, AZ = 0.6;
// colour range, leaving out the extreme 2% at each end
const srt = [...D.vol].sort((a, b) => a - b), lo = srt[Math.floor(0.02 * srt.length)], hi = srt[Math.floor(0.98 * srt.length)];
// brown for dry up to blue-green for wet
const stops = [[84,48,5],[140,81,10],[191,129,45],[223,194,125],[246,232,195],[199,234,229],[128,205,193],[53,151,143],[1,102,94],[0,60,48]];
// turns a moisture value into a colour
function colour(v){ let t = (v - lo) / (hi - lo || 1); t = Math.max(0, Math.min(1, t)) * (stops.length - 1);
  const i = Math.min(stops.length - 2, Math.floor(t)), f = t - i, a = stops[i], b = stops[i + 1];
  return [a[0] + (b[0]-a[0])*f, a[1] + (b[1]-a[1])*f, a[2] + (b[2]-a[2])*f]; }
// moisture at one grid point
function V(i, j, k){ return D.vol[(i * nl + j) * nx + k]; }
// moisture between grid points
function samp(df, jf, kf){
  df = Math.max(0, Math.min(nd - 1, df)); jf = Math.max(0, Math.min(nl - 1, jf)); kf = Math.max(0, Math.min(nx - 1, kf));
  const i0 = Math.floor(df), j0 = Math.floor(jf), k0 = Math.floor(kf), i1 = Math.min(nd-1,i0+1), j1 = Math.min(nl-1,j0+1), k1 = Math.min(nx-1,k0+1);
  const a = df - i0, b = jf - j0, c = kf - k0; let s = 0;
  for (const [ii, wi] of [[i0, 1-a],[i1, a]]) for (const [jj, wj] of [[j0, 1-b],[j1, b]]) for (const [kk, wk] of [[k0, 1-c],[k1, c]]) s += V(ii,jj,kk) * wi * wj * wk;
  return s;
}
// slider values and the pictures for the three cut planes
let S = {}, tex = {};
// reads the sliders
function state(){
  const f = id => +$(id).value / 1000;
  let xa = f('x0') * D.xmax, xb = f('x1') * D.xmax; if (xa > xb) [xa, xb] = [xb, xa]; if (xb - xa < 4) xb = Math.min(D.xmax, xa + 4);
  const kA = Math.max(0, Math.round(xa / dx)), kB = Math.min(nx - 1, Math.max(kA + 1, Math.round(xb / dx)));
  xa = D.vpos[kA]; xb = D.vpos[kB];
  S = { xa, xb, kA, kB, xcN: f('xc'), ycN: f('yc'), zcN: f('zc'), tol: +$('tol').value / 20, hl: $('hl').checked };
}
// makes the picture for one cut plane
function mk(w, h, fn){
  const c = document.createElement('canvas'); c.width = w; c.height = h; const x = c.getContext('2d'), im = x.createImageData(w, h);
  for (let v = 0; v < h; v++) for (let u = 0; u < w; u++){
    const m = fn((u + 0.5) / w, (v + 0.5) / h); let c3 = colour(m);
    if (S.hl){ if (Math.abs(m - D.target) > S.tol){ const lum = 0.3*c3[0] + 0.6*c3[1] + 0.1*c3[2]; c3 = [0.2*c3[0] + 0.8*(lum*0.35+165), 0.2*c3[1] + 0.8*(lum*0.35+165), 0.2*c3[2] + 0.8*(lum*0.35+170)]; }
      else c3 = [255, 60, 150].map((r, q) => 0.55 * r + 0.45 * [c3[0], c3[1], c3[2]][q]); }
    const p = (v * w + u) * 4; im.data[p] = c3[0]; im.data[p+1] = c3[1]; im.data[p+2] = c3[2]; im.data[p+3] = 255; }
  x.putImageData(im, 0, 0); return c;
}
// rebuilds the pictures and the boxes when a slider moves
function rebuild(){
  state();
  const kf = u => S.kA + u * (S.kB - S.kA), wN = S.kB - S.kA + 1;
  const kx = S.kA + S.xcN * (S.kB - S.kA);
  tex.y = mk(wN, 44, (u, v) => samp(v * (nd - 1), S.ycN * (nl - 1), kf(u)));
  tex.x = mk(52, 44, (u, v) => samp(v * (nd - 1), u * (nl - 1), kx));
  tex.z = mk(wN, 52, (u, v) => samp(S.zcN * (nd - 1), v * (nl - 1), kf(u)));
  $('x0v').textContent = S.xa.toFixed(0) + ' m'; $('x1v').textContent = S.xb.toFixed(0) + ' m';
  $('xcv').textContent = (S.xa + S.xcN * (S.xb - S.xa)).toFixed(0) + ' m'; $('ycv').textContent = (S.ycN * D.latmax).toFixed(1) + ' m';
  $('zcv').textContent = (D.depth0 + S.zcN * (D.depth1 - D.depth0)).toFixed(0) + ' mm'; $('tolv').textContent = S.tol.toFixed(2);
  // stats
  let tot = 0, near = 0; for (let i = 0; i < nd; i++) for (let j = 0; j < nl; j++) for (let k = S.kA; k <= S.kB; k++){ tot++; if (Math.abs(V(i,j,k) - D.target) <= S.tol) near++; }
  let n = 0, de = 0, he = 0; for (let m = 0; m < D.sx.length; m++) if (D.sx[m] >= S.xa && D.sx[m] <= S.xb){ n++; de += Math.abs(D.sz[m] - D.sbest[m]); he += Math.abs(D.sshift[m]); }
  $('stat').innerHTML = `<div class="st">Target moisture<b>${D.target.toFixed(1)} %</b></div>` +
    `<div class="st">Soil within ±${S.tol.toFixed(2)}% of target<b>${(near / tot * 100).toFixed(0)} %</b></div>` +
    `<div class="st">Seeds in view (sampled)<b>${n}</b></div>` +
    `<div class="st">Mean depth error<b>${n ? (de / n).toFixed(0) : '-'} mm</b></div>` +
    `<div class="st">Mean horizontal error<b>${n ? (he / n).toFixed(2) : '-'} m</b></div>`;
  draw();
}
// sets the canvas size
function resize(){ const w = cv.parentElement.clientWidth || 900; W = w; H = 660; cv.width = w * dpr; cv.height = H * dpr; cv.style.height = H + 'px'; draw(); }
// turns a 3d point into a point on the screen using the rotation
function proj(x, y, z){
  const px = (x - 0.5) * AX, py = (y - 0.5) * AY, pz = -(z - 0.5) * AZ;
  const cy = Math.cos(yaw), sy = Math.sin(yaw), cp = Math.cos(pitch), sp = Math.sin(pitch);
  const x1 = px * cy - py * sy, y1 = px * sy + py * cy, y2 = y1 * cp - pz * sp, z2 = y1 * sp + pz * cp;
  const s = Math.min(W / 2.5, H / 1.6) * zoom;
  return [W / 2 - 30 + x1 * s, H / 2 + 10 - z2 * s, y2];
}
// cuts the planes into pieces so they overlap in the right order
function planes(){
  const L = [];
  if ($('py').checked) L.push({ t: tex.y, b: [0, S.ycN, 0], eu: [1, 0, 0], ev: [0, 0, 1], su: S.xcN, sv: S.zcN });
  if ($('px').checked) L.push({ t: tex.x, b: [S.xcN, 0, 0], eu: [0, 1, 0], ev: [0, 0, 1], su: S.ycN, sv: S.zcN });
  if ($('pz').checked) L.push({ t: tex.z, b: [0, 0, S.zcN], eu: [1, 0, 0], ev: [0, 1, 0], su: S.xcN, sv: S.ycN });
  const Q = [];
  for (const p of L) for (const [u0, u1] of [[0, p.su], [p.su, 1]]) for (const [v0, v1] of [[0, p.sv], [p.sv, 1]]){
    if (u1 - u0 < 1e-4 || v1 - v0 < 1e-4) continue;
    const uc = (u0 + u1) / 2, vc = (v0 + v1) / 2, c = p.b.map((q, i) => q + p.eu[i] * uc + p.ev[i] * vc);
    Q.push({ p, u0, u1, v0, v1, d: proj(c[0], c[1], c[2])[2] });
  }
  return Q.sort((a, b) => b.d - a.d);
}
// draws the box, the cut planes, the labels, the seeds and the colour bar
function draw(){
  if (!tex.y) return;
  g.setTransform(dpr, 0, 0, dpr, 0, 0); g.clearRect(0, 0, W, H); g.imageSmoothingEnabled = true;
  // box
  const ca = [[0,0,0],[1,0,0],[1,1,0],[0,1,0],[0,0,1],[1,0,1],[1,1,1],[0,1,1]].map(c => proj(c[0], c[1], c[2]));
  g.strokeStyle = 'rgba(130,130,150,.55)'; g.lineWidth = 1;
  [[0,1],[1,2],[2,3],[3,0],[4,5],[5,6],[6,7],[7,4],[0,4],[1,5],[2,6],[3,7]].forEach(e => { g.beginPath(); g.moveTo(ca[e[0]][0], ca[e[0]][1]); g.lineTo(ca[e[1]][0], ca[e[1]][1]); g.stroke(); });
  // slices
  for (const q of planes()){
    const p = q.p, O = proj(p.b[0], p.b[1], p.b[2]), U = proj(p.b[0] + p.eu[0], p.b[1] + p.eu[1], p.b[2] + p.eu[2]), Vv = proj(p.b[0] + p.ev[0], p.b[1] + p.ev[1], p.b[2] + p.ev[2]);
    g.save(); g.setTransform(dpr * (U[0] - O[0]), dpr * (U[1] - O[1]), dpr * (Vv[0] - O[0]), dpr * (Vv[1] - O[1]), dpr * O[0], dpr * O[1]);
    const e = 0.004; g.beginPath(); g.rect(q.u0 - e, q.v0 - e, q.u1 - q.u0 + 2 * e, q.v1 - q.v0 + 2 * e); g.clip(); g.drawImage(p.t, 0, 0, 1, 1); g.restore();
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
  }
  // axis labels
  g.fillStyle = 'rgba(120,120,140,.95)'; g.font = '12px sans-serif';
  for (const t of [0, 0.25, 0.5, 0.75, 1]){ const p = proj(t, 1, 1); g.fillText((S.xa + t * (S.xb - S.xa)).toFixed(0) + ' m', p[0] - 8, p[1] + 14); }
  for (const t of [0, 0.5, 1]){ const p = proj(0, 0, t); g.fillText((D.depth0 + t * (D.depth1 - D.depth0)).toFixed(0) + ' mm', p[0] - 44, p[1] + 4); }
  for (const t of [0, 0.5, 1]){ const p = proj(1, t, 1); g.fillText((t * D.latmax).toFixed(0) + ' m', p[0] + 30, p[1] + 14); }
  let p = proj(0.5, 1, 1); g.fillText('distance along the field', p[0] - 55, p[1] + 34);
  p = proj(1, 0.5, 1); g.fillText('across the field', p[0] + 6, p[1] + 32); p = proj(0, 0, 0.5); g.fillText('depth', p[0] - 50, p[1] + 20);
  // seeds
  const sp = [], ly = D.lat / D.latmax;
  let inwin = 0; for (let m = 0; m < D.sx.length; m++) if (D.sx[m] >= S.xa && D.sx[m] <= S.xb) inwin++;
  const every = Math.max(1, Math.ceil(inwin / 60)); let cnt = 0;
  if ($('sd').checked) for (let m = 0; m < D.sx.length; m++){
    if (D.sx[m] < S.xa || D.sx[m] > S.xb) continue; if ((cnt++) % every) continue;
    const xn = (D.sx[m] - S.xa) / (S.xb - S.xa), zz = (D.sz[m] - D.depth0) / (D.depth1 - D.depth0), zb = (D.sbest[m] - D.depth0) / (D.depth1 - D.depth0);
    const pp = proj(xn, ly, zz);
    if ($('er').checked){
      const pb = proj(xn, ly, zb); g.lineWidth = 2; g.strokeStyle = '#ff8a00'; g.beginPath(); g.moveTo(pp[0], pp[1]); g.lineTo(pb[0], pb[1]); g.stroke();
      const xh = Math.max(0, Math.min(1, (D.sx[m] + D.sshift[m] - S.xa) / (S.xb - S.xa))), ph = proj(xh, ly, zz);
      g.strokeStyle = '#e0399b'; g.beginPath(); g.moveTo(pp[0], pp[1]); g.lineTo(ph[0], ph[1]); g.stroke();
    }
    sp.push([pp[0], pp[1], m]);
  }
  for (const q of sp){ g.beginPath(); g.arc(q[0], q[1], q[2] === hover ? 7 : 4.5, 0, 6.3); g.fillStyle = '#fff'; g.fill(); g.lineWidth = 2; g.strokeStyle = '#111'; g.stroke(); }
  cv._sp = sp;
  // colour bar with target tick
  const bx = W - 70, by = 50, bh = 240;
  for (let k = 0; k < bh; k++){ const c = colour(hi - k / bh * (hi - lo)); g.fillStyle = 'rgb(' + c.map(Math.round).join(',') + ')'; g.fillRect(bx, by + k, 18, 1.5); }
  g.fillStyle = 'rgba(120,120,140,.98)'; g.font = '12px sans-serif'; g.textAlign = 'left';
  g.fillText(hi.toFixed(1) + '% wet', bx - 2, by - 8); g.fillText(lo.toFixed(1) + '% dry', bx - 2, by + bh + 14);
  const ty = by + (hi - Math.max(lo, Math.min(hi, D.target))) / (hi - lo) * bh;
  g.strokeStyle = '#e0399b'; g.lineWidth = 2; g.beginPath(); g.moveTo(bx - 6, ty); g.lineTo(bx + 24, ty); g.stroke(); g.fillStyle = '#e0399b'; g.fillText('target ' + D.target.toFixed(1) + '%', bx - 6, ty - 5);
}
// mouse: drag to rotate, hover on a seed, scroll to zoom
cv.onmousedown = e => { drag = [e.clientX, e.clientY, yaw, pitch]; cv.style.cursor = 'grabbing'; };
window.onmouseup = () => { drag = null; cv.style.cursor = 'grab'; };
cv.onmousemove = e => {
  const r = cv.getBoundingClientRect();
  if (drag){ yaw = drag[2] + (e.clientX - drag[0]) * 0.008; pitch = Math.max(-0.1, Math.min(1.5, drag[3] + (e.clientY - drag[1]) * 0.008)); draw(); return; }
  const mx = e.clientX - r.left, my = e.clientY - r.top; let b = -1, bd = 120;
  for (const q of (cv._sp || [])){ const d = (q[0]-mx)**2 + (q[1]-my)**2; if (d < bd){ bd = d; b = q[2]; } }
  if (b !== hover){ hover = b;
    $('info').innerHTML = b < 0 ? 'Hover over a seed dot.' :
      '<b>Seed at ' + D.sx[b].toFixed(1) + ' m</b>: landed at ' + D.sz[b].toFixed(0) + ' mm. Best depth for the target moisture is ' + D.sbest[b].toFixed(0) +
      ' mm, so <span style="color:#ff8a00"><b>depth error = ' + (D.sz[b]-D.sbest[b]).toFixed(0) + ' mm</b></span>. The best spot along the field is ' +
      Math.abs(D.sshift[b]).toFixed(2) + ' m ' + (D.sshift[b] >= 0 ? 'ahead' : 'behind') + ', so <span style="color:#e0399b"><b>horizontal error = ' + Math.abs(D.sshift[b]).toFixed(2) + ' m</b></span>. Moisture there minus target: ' + D.sgap[b].toFixed(2) + ' %.';
    draw(); }
};
cv.onwheel = e => { e.preventDefault(); zoom = Math.max(0.5, Math.min(4, zoom * (e.deltaY < 0 ? 1.1 : 0.9))); draw(); };
// sliders and tick boxes
['x0','x1','xc','yc','zc','tol','hl'].forEach(id => $(id).oninput = rebuild);
['px','py','pz','sd','er'].forEach(id => $(id).oninput = draw);
// buttons for the different views
const view = (y, p) => () => { yaw = y; pitch = p; draw(); };
$('r_iso').onclick = view(-0.7, 0.62); $('r_top').onclick = view(0, 1.5); $('r_side').onclick = view(0, 0); $('r_front').onclick = view(1.5708, 0);
// start
window.addEventListener('resize', resize); resize(); rebuild();
</script></body></html>
"""


# ---- sidebar: data ----
st.sidebar.header("Data")
# optional upload, if nothing is uploaded we use the default files
data_file = st.sidebar.file_uploader("Upload dataset CSV (optional)", type=["csv"])

DEFAULT_CSV = ROOT / "data" / "integration" / "final_semi_synthetic_winter_wheat_v2.csv"
DEFAULT_MODEL = ROOT / "models" / "hao_mixture_gpr_runtime.joblib"
data_bytes = data_file.getvalue() if data_file is not None else DEFAULT_CSV.read_bytes()
# the key changes when the file changes, so results are recalculated
key = hashlib.md5(data_bytes).hexdigest()

# load the data and the model the first time we see this file
if key not in store():
    try:
        df_new = pd.read_csv(io.BytesIO(data_bytes))
        missing = sorted(REQUIRED_DATA_COLUMNS - set(df_new.columns))
        if missing:
            st.error("The dataset is missing these columns: " + ", ".join(missing))
            st.stop()
        if not np.any(np.isclose(df_new["depth_cm"], 5.0)):
            st.error("The dataset needs rows at a depth of 5 cm.")
            st.stop()
        model_new = None
        # use the saved model for the default data, otherwise train a new one
        if data_file is None and DEFAULT_MODEL.exists():
            try:
                model_new = HaoMixtureGPRRuntime.load(DEFAULT_MODEL)
            except Exception:
                model_new = None
        if model_new is None:
            with st.spinner("Training the model (about 10 seconds)..."):
                model_new = HaoMixtureGPRRuntime().fit(df_new)
    except Exception as e:
        st.error("Could not load the data: " + str(e))
        st.stop()
    store()[key] = (df_new, model_new)

df, model = get_data(key)
bridge._DATASET, bridge._MODEL = df, model
st.sidebar.caption("Using: " + (data_file.name if data_file is not None else "default dataset"))

# lateral lines and depths come from the data
LATERAL_LINES = np.sort(df["lateral_distance_m"].unique().astype(float))
LATERAL_GRID = np.round(np.linspace(LATERAL_LINES.min(), LATERAL_LINES.max(), 13), 3)
depths = np.sort(df["depth_cm"].unique().astype(float))
DEPTHS_CM = np.linspace(depths.min(), depths.max(), 11)
default_lat = float(LATERAL_GRID[np.argmin(np.abs(LATERAL_GRID - np.median(LATERAL_LINES)))])
depth_min = int(round(depths.min() * 10))
depth_max = int(round(depths.max() * 10))

# ---- sidebar: settings ----
with st.sidebar.form("controls"):
    st.header("Settings")
    lateral_m = st.select_slider("Seeder line across the field (m)", options=[float(v) for v in LATERAL_GRID], value=default_lat)
    spacing_mm = st.slider("Seed spacing (mm)", 10, 60, 30)
    depth_range = st.slider("Seeding depth range (mm)", 0, depth_max + 10, (depth_min, depth_max))
    moist_range = st.slider("Moisture range mapped to depth (%)", 0.0, 15.0,
                            (float(DEFAULT_CONFIG["min_moisture"]), float(DEFAULT_CONFIG["max_moisture"])), step=0.5)
    tau_ms = st.slider("Actuator speed (time constant, ms)", 10, 500, 150, step=10)
    dt_ms = st.slider("Control loop step (ms)", 5, 100, 100, step=5)
    target_m = st.slider("Target moisture (%)", 1.0, 9.0, 3.5, step=0.1)
    margin_m = st.slider("Horizontal margin (m)", 0.25, 5.0, 1.0, step=0.25)
    # Added this from the control logic
    sensor_offset_m = st.slider("Sensor offset (m)", 0.0, 2.0, float(DEFAULT_CONFIG["sensor_offset_m"]), 0.05)
    submitted = st.form_submit_button(
      "Run Simulation",
      type="primary",
    )

# settings in the units the simulation wants (seconds and metres)
params = (lateral_m, spacing_mm / 1000, dt_ms / 1000, tau_ms / 1000,
          moist_range[0], moist_range[1], depth_range[0], depth_range[1], sensor_offset_m)

# ---- main page ----
st.title("Dynamic Moisture-Triggered Seed Release")

if "simulation_started" not in st.session_state:
    st.session_state["simulation_started"] = False

if submitted:
    st.session_state["simulation_started"] = True

if not st.session_state["simulation_started"]:
    st.info(
        "Configure the settings in the sidebar, then click "
        "'Run Simulation' to start."
    )
    st.stop()

# run the simulation
with st.spinner("Running the seeder..."):
    pos, sec = moisture_section(key, lateral_m)
    log, rel = run_pass(key, *params)

# numbers at the top
err = log["error_mm"].to_numpy()
spacing = rel["position_m"].diff().dropna() * 1000
c = st.columns(5)
c[0].metric("Seeds released", f"{len(rel):,}")
c[1].metric("Mean spacing", f"{spacing.mean():.2f} mm", f"target {spacing_mm} mm")
c[2].metric("Mean actuator gap", f"{np.abs(err).mean():.2f} mm")
c[3].metric("Largest gap", f"{np.abs(err).max():.2f} mm")
c[4].metric("Within 1 mm", f"{(np.abs(err) <= 1).mean() * 100:.0f}%")

tab_anim, tab_3d, tab_err, tab_data = st.tabs(["Animation", "3D moisture model", "Seeding errors", "Release log"])

# tab 1: animation
with tab_anim:
    # errors for a small sample of seeds, used by both the animation and the 3d model
    seeds = rel.iloc[::max(1, len(rel) // 250)]
    se = seeding_errors(seeds, pos, sec, target_m, params[6], params[7], margin_m, max_seeds=1000)
    vpos, vol = moisture_volume(key)
    payload = build_payload(log, se, rel["time_s"].to_numpy(), pos, sec, base_rows(key), vol, lateral_m)
    show_page(HTML.replace("__DATA__", json.dumps(payload)), 1010)

# tab 2: 3d moisture model
with tab_3d:
    show_page(HTML3D.replace("__DATA__", json.dumps(build_payload3d(se, vpos, vol, lateral_m, target_m))), 980)

# tab 3: the two errors for every sampled seed
with tab_err:
    errs = seeding_errors(rel, pos, sec, target_m, params[6], params[7], margin_m)
    e = st.columns(3)
    e[0].metric("Depth error", f"{errs['depth_error_mm'].abs().mean():.1f} mm")
    e[1].metric("Horizontal shift", f"{errs['horizontal_shift_m'].abs().mean():.2f} m")
    e[2].metric("Moisture gap to target", f"{errs['moisture_gap'].abs().mean():.2f} %")
    # one histogram for each error
    h = st.columns(3)
    charts = [(h[0], "moisture_gap", "Moisture minus target (%)"),
              (h[1], "depth_error_mm", "Depth error: chosen minus best (mm)"),
              (h[2], "horizontal_shift_m", "Horizontal shift to best spot (m)")]
    for col, name, title in charts:
        counts, edges = np.histogram(errs[name], bins=30)
        col.markdown("**" + title + "**")
        col.bar_chart(pd.DataFrame({"seeds": counts}, index=np.round((edges[:-1] + edges[1:]) / 2, 2)), height=220)
    # chosen depth against the best depth along the field
    st.markdown("**Chosen depth vs best depth along the field (mm)**")
    line = errs.set_index("position_m")[["target_depth_mm", "best_depth_mm"]]
    line = line.rename(columns={"target_depth_mm": "chosen", "best_depth_mm": "best"})
    st.line_chart(line, height=260)

# tab 4: table of every release
with tab_data:
    wanted = ["time_s", "position_m", "speed_m_s", "measured_moisture_pct", "predicted_moisture_pct",
              "target_depth_mm", "actuator_depth_mm", "error_mm", "dominant_expert"]
    st.dataframe(rel[[c for c in wanted if c in rel.columns]], height=340)
    buf = io.StringIO()
    rel.to_csv(buf, index=False)
    st.download_button("Download release log (CSV)", buf.getvalue(), file_name="release_log.csv", mime="text/csv")
