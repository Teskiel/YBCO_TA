# -*- coding: utf-8 -*-
"""新旧数据集对比分析 + 生成对比图"""
import skrf as rf
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import os, pickle

cache_path = '../Auto_Sweep/experiment_data/~merged/output/_cache/_cache_20260609-0624__6-80K__full.pkl'
with open(cache_path, 'rb') as f:
    cache = pickle.load(f)

old_base = '../Auto_Sweep/experiment_data/accomplish_merged'
new_base = '../Auto_Sweep/experiment_data/~merged/20260609-0624__6-80K__full'
out_dir = 'output/comparison'
os.makedirs(out_dir, exist_ok=True)

temps_k = [6, 10, 20, 40, 50, 60, 70]
resonators = ['R1', 'R2', 'R3', 'R4', 'R5']
colors = ['#1f77b4', '#d62728', '#2ca02c', '#ff7f0e', '#9467bd']

old_f0 = {r: [] for r in resonators}
new_f0 = {r: [] for r in resonators}
old_dip = {r: [] for r in resonators}
new_dip = {r: [] for r in resonators}
valid_t = {r: [] for r in resonators}

for t in temps_k:
    t_str = f'{t:.0f}K'
    for r in resonators:
        if t in cache['collected'] and r in cache['collected'][t].get('identified', {}):
            n_f0 = cache['collected'][t]['identified'][r]['f0_ghz']
        else:
            continue
        new_f0[r].append(n_f0)

        old_dir = os.path.join(old_base, t_str, '-45dBm', '00mW')
        if not os.path.isdir(old_dir):
            continue
        s2p = [f for f in os.listdir(old_dir) if f.endswith('.s2p')]
        if not s2p:
            continue
        ntwk = rf.Network(os.path.join(old_dir, s2p[0]))
        freq = ntwk.f / 1e9
        s21 = 20 * np.log10(np.abs(ntwk.s[:,1,0]))
        w = 0.100
        mask = (freq >= n_f0 - w) & (freq <= n_f0 + w)
        if mask.sum() == 0:
            continue
        dip_idx = np.argmin(s21[mask])
        o_f0 = freq[mask][dip_idx]
        o_depth = np.percentile(s21[mask], 90) - s21[mask][dip_idx]

        new_dir = os.path.join(new_base, t_str, '-55dBm', '00mW')
        n_depth = 0
        if os.path.isdir(new_dir):
            s2p_n = [f for f in os.listdir(new_dir) if f.endswith('.s2p')]
            ntwk_n = rf.Network(os.path.join(new_dir, s2p_n[0]))
            freq_n = ntwk_n.f / 1e9
            s21_n = 20 * np.log10(np.abs(ntwk_n.s[:,1,0]))
            mask_n = (freq_n >= n_f0 - w) & (freq_n <= n_f0 + w)
            n_depth = np.percentile(s21_n[mask_n], 90) - np.min(s21_n[mask_n])

        valid_t[r].append(t)
        old_f0[r].append(o_f0)
        old_dip[r].append(o_depth)
        new_dip[r].append(n_depth)

# ============================================================
# Plot 1: f0(T) comparison
# ============================================================
fig, axes = plt.subplots(2, 3, figsize=(18, 12))
axes = axes.flatten()
for i, r in enumerate(resonators):
    ax = axes[i]
    if len(valid_t[r]) < 2:
        continue
    ax.plot(valid_t[r], old_f0[r], 's-', color=colors[i], lw=2, ms=8, label='OLD', alpha=0.8)
    ax.plot(valid_t[r], new_f0[r], 'o--', color=colors[i], lw=2, ms=8, label='NEW', alpha=0.8)
    ax.set_xlabel('Temperature (K)', fontsize=11)
    ax.set_ylabel('f0 (GHz)', fontsize=11)
    ax.set_title(f'{r}  f0(T)', fontsize=13, fontweight='bold')
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.25)
axes[5].set_visible(False)
fig.suptitle('f0(T) Comparison: OLD (accomplish_merged) vs NEW (20260609-0624)', fontsize=16, fontweight='bold')
fig.tight_layout()
fig.savefig(os.path.join(out_dir, 'f0_comparison_all.png'), dpi=150, bbox_inches='tight')
plt.close(fig)
print('[OK] f0_comparison_all.png')

