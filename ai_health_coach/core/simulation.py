"""Simulation clock — allows the frontend to control the current date.

In production, this would just return datetime.now(). For demos,
the frontend sets a simulated date and all date logic uses it.
"""

from __future__ import annotations

from datetime import datetime

_simulated_date: str | None = None


def get_current_date() -> str:
    """Return the current date as YYYY-MM-DD (simulated or real)."""
    if _simulated_date is not None:
        return _simulated_date
    return datetime.now().strftime("%Y-%m-%d")


def set_simulated_date(date_str: str) -> None:
    """Set the simulated date. Pass None to revert to real time."""
    global _simulated_date
    # Validate format
    datetime.strptime(date_str, "%Y-%m-%d")
    _simulated_date = date_str


def clear_simulated_date() -> None:
    """Revert to real time."""
    global _simulated_date
    _simulated_date = None
