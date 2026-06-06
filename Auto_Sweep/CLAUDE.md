# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Automated YBCO superconductor measurement system. Orchestrates temperature sweeps (LakeShore 335 cryostat) and laser power sweeps (Keysight N7779C), capturing S-parameter data from a Keysight PXI VNA. Also includes a PyQt5 GUI for manual instrument control and preset management.

Core workflow: **stabilise temperature → sweep laser power levels → capture S2P from VNA → repeat at next temperature**.

Everything was refactored from a single 860-line monolithic script into a layered modular architecture following BDD/TDD methodology.

**Three experiment runners exist** — a CLI script (`power_sweep_auto.py`), a GUI-based background worker (`ExperimentWorker` in `ui/workers.py`), and a standalone temperature ramp controller (`lakeshore335_ramp.py`). They share the same algorithm modules (stability, PID) but have independent orchestration logic. Changes to experiment behaviour may need updating in all three.

## File Map

```
Auto_Sweep/
├── app.py                       # GUI entry point (PyQt5) — also defines global QSS theme
├── app_settings.json            # Auto-persisted settings (addresses, params, sweep config)
├── config.py                    # ALL experiment constants — single source of truth
├── stability_monitor.py         # Temperature stability algorithms (pure, no hardware)
├── pid_controller.py            # OLDER PID selector — SmartPIDController (used by CLI runner)
├── pid_parameters.py            # NEWER PID module — PIDZoneManager, SetpointCalculator, zone validation
├── temperature_diagnostics.py   # OLDER diagnostic analyser + AdaptivePIDAdjuster (used by CLI runner)
├── temperature_state_diagnostics.py # NEWER state classifier — 7 states, auto PID adjust, lockout/rollback
├── lakeshore_control.py         # LakeShore 335 driver + duck-typing helpers
├── laser_driver.py              # Keysight N7779C laser driver (production — used by GUI + CLI)
├── laser_control.py             # Older standalone laser driver (different API, different default addr)
├── vna_control.py               # VNA S2P save + HiSLIP discovery + connection utilities
├── power_sweep_auto.py          # CLI experiment orchestration (temp + laser power + VNA sweep)
├── lakeshore335_ramp.py         # Standalone temperature ramp controller (10K→80K, no VNA/laser)
├── test_vna.py                  # Standalone VNA connection + S2P test (at root level)
│
├── ui/                          # PyQt5 GUI (manual instrument control)
│   ├── main_window.py           # QStackedWidget router + 3 device threads + experiment thread
│   ├── dashboard_page.py        # Overview: 3 device cards, Connect All, temp sweep config
│   ├── laser_page.py            # Laser: 3×6 power grid (editable), wavelength, quick actions
│   ├── lakeshore_page.py        # LakeShore: live readings, loop controls, emergency
│   ├── vna_page.py              # VNA: frequency (start/stop/center/span), S-param, power, sweep
│   ├── workers.py               # LaserWorker, LakeShoreWorker, VNAWorker, ExperimentWorker
│   ├── experiment_stability_controller.py  # Simplified stability: fixed PID + setpoint overshoot state machine (used by ExperimentWorker)
│   └── widgets.py               # StatusLight, DeviceCard, PresetBar, PresetManager, TempSweepWidget
│
├── presets/                     # Per-device JSON preset files
│   ├── laser_default.json
│   ├── lakeshore_default.json
│   └── vna_default.json
│
├── tests/                       # BDD test suite (pytest)
│   ├── conftest.py              # Shared fixtures: mock VISA, synthetic temp data
│   ├── test_config.py           # Config integrity tests
│   ├── test_stability_monitor.py# Stability algorithm behaviour tests
│   ├── test_pid_controller.py   # SmartPIDController zone + setpoint tests
│   ├── test_pid_parameters.py   # PIDZoneManager, SetpointCalculator, zone validation tests
│   ├── test_vna_page.py         # VNAPage frequency spinbox range + sync logic tests
│   ├── test_lakeshore_safety.py # LakeShore cooling-safety interlock tests
│   ├── test_experiment_worker.py# ExperimentWorker sweep loop + abort tests
│   ├── test_temperature_state_diagnostics.py # 7-state classifier + PID adjustment tests
│   ├── test_lakeshore335_ramp.py# Ramp controller SCPI sequence + emergency stop tests
│   ├── test_button_styling.py    # Connect/Disconnect button color styling tests
│   ├── test_stability_fallback.py# ExperimentStabilityController state machine + integration tests
│   └── test_auto_reconnect.py    # Auto-reconnect mechanism detection + retry tests
│
├── testcode/                    # Standalone interactive debugging tools
│   ├── laser_test.py            # Laser interactive menu (imports laser_driver)
│   ├── vna_test.py              # VNA interactive menu (self-contained)
│   └── vna_probe.py             # Dumps ALL readable VNA parameters (SCPI probe)
│
├── experiment_data/             # Output from GUI experiment runs
│   └── {timestamp}/             #   e.g. 20260605_043104/
│       └── {target}K/           #     e.g. 6K/
│           └── actual_{temp}K/  #       e.g. actual_4.313K/
│               └── {dbm}dBm/    #         e.g. -45dBm/
│                   └── {mw}mW/  #           e.g. 00mW/
│                       └── *.s2p
│
└── Lakeshore335_output.py       # Reference implementation (original GUI prototype)
```

