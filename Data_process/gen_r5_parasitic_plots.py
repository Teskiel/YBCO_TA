# -*- coding: utf-8 -*-
"""Generate R5 + parasitic dip analysis figures."""
import skrf as rf
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from scipy.signal import find_peaks
import os

base = '../Auto_Sweep/experiment_data/~merged/20260609-0624__6-80K__full'
out_dir = 'output/comparison'
os.makedirs(out_dir, exist_ok=True)

pv = '-55dBm'
pl = '00mW'
temps = ['6K','10K','20K','40K','50K','60K','70K','77K']

# Load all S21 traces
data = {}
for t in temps:
    d = os.path.join(base, t, pv, pl)
    s2p = [f for f in os.listdir(d) if f.endswith('.s2p')]
    ntwk = rf.Network(os.path.join(d, s2p[0]))
    data[t] = (ntwk.f / 1e9, 20 * np.log10(np.abs(ntwk.s[:,1,0])))

# ============================================================
# Plot 1: R5 at all temperatures — full overlay 4.4-5.4 GHz
# ============================================================
fig, ax = plt.subplots(figsize=(16, 8))
colors = plt.cm.RdYlBu(np.linspace(0.1, 0.9, len(temps)))

# Mark R5 and parasitic positions
r5_pos = {'6K':5.2515, '10K':5.2501, '20K':5.2386, '40K':5.1858,
          '50K':5.1339, '60K':5.0534, '70K':4.8891, '77K':4.6558}
parasitic_pos = 5.092  # fixed-frequency parasitic

for i, t in enumerate(temps):
    freq, s21 = data[t]
    mask = (freq >= 4.40) & (freq <= 5.40)
    ax.plot(freq[mask], s21[mask], color=colors[i], linewidth=0.8, alpha=0.9, label=t)

# Mark R5 trajectory
r5_freqs = [r5_pos[t] for t in temps]
# Find dip values at R5 positions
r5_dips = []
for t in temps:
    freq, s21 = data[t]
    mask = (freq >= r5_pos[t] - 0.03) & (freq <= r5_pos[t] + 0.03)
    r5_dips.append(np.min(s21[mask]))
ax.plot(r5_freqs, r5_dips, 'ko-', markersize=10, linewidth=2.5, label='R5 trajectory', zorder=10)

# Mark parasitic
ax.axvline(parasitic_pos, color='red', linestyle='--', linewidth=2, alpha=0.7, label=f'Parasitic ~{parasitic_pos:.3f} GHz')

# Annotate
ax.annotate('R5 crosses\nparasitic at\n50-60K', xy=(5.10, -12), fontsize=11, color='red',
            ha='center', bbox=dict(boxstyle='round', facecolor='white', alpha=0.85))

ax.set_xlabel('Frequency (GHz)', fontsize=13)
ax.set_ylabel('|S21| (dB)', fontsize=13)
ax.set_title('R5 Trajectory: Crossing a Fixed-Frequency Parasitic Dip', fontsize=15, fontweight='bold')
ax.legend(loc='lower left', fontsize=9, ncol=2)
ax.grid(True, alpha=0.2)
ax.set_xlim(4.40, 5.40)
fig.tight_layout()
fig.savefig(os.path.join(out_dir, 'R5_trajectory_vs_parasitic.png'), dpi=150, bbox_inches='tight')
plt.close(fig)
print('[OK] R5_trajectory_vs_parasitic.png')

# ============================================================
# Plot 2: Zoom into parasitic dip (~5.09 GHz) at all temperatures
# ============================================================
fig, ax = plt.subplots(figsize=(14, 7))
for i, t in enumerate(temps):
    freq, s21 = data[t]
    mask = (freq >= 5.00) & (freq <= 5.18)
    ax.plot(freq[mask], s21[mask], color=colors[i], linewidth=1.0, alpha=0.85, label=t)

ax.axvline(parasitic_pos, color='red', linestyle='--', linewidth=2.5, alpha=0.6)