# ============================================================
# Plot 2: Delta f0 vs T
# ============================================================
fig, ax = plt.subplots(figsize=(12, 7))
for i, r in enumerate(resonators):
    if len(valid_t[r]) < 2:
        continue
    delta_mhz = [(o - n) * 1000 for o, n in zip(old_f0[r], new_f0[r])]
    ax.plot(valid_t[r], delta_mhz, 'o-', color=colors[i], lw=2, ms=8, label=r)
ax.axhline(0, color='gray', ls='--', lw=0.8)
ax.set_xlabel('Temperature (K)', fontsize=12)
ax.set_ylabel('Delta f0 = OLD - NEW (MHz)', fontsize=12)
ax.set_title('Frequency Offset: OLD minus NEW', fontsize=14, fontweight='bold')
ax.legend(fontsize=10)
ax.grid(True, alpha=0.25)
fig.tight_layout()
fig.savefig(os.path.join(out_dir, 'delta_f0_vs_T.png'), dpi=150, bbox_inches='tight')
plt.close(fig)
print('[OK] delta_f0_vs_T.png')

# ============================================================
# Plot 3: Dip depth comparison
# ============================================================
fig, axes = plt.subplots(2, 3, figsize=(18, 12))
axes = axes.flatten()
for i, r in enumerate(resonators):
    ax = axes[i]
    if len(valid_t[r]) < 2:
        continue
    ax.plot(valid_t[r], old_dip[r], 's-', color=colors[i], lw=2, ms=8, label='OLD (-45dBm)', alpha=0.8)
    ax.plot(valid_t[r], new_dip[r], 'o--', color=colors[i], lw=2, ms=8, label='NEW (-55dBm)', alpha=0.8)
    ax.set_xlabel('Temperature (K)', fontsize=11)
    ax.set_ylabel('Dip Depth (dB)', fontsize=11)
    ax.set_title(f'{r}  Dip Depth', fontsize=13, fontweight='bold')
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.25)
axes[5].set_visible(False)
fig.suptitle('Resonator Dip Depth: OLD vs NEW', fontsize=16, fontweight='bold')
fig.tight_layout()
fig.savefig(os.path.join(out_dir, 'dip_depth_comparison.png'), dpi=150, bbox_inches='tight')
plt.close(fig)
print('[OK] dip_depth_comparison.png')

# ============================================================
# Print summaries for PPT
# ============================================================
print()
print('=== STABILITY PER TEMPERATURE (NEW dataset) ===')
for t in temps_k:
    n_res = 0
    dips = []
    for r in resonators:
        if t in cache['collected'] and r in cache['collected'][t].get('identified', {}):
            n_res += 1
            info = cache['collected'][t]['identified'][r]
            dips.append(info.get('dip_depth_db', 0))
    avg_dip = np.mean(dips) if dips else 0
    status = 'A' if avg_dip > 10 else ('B' if avg_dip > 5 else ('C' if avg_dip > 2 else 'D'))
    print(f'  T={t:>3d}K: {n_res}/5 resonators, avg dip={avg_dip:.1f} dB  Grade={status}')

print()
print('=== DELTA f0 (OLD - NEW) ===')
for t in temps_k:
    deltas = []
    for r in resonators:
        for j, vt in enumerate(valid_t[r]):
            if vt == t:
                deltas.append((old_f0[r][j] - new_f0[r][j]) * 1000)
                break
    if deltas:
        print(f'  T={t:>3d}K: mean={np.mean(deltas):.1f} MHz, range=[{min(deltas):.1f}, {max(deltas):.1f}] MHz')