## Architecture: Layered Dependency Graph

Strict one-way dependencies — no circular imports:

```
config.py                     ← zero dependencies, pure data
    │
    ├── stability_monitor.py        ← pure algorithm (time, dataclasses)
    ├── pid_controller.py           ← pure algorithm (imports config)
    ├── pid_parameters.py           ← pure algorithm (dataclasses, no config dependency)
    ├── temperature_diagnostics.py  ← pure algorithm (imports numpy)
    └── temperature_state_diagnostics.py ← pure algorithm (dataclasses, no hardware)
            │
            ├── lakeshore_control.py ← instrument driver (pyvisa + config)
            ├── laser_driver.py      ← instrument driver (pyvisa)
            ├── laser_control.py     ← older standalone driver (pyvisa)
            └── vna_control.py       ← instrument driver (pyvisa + socket)
                    │
                    ├── power_sweep_auto.py      ← CLI orchestration (temp + laser + VNA)
                    ├── lakeshore335_ramp.py     ← standalone ramp (temp only, no VNA/laser)
                    └── ui/workers.py            ← GUI orchestration (ExperimentWorker)
                            │  └── ui/experiment_stability_controller.py  ← simplified stability (fixed PID + overshoot)
                            │
                            └── ui/main_window.py → ui/*_page.py  ← GUI layer
```

**Key principle**: replacing an instrument means changing exactly one driver file. The orchestration layer only calls the driver's public API — it never sends raw SCPI commands.

## Two Laser Drivers

There are **two** laser driver modules — don't confuse them:

| File | Used by | API style | Default address |
|---|---|---|---|
| `laser_driver.py` | GUI, `power_sweep_auto.py` (production) | `set_power()`, `output_on()`, `output_off()`, `close()` | `TCPIP0::K-N7779C-00108::inst0::INSTR` |
| `laser_control.py` | Standalone (older) | `set_power()`, `physical_off()`, `physical_on()`, `disconnect()` | `TCPIP0::100.65.11.65::INSTR` |

`laser_driver.py` is the production module. `laser_control.py` has a different `handle_disconnection()` strategy and a different `physical_off`/`physical_on` pattern. When adding features, prefer `laser_driver.py`.

## Two PID Modules

There are **two** PID parameter modules — don't confuse them:

| File | Used by | API style | Heater range policy |
|---|---|---|---|
| `pid_controller.py` | CLI runner (`power_sweep_auto.py`) | `SmartPIDController.get_params_for_temperature()`, `calculate_adjusted_setpoint()` — static methods, reads from `config.PID_PARAMS` | No range management; caller manages heater range separately |
| `pid_parameters.py` | `lakeshore335_ramp.py` | `PIDZoneManager(zone_manager).get_zone()`, `get_params()`; `SetpointCalculator().calculate()` — instance-based, self-contained zone definitions | High (3) forbidden; Low (1) + Medium (2) only; auto-upgrade from Low→Medium when heater > 85% |

Note: The GUI ExperimentWorker **no longer uses either PID module**. It uses `ExperimentStabilityController` (`ui/experiment_stability_controller.py`) which has its own fixed-PID logic based on `config.FIXED_PID_ZONES`.

