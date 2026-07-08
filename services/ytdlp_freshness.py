"""
services/ytdlp_freshness.py — yt-dlp version introspection and staleness check.

yt-dlp is deliberately unpinned in requirements.txt because it must track
upstream closely as platforms change their anti-bot behaviour.  Every Render
deploy re-runs pip install, so unpinned already gets refreshed on each deploy.
What's missing without this module is visibility into what version is actually
running and whether it has gotten stale between deploys.

Staleness threshold: 90 days.  yt-dlp's own project documentation treats
installations older than ~90 days as worth warning about.  This is not an
invented number.

yt-dlp uses date-versioned releases (e.g. "2026.06.09").  A dev install from
git may produce a different format (e.g. "2026.06.09.dev0+git...").  This
module degrades gracefully when the version string cannot be parsed as a date,
rather than raising — failing soft is correct here because yt-dlp staleness is
an advisory signal, not a hard gate.

IMPORTANT: This module reports status only.  It never runs pip install or any
subprocess.  That would create a code-execution surface on an authenticated
endpoint, which is worse than stale yt-dlp.  Render's redeploy already handles
the update path cleanly.
"""

import importlib.metadata
from datetime import date, datetime, timezone

from utils.logger import get_logger

logger = get_logger(__name__)

# 90 days — yt-dlp project's own guidance.
STALENESS_THRESHOLD_DAYS = 90


def _parse_ytdlp_date(version: str) -> date | None:
    """
    Parse a yt-dlp release version string into a date.

    yt-dlp releases are date-versioned: "YYYY.MM.DD" or "YYYY.MM.DD.N"
    (where .N is the patch number for same-day releases).  Dev builds may
    append extra suffixes like ".dev0+g...".

    Returns the parsed date, or None if the string does not start with a
    recognisable date prefix.
    """
    # Take only the first three dot-separated components: YYYY.MM.DD
    parts = version.split(".")
    if len(parts) < 3:
        return None
    try:
        year = int(parts[0])
        month = int(parts[1])
        day = int(parts[2])
        return date(year, month, day)
    except (ValueError, TypeError):
        return None


def get_ytdlp_info() -> dict:
    """
    Return a dict describing the installed yt-dlp version and staleness.

    Keys:
        version (str | None):  Installed version string, or None if not found.
        release_date (str | None):  Parsed date in "YYYY-MM-DD" form, or None.
        age_days (int | None):  Days since release, or None if unparseable.
        is_stale (bool):  True when age_days >= STALENESS_THRESHOLD_DAYS.
                          False when version is unparseable (advisory, not a gate).
        stale_threshold_days (int):  The threshold used (for display).
        error (str | None):  Human-readable note when version is absent or
                             unparseable.  None on fully clean result.
    """
    try:
        version = importlib.metadata.version("yt-dlp")
    except importlib.metadata.PackageNotFoundError:
        logger.warning("yt-dlp is not installed — cannot report version.")
        return {
            "version": None,
            "release_date": None,
            "age_days": None,
            "is_stale": False,
            "stale_threshold_days": STALENESS_THRESHOLD_DAYS,
            "error": "yt-dlp package not found",
        }

    release_date = _parse_ytdlp_date(version)

    if release_date is None:
        logger.warning(
            "yt-dlp version %r does not match expected date-version format.", version
        )
        return {
            "version": version,
            "release_date": None,
            "age_days": None,
            "is_stale": False,
            "stale_threshold_days": STALENESS_THRESHOLD_DAYS,
            "error": f"Version {version!r} is not a standard date-versioned release — "
                     "cannot determine age.",
        }

    today = datetime.now(timezone.utc).date()
    age_days = (today - release_date).days
    is_stale = age_days >= STALENESS_THRESHOLD_DAYS

    return {
        "version": version,
        "release_date": release_date.isoformat(),
        "age_days": age_days,
        "is_stale": is_stale,
        "stale_threshold_days": STALENESS_THRESHOLD_DAYS,
        "error": None,
    }