# Mark dips in this range
for i, t in enumerate(temps):
    freq, s21 = data[t]
    mask = (freq >= 5.00) & (freq <= 5.18)
    f_win = freq[mask]
    s_win = s21[mask]
    peaks, props = find_peaks(-s_win, prominence=1.0, distance=30)
    for p in peaks:
        f0 = f_win[p]
        prom = props['prominences'][list(peaks).index(p)]
        if prom > 3.0:
            ax.plot(f0, s_win[p], 'o', color=colors[i], markersize=6)

ax.set_xlabel('Frequency (GHz)', fontsize=13)
ax.set_ylabel('|S21| (dB)', fontsize=13)
ax.set_title('Fixed-Frequency Parasitic Dip at ~5.09 GHz (All Temperatures)', fontsize=15, fontweight='bold')
ax.legend(loc='lower left', fontsize=8, ncol=4)
ax.grid(True, alpha=0.2)
fig.tight_layout()
fig.savefig(os.path.join(out_dir, 'parasitic_dip_detail.png'), dpi=150, bbox_inches='tight')
plt.close(fig)
print('[OK] parasitic_dip_detail.png')

# ============================================================
# Plot 3: R5 prominence vs parasitic prominence vs temperature
# ============================================================
fig, ax1 = plt.subplots(figsize=(12, 6))

parasitic_proms = []
r5_proms = []
r5_parasitic_gap = []
t_vals = []

for t in temps:
    freq, s21 = data[t]
    # R5 prominence
    mask = (freq >= r5_pos[t] - 0.05) & (freq <= r5_pos[t] + 0.05)
    peaks, props = find_peaks(-s21[mask], prominence=0.3, distance=10)
    r5p = props['prominences'][0] if len(peaks) > 0 else 0

    # Parasitic prominence
    mask = (freq >= 5.05) & (freq <= 5.13)
    peaks, props = find_peaks(-s21[mask], prominence=0.5, distance=30)
    pp = max(props['prominences']) if len(peaks) > 0 else 0

    gap = abs(r5_pos[t] - parasitic_pos) * 1000

    t_vals.append(float(t[:-1]))
    r5_proms.append(r5p)
    parasitic_proms.append(pp)
    r5_parasitic_gap.append(gap)

ax1.fill_between(t_vals, 0, parasitic_proms, alpha=0.2, color='red', label='Parasitic @5.09GHz')
ax1.plot(t_vals, parasitic_proms, 'rs-', linewidth=2, markersize=10, label='Parasitic prominence')
ax1.plot(t_vals, r5_proms, 'bo-', linewidth=2.5, markersize=12, label='R5 prominence')
ax1.set_xlabel('Temperature (K)', fontsize=13)
ax1.set_ylabel('Prominence (dB)', fontsize=13, color='black')
ax1.set_title('R5 vs Parasitic: Prominence Cross-over at 50-60K', fontsize=15, fontweight='bold')

# Add gap on twin axis
ax2 = ax1.twinx()
ax2.plot(t_vals, r5_parasitic_gap, 'g^--', linewidth=1.5, markersize=8, alpha=0.7, label='|R5 - Parasitic| gap')
ax2.set_ylabel('R5-Parasitic Gap (MHz)', fontsize=12, color='green')
ax2.axhline(50, color='green', linestyle=':', alpha=0.5, label='50 MHz threshold')
ax2.legend(loc='upper right', fontsize=9)

# Annotate cross-over zone
ax1.axvspan(45, 65, alpha=0.08, color='orange')
ax1.annotate('CROSS-OVER ZONE\nR5 passes through parasitic', xy=(55, 25), fontsize=12,
            ha='center', color='darkorange', fontweight='bold',
            bbox=dict(boxstyle='round', facecolor='white', alpha=0.85))

ax1.legend(loc='upper left', fontsize=10)
ax1.grid(True, alpha=0.2)
fig.tight_layout()
fig.savefig(os.path.join(out_dir, 'R5_vs_parasitic_prominence.png'), dpi=150, bbox_inches='tight')
plt.close(fig)
print('[OK] R5_vs_parasitic_prominence.png')

print('\nAll 3 figures generated in', out_dir)