`pid_parameters.py` is the richer module with `PIDZone` dataclass, zone validation (gap/overlap detection), and heater range policy enforcement. `pid_controller.py` is simpler and remains the production module for the CLI runner. When adding PID features, prefer extending `pid_parameters.py` and consider whether the runners should migrate to it.

## Two Temperature Diagnostics Modules

| File | Used by | API style | Classification |
|---|---|---|---|
| `temperature_diagnostics.py` | CLI runner (`power_sweep_auto.py`) | `TemperatureDiagnostics(history_window).analyze()` → `DiagnosticResult` with `ProblemType` enum; `AdaptivePIDAdjuster` for auto-correction | 8 problem types (oscillation, drift, overshoot, etc.) |
| `temperature_state_diagnostics.py` | `lakeshore335_ramp.py` | `TemperatureStateDiagnostics(sample_interval).diagnose()` → `DiagnosticResult` with 7 states + PID adjustment dict | 7 states (stable, converging, oscillating, offset, drifting, overshooting, insufficient_data); includes 15-min lockout, rollback, pure-P mode after 5+ oscillation failures |

`temperature_state_diagnostics.py` is the more sophisticated module with real-time PID auto-adjustment, safety lockouts, and oscillation time accumulation. `temperature_diagnostics.py` is the older module used by the CLI runner.

## Three Experiment Runners

| Runner | Location | Trigger | Output dir | What it does |
|---|---|---|---|---|
| CLI | `power_sweep_auto.py` | `python power_sweep_auto.py` | `D:\YBCO\VNAMeas\data\{date}\...` (from config.py) | Full experiment: temp → laser power sweep → VNA S2P |
| GUI | `ExperimentWorker` in `ui/workers.py` | "Start" button on Dashboard | `Auto_Sweep/experiment_data/{timestamp}/` | Full experiment + VNA power sweep outer loop |
| Ramp | `lakeshore335_ramp.py` | `python lakeshore335_ramp.py` | `Auto_Sweep/experiment_data/{timestamp}/ramp_log.csv` + `optimal_ramp_params.json` | Temperature-only ramp (10K→80K default); no VNA or laser |

The CLI runner uses `config.py` sweep lists directly. The GUI runner receives temp/power lists from `configure()`, sourced from the dashboard's `TempSweepWidget` (which supports "Fixed Points" and "Range Sweep" modes). The GUI runner now uses `ExperimentStabilityController` (fixed PID + setpoint overshoot state machine, see below) instead of `SmartPIDController`. The CLI runner still uses `SmartPIDController` and `TemperatureDiagnostics`.

The Ramp runner (`lakeshore335_ramp.py`) is a standalone temperature controller. It uses `PIDZoneManager` + `SetpointCalculator` (from `pid_parameters.py`) and `TemperatureStateDiagnostics` (from `temperature_state_diagnostics.py`). It includes:
- **Heater range auto-upgrade**: Low → Medium when heater exceeds 85% (High is forbidden)
- **Pure-P mode**: after 5 consecutive oscillation adjustment failures, forces I=0 and relies on setpoint overshoot
- **20–40K zone diagnostics**: real-time state classification and PID auto-adjustment
- **CSV logging** + **JSON optimal parameter summary** on completion
- **Emergency stop**: Ctrl+C → all heaters off; SIGTERM handler + atexit fallback

The GUI runner also supports a **VNA power sweep** outer loop (`vna_power_list`) that the CLI runner does not — it sweeps multiple VNA source power levels at each temperature before changing laser power.

## Entry Points

| File | Run with | Purpose |
|---|---|---|
| `app.py` | `python app.py` | Launch the PyQt5 GUI control panel |
| `power_sweep_auto.py` | `python power_sweep_auto.py` | Run automated temperature + power sweep (CLI) |
| `lakeshore335_ramp.py` | `python lakeshore335_ramp.py` | Run standalone temperature ramp (10K→80K, configurable) |
| `testcode/laser_test.py` | `python testcode/laser_test.py` | Interactive laser debugging menu |
| `testcode/vna_test.py` | `python testcode/vna_test.py` | Interactive VNA discovery + S2P test |
| `testcode/vna_probe.py` | `python testcode/vna_probe.py` | Dump all readable VNA SCPI parameters |
| `test_vna.py` | `python test_vna.py` | Standalone VNA connection + S2P save (at root) |
| `laser_control.py` | `python laser_control.py` | Older laser interactive test menu |
| `temperature_diagnostics.py` | `python temperature_diagnostics.py` | Run diagnostic algorithm demo |

