"""Paper campaign tooling (BUILD_PLAN slice 4.7).

Weekly tracking-error report with the plan's hard bands (slippage +/-1 tick,
trade count +/-20%, realized vol in band, cost/round-trip +/-25%), the
consecutive-weeks clock that resets on any out-of-band week, and cost-model
recalibration SUGGESTIONS from real fills (configs are never auto-edited).
"""

from qt.campaign.tracker import CampaignTracker
from qt.campaign.weekly import Expectations, WeeklyReport, build_weekly_report

__all__ = ["CampaignTracker", "Expectations", "WeeklyReport", "build_weekly_report"]
