# -*- coding: utf-8 -*-
"""
Temperature stability monitoring algorithms.

Pure algorithm module — no hardware or VISA dependencies.
Provides multiple stability-checking methods for cryogenic temperature control.

Usage:
    from stability_monitor import AdvancedStabilityMonitor

    monitor = AdvancedStabilityMonitor()
    monitor.add_reading(30.05, target=30.0)
    result = monitor.check_stability(30.0, method="custom")
    if result["stable"]:
        print("Ready to measure!")
"""

from dataclasses import dataclass
from time import time
from typing import List, Optional


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------

@dataclass
class TemperatureReading:
    timestamp: float
    temperature: float
    target: float


# ---------------------------------------------------------------------------
# Monitor
# ---------------------------------------------------------------------------

class AdvancedStabilityMonitor:
    """Ring-buffer-based temperature stability analyser.

    Supports five check methods: simple, v1, v2, v3, custom.
    The `custom` method (default in production) uses rolling 1-minute
    averages and a two-phase approach:
      1. ready_for_adjust  — rate-of-change is stable
      2. stable            — temperature is in the final measurement band
    """

    def __init__(self):
        self.readings: List[TemperatureReading] = []
        self.max_readings = 1000

    # ---- data management ----

    def add_reading(self, temperature: float, target: float):
        """Append a reading with the current timestamp."""
        reading = TemperatureReading(
            timestamp=time(),
            temperature=temperature,
            target=target,
        )
        self.readings.append(reading)
        if len(self.readings) > self.max_readings:
            self.readings.pop(0)

    def clear(self):
        """Discard all stored readings."""
        self.readings = []

    def _get_recent_readings(self, window_seconds: float = 60) -> List[TemperatureReading]:
        if not self.readings:
            return []
        current_time = time()
        return [r for r in self.readings if current_time - r.timestamp < window_seconds]

    # ---- stability methods ----

    def check_stability_simple(self, target_k: float, tolerance_k: float = 0.1,
                                hold_seconds: float = 60) -> dict:
        """All readings within ``tolerance_k`` over ``hold_seconds``."""
        recent = self._get_recent_readings(hold_seconds)
        if not recent:
            return {"stable": False, "reason": "No recent data"}

        temperatures = [r.temperature for r in recent]
        all_in_tolerance = all(abs(t - target_k) <= tolerance_k for t in temperatures)
        avg_temp = sum(temperatures) / len(temperatures)
        max_delta = max(temperatures) - min(temperatures) if len(temperatures) > 1 else 0.0

        return {
            "stable": all_in_tolerance,
            "method": "simple",
            "avg_temp": avg_temp,
            "max_delta": max_delta,
            "reason": "All within tolerance" if all_in_tolerance else "Temperature outside tolerance",
        }

    def check_stability_v1(self, target_k: float, threshold_k: float = 0.05,
                            window_size: int = 30) -> dict:
        """Mean error + variance threshold over last ``window_size`` readings."""
        if len(self.readings) < window_size:
            return {"stable": False, "method": "v1", "reason": "Insufficient data"}

        recent = self.readings[-window_size:]
        temps = [r.temperature for r in recent]
        mean_temp = sum(temps) / len(temps)
        variance = sum((t - mean_temp) ** 2 for t in temps) / len(temps)
        error = abs(mean_temp - target_k)

        stable = error < threshold_k and variance < (threshold_k / 2) ** 2

        return {
            "stable": stable,
            "method": "v1",
            "avg_temp": mean_temp,
            "variance": variance,
            "error": error,
            "threshold": threshold_k,
            "reason": "Stable" if stable else "Error or variance too high",
        }

    def check_stability_v2(self, target_k: float, abs_threshold: float = 0.1,
                            rel_threshold: float = 0.001, window_size: int = 20) -> dict:
        """Absolute error, relative error, and max-delta combined check."""
        if len(self.readings) < window_size:
            return {"stable": False, "method": "v2", "reason": "Insufficient data"}

        recent = self.readings[-window_size:]
        temps = [r.temperature for r in recent]
        avg_temp = sum(temps) / len(temps)
        max_temp = max(temps)
        min_temp = min(temps)

        abs_error = abs(avg_temp - target_k)
        rel_error = abs_error / max(abs(target_k), 1e-10)
        max_delta = max_temp - min_temp

        conditions = [
            ("abs_error", abs_error < abs_threshold),
            ("rel_error", rel_error < rel_threshold),
            ("max_delta", max_delta < abs_threshold / 2),
        ]

        all_met = all(c[1] for c in conditions)
        failed = [c[0] for c in conditions if not c[1]]

        return {
            "stable": all_met,
            "method": "v2",
            "avg_temp": avg_temp,
            "max_delta": max_delta,
            "abs_error": abs_error,
            "rel_error": rel_error,
            "reason": "All conditions met" if all_met else f'Failed: {", ".join(failed)}',
        }

    def check_stability_v3(self, target_k: float, window_seconds: float = 60,
                            threshold_k: float = 0.02) -> dict:
        """Standard deviation + relaxed error threshold over a time window."""
        recent = self._get_recent_readings(window_seconds)

        if len(recent) < 5:
            return {"stable": False, "method": "v3", "reason": "Insufficient data"}

        temps = [r.temperature for r in recent]
        avg_temp = sum(temps) / len(temps)
        n = len(temps)
        std_dev = (sum((t - avg_temp) ** 2 for t in temps) / n) ** 0.5
        error = abs(avg_temp - target_k)

        stable = error < threshold_k * 5 and std_dev < threshold_k

        return {
            "stable": stable,
            "method": "v3",
            "avg_temp": avg_temp,
            "std_dev": std_dev,
            "error": error,
            "reason": "Stable" if stable else "Error or std dev too high",
        }

    def check_stability_custom(self, target_k: float,
                                settings: Optional[dict] = None) -> dict:
        """Custom stability check using rolling 1-minute averages.

        Criteria:
          1. 1-min average within ±avg_tolerance_k of target
          2. Delta between consecutive 1-min averages < delta_tolerance_k
          3. Latest average within ±final_stable_band_k of target (→ stable=True)

        ``ready_for_adjust`` is True when condition 2 is met (rate stable),
        even if the temperature is not yet at the target.
        """
        if settings is None:
            from config import custom_stability_settings as settings

        avg_window = settings.get("avg_window_seconds", 60)
        avg_tolerance = settings.get("avg_tolerance_k", 0.5)
        delta_tolerance = settings.get("delta_tolerance_k", 0.3)
        final_band = settings.get("final_stable_band_k", 0.3)
        min_readings = settings.get("min_readings_required", 6)

        current_time = time()

        # readings from last 3 minutes
        all_recent = [r for r in self.readings if current_time - r.timestamp < 180]

        if len(all_recent) < min_readings:
            return {
                "stable": False,
                "method": "custom",
                "reason": f"Need at least {min_readings} readings, have {len(all_recent)}",
                "avg_temp": None,
                "avg_delta": None,
                "in_final_band": False,
                "ready_for_adjust": False,
            }

        # rolling 1-minute averages
        minute_windows = []
        for i in range(3):
            window_start = current_time - (i + 1) * avg_window
            window_end = current_time - i * avg_window
            window_readings = [
                r for r in all_recent
                if window_start <= r.timestamp < window_end
            ]
            if len(window_readings) >= 3:
                window_avg = sum(r.temperature for r in window_readings) / len(window_readings)
                minute_windows.append({
                    "start": window_start,
                    "end": window_end,
                    "avg": window_avg,
                    "count": len(window_readings),
                })

        minute_windows.sort(key=lambda x: x["end"], reverse=True)

        if not minute_windows:
            return {
                "stable": False,
                "method": "custom",
                "reason": "No valid 1-minute windows",
                "avg_temp": None,
                "avg_delta": None,
                "in_final_band": False,
                "ready_for_adjust": False,
            }

        latest_avg = minute_windows[0]["avg"]
        condition1 = abs(latest_avg - target_k) <= avg_tolerance

        condition2 = False
        avg_delta = None
        if len(minute_windows) >= 2:
            avg_delta = abs(minute_windows[0]["avg"] - minute_windows[1]["avg"])
            condition2 = avg_delta <= delta_tolerance

        condition3 = abs(latest_avg - target_k) <= final_band

        stable_for_adjust = condition2
        stable_for_measure = condition3

        reasons = []
        if not condition1:
            reasons.append(f"Average {latest_avg:.3f}K not within ±{avg_tolerance}K of target")
        if not condition2 and len(minute_windows) >= 2:
            reasons.append(f"Average delta {avg_delta:.3f}K > {delta_tolerance}K")
        if not condition3:
            reasons.append(f"Not within final stable band ±{final_band}K")

        return {
            "stable": stable_for_measure,
            "method": "custom",
            "avg_temp": latest_avg,
            "avg_delta": avg_delta,
            "in_final_band": condition3,
            "ready_for_adjust": stable_for_adjust,
            "reason": "All conditions met" if stable_for_measure else f'Failed: {", ".join(reasons)}',
            "minute_windows": minute_windows,
        }

    # ---- dispatcher ----

    def check_stability(self, target_k: float, method: str = "v2") -> dict:
        """Route to the appropriate stability method by name."""
        if method == "simple":
            from config import temperature_tolerance_k
            return self.check_stability_simple(
                target_k, tolerance_k=temperature_tolerance_k)
        elif method == "v1":
            return self.check_stability_v1(target_k)
        elif method == "v2":
            return self.check_stability_v2(target_k)
        elif method == "v3":
            return self.check_stability_v3(target_k)
        elif method == "custom":
            return self.check_stability_custom(target_k)
        else:
            return {
                "stable": False,
                "method": method,
                "reason": f"Unknown method: {method}",
            }