The ramp controller supports CLI arguments:
```bash
python lakeshore335_ramp.py --start 20 --end 30 --step 2 --hold-seconds 30
python lakeshore335_ramp.py --address ASRL3::INSTR --max-wait 600
```

## BDD/TDD Conventions

All new code follows BDD (Behaviour-Driven Development) and TDD (Test-Driven Development). Tests are written **first**, then implementation follows the Red → Green → Refactor cycle.

### Test naming

Test function names follow the pattern:
```
test_given_<precondition>_when_<action>_then_<expected_result>
```

Example from `test_stability_monitor.py`:
```python
def test_given_all_readings_in_band_when_checking_then_returns_stable(self):
def test_given_one_reading_outside_tolerance_when_checking_then_returns_not_stable(self):
def test_given_insufficient_data_when_checking_custom_then_returns_not_stable_with_reason(self):
```

### Test layers

| Layer | What is tested | How |
|---|---|---|
| **Config** | Constants integrity, value ranges, zone boundaries | Direct import + assertions |
| **Algorithm** (stability, PID, diagnostics) | Input → output logic | Synthetic data + expected outcomes |
| **Instrument** (lakeshore, laser, vna) | SCPI command sequences | Mock pyvisa ResourceManager + Resource |
| **GUI pages** (VNAPage, LakeShore safety) | Widget behaviour, signal/slot logic | QApplication + real widget instances |
| **Experiment orchestration** | Full sweep loop with mocked controllers | MagicMock instruments, patched `time.sleep` |
| **Hardware integration** | Not tested in this phase | Requires real hardware or integration harness |

### Running tests

```bash
pytest tests/ -v                                     # all tests
pytest tests/test_stability_monitor.py -v             # one module
pytest tests/test_pid_parameters.py -v                # PID zone manager tests
pytest tests/test_temperature_state_diagnostics.py -v # state classifier tests
pytest tests/test_lakeshore335_ramp.py -v             # ramp controller tests
pytest tests/test_stability_fallback.py -v            # simplified stability controller tests
pytest tests/test_auto_reconnect.py -v                # auto-reconnect tests
pytest tests/test_button_styling.py -v                # button color styling tests
pytest tests/ -k "test_given_actual_77k" -v           # single test by keyword
```

### Mock VISA pattern

`tests/conftest.py` provides `MockResource` and `MockResourceManager` classes that:
- Record all SCPI commands sent via `.write()` / `.query()`
- Return configurable canned responses for `*IDN?`, `KRDG?`, `SETP?`, etc.
- Allow asserting on `mock_resource.last_command` and `mock_resource.all_commands`

Use the `mock_pyvisa` fixture to patch `pyvisa.ResourceManager` globally.

### GUI testing pattern

Tests in `test_vna_page.py`, `test_lakeshore_safety.py`, `test_experiment_worker.py`, `test_button_styling.py`, `test_auto_reconnect.py`, and `test_stability_fallback.py` use:
- A module-scoped `qapp` fixture that creates one `QApplication` for the module
- Direct widget instantiation (no main window needed, though `test_auto_reconnect.py` and `test_button_styling.py` test `MainWindow` and detail pages directly)
- `MagicMock` controllers for worker tests — no real VISA calls
- `@patch("time.sleep", return_value=None)` to make experiment loop tests instantaneous
- `@patch("os.makedirs")` to skip real filesystem operations
- `@patch.object(MainWindow, "_start_reconnect")` to intercept auto-reconnect without real VISA

### Synthetic temperature data

`conftest.py` provides pre-built fixtures for all diagnostic scenarios:
- `stable_temperatures` — 30K ±0.02K noise
- `oscillating_temperatures` — 30K ±0.5K sinusoidal
- `drifting_temperatures` — 30K → 32K linear drift
- `noisy_temperatures` — 30K ±0.08K random noise
- `perfect_stable_temperatures` — exactly 30K, zero variance

## GUI Architecture

The PyQt5 GUI (`app.py` → `ui/main_window.py`) uses:

- **QStackedWidget**: 4 pages — Dashboard (index 0), Laser (1), LakeShore (2), VNA (3)
- **Worker threads**: Each instrument has its own `QThread` + `QObject` worker. All VISA I/O happens off the UI thread. Results delivered via `pyqtSignal`. The 4th worker (`ExperimentWorker`) runs the full experiment sweep on a dedicated thread created on demand.
- **DeviceCard**: Clickable cards on the dashboard. Click navigates to the detail page. StatusLight shows connection state (red/yellow/green).
- **PresetBar**: Dropdown + Save/Load/Delete. Each device page has its own. Dashboard also has per-device preset rows.
- **LakeShore polling**: 1-second QTimer drives `LakeShoreWorker.poll()` → emits `reading` signal → UI updates large-format temperature labels.
- **Settings auto-persist**: On window close, all current settings (addresses, parameters, sweep config) are saved to `app_settings.json`. On startup, they're restored automatically. No manual save/load needed. This replaces the JSON preset files for session state (preset files remain for named preset management).
- **Dashboard temperature sweep**: `TempSweepWidget` supports two modes — "Fixed Points" (comma-separated list) and "Range Sweep" (start/stop/step). The GUI runner receives the resolved temperature list via `configure()`.

### GUI design principles applied
1. **Information density layering** — dashboard shows only status; details in sub-pages
2. **Colour coding over text** — green/yellow/red status lights; coloured action buttons
3. **Danger confirmation** — physical laser off and all-heaters-off require QMessageBox confirmation
4. **Fusion style** — "Deep Space Cyan" dark theme with global stylesheet in `app.py`

## Temperature Safety Interlock (LakeShoreWorker)

`LakeShoreWorker.set_setpoint()` in `ui/workers.py` implements a **one-directional cooling-safety rule**:

If `actual_temp > target_setpoint + 20 K`:
1. Set heater range to **0 (OFF)**
2. Poll `get_temperature()` every 2 seconds
3. Wait until `actual_temp - target_setpoint < 20 K`
4. Set heater range to **2 (Medium)**
5. Then write the setpoint

A 10-minute safety timeout prevents infinite polling. If `actual_temp <= target_setpoint + 20 K`, the setpoint is written immediately without intervention. This is tested in `test_lakeshore_safety.py`.

## VNA Page Frequency Controls

`VNAPage` (`ui/vna_page.py`) provides:
- **Frequency spinboxes**: Start, Stop, Center, Span — all in GHz, range 1–14 GHz
- **Bidirectional sync**: Changing Start/Stop updates Center/Span and vice versa
- **Unit conversion**: Internal API uses Hz (`get_all_settings()` returns Hz), UI displays GHz
- **S-parameter selector**: S21, S11, S12, S22
- **VNA source power**, sweep points, IF bandwidth controls
- **Single sweep**: triggers one sweep and saves .s2p to a chosen path
- **Full settings dict**: `apply_settings()` sends all parameters to VNA in one call

## Experiment Data Directory Structure

GUI experiment runs create output in:
```
experiment_data/{YYYYMMDD_HHMMSS}/{target}K/actual_{actual}K/{vna_dbm}dBm/{laser_mw}mW/
    YBCO_{vna_dbm}dBm_{laser_mw}mW_target_{target}K_actual_{actual}K.s2p
```

CLI experiment runs use `config.py`'s `base_folder` and a slightly different naming scheme (no VNA power level in filename).

Ramp controller runs create output in:
```
experiment_data/{YYYYMMDD_HHMMSS}/
    ramp_log.csv               # per-step CSV with timestamps, PID, heater range, stability
    optimal_ramp_params.json   # full parameter summary for each temperature step
```

## Preset System

JSON files in `presets/` directory. One file per device. Managed by `PresetManager` class in `ui/widgets.py`.

```json
// presets/laser_default.json
{"name": "default", "device": "laser",
 "wavelength_nm": 1550.0, "power_sequence_mw": [0,1,3,5,7,9],
 "resource_address": "TCPIP0::169.254.77.29::INSTR"}

// presets/lakeshore_default.json
{"name": "default", "device": "lakeshore",
 "resource_address": "ASRL4::INSTR",
 "loop1": {"setpoint_k": 50.0, "pid": {"p":100,"i":5,"d":0}, "heater_range": 2},
 "loop2": {"setpoint_k": 295.0, "pid": {"p":10,"i":20,"d":0}, "heater_range": 0}}
```

