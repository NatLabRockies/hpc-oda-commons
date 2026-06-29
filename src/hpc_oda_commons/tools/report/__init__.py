"""
Report generation utilities.
"""

from __future__ import annotations

from hpc_oda_commons.tools.report.console import render_leaderboard_console
from hpc_oda_commons.tools.report.html import render_analysis_html, render_leaderboard_html

__all__ = ["render_analysis_html", "render_leaderboard_console", "render_leaderboard_html"]
