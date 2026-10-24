#!/usr/bin/env python3
"""Post-flight summary figure from a session's telemetry.csv (run on the Mac after ./fetch.sh).
    pip install matplotlib numpy          (once)
    python3 analysis/plot_session.py data/sessions/<session> [-o flight.png]
Produces a one-page figure: altitude with markers, climb rate, pressure, temperature, tilt, light/UV, air quality."""
import argparse, csv, os, math
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ap = argparse.ArgumentParser()
ap.add_argument("session")
ap.add_argument("-o", "--out")
a = ap.parse_args()
csv_path = os.path.join(a.session, "telemetry.csv") if os.path.isdir(a.session) else a.session
rows = list(csv.DictReader(open(csv_path)))
def col(k):
    return np.array([float(r[k]) if r.get(k) not in (None, "") else np.nan for r in rows])
t = col("t_unix"); t0 = t[0]; tm = (t - t0) / 60.0
markers = []
mp = os.path.join(os.path.dirname(csv_path), "markers.csv")
if os.path.exists(mp):
    markers = [(float(r["t_unix"]), r["note"]) for r in csv.DictReader(open(mp))]

panels = [
    ("Altitude (m, relative)", [("altitude_m", "altitude")]),
    ("Climb rate (m/s)", [("vspeed_mps", "v")]),
    ("Pressure (hPa)", [("pressure_hpa", "p")]),
    ("Temperature (°C)", [("temp_c", "T")]),
    ("Tilt (°)", [("pitch_deg", "pitch"), ("roll_deg", "roll"), ("tilt_deg", "total")]),
    ("Light (%) / UV index ×10", [("light_pct", "light"), ("uv_index", "UV×10")]),
    ("Air quality", [("aq_raw", "AQ raw"), ("eco2_ppm", "eCO2 ppm"), ("tvoc_ppb", "TVOC ppb")]),
]
colors = ["#2a78d6", "#eb6834", "#1baf7a"]
panels = [(title, [(k, l) for k, l in series if not np.all(np.isnan(col(k)))]) for title, series in panels]
panels = [p for p in panels if p[1]]
fig, axes = plt.subplots(len(panels), 1, figsize=(11, 2.2 * len(panels)), sharex=True)
axes = np.atleast_1d(axes)
for ax, (title, series) in zip(axes, panels):
    for i, (k, label) in enumerate(series):
        y = col(k)
        if k == "uv_index": y = y * 10
        ax.plot(tm, y, color=colors[i % 3], lw=1.2, label=label)
    ax.set_ylabel(title, fontsize=9); ax.grid(alpha=0.25)
    if len(series) > 1: ax.legend(fontsize=8, loc="upper left", ncol=len(series), frameon=False)
    for mt, note in markers:
        ax.axvline((mt - t0) / 60, color="#eb6834", ls="--", lw=0.8)
    if title.startswith("Altitude"):
        for mt, note in markers:
            ax.text((mt - t0) / 60, ax.get_ylim()[1], note, fontsize=7, color="#eb6834", va="top", rotation=90)
axes[-1].set_xlabel("minutes since start")
alt = col("altitude_m")
peak = np.nanmax(alt) if not np.all(np.isnan(alt)) else float("nan")
fig.suptitle("%s   peak %.1f m   %d samples over %.1f min" % (os.path.basename(os.path.dirname(csv_path)), peak, len(rows), tm[-1]), fontsize=11)
fig.tight_layout()
out = a.out or os.path.join(os.path.dirname(csv_path), "flight.png")
fig.savefig(out, dpi=130)
print("wrote", out, "peak altitude %.1f m" % peak)