Presets are loaded/saved from both the Dashboard and individual device pages.

## Hardware & VISA Addresses

| Instrument | Interface | Addresses used |
|---|---|---|
| Keysight PXI VNA | HiSLIP/TCPIP | `TCPIP0::localhost::hislip_PXI10_CHASSIS1_SLOT1_INDEX0::INSTR` |
| Keysight N7779C Laser | TCPIP | `TCPIP0::K-N7779C-00108::inst0::INSTR` (config.py), `TCPIP0::169.254.77.29::INSTR` (legacy), `TCPIP0::100.65.11.65::INSTR` (laser_control.py) |
| LakeShore 335 | RS-232 Serial | `ASRL4::INSTR` (57600 baud, 7 data bits, odd parity) |

The dashboard provides editable address comboboxes with pre-populated options for each instrument (see `LASER_ADDRS`, `LAKESHORE_ADDRS`, `VNA_ADDRS` in `dashboard_page.py`).

**Critical**: PXI VNA cannot use raw PXI resource addresses — must use HiSLIP format. `vna_control.build_hislip_addresses()` generates candidate addresses to try. `vna_control.try_connect()` returns `(resource, is_pxi, conn_type)` — if `is_pxi` is True, the address is wrong.

## Temperature Stability System

`AdvancedStabilityMonitor` in `stability_monitor.py` implements 6 methods selectable via `config.stability_method`:

| Method | Behaviour |
|---|---|
| `simple` | All readings within tolerance for hold duration |
| `v1` | Mean error + variance below thresholds |
| `v2` | Absolute error, relative error, and max-delta combined |
| `v3` | Standard deviation + error over a time window |
| `custom` | Rolling 1-minute averages; delta between consecutive windows; final band check |

The `custom` method (production default) uses a two-phase protocol:
1. **`ready_for_adjust`** — rate-of-change is stable (condition 2 passes). Triggers dynamic setpoint re-adjustment.
2. **`stable`** — temperature is within the final measurement band (condition 3 passes). Starts the hold timer.

## Experiment Stability Controller (GUI runner)

`ExperimentStabilityController` (`ui/experiment_stability_controller.py`) is a **simplified** stability controller used by the GUI's `ExperimentWorker`. It replaces the older `SmartPIDController` + dynamic PID adjustment approach.

**Core philosophy**: PID parameters are **fixed per temperature zone and never adjusted**. Only the setpoint overshoot is tuned.

**Fixed PID zones** (from `config.FIXED_PID_ZONES`):

| Zone | Range | P | I | D | Base Overshoot |
|---|---|---|---|---|---|
| Low | ≤ 20 K | 100 | 5 | 0 | 0 K |
| Medium | 20–40 K | 100 | 0 | 0 | 1.5 K |
| High | > 40 K | 150 | 0 | 0 | 2.0 K |

**3-state machine**:

| State | What happens |
|---|---|
| `INITIAL_SETPOINT` (0) | Set fixed PID + setpoint = target + base_overshoot. If not stable after 60s → advance. |
| `SETPOINT_ADJUST_1` (1) | Overshoot = base + (target − actual_avg). Re-set setpoint. If not stable after another 60s → advance. |
| `SETPOINT_ADJUST_2` (2) | Second overshoot adjustment. After 60s: if |avg − target| ≤ 0.5K → **good_enough** (proceed to measure). |

**Key properties**:
- `MAX_SETPOINT_ADJUSTMENTS = 2` — at most 2 adjustments
- `GOOD_ENOUGH_BAND_K = 0.5` — ±0.5K tolerance for "close enough"
- `MAX_OVERSHOOT_K = 10.0` — overshoot clamp
- `DIAGNOSTIC_INTERVAL_S = 60` — wait time before each state transition
- `STABLE_HOLD_SECONDS = 60` — must hold stable for 60s
- `MAX_WAIT_SECONDS = 30 min` — hard timeout

