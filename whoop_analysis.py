import pandas as pd
import matplotlib.pyplot as plt

# ── Load data ──────────────────────────────────────────────────
cycles     = pd.read_csv("whoop_cycles.csv")
recoveries = pd.read_csv("whoop_recoveries.csv")

# ── Parse dates ────────────────────────────────────────────────
cycles["start"] = pd.to_datetime(cycles["start"], utc=True)

# ── Sort oldest → newest ───────────────────────────────────────
cycles = cycles.sort_values("start").reset_index(drop=True)

# ── Join cycles + recoveries on cycle_id ──────────────────────
# This merges the two tables so each row has both strain AND recovery score
df = cycles.merge(recoveries[["cycle_id", "recovery_score"]], on="cycle_id", how="left")

# ── Drop rows where either value is missing ────────────────────
df = df.dropna(subset=["strain", "recovery_score"])

print(f"Plotting {len(df)} days of data...\n")

# ── Build the chart ────────────────────────────────────────────
fig, ax1 = plt.subplots(figsize=(14, 5))

# Strain line (left axis)
ax1.plot(df["start"], df["strain"], color="#E8563A", linewidth=1.2, label="Strain")
ax1.set_ylabel("Strain", color="#E8563A")
ax1.tick_params(axis="y", labelcolor="#E8563A")

# Recovery line (right axis — separate scale)
ax2 = ax1.twinx()
ax2.plot(df["start"], df["recovery_score"], color="#4FC3F7", linewidth=1.2, label="Recovery %")
ax2.set_ylabel("Recovery Score (%)", color="#4FC3F7")
ax2.tick_params(axis="y", labelcolor="#4FC3F7")

# Labels and layout
ax1.set_xlabel("Date")
plt.title("Strain vs Recovery Score Over Time")
fig.legend(loc="upper left", bbox_to_anchor=(0.08, 0.92))
plt.tight_layout()
plt.savefig("strain_vs_recovery.png", dpi=150)
print("Chart saved as strain_vs_recovery.png")
plt.show()