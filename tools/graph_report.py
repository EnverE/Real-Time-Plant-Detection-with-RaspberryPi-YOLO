"""
AgriDrone - test results graph generator.

Run this after a session to turn the CSV that receiver.py wrote into a
performance chart (network delay, YOLO time, jitter, FPS, pipeline breakdown).

Usage:
    python tools/graph_report.py                          # newest log in logs/
    python tools/graph_report.py logs/test_log_2024.csv   # a specific file

The chart is saved next to the CSV as <name>_graphs.png and also shown in a
window; close the window to end the script.
"""

import sys
import os
from pathlib import Path

import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config       # noqa: E402


# ------------------------------------------------------------------ load CSV
def load_csv(path=None):
    if path:
        path = Path(path)
        if not path.exists():
            sys.exit(f"No such file: {path}")
        return pd.read_csv(path), str(path)

    # Auto-pick the most recent log, looking in logs/ and the working directory
    cfg = config.load_config()
    search_dirs = [config.resolve_path(cfg["logging"]["csv_dir"]), Path.cwd()]
    files = [f for d in search_dirs for f in d.glob("test_log_*.csv")]
    if not files:
        sys.exit("No test_log_*.csv files found. Run a mission first.")

    latest = max(files, key=os.path.getmtime)
    print(f"Loading: {latest}")
    return pd.read_csv(latest), str(latest)