**Usage pattern in ExperimentWorker**:
```python
stability_ctrl = ExperimentStabilityController()
stability_ctrl.setup(target_k=30.0, current_temperature=actual_k)
# Every 10 seconds:
stability_ctrl.add_reading(actual_k)
result = stability_ctrl.check(elapsed_s=elapsed)
if result.stable or result.reason == "good_enough":
    # proceed to measurement
sp_adj = stability_ctrl.needs_setpoint_adjustment()
if sp_adj:
    lakeshore.set_temperature(sp_adj, loop=1)
```

The `get_fixed_pid()` method returns the zone's PID dict (never changes). Tests in `tests/test_stability_fallback.py` cover all states, zone selection, overshoot clamping, good_enough fallback, and ExperimentWorker integration.

## Auto-Reconnect Mechanism

`MainWindow` (`ui/main_window.py`) detects VISA connection errors and automatically attempts reconnection.

**Error detection** (`_is_connection_error()`):
- `VI_ERROR` prefix → connection error
- Keywords: `timeout`, `disconnect`, `closed`, `lost`, `not responding`
- Non-connection errors (data parse failures, invalid parameters) do **not** trigger reconnect

**Reconnect flow**:
1. `_on_error("laser", message)` → if connection error AND not user-initiated disconnect → `_start_reconnect("laser")`
2. `_start_reconnect()`: increments attempt counter, sets device to "connecting" (yellow), starts QTimer(2s delay)
3. `_attempt_reconnect()`: tries to re-create the VISA connection using the last known address
4. On success → `_on_device_connected()` resets attempt counter to 0
5. On failure → if attempts < `max_reconnect_attempts` (3), retry; otherwise stay disconnected (red)

**User disconnect protection**: `_user_disconnect[device]` flag is set True when the user clicks "Disconnect". Auto-reconnect is **never** triggered when this flag is True. The flag is cleared when the user clicks "Connect".

**Per-device independence**: Each device (laser, lakeshore, vna) has its own reconnect state, attempt counter, and timer — they operate completely independently.

**Config**: `max_reconnect_attempts = 3`, `reconnect_delay_seconds = 2` in `config.py`.

Tests in `tests/test_auto_reconnect.py` cover error classification, trigger conditions, retry limits, user-disconnect flag, and multi-device independence.

## Dashboard Button Styling API

`DashboardPage` (`ui/dashboard_page.py`) provides per-device connection state methods that update button colors and enabled states:

| Method | Connect button | Disconnect button |
|---|---|---|
| `set_device_disconnected(key)` | 🟢 Green, enabled | ⚫ Gray, disabled |
| `set_device_connected(key, model)` | ⚫ Gray, disabled | 🔴 Red, enabled |
| `set_device_error(key)` | 🟢 Green, enabled | ⚫ Gray, disabled |
| `set_device_connecting(key)` | ⚫ Gray, disabled | ⚫ Gray, disabled |

All three devices (laser, lakeshore, vna) use the same pattern. Detail pages (LaserPage, LakeShorePage, VNAPage) have their own `_connect_btn`/`_disconnect_btn` with matching `set_connected()`/`set_disconnected()`/`set_connecting()` methods. Tests in `tests/test_button_styling.py` verify styling for all states.

## PID Strategy

There are two PID modules with different design philosophies:

### SmartPIDController (`pid_controller.py`) — used by CLI runner

Selects parameters by temperature zone from `config.PID_PARAMS`:

| Zone | Range | P | I | D | Rationale |
|---|---|---|---|---|---|
| Low | ≤ 20 K | 100 | 5 | 0 | Integral term for steady-state accuracy at cryogenic temps |
| Medium | 20–40 K | 100 | 0 | 0 | Proportional-only |
| High | > 40 K | 150 | 0 | 0 | Higher gain for faster warm-up |

Setpoint overshoot (`calculate_adjusted_setpoint`) is only applied above 20 K. Below 20 K, setpoint = target exactly (cryogenic safety).

### PIDZoneManager (`pid_parameters.py`) — used by ramp controller

Self-contained zone definitions with additional constraints:

| Zone | Range | P | I | D | Heater Range |
|---|---|---|---|---|---|
| Low | ≤ 20 K | 100 | 5 | 0 | Low (1) |
| Medium | 20–40 K | 100 | 3 | 0 | Medium (2) |
| High | > 40 K | 150 | 0 | 0 | Medium (2) |

Key differences from `pid_controller.py`:
- **Heater range policy**: High (3) is explicitly forbidden. The ramp controller auto-upgrades Low→Medium when heater exceeds 85%.
- **Zone validation**: `PIDZoneManager.validate_zones()` checks for gaps, overlaps, valid ranges, and D=0 enforcement.
- **Medium zone uses I=3** (not I=0) — small integral term to eliminate steady-state error in the transitional zone.
- **SetpointCalculator**: configurable overshoot factors per zone (0.3 medium, 0.5 high), clamped to [1.0, 5.0] K. No overshoot below 20 K.
- **Pure-P mode**: after 5+ consecutive oscillation adjustment failures, forces I=0 and relies solely on setpoint overshoot.

## LakeShore Duck-Typing Pattern

`lakeshore_control.py` provides driver-agnostic helper functions that work with *any* LakeShore 335 object — whether it's the built-in `LakeShore335` class, the external `Lakeshore335` pip package, or the legacy fallback class. They try multiple method names before falling back to raw VISA writes:

- `set_lakeshore_temperature()` — tries `set_temperature()`, `set_setpoint()`, `setpoint()`, `set_temperature_setpoint()`, then raw `SETP`
- `set_lakeshore_pid()` — tries `set_pid()`, then raw `PID`
- `get_lakeshore_temperature()` — tries `get_temperature()`, then raw `KRDG? A`
- `configure_lakeshore_serial()` — sets baud/parity on the underlying VISA handle (ASRL only)
- `_raw_lakeshore_handle()` — introspects for a `.write()`-capable attribute

## Common Modifications

All experiment parameters are in **`config.py`** — no other file needs editing for routine changes:

| To change | Edit in `config.py` |
|---|---|
| Sweep temperature range | `temperature_levels_k` (default: 26–100 K, step 2) |
| Sweep power levels | `power_levels_mw` (default: [0,1,3,5,7,9]) |
| Stability tolerances | `custom_stability_settings` dict |
| PID values | `PID_PARAMS` dict |
| Setpoint overshoot | `setpoint_adjust_settings` dict |
| Fixed PID zones & overshoot | `FIXED_PID_ZONES` dict (low/medium/high: P, I, D, base_overshoot_k) |
| Stability fallback | `stability_fallback_settings` (max adjustments, good_enough band, diagnostic interval, overshoot clamp) |
| VISA addresses | `resource_vna`, `laser_resource`, `resource_lakeshore` |
| Output directory | `date` and `base_folder` |
| Poll/stable/max timing | `temperature_poll_seconds`, `stable_hold_seconds`, `max_wait_seconds` |
| Stability method | `stability_method` (one of: simple, v1, v2, v3, custom) |
| Auto-reconnect | `max_reconnect_attempts` (3), `reconnect_delay_seconds` (2) |

To replace an instrument: implement the same public API in a new driver file, then update the import in `power_sweep_auto.py`. The orchestration layer does not contain any raw SCPI commands.

**Important**: If the change affects experiment protocol (e.g. stability criteria, sweep logic, output path structure), check whether `ExperimentWorker.run()` in `ui/workers.py` needs the same change — it has its own copy of the experiment loop. Also check `lakeshore335_ramp.py` if it affects temperature ramp behaviour.

## Dependencies

- **pyvisa** (with `visa32.dll` backend — NI-VISA or Keysight IO Libraries)
- **numpy** (temperature diagnostics)
- **PyQt5** (GUI only — `app.py` and `ui/`; not needed for `power_sweep_auto.py` or `lakeshore335_ramp.py`)
- **pytest** (testing only — not needed for production use)

## Parent Directory Context

The parent directory `D:\YBCO\VNAMeas\` contains related but independent scripts:
- `Lakeshore335.py` — another LakeShore driver variant
- `PowerSweep_auto.py`, `PowerSweep_auto_forKeysightVA.py` — older sweep scripts (pre-refactor)
- `Lakeshore335_auto_tune_PID.py` — PID auto-tuning utility
- `VoltageMeterReader.py`, `temperature_power_sweep.py` — additional measurement tools
- `plot_result.py`, `plot_s_params.py`, `Read_VNA.py` — data analysis/plotting scripts
- `data/` — historical measurement data (separate from `Auto_Sweep/experiment_data/`)

These are not part of the Auto_Sweep module but may be referenced for context or merged in the future.