# ------------------------------------------------------------------ plot
def generate_graphs(df, source_file):
    # Relative time axis in seconds
    df["time_s"] = df["timestamp"] - df["timestamp"].iloc[0]

    fig = plt.figure(figsize=(16, 14))
    fig.patch.set_facecolor("#737680")

    title = f"Network Performance Analysis\nSource: {os.path.basename(source_file)}"
    fig.suptitle(title, color="#E8EAF0", fontsize=14, fontweight="bold", y=0.98)

    gs = gridspec.GridSpec(3, 2, figure=fig, hspace=0.45, wspace=0.35)

    STYLE = {
        "facecolor": "#1A1D27",
        "grid_color": "#2A2D3A",
        "text_color": "#E8EAF0",
        "muted_color": "#f0f5f1",
    }

    def styled_ax(ax, title, ylabel):
        ax.set_facecolor(STYLE["facecolor"])
        ax.set_title(title, color=STYLE["text_color"], fontsize=11, pad=8)
        ax.set_ylabel(ylabel, color=STYLE["muted_color"], fontsize=9)
        ax.set_xlabel("Time (s)", color=STYLE["muted_color"], fontsize=9)
        ax.tick_params(colors=STYLE["muted_color"])
        ax.spines[:].set_color(STYLE["grid_color"])
        ax.grid(True, color=STYLE["grid_color"], linewidth=0.5, linestyle="--")
        for spine in ax.spines.values():
            spine.set_linewidth(0.5)

    def stat_box(ax, series, unit="ms"):
        """Add min/avg/max annotation box to axis."""
        text = (
            f"min:  {series.min():.2f} {unit}\n"
            f"avg:  {series.mean():.2f} {unit}\n"
            f"max:  {series.max():.2f} {unit}\n"
            f"std:  {series.std():.2f} {unit}"
        )
        ax.text(
            0.99, 0.97, text,
            transform=ax.transAxes,
            fontsize=8, verticalalignment="top",
            horizontalalignment="right",
            color=STYLE["text_color"],
            bbox=dict(boxstyle="round,pad=0.4", facecolor="#0F1117",
                      edgecolor=STYLE["grid_color"], linewidth=0.5)
        )

    def set_ylim_tight(ax, series, padding_pct=0.3):
        """Set Y axis limits tightly around the data range for better visibility."""
        vmin = series.min()
        vmax = series.max()
        spread = vmax - vmin if vmax != vmin else vmax * 0.1 or 1
        ax.set_ylim(vmin - spread * padding_pct, vmax + spread * padding_pct)

    # ── 1. Network delay ────────────────────────────────────────────────────
    ax1 = fig.add_subplot(gs[0, 0])
    styled_ax(ax1, "Network Delay", "ms")
    raw = df["network_ms"]
    ax1.plot(df["time_s"], raw, color="#F59E0B", linewidth=1.5, label="network delay")
    ax1.axhline(raw.mean(), color="#F59E0B", linestyle="--", linewidth=1,
                alpha=0.6, label=f"avg {raw.mean():.1f} ms")
    ax1.legend(fontsize=8, labelcolor=STYLE["text_color"],
               facecolor=STYLE["facecolor"], edgecolor=STYLE["grid_color"])
    stat_box(ax1, raw)
    set_ylim_tight(ax1, raw)

    # ── 2. YOLO inference time ───────────────────────────────────────────────
    ax2 = fig.add_subplot(gs[0, 1])
    styled_ax(ax2, "YOLO Inference Time", "ms")
    raw = df["yolo_ms"]
    ax2.plot(df["time_s"], raw, color="#A78BFA", linewidth=1.5, label="YOLO time")
    ax2.axhline(raw.mean(), color="#A78BFA", linestyle="--", linewidth=1,
                alpha=0.6, label=f"avg {raw.mean():.1f} ms")
    ax2.legend(fontsize=8, labelcolor=STYLE["text_color"],
               facecolor=STYLE["facecolor"], edgecolor=STYLE["grid_color"])
    stat_box(ax2, raw)
    set_ylim_tight(ax2, raw)

    # ── 3. Jitter ────────────────────────────────────────────────────────────
    ax3 = fig.add_subplot(gs[1, 0])
    styled_ax(ax3, "Network Jitter", "ms")
    if "jitter_ms" in df.columns:
        raw = df["jitter_ms"]
        ax3.plot(df["time_s"], raw, color="#60A5FA", linewidth=1.5, label="jitter")
        ax3.axhline(raw.mean(), color="#60A5FA", linestyle="--", linewidth=1,
                    alpha=0.6, label=f"avg {raw.mean():.1f} ms")
        ax3.legend(fontsize=8, labelcolor=STYLE["text_color"],
                   facecolor=STYLE["facecolor"], edgecolor=STYLE["grid_color"])
        stat_box(ax3, raw)
        set_ylim_tight(ax3, raw)
    else:
        ax3.text(0.5, 0.5, "No jitter data", transform=ax3.transAxes,
                 ha="center", va="center", color=STYLE["muted_color"])

    # ── 4. FPS ───────────────────────────────────────────────────────────────
    ax4 = fig.add_subplot(gs[1, 1])
    styled_ax(ax4, "Frames Per Second", "fps")
    raw = df["fps"]
    ax4.plot(df["time_s"], raw, color="#34D399", linewidth=1.5, label="fps")
    ax4.axhline(raw.mean(), color="#34D399", linestyle="--", linewidth=1,
                alpha=0.6, label=f"avg {raw.mean():.1f} fps")
    ax4.legend(fontsize=8, labelcolor=STYLE["text_color"],
               facecolor=STYLE["facecolor"], edgecolor=STYLE["grid_color"])
    stat_box(ax4, raw, unit="fps")
    set_ylim_tight(ax4, raw)

    # ── 5. Pipeline breakdown bar chart — full width ──────────────────────────
    ax5 = fig.add_subplot(gs[2, :])
    styled_ax(ax5, "Average Pipeline Breakdown", "ms")
    ax5.set_xlabel("")

    categories = ["Network delay", "YOLO inference", "Total pipeline"]
    net_avg  = df["network_ms"].mean()
    yolo_avg = df["yolo_ms"].mean()
    total    = net_avg + yolo_avg
    values   = [net_avg, yolo_avg, total]
    colors   = ["#F59E0B", "#A78BFA", "#E8EAF0"]

    bars = ax5.bar(categories, values, color=colors, width=0.3, edgecolor=STYLE["grid_color"])
    for bar, val in zip(bars, values):
        ax5.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.1,
                 f"{val:.1f} ms", ha="center", va="bottom",
                 color=STYLE["text_color"], fontsize=10, fontweight="bold")
    ax5.tick_params(axis="x", colors=STYLE["text_color"])
    set_ylim_tight(ax5, pd.Series(values), padding_pct=0.2)

    # Save
    out_name = source_file.replace(".csv", "_graphs.png")
    plt.savefig(out_name, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
    print(f"[GRAPH] Saved to {out_name}")
    plt.show()


# ------------------------------------------------------------------ summary
def print_summary(df, source_file):
    print("\n" + "=" * 50)
    print("  AgriDrone — Session Summary")
    print("=" * 50)
    duration = df["timestamp"].iloc[-1] - df["timestamp"].iloc[0]
    print(f"  Duration:          {duration:.1f} s ({len(df)} frames)")
    print(f"\n  Network delay:")
    print(f"    Min:             {df['network_ms'].min():.2f} ms")
    print(f"    Avg:             {df['network_ms'].mean():.2f} ms")
    print(f"    Max:             {df['network_ms'].max():.2f} ms")
    print(f"    Std dev:         {df['network_ms'].std():.2f} ms")
    print(f"\n  YOLO inference:")
    print(f"    Min:             {df['yolo_ms'].min():.2f} ms")
    print(f"    Avg:             {df['yolo_ms'].mean():.2f} ms")
    print(f"    Max:             {df['yolo_ms'].max():.2f} ms")
    if "jitter_ms" in df.columns:
        print(f"\n  Jitter:")
        print(f"    Min:             {df['jitter_ms'].min():.2f} ms")
        print(f"    Avg:             {df['jitter_ms'].mean():.2f} ms")
        print(f"    Max:             {df['jitter_ms'].max():.2f} ms")
    print(f"\n  FPS:")
    print(f"    Min:             {df['fps'].min():.1f}")
    print(f"    Avg:             {df['fps'].mean():.1f}")
    print(f"    Max:             {df['fps'].max():.1f}")
    print(f"\n  Total pipeline:    {(df['network_ms'] + df['yolo_ms']).mean():.2f} ms avg")
    print("=" * 50 + "\n")


# ------------------------------------------------------------------ main
if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else None
    df, source = load_csv(path)
    if df.empty:
        sys.exit(f"{source} has no rows — the mission ended before any frame arrived.")
    print_summary(df, source)
    generate_graphs(df, source)