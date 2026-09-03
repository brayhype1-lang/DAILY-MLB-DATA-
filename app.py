"""Stable configuration for the MLB Quantitative Terminal."""

from __future__ import annotations

MLB_API_BASE = "https://statsapi.mlb.com/api/v1"
MLB_LIVE_BASE = "https://statsapi.mlb.com/api/v1.1"
SAVANT_BASE = "https://baseballsavant.mlb.com"
OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
ODDS_API_URL = "https://api.the-odds-api.com/v4/sports/baseball_mlb/odds/"

USER_AGENT = (
    "Mozilla/5.0 (compatible; MLBQuantTerminal/2.0; "
    "+https://github.com/)"
)

CONTROLLED_ROOF_WORDS = ("dome", "fixed")
RETRACTABLE_ROOF_WORDS = ("retractable",)

SOURCE_LINKS = {
    "MLB Stats API": "https://statsapi.mlb.com/api/v1/schedule?sportId=1",
    "Baseball Savant": "https://baseballsavant.mlb.com/statcast_search",
    "Statcast park factors": "https://baseballsavant.mlb.com/leaderboard/statcast-park-factors",
    "Open-Meteo": "https://open-meteo.com/en/docs",
    "The Odds API": "https://the-odds-api.com/sports/mlb-odds.html",
}

# Primary and secondary accents used only for visual matchup identity.
TEAM_COLORS = {
    108: ("#BA0021", "#003263"),  # Angels
    109: ("#A71930", "#E3D4AD"),  # Diamondbacks
    110: ("#DF4601", "#000000"),  # Orioles
    111: ("#BD3039", "#0C2340"),  # Red Sox
    112: ("#0E3386", "#CC3433"),  # Cubs
    113: ("#C6011F", "#000000"),  # Reds
    114: ("#00385D", "#E50022"),  # Guardians
    115: ("#333366", "#C4CED4"),  # Rockies
    116: ("#0C2340", "#FA4616"),  # Tigers
    117: ("#002D62", "#EB6E1F"),  # Astros
    118: ("#004687", "#BD9B60"),  # Royals
    119: ("#005A9C", "#EF3E42"),  # Dodgers
    120: ("#AB0003", "#14225A"),  # Nationals
    121: ("#002D72", "#FF5910"),  # Mets
    133: ("#003831", "#EFB21E"),  # Athletics
    134: ("#27251F", "#FDB827"),  # Pirates
    135: ("#2F241D", "#FFC425"),  # Padres
    136: ("#0C2C56", "#005C5C"),  # Mariners
    137: ("#FD5A1E", "#27251F"),  # Giants
    138: ("#C41E3A", "#0C2340"),  # Cardinals
    139: ("#092C5C", "#8FBCE6"),  # Rays
    140: ("#003278", "#C0111F"),  # Rangers
    141: ("#134A8E", "#E8291C"),  # Blue Jays
    142: ("#002B5C", "#D31145"),  # Twins
    143: ("#E81828", "#002D72"),  # Phillies
    144: ("#CE1141", "#13274F"),  # Braves
    145: ("#27251F", "#C4CED4"),  # White Sox
    146: ("#00A3E0", "#EF3340"),  # Marlins
    147: ("#0C2340", "#C4CED4"),  # Yankees
    158: ("#12284B", "#FFC52F"),  # Brewers
}

WEATHER_CODES = {
    0: "Clear",
    1: "Mostly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Rime fog",
    51: "Light drizzle",
    53: "Drizzle",
    55: "Heavy drizzle",
    61: "Light rain",
    63: "Rain",
    65: "Heavy rain",
    71: "Light snow",
    73: "Snow",
    75: "Heavy snow",
    80: "Rain showers",
    81: "Rain showers",
    82: "Heavy showers",
    95: "Thunderstorms",
    96: "Thunderstorms",
    99: "Severe thunderstorms",
}
import csv
import base64
import copy
import io
import hmac
import json
import math
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable



class DataSourceError(RuntimeError):
    """A remote source did not return usable data."""


def _request_bytes(
    url: str,
    params: dict[str, Any] | None = None,
    *,
    timeout: int = 18,
    attempts: int = 3,
) -> bytes:
    if params:
        query = urllib.parse.urlencode(params, doseq=True)
        separator = "&" if "?" in url else "?"
        url = f"{url}{separator}{query}"

    last_error: Exception | None = None
    for attempt in range(attempts):
        request = urllib.request.Request(
            url,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json,text/csv,text/html"},
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                body = response.read()
                if not body:
                    raise DataSourceError(f"Empty response from {url}")
                return body
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError) as exc:
            last_error = exc
            retryable = not isinstance(exc, urllib.error.HTTPError) or exc.code in {
                408,
                429,
                500,
                502,
                503,
                504,
            }
            if not retryable or attempt == attempts - 1:
                break
            time.sleep(0.45 * (2**attempt))
    raise DataSourceError(f"Unable to read {url}: {last_error}")


def _request_json(
    url: str,
    params: dict[str, Any] | None = None,
    *,
    timeout: int = 18,
) -> dict[str, Any] | list[Any]:
    body = _request_bytes(url, params, timeout=timeout)
    try:
        return json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DataSourceError(f"Invalid JSON from {url}") from exc


def _as_float(value: Any, default: float | None = None) -> float | None:
    try:
        if value in (None, "", "-.--"):
            return default
        number = float(value)
        return number if math.isfinite(number) else default
    except (TypeError, ValueError):
        return default


def _parse_utc(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def _date_bounds(as_of_date: str) -> tuple[str, str, str]:
    target = date.fromisoformat(as_of_date)
    end = target - timedelta(days=1)
    season_start = date(target.year, 3, 1)
    recent_start = max(season_start, end - timedelta(days=13))
    return season_start.isoformat(), recent_start.isoformat(), end.isoformat()


def _status_class(abstract_state: str) -> str:
    state = (abstract_state or "").lower()
    if state == "live":
        return "LIVE"
    if state == "final":
        return "FINAL"
    return "PREVIEW"


def _normalize_team(game_side: dict[str, Any]) -> dict[str, Any]:
    team = game_side.get("team", {})
    pitcher = game_side.get("probablePitcher") or {}
    team_id = team.get("id")
    return {
        "id": team_id,
        "name": team.get("name", "Unknown team"),
        "short_name": team.get("teamName") or team.get("clubName") or team.get("name", "Team"),
        "abbreviation": team.get("abbreviation", "—"),
        "logo": (
            f"https://www.mlbstatic.com/team-logos/team-cap-on-dark/{team_id}.svg"
            if team_id
            else ""
        ),
        "wins": int((game_side.get("leagueRecord") or {}).get("wins") or 0),
        "losses": int((game_side.get("leagueRecord") or {}).get("losses") or 0),
        "pitcher_id": pitcher.get("id"),
        "pitcher_name": pitcher.get("fullName") or "Starter TBD",
    }


def _normalize_linescore(game: dict[str, Any]) -> dict[str, Any]:
    status = game.get("status") or {}
    abstract_state = status.get("abstractGameState", "Preview")
    model_status = _status_class(abstract_state)
    linescore = game.get("linescore") or {}
    line_teams = linescore.get("teams") or {}

    def score(side: str) -> int:
        line_score = (line_teams.get(side) or {}).get("runs")
        schedule_score = ((game.get("teams") or {}).get(side) or {}).get("score")
        return int(line_score if line_score is not None else schedule_score or 0)

    offense = linescore.get("offense") or {}
    inning = int(linescore.get("currentInning") or 0)
    inning_state = linescore.get("inningState") or ""
    ordinal = linescore.get("currentInningOrdinal") or (f"{inning}th" if inning else "")
    if model_status == "LIVE":
        label = f"LIVE • {inning_state} {ordinal}".strip()
    elif model_status == "FINAL":
        label = status.get("detailedState") or "FINAL"
    else:
        label = status.get("detailedState") or "Scheduled"

    return {
        "status": model_status,
        "status_label": label,
        "detailed_state": status.get("detailedState", "Scheduled"),
        "away_runs": score("away"),
        "home_runs": score("home"),
        "inning": inning,
        "inning_state": inning_state,
        "inning_ordinal": ordinal,
        "outs": int(linescore.get("outs") or 0),
        "has_1b": bool(offense.get("first")),
        "has_2b": bool(offense.get("second")),
        "has_3b": bool(offense.get("third")),
    }


def fetch_schedule(as_of_date: str) -> list[dict[str, Any]]:
    """Return a normalized MLB slate for one date."""
    payload = _request_json(
        f"{MLB_API_BASE}/schedule",
        {
            "sportId": 1,
            "date": as_of_date,
            "gameTypes": "R,P,F,D,L,W,C",
            "hydrate": "probablePitcher,team,venue(location,fieldInfo),linescore",
        },
    )
    dates = payload.get("dates", []) if isinstance(payload, dict) else []
    if not dates:
        return []

    games: list[dict[str, Any]] = []
    for raw in dates[0].get("games", []):
        venue = raw.get("venue") or {}
        location = venue.get("location") or {}
        coordinates = location.get("defaultCoordinates") or {}
        field_info = venue.get("fieldInfo") or {}
        teams = raw.get("teams") or {}
        game_dt = _parse_utc(raw.get("gameDate"))
        games.append(
            {
                "game_pk": int(raw.get("gamePk")),
                "official_date": raw.get("officialDate") or as_of_date,
                "game_datetime_utc": game_dt,
                "game_datetime_raw": raw.get("gameDate"),
                "away": _normalize_team(teams.get("away") or {}),
                "home": _normalize_team(teams.get("home") or {}),
                "venue": {
                    "id": venue.get("id"),
                    "name": venue.get("name") or "Venue TBD",
                    "latitude": _as_float(coordinates.get("latitude")),
                    "longitude": _as_float(coordinates.get("longitude")),
                    "azimuth": _as_float(location.get("azimuthAngle")),
                    "elevation": _as_float(location.get("elevation")),
                    "roof_type": field_info.get("roofType") or "Unknown",
                    "surface": field_info.get("turfType") or "Unknown",
                },
                "day_night": raw.get("dayNight") or "Unknown",
                "doubleheader": raw.get("doubleHeader") not in (None, "N"),
                "game_number": int(raw.get("gameNumber") or 1),
                "series_game_number": raw.get("seriesGameNumber"),
                "games_in_series": raw.get("gamesInSeries"),
                "series_description": raw.get("seriesDescription") or "",
                "live": _normalize_linescore(raw),
            }
        )
    return games


def _stats_splits(
    *,
    group: str,
    stats_type: str,
    season: int,
    start_date: str,
    end_date: str,
) -> dict[int, dict[str, Any]]:
    if end_date < start_date:
        return {}
    payload = _request_json(
        f"{MLB_API_BASE}/teams/stats",
        {
            "sportIds": 1,
            "season": season,
            "gameType": "R",
            "group": group,
            "stats": stats_type,
            "startDate": start_date,
            "endDate": end_date,
        },
    )
    blocks = payload.get("stats", []) if isinstance(payload, dict) else []
    if not blocks:
        return {}
    result: dict[int, dict[str, Any]] = {}
    for split in blocks[0].get("splits", []):
        team_id = (split.get("team") or {}).get("id")
        if team_id:
            result[int(team_id)] = split.get("stat") or {}
    return result


def fetch_team_stats(season: int, as_of_date: str) -> dict[int, dict[str, Any]]:
    """Return season-to-date and recent team data without same-day leakage."""
    season_start, recent_start, end_date = _date_bounds(as_of_date)
    jobs = {
        "hitting": ("hitting", "byDateRange", season_start, end_date),
        "pitching": ("pitching", "byDateRange", season_start, end_date),
        "fielding": ("fielding", "byDateRange", season_start, end_date),
        "recent_hitting": ("hitting", "byDateRange", recent_start, end_date),
        "recent_pitching": ("pitching", "byDateRange", recent_start, end_date),
    }
    output: dict[str, dict[int, dict[str, Any]]] = {}
    with ThreadPoolExecutor(max_workers=5) as pool:
        future_map = {
            pool.submit(
                _stats_splits,
                group=group,
                stats_type=stats_type,
                season=season,
                start_date=start,
                end_date=end,
            ): label
            for label, (group, stats_type, start, end) in jobs.items()
        }
        for future in as_completed(future_map):
            label = future_map[future]
            try:
                output[label] = future.result()
            except DataSourceError:
                output[label] = {}

    team_ids: set[int] = set()
    for values in output.values():
        team_ids.update(values)
    return {
        team_id: {label: output.get(label, {}).get(team_id, {}) for label in jobs}
        for team_id in team_ids
    }


def _combined_split(block: dict[str, Any]) -> dict[str, Any]:
    splits = block.get("splits", [])
    if not splits:
        return {}
    no_team = [split for split in splits if not split.get("team")]
    selected = no_team[-1] if no_team else splits[0]
    return selected.get("stat") or {}


def innings_to_float(value: Any) -> float:
    """Convert baseball innings notation (5.2 = 5 and 2/3) to a float."""
    if value in (None, ""):
        return 0.0
    text = str(value)
    if "." not in text:
        return float(text)
    whole, partial = text.split(".", 1)
    outs = int(partial[:1] or 0)
    if outs not in (0, 1, 2):
        return float(value)
    return float(whole) + outs / 3.0


def _single_pitcher_profile(player_id: int, season: int, as_of_date: str) -> dict[str, Any]:
    season_start, _, end_date = _date_bounds(as_of_date)
    payload = _request_json(
        f"{MLB_API_BASE}/people/{player_id}/stats",
        {
            "stats": "byDateRange,gameLog",
            "group": "pitching",
            "season": season,
            "gameType": "R",
            "startDate": season_start,
            "endDate": end_date,
        },
    )
    blocks = payload.get("stats", []) if isinstance(payload, dict) else []
    season_stat: dict[str, Any] = {}
    logs: list[dict[str, Any]] = []
    cutoff = date.fromisoformat(as_of_date)
    for block in blocks:
        block_name = (block.get("type") or {}).get("displayName")
        if block_name == "byDateRange":
            season_stat = _combined_split(block)
        elif block_name == "gameLog":
            for split in block.get("splits", []):
                try:
                    log_date = date.fromisoformat(split.get("date"))
                except (TypeError, ValueError):
                    continue
                if log_date >= cutoff:
                    continue
                stat = split.get("stat") or {}
                logs.append(
                    {
                        "date": log_date.isoformat(),
                        "opponent": (split.get("opponent") or {}).get("name", "—"),
                        "is_home": bool(split.get("isHome")),
                        "innings": stat.get("inningsPitched"),
                        "innings_float": innings_to_float(stat.get("inningsPitched")),
                        "earned_runs": int(stat.get("earnedRuns") or 0),
                        "hits": int(stat.get("hits") or 0),
                        "strikeouts": int(stat.get("strikeOuts") or 0),
                        "walks": int(stat.get("baseOnBalls") or 0),
                        "pitches": int(stat.get("numberOfPitches") or 0),
                    }
                )
    logs.sort(key=lambda item: item["date"], reverse=True)
    last_three = logs[:3]
    last_date = date.fromisoformat(logs[0]["date"]) if logs else None
    days_rest = (cutoff - last_date).days if last_date else None

    windows: dict[str, int] = {}
    for days in (7, 14, 30):
        windows[f"pitches_{days}d"] = sum(
            log["pitches"]
            for log in logs
            if (cutoff - date.fromisoformat(log["date"])).days <= days
        )

    return {
        "player_id": player_id,
        "season": season_stat,
        "last_three": last_three,
        "days_rest": days_rest,
        **windows,
    }


def fetch_pitcher_profiles(
    player_ids: Iterable[int], season: int, as_of_date: str
) -> dict[int, dict[str, Any]]:
    unique_ids = sorted({int(player_id) for player_id in player_ids if player_id})
    results: dict[int, dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=10) as pool:
        future_map = {
            pool.submit(_single_pitcher_profile, player_id, season, as_of_date): player_id
            for player_id in unique_ids
        }
        for future in as_completed(future_map):
            player_id = future_map[future]
            try:
                results[player_id] = future.result()
            except DataSourceError:
                results[player_id] = {
                    "player_id": player_id,
                    "season": {},
                    "last_three": [],
                    "days_rest": None,
                    "pitches_7d": 0,
                    "pitches_14d": 0,
                    "pitches_30d": 0,
                }
    return results


def _single_bullpen(team_id: int, season: int) -> dict[str, Any]:
    payload = _request_json(
        f"{MLB_API_BASE}/teams/{team_id}/stats",
        {
            "season": season,
            "gameType": "R",
            "group": "pitching",
            "stats": "statSplits",
            "sitCodes": "rp",
        },
    )
    blocks = payload.get("stats", []) if isinstance(payload, dict) else []
    if not blocks or not blocks[0].get("splits"):
        return {}
    return blocks[0]["splits"][0].get("stat") or {}


def fetch_bullpen_profiles(team_ids: Iterable[int], season: int) -> dict[int, dict[str, Any]]:
    unique_ids = sorted({int(team_id) for team_id in team_ids if team_id})
    results: dict[int, dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=10) as pool:
        future_map = {
            pool.submit(_single_bullpen, team_id, season): team_id for team_id in unique_ids
        }
        for future in as_completed(future_map):
            team_id = future_map[future]
            try:
                results[team_id] = future.result()
            except DataSourceError:
                results[team_id] = {}
    return results


def fetch_pitcher_statcast(season: int) -> dict[int, dict[str, Any]]:
    """Fetch official Savant expected/contact leaderboards once for the slate."""
    urls = {
        "expected": f"{SAVANT_BASE}/leaderboard/expected_statistics",
        "contact": f"{SAVANT_BASE}/leaderboard/statcast",
    }
    params = {
        "expected": {
            "type": "pitcher",
            "year": season,
            "position": "",
            "team": "",
            "filterType": "pa",
            "min": 1,
            "csv": "true",
        },
        "contact": {
            "type": "pitcher",
            "year": season,
            "position": "",
            "team": "",
            "min": 1,
            "csv": "true",
        },
    }
    tables: dict[str, list[dict[str, str]]] = {}
    for label, url in urls.items():
        try:
            body = _request_bytes(
                url + "?" + urllib.parse.urlencode(params[label]), timeout=32, attempts=2
            )
            tables[label] = list(csv.DictReader(io.StringIO(body.decode("utf-8-sig"))))
        except (DataSourceError, UnicodeDecodeError):
            tables[label] = []

    result: dict[int, dict[str, Any]] = {}
    for row in tables.get("expected", []):
        try:
            player_id = int(row.get("player_id") or 0)
        except ValueError:
            continue
        if not player_id:
            continue
        result[player_id] = {
            "pa": int(float(row.get("pa") or 0)),
            "xwoba": _as_float(row.get("est_woba")),
            "woba": _as_float(row.get("woba")),
            "xera": _as_float(row.get("xera")),
            "xba": _as_float(row.get("est_ba")),
            "xslg": _as_float(row.get("est_slg")),
        }
    for row in tables.get("contact", []):
        try:
            player_id = int(row.get("player_id") or 0)
        except ValueError:
            continue
        if not player_id:
            continue
        result.setdefault(player_id, {}).update(
            {
                "batted_balls": int(float(row.get("attempts") or 0)),
                "hard_hit_pct": _as_float(row.get("ev95percent")),
                "barrel_pct": _as_float(row.get("brl_percent")),
                "avg_exit_velocity": _as_float(row.get("avg_hit_speed")),
            }
        )
    return result


def fetch_park_factors(season: int) -> dict[int, dict[str, Any]]:
    """Read Baseball Savant's rolling three-year park-factor payload."""
    url = f"{SAVANT_BASE}/leaderboard/statcast-park-factors"
    body = _request_bytes(
        url,
        {
            "type": "year",
            "year": season,
            "batSide": "",
            "stat": "index_wOBA",
            "condition": "All",
            "rolling": 3,
            "parks": "mlb",
        },
        timeout=30,
        attempts=2,
    ).decode("utf-8", "ignore")
    match = re.search(r"var\s+data\s*=\s*", body)
    if not match:
        raise DataSourceError("Savant park-factor payload not found")
    try:
        rows, _ = json.JSONDecoder().raw_decode(body[match.end() :])
    except json.JSONDecodeError as exc:
        raise DataSourceError("Savant park-factor payload was invalid") from exc

    output: dict[int, dict[str, Any]] = {}
    for row in rows:
        try:
            venue_id = int(row.get("venue_id"))
        except (TypeError, ValueError):
            continue
        run_index = _as_float(row.get("index_runs"), 100.0) or 100.0
        woba_index = _as_float(row.get("index_woba"), 100.0) or 100.0
        output[venue_id] = {
            "run_factor": min(1.20, max(0.82, run_index / 100.0)),
            "woba_factor": min(1.20, max(0.82, woba_index / 100.0)),
            "sample_pa": int(float(row.get("n_pa") or 0)),
            "window": f"{season - 2}-{season}",
            "source": "Baseball Savant rolling 3-year park factors",
        }
    return output


def _weather_multiplier(
    temperature_f: float,
    humidity_pct: float,
    pressure_hpa: float,
    wind_mph: float,
    wind_from_degrees: float,
    field_azimuth: float | None,
) -> tuple[float, float | None]:
    temp_c = (temperature_f - 32.0) * 5.0 / 9.0
    saturation_hpa = 6.1078 * (10 ** ((7.5 * temp_c) / (237.3 + temp_c)))
    vapor_hpa = saturation_hpa * humidity_pct / 100.0
    dry_hpa = max(0.0, pressure_hpa - vapor_hpa)
    kelvin = temp_c + 273.15
    density = ((dry_hpa * 100.0) / (287.058 * kelvin)) + (
        (vapor_hpa * 100.0) / (461.495 * kelvin)
    )

    temperature_effect = (temperature_f - 70.0) * 0.0017
    density_effect = (1.204 - density) * 0.10
    out_component: float | None = None
    wind_effect = 0.0
    if field_azimuth is not None:
        wind_to = (wind_from_degrees + 180.0) % 360.0
        angle = math.radians(((wind_to - field_azimuth + 180.0) % 360.0) - 180.0)
        out_component = wind_mph * math.cos(angle)
        wind_effect = out_component * 0.0027
    multiplier = min(1.15, max(0.88, 1.0 + temperature_effect + density_effect + wind_effect))
    return multiplier, out_component


def _single_weather(game: dict[str, Any]) -> dict[str, Any]:
    venue = game["venue"]
    roof = (venue.get("roof_type") or "Unknown").lower()
    if any(word in roof for word in CONTROLLED_ROOF_WORDS):
        return {
            "available": True,
            "controlled": True,
            "description": "Climate controlled",
            "temperature_f": 72.0,
            "humidity_pct": None,
            "wind_mph": 0.0,
            "wind_direction": None,
            "out_to_center_mph": 0.0,
            "precip_probability": 0.0,
            "pressure_hpa": None,
            "run_multiplier": 1.0,
            "roof_uncertain": False,
        }
    lat, lon = venue.get("latitude"), venue.get("longitude")
    game_dt = game.get("game_datetime_utc")
    if lat is None or lon is None or game_dt is None:
        return {"available": False, "controlled": False, "run_multiplier": 1.0}

    day = game_dt.date().isoformat()
    payload = _request_json(
        OPEN_METEO_URL,
        {
            "latitude": lat,
            "longitude": lon,
            "start_date": day,
            "end_date": day,
            "timezone": "UTC",
            "temperature_unit": "fahrenheit",
            "wind_speed_unit": "mph",
            "hourly": (
                "temperature_2m,relative_humidity_2m,precipitation_probability,"
                "pressure_msl,wind_speed_10m,wind_direction_10m,weather_code"
            ),
        },
        timeout=16,
    )
    hourly = payload.get("hourly", {}) if isinstance(payload, dict) else {}
    times = hourly.get("time") or []
    if not times:
        return {"available": False, "controlled": False, "run_multiplier": 1.0}

    parsed_times = [_parse_utc(f"{value}:00Z" if len(value) == 16 else value) for value in times]
    index = min(
        range(len(times)),
        key=lambda i: abs((parsed_times[i] - game_dt).total_seconds()) if parsed_times[i] else 10**12,
    )

    def hourly_value(field: str, default: float) -> float:
        values = hourly.get(field) or []
        return float(values[index]) if index < len(values) and values[index] is not None else default

    temperature = hourly_value("temperature_2m", 72.0)
    humidity = hourly_value("relative_humidity_2m", 50.0)
    precip = hourly_value("precipitation_probability", 0.0)
    pressure = hourly_value("pressure_msl", 1013.25)
    wind = hourly_value("wind_speed_10m", 0.0)
    wind_direction = hourly_value("wind_direction_10m", 0.0)
    weather_code = int(hourly_value("weather_code", 0.0))
    multiplier, out_component = _weather_multiplier(
        temperature,
        humidity,
        pressure,
        wind,
        wind_direction,
        venue.get("azimuth"),
    )
    retractable = any(word in roof for word in RETRACTABLE_ROOF_WORDS)
    if retractable:
        multiplier = 1.0 + (multiplier - 1.0) * 0.5

    return {
        "available": True,
        "controlled": False,
        "description": WEATHER_CODES.get(weather_code, "Forecast"),
        "temperature_f": temperature,
        "humidity_pct": humidity,
        "wind_mph": wind,
        "wind_direction": wind_direction,
        "out_to_center_mph": out_component,
        "precip_probability": precip,
        "pressure_hpa": pressure,
        "run_multiplier": round(multiplier, 3),
        "roof_uncertain": retractable,
    }


def fetch_weather_slate(games: Iterable[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    games_list = list(games)
    results: dict[int, dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=8) as pool:
        future_map = {pool.submit(_single_weather, game): game["game_pk"] for game in games_list}
        for future in as_completed(future_map):
            game_pk = future_map[future]
            try:
                results[game_pk] = future.result()
            except DataSourceError:
                results[game_pk] = {
                    "available": False,
                    "controlled": False,
                    "run_multiplier": 1.0,
                }
    return results


def _single_lineup(game_pk: int) -> dict[str, Any]:
    payload = _request_json(f"{MLB_API_BASE}/game/{game_pk}/boxscore", timeout=12)
    teams = payload.get("teams", {}) if isinstance(payload, dict) else {}
    output: dict[str, Any] = {}
    for side in ("away", "home"):
        team_box = teams.get(side) or {}
        batter_ids = team_box.get("batters") or []
        players = team_box.get("players") or {}
        names: list[str] = []
        ordered: list[tuple[int, str]] = []
        for player_id in batter_ids:
            player = players.get(f"ID{player_id}") or {}
            order = player.get("battingOrder")
            name = ((player.get("person") or {}).get("fullName") or "").strip()
            if order and name:
                try:
                    ordered.append((int(order), name))
                except (TypeError, ValueError):
                    continue
        for _, name in sorted(ordered):
            if name not in names:
                names.append(name)
        output[side] = {
            "confirmed": len(names) >= 9,
            "count": len(names),
            "names": names[:9],
        }
    return output


def fetch_lineup_statuses(game_pks: Iterable[int]) -> dict[int, dict[str, Any]]:
    unique_ids = sorted({int(game_pk) for game_pk in game_pks})
    results: dict[int, dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=8) as pool:
        future_map = {pool.submit(_single_lineup, game_pk): game_pk for game_pk in unique_ids}
        for future in as_completed(future_map):
            game_pk = future_map[future]
            try:
                results[game_pk] = future.result()
            except DataSourceError:
                results[game_pk] = {
                    "away": {"confirmed": False, "count": 0, "names": []},
                    "home": {"confirmed": False, "count": 0, "names": []},
                }
    return results


def fetch_odds(api_key: str | None) -> list[dict[str, Any]]:
    if not api_key:
        return []
    payload = _request_json(
        ODDS_API_URL,
        {
            "apiKey": api_key,
            "regions": "us",
            "markets": "h2h,spreads,totals",
            "oddsFormat": "american",
            "dateFormat": "iso",
        },
        timeout=20,
    )
    return payload if isinstance(payload, list) else []


def _implied_probability(american_odds: float) -> float:
    if american_odds > 0:
        return 100.0 / (american_odds + 100.0)
    return -american_odds / (-american_odds + 100.0)


def match_moneyline_odds(game: dict[str, Any], events: list[dict[str, Any]]) -> dict[str, Any] | None:
    away_name = game["away"]["name"].lower()
    home_name = game["home"]["name"].lower()
    event = next(
        (
            item
            for item in events
            if str(item.get("away_team", "")).lower() == away_name
            and str(item.get("home_team", "")).lower() == home_name
        ),
        None,
    )
    if not event:
        return None

    book_rows: list[dict[str, Any]] = []
    totals: list[float] = []
    for book in event.get("bookmakers", []):
        markets = {market.get("key"): market for market in book.get("markets", [])}
        h2h = markets.get("h2h") or {}
        prices = {outcome.get("name"): outcome.get("price") for outcome in h2h.get("outcomes", [])}
        away_price = _as_float(prices.get(game["away"]["name"]))
        home_price = _as_float(prices.get(game["home"]["name"]))
        if away_price is not None and home_price is not None:
            away_raw = _implied_probability(away_price)
            home_raw = _implied_probability(home_price)
            overround = away_raw + home_raw
            book_rows.append(
                {
                    "book": book.get("title") or book.get("key") or "Sportsbook",
                    "away_price": int(away_price),
                    "home_price": int(home_price),
                    "away_no_vig": away_raw / overround,
                    "home_no_vig": home_raw / overround,
                    "updated": book.get("last_update"),
                }
            )
        total_market = markets.get("totals") or {}
        for outcome in total_market.get("outcomes", []):
            point = _as_float(outcome.get("point"))
            if point is not None:
                totals.append(point)
                break
    if not book_rows:
        return None
    return {
        "books": book_rows,
        "away_no_vig": sum(row["away_no_vig"] for row in book_rows) / len(book_rows),
        "home_no_vig": sum(row["home_no_vig"] for row in book_rows) / len(book_rows),
        "best_away_price": max(row["away_price"] for row in book_rows),
        "best_home_price": max(row["home_price"] for row in book_rows),
        "consensus_total": sorted(totals)[len(totals) // 2] if totals else None,
        "book_count": len(book_rows),
    }
import hashlib
import math
from typing import Any

import numpy as np



def safe_float(value: Any, default: float | None = None) -> float | None:
    try:
        if value in (None, "", "-.--"):
            return default
        number = float(value)
        return number if math.isfinite(number) else default
    except (TypeError, ValueError):
        return default


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def american_from_probability(probability: float) -> int:
    probability = clamp(probability, 0.001, 0.999)
    if probability >= 0.5:
        return int(round(-100.0 * probability / (1.0 - probability)))
    return int(round(100.0 * (1.0 - probability) / probability))


def implied_probability(american_odds: int | float) -> float:
    odds = float(american_odds)
    if odds > 0:
        return 100.0 / (odds + 100.0)
    return -odds / (-odds + 100.0)


def expected_roi(probability: float, american_odds: int | float) -> float:
    odds = float(american_odds)
    profit = odds / 100.0 if odds > 0 else 100.0 / -odds
    return probability * profit - (1.0 - probability)


def _weighted_mean(values: list[tuple[float | None, float]], fallback: float) -> float:
    valid = [(value, weight) for value, weight in values if value is not None and weight > 0]
    if not valid:
        return fallback
    denominator = sum(weight for _, weight in valid)
    return sum(float(value) * weight for value, weight in valid) / denominator


def _rate(stat: dict[str, Any], numerator: str, denominator: str) -> float | None:
    top = safe_float(stat.get(numerator))
    bottom = safe_float(stat.get(denominator))
    if top is None or bottom in (None, 0):
        return None
    return top / bottom


def build_league_context(team_stats: dict[int, dict[str, Any]]) -> dict[str, float]:
    hitting = [row.get("hitting", {}) for row in team_stats.values() if row.get("hitting")]
    pitching = [row.get("pitching", {}) for row in team_stats.values() if row.get("pitching")]
    fielding = [row.get("fielding", {}) for row in team_stats.values() if row.get("fielding")]

    total_runs = sum(safe_float(row.get("runs"), 0.0) or 0.0 for row in hitting)
    total_games = sum(safe_float(row.get("gamesPlayed"), 0.0) or 0.0 for row in hitting)
    league_rpg = total_runs / total_games if total_games else 4.45

    total_ab = sum(safe_float(row.get("atBats"), 0.0) or 0.0 for row in hitting)
    league_ops = (
        sum((safe_float(row.get("ops"), 0.715) or 0.715) * (safe_float(row.get("atBats"), 0.0) or 0.0) for row in hitting)
        / total_ab
        if total_ab
        else 0.715
    )

    total_ip = sum(innings_to_float(row.get("inningsPitched")) for row in pitching)
    total_er = sum(safe_float(row.get("earnedRuns"), 0.0) or 0.0 for row in pitching)
    league_era = total_er * 9.0 / total_ip if total_ip else 4.20

    total_hr = sum(safe_float(row.get("homeRuns"), 0.0) or 0.0 for row in pitching)
    total_bb = sum(safe_float(row.get("baseOnBalls"), 0.0) or 0.0 for row in pitching)
    total_hbp = sum(safe_float(row.get("hitByPitch"), 0.0) or 0.0 for row in pitching)
    total_k = sum(safe_float(row.get("strikeOuts"), 0.0) or 0.0 for row in pitching)
    raw_fip = (13.0 * total_hr + 3.0 * (total_bb + total_hbp) - 2.0 * total_k) / total_ip if total_ip else 1.05
    fip_constant = league_era - raw_fip

    total_bf = sum(safe_float(row.get("battersFaced"), 0.0) or 0.0 for row in pitching)
    league_whip = (
        sum((safe_float(row.get("whip"), 1.30) or 1.30) * (safe_float(row.get("battersFaced"), 0.0) or 0.0) for row in pitching)
        / total_bf
        if total_bf
        else 1.30
    )

    total_errors = sum(safe_float(row.get("errors"), 0.0) or 0.0 for row in fielding)
    field_games = sum(safe_float(row.get("gamesPlayed"), 0.0) or 0.0 for row in fielding)
    errors_per_game = total_errors / field_games if field_games else 0.55

    return {
        "runs_per_game": league_rpg,
        "ops": league_ops,
        "era": league_era,
        "whip": league_whip,
        "fip_constant": fip_constant,
        "errors_per_game": errors_per_game,
    }


def offense_profile(team_row: dict[str, Any], league: dict[str, float]) -> dict[str, float]:
    season = team_row.get("hitting", {})
    recent = team_row.get("recent_hitting", {})
    games = safe_float(season.get("gamesPlayed"), 0.0) or 0.0
    recent_games = safe_float(recent.get("gamesPlayed"), 0.0) or 0.0
    season_rpg = _rate(season, "runs", "gamesPlayed")
    recent_rpg = _rate(recent, "runs", "gamesPlayed")
    ops = safe_float(season.get("ops"))
    season_rpg = league["runs_per_game"] if season_rpg is None else season_rpg
    recent_rpg = season_rpg if recent_rpg is None else recent_rpg
    ops = league["ops"] if ops is None else ops

    season_index_raw = season_rpg / league["runs_per_game"]
    season_index = 1.0 + (season_index_raw - 1.0) * (games / (games + 24.0))
    ops_index_raw = math.exp((ops - league["ops"]) * 2.55)
    ops_index = 1.0 + (ops_index_raw - 1.0) * (games / (games + 30.0))
    recent_index_raw = recent_rpg / league["runs_per_game"]
    recent_index = 1.0 + (recent_index_raw - 1.0) * (recent_games / (recent_games + 24.0))
    strength = clamp(0.56 * season_index + 0.29 * ops_index + 0.15 * recent_index, 0.68, 1.38)
    return {
        "strength": strength,
        "season_rpg": season_rpg,
        "recent_rpg": recent_rpg,
        "ops": ops,
        "games": games,
    }


def _fip(stat: dict[str, Any], constant: float) -> float | None:
    innings = innings_to_float(stat.get("inningsPitched"))
    if innings <= 0:
        return None
    counts = [safe_float(stat.get(key)) for key in
              ("homeRuns", "baseOnBalls", "hitByPitch", "strikeOuts")]
    if any(value is None or value < 0 for value in counts):
        return None
    home_runs, walks, hit_batters, strikeouts = counts
    return (13.0 * home_runs + 3.0 * (walks + hit_batters) - 2.0 * strikeouts) / innings + constant


def starter_profile(
    profile: dict[str, Any], statcast: dict[str, Any], league: dict[str, float]
) -> dict[str, Any]:
    stat = profile.get("season", {})
    innings = innings_to_float(stat.get("inningsPitched"))
    games_started = safe_float(stat.get("gamesStarted"), 0.0) or 0.0
    batters_faced = safe_float(stat.get("battersFaced"), 0.0) or 0.0
    era = safe_float(stat.get("era"))
    whip = safe_float(stat.get("whip"))
    fip = _fip(stat, league["fip_constant"])
    xera = safe_float(statcast.get("xera"))
    whip_ra9 = (
        league["era"] * (whip / league["whip"]) ** 1.25 if whip and league["whip"] else None
    )

    last_three = profile.get("last_three", [])
    recent_ip = sum(safe_float(log.get("innings_float"), 0.0) or 0.0 for log in last_three)
    recent_er = sum(safe_float(log.get("earned_runs"), 0.0) or 0.0 for log in last_three)
    recent_era = recent_er * 9.0 / recent_ip if recent_ip >= 3 else None

    skill = _weighted_mean(
        [(xera, 0.34), (fip, 0.29), (era, 0.24), (whip_ra9, 0.13)],
        league["era"],
    )
    if recent_era is not None:
        skill = 0.91 * skill + 0.09 * clamp(recent_era, 1.0, 8.0)
    sample_weight = batters_faced / (batters_faced + 150.0)
    skill = league["era"] + (skill - league["era"]) * sample_weight
    skill = clamp(skill, 1.75, 7.25)

    season_ip_per_start = innings / games_started if games_started else 5.0
    recent_ip_per_start = recent_ip / len(last_three) if last_three else season_ip_per_start
    expected_ip = 0.67 * season_ip_per_start + 0.33 * recent_ip_per_start

    days_rest = profile.get("days_rest")
    fatigue_score = 18.0
    if days_rest is not None:
        if days_rest <= 3:
            fatigue_score += 42
            expected_ip -= 0.65
        elif days_rest == 4:
            fatigue_score += 20
            expected_ip -= 0.22
        elif days_rest >= 7:
            fatigue_score -= 5
    pitches_7d = int(profile.get("pitches_7d") or 0)
    pitches_14d = int(profile.get("pitches_14d") or 0)
    if pitches_7d > 108:
        fatigue_score += 18
        expected_ip -= 0.18
    if pitches_14d > 215:
        fatigue_score += 10
    expected_ip = clamp(expected_ip, 3.4, 7.1)

    return {
        "quality_ra9": skill,
        "expected_ip": expected_ip,
        "era": era,
        "fip": fip,
        "xera": xera,
        "xwoba": safe_float(statcast.get("xwoba")),
        "whip": whip,
        "k9": safe_float(stat.get("strikeoutsPer9Inn")),
        "bb9": safe_float(stat.get("walksPer9Inn")),
        "hard_hit_pct": safe_float(statcast.get("hard_hit_pct")),
        "barrel_pct": safe_float(statcast.get("barrel_pct")),
        "record": f"{int(stat.get('wins') or 0)}-{int(stat.get('losses') or 0)}" if stat else "—",
        "last_three": last_three,
        "days_rest": days_rest,
        "fatigue_score": clamp(fatigue_score, 0.0, 100.0),
        "sample_bf": batters_faced,
        "has_stats": innings > 0 and any(value is not None for value in (era, fip, xera, whip_ra9)),
        "has_statcast": xera is not None or safe_float(statcast.get("xwoba")) is not None,
    }


def bullpen_profile(
    bullpen_stat: dict[str, Any], team_pitching: dict[str, Any], league: dict[str, float]
) -> dict[str, Any]:
    stat = bullpen_stat or team_pitching or {}
    era = safe_float(stat.get("era"))
    whip = safe_float(stat.get("whip"))
    fip = _fip(stat, league["fip_constant"])
    whip_ra9 = (
        league["era"] * (whip / league["whip"]) ** 1.18 if whip and league["whip"] else None
    )
    quality = _weighted_mean(
        [(era, 0.46), (fip, 0.35), (whip_ra9, 0.19)], league["era"]
    )
    innings = innings_to_float(stat.get("inningsPitched"))
    sample_weight = innings / (innings + 80.0)
    quality = league["era"] + (quality - league["era"]) * sample_weight
    return {
        "quality_ra9": clamp(quality, 2.25, 6.50),
        "era": era,
        "fip": fip,
        "whip": whip,
        "has_split": bool(bullpen_stat),
    }


def defense_multiplier(team_row: dict[str, Any], league: dict[str, float]) -> float:
    fielding = team_row.get("fielding", {})
    errors_per_game = _rate(fielding, "errors", "gamesPlayed")
    if errors_per_game is None:
        return 1.0
    return clamp(1.0 + (errors_per_game - league["errors_per_game"]) * 0.055, 0.975, 1.025)


def _log5(team_a: float, team_b: float) -> float:
    team_a = clamp(team_a, 0.25, 0.75)
    team_b = clamp(team_b, 0.25, 0.75)
    denominator = team_a + team_b - 2.0 * team_a * team_b
    return (team_a - team_a * team_b) / denominator if denominator else 0.5


def _record_probability(game: dict[str, Any]) -> float:
    away_games = game["away"]["wins"] + game["away"]["losses"]
    home_games = game["home"]["wins"] + game["home"]["losses"]
    away_pct = game["away"]["wins"] / away_games if away_games else 0.5
    home_pct = game["home"]["wins"] / home_games if home_games else 0.5
    away_neutral = _log5(away_pct, home_pct)
    home_neutral = 1.0 - away_neutral
    logit = math.log(home_neutral / (1.0 - home_neutral)) + 0.105
    return 1.0 / (1.0 + math.exp(-logit))


def _seed_for_game(game: dict[str, Any], away_mean: float, home_mean: float) -> int:
    live = game["live"]
    value = (
        f"{game['game_pk']}|{away_mean:.4f}|{home_mean:.4f}|{live['status']}|"
        f"{live['away_runs']}|{live['home_runs']}|{live['inning']}|{live['inning_state']}|{live['outs']}"
    )
    return int.from_bytes(hashlib.sha256(value.encode("utf-8")).digest()[:8], "big")


def _negative_binomial_runs(rng: np.random.Generator, mean: float, count: int) -> np.ndarray:
    mean = max(0.001, mean)
    dispersion = 5.0
    probability = dispersion / (dispersion + mean)
    return rng.negative_binomial(dispersion, probability, size=count)


def _remaining_innings(live: dict[str, Any]) -> tuple[float, float]:
    inning = max(1, int(live.get("inning") or 1))
    outs = clamp(float(live.get("outs") or 0), 0.0, 3.0)
    current_fraction = (3.0 - outs) / 3.0
    state = str(live.get("inning_state") or "Top").lower()
    if state.startswith("top"):
        away = max(0.0, 9 - inning) + current_fraction
        home = max(0.0, 9 - inning + 1)
    elif state.startswith("bottom"):
        away = max(0.0, 9 - inning)
        home = max(0.0, 9 - inning) + current_fraction
    else:
        away = home = max(0.0, 9 - inning + 1)
    return away, home


def _base_state_bonus(live: dict[str, Any]) -> float:
    bonus = 0.0
    bonus += 0.24 if live.get("has_1b") else 0.0
    bonus += 0.42 if live.get("has_2b") else 0.0
    bonus += 0.62 if live.get("has_3b") else 0.0
    out_discount = [1.0, 0.72, 0.38, 0.0][min(3, int(live.get("outs") or 0))]
    return bonus * out_discount


def simulate_score_distribution(
    game: dict[str, Any],
    away_mean: float,
    home_mean: float,
    simulations: int,
    total_line: float | None = None,
) -> dict[str, Any]:
    simulations = int(clamp(float(simulations), 5_000, 100_000))
    rng = np.random.default_rng(_seed_for_game(game, away_mean, home_mean))
    live = game["live"]
    status = live["status"]

    if status == "FINAL":
        away_scores = np.full(simulations, int(live["away_runs"]), dtype=int)
        home_scores = np.full(simulations, int(live["home_runs"]), dtype=int)
    elif status == "LIVE":
        away_innings, home_innings = _remaining_innings(live)
        away_remaining_mean = away_mean / 9.0 * away_innings
        home_remaining_mean = home_mean / 9.0 * home_innings
        bonus = _base_state_bonus(live)
        if str(live.get("inning_state") or "").lower().startswith("top"):
            away_remaining_mean += bonus
        else:
            home_remaining_mean += bonus
        away_scores = int(live["away_runs"]) + _negative_binomial_runs(
            rng, away_remaining_mean, simulations
        )
        home_scores = int(live["home_runs"]) + _negative_binomial_runs(
            rng, home_remaining_mean, simulations
        )
    else:
        away_scores = _negative_binomial_runs(rng, away_mean, simulations)
        home_scores = _negative_binomial_runs(rng, home_mean, simulations)

    ties = away_scores == home_scores
    if np.any(ties):
        home_extra = rng.random(int(np.sum(ties))) < 0.54
        tie_indices = np.flatnonzero(ties)
        home_scores[tie_indices[home_extra]] += 1
        away_scores[tie_indices[~home_extra]] += 1

    home_win = float(np.mean(home_scores > away_scores))
    away_win = 1.0 - home_win
    totals = home_scores + away_scores
    differences = home_scores - away_scores
    total_line = 8.5 if total_line is None else float(total_line)
    return {
        "home_win": home_win,
        "away_win": away_win,
        "home_minus_1_5": float(np.mean(differences > 1.5)),
        "away_plus_1_5": float(np.mean(differences < 1.5)),
        "over_probability": float(np.mean(totals > total_line)),
        "under_probability": float(np.mean(totals < total_line)),
        "push_probability": float(np.mean(totals == total_line)),
        "median_away": float(np.median(away_scores)),
        "median_home": float(np.median(home_scores)),
        "mean_away": float(np.mean(away_scores)),
        "mean_home": float(np.mean(home_scores)),
        "total_line": total_line,
    }


def pregame_model_state(game: dict[str, Any]) -> dict[str, Any]:
    """Return a score-neutral copy of a game for a locked pregame forecast.

    The original game object still carries the real live/final state for the UI.
    Only the copy passed to the prediction simulation is neutralized, preventing
    the current score, inning, outs or occupied bases from changing the pick.
    """
    model_game = dict(game)
    model_game["live"] = {
        **(game.get("live") or {}),
        "status": "PREVIEW",
        "away_runs": 0,
        "home_runs": 0,
        "inning": 0,
        "inning_state": "",
        "outs": 0,
        "has_1b": False,
        "has_2b": False,
        "has_3b": False,
    }
    return model_game


def _data_quality(
    away_team: dict[str, Any],
    home_team: dict[str, Any],
    away_starter: dict[str, Any],
    home_starter: dict[str, Any],
    away_bullpen: dict[str, Any],
    home_bullpen: dict[str, Any],
    weather: dict[str, Any],
    lineup: dict[str, Any],
    agreement: float,
) -> tuple[int, str]:
    score = 18
    if away_team.get("hitting") and home_team.get("hitting"):
        score += 18
    if away_team.get("pitching") and home_team.get("pitching"):
        score += 10
    if away_starter["has_stats"] and home_starter["has_stats"]:
        score += 17
    elif away_starter["has_stats"] or home_starter["has_stats"]:
        score += 8
    if away_starter["has_statcast"] and home_starter["has_statcast"]:
        score += 12
    elif away_starter["has_statcast"] or home_starter["has_statcast"]:
        score += 6
    if away_bullpen["has_split"] and home_bullpen["has_split"]:
        score += 8
    if weather.get("available"):
        score += 6
    if weather.get("roof_uncertain"):
        score -= 3
    away_confirmed = (lineup.get("away") or {}).get("confirmed")
    home_confirmed = (lineup.get("home") or {}).get("confirmed")
    if away_confirmed and home_confirmed:
        score += 7
    elif away_confirmed or home_confirmed:
        score += 3
    if agreement <= 0.045:
        score += 4
    elif agreement >= 0.11:
        score -= 7
    score = int(clamp(score, 25, 98))
    label = "Higher" if score >= 84 else "Moderate" if score >= 68 else "Limited"
    return score, label


def _comparison_reasons(
    game: dict[str, Any],
    away_offense: dict[str, float],
    home_offense: dict[str, float],
    away_starter: dict[str, Any],
    home_starter: dict[str, Any],
    away_bullpen: dict[str, Any],
    home_bullpen: dict[str, Any],
    weather: dict[str, Any],
    target_side: str,
) -> tuple[list[str], list[str]]:
    target_name = game[target_side]["name"]
    opponent_side = "home" if target_side == "away" else "away"
    opponent_name = game[opponent_side]["name"]
    target_offense = away_offense if target_side == "away" else home_offense
    opponent_offense = home_offense if target_side == "away" else away_offense
    target_starter = away_starter if target_side == "away" else home_starter
    opponent_starter = home_starter if target_side == "away" else away_starter
    target_bullpen = away_bullpen if target_side == "away" else home_bullpen
    opponent_bullpen = home_bullpen if target_side == "away" else away_bullpen
    target_pitcher_name = game[target_side].get("pitcher_name") or "Listed starter"
    opponent_pitcher_name = game[opponent_side].get("pitcher_name") or "Opposing starter"

    supports: list[tuple[float, str]] = []
    risks: list[tuple[float, str]] = []
    offense_delta = target_offense["strength"] - opponent_offense["strength"]
    starter_delta = opponent_starter["quality_ra9"] - target_starter["quality_ra9"]
    bullpen_delta = opponent_bullpen["quality_ra9"] - target_bullpen["quality_ra9"]

    if offense_delta >= 0:
        supports.append(
            (
                abs(offense_delta),
                f"{target_name}'s blended offense grades {target_offense['strength']*100:.0f} "
                f"vs {opponent_name} {opponent_offense['strength']*100:.0f} "
                "(100 is league average; season/recent runs and OPS are included).",
            )
        )
    else:
        risks.append(
            (
                abs(offense_delta),
                f"{opponent_name}'s blended offense grades {opponent_offense['strength']*100:.0f} "
                f"vs {target_name} {target_offense['strength']*100:.0f}.",
            )
        )
    if target_starter["has_stats"] and opponent_starter["has_stats"] and starter_delta >= 0:
        supports.append(
            (
                abs(starter_delta) / 4,
                f"Starter blend favors {target_pitcher_name}: {target_starter['quality_ra9']:.2f} "
                f"vs {opponent_pitcher_name} {opponent_starter['quality_ra9']:.2f} "
                "estimated runs allowed per nine (lower is better).",
            )
        )
    elif target_starter["has_stats"] and opponent_starter["has_stats"]:
        risks.append(
            (
                abs(starter_delta) / 4,
                f"Starter blend favors {opponent_pitcher_name}: {opponent_starter['quality_ra9']:.2f} "
                f"vs {target_pitcher_name} {target_starter['quality_ra9']:.2f} (lower is better).",
            )
        )
    elif target_starter["has_stats"]:
        supports.append(
            (0.06, f"{target_pitcher_name} has a usable starter profile while the opposing starter remains uncertain.")
        )
    elif opponent_starter["has_stats"]:
        risks.append(
            (0.08, f"{target_pitcher_name}'s profile is incomplete while {opponent_pitcher_name} has usable data.")
        )
    else:
        risks.append((0.10, "Both starting-pitcher profiles are incomplete or still listed as TBD."))
    if target_bullpen["has_split"] and opponent_bullpen["has_split"] and bullpen_delta >= 0:
        supports.append(
            (
                abs(bullpen_delta) / 4,
                f"Relief pitching favors {target_name}: {target_bullpen['quality_ra9']:.2f} "
                f"vs {opponent_name} {opponent_bullpen['quality_ra9']:.2f} blended bullpen RA9.",
            )
        )
    elif target_bullpen["has_split"] and opponent_bullpen["has_split"]:
        risks.append(
            (
                abs(bullpen_delta) / 4,
                f"Relief pitching favors {opponent_name}: {opponent_bullpen['quality_ra9']:.2f} "
                f"vs {target_name} {target_bullpen['quality_ra9']:.2f} blended bullpen RA9.",
            )
        )
    else:
        risks.append((0.04, "A complete relief-pitching split was not available for both teams."))
    if target_starter["fatigue_score"] >= 48:
        risks.append((0.16, "Starter rest and recent pitch workload add fatigue uncertainty."))
    if weather.get("precip_probability", 0) >= 35:
        risks.append((0.12, "Rain or delay risk could change starter usage and bullpen exposure."))

    supports.sort(key=lambda item: item[0], reverse=True)
    risks.sort(key=lambda item: item[0], reverse=True)
    support_text = [text for _, text in supports[:3]] or ["The ensemble creates only a small matchup advantage."]
    risk_text = [text for _, text in risks[:3]] or ["Normal MLB outcome variance remains the largest risk."]
    return support_text, risk_text


def build_game_prediction(
    game: dict[str, Any],
    team_stats: dict[int, dict[str, Any]],
    pitcher_profiles: dict[int, dict[str, Any]],
    pitcher_statcast: dict[int, dict[str, Any]],
    bullpen_stats: dict[int, dict[str, Any]],
    park_factors: dict[int, dict[str, Any]],
    weather: dict[str, Any],
    lineup: dict[str, Any],
    moneyline_odds: dict[str, Any] | None,
    simulations: int = 30_000,
    lock_pregame: bool = True,
) -> dict[str, Any]:
    league = build_league_context(team_stats)
    away_id, home_id = game["away"]["id"], game["home"]["id"]
    away_team = team_stats.get(away_id, {})
    home_team = team_stats.get(home_id, {})
    away_offense = offense_profile(away_team, league)
    home_offense = offense_profile(home_team, league)

    away_pitcher_id = game["away"].get("pitcher_id")
    home_pitcher_id = game["home"].get("pitcher_id")
    away_starter = starter_profile(
        pitcher_profiles.get(away_pitcher_id, {}), pitcher_statcast.get(away_pitcher_id, {}), league
    )
    home_starter = starter_profile(
        pitcher_profiles.get(home_pitcher_id, {}), pitcher_statcast.get(home_pitcher_id, {}), league
    )
    away_bullpen = bullpen_profile(
        bullpen_stats.get(away_id, {}), away_team.get("pitching", {}), league
    )
    home_bullpen = bullpen_profile(
        bullpen_stats.get(home_id, {}), home_team.get("pitching", {}), league
    )

    away_staff = (
        away_starter["quality_ra9"] * away_starter["expected_ip"]
        + away_bullpen["quality_ra9"] * (9.0 - away_starter["expected_ip"])
    ) / 9.0
    home_staff = (
        home_starter["quality_ra9"] * home_starter["expected_ip"]
        + home_bullpen["quality_ra9"] * (9.0 - home_starter["expected_ip"])
    ) / 9.0

    venue_factor = park_factors.get(game["venue"].get("id"), {}).get("run_factor", 1.0)
    weather_factor = safe_float(weather.get("run_multiplier"), 1.0) or 1.0
    shared_environment = clamp(float(venue_factor) * weather_factor, 0.78, 1.28)
    away_mean = (
        league["runs_per_game"]
        * away_offense["strength"]
        * (home_staff / league["era"])
        * defense_multiplier(home_team, league)
        * shared_environment
    )
    home_mean = (
        league["runs_per_game"]
        * home_offense["strength"]
        * (away_staff / league["era"])
        * defense_multiplier(away_team, league)
        * shared_environment
        * 1.025
    )
    away_mean = clamp(away_mean, 2.0, 8.2)
    home_mean = clamp(home_mean, 2.0, 8.2)

    total_line = moneyline_odds.get("consensus_total") if moneyline_odds else None
    actual_status = game["live"]["status"]
    model_game = pregame_model_state(game) if lock_pregame else game
    distribution = simulate_score_distribution(
        model_game, away_mean, home_mean, simulations, total_line=total_line
    )
    record_home = _record_probability(game)
    sim_home = distribution["home_win"]
    model_status = model_game["live"]["status"]
    if model_status == "FINAL":
        home_probability = 1.0 if game["live"]["home_runs"] > game["live"]["away_runs"] else 0.0
    elif model_status == "LIVE":
        home_probability = 0.96 * sim_home + 0.04 * record_home
        home_probability = clamp(home_probability, 0.005, 0.995)
    else:
        raw_home = 0.78 * sim_home + 0.22 * record_home
        home_probability = 0.5 + (raw_home - 0.5) * 0.88
        home_probability = clamp(home_probability, 0.18, 0.82)
    away_probability = 1.0 - home_probability
    agreement = abs(sim_home - record_home)

    target_side = "home" if home_probability >= away_probability else "away"
    target_probability = max(home_probability, away_probability)
    support, risks = _comparison_reasons(
        game,
        away_offense,
        home_offense,
        away_starter,
        home_starter,
        away_bullpen,
        home_bullpen,
        weather,
        target_side,
    )
    quality_score, quality_label = _data_quality(
        away_team,
        home_team,
        away_starter,
        home_starter,
        away_bullpen,
        home_bullpen,
        weather,
        lineup,
        agreement,
    )

    value: dict[str, Any] | None = None
    if moneyline_odds and actual_status == "PREVIEW":
        candidates = []
        for side, model_probability in (("away", away_probability), ("home", home_probability)):
            market_probability = moneyline_odds[f"{side}_no_vig"]
            price = moneyline_odds[f"best_{side}_price"]
            candidates.append(
                {
                    "side": side,
                    "team": game[side]["name"],
                    "model_probability": model_probability,
                    "market_probability": market_probability,
                    "edge": model_probability - market_probability,
                    "price": price,
                    "expected_roi": expected_roi(model_probability, price),
                }
            )
        best = max(candidates, key=lambda item: item["edge"])
        best["qualifies"] = bool(best["edge"] >= 0.025 and quality_score >= 68)
        value = best

    lineup_confirmed = bool(
        (lineup.get("away") or {}).get("confirmed") and (lineup.get("home") or {}).get("confirmed")
    )
    invalidation = [
        "Either listed starter is scratched or placed on an opener/bulk plan.",
        "A confirmed lineup removes a key hitter or materially changes the batting order.",
    ]
    if value:
        invalidation.append("The available price moves beyond the model's fair value.")
    if weather.get("roof_uncertain") or weather.get("precip_probability", 0) >= 30:
        invalidation.append("Roof or weather conditions change materially before first pitch.")

    return {
        "game": game,
        "pregame_locked": bool(lock_pregame),
        "live_score_used": bool(not lock_pregame and actual_status in {"LIVE", "FINAL"}),
        "away_probability": away_probability,
        "home_probability": home_probability,
        "target_side": target_side,
        "target_name": game[target_side]["name"],
        "target_probability": target_probability,
        "fair_away_odds": american_from_probability(away_probability),
        "fair_home_odds": american_from_probability(home_probability),
        "projected_away_runs": away_mean,
        "projected_home_runs": home_mean,
        "distribution": distribution,
        "away_offense": away_offense,
        "home_offense": home_offense,
        "away_starter": away_starter,
        "home_starter": home_starter,
        "away_bullpen": away_bullpen,
        "home_bullpen": home_bullpen,
        "park_factor": venue_factor,
        "weather_factor": weather_factor,
        "quality_score": quality_score,
        "quality_label": quality_label,
        "model_agreement_gap": agreement,
        "simulation_home_probability": sim_home,
        "record_home_probability": record_home,
        "away_staff_ra9": away_staff,
        "home_staff_ra9": home_staff,
        "shared_environment_factor": shared_environment,
        "league_context": league,
        "simulations": int(simulations),
        "support": support,
        "risks": risks,
        "invalidation": invalidation,
        "lineup_confirmed": lineup_confirmed,
        "value": value,
        "odds": moneyline_odds,
        "methodology": (
            "Ensemble of opponent-adjusted run estimates, ERA/FIP/xERA starter quality, "
            "bullpen splits, team offense, defense, park/weather and Monte Carlo scoring."
        ),
    }
import random


_RUBIK_REGULAR_WOFF2 = "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"
_RUBIK_BOLD_WOFF2 = "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"


def native_stylesheet() -> str:
    """Small, stable visual layer for the native Streamlit interface.

    This intentionally styles Streamlit's own widgets instead of replacing
    them with large custom HTML blocks. The result keeps normal widget behavior
    while adding a sports-broadcast type system, card depth and subtle 3D orbs.
    """
    return (
        "<style>"
        "@font-face{font-family:'Quant Rubik';src:url(data:font/woff2;base64,"
        + _RUBIK_REGULAR_WOFF2
        + ") format('woff2');font-style:normal;font-weight:400;font-display:swap;}"
        "@font-face{font-family:'Quant Rubik';src:url(data:font/woff2;base64,"
        + _RUBIK_BOLD_WOFF2
        + ") format('woff2');font-style:normal;font-weight:700;font-display:swap;}"
        """

:root {
    --quant-bg-0: #050a12;
    --quant-bg-1: #091625;
    --quant-panel: rgba(10, 24, 39, .88);
    --quant-panel-strong: rgba(7, 18, 31, .96);
    --quant-line: rgba(125, 211, 252, .17);
    --quant-line-strong: rgba(103, 232, 249, .48);
    --quant-cyan: #5ee7f7;
    --quant-blue: #60a5fa;
    --quant-mint: #6ee7b7;
    --quant-red: #fb7185;
    --quant-text: #f5f8fc;
    --quant-muted: #9fb0c3;
}

html, body, .stApp,
[data-testid="stAppViewContainer"],
[data-testid="stMainBlockContainer"] {
    font-family: "Quant Rubik", "Aptos", "Segoe UI Variable", sans-serif !important;
}

.stApp {
    font-size: 15.5px;
    color: var(--quant-text);
    background-color: var(--quant-bg-0);
    background-image:
        radial-gradient(ellipse at 8% -8%, rgba(14,165,233,.23), transparent 39%),
        radial-gradient(ellipse at 98% 18%, rgba(37,99,235,.14), transparent 34%),
        linear-gradient(138deg, #040910 0%, #091827 48%, #06111d 100%);
    background-attachment: fixed;
}

.stApp::before,
.stApp::after { display: none !important; }

.quant-bubbles {
    position: fixed;
    inset: 0;
    overflow: hidden;
    pointer-events: none;
    z-index: 0;
    contain: strict;
}

.quant-bubble {
    position: absolute;
    left: var(--bubble-left);
    bottom: calc(-1 * var(--bubble-size) - 24px);
    width: var(--bubble-size);
    height: var(--bubble-size);
    display: block;
    border-radius: 999px;
    border: 1px solid rgba(186,230,253,.34);
    background:
        radial-gradient(circle at 28% 23%, rgba(255,255,255,.72) 0 2.5%, rgba(224,247,255,.30) 4%, transparent 11%),
        radial-gradient(circle at 32% 29%, rgba(186,230,253,.20), rgba(56,189,248,.10) 28%, rgba(14,69,109,.07) 55%, transparent 72%);
    box-shadow:
        inset -14px -16px 26px rgba(0,7,18,.52),
        inset 8px 8px 17px rgba(255,255,255,.09),
        0 10px 28px rgba(0,0,0,.18),
        0 0 20px rgba(56,189,248,.11);
    opacity: var(--bubble-opacity);
    animation: quantBubbleLift var(--bubble-duration) linear var(--bubble-delay) infinite !important;
    will-change: transform;
    transform: translate3d(0, 0, 0) scale(.86);
}

@keyframes quantBubbleLift {
    0% {
        transform: translate3d(0, 0, 0) scale(.86) rotate(0deg);
    }
    24% {
        transform: translate3d(var(--bubble-drift), -27vh, 0) scale(.94) rotate(4deg);
    }
    52% {
        transform: translate3d(var(--bubble-return), -58vh, 0) scale(1) rotate(-3deg);
    }
    78% {
        transform: translate3d(var(--bubble-soft-drift), -88vh, 0) scale(1.04) rotate(3deg);
    }
    100% {
        transform: translate3d(var(--bubble-exit-drift), calc(-100vh - 190px), 0) scale(1.08) rotate(0deg);
    }
}

[data-testid="stAppViewContainer"] {
    position: relative;
    z-index: 1;
    background: transparent;
}

[data-testid="stHeader"] {
    background: rgba(5, 10, 18, .76);
    border-bottom: 1px solid rgba(125,211,252,.08);
}

[data-testid="stMainBlockContainer"] {
    position: relative;
    z-index: 2;
    max-width: 1480px;
    padding-top: 1.35rem;
    padding-bottom: 4rem;
}

h1, h2, h3, h4,
[data-testid="stHeadingWithActionElements"] {
    font-family: "Quant Rubik", "Aptos", "Segoe UI Variable", sans-serif !important;
    font-stretch: normal;
    font-weight: 750 !important;
    letter-spacing: -.028em !important;
    color: var(--quant-text) !important;
}

h2 { letter-spacing: -.032em !important; }
p, label, li, [data-testid="stCaptionContainer"] {
    color: inherit;
}
[data-testid="stCaptionContainer"] {
    color: var(--quant-muted) !important;
    font-size: .82rem !important;
    line-height: 1.45 !important;
}

hr {
    border-color: rgba(125,211,252,.14) !important;
    margin: .85rem 0 1rem !important;
}

[data-testid="stVerticalBlockBorderWrapper"] {
    border-color: var(--quant-line) !important;
    border-radius: 15px !important;
    background: linear-gradient(148deg, rgba(13,30,48,.92), rgba(7,18,31,.88)) !important;
    box-shadow: 0 14px 34px rgba(0,0,0,.22), inset 0 1px 0 rgba(255,255,255,.035);
}

[class*="st-key-score_card_"] [data-testid="stVerticalBlockBorderWrapper"] {
    position: relative;
    overflow: hidden;
    min-height: 214px;
    border-color: rgba(94,231,247,.25) !important;
    background: linear-gradient(155deg, rgba(13,34,55,.97), rgba(6,18,32,.95)) !important;
    box-shadow: 0 16px 34px rgba(0,0,0,.28), inset 0 1px 0 rgba(255,255,255,.05);
    transition: transform .16s ease, border-color .16s ease, box-shadow .16s ease;
}

[class*="st-key-score_card_"] [data-testid="stVerticalBlockBorderWrapper"]::before {
    content: "";
    position: absolute;
    inset: 0 0 auto 0;
    height: 3px;
    background: linear-gradient(90deg, var(--quant-blue), var(--quant-cyan), var(--quant-mint));
    opacity: .85;
}

[class*="st-key-score_card_"]:hover [data-testid="stVerticalBlockBorderWrapper"] {
    transform: translateY(-2px);
    border-color: var(--quant-line-strong) !important;
    box-shadow: 0 20px 42px rgba(0,0,0,.34), 0 0 24px rgba(34,211,238,.08);
}

[class*="st-key-matchup_row_"] [data-testid="stVerticalBlockBorderWrapper"] {
    position: relative;
    overflow: hidden;
    padding: 1.08rem 1.18rem .96rem !important;
    border: 1px solid rgba(125,211,252,.11) !important;
    border-left: 1px solid rgba(125,211,252,.11) !important;
    border-radius: 18px !important;
    background:
        radial-gradient(circle at 92% 14%, rgba(96,165,250,.085), transparent 31%),
        linear-gradient(145deg, rgba(12,29,46,.975), rgba(7,18,31,.965)) !important;
    box-shadow:
        0 17px 40px rgba(0,0,0,.25),
        inset 0 1px 0 rgba(255,255,255,.035) !important;
    transition: transform .18s ease, border-color .18s ease, box-shadow .18s ease;
}

[class*="st-key-matchup_row_"] [data-testid="stVerticalBlockBorderWrapper"]::before {
    content: "";
    position: absolute;
    inset: 0 auto 0 0;
    width: 4px;
    background: linear-gradient(180deg, var(--quant-cyan), var(--quant-blue));
    box-shadow: 0 0 22px rgba(94,231,247,.30);
}

[class*="st-key-matchup_row_"]:hover [data-testid="stVerticalBlockBorderWrapper"] {
    transform: translateY(-2px);
    border-color: rgba(103,232,249,.34) !important;
    box-shadow:
        0 22px 48px rgba(0,0,0,.34),
        0 0 28px rgba(34,211,238,.06),
        inset 0 1px 0 rgba(255,255,255,.055) !important;
}

[class*="st-key-matchup_row_"] [data-testid="stHorizontalBlock"] {
    gap: 1rem !important;
}

[class*="st-key-matchup_row_"] [data-testid="stProgress"] {
    margin-top: .35rem;
}

[class*="st-key-matchup_row_"] [data-testid="stProgress"] > div {
    height: .52rem !important;
    border-radius: 999px !important;
    background: rgba(4,12,22,.82) !important;
    box-shadow: inset 0 1px 4px rgba(0,0,0,.46);
}

[class*="st-key-matchup_row_"] [data-testid="stProgress"] p {
    font-size: .78rem !important;
    font-weight: 700 !important;
    color: #c7d6e6 !important;
}

.matchup-team-stack {
    display: grid;
    gap: .32rem;
    min-width: 0;
}

.matchup-team-line {
    display: flex;
    align-items: center;
    gap: .68rem;
    min-width: 0;
}

.matchup-team-line img {
    width: 32px;
    height: 32px;
    object-fit: contain;
    filter: drop-shadow(0 5px 7px rgba(0,0,0,.42));
    flex: 0 0 32px;
}

.matchup-team-name {
    overflow: hidden;
    color: #f7fbff;
    font-family: "Quant Rubik", "Aptos", "Segoe UI Variable", sans-serif;
    font-size: 1.02rem;
    font-weight: 750;
    letter-spacing: -.018em;
    line-height: 1.25;
    text-overflow: ellipsis;
    white-space: nowrap;
}

.matchup-at {
    margin-left: 43px;
    color: #7f94a8;
    font-size: .70rem;
    font-weight: 650;
    letter-spacing: .02em;
    line-height: .85;
}

.matchup-kicker {
    margin-bottom: .42rem;
    color: #91a6ba;
    font-size: .73rem;
    font-weight: 650;
    letter-spacing: .005em;
}

.matchup-probability-labels {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: .5rem;
    margin-bottom: .5rem;
    color: #d2deea;
    font-size: .77rem;
    font-weight: 700;
}

.matchup-probability-labels span:last-child {
    text-align: right;
}

.matchup-probability-bar {
    display: flex;
    width: 100%;
    height: 9px;
    overflow: hidden;
    border: 2px solid rgba(4,12,22,.80);
    border-radius: 999px;
    background: rgba(4,12,22,.82);
    box-shadow: inset 0 1px 5px rgba(0,0,0,.58), 0 0 16px rgba(34,211,238,.05);
}

.matchup-probability-away {
    width: var(--away-probability);
    background: linear-gradient(90deg, var(--away-secondary), var(--away-primary));
    box-shadow: 4px 0 12px color-mix(in srgb, var(--away-primary) 34%, transparent);
}

.matchup-probability-home {
    flex: 1;
    background: linear-gradient(90deg, var(--home-primary), var(--home-secondary));
}

.matchup-pick-card {
    position: relative;
    overflow: hidden;
    min-height: 88px;
    padding: .78rem .82rem;
    border: 1px solid rgba(110,231,183,.13);
    border-radius: 14px;
    background: linear-gradient(145deg, rgba(15,53,54,.35), rgba(5,18,29,.48));
}

.matchup-pick-card::after {
    content: "";
    position: absolute;
    width: 54px;
    height: 54px;
    right: -18px;
    bottom: -24px;
    border-radius: 50%;
    background: radial-gradient(circle, rgba(110,231,183,.16), transparent 68%);
}

.matchup-score-lines {
    display: grid;
    gap: .3rem;
}

.matchup-score-line {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: .4rem;
    color: #bccbd9;
    font-size: .77rem;
    font-weight: 600;
}

.matchup-score-line strong {
    color: #f7fbff;
    font-family: "Quant Rubik", "Aptos", "Segoe UI Variable", sans-serif;
    font-size: .96rem;
    font-weight: 750;
    line-height: 1.15;
}

.matchup-value {
    color: #f7fbff;
    font-family: "Quant Rubik", "Aptos", "Segoe UI Variable", sans-serif;
    font-size: .98rem;
    font-weight: 750;
    letter-spacing: -.02em;
    line-height: 1.28;
}

.matchup-value--pick {
    color: #8ff3df;
    font-size: 1.06rem;
}

.matchup-subvalue {
    margin-top: .32rem;
    color: #9eb1c3;
    font-size: .76rem;
    font-weight: 550;
    line-height: 1.4;
}

.matchup-status {
    display: inline-flex;
    align-items: center;
    gap: .38rem;
    width: fit-content;
    padding: .34rem .58rem;
    border: 1px solid rgba(148,163,184,.18);
    border-radius: 999px;
    background: rgba(4,12,22,.52);
    color: #dce8f4;
    font-size: .68rem;
    font-weight: 700;
    letter-spacing: .045em;
    text-transform: uppercase;
}

.matchup-status::before {
    content: "";
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: #94a3b8;
    box-shadow: 0 0 10px rgba(148,163,184,.35);
}

.matchup-status--live {
    border-color: rgba(251,113,133,.30);
    color: #fecdd3;
}

.matchup-status--live::before {
    background: #fb7185;
    box-shadow: 0 0 12px rgba(251,113,133,.72);
    animation: quantLivePulse 1.35s ease-in-out infinite;
}

.matchup-status--final {
    border-color: rgba(110,231,183,.27);
    color: #bbf7d0;
}

.matchup-status--final::before {
    background: #6ee7b7;
    box-shadow: 0 0 10px rgba(110,231,183,.45);
}

.matchup-start {
    color: #eef6ff;
    font-family: "Quant Rubik", "Aptos", "Segoe UI Variable", sans-serif;
    font-size: .79rem;
    font-weight: 700;
    text-align: right;
}

.matchup-game-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: .5rem;
}

.matchup-score-kicker {
    margin-top: .78rem;
}

.matchup-context-strip {
    margin-top: .22rem;
    padding-top: .78rem;
    border-top: 1px solid rgba(125,211,252,.085);
    color: #91a5b8;
    font-size: .76rem;
    font-weight: 500;
    line-height: 1.45;
}

.matchup-quality {
    display: grid;
    gap: .08rem;
    padding-top: .76rem;
    color: #8fa3b6;
    font-size: .69rem;
    font-weight: 600;
    line-height: 1.2;
}

.matchup-quality strong {
    color: #edf5fc;
    font-size: .86rem;
    font-weight: 750;
}

.matchup-quality small {
    color: #7890a5;
    font-size: .66rem;
    font-weight: 550;
}

[class*="st-key-matchup_row_"] [data-testid="stBaseButton-secondary"] {
    min-height: 40px;
    margin-top: .54rem;
    border-color: rgba(125,211,252,.20) !important;
    border-radius: 11px !important;
    background: linear-gradient(135deg, rgba(13,39,59,.96), rgba(12,31,51,.96)) !important;
    color: #e7f3fc !important;
    font-size: .79rem !important;
    box-shadow: inset 0 1px 0 rgba(255,255,255,.035), 0 8px 18px rgba(0,0,0,.14) !important;
}

[class*="st-key-matchup_row_"] [data-testid="stBaseButton-secondary"]:hover {
    border-color: rgba(103,232,249,.48) !important;
    background: linear-gradient(135deg, rgba(16,55,78,.98), rgba(14,39,62,.98)) !important;
}

@keyframes quantLivePulse {
    0%, 100% { opacity: .68; transform: scale(.9); }
    50% { opacity: 1; transform: scale(1.16); }
}

[data-testid="stImage"] img {
    filter: drop-shadow(0 5px 8px rgba(0,0,0,.42));
}

[data-baseweb="tab-list"] {
    gap: .35rem;
    padding: .3rem;
    border: 1px solid rgba(125,211,252,.14);
    border-radius: 12px;
    background: rgba(5,15,27,.72);
}

[data-baseweb="tab"] {
    border-radius: 9px;
    font-family: "Quant Rubik", "Aptos", "Segoe UI Variable", sans-serif !important;
    font-weight: 650 !important;
    letter-spacing: .015em;
}

[aria-selected="true"][data-baseweb="tab"] {
    background: linear-gradient(135deg, rgba(14,116,144,.48), rgba(37,99,235,.25));
}

[data-testid="stBaseButton-primary"],
[data-testid="stBaseButton-secondary"],
[data-testid="stPopoverButton"] button {
    border-radius: 10px !important;
    font-family: "Quant Rubik", "Aptos", "Segoe UI Variable", sans-serif !important;
    font-weight: 700 !important;
    letter-spacing: .01em;
    transition: transform .14s ease, border-color .14s ease, box-shadow .14s ease;
}

[data-testid="stBaseButton-primary"] {
    background: linear-gradient(135deg, #0891b2, #2563eb) !important;
    border-color: rgba(103,232,249,.62) !important;
    box-shadow: 0 8px 20px rgba(8,145,178,.20);
}

[data-testid="stBaseButton-secondary"] {
    background: rgba(11,29,47,.86) !important;
    border-color: rgba(125,211,252,.24) !important;
}

[data-testid="stBaseButton-primary"]:hover,
[data-testid="stBaseButton-secondary"]:hover {
    transform: translateY(-1px);
    border-color: rgba(103,232,249,.62) !important;
    box-shadow: 0 10px 24px rgba(0,0,0,.22), 0 0 17px rgba(34,211,238,.08);
}

[data-testid="stMetric"] {
    padding: .72rem .8rem;
    border: 1px solid rgba(125,211,252,.14);
    border-radius: 12px;
    background: rgba(5,17,30,.56);
}

[data-testid="stMetricValue"] {
    font-family: "Quant Rubik", "Aptos", "Segoe UI Variable", sans-serif !important;
    font-weight: 750 !important;
    color: #f8fbff !important;
}

[data-testid="stProgress"] > div > div {
    background: linear-gradient(90deg, var(--quant-blue), var(--quant-cyan), var(--quant-mint)) !important;
}

[data-testid="stExpander"] {
    border-color: rgba(125,211,252,.20) !important;
    border-radius: 0 0 17px 17px !important;
    background: linear-gradient(150deg, rgba(7,19,33,.94), rgba(5,14,25,.92)) !important;
    box-shadow: 0 18px 42px rgba(0,0,0,.24);
}

[data-baseweb="input"],
[data-baseweb="select"] > div,
[data-testid="stDateInput"] input {
    background: rgba(5,17,30,.90) !important;
    border-color: rgba(125,211,252,.22) !important;
}

[data-testid="stAlert"] {
    border-radius: 12px !important;
    border-color: rgba(125,211,252,.16) !important;
}

a { color: #72e6f4; }

/* Premium sports-product layer. These selectors stay intentionally simple so
   Streamlit can rerun without remounting or hiding the app. */
.stApp {
    font-size: 16px;
    background-image:
        radial-gradient(ellipse at 10% -12%, rgba(14,165,233,.18), transparent 38%),
        radial-gradient(ellipse at 96% 16%, rgba(37,99,235,.10), transparent 31%),
        linear-gradient(145deg, #04080e 0%, #081523 50%, #050d17 100%);
}

[data-testid="stMainBlockContainer"] {
    max-width: 1440px;
    padding-top: 1.15rem;
}

h1, h2, h3, h4,
[data-testid="stHeadingWithActionElements"] {
    font-weight: 700 !important;
    letter-spacing: -.032em !important;
}

h2 { font-size: 1.52rem !important; }
h3 { font-size: 1.17rem !important; }

.quant-brand {
    display: flex;
    align-items: center;
    gap: .78rem;
    min-height: 48px;
}

.quant-brand-mark {
    position: relative;
    display: grid;
    place-items: center;
    width: 42px;
    height: 42px;
    overflow: hidden;
    border-radius: 12px;
    background: linear-gradient(145deg, #8cf2ff 0%, #27b9d7 50%, #2563eb 100%);
    color: #03101b;
    font-size: 1.05rem;
    font-weight: 700;
    box-shadow: 0 10px 27px rgba(16,185,219,.21), inset 0 1px 0 rgba(255,255,255,.48);
}

.quant-brand-mark::after {
    content: "";
    position: absolute;
    width: 52px;
    height: 1px;
    background: rgba(3,16,27,.34);
    transform: rotate(-35deg);
}

.quant-brand-title {
    color: #f8fbff;
    font-size: 1.16rem;
    font-weight: 700;
    letter-spacing: -.035em;
    line-height: 1.15;
}

.quant-brand-heading {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: .48rem;
}

.quant-build {
    display: inline-flex;
    align-items: center;
    padding: .2rem .48rem;
    border: 1px solid rgba(81, 213, 255, .32);
    border-radius: 999px;
    background: rgba(31, 172, 218, .1);
    color: #7bdef8;
    font-size: .57rem;
    font-weight: 700;
    letter-spacing: .08em;
    line-height: 1;
    text-transform: uppercase;
}

.quant-brand-subtitle {
    margin-top: .22rem;
    color: #8699ac;
    font-size: .76rem;
    line-height: 1.25;
}

.quant-sync {
    display: flex;
    align-items: center;
    justify-content: flex-end;
    gap: .52rem;
    min-height: 44px;
}

.quant-sync-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: #5ee7b7;
    box-shadow: 0 0 0 4px rgba(94,231,183,.09), 0 0 12px rgba(94,231,183,.42);
}

.quant-sync-copy span {
    display: block;
    color: #a7f3d0;
    font-size: .68rem;
    font-weight: 700;
    letter-spacing: .025em;
}

.quant-sync-copy small {
    display: block;
    margin-top: .12rem;
    color: #75899e;
    font-size: .67rem;
}

.model-note {
    margin: .95rem 0 1.12rem;
    padding: .78rem .94rem;
    border-left: 3px solid #fbbf24;
    border-radius: 9px;
    background: rgba(120,53,15,.12);
    color: #c9d5e1;
    font-size: .78rem;
    line-height: 1.5;
}

/* Compact score center */
[class*="st-key-score_card_"] [data-testid="stVerticalBlockBorderWrapper"] {
    min-height: 0;
    padding: .88rem .9rem .78rem !important;
    border: 1px solid rgba(148,163,184,.09) !important;
    border-radius: 16px !important;
    background:
        radial-gradient(circle at 94% 0%, rgba(96,165,250,.08), transparent 35%),
        linear-gradient(150deg, rgba(13,29,45,.97), rgba(7,17,29,.97)) !important;
    box-shadow: 0 14px 30px rgba(0,0,0,.25), inset 0 1px 0 rgba(255,255,255,.032) !important;
}

[class*="st-key-score_card_"] [data-testid="stVerticalBlockBorderWrapper"]::before {
    height: 2px;
    opacity: .92;
}

[class*="st-key-score_card_"]:hover [data-testid="stVerticalBlockBorderWrapper"] {
    transform: translateY(-2px);
    border-color: rgba(103,232,249,.24) !important;
    box-shadow: 0 18px 36px rgba(0,0,0,.31), 0 0 24px rgba(34,211,238,.045) !important;
}

.score-tile {
    display: grid;
    gap: .45rem;
}

.score-tile-head,
.score-tile-team,
.score-tile-model {
    display: flex;
    align-items: center;
}

.score-tile-head {
    justify-content: space-between;
    gap: .5rem;
    margin-bottom: .08rem;
}

.score-tile-status {
    display: inline-flex;
    align-items: center;
    gap: .34rem;
    color: #aebdca;
    font-size: .66rem;
    font-weight: 700;
}

.score-tile-status::before {
    content: "";
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: #94a3b8;
}

.score-tile-status.live { color: #fecdd3; }
.score-tile-status.live::before {
    background: #fb7185;
    box-shadow: 0 0 10px rgba(251,113,133,.72);
    animation: quantLivePulse 1.35s ease-in-out infinite;
}
.score-tile-status.final { color: #bbf7d0; }
.score-tile-status.final::before { background: #6ee7b7; }

.score-tile-time {
    color: #778b9f;
    font-size: .66rem;
    text-align: right;
}

.score-tile-team {
    display: grid;
    grid-template-columns: 29px minmax(0,1fr) auto;
    gap: .56rem;
    min-height: 36px;
}

.score-tile-team + .score-tile-team {
    border-top: 1px solid rgba(148,163,184,.075);
    padding-top: .42rem;
}

.score-tile-team img {
    width: 28px;
    height: 28px;
    object-fit: contain;
    filter: drop-shadow(0 5px 7px rgba(0,0,0,.40));
}

.score-tile-team-name {
    overflow: hidden;
    color: #f3f7fb;
    font-size: .87rem;
    font-weight: 700;
    letter-spacing: -.018em;
    text-overflow: ellipsis;
    white-space: nowrap;
}

.score-tile-team-record {
    margin-top: .08rem;
    color: #71869a;
    font-size: .63rem;
}

.score-tile-value {
    color: #f8fbff;
    font-size: 1.04rem;
    font-weight: 700;
    font-variant-numeric: tabular-nums;
}

.score-tile-model {
    justify-content: space-between;
    gap: .55rem;
    margin-top: .12rem;
    padding-top: .56rem;
    border-top: 1px solid rgba(148,163,184,.085);
}

.score-tile-model span {
    color: #74899c;
    font-size: .63rem;
}

.score-tile-model strong {
    color: #8ff3df;
    font-size: .76rem;
    font-weight: 700;
    text-align: right;
}

[class*="st-key-score_card_"] [data-testid="stBaseButton-secondary"],
[class*="st-key-score_card_"] [data-testid="stBaseButton-primary"] {
    min-height: 34px;
    margin-top: .52rem;
    border: 0 !important;
    border-radius: 9px !important;
    background: rgba(71,118,153,.14) !important;
    color: #d7e7f3 !important;
    font-size: .72rem !important;
    box-shadow: none !important;
}

[class*="st-key-score_card_"] [data-testid="stBaseButton-secondary"]:hover,
[class*="st-key-score_card_"] [data-testid="stBaseButton-primary"]:hover {
    background: rgba(49,169,196,.18) !important;
    color: #ecfeff !important;
}

/* Slate insight cards */
[class*="st-key-insight_"] [data-testid="stVerticalBlockBorderWrapper"] {
    min-height: 126px;
    padding: .88rem .92rem !important;
    border: 1px solid rgba(148,163,184,.075) !important;
    border-radius: 15px !important;
    background: linear-gradient(150deg, rgba(12,27,43,.94), rgba(7,17,29,.94)) !important;
    box-shadow: 0 12px 27px rgba(0,0,0,.21), inset 0 1px 0 rgba(255,255,255,.025) !important;
}

.insight-card-body {
    display: grid;
    gap: .42rem;
}

.insight-card-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: .5rem;
}

.insight-card-label {
    color: #8498ab;
    font-size: .67rem;
    font-weight: 700;
}

.insight-card-logos {
    display: flex;
    align-items: center;
}

.insight-card-logos img {
    width: 24px;
    height: 24px;
    object-fit: contain;
    filter: drop-shadow(0 4px 6px rgba(0,0,0,.38));
}

.insight-card-logos img + img { margin-left: -.3rem; }

.insight-card-value {
    color: #f5f9fd;
    font-size: 1rem;
    font-weight: 700;
    letter-spacing: -.025em;
    line-height: 1.25;
}

.insight-card-detail {
    color: #74899d;
    font-size: .7rem;
    line-height: 1.35;
}

/* Complete matchup cards */
[class*="st-key-matchup_row_"] [data-testid="stVerticalBlockBorderWrapper"] {
    padding: 1.08rem 1.12rem .88rem !important;
    border: 1px solid rgba(148,163,184,.075) !important;
    border-radius: 19px !important;
    background:
        radial-gradient(circle at 100% 0%, rgba(96,165,250,.065), transparent 31%),
        linear-gradient(148deg, rgba(12,27,43,.975), rgba(6,16,27,.975)) !important;
    box-shadow: 0 17px 38px rgba(0,0,0,.27), inset 0 1px 0 rgba(255,255,255,.028) !important;
}

[class*="st-key-matchup_row_"] [data-testid="stVerticalBlockBorderWrapper"]::before {
    width: 3px;
    box-shadow: none;
}

[class*="st-key-matchup_row_"]:hover [data-testid="stVerticalBlockBorderWrapper"] {
    transform: translateY(-2px);
    border-color: rgba(103,232,249,.20) !important;
    box-shadow: 0 21px 45px rgba(0,0,0,.32), inset 0 1px 0 rgba(255,255,255,.04) !important;
}

.premium-matchup {
    display: grid;
    grid-template-columns: minmax(0,1.65fr) minmax(235px,.82fr) minmax(180px,.60fr);
    align-items: stretch;
    gap: 1.05rem;
}

.premium-teams {
    display: grid;
    align-content: center;
    gap: .52rem;
    min-width: 0;
}

.premium-team-row {
    display: grid;
    grid-template-columns: 38px minmax(0,1fr) auto;
    align-items: center;
    gap: .72rem;
    min-width: 0;
}

.premium-team-logo {
    width: 37px;
    height: 37px;
    object-fit: contain;
    filter: drop-shadow(0 6px 8px rgba(0,0,0,.42));
}

.premium-team-copy { min-width: 0; }

.premium-team-name {
    overflow: hidden;
    color: #f6f9fc;
    font-size: 1.04rem;
    font-weight: 700;
    letter-spacing: -.025em;
    line-height: 1.22;
    text-overflow: ellipsis;
    white-space: nowrap;
}

.premium-team-meta {
    overflow: hidden;
    margin-top: .16rem;
    color: #71869a;
    font-size: .71rem;
    line-height: 1.25;
    text-overflow: ellipsis;
    white-space: nowrap;
}

.premium-team-probability {
    color: #e9f1f8;
    font-size: .98rem;
    font-weight: 700;
    font-variant-numeric: tabular-nums;
}

.premium-probability-track {
    position: relative;
    display: flex;
    height: 8px;
    margin-left: 49px;
    overflow: hidden;
    border-radius: 999px;
    background: #030a12;
    box-shadow: inset 0 1px 4px rgba(0,0,0,.58);
}

.premium-probability-track::after {
    content: "";
    position: absolute;
    left: 50%;
    top: -2px;
    bottom: -2px;
    width: 1px;
    background: rgba(255,255,255,.38);
}

.premium-probability-away {
    width: var(--away-probability);
    background: linear-gradient(90deg, var(--away-secondary), var(--away-primary));
}

.premium-probability-home {
    flex: 1;
    background: linear-gradient(90deg, var(--home-primary), var(--home-secondary));
}

.premium-pick-panel,
.premium-game-panel {
    display: grid;
    align-content: center;
    min-width: 0;
    padding: .82rem .88rem;
    border-radius: 14px;
}

.premium-pick-panel {
    border: 1px solid rgba(110,231,183,.09);
    background: linear-gradient(145deg, rgba(18,57,58,.30), rgba(7,19,30,.46));
}

.premium-eyebrow {
    color: #7f95a8;
    font-size: .67rem;
    font-weight: 700;
    line-height: 1.2;
}

.premium-pick-team {
    display: flex;
    align-items: center;
    gap: .58rem;
    margin-top: .46rem;
}

.premium-pick-team img {
    width: 31px;
    height: 31px;
    object-fit: contain;
}

.premium-pick-name {
    color: #a2f3e2;
    font-size: 1.02rem;
    font-weight: 700;
    letter-spacing: -.025em;
    line-height: 1.18;
}

.premium-pick-line {
    margin-top: .26rem;
    color: #8398ab;
    font-size: .7rem;
}

.premium-game-panel {
    border-left: 1px solid rgba(148,163,184,.10);
    border-radius: 0;
    padding-right: .1rem;
}

.premium-status-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: .5rem;
}

.premium-status {
    display: inline-flex;
    align-items: center;
    gap: .35rem;
    color: #aebdca;
    font-size: .67rem;
    font-weight: 700;
}

.premium-status::before {
    content: "";
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: #94a3b8;
}

.premium-status.live { color: #fecdd3; }
.premium-status.live::before {
    background: #fb7185;
    box-shadow: 0 0 10px rgba(251,113,133,.70);
    animation: quantLivePulse 1.35s ease-in-out infinite;
}
.premium-status.final { color: #bbf7d0; }
.premium-status.final::before { background: #6ee7b7; }

.premium-start-time {
    color: #71869a;
    font-size: .65rem;
    text-align: right;
}

.premium-score-label {
    margin-top: .72rem;
    color: #71869a;
    font-size: .66rem;
}

.premium-score-row {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: .5rem;
    margin-top: .29rem;
    color: #aebdca;
    font-size: .72rem;
}

.premium-score-row strong {
    color: #f7fbff;
    font-size: .94rem;
    font-weight: 700;
    font-variant-numeric: tabular-nums;
}

.premium-card-footer {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: .85rem;
    min-height: 38px;
    margin-top: .72rem;
    padding-top: .7rem;
    border-top: 1px solid rgba(148,163,184,.075);
}

.premium-context {
    overflow: hidden;
    color: #768b9f;
    font-size: .71rem;
    line-height: 1.4;
    text-overflow: ellipsis;
    white-space: nowrap;
}

.premium-quality {
    display: inline-flex;
    align-items: center;
    gap: .35rem;
    flex: 0 0 auto;
    color: #8296a9;
    font-size: .66rem;
}

.premium-quality strong {
    color: #c9d7e4;
    font-size: .71rem;
    font-weight: 700;
}

[class*="st-key-matchup_row_"] [data-testid="stBaseButton-secondary"],
[class*="st-key-matchup_row_"] [data-testid="stBaseButton-primary"] {
    min-height: 38px;
    margin-top: .74rem;
    border: 0 !important;
    border-radius: 10px !important;
    background: rgba(71,118,153,.14) !important;
    color: #d9e7f2 !important;
    font-size: .75rem !important;
    box-shadow: none !important;
}

[class*="st-key-matchup_row_"] [data-testid="stBaseButton-secondary"]:hover,
[class*="st-key-matchup_row_"] [data-testid="stBaseButton-primary"]:hover {
    background: rgba(49,169,196,.18) !important;
    color: #ecfeff !important;
}

/* Native controls and the attached report */
[data-baseweb="tab-list"] {
    gap: .25rem;
    padding: .24rem;
    border: 1px solid rgba(148,163,184,.08);
    border-radius: 11px;
    background: rgba(4,12,21,.56);
}

[data-baseweb="tab"] {
    min-height: 40px;
    padding-left: .82rem !important;
    padding-right: .82rem !important;
    border-radius: 8px;
    color: #8fa2b5 !important;
    font-size: .78rem;
    font-weight: 700 !important;
    letter-spacing: 0;
}

[aria-selected="true"][data-baseweb="tab"] {
    color: #eefaff !important;
    background: rgba(31,132,160,.19);
}

[data-testid="stExpander"] {
    margin-top: -.18rem;
    border: 1px solid rgba(148,163,184,.08) !important;
    border-radius: 0 0 18px 18px !important;
    background: linear-gradient(150deg, rgba(8,20,33,.97), rgba(5,14,24,.97)) !important;
    box-shadow: 0 18px 38px rgba(0,0,0,.24);
}

[data-testid="stMetric"] {
    padding: .76rem .8rem;
    border: 1px solid rgba(148,163,184,.075);
    border-radius: 12px;
    background: rgba(11,27,43,.56);
}

[data-testid="stMetricLabel"] {
    color: #8195a8 !important;
    font-size: .72rem !important;
}

[data-testid="stMetricValue"] {
    color: #f4f8fc !important;
    font-size: 1.18rem !important;
    font-weight: 700 !important;
    letter-spacing: -.025em;
}

[data-testid="stMetricDelta"] { font-size: .69rem !important; }

[data-testid="stRadio"] label {
    padding: .32rem .64rem !important;
    border: 1px solid rgba(148,163,184,.09);
    border-radius: 9px;
    background: rgba(8,21,35,.55);
}

[data-baseweb="input"],
[data-baseweb="select"] > div,
[data-testid="stDateInput"] input {
    border-color: rgba(148,163,184,.10) !important;
    border-radius: 10px !important;
    background: rgba(6,17,29,.88) !important;
}

[data-testid="stAlert"] {
    border: 1px solid rgba(148,163,184,.09) !important;
    border-radius: 11px !important;
    background: rgba(10,25,40,.74) !important;
}

@media (max-width: 1100px) {
    .premium-matchup {
        grid-template-columns: minmax(0,1.55fr) minmax(220px,.82fr);
    }
    .premium-game-panel {
        grid-column: 1 / -1;
        display: grid;
        grid-template-columns: 1fr 1fr;
        align-items: center;
        gap: 1rem;
        border-left: 0;
        border-top: 1px solid rgba(148,163,184,.08);
        padding: .72rem 0 0;
    }
    .premium-score-label { margin-top: 0; }
}

@media (max-width: 900px) {
    [data-testid="stMainBlockContainer"] { padding-top: .85rem; }
    .quant-brand-subtitle { display: none; }
    .premium-matchup { grid-template-columns: 1fr; }
    .premium-pick-panel { min-height: 0; }
    .premium-game-panel {
        grid-column: auto;
        grid-template-columns: 1fr;
        gap: .45rem;
    }
    .premium-score-label { margin-top: .35rem; }
}

@media (max-width: 620px) {
    .quant-brand-mark { width: 38px; height: 38px; border-radius: 11px; }
    .quant-brand-title { font-size: 1rem; }
    .quant-sync-copy small { display: none; }
    .premium-team-name { font-size: .96rem; }
    .premium-team-logo { width: 33px; height: 33px; }
    .premium-probability-track { margin-left: 45px; }
    .premium-card-footer { align-items: flex-start; flex-direction: column; gap: .38rem; }
    .premium-context { white-space: normal; }
}
</style>
"""
    )


def stadium_stylesheet() -> str:
    """Build 24: retain the established readable stadium presentation."""
    return """
<style>
:root {
    --bg-0: #070908;
    --bg-1: #0b0f0d;
    --surface-0: rgba(14, 19, 16, .94);
    --surface-1: rgba(20, 27, 23, .94);
    --surface-2: rgba(26, 34, 29, .92);
    --line: rgba(218, 231, 223, .105);
    --line-strong: rgba(218, 231, 223, .19);
    --text: #f4f7f5;
    --muted: #99a69f;
    --muted-2: #6f7c75;
    --good: #75e49b;
    --good-rgb: 117, 228, 155;
    --bad: #ff6878;
    --bad-rgb: 255, 104, 120;
    --warn: #f4c76a;
    --ice: #8bd9ef;
    --ice-rgb: 139, 217, 239;
}

html, body, .stApp,
[data-testid="stAppViewContainer"],
[data-testid="stMainBlockContainer"],
button, input, textarea, select {
    font-family: "Aptos", "Segoe UI Variable Text", "Segoe UI", sans-serif !important;
    font-optical-sizing: auto;
}

.stApp {
    isolation: isolate;
    color: var(--text);
    background-color: var(--bg-0);
    background-image:
        radial-gradient(ellipse at 12% -8%, rgba(45, 121, 78, .20), transparent 38%),
        radial-gradient(ellipse at 95% 8%, rgba(139, 217, 239, .075), transparent 30%),
        radial-gradient(ellipse at 52% 115%, rgba(104, 75, 38, .11), transparent 42%),
        linear-gradient(145deg, #060806 0%, #0c110e 47%, #080b09 100%);
    background-attachment: fixed;
    font-size: 16px;
}

.league-backdrop {
    position: fixed;
    inset: 0;
    z-index: 0;
    overflow: hidden;
    pointer-events: none;
    perspective: 900px;
}

.league-backdrop::before {
    content: "";
    position: absolute;
    inset: 0;
    background-image:
        linear-gradient(rgba(255,255,255,.014) 1px, transparent 1px),
        linear-gradient(90deg, rgba(255,255,255,.014) 1px, transparent 1px);
    background-size: 58px 58px;
    mask-image: linear-gradient(to bottom, rgba(0,0,0,.72), transparent 88%);
}

.league-backdrop::after {
    content: "";
    position: absolute;
    left: 50%;
    bottom: -43vh;
    width: 112vw;
    height: 78vh;
    transform: translateX(-50%) rotateX(66deg);
    border: 1px solid rgba(var(--good-rgb), .07);
    border-radius: 50%;
    background: repeating-radial-gradient(
        ellipse at center,
        rgba(var(--good-rgb), .022) 0 1px,
        transparent 1px 78px
    );
    box-shadow: inset 0 0 120px rgba(var(--good-rgb), .035);
}

.league-logo {
    position: absolute;
    left: var(--logo-left);
    bottom: -110px;
    width: var(--logo-size);
    height: var(--logo-size);
    object-fit: contain;
    opacity: var(--logo-opacity);
    filter: grayscale(.28) saturate(.72) drop-shadow(0 12px 18px rgba(0,0,0,.42));
    animation: leagueLogoRise var(--logo-duration) linear var(--logo-delay) infinite;
    transform: translate3d(0,0,0) rotate(var(--logo-tilt));
    will-change: transform;
}

@keyframes leagueLogoRise {
    0% { transform: translate3d(0, 0, 0) rotate(var(--logo-tilt)) scale(.86); }
    28% { transform: translate3d(var(--logo-drift), -32vh, 30px) rotate(var(--logo-tilt)) scale(.93); }
    57% { transform: translate3d(var(--logo-return), -66vh, 55px) rotate(var(--logo-tilt)) scale(1); }
    82% { transform: translate3d(var(--logo-soft), -96vh, 28px) rotate(var(--logo-tilt)) scale(1.04); }
    100% { transform: translate3d(var(--logo-exit), calc(-115vh - 150px), 0) rotate(var(--logo-tilt)) scale(1.08); }
}

[data-testid="stAppViewContainer"] {
    position: relative;
    z-index: 1;
    background: transparent;
}

[data-testid="stHeader"] {
    background: rgba(7, 9, 8, .78);
    border-bottom: 1px solid rgba(255,255,255,.045);
    backdrop-filter: blur(12px);
}

[data-testid="stMainBlockContainer"] {
    position: relative;
    z-index: 2;
    max-width: 1420px;
    padding-top: 1.05rem;
    padding-bottom: 4.5rem;
}

h1, h2, h3, h4,
[data-testid="stHeadingWithActionElements"] {
    color: var(--text) !important;
    font-family: "Segoe UI Variable Display", "Aptos Display", "Segoe UI", sans-serif !important;
    font-weight: 690 !important;
    letter-spacing: -.042em !important;
}

h2 { font-size: 1.55rem !important; }
h3 { font-size: 1.18rem !important; }
[data-testid="stCaptionContainer"] {
    color: var(--muted) !important;
    font-size: .83rem !important;
    line-height: 1.45 !important;
}

hr {
    margin: .84rem 0 1.05rem !important;
    border-color: rgba(255,255,255,.065) !important;
}

.quant-brand {
    display: flex;
    align-items: center;
    gap: .82rem;
    min-height: 50px;
}

.quant-brand-mark {
    position: relative;
    display: grid;
    place-items: center;
    width: 44px;
    height: 44px;
    overflow: hidden;
    border: 1px solid rgba(var(--good-rgb), .42);
    border-radius: 13px;
    background:
        linear-gradient(135deg, rgba(var(--good-rgb), .22), rgba(var(--ice-rgb), .08)),
        #111814;
    color: var(--good);
    font-family: "Segoe UI Variable Display", "Aptos Display", sans-serif;
    font-size: 1.03rem;
    font-weight: 760;
    box-shadow: 0 13px 28px rgba(0,0,0,.34), inset 0 1px 0 rgba(255,255,255,.08);
}

.quant-brand-mark::before,
.quant-brand-mark::after {
    content: "";
    position: absolute;
    width: 62px;
    height: 1px;
    background: rgba(var(--good-rgb), .25);
}
.quant-brand-mark::before { transform: rotate(38deg); }
.quant-brand-mark::after { transform: rotate(-38deg); }

.quant-brand-mark { text-shadow: 0 0 16px rgba(var(--good-rgb), .34); }
.quant-brand-mark > * { position: relative; z-index: 1; }

.quant-brand-heading {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: .55rem;
}

.quant-brand-title {
    color: var(--text);
    font-family: "Segoe UI Variable Display", "Aptos Display", sans-serif;
    font-size: 1.2rem;
    font-weight: 720;
    letter-spacing: -.043em;
    line-height: 1.1;
}

.quant-build {
    display: inline-flex;
    align-items: center;
    padding: .22rem .48rem;
    border: 1px solid rgba(var(--good-rgb), .25);
    border-radius: 6px;
    background: rgba(var(--good-rgb), .075);
    color: #a7f1bd;
    font-size: .56rem;
    font-weight: 760;
    letter-spacing: .09em;
    line-height: 1;
    text-transform: uppercase;
}

.quant-brand-subtitle {
    margin-top: .22rem;
    color: var(--muted-2);
    font-size: .73rem;
    line-height: 1.25;
}

.quant-sync {
    display: flex;
    align-items: center;
    justify-content: flex-end;
    gap: .55rem;
    min-height: 44px;
}
.quant-sync-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: var(--good);
    box-shadow: 0 0 0 4px rgba(var(--good-rgb),.08), 0 0 14px rgba(var(--good-rgb),.36);
}
.quant-sync-copy span {
    display: block;
    color: #b8edc7;
    font-size: .68rem;
    font-weight: 700;
}
.quant-sync-copy small {
    display: block;
    margin-top: .1rem;
    color: var(--muted-2);
    font-size: .65rem;
    font-variant-numeric: tabular-nums;
}

.section-heading {
    display: flex;
    align-items: flex-end;
    justify-content: space-between;
    gap: 1rem;
    margin: 1.2rem 0 .72rem;
}
.section-kicker {
    margin-bottom: .24rem;
    color: var(--good);
    font-size: .61rem;
    font-weight: 760;
    letter-spacing: .13em;
    text-transform: uppercase;
}
.section-title {
    color: var(--text);
    font-family: "Segoe UI Variable Display", "Aptos Display", sans-serif;
    font-size: 1.55rem;
    font-weight: 690;
    letter-spacing: -.045em;
    line-height: 1.08;
}
.section-meta {
    max-width: 56%;
    color: var(--muted-2);
    font-size: .76rem;
    line-height: 1.4;
    text-align: right;
}

/* Build 22 performance tracker */
[class*="st-key-tracker_summary"] [data-testid="stVerticalBlockBorderWrapper"] {
    margin-top: .82rem;
    padding: .82rem 1rem !important;
    border: 1px solid rgba(117,228,155,.17) !important;
    border-radius: 15px !important;
    background:
        linear-gradient(100deg, rgba(117,228,155,.055), transparent 37%),
        linear-gradient(145deg, rgba(18,24,20,.96), rgba(10,14,12,.97)) !important;
    box-shadow: 0 15px 34px rgba(0,0,0,.22), inset 0 1px 0 rgba(255,255,255,.03);
}
.tracker-strip {
    display: flex;
    align-items: center;
    gap: 1.35rem;
    min-height: 48px;
}
.tracker-strip-brand {
    flex: 0 0 auto;
    padding-right: 1.35rem;
    border-right: 1px solid rgba(255,255,255,.09);
}
.tracker-strip-brand span,
.tracker-strip-metrics span {
    display: block;
    color: var(--muted-2);
    font-size: .61rem;
    font-weight: 720;
    letter-spacing: .08em;
    line-height: 1.15;
    text-transform: uppercase;
}
.tracker-strip-brand strong {
    display: block;
    margin-top: .22rem;
    color: var(--text);
    font-family: "Segoe UI Variable Display", "Aptos Display", sans-serif;
    font-size: 1.55rem;
    font-weight: 720;
    letter-spacing: -.055em;
    line-height: 1;
    font-variant-numeric: tabular-nums;
}
.tracker-strip-metrics {
    display: grid;
    grid-template-columns: repeat(4, minmax(88px, 1fr));
    flex: 1 1 auto;
    gap: .55rem;
}
.tracker-strip-metrics > div {
    min-width: 0;
    padding: .15rem .55rem;
}
.tracker-strip-metrics strong {
    display: block;
    margin-top: .22rem;
    color: #e9efeb;
    font-size: .94rem;
    font-weight: 690;
    letter-spacing: -.025em;
    font-variant-numeric: tabular-nums;
}
.tracker-strip-metrics .pending strong { color: var(--warn); }
[class*="st-key-tracker_summary"] .stButton > button {
    min-height: 42px !important;
    border-color: rgba(117,228,155,.22) !important;
    background: rgba(117,228,155,.075) !important;
    color: #c8f4d4 !important;
}

[class*="st-key-tracker_panel"] {
    margin: .7rem 0 1.2rem;
    padding: 1.05rem 1.12rem 1.15rem;
    border: 1px solid rgba(117,228,155,.16);
    border-radius: 18px;
    background:
        radial-gradient(circle at 96% 3%, rgba(139,217,239,.055), transparent 25%),
        linear-gradient(150deg, rgba(15,21,17,.97), rgba(8,12,10,.98));
    box-shadow: 0 24px 56px rgba(0,0,0,.32), inset 0 1px 0 rgba(255,255,255,.035);
}
.tracker-panel-head {
    display: flex;
    align-items: flex-end;
    justify-content: space-between;
    gap: 1rem;
    padding: .18rem .1rem .85rem;
}
.tracker-panel-kicker {
    color: var(--good);
    font-size: .61rem;
    font-weight: 740;
    letter-spacing: .13em;
    text-transform: uppercase;
}
.tracker-panel-title {
    margin-top: .22rem;
    color: var(--text);
    font-family: "Segoe UI Variable Display", "Aptos Display", sans-serif;
    font-size: 1.42rem;
    font-weight: 710;
    letter-spacing: -.045em;
}
.tracker-panel-subtitle {
    margin-top: .22rem;
    color: var(--muted);
    font-size: .77rem;
}
.tracker-panel-count {
    padding: .36rem .58rem;
    border: 1px solid rgba(139,217,239,.16);
    border-radius: 8px;
    color: #bed8df;
    background: rgba(139,217,239,.045);
    font-size: .67rem;
    font-weight: 680;
}
.tracker-overview {
    display: grid;
    grid-template-columns: minmax(300px, .9fr) minmax(0, 1.55fr);
    gap: .75rem;
    padding-top: .5rem;
}
.tracker-record-hero {
    display: flex;
    align-items: center;
    justify-content: space-between;
    min-height: 158px;
    padding: 1.05rem 1.08rem;
    border: 1px solid rgba(139,217,239,.16);
    border-radius: 14px;
    background: linear-gradient(145deg, rgba(24,32,27,.93), rgba(12,17,14,.96));
}
.tracker-record-hero.good { border-color: rgba(117,228,155,.30); box-shadow: inset 3px 0 0 rgba(117,228,155,.78); }
.tracker-record-hero.bad { border-color: rgba(255,104,120,.28); box-shadow: inset 3px 0 0 rgba(255,104,120,.74); }
.tracker-record-eyebrow {
    color: var(--muted-2);
    font-size: .61rem;
    font-weight: 720;
    letter-spacing: .11em;
    text-transform: uppercase;
}
.tracker-record-big {
    margin-top: .3rem;
    color: var(--text);
    font-family: "Segoe UI Variable Display", "Aptos Display", sans-serif;
    font-size: 2.35rem;
    font-weight: 720;
    letter-spacing: -.07em;
    line-height: 1;
    font-variant-numeric: tabular-nums;
}
.tracker-record-copy {
    max-width: 190px;
    margin-top: .45rem;
    color: var(--muted-2);
    font-size: .66rem;
    line-height: 1.4;
}
.tracker-win-gauge {
    --gauge-angle: 0deg;
    --gauge-color: var(--ice);
    display: grid;
    place-items: center;
    width: 94px;
    height: 94px;
    flex: 0 0 94px;
    border-radius: 50%;
    background: conic-gradient(var(--gauge-color) var(--gauge-angle), rgba(255,255,255,.075) 0);
    box-shadow: 0 0 28px color-mix(in srgb, var(--gauge-color) 18%, transparent);
}
.tracker-win-gauge::before {
    content: "";
    grid-area: 1/1;
    width: 76px;
    height: 76px;
    border-radius: 50%;
    background: #0d130f;
    box-shadow: inset 0 1px 0 rgba(255,255,255,.045);
}
.tracker-win-gauge .gauge-copy { grid-area: 1/1; z-index: 1; text-align: center; }
.tracker-win-gauge strong { display: block; color: var(--text); font-size: 1.05rem; font-weight: 720; letter-spacing: -.035em; }
.tracker-win-gauge span { display: block; margin-top: .1rem; color: var(--muted-2); font-size: .52rem; font-weight: 700; text-transform: uppercase; }
.tracker-overview-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0,1fr));
    gap: .75rem;
}
.tracker-overview-card {
    min-height: 74px;
    padding: .85rem .9rem;
    border: 1px solid rgba(255,255,255,.075);
    border-radius: 13px;
    background: rgba(255,255,255,.018);
}
.tracker-overview-card.pending { border-color: rgba(244,199,106,.16); }
.tracker-overview-card > span { display: block; color: var(--muted-2); font-size: .61rem; font-weight: 690; text-transform: uppercase; letter-spacing: .08em; }
.tracker-overview-card > strong { display: block; margin-top: .24rem; color: var(--text); font-size: 1.12rem; font-weight: 700; letter-spacing: -.03em; }
.tracker-overview-card.pending > strong { color: var(--warn); }
.tracker-overview-card > small { display: block; margin-top: .1rem; color: var(--muted-2); font-size: .62rem; }
.tracker-split-heading {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 1rem;
    margin: .72rem 0 .52rem;
}
.tracker-split-heading.quality { margin-top: 1rem; }
.tracker-split-heading strong { color: #e9efeb; font-size: .85rem; font-weight: 690; }
.tracker-split-heading span { color: var(--muted-2); font-size: .68rem; }
.tracker-bucket-grid { display: grid; grid-template-columns: repeat(3, minmax(0,1fr)); gap: .72rem; }
.tracker-bucket {
    min-height: 116px;
    padding: .86rem .9rem;
    border: 1px solid rgba(255,255,255,.075);
    border-radius: 13px;
    background: linear-gradient(145deg, rgba(25,32,28,.86), rgba(12,17,14,.91));
}
.tracker-bucket.good { border-color: rgba(117,228,155,.26); box-shadow: inset 3px 0 0 rgba(117,228,155,.75); }
.tracker-bucket.bad { border-color: rgba(255,104,120,.25); box-shadow: inset 3px 0 0 rgba(255,104,120,.72); }
.tracker-bucket-label { color: var(--muted); font-size: .69rem; font-weight: 680; }
.tracker-bucket-record { margin-top: .3rem; color: var(--text); font-size: 1.35rem; font-weight: 710; letter-spacing: -.045em; font-variant-numeric: tabular-nums; }
.tracker-bucket-rate { margin-top: .08rem; color: #cdd8d1; font-size: .68rem; font-weight: 650; }
.tracker-bucket.good .tracker-bucket-rate { color: var(--good); }
.tracker-bucket.bad .tracker-bucket-rate { color: var(--bad); }
.tracker-bucket-note { margin-top: .38rem; color: var(--muted-2); font-size: .6rem; line-height: 1.35; }
.tracker-log { display: grid; gap: .55rem; padding-top: .58rem; }
.tracker-log-row {
    display: grid;
    grid-template-columns: minmax(210px,1.25fr) minmax(190px,1fr) minmax(170px,.9fr) 100px;
    align-items: center;
    gap: .75rem;
    padding: .76rem .82rem;
    border: 1px solid rgba(255,255,255,.07);
    border-radius: 12px;
    background: rgba(255,255,255,.018);
}
.tracker-log-row.win { border-left: 3px solid var(--good); }
.tracker-log-row.loss { border-left: 3px solid var(--bad); }
.tracker-log-row.pending { border-left: 3px solid var(--warn); }
.tracker-log-row.void { border-left: 3px solid var(--muted-2); }
.tracker-log-matchup, .tracker-log-pick { display: flex; align-items: center; gap: .65rem; min-width: 0; }
.tracker-log-logos { display: flex; align-items: center; flex: 0 0 auto; }
.tracker-log-logos img, .tracker-log-pick img { width: 28px; height: 28px; object-fit: contain; }
.tracker-log-logos img + img { margin-left: -7px; }
.tracker-log-teams { overflow: hidden; color: #e9efeb; font-size: .77rem; font-weight: 680; text-overflow: ellipsis; white-space: nowrap; }
.tracker-log-date, .tracker-log-pick span, .tracker-log-score span { display: block; margin-bottom: .12rem; color: var(--muted-2); font-size: .56rem; font-weight: 680; letter-spacing: .06em; text-transform: uppercase; }
.tracker-log-pick strong, .tracker-log-score strong { display: block; overflow: hidden; color: #dbe5df; font-size: .69rem; font-weight: 650; text-overflow: ellipsis; white-space: nowrap; }
.tracker-result {
    justify-self: end;
    padding: .32rem .48rem;
    border: 1px solid rgba(255,255,255,.1);
    border-radius: 7px;
    color: var(--muted);
    background: rgba(255,255,255,.025);
    font-size: .59rem;
    font-weight: 760;
    letter-spacing: .06em;
}
.tracker-result.win { border-color: rgba(117,228,155,.27); color: var(--good); background: rgba(117,228,155,.065); }
.tracker-result.loss { border-color: rgba(255,104,120,.25); color: var(--bad); background: rgba(255,104,120,.06); }
.tracker-result.pending { border-color: rgba(244,199,106,.22); color: var(--warn); background: rgba(244,199,106,.055); }
.tracker-tools-heading { margin: 1.05rem 0 .55rem; padding-top: .8rem; border-top: 1px solid rgba(255,255,255,.07); }
.tracker-tools-heading strong { display: block; color: #e9efeb; font-size: .79rem; }
.tracker-tools-heading span { display: block; margin-top: .12rem; color: var(--muted-2); font-size: .64rem; }

[data-baseweb="tab-list"] {
    gap: .25rem;
    padding: .25rem;
    border: 1px solid var(--line);
    border-radius: 12px;
    background: rgba(9,13,11,.78);
    box-shadow: inset 0 1px 0 rgba(255,255,255,.025);
}
[data-baseweb="tab"] {
    min-height: 39px;
    padding: 0 .9rem !important;
    border-radius: 9px;
    color: var(--muted) !important;
    font-size: .79rem;
    font-weight: 650 !important;
    letter-spacing: -.01em;
}
[aria-selected="true"][data-baseweb="tab"] {
    background: rgba(var(--good-rgb), .10);
    color: #c9f5d5 !important;
}

[data-testid="stVerticalBlockBorderWrapper"] {
    border-color: var(--line) !important;
    border-radius: 16px !important;
    background: linear-gradient(145deg, var(--surface-1), var(--surface-0)) !important;
    box-shadow: 0 16px 38px rgba(0,0,0,.24), inset 0 1px 0 rgba(255,255,255,.025);
}

/* Scoreboard */
[class*="st-key-score_card_"] [data-testid="stVerticalBlockBorderWrapper"] {
    position: relative;
    overflow: hidden;
    min-height: 232px;
    padding: .92rem .94rem .78rem !important;
    border: 1px solid rgba(255,255,255,.085) !important;
    border-radius: 16px !important;
    background:
        radial-gradient(circle at 100% 0%, rgba(var(--ice-rgb),.055), transparent 36%),
        linear-gradient(148deg, rgba(22,29,25,.97), rgba(11,16,13,.97)) !important;
    transition: transform .18s ease, border-color .18s ease, box-shadow .18s ease;
}
[class*="st-key-score_card_"] [data-testid="stVerticalBlockBorderWrapper"]::before {
    content: "";
    position: absolute;
    inset: 0 0 auto 0;
    height: 2px;
    background: linear-gradient(90deg, var(--away-primary), var(--home-primary));
    opacity: .9;
}
[class*="st-key-score_card_"]:hover [data-testid="stVerticalBlockBorderWrapper"] {
    transform: translateY(-3px);
    border-color: rgba(var(--good-rgb), .22) !important;
    box-shadow: 0 22px 46px rgba(0,0,0,.34), inset 0 1px 0 rgba(255,255,255,.04) !important;
}
.score-tile { display: grid; gap: .48rem; }
.score-tile-head,
.score-tile-team,
.score-tile-model { display: flex; align-items: center; }
.score-tile-head { justify-content: space-between; gap: .5rem; margin-bottom: .05rem; }
.score-tile-status {
    display: inline-flex;
    align-items: center;
    gap: .38rem;
    color: var(--muted);
    font-size: .63rem;
    font-weight: 750;
    letter-spacing: .075em;
    text-transform: uppercase;
}
.score-tile-status::before {
    content: "";
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: #8b9690;
}
.score-tile-status.live { color: #ffb0b9; }
.score-tile-status.live::before { background: var(--bad); box-shadow: 0 0 11px rgba(var(--bad-rgb),.62); animation: signalPulse 1.35s ease-in-out infinite; }
.score-tile-status.final { color: #a9ecc0; }
.score-tile-status.final::before { background: var(--good); }
.score-tile-time { color: var(--muted-2); font-size: .65rem; text-align: right; }
.score-tile-team {
    display: grid;
    grid-template-columns: 34px minmax(0,1fr) auto;
    gap: .62rem;
    min-height: 40px;
}
.score-tile-team + .score-tile-team { padding-top: .43rem; border-top: 1px solid rgba(255,255,255,.055); }
.score-tile-team img { width: 33px; height: 33px; object-fit: contain; filter: drop-shadow(0 6px 8px rgba(0,0,0,.45)); }
.score-tile-team-name {
    overflow: hidden;
    color: var(--text);
    font-family: "Segoe UI Variable Display", "Aptos Display", sans-serif;
    font-size: .91rem;
    font-weight: 680;
    letter-spacing: -.028em;
    text-overflow: ellipsis;
    white-space: nowrap;
}
.score-tile-team-record { margin-top: .07rem; color: var(--muted-2); font-size: .63rem; }
.score-tile-value { color: var(--text); font-size: 1.11rem; font-weight: 720; font-variant-numeric: tabular-nums; }
.score-tile-model {
    justify-content: space-between;
    gap: .62rem;
    margin-top: .08rem;
    padding-top: .58rem;
    border-top: 1px solid rgba(255,255,255,.065);
}
.score-model-copy { min-width: 0; }
.score-model-copy span { display: block; color: var(--muted-2); font-size: .6rem; font-weight: 650; letter-spacing: .04em; text-transform: uppercase; }
.score-model-copy strong { display: block; overflow: hidden; margin-top: .12rem; color: #b8efc8; font-size: .75rem; font-weight: 700; text-overflow: ellipsis; white-space: nowrap; }

.mini-gauge,
.prediction-gauge,
.quality-gauge {
    position: relative;
    display: grid;
    place-items: center;
    flex: 0 0 auto;
    border-radius: 50%;
    background: conic-gradient(var(--gauge-color) var(--gauge-angle), rgba(255,255,255,.07) 0);
    box-shadow: 0 0 22px color-mix(in srgb, var(--gauge-color) 15%, transparent);
}
.mini-gauge { width: 45px; height: 45px; }
.prediction-gauge { width: 104px; height: 104px; }
.quality-gauge { width: 64px; height: 64px; }
.mini-gauge::before,
.prediction-gauge::before,
.quality-gauge::before {
    content: "";
    position: absolute;
    inset: 5px;
    border-radius: 50%;
    background: #111713;
    box-shadow: inset 0 0 15px rgba(0,0,0,.34);
}
.prediction-gauge::before { inset: 7px; }
.gauge-copy { position: relative; z-index: 1; display: grid; place-items: center; line-height: 1; }
.gauge-copy strong { color: var(--text); font-size: .85rem; font-weight: 760; font-variant-numeric: tabular-nums; }
.prediction-gauge .gauge-copy strong { font-size: 1.45rem; letter-spacing: -.045em; }
.quality-gauge .gauge-copy strong { font-size: 1.02rem; }
.gauge-copy span { margin-top: .13rem; color: var(--muted-2); font-size: .48rem; font-weight: 720; letter-spacing: .08em; text-transform: uppercase; }

[class*="st-key-score_card_"] [data-testid="stBaseButton-secondary"],
[class*="st-key-score_card_"] [data-testid="stBaseButton-primary"] {
    min-height: 35px;
    margin-top: .5rem;
    border: 1px solid rgba(255,255,255,.075) !important;
    border-radius: 9px !important;
    background: rgba(255,255,255,.035) !important;
    color: #d9e2dd !important;
    font-size: .71rem !important;
    box-shadow: none !important;
}
[class*="st-key-score_card_"] [data-testid="stBaseButton-secondary"]:hover,
[class*="st-key-score_card_"] [data-testid="stBaseButton-primary"]:hover {
    border-color: rgba(var(--good-rgb),.28) !important;
    background: rgba(var(--good-rgb),.08) !important;
    color: #c7f4d3 !important;
}

/* Slate signals */
[class*="st-key-insight_"] [data-testid="stVerticalBlockBorderWrapper"] {
    min-height: 150px;
    padding: .9rem .92rem !important;
    border: 1px solid rgba(255,255,255,.075) !important;
    border-radius: 15px !important;
    background: linear-gradient(148deg, rgba(21,28,24,.96), rgba(11,16,13,.96)) !important;
}
.slate-signal { display: grid; grid-template-columns: minmax(0,1fr) auto; align-items: center; gap: .7rem; min-height: 124px; }
.slate-signal-copy { min-width: 0; }
.slate-signal-label { color: var(--muted); font-size: .66rem; font-weight: 680; }
.slate-signal-value { margin-top: .42rem; color: var(--text); font-family: "Segoe UI Variable Display", "Aptos Display", sans-serif; font-size: 1rem; font-weight: 710; letter-spacing: -.035em; line-height: 1.2; }
.slate-signal-detail { margin-top: .28rem; color: var(--muted-2); font-size: .67rem; line-height: 1.35; }
.slate-signal-logos { display: flex; align-items: center; margin-top: .54rem; }
.slate-signal-logos img { width: 24px; height: 24px; object-fit: contain; filter: drop-shadow(0 5px 7px rgba(0,0,0,.4)); }
.slate-signal-logos img + img { margin-left: -.26rem; }

/* Matchup board */
[class*="st-key-matchup_row_"] [data-testid="stVerticalBlockBorderWrapper"] {
    position: relative;
    overflow: hidden;
    padding: 0 !important;
    border: 1px solid rgba(255,255,255,.08) !important;
    border-radius: 20px !important;
    background:
        radial-gradient(circle at 50% 115%, rgba(var(--good-rgb),.045), transparent 38%),
        linear-gradient(148deg, rgba(22,29,25,.975), rgba(10,15,12,.975)) !important;
    box-shadow: 0 19px 46px rgba(0,0,0,.28), inset 0 1px 0 rgba(255,255,255,.03) !important;
    transition: transform .18s ease, border-color .18s ease, box-shadow .18s ease;
}
[class*="st-key-matchup_row_"] [data-testid="stVerticalBlockBorderWrapper"]::before {
    content: "";
    position: absolute;
    inset: 0 0 auto 0;
    height: 2px;
    background: linear-gradient(90deg, var(--away-primary), rgba(255,255,255,.16) 50%, var(--home-primary));
}
[class*="st-key-matchup_row_"]:hover [data-testid="stVerticalBlockBorderWrapper"] {
    transform: translateY(-2px);
    border-color: rgba(var(--good-rgb),.18) !important;
    box-shadow: 0 25px 55px rgba(0,0,0,.34), inset 0 1px 0 rgba(255,255,255,.04) !important;
}
.match-card { display: grid; }
.match-card-top {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
    padding: .76rem 1.05rem;
    border-bottom: 1px solid rgba(255,255,255,.06);
    background: rgba(255,255,255,.018);
}
.match-status-wrap { display: flex; align-items: center; gap: .65rem; min-width: 0; }
.match-status {
    display: inline-flex;
    align-items: center;
    gap: .36rem;
    flex: 0 0 auto;
    color: var(--muted);
    font-size: .61rem;
    font-weight: 760;
    letter-spacing: .09em;
    text-transform: uppercase;
}
.match-status::before { content: ""; width: 7px; height: 7px; border-radius: 50%; background: #87938c; }
.match-status.live { color: #ffb4bd; }
.match-status.live::before { background: var(--bad); box-shadow: 0 0 12px rgba(var(--bad-rgb),.55); animation: signalPulse 1.35s ease-in-out infinite; }
.match-status.final { color: #a9ebbf; }
.match-status.final::before { background: var(--good); }
.match-clock { color: #cbd4cf; font-size: .72rem; font-weight: 620; white-space: nowrap; }
.match-context { overflow: hidden; color: var(--muted-2); font-size: .68rem; text-align: right; text-overflow: ellipsis; white-space: nowrap; }
.match-comparison {
    display: grid;
    grid-template-columns: minmax(0,1fr) 168px minmax(0,1fr);
    align-items: center;
    gap: 1rem;
    padding: 1.14rem 1.18rem 1rem;
}
.team-block { display: grid; grid-template-columns: 54px minmax(0,1fr); align-items: center; gap: .82rem; min-width: 0; }
.team-block.home { grid-template-columns: minmax(0,1fr) 54px; text-align: right; }
.team-block.home .team-logo-large { grid-column: 2; }
.team-block.home .team-copy { grid-column: 1; grid-row: 1; }
.team-logo-large { width: 54px; height: 54px; object-fit: contain; filter: drop-shadow(0 9px 11px rgba(0,0,0,.48)); }
.team-name-large { overflow: hidden; color: var(--text); font-family: "Segoe UI Variable Display", "Aptos Display", sans-serif; font-size: 1.1rem; font-weight: 700; letter-spacing: -.038em; line-height: 1.14; text-overflow: ellipsis; white-space: nowrap; }
.team-meta { overflow: hidden; margin-top: .2rem; color: var(--muted-2); font-size: .69rem; line-height: 1.3; text-overflow: ellipsis; white-space: nowrap; }
.team-probability { margin-top: .4rem; color: #dbe4df; font-size: .8rem; font-weight: 720; font-variant-numeric: tabular-nums; }
.team-block.is-pick .team-name-large,
.team-block.is-pick .team-probability { color: #b8efc8; }
.forecast-core { display: grid; place-items: center; text-align: center; }
.forecast-label { margin-top: .48rem; color: var(--good); font-size: .57rem; font-weight: 780; letter-spacing: .12em; text-transform: uppercase; }
.forecast-team { margin-top: .12rem; color: var(--text); font-size: .85rem; font-weight: 700; line-height: 1.18; }
.forecast-line { margin-top: .12rem; color: var(--muted-2); font-size: .63rem; }
.match-signals {
    display: grid;
    grid-template-columns: minmax(0,1fr) minmax(0,1fr) auto;
    gap: .65rem;
    padding: .78rem 1.05rem .92rem;
    border-top: 1px solid rgba(255,255,255,.055);
    background: rgba(0,0,0,.09);
}
.signal-strip {
    min-width: 0;
    padding: .62rem .72rem;
    border: 1px solid var(--line);
    border-radius: 11px;
    background: rgba(255,255,255,.02);
}
.signal-strip.good { border-color: rgba(var(--good-rgb),.20); background: rgba(var(--good-rgb),.045); }
.signal-strip.bad { border-color: rgba(var(--bad-rgb),.19); background: rgba(var(--bad-rgb),.038); }
.signal-strip-label { display: flex; align-items: center; gap: .35rem; color: var(--muted); font-size: .55rem; font-weight: 780; letter-spacing: .1em; text-transform: uppercase; }
.signal-strip.good .signal-strip-label { color: #9ee9b5; }
.signal-strip.bad .signal-strip-label { color: #ff9ca7; }
.signal-strip-label::before { content: ""; width: 6px; height: 6px; border-radius: 50%; background: currentColor; }
.signal-strip-copy { overflow: hidden; margin-top: .28rem; color: #cbd4cf; font-size: .68rem; line-height: 1.35; text-overflow: ellipsis; white-space: nowrap; }
.quality-lockup { display: flex; align-items: center; gap: .55rem; min-width: 132px; }
.quality-lockup-copy span { display: block; color: var(--muted-2); font-size: .56rem; font-weight: 750; letter-spacing: .08em; text-transform: uppercase; }
.quality-lockup-copy strong { display: block; margin-top: .15rem; color: #dce5e0; font-size: .71rem; font-weight: 690; white-space: nowrap; }

[class*="st-key-matchup_row_"] > div > [data-testid="stVerticalBlockBorderWrapper"] > div > div {
    gap: 0 !important;
}
[class*="st-key-matchup_row_"] [data-testid="stHorizontalBlock"] {
    gap: .65rem !important;
    padding: 0 1.02rem .88rem;
}
.match-action-note { color: var(--muted-2); font-size: .67rem; line-height: 1.35; }
[class*="st-key-matchup_row_"] [data-testid="stBaseButton-secondary"],
[class*="st-key-matchup_row_"] [data-testid="stBaseButton-primary"] {
    min-height: 38px;
    border: 1px solid rgba(var(--good-rgb),.18) !important;
    border-radius: 10px !important;
    background: rgba(var(--good-rgb),.07) !important;
    color: #bdeecb !important;
    font-size: .73rem !important;
    font-weight: 680 !important;
    box-shadow: none !important;
}
[class*="st-key-matchup_row_"] [data-testid="stBaseButton-secondary"]:hover,
[class*="st-key-matchup_row_"] [data-testid="stBaseButton-primary"]:hover {
    border-color: rgba(var(--good-rgb),.38) !important;
    background: rgba(var(--good-rgb),.12) !important;
}

/* Attached analysis */
[data-testid="stExpander"] {
    margin-top: .65rem;
    border: 1px solid rgba(255,255,255,.085) !important;
    border-radius: 14px !important;
    background: linear-gradient(148deg, rgba(16,22,18,.98), rgba(8,12,10,.98)) !important;
    box-shadow: 0 14px 34px rgba(0,0,0,.22);
}
[class*="st-key-analysis_panel_"] {
    position: relative;
    z-index: 1;
    margin: -.35rem 0 1rem;
    padding: .9rem 1.05rem 1.15rem;
    overflow: hidden;
    border: 1px solid rgba(255,255,255,.085);
    border-top-color: rgba(var(--good-rgb),.16);
    border-radius: 0 0 20px 20px;
    background:
        radial-gradient(circle at 92% -6%, rgba(var(--good-rgb),.055), transparent 29%),
        linear-gradient(150deg, rgba(16,22,18,.985), rgba(8,12,10,.985));
    box-shadow: 0 23px 52px rgba(0,0,0,.31), inset 0 1px 0 rgba(255,255,255,.022);
}
[class*="st-key-analysis_panel_"]::before {
    content: "";
    position: absolute;
    inset: 0 0 auto;
    height: 1px;
    background: linear-gradient(90deg, transparent, rgba(var(--good-rgb),.45), transparent);
}
.analysis-panel-heading {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: .75rem;
    margin: 0 .05rem .72rem;
}
.analysis-panel-label {
    display: inline-flex;
    align-items: center;
    gap: .42rem;
    color: #a8b5ae;
    font-size: .6rem;
    font-weight: 760;
    letter-spacing: .11em;
    text-transform: uppercase;
}
.analysis-panel-label::before {
    content: "";
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: var(--good);
    box-shadow: 0 0 10px rgba(var(--good-rgb),.34);
}
.analysis-panel-matchup { color: var(--muted-2); font-size: .68rem; }
.analysis-lock-note {
    display: inline-flex;
    align-items: center;
    gap: .34rem;
    color: #95cda6;
    font-size: .62rem;
    font-weight: 650;
}
.analysis-hero {
    display: grid;
    grid-template-columns: 128px minmax(0,1fr) 96px;
    align-items: center;
    gap: 1.05rem;
    padding: .9rem .95rem;
    border: 0;
    border-radius: 14px;
    background:
        linear-gradient(100deg, rgba(var(--good-rgb),.055), rgba(255,255,255,.018) 48%, rgba(var(--ice-rgb),.025));
    box-shadow: inset 0 1px 0 rgba(255,255,255,.03);
}
.analysis-matchup-logos { display: grid; grid-template-columns: 48px 20px 48px; align-items: center; justify-content: center; }
.analysis-matchup-logos img { width: 48px; height: 48px; object-fit: contain; filter: drop-shadow(0 9px 11px rgba(0,0,0,.46)); }
.analysis-vs { color: var(--muted-2); font-size: .56rem; font-weight: 760; text-align: center; }
.analysis-eyebrow { color: var(--good); font-size: .57rem; font-weight: 780; letter-spacing: .12em; text-transform: uppercase; }
.analysis-title { margin-top: .2rem; color: var(--text); font-family: "Segoe UI Variable Display", "Aptos Display", sans-serif; font-size: 1.18rem; font-weight: 710; letter-spacing: -.04em; }
.analysis-summary { max-width: 920px; margin-top: .34rem; color: #bac6bf; font-size: .75rem; line-height: 1.52; }
.analysis-hero-gauge { justify-self: end; }
.analysis-hero .prediction-gauge { width: 82px; height: 82px; }
.analysis-hero .prediction-gauge::before { inset: 6px; }
.analysis-hero .prediction-gauge .gauge-copy strong { font-size: 1.08rem; }
.analysis-stat-rail {
    display: grid;
    grid-template-columns: repeat(4,1fr);
    margin: .62rem 0 .88rem;
    overflow: hidden;
    border-top: 1px solid rgba(255,255,255,.07);
    border-bottom: 1px solid rgba(255,255,255,.07);
    background: rgba(0,0,0,.10);
}
.analysis-stat { min-width: 0; padding: .64rem .78rem; }
.analysis-stat + .analysis-stat { border-left: 1px solid rgba(255,255,255,.065); }
.analysis-stat.good { background: rgba(var(--good-rgb),.025); }
.analysis-stat.bad { background: rgba(var(--bad-rgb),.022); }
.snapshot-label { color: var(--muted-2); font-size: .56rem; font-weight: 760; letter-spacing: .085em; text-transform: uppercase; }
.snapshot-value { overflow: hidden; margin-top: .22rem; color: var(--text); font-size: .86rem; font-weight: 700; line-height: 1.22; text-overflow: ellipsis; white-space: nowrap; }
.snapshot-detail { margin-top: .14rem; color: var(--muted-2); font-size: .61rem; line-height: 1.25; }

[class*="st-key-analysis_panel_"] [data-baseweb="tab-list"] {
    gap: 1.15rem;
    padding: 0;
    border: 0;
    border-bottom: 1px solid rgba(255,255,255,.075);
    border-radius: 0;
    background: transparent;
    box-shadow: none;
}
[class*="st-key-analysis_panel_"] [data-baseweb="tab"] {
    min-height: 42px;
    padding: 0 .05rem !important;
    border-radius: 0;
    background: transparent !important;
    color: var(--muted) !important;
    font-size: .76rem;
}
[class*="st-key-analysis_panel_"] [aria-selected="true"][data-baseweb="tab"] {
    color: #b8efc8 !important;
    box-shadow: inset 0 -2px 0 var(--good);
}

.analysis-grid-two { display: grid; grid-template-columns: repeat(2,minmax(0,1fr)); gap: .66rem; margin-top: .68rem; }
.analysis-copy-card {
    padding: .86rem .9rem;
    border: 0;
    border-left: 2px solid rgba(255,255,255,.105);
    border-radius: 0 11px 11px 0;
    background: rgba(255,255,255,.022);
    box-shadow: inset 0 1px 0 rgba(255,255,255,.018);
}
.analysis-copy-card.good { border-left-color: rgba(var(--good-rgb),.70); background: rgba(var(--good-rgb),.03); }
.analysis-copy-card.bad { border-left-color: rgba(var(--bad-rgb),.72); background: rgba(var(--bad-rgb),.028); }
.analysis-copy-card.warn { border-left-color: rgba(244,199,106,.68); background: rgba(244,199,106,.027); }
.analysis-card-label { display: flex; align-items: center; gap: .4rem; color: var(--muted); font-size: .59rem; font-weight: 780; letter-spacing: .1em; text-transform: uppercase; }
.analysis-copy-card.good .analysis-card-label { color: #9ee9b5; }
.analysis-copy-card.bad .analysis-card-label { color: #ff9ca7; }
.analysis-copy-card.warn .analysis-card-label { color: #f0cf8c; }
.analysis-card-label::before { content: ""; width: 7px; height: 7px; border-radius: 50%; background: currentColor; }
.analysis-card-title { margin-top: .44rem; color: var(--text); font-size: .92rem; font-weight: 690; letter-spacing: -.02em; }
.analysis-card-copy { margin-top: .32rem; color: #b5c1ba; font-size: .75rem; line-height: 1.55; }
.analysis-signal-list { display: grid; gap: .42rem; margin-top: .65rem; }
.analysis-signal-row {
    display: grid;
    grid-template-columns: 84px minmax(0,1fr);
    align-items: start;
    gap: .68rem;
    padding: .58rem .68rem;
    border-radius: 9px;
    background: rgba(255,255,255,.018);
}
.analysis-signal-row.good { background: rgba(var(--good-rgb),.035); }
.analysis-signal-row.bad { background: rgba(var(--bad-rgb),.035); }
.analysis-signal-row.warn { background: rgba(244,199,106,.03); }
.analysis-signal-tag { display: flex; align-items: center; gap: .35rem; color: var(--muted); font-size: .55rem; font-weight: 780; letter-spacing: .09em; text-transform: uppercase; }
.analysis-signal-tag::before { content: ""; width: 6px; height: 6px; border-radius: 50%; background: currentColor; }
.analysis-signal-row.good .analysis-signal-tag { color: #9ee9b5; }
.analysis-signal-row.bad .analysis-signal-tag { color: #ff9ca7; }
.analysis-signal-row.warn .analysis-signal-tag { color: #f0cf8c; }
.analysis-signal-copy { color: #bac5bf; font-size: .72rem; line-height: 1.45; }
.analysis-subsection-title { margin-top: .7rem; color: var(--muted); font-size: .58rem; font-weight: 780; letter-spacing: .1em; text-transform: uppercase; }
.analysis-subsection-title.good { color: #9ee9b5; }
.analysis-subsection-title.bad { color: #ff9ca7; }
.analysis-subsection-title.warn { color: #f0cf8c; }
.lineup-list { display: grid; gap: .24rem; margin: .55rem 0 0; padding: 0; list-style: none; color: #b5c1ba; font-size: .72rem; line-height: 1.4; }
.pitch-compare { display: grid; grid-template-columns: repeat(2,minmax(0,1fr)); gap: .68rem; margin: .72rem 0; }
.pitch-team-card { padding: .86rem; border: 0; border-top: 2px solid rgba(255,255,255,.10); border-radius: 11px; background: rgba(255,255,255,.02); }
.pitch-team-card.better { border-top-color: rgba(var(--good-rgb),.72); background: rgba(var(--good-rgb),.03); }
.pitch-team-card.worse { border-top-color: rgba(var(--bad-rgb),.64); background: rgba(var(--bad-rgb),.025); }
.pitch-team-head { display: flex; align-items: center; gap: .58rem; }
.pitch-team-head img { width: 34px; height: 34px; object-fit: contain; }
.pitch-team-name { color: var(--text); font-size: .88rem; font-weight: 700; }
.pitch-team-tag { margin-top: .1rem; color: var(--muted-2); font-size: .61rem; }
.pitch-metrics { display: grid; grid-template-columns: repeat(2,1fr); gap: .42rem; margin-top: .7rem; }
.pitch-metric { padding: .52rem .56rem; border-radius: 9px; background: rgba(0,0,0,.16); }
.pitch-metric span { display: block; color: var(--muted-2); font-size: .56rem; }
.pitch-metric strong { display: block; margin-top: .14rem; color: #e5ece8; font-size: .83rem; font-weight: 710; font-variant-numeric: tabular-nums; }
.model-note {
    margin: .95rem 0 1.18rem;
    padding: .72rem .86rem;
    border: 1px solid rgba(244,199,106,.14);
    border-left: 3px solid rgba(244,199,106,.62);
    border-radius: 10px;
    background: rgba(244,199,106,.035);
    color: #b9c3bd;
    font-size: .73rem;
    line-height: 1.5;
}

[data-testid="stMetric"] {
    padding: .74rem .78rem;
    border: 1px solid var(--line);
    border-radius: 11px;
    background: rgba(255,255,255,.022);
}
[data-testid="stMetricLabel"] { color: var(--muted) !important; font-size: .7rem !important; }
[data-testid="stMetricValue"] { color: var(--text) !important; font-size: 1.12rem !important; font-weight: 710 !important; letter-spacing: -.035em; }
[data-testid="stMetricDelta"] { font-size: .67rem !important; }

[data-testid="stBaseButton-primary"],
[data-testid="stBaseButton-secondary"],
[data-testid="stPopoverButton"] button {
    border-radius: 10px !important;
    font-weight: 650 !important;
    letter-spacing: -.01em;
}
[data-testid="stBaseButton-primary"] {
    border-color: rgba(var(--good-rgb),.34) !important;
    background: linear-gradient(135deg, #2d8e55, #207344) !important;
    color: #f4fff7 !important;
}
[data-testid="stBaseButton-secondary"],
[data-testid="stPopoverButton"] button {
    border-color: rgba(255,255,255,.105) !important;
    background: rgba(20,27,23,.88) !important;
    color: #dce5e0 !important;
}
[data-testid="stBaseButton-secondary"]:hover,
[data-testid="stPopoverButton"] button:hover {
    border-color: rgba(var(--good-rgb),.30) !important;
    background: rgba(var(--good-rgb),.075) !important;
}

[data-testid="stRadio"] label {
    padding: .34rem .65rem !important;
    border: 1px solid var(--line);
    border-radius: 9px;
    background: rgba(13,18,15,.74);
}
[data-baseweb="input"],
[data-baseweb="select"] > div,
[data-testid="stDateInput"] input {
    border-color: var(--line) !important;
    border-radius: 10px !important;
    background: rgba(12,17,14,.94) !important;
}
[data-testid="stAlert"] {
    border: 1px solid var(--line) !important;
    border-radius: 11px !important;
    background: rgba(15,21,17,.92) !important;
}

@keyframes signalPulse {
    0%,100% { opacity: .72; transform: scale(.9); }
    50% { opacity: 1; transform: scale(1.16); }
}

@media (max-width: 1100px) {
    .match-comparison { grid-template-columns: minmax(0,1fr) 142px minmax(0,1fr); }
    .prediction-gauge { width: 92px; height: 92px; }
    .match-signals { grid-template-columns: 1fr 1fr; }
    .quality-lockup { grid-column: 1 / -1; justify-self: end; }
}

@media (max-width: 850px) {
    [data-testid="stMainBlockContainer"] { padding-top: .75rem; }
    .quant-brand-subtitle, .quant-sync-copy small { display: none; }
    .section-heading { align-items: flex-start; flex-direction: column; gap: .35rem; }
    .section-meta { max-width: none; text-align: left; }
    .match-comparison { grid-template-columns: 1fr; gap: .85rem; }
    .team-block.home { grid-template-columns: 54px minmax(0,1fr); text-align: left; }
    .team-block.home .team-logo-large { grid-column: 1; }
    .team-block.home .team-copy { grid-column: 2; }
    .forecast-core { grid-row: 1; }
    .match-signals { grid-template-columns: 1fr; }
    .quality-lockup { grid-column: auto; justify-self: start; }
    .analysis-hero { grid-template-columns: 112px minmax(0,1fr); }
    .analysis-matchup-logos { grid-template-columns: 42px 18px 42px; justify-content: start; }
    .analysis-matchup-logos img { width: 42px; height: 42px; }
    .analysis-hero-gauge { grid-column: 1 / -1; justify-self: center; }
    .analysis-stat-rail { grid-template-columns: repeat(2,1fr); }
    .analysis-stat:nth-child(3) { border-left: 0; border-top: 1px solid rgba(255,255,255,.065); }
    .analysis-stat:nth-child(4) { border-top: 1px solid rgba(255,255,255,.065); }
}

@media (max-width: 600px) {
    .quant-brand-mark { width: 39px; height: 39px; border-radius: 11px; }
    .quant-brand-title { font-size: 1.02rem; }
    .quant-build { font-size: .5rem; }
    .section-title { font-size: 1.34rem; }
    .match-card-top { align-items: flex-start; flex-direction: column; gap: .35rem; }
    .match-context { text-align: left; white-space: normal; }
    .team-name-large { font-size: 1rem; }
    [class*="st-key-analysis_panel_"] { padding: .76rem .72rem .95rem; }
    .analysis-panel-heading { align-items: flex-start; flex-direction: column; gap: .22rem; }
    .analysis-hero { grid-template-columns: 1fr; gap: .72rem; padding: .78rem; }
    .analysis-matchup-logos { justify-content: start; }
    .analysis-hero-gauge { grid-column: auto; justify-self: start; }
    .analysis-stat-rail, .analysis-grid-two, .pitch-compare { grid-template-columns: 1fr; }
    .analysis-stat + .analysis-stat { border-left: 0; border-top: 1px solid rgba(255,255,255,.065); }
    .analysis-signal-row { grid-template-columns: 1fr; gap: .28rem; }
    [class*="st-key-analysis_panel_"] [data-baseweb="tab-list"] { gap: .72rem; }
}
</style>
"""


def floating_logo_markup() -> str:
    """Render all MLB club marks as a restrained, moving 3D backdrop."""
    rng = random.Random(2020)
    marks: list[str] = []
    for team_id in TEAM_COLORS:
        size = rng.uniform(34, 72)
        left = rng.uniform(-2, 101)
        duration = rng.uniform(42, 74)
        delay = rng.uniform(0, duration)
        opacity = rng.uniform(0.025, 0.070)
        drift = rng.uniform(22, 82) * (-1 if rng.random() < 0.5 else 1)
        tilt = rng.uniform(-13, 13)
        marks.append(
            "<img class='league-logo' alt='' aria-hidden='true' loading='lazy' "
            f"src='https://www.mlbstatic.com/team-logos/{team_id}.svg' style='"
            f"--logo-left:{left:.2f}vw;--logo-size:{size:.1f}px;"
            f"--logo-duration:{duration:.1f}s;--logo-delay:-{delay:.1f}s;"
            f"--logo-opacity:{opacity:.3f};--logo-drift:{drift:.1f}px;"
            f"--logo-return:{-drift * .52:.1f}px;--logo-soft:{drift * .32:.1f}px;"
            f"--logo-exit:{-drift * .18:.1f}px;--logo-tilt:{tilt:.1f}deg;'>"
        )
    return "<div class='league-backdrop' aria-hidden='true'>" + "".join(marks) + "</div>"


def bubble_markup(count: int = 24) -> str:
    """Return deterministic decorative bubbles so reruns do not jump around."""
    rng = random.Random(937)
    bubbles: list[str] = []
    for _ in range(count):
        size = rng.uniform(14, 76)
        left = rng.uniform(-3, 103)
        duration = rng.uniform(27, 50)
        delay = rng.uniform(0, duration)
        opacity = rng.uniform(0.08, 0.22)
        drift = rng.uniform(16, 54) * (-1 if rng.random() < 0.5 else 1)
        bubbles.append(
            "<span class='quant-bubble' style='"
            f"--bubble-left:{left:.2f}vw;--bubble-size:{size:.1f}px;"
            f"--bubble-duration:{duration:.1f}s;--bubble-delay:-{delay:.1f}s;"
            f"--bubble-opacity:{opacity:.2f};--bubble-drift:{drift:.1f}px;"
            f"--bubble-return:{-drift * .55:.1f}px;"
            f"--bubble-soft-drift:{drift * .35:.1f}px;"
            f"--bubble-exit-drift:{-drift * .2:.1f}px' aria-hidden='true'></span>"
        )
    return "<div class='quant-bubbles'>" + "".join(bubbles) + "</div>"


def full_stylesheet() -> str:
    return """
<style>
:root {
    --navy-0: #030817;
    --navy-1: #07172d;
    --navy-2: #0b2848;
    --cyan: #22d3ee;
    --cyan-soft: #67e8f9;
    --mint: #5eead4;
    --text: #f8fafc;
    --muted: #9fb3c8;
    --danger: #fb7185;
    --amber: #fbbf24;
}

html, body, [class*="css"], .stApp {
    font-family: 'Inter', system-ui, sans-serif !important;
}

.stApp {
    position: relative;
    color: var(--text);
    background:
        radial-gradient(circle at 15% 0%, rgba(14, 165, 233, .22), transparent 34%),
        radial-gradient(circle at 90% 15%, rgba(34, 211, 238, .12), transparent 32%),
        linear-gradient(145deg, var(--navy-0) 0%, var(--navy-2) 48%, #061224 100%);
}

[data-testid="stHeader"] { background: rgba(3, 8, 23, .45); }
[data-testid="stSidebar"] { background: rgba(3, 8, 23, .96); }
[data-testid="stMainBlockContainer"] { max-width: 1440px; padding-top: 1.4rem; padding-bottom: 4rem; }
h1, h2, h3, h4 { font-family: 'Sora', system-ui, sans-serif !important; letter-spacing: -.025em; }

.quant-bubbles {
    display: none;
}
.quant-bubble {
    position: absolute; bottom: -130px; display: block; border-radius: 999px;
    border: 1px solid rgba(255,255,255,.30);
    background: radial-gradient(circle at 28% 25%, rgba(255,255,255,.34) 0 3%, rgba(125,211,252,.08) 24%, transparent 62%);
    box-shadow: inset 0 0 18px rgba(255,255,255,.12), 0 0 16px rgba(34,211,238,.10);
    animation-name: quantFloat, quantWobble;
    animation-timing-function: linear, ease-in-out;
    animation-iteration-count: infinite;
}
@keyframes quantFloat { from { transform: translateY(0); } to { transform: translateY(-1050px); } }
@keyframes quantWobble { 0%,100% { margin-left: 0; } 50% { margin-left: 34px; } }

.top-nav-brand { display: flex; align-items: center; gap: .7rem; min-height: 44px; }
.top-nav-mark {
    display: grid; place-items: center; width: 39px; height: 39px; border-radius: 12px;
    background: linear-gradient(145deg, #67e8f9, #0e7490); color: #03111f;
    box-shadow: 0 0 22px rgba(34,211,238,.22); font-size: 1.15rem;
}
.top-nav-title { font: 700 1rem 'Sora', sans-serif; letter-spacing: -.035em; color: #f8fafc; }
.top-nav-sub { color: #8198ae; font-size: .69rem; margin-top: .08rem; }
.top-nav-sync { display: flex; align-items: center; gap: .55rem; justify-content: flex-end; }
.top-nav-sync strong { display: block; color: #a7f3d0; font: 700 .65rem 'IBM Plex Mono', monospace; letter-spacing: .04em; }
.top-nav-sync small { display: block; color: #7890a6; font: 500 .59rem 'IBM Plex Mono', monospace; margin-top: .12rem; }
.sync-dot { width: 8px; height: 8px; border-radius: 50%; background: #34d399; box-shadow: 0 0 0 5px rgba(52,211,153,.10), 0 0 12px rgba(52,211,153,.58); }
[data-testid="stDateInput"] input { color: #ecfeff !important; font-weight: 700; }

.hero-card {
    position: relative; overflow: hidden; margin: .35rem 0 1.3rem;
    padding: 1.45rem 1.6rem; border-radius: 20px;
    border: 1px solid rgba(103,232,249,.55);
    background: linear-gradient(110deg, rgba(8,47,73,.82), rgba(14,116,144,.28), rgba(15,23,42,.78));
    box-shadow: 0 20px 55px rgba(0,0,0,.36), inset 0 1px 0 rgba(255,255,255,.15);
}
.hero-card:after {
    content: ''; position: absolute; inset: 0;
    background: linear-gradient(90deg, transparent, rgba(103,232,249,.08), transparent);
    pointer-events: none;
}
.hero-eyebrow { color: #67e8f9; font: 700 .68rem 'IBM Plex Mono', monospace; letter-spacing: .11em; margin-bottom: .35rem; }
.hero-title { font: 800 clamp(1.35rem, 3vw, 2.25rem) 'Sora', sans-serif; letter-spacing: -.035em; }
.hero-sub { margin-top: .35rem; color: #bae6fd; font-size: .96rem; }
.hero-meta { margin-top: .7rem; color: var(--muted); font: 600 .76rem 'IBM Plex Mono', monospace; text-transform: uppercase; letter-spacing: .06em; }

.section-title { margin: 1.2rem 0 .75rem; font: 700 1.4rem 'Sora', sans-serif; letter-spacing: -.025em; }
.section-sub { color: var(--muted); margin-bottom: 1rem; }

.game-center-sticky {
    border: 1px solid rgba(103,232,249,.22); border-radius: 17px;
    padding: .78rem .85rem .15rem; margin: 1rem 0 1.1rem;
    background: rgba(2,12,26,.91); box-shadow: 0 16px 42px rgba(0,0,0,.30);
}
.game-center-head {
    display: flex; align-items: flex-end; justify-content: space-between; gap: 1rem;
    margin: 0 0 .38rem;
}
.game-center-title {
    font: 700 1.42rem 'Sora', sans-serif; letter-spacing: -.035em; color: #f8fafc;
}
.game-center-sub { margin-top: .3rem; color: #9fb3c8; font-size: .86rem; }
.live-indicator {
    display: inline-flex; align-items: center; gap: .42rem; color: #fecdd3;
    font: 700 .7rem 'IBM Plex Mono', monospace; letter-spacing: .04em;
}
.live-indicator:before {
    content: ''; width: 8px; height: 8px; border-radius: 50%; background: #fb7185;
    box-shadow: 0 0 0 5px rgba(251,113,133,.12), 0 0 14px rgba(251,113,133,.7);
}
.game-center-counts { display: flex; flex-wrap: wrap; gap: .36rem; margin: .4rem 0 .6rem; }
.game-count {
    padding: .24rem .46rem; border-radius: 999px; color: #8097ad;
    background: rgba(30,41,59,.52); border: 1px solid rgba(148,163,184,.15);
    font: 700 .58rem 'IBM Plex Mono', monospace; letter-spacing: .045em;
}
.game-count.active { color: #cffafe; border-color: rgba(34,211,238,.30); background: rgba(8,145,178,.18); }
.game-count.live { color: #fecdd3; border-color: rgba(251,113,133,.30); background: rgba(190,18,60,.18); }
.scoreboard-rail {
    display: flex; gap: .8rem; overflow-x: auto; scroll-snap-type: x proximity;
    padding: .25rem .1rem .8rem; scrollbar-width: thin; scrollbar-color: #155e75 rgba(3,15,31,.55);
}
.scoreboard-rail::-webkit-scrollbar { height: 7px; }
.scoreboard-rail::-webkit-scrollbar-track { background: rgba(3,15,31,.55); border-radius: 99px; }
.scoreboard-rail::-webkit-scrollbar-thumb { background: #155e75; border-radius: 99px; }
.score-card {
    position: relative; overflow: hidden;
    flex: 0 0 258px; scroll-snap-align: start; display: block; min-height: 188px;
    padding: .88rem; border-radius: 15px; text-decoration: none !important; color: #f8fafc !important;
    border: 1px solid rgba(103,232,249,.24);
    background: linear-gradient(150deg, rgba(4,18,36,.96), rgba(8,46,73,.88));
    box-shadow: 0 10px 26px rgba(0,0,0,.26), inset 0 1px 0 rgba(255,255,255,.06);
    transition: transform .16s ease, border-color .16s ease, box-shadow .16s ease;
}
.score-card:before {
    content: ''; position: absolute; inset: 0 0 auto; height: 3px;
    background: linear-gradient(90deg, var(--away-secondary), var(--away-primary) 42%, var(--home-primary) 58%, var(--home-secondary));
}
.score-card:hover {
    transform: translateY(-2px); border-color: rgba(103,232,249,.62);
    box-shadow: 0 14px 32px rgba(0,0,0,.34), 0 0 20px rgba(34,211,238,.10);
}
.score-card.is-live { border-color: rgba(251,113,133,.50); }
.score-card.is-final { opacity: .86; border-color: rgba(148,163,184,.25); }
.score-card-top { display: flex; align-items: center; justify-content: space-between; gap: .5rem; margin-bottom: .65rem; }
.score-card-status {
    padding: .27rem .48rem; border-radius: 999px; font: 700 .61rem 'IBM Plex Mono', monospace;
    letter-spacing: .045em; text-transform: uppercase;
}
.score-card-status.live { color: #ffe4e6; background: rgba(190,18,60,.42); border: 1px solid rgba(251,113,133,.55); }
.score-card-status.preview { color: #cffafe; background: rgba(8,145,178,.22); border: 1px solid rgba(34,211,238,.32); }
.score-card-status.final { color: #d5deea; background: rgba(51,65,85,.62); border: 1px solid rgba(148,163,184,.28); }
.score-card-time { color: #91a8bd; font: 600 .65rem 'IBM Plex Mono', monospace; text-align: right; }
.score-team-row {
    display: grid; grid-template-columns: 28px minmax(0,1fr) auto; align-items: center;
    gap: .55rem; min-height: 39px; border-bottom: 1px solid rgba(148,163,184,.10);
}
.score-team-row:last-of-type { border-bottom: 0; }
.score-team-logo { width: 25px; height: 25px; object-fit: contain; }
.score-team-copy { min-width: 0; }
.score-team-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font: 700 .83rem 'Sora', sans-serif; letter-spacing: -.02em; }
.score-team-record { color: #7f96ac; font-size: .64rem; margin-top: .08rem; }
.score-team-value { color: #fff; font: 700 1.05rem 'IBM Plex Mono', monospace; }
.score-card-footer {
    display: flex; align-items: center; justify-content: space-between; gap: .5rem;
    margin-top: .68rem; padding-top: .58rem; border-top: 1px solid rgba(103,232,249,.13);
}
.score-card-actions { display: flex; flex-direction: column; align-items: flex-end; gap: .28rem; }
.score-model-label { color: #7f96ac; font-size: .61rem; text-transform: uppercase; letter-spacing: .06em; }
.score-model-pick { color: #99f6e4; font-weight: 700; font-size: .75rem; margin-top: .08rem; }
.score-open { color: #67e8f9; font: 700 .66rem 'IBM Plex Mono', monospace; white-space: nowrap; }
.quality-badge {
    display: inline-flex; width: fit-content; padding: .24rem .4rem; border-radius: 999px;
    font: 700 .56rem 'IBM Plex Mono', monospace; letter-spacing: .035em; white-space: nowrap;
}
.quality-high { color: #a7f3d0; border: 1px solid rgba(52,211,153,.36); background: rgba(6,95,70,.30); }
.quality-moderate { color: #fde68a; border: 1px solid rgba(251,191,36,.34); background: rgba(146,64,14,.26); }
.quality-limited { color: #cbd5e1; border: 1px solid rgba(148,163,184,.28); background: rgba(51,65,85,.42); }
.empty-scoreboard {
    padding: 1.35rem; border: 1px dashed rgba(103,232,249,.25); border-radius: 14px;
    color: #9fb3c8; background: rgba(3,15,31,.55); text-align: center;
}

.insights-head .section-title { margin-bottom: .22rem; }
.insights-head .section-sub { margin-bottom: .7rem; }
.insights-grid { display: grid; grid-template-columns: repeat(4, minmax(0,1fr)); gap: .72rem; margin-bottom: 1.15rem; }
.insight-card {
    position: relative; overflow: hidden; min-width: 0; display: flex; flex-direction: column;
    padding: .92rem; min-height: 142px; border-radius: 14px; text-decoration: none !important;
    color: #f8fafc !important; border: 1px solid rgba(103,232,249,.20);
    background: linear-gradient(150deg, rgba(3,15,31,.92), rgba(8,42,66,.72));
    box-shadow: 0 10px 26px rgba(0,0,0,.22); transition: transform .16s ease, border-color .16s ease;
}
.insight-card:before {
    content: ''; position: absolute; left: 0; top: 0; bottom: 0; width: 3px;
    background: linear-gradient(180deg, var(--away-secondary), var(--home-secondary));
}
.insight-card:hover { transform: translateY(-2px); border-color: rgba(103,232,249,.46); }
.insight-top { display: flex; align-items: center; gap: .4rem; color: #8fa7bd; font: 700 .63rem 'IBM Plex Mono', monospace; text-transform: uppercase; letter-spacing: .045em; }
.insight-value { margin-top: .55rem; color: #fff; font: 700 clamp(.92rem, 1.5vw, 1.08rem) 'Sora', sans-serif; letter-spacing: -.03em; line-height: 1.32; }
.insight-detail { margin-top: .32rem; color: #9fb3c8; font-size: .72rem; line-height: 1.42; }
.insight-link { margin-top: auto; padding-top: .55rem; color: #67e8f9; font: 700 .58rem 'IBM Plex Mono', monospace; letter-spacing: .035em; }

.compact-game {
    position: relative; overflow: hidden; display: grid;
    grid-template-columns: minmax(0,1.75fr) minmax(180px,.62fr) minmax(190px,.72fr);
    gap: 1rem; align-items: center; margin: .85rem 0 .38rem; padding: 1rem 1.05rem;
    border-radius: 16px; border: 1px solid rgba(103,232,249,.22);
    background: linear-gradient(145deg, rgba(3,15,31,.94), rgba(7,39,62,.78));
    box-shadow: 0 12px 30px rgba(0,0,0,.25); scroll-margin-top: 18rem;
}
.compact-game:before {
    content: ''; position: absolute; inset: 0 0 auto; height: 3px;
    background: linear-gradient(90deg, var(--away-secondary), var(--away-primary) 42%, var(--home-primary) 58%, var(--home-secondary));
}
.compact-main { min-width: 0; }
.compact-status-row { display: flex; align-items: center; gap: .5rem; margin-bottom: .48rem; }
.compact-time { color: #8ea5ba; font: 600 .64rem 'IBM Plex Mono', monospace; }
.compact-teams { display: flex; flex-wrap: wrap; align-items: center; gap: .52rem; }
.compact-team { display: inline-flex; align-items: center; gap: .38rem; color: #f8fafc; font: 700 .97rem 'Sora', sans-serif; letter-spacing: -.025em; }
.compact-team img { width: 25px; height: 25px; object-fit: contain; }
.compact-at { color: #688197; font: 700 .59rem 'IBM Plex Mono', monospace; letter-spacing: .08em; }
.compact-starters { margin-top: .38rem; color: #8fa7bd; font-size: .69rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.compact-prob-labels { display: flex; justify-content: space-between; margin-top: .58rem; color: #b8c8d8; font: 600 .62rem 'IBM Plex Mono', monospace; }
.compact-prob-track { display: flex; height: 7px; margin-top: .24rem; overflow: hidden; border-radius: 999px; background: #07111f; }
.compact-away { height: 100%; background: linear-gradient(90deg, var(--away-primary), var(--away-secondary)); }
.compact-home { height: 100%; background: linear-gradient(90deg, var(--home-secondary), var(--home-primary)); }
.compact-pick, .compact-score { min-width: 0; padding-left: 1rem; border-left: 1px solid rgba(148,163,184,.14); }
.compact-kicker { color: #71899f; font: 700 .58rem 'IBM Plex Mono', monospace; letter-spacing: .07em; text-transform: uppercase; }
.compact-pick-name { margin-top: .28rem; color: #99f6e4; font: 700 .93rem 'Sora', sans-serif; letter-spacing: -.025em; }
.compact-pick-prob { margin-top: .2rem; color: #b8c8d8; font: 600 .66rem 'IBM Plex Mono', monospace; }
.compact-score-value { margin: .3rem 0 .5rem; color: #f8fafc; font: 700 .8rem 'Sora', sans-serif; line-height: 1.35; }

.game-shell {
    position: relative; overflow: hidden;
    margin: 1rem 0 1.35rem; padding: 1.25rem; border-radius: 18px;
    border: 1px solid rgba(34,211,238,.48);
    background: linear-gradient(135deg, rgba(6,24,46,.88), rgba(9,52,83,.65));
    box-shadow: 0 17px 45px rgba(0,0,0,.30), inset 0 1px 0 rgba(255,255,255,.09);
    scroll-margin-top: 4.5rem;
}
.game-shell:before {
    content: ''; position: absolute; inset: 0 0 auto; height: 3px;
    background: linear-gradient(90deg, var(--away-secondary), var(--away-primary) 42%, var(--home-primary) 58%, var(--home-secondary));
}
.game-top { display: flex; justify-content: space-between; align-items: flex-start; gap: 1rem; }
.matchup { display: flex; flex-wrap: wrap; align-items: center; gap: .55rem; font: 700 1.18rem 'Sora', sans-serif; letter-spacing: -.025em; }
.team-chip { display: inline-flex; align-items: center; gap: .45rem; }
.team-logo { width: 28px; height: 28px; object-fit: contain; }
.at-mark { color: #5eead4; font-family: 'IBM Plex Mono', monospace; font-size: .92rem; }
.game-context { color: var(--muted); margin-top: .36rem; font-size: .86rem; }
.status-pill { white-space: nowrap; padding: .42rem .72rem; border-radius: 999px; font: 700 .7rem 'IBM Plex Mono', monospace; letter-spacing: .04em; }
.status-live { color: #fecdd3; border: 1px solid rgba(251,113,133,.8); background: rgba(190,18,60,.3); box-shadow: 0 0 17px rgba(251,113,133,.34); }
.status-preview { color: #a5f3fc; border: 1px solid rgba(34,211,238,.52); background: rgba(8,145,178,.18); }
.status-final { color: #cbd5e1; border: 1px solid rgba(148,163,184,.45); background: rgba(51,65,85,.55); }

.pick-row { display: flex; flex-wrap: wrap; gap: .6rem; align-items: center; margin: .9rem 0 .8rem; }
.pick-pill { padding: .48rem .75rem; border-radius: 999px; color: #042f2e; background: linear-gradient(90deg, #5eead4, #22d3ee); font-weight: 800; box-shadow: 0 0 22px rgba(34,211,238,.34); }
.pick-prob { color: #99f6e4; font: 700 .82rem 'IBM Plex Mono', monospace; }
.quality-pill { color: #cbd5e1; font: 600 .72rem 'IBM Plex Mono', monospace; }

.prob-grid { display: grid; grid-template-columns: 1fr 1fr; gap: .85rem; margin: .65rem 0 1rem; }
.prob-label { display: flex; justify-content: space-between; margin-bottom: .28rem; font-size: .78rem; color: #cbd5e1; }
.prob-label strong { color: white; font-family: 'IBM Plex Mono', monospace; }
.prob-track { height: 9px; border-radius: 99px; overflow: hidden; background: rgba(15,23,42,.9); border: 1px solid rgba(103,232,249,.25); }
.prob-fill { display: block; height: 100%; border-radius: inherit; box-shadow: 0 0 14px rgba(103,232,249,.35); }
.away-fill { background: linear-gradient(90deg, var(--away-primary), var(--away-secondary)); }
.home-fill { background: linear-gradient(90deg, var(--home-primary), var(--home-secondary)); }

.analysis-grid { display: grid; grid-template-columns: minmax(0,.9fr) minmax(0,.9fr) minmax(320px,1.3fr); gap: .85rem; }
.pitcher-card, .rationale-card {
    min-width: 0; border-radius: 14px; padding: 1rem;
    border: 1px solid rgba(34,211,238,.32); background: rgba(2,12,26,.78);
}
.pitcher-name { display: flex; justify-content: space-between; gap: .5rem; font-weight: 800; font-size: 1rem; }
.record { color: #5eead4; font: 600 .75rem 'IBM Plex Mono', monospace; }
.metric-row { display: flex; flex-wrap: wrap; gap: .38rem; margin: .62rem 0; }
.metric { padding: .28rem .42rem; border-radius: 7px; border: 1px solid rgba(103,232,249,.40); color: #dbeafe; font: 600 .67rem 'IBM Plex Mono', monospace; }
.metric.missing { color: #94a3b8; border-color: rgba(148,163,184,.28); }
.mini-title { margin: .65rem 0 .35rem; color: #a5f3fc; font: 700 .68rem 'IBM Plex Mono', monospace; letter-spacing: .06em; }
.start-row { display: grid; grid-template-columns: 1.15fr .65fr .55fr .55fr; gap: .3rem; padding: .24rem 0; border-bottom: 1px solid rgba(148,163,184,.12); color: #cbd5e1; font: 600 .66rem 'IBM Plex Mono', monospace; }
.start-row span:nth-child(n+2) { text-align: right; color: #99f6e4; }
.rationale-title { color: white; font: 700 .98rem 'Sora', sans-serif; letter-spacing: -.02em; margin-bottom: .65rem; }
.rationale-line { color: #d5e2ef; font-size: .84rem; line-height: 1.55; margin: .46rem 0; }
.rationale-line strong { color: #67e8f9; }
.source-line { margin-top: .8rem; color: #8fa6bb; font: 600 .64rem 'IBM Plex Mono', monospace; line-height: 1.45; }

.stButton > button {
    border-radius: 999px !important; border: 1px solid rgba(34,211,238,.65) !important;
    color: white !important; font-weight: 700 !important;
    background: linear-gradient(135deg, rgba(8,145,178,.35), rgba(15,23,42,.92)) !important;
}
.stButton > button:hover { border-color: #67e8f9 !important; box-shadow: 0 0 22px rgba(34,211,238,.35) !important; }
[data-testid="stRadio"] [role="radiogroup"] { gap: .35rem; flex-wrap: wrap; }
[data-testid="stRadio"] label {
    padding: .3rem .6rem !important; border-radius: 999px;
    border: 1px solid rgba(103,232,249,.16); background: rgba(3,15,31,.62);
}
[data-testid="stExpander"] {
    border: 1px solid rgba(34,211,238,.28) !important;
    border-radius: 14px !important;
    background: rgba(2,12,26,.76) !important;
    box-shadow: 0 12px 32px rgba(0,0,0,.22);
    margin-bottom: .55rem;
}
[data-testid="stExpander"] details > summary {
    font-weight: 700 !important;
    color: #dff8ff !important;
    padding-top: .85rem !important;
    padding-bottom: .85rem !important;
}
[data-testid="stVerticalBlockBorderWrapper"] {
    background: rgba(5,20,38,.80);
    border-color: rgba(103,232,249,.20) !important;
    border-radius: 13px !important;
}
[data-testid="stMetric"] {
    background: rgba(5,20,38,.68);
    border: 1px solid rgba(103,232,249,.16);
    border-radius: 12px;
    padding: .72rem .82rem;
}
[data-testid="stMetricLabel"] { color: #9fb3c8 !important; }
[data-testid="stMetricValue"] { color: #f8fafc !important; }
[data-baseweb="tab-list"] {
    gap: .45rem;
    background: rgba(3,15,31,.68);
    border: 1px solid rgba(103,232,249,.16);
    border-radius: 12px;
    padding: .35rem;
    margin: .75rem 0 1rem;
}
[data-baseweb="tab"] {
    border-radius: 9px !important;
    color: #a9bfd3 !important;
    font-weight: 700 !important;
    padding-left: .85rem !important;
    padding-right: .85rem !important;
}
[aria-selected="true"][data-baseweb="tab"] {
    color: #ecfeff !important;
    background: rgba(8,145,178,.28) !important;
}
[data-baseweb="tab-highlight"] { background-color: #67e8f9 !important; }
[data-baseweb="tab-panel"] p,
[data-testid="stExpanderDetails"] p {
    color: #d4e1ed;
    font-size: .94rem;
    line-height: 1.65;
    max-width: 78ch;
}
[data-testid="stExpanderDetails"] h3,
[data-testid="stExpanderDetails"] h4 {
    margin-top: .45rem;
    margin-bottom: .45rem;
}

.disclaimer { color: #cbd5e1; padding: .8rem 1rem; border-left: 3px solid #fbbf24; background: rgba(120,53,15,.15); border-radius: 8px; font-size: .83rem; }
.data-note { color: #94a3b8; font-size: .78rem; }

@media (max-width: 1100px) {
    .insights-grid { grid-template-columns: repeat(2, minmax(0,1fr)); }
    .compact-game { grid-template-columns: minmax(0,1.45fr) minmax(160px,.6fr); }
    .compact-score { grid-column: 1 / -1; padding: .72rem 0 0; border-left: 0; border-top: 1px solid rgba(148,163,184,.14); }
    .tracker-log-row { grid-template-columns: minmax(190px,1.15fr) minmax(170px,1fr) minmax(150px,.85fr) 92px; }
}

@media (max-width: 900px) {
    .analysis-grid { grid-template-columns: 1fr; }
    .prob-grid { grid-template-columns: 1fr; }
    .game-top { align-items: stretch; flex-direction: column; }
    .status-pill { align-self: flex-start; }
    .game-center-head { align-items: flex-start; flex-direction: column; gap: .4rem; }
    .score-card { flex-basis: 226px; }
    .compact-game { grid-template-columns: 1fr; scroll-margin-top: 1rem; }
    .compact-pick, .compact-score { padding: .72rem 0 0; border-left: 0; border-top: 1px solid rgba(148,163,184,.14); }
    .tracker-strip { align-items: flex-start; flex-direction: column; gap: .72rem; }
    .tracker-strip-brand { width: 100%; padding: 0 0 .65rem; border-right: 0; border-bottom: 1px solid rgba(255,255,255,.08); }
    .tracker-strip-metrics { width: 100%; }
    .tracker-overview { grid-template-columns: 1fr; }
    .tracker-log-row { grid-template-columns: minmax(0,1fr) minmax(0,1fr); }
    .tracker-result { justify-self: start; }
    [data-testid="stMainBlockContainer"] { padding-left: .8rem; padding-right: .8rem; }
}

@media (max-width: 620px) {
    .insights-grid { grid-template-columns: 1fr; }
    .top-nav-sub, .top-nav-sync small { display: none; }
    .hero-card { padding: 1.1rem; }
    .tracker-strip-metrics { grid-template-columns: repeat(2, minmax(0,1fr)); }
    .tracker-bucket-grid, .tracker-overview-grid { grid-template-columns: 1fr; }
    .tracker-record-hero { align-items: flex-start; flex-direction: column; gap: .8rem; }
    .tracker-log-row { grid-template-columns: 1fr; }
    .tracker-split-heading, .tracker-panel-head { align-items: flex-start; flex-direction: column; }
    .tracker-panel-count { align-self: flex-start; }
}
</style>
"""
import html
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import streamlit as st



ET = ZoneInfo("America/New_York")

# Change these two numbers if you want a different daily forced-update time.
# Live scores refresh independently; saved forecast inputs remain immutable.
DAILY_REFRESH_HOUR_ET = 8
DAILY_REFRESH_MINUTE_ET = 0
LIVE_REFRESH_SECONDS = 30
MODEL_VERSION = "24.1-input-integrity"
SHORTLIST_RULE_VERSION = "24.1-prospective"

def initialize_page() -> None:
    st.set_page_config(
        page_title="MLB Quantitative Matchup & Winner Engine",
        page_icon="⚾", layout="wide", initial_sidebar_state="collapsed",
    )
    st.markdown(stadium_stylesheet(), unsafe_allow_html=True)
    st.markdown(floating_logo_markup(), unsafe_allow_html=True)


@st.cache_resource
def daily_refresh_tracker() -> dict[str, str | None]:
    """Share the last forced-refresh date across sessions in this app process."""
    return {"completed_for": None}


def scheduled_update_at(day: date) -> datetime:
    return datetime(
        day.year,
        day.month,
        day.day,
        DAILY_REFRESH_HOUR_ET,
        DAILY_REFRESH_MINUTE_ET,
        tzinfo=ET,
    )


def next_scheduled_update(now_et: datetime) -> datetime:
    scheduled = scheduled_update_at(now_et.date())
    return scheduled if now_et < scheduled else scheduled + timedelta(days=1)


def shift_slate_date(days: int) -> None:
    today = datetime.now(ET).date()
    current = st.session_state.get("slate_date", today)
    if isinstance(current, datetime):
        current = current.date()
    target = max(today, min(current + timedelta(days=days), today + timedelta(days=7)))
    st.session_state["slate_date"] = target


def toggle_game_analysis(game_pk: int) -> None:
    """Keep only one heavyweight matchup report mounted in the browser."""
    current = st.session_state.get("open_game_pk")
    st.session_state["open_game_pk"] = None if current == game_pk else game_pk


TRACKER_SCHEMA_VERSION = 1
TRACKER_BUILD = 24
TRACKER_MAX_BYTES = 50_000_000
TRACKER_RESULT_OPTIONS = ("PENDING", "WIN", "LOSS", "VOID")
_tracker_path_override = os.environ.get("MLB_TRACKER_PATH", "").strip()
TRACKER_PATH = (
    Path(_tracker_path_override).expanduser()
    if _tracker_path_override
    else Path(__file__).resolve().with_name(".mlb_quant_tracker.json")
)


@st.cache_resource(show_spinner=False)
def _shared_tracker_lock(path: str) -> Any:
    """One transaction lock per ledger, shared across Streamlit reruns/sessions."""
    return threading.RLock()


_TRACKER_LOCK = _shared_tracker_lock(str(TRACKER_PATH.resolve()))


def _tracker_timestamp(moment: datetime | None = None) -> str:
    value = moment or datetime.now(ET)
    if value.tzinfo is None:
        value = value.replace(tzinfo=ET)
    return value.astimezone(ET).isoformat(timespec="seconds")


def empty_prediction_tracker() -> dict[str, Any]:
    created_at = _tracker_timestamp()
    return {
        "schema_version": TRACKER_SCHEMA_VERSION,
        "created_at": created_at,
        "updated_at": created_at,
        "picks": {},
    }


def _validate_tracker_payload(raw: Any) -> dict[str, Any]:
    """Return a normalized tracker payload or raise a clear validation error."""
    if not isinstance(raw, dict):
        raise ValueError("The tracker backup must contain a JSON object.")
    if raw.get("schema_version", TRACKER_SCHEMA_VERSION) != TRACKER_SCHEMA_VERSION:
        raise ValueError("This backup uses an unsupported tracker format.")
    raw_picks = raw.get("picks")
    if not isinstance(raw_picks, dict):
        raise ValueError("The tracker backup is missing its picks collection.")

    payload = dict(raw)
    payload.update({
        "schema_version": TRACKER_SCHEMA_VERSION,
        "created_at": str(raw.get("created_at") or _tracker_timestamp()),
        "updated_at": str(raw.get("updated_at") or _tracker_timestamp()),
        "picks": {},
    })
    for raw_key, raw_entry in raw_picks.items():
        if not isinstance(raw_entry, dict):
            raise ValueError(f"Tracker entry {raw_key!s} is not valid.")
        try:
            game_pk = int(raw_entry.get("game_pk", raw_key))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Tracker entry {raw_key!s} has no valid game ID.") from exc
        if game_pk <= 0 or str(game_pk) != str(raw_key):
            raise ValueError(f"Tracker entry {raw_key!s} has a mismatched game ID.")
        if raw_entry.get("target_side") not in {"away", "home"}:
            raise ValueError(f"Tracker entry {game_pk} has no valid frozen pick.")
        try:
            probability = float(raw_entry.get("target_probability"))
            quality = float(raw_entry.get("quality_score", 0))
            date.fromisoformat(str(raw_entry.get("game_date")))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Tracker entry {game_pk} has invalid pick details.") from exc
        if not math.isfinite(probability) or not 0.0 <= probability <= 1.0:
            raise ValueError(f"Tracker entry {game_pk} has an invalid probability.")
        if not math.isfinite(quality) or not 0 <= quality <= 100:
            raise ValueError(f"Tracker entry {game_pk} has an invalid data-quality score.")
        result = str(raw_entry.get("result") or "PENDING").upper()
        if result not in TRACKER_RESULT_OPTIONS:
            raise ValueError(f"Tracker entry {game_pk} has an unsupported result.")
        entry = dict(raw_entry)
        entry["game_pk"] = game_pk
        entry["result"] = result
        if not isinstance(entry.get("manual_override", False), bool):
            raise ValueError(f"Tracker entry {game_pk} has an invalid correction flag.")
        entry["manual_override"] = entry.get("manual_override", False)
        snapshot = entry.get("frozen_prediction")
        if snapshot is not None:
            if not isinstance(snapshot, dict):
                raise ValueError(f"Tracker entry {game_pk} has an invalid frozen forecast.")
            required_numbers = ("away_probability", "home_probability", "target_probability",
                                "projected_away_runs", "projected_home_runs", "quality_score",
                                "simulation_home_probability", "record_home_probability", "model_agreement_gap",
                                "park_factor", "weather_factor", "shared_environment_factor", "simulations")
            if any(safe_float(snapshot.get(field)) is None for field in required_numbers):
                raise ValueError(f"Tracker entry {game_pk} has incomplete frozen model values.")
            if (snapshot.get("target_side") != entry["target_side"]
                    or abs(float(snapshot["target_probability"]) - probability) > 0.000002
                    or abs(float(snapshot["away_probability"]) + float(snapshot["home_probability"]) - 1.0) > 0.000002):
                raise ValueError(f"Tracker entry {game_pk} has a conflicting frozen pick.")
            numeric_profiles = {
                "away_offense": ("strength", "season_rpg", "recent_rpg", "ops"),
                "home_offense": ("strength", "season_rpg", "recent_rpg", "ops"),
                "away_starter": ("quality_ra9", "expected_ip"),
                "home_starter": ("quality_ra9", "expected_ip"),
                "away_bullpen": ("quality_ra9",), "home_bullpen": ("quality_ra9",),
                "distribution": ("total_line", "over_probability", "under_probability"),
            }
            for field, keys in numeric_profiles.items():
                profile = snapshot.get(field)
                if not isinstance(profile, dict) or any(safe_float(profile.get(key)) is None for key in keys):
                    raise ValueError(f"Tracker entry {game_pk} has invalid frozen {field} data.")
        payload["picks"][str(game_pk)] = entry
    return payload


def load_prediction_tracker() -> tuple[dict[str, Any], str]:
    """Load the local ledger without allowing a damaged file to break the app."""
    with _TRACKER_LOCK:
        try:
            with TRACKER_PATH.open("r", encoding="utf-8") as handle:
                payload = _validate_tracker_payload(json.load(handle))
            return payload, "ready"
        except FileNotFoundError:
            return empty_prediction_tracker(), "ready"
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            return empty_prediction_tracker(), f"Tracker storage needs attention: {exc}"


def save_prediction_tracker(payload: dict[str, Any]) -> tuple[bool, str]:
    """Atomically persist the ledger so an interrupted rerun cannot corrupt it."""
    try:
        normalized = _validate_tracker_payload(payload)
        normalized["updated_at"] = _tracker_timestamp()
        with _TRACKER_LOCK:
            TRACKER_PATH.parent.mkdir(parents=True, exist_ok=True)
            temporary_path = TRACKER_PATH.with_name(f"{TRACKER_PATH.name}.tmp")
            with temporary_path.open("w", encoding="utf-8") as handle:
                json.dump(normalized, handle, indent=2, sort_keys=True)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, TRACKER_PATH)
        return True, "ready"
    except (OSError, ValueError, TypeError) as exc:
        return False, f"Tracker could not save: {exc}"


def _tracker_fair_moneyline(prediction: dict[str, Any]) -> int | None:
    value = (
        prediction.get("fair_away_odds")
        if prediction.get("target_side") == "away"
        else prediction.get("fair_home_odds")
    )
    try:
        return int(round(float(value))) if value is not None else None
    except (TypeError, ValueError):
        return None


def forecast_research_selection(prediction: dict[str, Any]) -> dict[str, Any]:
    """A fixed prospective research rule, not a claim of proven betting value."""
    probability = float(prediction.get("target_probability") or 0.5)
    quality = float(prediction.get("quality_score") or 0)
    agreement = safe_float(prediction.get("model_agreement_gap"))
    starters_ready = all(
        bool((prediction.get(f"{side}_starter") or {}).get("has_stats"))
        and float((prediction.get(f"{side}_starter") or {}).get("sample_bf") or 0) >= 80
        for side in ("away", "home")
    )
    reasons = []
    if probability < 0.60:
        reasons.append("Win probability is below the 60% research cutoff.")
    if quality < 80:
        reasons.append("Data completeness is below 80/100.")
    if not starters_ready:
        reasons.append("Both starters need usable statistics and at least 80 batters faced.")
    if agreement is None or agreement > 0.10:
        reasons.append("The simulation and record estimate do not agree within 10 points.")
    qualifies = not reasons
    if qualifies:
        label, tone = "Stronger setup", "good"
    elif probability < 0.55:
        label, tone = "Close matchup · pass", "warn"
    elif quality < 80 or not starters_ready:
        label, tone = "Incomplete setup · pass", "warn"
    else:
        label, tone = "Standard forecast", "ice"
    return {
        "rule_version": SHORTLIST_RULE_VERSION, "qualifies": qualifies,
        "label": label, "tone": tone, "reasons": reasons,
        "notice": "Experimental research selection, not a validated edge or guaranteed winner.",
    }


def _wilson_interval(wins: int, total: int) -> tuple[float | None, float | None]:
    if not total:
        return None, None
    z = 1.959963984540054
    proportion = wins / total
    denominator = 1.0 + z * z / total
    center = (proportion + z * z / (2.0 * total)) / denominator
    radius = z * math.sqrt(proportion * (1.0 - proportion) / total + z * z / (4.0 * total * total)) / denominator
    return max(0.0, center - radius), min(1.0, center + radius)


def evaluate_frozen_forecasts(entries: Iterable[dict[str, Any]]) -> dict[str, Any]:
    rows = list(entries)
    graded = [row for row in rows if row.get("result") in {"WIN", "LOSS"}
              and not row.get("manual_override")]
    probabilities = [float(row["target_probability"]) for row in graded]
    outcomes = [float(row["result"] == "WIN") for row in graded]
    count = len(graded)
    wins = int(sum(outcomes))
    low, high = _wilson_interval(wins, count)
    brier = sum((p - y) ** 2 for p, y in zip(probabilities, outcomes)) / count if count else None
    log_loss = -sum(y * math.log(clamp(p, 1e-12, 1.0 - 1e-12))
                    + (1.0 - y) * math.log(clamp(1.0 - p, 1e-12, 1.0 - 1e-12))
                    for p, y in zip(probabilities, outcomes)) / count if count else None
    mean_probability = sum(probabilities) / count if count else None
    observed = wins / count if count else None
    prospectively_labeled = [row for row in rows
                            if (row.get("research_selection") or {}).get("rule_version") == SHORTLIST_RULE_VERSION]
    shortlisted = [row for row in prospectively_labeled
                   if row["research_selection"].get("qualifies")]
    comparisons = []
    for key, label in (("simulation_home", "Run simulation"), ("record_home", "Record baseline"),
                       ("market_home", "No-vig sportsbook"), ("calibrated_target", "Calibration challenger")):
        paired = []
        for row in graded:
            evidence = row.get("evaluation_probabilities") or {}
            candidate = safe_float(evidence.get(key))
            if candidate is None or not 0.0 <= candidate <= 1.0:
                continue
            y = float(row["result"] == "WIN")
            candidate_target = candidate if key == "calibrated_target" or row["target_side"] == "home" else 1.0 - candidate
            paired.append(((float(row["target_probability"]) - y) ** 2, (candidate_target - y) ** 2))
        if paired:
            comparisons.append({
                "name": label, "n": len(paired),
                "main_brier": sum(pair[0] for pair in paired) / len(paired),
                "candidate_brier": sum(pair[1] for pair in paired) / len(paired),
            })
    return {
        "n": count, "wins": wins, "win_rate": observed,
        "mean_probability": mean_probability, "brier": brier, "log_loss": log_loss,
        "interval_low": low, "interval_high": high,
        "calibration_gap": observed - mean_probability if count else None,
        "manual_excluded": sum(bool(row.get("manual_override")) for row in rows),
        "shortlisted": tracker_record(shortlisted),
        "prospective_count": len(prospectively_labeled), "comparisons": comparisons,
    }


def fit_calibration_challenger(entries: Iterable[dict[str, Any]], as_of: datetime) -> dict[str, Any] | None:
    """Fit only on older verified results; never alter the published main pick."""
    cutoff = as_of.astimezone(timezone.utc)
    training = []
    for row in entries:
        graded_at = _parse_utc(str(row.get("graded_at_et") or ""))
        captured_at = _parse_utc(str(row.get("captured_at_et") or ""))
        if (row.get("model_version") != MODEL_VERSION or row.get("manual_override")
                or row.get("result") not in {"WIN", "LOSS"}
                or row.get("graded_source") != "official MLB final"
                or not graded_at or not captured_at or not captured_at < graded_at < cutoff):
            continue
        training.append(row)
    training.sort(key=lambda row: _parse_utc(str(row["graded_at_et"])))
    training = training[-2000:]
    if len(training) < 200 or len({row["game_date"] for row in training}) < 14:
        return None
    examples = [(math.log(clamp(float(row["target_probability"]), .001, .999)
                           / (1.0 - clamp(float(row["target_probability"]), .001, .999))),
                 float(row["result"] == "WIN")) for row in training]
    def loss(scale: float) -> float:
        total = 0.0
        for logit, outcome in examples:
            p = 1.0 / (1.0 + math.exp(-scale * logit))
            total -= outcome * math.log(p) + (1.0 - outcome) * math.log(1.0 - p)
        return total / len(examples) + .01 * (scale - 1.0) ** 2
    scale = min((.25 + .05 * step for step in range(26)), key=loss)
    return {"scale": round(scale, 3), "training_count": len(training),
            "trained_through_et": str(training[-1]["graded_at_et"])}


def attach_forecast_evidence(prediction: dict[str, Any], weather: dict[str, Any],
                             lineup: dict[str, Any], calibration: dict[str, Any] | None) -> dict[str, Any]:
    prediction = dict(prediction)
    prediction["model_version"] = MODEL_VERSION
    prediction["research_selection"] = forecast_research_selection(prediction)
    prediction["captured_context"] = {"weather": copy.deepcopy(weather), "lineup": copy.deepcopy(lineup)}
    prediction["evaluation_probabilities"] = {
        "simulation_home": safe_float(prediction.get("simulation_home_probability")),
        "record_home": safe_float(prediction.get("record_home_probability")),
        "market_home": safe_float((prediction.get("odds") or {}).get("home_no_vig")),
    }
    if calibration:
        probability = clamp(float(prediction["target_probability"]), .001, .999)
        calibrated = 1.0 / (1.0 + math.exp(-float(calibration["scale"]) * math.log(probability / (1.0 - probability))))
        prediction["evaluation_probabilities"]["calibrated_target"] = calibrated
        prediction["calibration_training"] = dict(calibration)
    return prediction


def apply_frozen_forecast(prediction: dict[str, Any], entry: dict[str, Any] | None) -> dict[str, Any]:
    """Use the saved forecast for display; only the separate scoreboard stays live."""
    current_game = prediction["game"]
    if entry is None:
        output = dict(prediction)
        output["snapshot_state"] = "preview" if current_game["live"]["status"] == "PREVIEW" else "untracked"
        output["pregame_locked"] = False
        if output["snapshot_state"] == "untracked":
            output["research_selection"] = {"label": "No pregame record", "tone": "warn", "qualifies": False,
                                            "reasons": ["Not eligible for a pregame research trial after play has started."]}
        return output
    if any(int(current_game[side].get("id") or 0) != int(entry.get(f"{side}_id") or 0)
           for side in ("away", "home")):
        raise ValueError("A saved forecast's team IDs do not match the official game.")
    snapshot = entry.get("frozen_prediction")
    output = copy.deepcopy(snapshot) if isinstance(snapshot, dict) else dict(prediction)
    output["game"] = copy.deepcopy(current_game)
    original_teams = entry.get("frozen_teams") or {}
    for side in ("away", "home"):
        if isinstance(original_teams.get(side), dict):
            for field in ("pitcher_id", "pitcher_name"):
                output["game"][side][field] = original_teams[side].get(field)
    target_side = entry["target_side"]
    target_probability = float(entry["target_probability"])
    output.update({
        "target_side": target_side, "target_name": entry["target_name"],
        "target_probability": target_probability,
        "home_probability": target_probability if target_side == "home" else 1.0 - target_probability,
        "away_probability": target_probability if target_side == "away" else 1.0 - target_probability,
        "projected_away_runs": float(entry["projected_away_runs"]),
        "projected_home_runs": float(entry["projected_home_runs"]),
        "quality_score": int(entry["quality_score"]), "quality_label": entry["quality_label"],
        "pregame_locked": True, "live_score_used": False,
        "snapshot_state": "saved" if isinstance(snapshot, dict) else "legacy",
        "captured_at_et": entry["captured_at_et"],
        "research_selection": copy.deepcopy(entry.get("research_selection")) or {
            "label": "Earlier-build pick", "tone": "ice", "qualifies": False,
            "reasons": ["Not retrospectively added to the new research shortlist."],
        },
    })
    for side in ("away", "home"):
        output[f"fair_{side}_odds"] = american_from_probability(output[f"{side}_probability"])
    output[f"fair_{target_side}_odds"] = entry.get("fair_moneyline") or output[f"fair_{target_side}_odds"]
    if not snapshot:
        output["value"] = None
        output["support"], output["risks"] = _comparison_reasons(
            output["game"], output["away_offense"], output["home_offense"],
            output["away_starter"], output["home_starter"], output["away_bullpen"], output["home_bullpen"],
            (prediction.get("captured_context") or {}).get("weather") or {}, target_side,
        )
    return output


def forecast_lock_label(prediction: dict[str, Any]) -> str:
    state = prediction.get("snapshot_state")
    if state == "untracked":
        return "Not recorded pregame"
    if state == "preview":
        return "Pregame preview · not saved"
    return "Saved pregame pick"


def prediction_tracker_entry(
    prediction: dict[str, Any], captured_at: datetime
) -> dict[str, Any]:
    """Freeze the published pregame pick and its supporting display fields."""
    game = prediction["game"]
    target_side = str(prediction["target_side"])
    target = game[target_side]
    scheduled = game.get("game_datetime_utc")
    entry = {
        "game_pk": int(game["game_pk"]),
        "game_date": str(game.get("official_date") or captured_at.date().isoformat()),
        "scheduled_at": (
            scheduled.astimezone(timezone.utc).isoformat(timespec="seconds")
            if isinstance(scheduled, datetime)
            else str(game.get("game_datetime_raw") or "")
        ),
        "away_id": int(game["away"].get("id") or 0),
        "away_name": str(game["away"].get("name") or "Away team"),
        "away_short_name": str(game["away"].get("short_name") or "Away"),
        "away_logo": str(game["away"].get("logo") or ""),
        "home_id": int(game["home"].get("id") or 0),
        "home_name": str(game["home"].get("name") or "Home team"),
        "home_short_name": str(game["home"].get("short_name") or "Home"),
        "home_logo": str(game["home"].get("logo") or ""),
        "target_side": target_side,
        "target_id": int(target.get("id") or 0),
        "target_name": str(target.get("name") or "Model pick"),
        "target_short_name": str(target.get("short_name") or target.get("name") or "Pick"),
        "target_logo": str(target.get("logo") or ""),
        "target_probability": round(float(prediction["target_probability"]), 6),
        "fair_moneyline": _tracker_fair_moneyline(prediction),
        "projected_away_runs": round(float(prediction["projected_away_runs"]), 3),
        "projected_home_runs": round(float(prediction["projected_home_runs"]), 3),
        "quality_score": int(prediction.get("quality_score") or 0),
        "quality_label": str(prediction.get("quality_label") or "Limited"),
        "captured_at_et": _tracker_timestamp(captured_at),
        "source_build": TRACKER_BUILD,
        "result": "PENDING",
        "manual_override": False,
        "final_away_runs": None,
        "final_home_runs": None,
        "graded_at_et": None,
        "latest_status": "PREVIEW",
        "status_label": str(game["live"].get("status_label") or "Scheduled"),
    }
    entry.update({
        "model_version": prediction.get("model_version", MODEL_VERSION),
        "research_selection": copy.deepcopy(prediction.get("research_selection")) or forecast_research_selection(prediction),
        "evaluation_probabilities": copy.deepcopy(prediction.get("evaluation_probabilities") or {}),
    })
    if prediction.get("captured_context") is not None:
        entry["frozen_prediction"] = copy.deepcopy({key: value for key, value in prediction.items() if key != "game"})
        entry["frozen_teams"] = {side: copy.deepcopy(game[side]) for side in ("away", "home")}
    return entry


def _pregame_snapshot_allowed(game: dict[str, Any], now_et: datetime) -> bool:
    live = game.get("live") or {}
    if live.get("status") != "PREVIEW":
        return False
    if str(game.get("official_date") or "") != now_et.date().isoformat():
        return False
    scheduled = game.get("game_datetime_utc") or _parse_utc(str(game.get("game_datetime_raw") or ""))
    if not isinstance(scheduled, datetime) or scheduled.tzinfo is None:
        return False
    # A stale Preview response must not let the model create a pick after play.
    # Conservatively skip late captures even when a scheduled start is delayed.
    if now_et.astimezone(timezone.utc) >= scheduled.astimezone(timezone.utc):
        return False
    state_text = " ".join(
        str(live.get(key) or "") for key in ("status_label", "detailed_state")
    ).lower()
    blocked_states = ("postpon", "cancel", "suspend", "completed early")
    return not any(blocked in state_text for blocked in blocked_states)


def _automatic_result(entry: dict[str, Any], away_runs: int, home_runs: int) -> str:
    if away_runs == home_runs:
        return "VOID"
    winning_side = "away" if away_runs > home_runs else "home"
    return "WIN" if entry.get("target_side") == winning_side else "LOSS"


def fetch_tracker_official_results(game_pks: tuple[int, ...]) -> dict[str, Any]:
    """Look up saved game IDs across ALL dates, independently of the viewed slate."""
    unique_ids = sorted({int(game_pk) for game_pk in game_pks})
    batches = [unique_ids[index:index + 50] for index in range(0, len(unique_ids), 50)]
    games: dict[int, dict[str, Any]] = {}
    warnings: list[str] = []

    def fetch_batch(batch: list[int]) -> dict[str, Any]:
        body = _request_bytes(
            f"{MLB_API_BASE}/schedule",
            {"sportId": 1, "gamePks": ",".join(str(pk) for pk in batch), "hydrate": "linescore"},
            timeout=10,
            attempts=1,
        )
        response = json.loads(body.decode("utf-8"))
        if not isinstance(response, dict) or not isinstance(response.get("dates"), list):
            raise DataSourceError("The MLB result response was incomplete.")
        return response

    if batches:
        with ThreadPoolExecutor(max_workers=min(4, len(batches))) as executor:
            futures = {executor.submit(fetch_batch, batch): batch for batch in batches}
            for future in as_completed(futures):
                batch = futures[future]
                try:
                    response = future.result()
                    # A gamePks lookup can return several separate date objects.
                    # Reading only dates[0] recreates the rollover bug.
                    for day in response["dates"]:
                        for raw in day.get("games", []):
                            game_pk = int(raw.get("gamePk") or 0)
                            if game_pk in batch:
                                games[game_pk] = raw
                except (DataSourceError, OSError, ValueError, TypeError, AttributeError):
                    warnings.append(f"MLB result lookup failed for {len(batch)} saved games.")

    missing = [game_pk for game_pk in unique_ids if game_pk not in games]
    if missing and not warnings:
        warnings.append(f"MLB did not return {len(missing)} saved games.")
    return {
        "games": games,
        "requested_ids": unique_ids,
        "missing_ids": missing,
        "checked_at_et": _tracker_timestamp(),
        "warnings": warnings,
    }


@st.cache_data(ttl=60, show_spinner=False)
def cached_tracker_official_results(game_pks: tuple[int, ...]) -> dict[str, Any]:
    return fetch_tracker_official_results(game_pks)


def _tracker_official_score(raw: dict[str, Any], side: str) -> int | None:
    """Missing scores must stay missing; never turn an absent result into 0–0."""
    teams = raw.get("teams") or {}
    line_teams = (raw.get("linescore") or {}).get("teams") or {}
    value = (teams.get(side) or {}).get("score")
    if value is None:
        value = (line_teams.get(side) or {}).get("runs")
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or number < 0 or not number.is_integer():
        return None
    return int(number)


def reconcile_tracker_payload(
    payload: dict[str, Any], result_batch: dict[str, Any]
) -> tuple[int, list[str]]:
    """Settle existing pending entries only; never recalculate or invent a pick."""
    settled = 0
    warnings = list(result_batch.get("warnings") or [])
    checked_at = str(result_batch.get("checked_at_et") or _tracker_timestamp())
    official_games = result_batch.get("games") or {}

    for entry in payload["picks"].values():
        if entry.get("result") != "PENDING" or entry.get("manual_override"):
            continue
        game_pk = int(entry["game_pk"])
        raw = official_games.get(game_pk) or official_games.get(str(game_pk))
        if raw is None:
            continue
        try:
            raw_teams = raw.get("teams") or {}
            identity_matches = int(raw.get("gamePk") or 0) == game_pk and all(
                int(((raw_teams.get(side) or {}).get("team") or {}).get("id") or 0)
                == int(entry.get(f"{side}_id") or 0)
                for side in ("away", "home")
            )
        except (AttributeError, TypeError, ValueError, OverflowError):
            identity_matches = False
        if not identity_matches:
            warnings.append(f"Game {game_pk}: team identity could not be verified; kept pending.")
            continue

        official_status = raw.get("status") or {}
        abstract_state = str(official_status.get("abstractGameState") or "Preview").upper()
        detail = str(official_status.get("detailedState") or abstract_state.title())
        detail_lower = detail.lower()
        entry["latest_status"] = abstract_state
        entry["status_label"] = detail
        entry["last_result_checked_at_et"] = checked_at

        # Postponed/suspended games may have an abstract Final status but have
        # not produced a usable result. Keep checking the same saved game ID.
        if "postpon" in detail_lower or "suspend" in detail_lower:
            continue
        if "cancel" in detail_lower:
            entry["result"] = "VOID"
            entry["graded_source"] = "official MLB cancellation"
        elif abstract_state == "FINAL":
            away_runs = _tracker_official_score(raw, "away")
            home_runs = _tracker_official_score(raw, "home")
            if away_runs is None or home_runs is None:
                warnings.append(f"Game {game_pk}: final score is missing; kept pending.")
                continue
            entry["final_away_runs"] = away_runs
            entry["final_home_runs"] = home_runs
            entry["result"] = _automatic_result(entry, away_runs, home_runs)
            entry["graded_source"] = "official MLB final"
        else:
            continue

        entry["graded_at_et"] = checked_at
        entry["graded_by_build"] = TRACKER_BUILD
        settled += 1

    payload["result_sync"] = {
        "checked_at_et": checked_at,
        "requested_count": len(result_batch.get("requested_ids") or []),
        "returned_count": len(official_games),
        "settled_count": settled,
        "warnings": warnings,
    }
    return settled, warnings


def sync_prediction_tracker(
    predictions: list[dict[str, Any]], now_et: datetime, *, reconcile: bool = True
) -> tuple[dict[str, Any], str]:
    """Capture today's previews, then reconcile pending IDs from every saved date."""
    snapshot, storage_status = load_prediction_tracker()
    if storage_status != "ready":
        # Never overwrite an unreadable ledger with an apparently empty one.
        return snapshot, storage_status

    requested_ids = {
        int(entry["game_pk"])
        for entry in snapshot["picks"].values()
        if entry.get("result") == "PENDING" and not entry.get("manual_override")
    }
    requested_ids.update(
        int(prediction["game"]["game_pk"])
        for prediction in predictions
        if str(prediction["game"]["game_pk"]) not in snapshot["picks"]
        and _pregame_snapshot_allowed(prediction["game"], now_et)
    )
    result_batch = None
    if reconcile and requested_ids:
        # Network calls run outside the write lock. Reload under the lock below
        # so another browser session's captures/corrections are not lost.
        result_batch = cached_tracker_official_results(tuple(sorted(requested_ids)))

    with _TRACKER_LOCK:
        payload, storage_status = load_prediction_tracker()
        if storage_status != "ready":
            return payload, storage_status
        before = json.dumps(payload, sort_keys=True)
        for prediction in predictions:
            game = prediction["game"]
            key = str(int(game["game_pk"]))
            entry = payload["picks"].get(key)
            if entry is None and _pregame_snapshot_allowed(game, now_et):
                entry = prediction_tracker_entry(prediction, now_et)
                payload["picks"][key] = entry
            if entry is not None and entry.get("result") == "PENDING" and not entry.get("manual_override"):
                live = game.get("live") or {}
                entry["latest_status"] = str(live.get("status") or "PREVIEW")
                entry["status_label"] = str(live.get("status_label") or "Scheduled")

        warnings: list[str] = []
        if result_batch is not None:
            _, warnings = reconcile_tracker_payload(payload, result_batch)
        elif reconcile and not requested_ids:
            # There is nothing automatic left to settle, so stale network
            # warnings should not persist after a manual correction/restore.
            if payload.get("result_sync", {}).get("warnings"):
                payload["result_sync"]["warnings"] = []

        if json.dumps(payload, sort_keys=True) != before:
            saved, save_status = save_prediction_tracker(payload)
            if not saved:
                return payload, save_status
            payload, storage_status = load_prediction_tracker()
        if warnings:
            storage_status = " ".join(warnings) + " Saved picks are unchanged; the tracker will retry."
        return payload, storage_status


def tracker_sync_can_publish(payload: dict[str, Any], status: str) -> bool:
    """A partial results-feed failure must not block other saved progress."""
    if status == "ready":
        return True
    warnings = (payload.get("result_sync") or {}).get("warnings") or []
    return bool(warnings) and status == " ".join(warnings) + " Saved picks are unchanged; the tracker will retry."


def _tracker_sort_key(entry: dict[str, Any]) -> tuple[str, str, int]:
    return (
        str(entry.get("game_date") or ""),
        str(entry.get("scheduled_at") or entry.get("captured_at_et") or ""),
        int(entry.get("game_pk") or 0),
    )


def tracker_record(entries: Iterable[dict[str, Any]]) -> dict[str, Any]:
    rows = list(entries)
    completed = [row for row in rows if row.get("result") in {"WIN", "LOSS"}]
    completed.sort(key=_tracker_sort_key, reverse=True)
    wins = sum(row.get("result") == "WIN" for row in completed)
    losses = sum(row.get("result") == "LOSS" for row in completed)
    decisions = wins + losses
    recent = completed[:10]
    recent_wins = sum(row.get("result") == "WIN" for row in recent)
    recent_losses = sum(row.get("result") == "LOSS" for row in recent)
    streak = "—"
    if completed:
        streak_result = str(completed[0]["result"])
        streak_count = 0
        for row in completed:
            if row.get("result") != streak_result:
                break
            streak_count += 1
        streak = f"{'W' if streak_result == 'WIN' else 'L'}{streak_count}"
    return {
        "wins": wins,
        "losses": losses,
        "decisions": decisions,
        "pending": sum(row.get("result") == "PENDING" for row in rows),
        "void": sum(row.get("result") == "VOID" for row in rows),
        "win_rate": wins / decisions if decisions else None,
        "last_ten": f"{recent_wins}-{recent_losses}" if recent else "—",
        "streak": streak,
    }


def tracker_confidence_group(entry: dict[str, Any]) -> str:
    probability = float(entry.get("target_probability") or 0.0) * 100.0
    if probability >= 60.0:
        return "60%+"
    if probability >= 55.0:
        return "55–59.9%"
    return "50–54.9%"


def tracker_quality_group(entry: dict[str, Any]) -> str:
    quality = int(entry.get("quality_score") or 0)
    if quality >= 80:
        return "Higher quality"
    if quality >= 65:
        return "Solid quality"
    return "Limited quality"


def tracker_group_records(
    entries: Iterable[dict[str, Any]], group_function: Any, labels: Iterable[str]
) -> list[tuple[str, dict[str, Any]]]:
    rows = list(entries)
    return [
        (label, tracker_record(row for row in rows if group_function(row) == label))
        for label in labels
    ]


def tracker_json_bytes(payload: dict[str, Any]) -> bytes:
    normalized = _validate_tracker_payload(payload)
    return json.dumps(normalized, indent=2, sort_keys=True).encode("utf-8")


def tracker_csv_bytes(payload: dict[str, Any]) -> bytes:
    columns = [
        "game_date", "away_name", "home_name", "target_name", "target_probability",
        "fair_moneyline", "quality_score", "result", "final_away_runs",
        "final_home_runs", "captured_at_et", "graded_at_et", "manual_override",
    ]
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=columns)
    writer.writeheader()
    for entry in sorted(payload["picks"].values(), key=_tracker_sort_key, reverse=True):
        row = {column: entry.get(column) for column in columns}
        probability = entry.get("target_probability")
        row["target_probability"] = (
            round(float(probability) * 100.0, 1) if probability is not None else None
        )
        writer.writerow(row)
    return output.getvalue().encode("utf-8")


def apply_tracker_override(game_pk: int, result: str) -> tuple[bool, str]:
    with _TRACKER_LOCK:
        payload, status = load_prediction_tracker()
        if status != "ready":
            return False, status
        entry = payload["picks"].get(str(int(game_pk)))
        if entry is None:
            return False, "That tracked game could not be found."
        normalized_result = str(result).upper()
        if normalized_result == "AUTO":
            entry["manual_override"] = False
            entry["result"] = "PENDING"
            entry["graded_at_et"] = None
            entry["graded_source"] = None
        elif normalized_result in TRACKER_RESULT_OPTIONS:
            entry["manual_override"] = True
            entry["result"] = normalized_result
            entry["graded_at_et"] = _tracker_timestamp()
            entry["graded_source"] = "manual correction"
        else:
            return False, "Choose Auto, Win, Loss, Void or Pending."
        entry["correction_updated_at_et"] = _tracker_timestamp()
        return save_prediction_tracker(payload)


def _tracker_captured_utc(entry: dict[str, Any]) -> datetime:
    return _parse_utc(str(entry.get("captured_at_et") or "")) or datetime.max.replace(tzinfo=timezone.utc)


def merge_tracker_backup(
    current: dict[str, Any], restored: dict[str, Any]
) -> dict[str, Any]:
    """Merge by game ID without dropping picks captured since the backup."""
    merged = dict(current)
    merged["picks"] = dict(current["picks"])
    for game_pk, restored_entry in restored["picks"].items():
        existing = merged["picks"].get(game_pk)
        if existing is None:
            merged["picks"][game_pk] = restored_entry
            continue
        if existing.get("manual_override"):
            continue
        restored_time = _tracker_captured_utc(restored_entry)
        existing_time = _tracker_captured_utc(existing)
        same_pick = all(
            existing.get(field) == restored_entry.get(field)
            for field in ("away_id", "home_id", "target_side", "target_probability", "captured_at_et")
        )
        # After a redeploy, a fresh capture may exist for the same game. The
        # earlier recorded forecast is the canonical original, not the rerun.
        if restored_time < existing_time or (
            same_pick and existing.get("result") == "PENDING"
            and restored_entry.get("result") != "PENDING"
        ):
            merged["picks"][game_pk] = restored_entry
    merged["created_at"] = min(
        str(current.get("created_at") or _tracker_timestamp()),
        str(restored.get("created_at") or _tracker_timestamp()),
    )
    merged["restored_at_et"] = _tracker_timestamp()
    return merged


def restore_prediction_tracker(uploaded_bytes: bytes) -> tuple[bool, str]:
    try:
        if len(uploaded_bytes) > TRACKER_MAX_BYTES:
            raise ValueError("The backup is too large; the limit is 50 MB.")
        raw = json.loads(uploaded_bytes.decode("utf-8"))
        payload = _validate_tracker_payload(raw)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        return False, f"That backup could not be restored: {exc}"
    with _TRACKER_LOCK:
        current, status = load_prediction_tracker()
        if status == "ready":
            payload = merge_tracker_backup(current, payload)
        # Explicit restore can repair an unreadable ledger; automatic sync
        # never overwrites one. The uploaded backup remains the recovery source.
        saved, status = save_prediction_tracker(payload)
    if saved:
        cached_tracker_official_results.clear()
        return True, f"Backup restored: {len(payload['picks'])} picks saved. Newer entries and manual corrections were retained."
    return False, status


class RemoteTrackerError(RuntimeError):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


def _remote_tracker_settings() -> tuple[str, str] | None:
    repo, token = secret_value("MLB_TRACKER_REPO"), secret_value("MLB_TRACKER_TOKEN")
    if not repo and not token:
        return None
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo) or not token:
        raise RemoteTrackerError("Shared tracker needs MLB_TRACKER_REPO (owner/repository) and MLB_TRACKER_TOKEN in Streamlit Secrets.")
    return repo, token


def _github_tracker_request(repo: str, token: str, path: str, *, method: str = "GET", body: dict | None = None, raw: bool = False) -> Any:
    """Use only explicitly configured credentials and the fixed GitHub API host."""
    # Object metadata remains available above 1 MiB; fetch its raw bytes below.
    accept = ("application/vnd.github.raw+json" if raw else
              "application/vnd.github.object+json" if method == "GET" and path.startswith("contents/") else
              "application/vnd.github+json")
    request = urllib.request.Request(
        f"https://api.github.com/repos/{repo}/{path}",
        data=json.dumps(body).encode("utf-8") if body is not None else None,
        method=method,
        headers={"Authorization": f"Bearer {token}", "Accept": accept,
                 "Content-Type": "application/json", "User-Agent": USER_AGENT,
                 "X-GitHub-Api-Version": "2022-11-28"},
    )
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            data = response.read(TRACKER_MAX_BYTES + 1)
            if len(data) > TRACKER_MAX_BYTES:
                raise ValueError("Response too large")
            return data if raw else json.loads(data.decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise RemoteTrackerError(f"Shared tracker returned HTTP {exc.code}; no remote data was overwritten.", exc.code) from None
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        raise RemoteTrackerError("Shared tracker could not be reached; the local tracker is retained.") from None


def _read_remote_tracker(repo: str, token: str) -> tuple[dict, str]:
    item = _github_tracker_request(repo, token, "contents/tracker.json?ref=mlb-tracker-data")
    try:
        if item.get("encoding") == "none" or not item.get("content"):
            content = _github_tracker_request(repo, token, "contents/tracker.json?ref=mlb-tracker-data", raw=True)
        else:
            content = base64.b64decode(item["content"], validate=False)
        if len(content) > TRACKER_MAX_BYTES:
            raise ValueError("Ledger too large")
        return _validate_tracker_payload(json.loads(content)), str(item["sha"])
    except (KeyError, TypeError, ValueError):
        raise RemoteTrackerError("Shared tracker data did not validate; existing local picks were kept.") from None


def tracker_owner_access() -> bool:
    if not secret_value("MLB_TRACKER_REPO") and not secret_value("MLB_TRACKER_TOKEN"):
        return True
    password = secret_value("MLB_TRACKER_ADMIN_PASSWORD")
    if not password:
        st.caption("Shared-tracker corrections are locked. Configure MLB_TRACKER_ADMIN_PASSWORD in Streamlit Secrets to enable owner access.")
        return False
    entered = st.text_input("Owner password", type="password", key="tracker_owner_password")
    return bool(entered) and hmac.compare_digest(entered.encode("utf-8"), password.encode("utf-8"))


@st.cache_data(ttl=45, show_spinner=False)
def cached_remote_tracker(repo: str, token: str) -> tuple[dict, str]:
    return _read_remote_tracker(repo, token)


@st.cache_resource(show_spinner=False)
def remote_permission_blocks() -> set[str]:
    return set()


def _tracker_material_digest(payload: dict[str, Any]) -> str:
    volatile = {"latest_status", "status_label", "last_result_checked_at_et"}
    stable = {key: {name: value for name, value in row.items() if name not in volatile}
              for key, row in payload["picks"].items()}
    return hashlib.sha256(json.dumps(stable, sort_keys=True).encode("utf-8")).hexdigest()


def _merge_remote_ledger(local: dict, remote: dict) -> dict:
    merged = merge_tracker_backup(copy.deepcopy(local), copy.deepcopy(remote))
    if "restored_at_et" in local:
        merged["restored_at_et"] = local["restored_at_et"]
    else:
        merged.pop("restored_at_et", None)
    for key, row in merged["picks"].items():
        left, right = local["picks"].get(key), remote["picks"].get(key)
        if not left or not right or left["target_side"] != right["target_side"]:
            continue
        left_at = _parse_utc(str(left.get("correction_updated_at_et") or (left.get("graded_at_et") if left.get("manual_override") else "") or ""))
        right_at = _parse_utc(str(right.get("correction_updated_at_et") or (right.get("graded_at_et") if right.get("manual_override") else "") or ""))
        if right_at and (not left_at or right_at > left_at):
            for field in ("result", "manual_override", "graded_at_et", "graded_source", "graded_by_build",
                          "final_away_runs", "final_home_runs", "correction_updated_at_et"):
                if field in right:
                    row[field] = right[field]
    worker_times = [str(item.get("worker_last_run_at_et") or "") for item in (local, remote)]
    if any(worker_times):
        merged["worker_last_run_at_et"] = max(worker_times)
    return merged


def sync_remote_tracker(*, write: bool, heartbeat: bool = False) -> str:
    """Optional shared durable ledger; never needed for local automatic grading."""
    settings = None
    try:
        settings = _remote_tracker_settings()
        if settings is None:
            return "not configured"
        repo, token = settings
        identity = hashlib.sha256((repo + token).encode()).hexdigest()
        if identity in remote_permission_blocks():
            return "Shared tracker access was denied. Check the configured token permissions and reboot the app to retry. Local picks are retained."
        for attempt in range(3 if write else 1):
            remote, sha = _read_remote_tracker(repo, token) if write else cached_remote_tracker(repo, token)
            with _TRACKER_LOCK:
                local, status = load_prediction_tracker()
                if status != "ready":
                    return status
                merged = _merge_remote_ledger(local, remote)
                if heartbeat:
                    merged["worker_last_run_at_et"] = _tracker_timestamp()
                if merged != local:
                    saved, status = save_prediction_tracker(merged)
                    if not saved:
                        return status
            if not write or (not heartbeat and _tracker_material_digest(merged) == _tracker_material_digest(remote)):
                return "ready"
            # Content hashes are an optimistic lock across app sessions and workers.
            try:
                _github_tracker_request(repo, token, "contents/tracker.json", method="PUT", body={
                    "message": "Update frozen MLB forecasts and official grades",
                    "branch": "mlb-tracker-data", "sha": sha,
                    "content": base64.b64encode(tracker_json_bytes(merged)).decode("ascii"),
                })
                cached_remote_tracker.clear()
                return "ready"
            except RemoteTrackerError as exc:
                if exc.status not in {409, 422} or attempt == 2:
                    raise
        return "Shared tracker changed concurrently; local picks are retained and will retry."
    except RemoteTrackerError as exc:
        if settings and exc.status in {401, 403}:
            remote_permission_blocks().add(hashlib.sha256((settings[0] + settings[1]).encode()).hexdigest())
        if exc.status == 404:
            return "Shared tracker has not been initialized or cannot be accessed. Run the GitHub tracker workflow once and check its repository permissions. Local picks are retained."
        return str(exc)


def initialize_remote_tracker() -> None:
    """Explicit worker setup only; normal dashboard visits never create branches."""
    settings = _remote_tracker_settings()
    if settings is None:
        raise RemoteTrackerError("The background worker needs its repository and token settings.")
    repo, token = settings
    repository = _github_tracker_request(repo, token, "")
    try:
        _github_tracker_request(repo, token, "git/ref/heads/mlb-tracker-data")
    except RemoteTrackerError as exc:
        if exc.status != 404:
            raise
        default = urllib.parse.quote(str(repository["default_branch"]), safe="")
        reference = _github_tracker_request(repo, token, f"git/ref/heads/{default}")
        _github_tracker_request(repo, token, "git/refs", method="POST", body={
            "ref": "refs/heads/mlb-tracker-data", "sha": reference["object"]["sha"],
        })
    try:
        _read_remote_tracker(repo, token)
    except RemoteTrackerError as exc:
        if exc.status != 404:
            raise
        local, status = load_prediction_tracker()
        if status != "ready":
            raise RemoteTrackerError(status)
        _github_tracker_request(repo, token, "contents/tracker.json", method="PUT", body={
            "message": "Initialize shared MLB tracker", "branch": "mlb-tracker-data",
            "content": base64.b64encode(tracker_json_bytes(local)).decode("ascii"),
        })
        cached_remote_tracker.clear()


def toggle_tracker_dashboard() -> None:
    st.session_state["show_tracker_dashboard"] = not bool(
        st.session_state.get("show_tracker_dashboard", False)
    )


@st.cache_data(ttl=45, show_spinner=False)
def cached_schedule(day: str) -> list[dict[str, Any]]:
    return fetch_schedule(day)


@st.cache_data(ttl=1_800, show_spinner=False)
def cached_team_stats(season: int, day: str) -> dict[int, dict[str, Any]]:
    return fetch_team_stats(season, day)


@st.cache_data(ttl=1_800, show_spinner=False)
def cached_pitchers(
    player_ids: tuple[int, ...], season: int, day: str
) -> dict[int, dict[str, Any]]:
    return fetch_pitcher_profiles(player_ids, season, day)


@st.cache_data(ttl=3_600, show_spinner=False)
def cached_bullpens(team_ids: tuple[int, ...], season: int) -> dict[int, dict[str, Any]]:
    return fetch_bullpen_profiles(team_ids, season)


@st.cache_data(ttl=21_600, show_spinner=False)
def cached_statcast(season: int) -> dict[int, dict[str, Any]]:
    return fetch_pitcher_statcast(season)


@st.cache_data(ttl=86_400, show_spinner=False)
def cached_park_factors(season: int) -> dict[int, dict[str, Any]]:
    return fetch_park_factors(season)


@st.cache_data(ttl=600, show_spinner=False)
def cached_weather(games: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    return fetch_weather_slate(games)


@st.cache_data(ttl=90, show_spinner=False)
def cached_lineups(game_pks: tuple[int, ...]) -> dict[int, dict[str, Any]]:
    return fetch_lineup_statuses(game_pks)


@st.cache_data(ttl=120, show_spinner=False)
def cached_odds(api_key: str) -> list[dict[str, Any]]:
    return fetch_odds(api_key or None)


def secret_value(name: str) -> str:
    if os.environ.get(name):
        return str(os.environ[name]).strip()
    try:
        return str(st.secrets.get(name, "") or "").strip()
    except Exception:
        return ""


def fmt_number(value: Any, decimals: int = 2, missing: str = "N/A") -> str:
    try:
        if value is None:
            return missing
        return f"{float(value):.{decimals}f}"
    except (TypeError, ValueError):
        return missing


def fmt_odds(value: int | float | None) -> str:
    if value is None:
        return "N/A"
    integer = int(round(value))
    return f"+{integer}" if integer > 0 else str(integer)


def safe_text(value: Any) -> str:
    return html.escape(str(value if value is not None else ""), quote=True)


def html_block(markup: str) -> str:
    """Keep custom cards out of Markdown's indented-code path."""
    return "".join(line.strip() for line in markup.splitlines())


def team_accents(team_id: int | None) -> tuple[str, str]:
    return TEAM_COLORS.get(int(team_id or 0), ("#22D3EE", "#5EEAD4"))


def matchup_style(game: dict[str, Any]) -> str:
    away_primary, away_secondary = team_accents(game["away"].get("id"))
    home_primary, home_secondary = team_accents(game["home"].get("id"))
    return (
        f"--away-primary:{away_primary};--away-secondary:{away_secondary};"
        f"--home-primary:{home_primary};--home-secondary:{home_secondary};"
    )


def native_matchup_accents(predictions: list[dict[str, Any]]) -> str:
    """Give native cards team-colored accents without replacing their widgets."""
    rules: list[str] = []
    for prediction in predictions:
        game = prediction["game"]
        game_pk = int(game["game_pk"])
        away_primary, away_secondary = team_accents(game["away"].get("id"))
        home_primary, home_secondary = team_accents(game["home"].get("id"))
        target_primary, target_secondary = team_accents(
            game[prediction["target_side"]].get("id")
        )
        rules.extend(
            [
                (
                    f".st-key-score_card_{game_pk} "
                    "[data-testid='stVerticalBlockBorderWrapper']::before"
                    "{background:linear-gradient(90deg,"
                    f"{away_secondary},{away_primary} 44%,{home_primary} 56%,{home_secondary}) !important;}}"
                ),
                (
                    f".st-key-matchup_row_{game_pk} "
                    "[data-testid='stVerticalBlockBorderWrapper']::before"
                    "{background:linear-gradient(90deg,"
                    f"{away_primary},rgba(255,255,255,.16) 50%,{home_primary}) !important;"
                    "box-shadow:none !important;}"
                ),
                (
                    f".st-key-verdict_{game_pk} "
                    "[data-testid='stVerticalBlockBorderWrapper']"
                    f"{{border-left:3px solid {target_primary} !important;}}"
                ),
            ]
        )
    return "<style>" + "".join(rules) + "</style>"


def confidence_class(label: str) -> str:
    normalized = (label or "").lower()
    if normalized.startswith("high"):
        return "quality-high"
    if normalized.startswith("moderate"):
        return "quality-moderate"
    return "quality-limited"


def probability_tone(probability: float) -> str:
    percentage = float(probability) * 100.0 if probability <= 1.0 else float(probability)
    if percentage >= 58.0:
        return "good"
    if percentage >= 53.0:
        return "warn"
    return "ice"


def quality_tone(score: int | float) -> str:
    if float(score) >= 85.0:
        return "good"
    if float(score) >= 70.0:
        return "warn"
    return "bad"


def tone_color(tone: str) -> str:
    return {
        "good": "#75e49b",
        "bad": "#ff6878",
        "warn": "#f4c76a",
        "ice": "#8bd9ef",
    }.get(tone, "#8bd9ef")


def gauge_markup(
    value: int | float,
    label: str,
    *,
    kind: str = "prediction-gauge",
    tone: str = "ice",
    display: str | None = None,
) -> str:
    numeric = clamp(float(value), 0.0, 100.0)
    shown = display if display is not None else f"{numeric:.1f}%"
    return (
        f"<div class='{safe_text(kind)}' style='--gauge-angle:{numeric * 3.6:.2f}deg;"
        f"--gauge-color:{tone_color(tone)}' aria-label='{safe_text(label)} {safe_text(shown)}'>"
        f"<div class='gauge-copy'><strong>{safe_text(shown)}</strong>"
        f"<span>{safe_text(label)}</span></div></div>"
    )


def section_heading(kicker: str, title: str, meta: str) -> None:
    st.markdown(
        html_block(f"""
        <div class="section-heading">
            <div>
                <div class="section-kicker">{safe_text(kicker)}</div>
                <div class="section-title">{safe_text(title)}</div>
            </div>
            <div class="section-meta">{safe_text(meta)}</div>
        </div>
        """),
        unsafe_allow_html=True,
    )


def metric_pill(label: str, value: str, missing: bool = False) -> str:
    missing_class = " missing" if missing else ""
    return f"<span class='metric{missing_class}'>{safe_text(label)}: {safe_text(value)}</span>"


def pitcher_card(team: dict[str, Any], starter: dict[str, Any]) -> str:
    metrics = [
        ("ERA", fmt_number(starter.get("era"), 2), starter.get("era") is None),
        ("xERA", fmt_number(starter.get("xera"), 2), starter.get("xera") is None),
        ("xwOBA", fmt_number(starter.get("xwoba"), 3), starter.get("xwoba") is None),
        ("WHIP", fmt_number(starter.get("whip"), 2), starter.get("whip") is None),
        ("K/9", fmt_number(starter.get("k9"), 1), starter.get("k9") is None),
        (
            "HardHit%",
            f"{fmt_number(starter.get('hard_hit_pct'), 1)}%",
            starter.get("hard_hit_pct") is None,
        ),
    ]
    metric_html = "".join(metric_pill(label, value, missing) for label, value, missing in metrics)

    logs = starter.get("last_three") or []
    if logs:
        rows = []
        for log in logs[:3]:
            opponent = str(log.get("opponent") or "—").replace("New York", "NY")
            rows.append(
                "<div class='start-row'>"
                f"<span>{safe_text(str(log.get('date', ''))[5:])} vs {safe_text(opponent)}</span>"
                f"<span>{safe_text(log.get('innings') or '—')} IP</span>"
                f"<span>{int(log.get('earned_runs') or 0)} ER</span>"
                f"<span>{int(log.get('strikeouts') or 0)} K</span>"
                "</div>"
            )
        starts_html = "".join(rows)
    else:
        starts_html = "<div class='data-note'>No completed MLB starts were returned.</div>"

    rest = starter.get("days_rest")
    rest_text = f"{rest} days rest" if rest is not None else "Rest unknown"
    return f"""
    <div class="pitcher-card">
        <div class="pitcher-name">
            <span>{safe_text(team.get('pitcher_name') or 'Starter TBD')}</span>
            <span class="record">{safe_text(starter.get('record') or '—')}</span>
        </div>
        <div class="metric-row">{metric_html}</div>
        <div class="mini-title">LAST 3 STARTS · {safe_text(rest_text)}</div>
        {starts_html}
    </div>
    """


def weather_text(weather: dict[str, Any], venue: dict[str, Any]) -> str:
    if weather.get("controlled"):
        return f"{venue.get('name', 'Venue')} · climate controlled"
    if not weather.get("available"):
        return f"{venue.get('name', 'Venue')} · weather unavailable"
    rain = float(weather.get("precip_probability") or 0)
    roof_note = " · roof decision uncertain" if weather.get("roof_uncertain") else ""
    return (
        f"{venue.get('name', 'Venue')} · {weather.get('temperature_f', 72):.0f}°F · "
        f"{weather.get('description', 'Forecast')} · wind {weather.get('wind_mph', 0):.0f} mph · "
        f"rain {rain:.0f}%{roof_note}"
    )


def lean_description(probability: float) -> str:
    if probability >= 0.64:
        return "a clear model lean"
    if probability >= 0.58:
        return "a moderate model lean"
    if probability >= 0.535:
        return "a small model lean"
    return "essentially a toss-up"


def agreement_description(gap: float) -> str:
    if gap <= 0.04:
        return "close agreement between the two model branches"
    if gap <= 0.085:
        return "some disagreement, but not enough to erase the lean"
    return "meaningful model disagreement, which lowers confidence"


def build_model_explanation(
    prediction: dict[str, Any], weather: dict[str, Any], lineup: dict[str, Any]
) -> dict[str, str]:
    """Translate the model inputs and intermediate estimates into plain English."""
    game = prediction["game"]
    away, home = game["away"], game["home"]
    target_side = prediction["target_side"]
    opponent_side = "home" if target_side == "away" else "away"
    target = game[target_side]
    opponent = game[opponent_side]
    target_probability = prediction["target_probability"]
    status = game["live"]["status"]

    if prediction.get("snapshot_state") == "untracked":
        summary = ("No forecast was saved before this game's scheduled first pitch. "
                   "The estimate below is not an original pregame pick and will not be added to the record.")
        short_summary = "Untracked estimate · excluded from the pregame record."
    elif prediction.get("pregame_locked") and status in {"LIVE", "FINAL"}:
        game_state_copy = (
            "The live score is displayed separately" if status == "LIVE"
            else "The final score is displayed separately"
        )
        summary = (
            f"This is the locked pregame forecast: {target['name']} at "
            f"{target_probability*100:.1f}%. {game_state_copy}, but the score, inning, outs "
            "and occupied bases are not fed back into this prediction. The pick is retained "
            "unchanged so its eventual win or loss can be graded honestly."
        )
        short_summary = (
            f"Locked pregame pick: {target['short_name']} {target_probability*100:.1f}% · "
            "live game state excluded."
        )
    elif status == "FINAL":
        summary = (
            f"This game is final. {target['name']} is shown as the result winner; the probability "
            "is no longer a pregame forecast."
        )
        short_summary = f"Final result favors {target['short_name']}."
    elif status == "LIVE":
        summary = (
            f"The live model makes {target['name']} {lean_description(target_probability)} at "
            f"{target_probability*100:.1f}%. It starts from the current score, inning, outs and "
            "occupied bases, then simulates the innings remaining."
        )
        short_summary = (
            f"{target['short_name']} {target_probability*100:.1f}% live win probability based on "
            "the current score and inning state."
        )
    else:
        summary = (
            f"{target['name']} is {lean_description(target_probability)} at "
            f"{target_probability*100:.1f}%. The run model projects {away['short_name']} "
            f"{prediction['projected_away_runs']:.2f} and {home['short_name']} "
            f"{prediction['projected_home_runs']:.2f}; that is an expected margin of "
            f"{abs(prediction['projected_home_runs']-prediction['projected_away_runs']):.2f} runs, "
            "not a guarantee of the final score."
        )
        short_summary = (
            f"{target['short_name']} {target_probability*100:.1f}% · projected runs "
            f"{away['short_name']} {prediction['projected_away_runs']:.2f}, "
            f"{home['short_name']} {prediction['projected_home_runs']:.2f}."
        )

    simulation_target = (
        1.0 - prediction["simulation_home_probability"]
        if target_side == "away"
        else prediction["simulation_home_probability"]
    )
    record_target = (
        1.0 - prediction["record_home_probability"]
        if target_side == "away"
        else prediction["record_home_probability"]
    )
    simulation = (
        f"In {prediction['simulations']:,} score simulations, {target['short_name']} won "
        f"{simulation_target*100:.1f}%. A separate record-and-home-field baseline gives "
        f"{target['short_name']} {record_target*100:.1f}%. Their "
        f"{prediction['model_agreement_gap']*100:.1f}-point gap means "
        f"{agreement_description(prediction['model_agreement_gap'])}. The final pregame "
        "probability blends both estimates and shrinks the result toward 50% to reduce false precision."
    )
    if prediction.get("snapshot_state") == "legacy":
        simulation = ("This earlier build saved the original pick, probability and projected score, "
                      "but not the full simulation inputs. Those original values are retained. "
                      "The other panels show current context, not a reconstruction of the original model.")
    branch_short = (
        f"Score simulations: {simulation_target*100:.1f}% · record/home baseline: "
        f"{record_target*100:.1f}% · disagreement: "
        f"{prediction['model_agreement_gap']*100:.1f} points."
    )

    away_offense = prediction["away_offense"]
    home_offense = prediction["home_offense"]
    offense = (
        f"{away['short_name']}: {away_offense['strength']*100:.0f} offense index, "
        f"{away_offense['season_rpg']:.2f} season runs/game, "
        f"{away_offense['recent_rpg']:.2f} recent-window runs/game and "
        f"{away_offense['ops']:.3f} OPS. {home['short_name']}: "
        f"{home_offense['strength']*100:.0f} index, {home_offense['season_rpg']:.2f} season "
        f"runs/game, {home_offense['recent_rpg']:.2f} recent-window runs/game and "
        f"{home_offense['ops']:.3f} OPS. An index of 100 is league average, and recent form "
        "is intentionally regressed so a short hot streak cannot dominate the pick."
    )

    away_starter = prediction["away_starter"]
    home_starter = prediction["home_starter"]
    starters = (
        f"{away.get('pitcher_name') or 'Away starter TBD'} grades "
        f"{away_starter['quality_ra9']:.2f} in the ERA/FIP/xERA/WHIP blend over an expected "
        f"{away_starter['expected_ip']:.1f} IP; {home.get('pitcher_name') or 'Home starter TBD'} "
        f"grades {home_starter['quality_ra9']:.2f} over {home_starter['expected_ip']:.1f} IP. "
        "Lower is better. The blend is pulled toward league average when the sample is small, "
        "and rest plus recent workload can reduce expected innings."
    )

    away_bullpen = prediction["away_bullpen"]
    home_bullpen = prediction["home_bullpen"]
    bullpen = (
        f"{away['short_name']} relief grade: {away_bullpen['quality_ra9']:.2f} blended RA9 "
        f"(ERA {fmt_number(away_bullpen.get('era'), 2)}, FIP {fmt_number(away_bullpen.get('fip'), 2)}). "
        f"{home['short_name']} relief grade: {home_bullpen['quality_ra9']:.2f} "
        f"(ERA {fmt_number(home_bullpen.get('era'), 2)}, FIP {fmt_number(home_bullpen.get('fip'), 2)}). "
        "Lower is better. This measures relief performance, but it does not yet know which "
        "individual relievers are unavailable after recent usage."
    )

    environment_delta = (prediction["shared_environment_factor"] - 1.0) * 100.0
    if environment_delta >= 2:
        environment_direction = f"raises the expected run environment about {environment_delta:.1f}%"
    elif environment_delta <= -2:
        environment_direction = f"reduces the expected run environment about {abs(environment_delta):.1f}%"
    else:
        environment_direction = "is approximately neutral for scoring"
    environment = (
        f"The {prediction['park_factor']:.3f} park factor and "
        f"{prediction['weather_factor']:.3f} weather factor combine to "
        f"{prediction['shared_environment_factor']:.3f}, which {environment_direction}. "
        f"Current context: {weather_text(weather, game['venue'])}."
    )

    away_confirmed = bool((lineup.get("away") or {}).get("confirmed"))
    home_confirmed = bool((lineup.get("home") or {}).get("confirmed"))
    if away_confirmed and home_confirmed:
        lineup_text = "both batting orders are confirmed"
    elif away_confirmed:
        lineup_text = f"only the {away['short_name']} batting order is confirmed"
    elif home_confirmed:
        lineup_text = f"only the {home['short_name']} batting order is confirmed"
    else:
        lineup_text = "neither batting order is confirmed yet"
    confidence = (
        f"Data quality is {prediction['quality_score']}/100 ({prediction['quality_label']}); "
        f"{lineup_text}. Confidence is a data-completeness label, not the chance the wager wins."
    )

    value = prediction.get("value")
    target_fair_odds = (
        prediction["fair_away_odds"] if target_side == "away" else prediction["fair_home_odds"]
    )
    if value:
        market = (
            f"Best measured comparison is {value['team']} {fmt_odds(value['price'])}: model "
            f"{value['model_probability']*100:.1f}% vs no-vig market "
            f"{value['market_probability']*100:.1f}%, a {value['edge']*100:+.1f}-point edge "
            f"and {value['expected_roi']*100:+.1f}% modeled ROI. "
            f"It {'passes' if value.get('qualifies') else 'does not pass'} the app's minimum "
            "edge/data-quality filter."
        )
        if prediction.get("snapshot_state") == "saved":
            market = "At the original forecast capture: " + market + " These are saved prices, not a current offer."
        market_short = (
            f"{value['team']} {fmt_odds(value['price'])} · edge {value['edge']*100:+.1f} points · "
            f"{'qualifies' if value.get('qualifies') else 'below filter'}."
        )
    else:
        market = (
            f"The model's fair moneyline for {target['name']} is {fmt_odds(target_fair_odds)}. "
            "No verified sportsbook price is connected, so this is a matchup projection only; "
            "the app is not claiming that a bet has positive value."
        )
        market_short = f"Fair line {fmt_odds(target_fair_odds)} · sportsbook price not connected."

    return {
        "summary": summary,
        "short_summary": short_summary,
        "simulation": simulation,
        "branch_short": branch_short,
        "offense": offense,
        "starters": starters,
        "bullpen": bullpen,
        "environment": environment,
        "confidence": confidence,
        "market": market,
        "market_short": market_short,
        "changes": " ".join(prediction.get("invalidation") or []),
        "opponent": opponent["name"],
    }


def render_game(
    prediction: dict[str, Any], weather: dict[str, Any], lineup: dict[str, Any]
) -> str:
    game = prediction["game"]
    away, home = game["away"], game["home"]
    explanation = build_model_explanation(prediction, weather, lineup)
    live = game["live"]
    status = live["status"]
    status_class = {
        "LIVE": "status-live",
        "FINAL": "status-final",
        "PREVIEW": "status-preview",
    }[status]
    status_label = live["status_label"]
    if status in {"LIVE", "FINAL"}:
        status_label = f"{status_label} · {live['away_runs']}-{live['home_runs']}"

    game_dt = game.get("game_datetime_utc")
    start_text = game_dt.astimezone(ET).strftime("%-I:%M %p ET") if game_dt else "Time TBD"
    context = f"{start_text} · {weather_text(weather, game['venue'])}"
    if game.get("doubleheader"):
        context += f" · Doubleheader G{game.get('game_number', 1)}"

    away_pct = prediction["away_probability"] * 100.0
    home_pct = prediction["home_probability"] * 100.0
    if status == "FINAL":
        pick_prefix = "RESULT"
    elif status == "LIVE":
        pick_prefix = "LIVE MODEL LEAN"
    else:
        pick_prefix = "MODEL LEAN"

    support = prediction.get("support") or []
    risks = prediction.get("risks") or []
    support_html = "".join(
        f"<div class='rationale-line'><strong>Why:</strong> {safe_text(reason)}</div>"
        for reason in support[:2]
    )
    risk_html = "".join(
        f"<div class='rationale-line'><strong>Risk:</strong> {safe_text(reason)}</div>"
        for reason in risks[:1]
    )

    value = prediction.get("value")
    value_label = "Market check" if value else "Fair-price context"
    market_html = (
        f"<div class='rationale-line'><strong>{safe_text(value_label)}:</strong> "
        f"{safe_text(explanation['market_short'])}</div>"
    )

    rationale = f"""
    <div class="rationale-card">
        <div class="rationale-title">Why the Model Leans {safe_text(prediction['target_name'])}</div>
        <div class="rationale-line"><strong>Verdict:</strong> {safe_text(explanation['short_summary'])}</div>
        <div class="rationale-line"><strong>Model mix:</strong> {safe_text(explanation['branch_short'])}</div>
        {support_html}
        {risk_html}
        {market_html}
        <div class="source-line">DATA QUALITY {prediction['quality_score']}/100 · {safe_text(prediction['quality_label'])} · EXPAND THE BREAKDOWN BELOW FOR MORE</div>
    </div>
    """

    markup = f"""
    <div class="game-shell" style="{matchup_style(game)}">
        <div class="game-top">
            <div>
                <div class="matchup">
                    <span class="team-chip"><img class="team-logo" src="{safe_text(away['logo'])}" alt="">{safe_text(away['name'])}</span>
                    <span class="at-mark">@</span>
                    <span class="team-chip"><img class="team-logo" src="{safe_text(home['logo'])}" alt="">{safe_text(home['name'])}</span>
                </div>
                <div class="game-context">{safe_text(context)}</div>
            </div>
            <span class="status-pill {status_class}">{safe_text(status_label)}</span>
        </div>

        <div class="pick-row">
            <span class="pick-pill">{pick_prefix}: {safe_text(prediction['target_name'])}</span>
            <span class="pick-prob">{prediction['target_probability']*100:.1f}% model probability</span>
            <span class="quality-pill">Fair ML {fmt_odds(prediction['fair_home_odds'] if prediction['target_side']=='home' else prediction['fair_away_odds'])}</span>
        </div>

        <div class="prob-grid">
            <div>
                <div class="prob-label"><span>{safe_text(away['short_name'])}</span><strong>{away_pct:.1f}%</strong></div>
                <div class="prob-track"><span class="prob-fill away-fill" style="width:{away_pct:.1f}%"></span></div>
            </div>
            <div>
                <div class="prob-label"><span>{safe_text(home['short_name'])}</span><strong>{home_pct:.1f}%</strong></div>
                <div class="prob-track"><span class="prob-fill home-fill" style="width:{home_pct:.1f}%"></span></div>
            </div>
        </div>

        <div class="analysis-grid">
            {pitcher_card(away, prediction['away_starter'])}
            {pitcher_card(home, prediction['home_starter'])}
            {rationale}
        </div>
    </div>
    """
    # Streamlit's Markdown parser can treat indented HTML after a blank line as
    # a fenced code block. Collapse the card to one continuous HTML line so all
    # nested sections render as HTML on every supported Streamlit version.
    return "".join(line.strip() for line in markup.splitlines())


def scoreboard_card(prediction: dict[str, Any]) -> str:
    """Build a compact, clickable scoreboard card for the top game center."""
    game = prediction["game"]
    away, home = game["away"], game["home"]
    live = game["live"]
    status = live["status"]
    game_dt = game.get("game_datetime_utc")
    start_text = game_dt.astimezone(ET).strftime("%-I:%M %p") if game_dt else "TBD"

    if status == "LIVE":
        card_class = "is-live"
        badge_class = "live"
        badge_text = f"Live · {live.get('status_label') or 'In progress'}"
        side_note = f"{int(live.get('outs') or 0)} outs"
        away_value = str(int(live.get("away_runs") or 0))
        home_value = str(int(live.get("home_runs") or 0))
        footer_label = "Live model lean"
    elif status == "FINAL":
        card_class = "is-final"
        badge_class = "final"
        badge_text = "Final"
        side_note = "Completed"
        away_value = str(int(live.get("away_runs") or 0))
        home_value = str(int(live.get("home_runs") or 0))
        footer_label = "Winner"
    else:
        card_class = "is-preview"
        badge_class = "preview"
        badge_text = "Upcoming"
        side_note = f"{start_text} ET"
        away_value = f"{prediction['away_probability']*100:.0f}%"
        home_value = f"{prediction['home_probability']*100:.0f}%"
        footer_label = "Model lean"

    away_record = f"{int(away.get('wins') or 0)}-{int(away.get('losses') or 0)}"
    home_record = f"{int(home.get('wins') or 0)}-{int(home.get('losses') or 0)}"
    matchup_target = prediction["target_name"]
    matchup_probability = prediction["target_probability"] * 100.0

    return f"""
    <a class="score-card {card_class}" style="{matchup_style(game)}" href="#game-{int(game['game_pk'])}">
        <div class="score-card-top">
            <span class="score-card-status {badge_class}">{safe_text(badge_text)}</span>
            <span class="score-card-time">{safe_text(side_note)}</span>
        </div>
        <div class="score-team-row">
            <img class="score-team-logo" src="{safe_text(away['logo'])}" alt="">
            <div class="score-team-copy">
                <div class="score-team-name">{safe_text(away['name'])}</div>
                <div class="score-team-record">{safe_text(away_record)} · {safe_text(away.get('pitcher_name') or 'Starter TBD')}</div>
            </div>
            <span class="score-team-value">{safe_text(away_value)}</span>
        </div>
        <div class="score-team-row">
            <img class="score-team-logo" src="{safe_text(home['logo'])}" alt="">
            <div class="score-team-copy">
                <div class="score-team-name">{safe_text(home['name'])}</div>
                <div class="score-team-record">{safe_text(home_record)} · {safe_text(home.get('pitcher_name') or 'Starter TBD')}</div>
            </div>
            <span class="score-team-value">{safe_text(home_value)}</span>
        </div>
        <div class="score-card-footer">
            <div>
                <div class="score-model-label">{safe_text(footer_label)}</div>
                <div class="score-model-pick">{safe_text(matchup_target)} · {matchup_probability:.1f}%</div>
            </div>
            <div class="score-card-actions">
                <span class="quality-badge {confidence_class(prediction['quality_label'])}" title="Data completeness, not win probability">{safe_text(prediction['quality_label'])} DATA</span>
                <span class="score-open">DETAILS ↓</span>
            </div>
        </div>
    </a>
    """


def scoreboard_rail(predictions: list[dict[str, Any]], empty_message: str) -> str:
    if not predictions:
        return f"<div class='empty-scoreboard'>{safe_text(empty_message)}</div>"
    cards = "".join(scoreboard_card(prediction) for prediction in predictions)
    markup = f"<div class='scoreboard-rail'>{cards}</div>"
    return "".join(line.strip() for line in markup.splitlines())


def render_native_score_card(prediction: dict[str, Any]) -> None:
    """Render a compact sports-app score tile using stable Streamlit widgets."""
    game = prediction["game"]
    away, home = game["away"], game["home"]
    live = game["live"]
    status = live["status"]
    game_dt = game.get("game_datetime_utc")
    start_text = game_dt.astimezone(ET).strftime("%-I:%M %p ET") if game_dt else "Time TBD"

    if status == "LIVE":
        outs = int(live.get("outs") or 0)
        status_label = "Live"
        status_class = "live"
        status_detail = (
            f"{live.get('status_label') or 'In progress'} · "
            f"{outs} {'out' if outs == 1 else 'outs'}"
        )
        away_value = str(int(live.get("away_runs") or 0))
        home_value = str(int(live.get("home_runs") or 0))
    elif status == "FINAL":
        status_label = "Final"
        status_class = "final"
        status_detail = "Completed"
        away_value = str(int(live.get("away_runs") or 0))
        home_value = str(int(live.get("home_runs") or 0))
    else:
        status_label = "Upcoming"
        status_class = "upcoming"
        status_detail = start_text
        away_value = "—"
        home_value = "—"

    away_record = f"{int(away.get('wins') or 0)}-{int(away.get('losses') or 0)}"
    home_record = f"{int(home.get('wins') or 0)}-{int(home.get('losses') or 0)}"
    target = game[prediction["target_side"]]
    score_gauge = gauge_markup(
        prediction["target_probability"] * 100.0,
        "%",
        kind="mini-gauge",
        tone=probability_tone(prediction["target_probability"]),
        display=f"{prediction['target_probability']*100:.0f}",
    )
    with st.container(border=True, key=f"score_card_{game['game_pk']}"):
        st.markdown(
            html_block(f"""
            <div class="score-tile">
                <div class="score-tile-head">
                    <span class="score-tile-status {status_class}">{safe_text(status_label)}</span>
                    <span class="score-tile-time">{safe_text(status_detail)}</span>
                </div>
                <div class="score-tile-team">
                    <img src="{safe_text(away['logo'])}" alt="" loading="lazy">
                    <div>
                        <div class="score-tile-team-name">{safe_text(away['short_name'])}</div>
                        <div class="score-tile-team-record">{safe_text(away_record)}</div>
                    </div>
                    <span class="score-tile-value">{safe_text(away_value)}</span>
                </div>
                <div class="score-tile-team">
                    <img src="{safe_text(home['logo'])}" alt="" loading="lazy">
                    <div>
                        <div class="score-tile-team-name">{safe_text(home['short_name'])}</div>
                        <div class="score-tile-team-record">{safe_text(home_record)}</div>
                    </div>
                    <span class="score-tile-value">{safe_text(home_value)}</span>
                </div>
                <div class="score-tile-model">
                    <div class="score-model-copy">
                        <span>{safe_text(forecast_lock_label(prediction))}</span>
                        <strong>{safe_text(target['short_name'])}</strong>
                    </div>
                    {score_gauge}
                </div>
            </div>
            """),
            unsafe_allow_html=True,
        )
        analysis_is_open = st.session_state.get("open_game_pk") == game["game_pk"]
        st.button(
            "Close details" if analysis_is_open else "Open matchup",
            key=f"game_center_toggle_{game['game_pk']}",
            on_click=toggle_game_analysis,
            args=(game["game_pk"],),
            type="secondary",
            use_container_width=True,
        )


def render_score_card_grid(predictions: list[dict[str, Any]], empty_message: str) -> None:
    if not predictions:
        st.info(empty_message)
        return
    for row_start in range(0, len(predictions), 4):
        columns = st.columns(4)
        for column, prediction in zip(columns, predictions[row_start : row_start + 4]):
            with column:
                render_native_score_card(prediction)


def render_game_center(predictions: list[dict[str, Any]], selected_date: date) -> None:
    live_games = [p for p in predictions if p["game"]["live"]["status"] == "LIVE"]
    upcoming_games = [p for p in predictions if p["game"]["live"]["status"] == "PREVIEW"]
    final_games = [p for p in predictions if p["game"]["live"]["status"] == "FINAL"]

    st.markdown(native_matchup_accents(predictions), unsafe_allow_html=True)
    section_heading(
        "Live scoreboard",
        "Score Center",
        f"{selected_date.strftime('%A, %B %-d')} · {len(predictions)} games · "
        f"{len(live_games)} live · {len(upcoming_games)} upcoming · {len(final_games)} final",
    )

    groups = [
        (f"Live ({len(live_games)})", live_games, "No games are live right now."),
        (
            f"Upcoming ({len(upcoming_games)})",
            upcoming_games,
            "No upcoming games remain on this slate.",
        ),
        (f"Final ({len(final_games)})", final_games, "No games are final yet."),
    ]
    if not live_games:
        groups = [groups[1], groups[2], groups[0]]
    tabs = st.tabs([label for label, _, _ in groups])
    for tab, (_, games, empty_message) in zip(tabs, groups):
        with tab:
            render_score_card_grid(games, empty_message)


def _tracker_rate_text(stats: dict[str, Any]) -> str:
    rate = stats.get("win_rate")
    return f"{float(rate) * 100.0:.1f}%" if rate is not None else "—"


def _tracker_record_tone(stats: dict[str, Any]) -> str:
    rate = stats.get("win_rate")
    if rate is None:
        return "neutral"
    if float(rate) >= 0.55:
        return "good"
    if float(rate) < 0.50:
        return "bad"
    return "neutral"


def tracker_bucket_markup(label: str, stats: dict[str, Any], subtitle: str) -> str:
    tone = _tracker_record_tone(stats)
    decisions = int(stats["decisions"])
    sample_text = f"{decisions} graded {'pick' if decisions == 1 else 'picks'}"
    if int(stats["pending"]):
        sample_text += f" · {int(stats['pending'])} pending"
    return f"""
    <div class="tracker-bucket {tone}">
        <div class="tracker-bucket-label">{safe_text(label)}</div>
        <div class="tracker-bucket-record">{int(stats['wins'])}–{int(stats['losses'])}</div>
        <div class="tracker-bucket-rate">{safe_text(_tracker_rate_text(stats))} win rate</div>
        <div class="tracker-bucket-note">{safe_text(subtitle)} · {safe_text(sample_text)}</div>
    </div>
    """


def tracker_pick_log_markup(entries: Iterable[dict[str, Any]]) -> str:
    rows: list[str] = []
    for entry in sorted(entries, key=_tracker_sort_key, reverse=True):
        result = str(entry.get("result") or "PENDING").upper()
        result_class = result.lower()
        probability = float(entry.get("target_probability") or 0.0) * 100.0
        away_runs = entry.get("final_away_runs")
        home_runs = entry.get("final_home_runs")
        if away_runs is not None and home_runs is not None:
            game_state = (
                f"{entry.get('away_short_name') or 'Away'} {int(away_runs)} · "
                f"{entry.get('home_short_name') or 'Home'} {int(home_runs)}"
            )
        else:
            game_state = str(entry.get("status_label") or "Awaiting first pitch")
        date_text = str(entry.get("game_date") or "")
        try:
            date_text = date.fromisoformat(date_text).strftime("%b %-d, %Y")
        except ValueError:
            pass
        manual_text = " · corrected" if entry.get("manual_override") else ""
        rows.append(
            f"""
            <div class="tracker-log-row {result_class}">
                <div class="tracker-log-matchup">
                    <div class="tracker-log-logos">
                        <img src="{safe_text(entry.get('away_logo'))}" alt="" loading="lazy">
                        <img src="{safe_text(entry.get('home_logo'))}" alt="" loading="lazy">
                    </div>
                    <div>
                        <div class="tracker-log-teams">{safe_text(entry.get('away_short_name'))} at {safe_text(entry.get('home_short_name'))}</div>
                        <div class="tracker-log-date">{safe_text(date_text)}</div>
                    </div>
                </div>
                <div class="tracker-log-pick">
                    <img src="{safe_text(entry.get('target_logo'))}" alt="" loading="lazy">
                    <div><span>Locked pick</span><strong>{safe_text(entry.get('target_short_name'))} {probability:.1f}%</strong></div>
                </div>
                <div class="tracker-log-score"><span>Official score</span><strong>{safe_text(game_state)}</strong></div>
                <div class="tracker-result {result_class}">{safe_text(result)}{safe_text(manual_text)}</div>
            </div>
            """
        )
    return "".join(rows)


def render_model_lab(payload: dict[str, Any]) -> None:
    assessment = evaluate_frozen_forecasts(payload["picks"].values())
    st.markdown("**Measured performance—not promised accuracy**")
    st.caption("Uses saved probabilities and official win/loss grades. Manual corrections, pending games and voids are excluded from the probability checks.")
    if not assessment["n"]:
        st.info("The first official finals will start the probability checks. No historical picks are invented.")
    else:
        columns = st.columns(3)
        columns[0].metric("Forecast average", f"{assessment['mean_probability']:.1%}")
        columns[1].metric("Actual win rate", f"{assessment['win_rate']:.1%}")
        columns[2].metric("Probability error · Brier", f"{assessment['brier']:.4f}")
        st.caption(
            f"{assessment['n']} official decisions · 95% win-rate interval "
            f"{assessment['interval_low']:.1%}–{assessment['interval_high']:.1%}. "
            "This descriptive interval assumes independent games; it is not a future win-rate guarantee. "
            "Lower Brier error is better; assigning 50% to every game scores 0.2500. "
            "That is a simple reference—not proof of beating sportsbook prices."
        )
        if assessment["n"] < 200:
            st.info("Early sample: keep collecting games. A few good or bad days do not establish an accurate 70% model.")
    st.markdown("**Stronger-setup trial**")
    trial = assessment["shortlisted"]
    st.write(f"{trial['wins']} wins · {trial['losses']} losses · {trial['pending']} pending")
    st.caption(
        "Fixed rule for new Build 24 captures: at least 60% model probability, data quality 80/100, "
        "both starters with usable stats and 80 batters faced, and model disagreement no greater than 10 points. "
        "This is an experimental research shortlist, not validated betting advice. Every game still remains in the main record. "
        "Older picks are not retrospectively labeled to improve this trial's results."
    )
    st.markdown("**Future-game comparisons**")
    if assessment["comparisons"]:
        st.dataframe([
            {"Alternative": row["name"], "Same games": row["n"],
             "Main model error": round(row["main_brier"], 4),
             "Alternative error": round(row["candidate_brier"], 4)}
            for row in assessment["comparisons"]
        ], hide_index=True, use_container_width=True)
    else:
        st.caption("Comparisons begin when newly saved Build 24 forecasts finish. Older inputs were not recorded, so they are not backfilled.")
    st.caption(
        "The calibration challenger waits for 200 official results from this model version across at least 14 dates. "
        "It learns only from results available before each new forecast, then is scored on later games. "
        "It never replaces the published probability automatically. Lineups are currently a completeness check, "
        "not yet a batter-by-batter offensive adjustment."
    )


def render_full_tracker(payload: dict[str, Any], storage_status: str) -> None:
    entries = list(payload["picks"].values())
    stats = tracker_record(entries)
    rate_value = float(stats["win_rate"] or 0.0) * 100.0
    rate_gauge = gauge_markup(
        rate_value,
        "win rate",
        kind="tracker-win-gauge",
        tone="good" if stats["win_rate"] is not None and stats["win_rate"] >= 0.5 else "ice",
        display=_tracker_rate_text(stats),
    )

    with st.container(key="tracker_panel"):
        st.markdown(
            html_block(f"""
            <div class="tracker-panel-head">
                <div>
                    <div class="tracker-panel-kicker">Verified model history</div>
                    <div class="tracker-panel-title">Performance Tracker</div>
                    <div class="tracker-panel-subtitle">Saved pregame forecasts · Official MLB results · Manual corrections are labeled.</div>
                </div>
                <div class="tracker-panel-count">{len(entries)} tracked {'pick' if len(entries) == 1 else 'picks'}</div>
            </div>
            """),
            unsafe_allow_html=True,
        )

        feedback = st.session_state.pop("tracker_feedback", None)
        if feedback:
            message_type, message = feedback
            if message_type == "success":
                st.success(message)
            else:
                st.error(message)
        if storage_status != "ready":
            st.error(storage_status)

        overview_tab, confidence_tab, log_tab, lab_tab = st.tabs(
            ["Overview", "Confidence splits", "Pick log", "Model lab"]
        )

        with overview_tab:
            st.markdown(
                html_block(f"""
                <div class="tracker-overview">
                    <div class="tracker-record-hero {_tracker_record_tone(stats)}">
                        <div>
                            <div class="tracker-record-eyebrow">Official record</div>
                            <div class="tracker-record-big">{int(stats['wins'])}–{int(stats['losses'])}</div>
                            <div class="tracker-record-copy">Wins and losses only. Voids never affect the percentage.</div>
                        </div>
                        {rate_gauge}
                    </div>
                    <div class="tracker-overview-grid">
                        <div class="tracker-overview-card"><span>Last 10</span><strong>{safe_text(stats['last_ten'])}</strong><small>Most recent decisions</small></div>
                        <div class="tracker-overview-card"><span>Current streak</span><strong>{safe_text(stats['streak'])}</strong><small>Consecutive results</small></div>
                        <div class="tracker-overview-card pending"><span>Pending</span><strong>{int(stats['pending'])}</strong><small>Waiting for a final</small></div>
                        <div class="tracker-overview-card"><span>Voids</span><strong>{int(stats['void'])}</strong><small>Excluded from record</small></div>
                    </div>
                </div>
                """),
                unsafe_allow_html=True,
            )
            if not entries:
                st.info(
                    "Tracking starts when the app sees a matchup before first pitch. "
                    "It will not invent or backfill older picks."
                )

        with confidence_tab:
            confidence_groups = tracker_group_records(
                entries,
                tracker_confidence_group,
                ("50–54.9%", "55–59.9%", "60%+"),
            )
            quality_groups = tracker_group_records(
                entries,
                tracker_quality_group,
                ("Higher quality", "Solid quality", "Limited quality"),
            )
            confidence_markup = "".join(
                tracker_bucket_markup(label, group_stats, "Locked win probability")
                for label, group_stats in confidence_groups
            )
            quality_markup = "".join(
                tracker_bucket_markup(label, group_stats, "Pregame data completeness")
                for label, group_stats in quality_groups
            )
            st.markdown(
                html_block(f"""
                <div class="tracker-split-heading"><strong>By model probability</strong><span>Shows where the model has actually performed best.</span></div>
                <div class="tracker-bucket-grid">{confidence_markup}</div>
                <div class="tracker-split-heading quality"><strong>By data quality</strong><span>Data quality measures completeness, not certainty.</span></div>
                <div class="tracker-bucket-grid">{quality_markup}</div>
                """),
                unsafe_allow_html=True,
            )

        with lab_tab:
            render_model_lab(payload)

        with log_tab:
            if entries:
                st.markdown(
                    html_block(f"<div class='tracker-log'>{tracker_pick_log_markup(entries)}</div>"),
                    unsafe_allow_html=True,
                )
            else:
                st.info("No picks have been captured yet. Today's pregame slate will appear here automatically.")

        st.markdown(
            html_block("""
            <div class="tracker-tools-heading">
                <div><strong>Tracker controls</strong><span>Keep a backup before replacing or redeploying the app.</span></div>
            </div>
            """),
            unsafe_allow_html=True,
        )
        backup_column, csv_column, correction_column = st.columns([1, 1, 1.15])
        with backup_column:
            st.download_button(
                "Download tracker backup",
                data=tracker_json_bytes(payload),
                file_name="mlb_quant_tracker_backup.json",
                mime="application/json",
                key="tracker_backup_download",
                use_container_width=True,
            )
        with csv_column:
            st.download_button(
                "Export pick log CSV",
                data=tracker_csv_bytes(payload),
                file_name="mlb_quant_pick_log.csv",
                mime="text/csv",
                key="tracker_csv_download",
                use_container_width=True,
            )
        with correction_column:
            with st.popover("Corrections & restore", use_container_width=True):
                can_edit = tracker_owner_access()
                if entries:
                    entry_labels = {
                        (
                            f"{entry.get('game_date', '')} · {entry.get('away_short_name', 'Away')} at "
                            f"{entry.get('home_short_name', 'Home')} · {entry.get('result', 'PENDING')} · Game {entry['game_pk']}"
                        ): int(entry["game_pk"])
                        for entry in sorted(entries, key=_tracker_sort_key, reverse=True)
                    }
                    selected_entry_label = st.selectbox(
                        "Tracked game",
                        list(entry_labels),
                        key="tracker_correction_game",
                    )
                    corrected_result = st.selectbox(
                        "Recorded result",
                        ["Auto (official final)", "Win", "Loss", "Void", "Pending"],
                        key="tracker_correction_result",
                    )
                    if st.button("Save correction", key="tracker_save_correction", use_container_width=True, disabled=not can_edit) and can_edit:
                        result_value = "AUTO" if corrected_result.startswith("Auto") else corrected_result.upper()
                        saved, message = apply_tracker_override(
                            entry_labels[selected_entry_label], result_value
                        )
                        st.session_state["tracker_feedback"] = (
                            "success" if saved else "error",
                            "Tracker result updated." if saved else message,
                        )
                        st.rerun()
                    st.divider()
                uploaded_backup = st.file_uploader(
                    "Restore JSON backup",
                    type=["json"],
                    key="tracker_restore_upload",
                    disabled=not can_edit,
                    help="Restoring merges saved games by ID, keeps the earliest frozen pick, and retains newer games and existing manual corrections.",
                )
                if st.button(
                    "Restore selected backup",
                    key="tracker_restore_button",
                    disabled=uploaded_backup is None or not can_edit,
                    use_container_width=True,
                ) and can_edit:
                    restored, message = restore_prediction_tracker(uploaded_backup.getvalue())
                    st.session_state["tracker_feedback"] = (
                        "success" if restored else "error",
                        message,
                    )
                    st.rerun()
        st.caption(
            "Automatic grading uses official MLB final scores. Manual corrections are visibly marked in the pick log."
        )
        if st.button("Check results now", key="tracker_check_results", use_container_width=True):
            cached_tracker_official_results.clear()
            st.rerun()
        st.caption(
            "Checks all pending game IDs, including earlier dates, every 60 seconds while open. "
            "After the app sleeps, results catch up when it is reopened. "
            "App-local storage can reset on redeployment; keep a downloaded backup."
        )


def render_tracker_summary(payload: dict[str, Any], storage_status: str) -> None:
    entries = list(payload["picks"].values())
    stats = tracker_record(entries)
    with st.container(border=True, key="tracker_summary"):
        summary_column, action_column = st.columns([6, 1.25], vertical_alignment="center")
        with summary_column:
            st.markdown(
                html_block(f"""
                <div class="tracker-strip">
                    <div class="tracker-strip-brand">
                        <span>Model record</span>
                        <strong>{int(stats['wins'])}–{int(stats['losses'])}</strong>
                    </div>
                    <div class="tracker-strip-metrics">
                        <div><span>Win rate</span><strong>{safe_text(_tracker_rate_text(stats))}</strong></div>
                        <div><span>Last 10</span><strong>{safe_text(stats['last_ten'])}</strong></div>
                        <div><span>Streak</span><strong>{safe_text(stats['streak'])}</strong></div>
                        <div class="pending"><span>Pending</span><strong>{int(stats['pending'])}</strong></div>
                    </div>
                </div>
                """),
                unsafe_allow_html=True,
            )
        with action_column:
            st.button(
                "Close tracker" if st.session_state.get("show_tracker_dashboard") else "View full tracker",
                key="tracker_dashboard_toggle",
                on_click=toggle_tracker_dashboard,
                use_container_width=True,
            )
    if storage_status != "ready":
        st.warning(storage_status)
    sync_info = payload.get("result_sync") or {}
    checked_at = _parse_utc(str(sync_info.get("checked_at_et") or ""))
    if checked_at:
        st.caption(
            f"Results last checked {checked_at.astimezone(ET).strftime('%b %-d, %-I:%M:%S %p ET')} "
            "· All saved dates · Auto-check every 60 seconds while open"
        )
    elif stats["pending"]:
        st.caption("Pending picks are saved. An official-result check is due.")
    if st.session_state.get("show_tracker_dashboard"):
        render_full_tracker(payload, storage_status)


def dashboard_refresh_due(now: datetime, last_rendered: datetime | None, calendar_day: str) -> bool:
    return (calendar_day != now.date().isoformat()
            or last_rendered is None or (now - last_rendered).total_seconds() >= 60)


@st.fragment(run_every=30)
def render_live_tracker(capture_status: str = "ready", *, page_started_at: str | None = None) -> None:
    """Refresh the tracker independently of slate date, predictions and widgets."""
    now = datetime.now(ET)
    if st.session_state.get("_tracker_page_token") != page_started_at or not st.session_state.get("_dashboard_rendered_at"):
        st.session_state["_tracker_page_token"] = page_started_at
        st.session_state["_dashboard_rendered_at"] = _tracker_timestamp(now)
    elif dashboard_refresh_due(now, _parse_utc(st.session_state["_dashboard_rendered_at"]),
                               str(st.session_state.get("calendar_day") or now.date().isoformat())):
        # A full rerun also refreshes scores and captures the next day's slate.
        # The new token prevents slow first loads from entering a rerun loop.
        st.rerun()
    remote_status = sync_remote_tracker(write=False)
    payload, status = sync_prediction_tracker([], datetime.now(ET))
    if tracker_sync_can_publish(payload, status):
        pushed = sync_remote_tracker(write=True)
        remote_status = pushed if pushed != "not configured" else remote_status
    if capture_status != "ready" and status == "ready":
        status = capture_status
    render_tracker_summary(payload, status)
    if remote_status not in {"ready", "not configured"}:
        st.warning(remote_status)
    if remote_status == "not configured":
        st.caption("Automatic checks run while this page is open. Overnight worker: not connected yet.")
    elif remote_status == "ready":
        st.caption("Shared tracker connected. The overnight schedule must also be enabled in GitHub Actions.")
        worker_at = _parse_utc(str(payload.get("worker_last_run_at_et") or ""))
        if worker_at:
            st.caption(f"Background worker last checked {worker_at.astimezone(ET).strftime('%b %-d, %-I:%M %p ET')}")
            if (datetime.now(ET) - worker_at).total_seconds() > 45 * 60:
                st.warning("The background worker has not checked in for over 45 minutes. Review its GitHub Actions run; this page continues checking saved results.")
        else:
            st.caption("No background-worker check-in has been recorded yet.")


def slate_insight_card(
    prediction: dict[str, Any], icon: str, label: str, value: str, detail: str
) -> str:
    game = prediction["game"]
    return f"""
    <a class="insight-card" style="{matchup_style(game)}" href="#game-{int(game['game_pk'])}">
        <div class="insight-top"><span>{safe_text(icon)}</span><span>{safe_text(label)}</span></div>
        <div class="insight-value">{safe_text(value)}</div>
        <div class="insight-detail">{safe_text(detail)}</div>
        <div class="insight-link">OPEN MATCHUP →</div>
    </a>
    """


def render_slate_insights(predictions: list[dict[str, Any]]) -> None:
    candidates = [p for p in predictions if p["game"]["live"]["status"] != "FINAL"] or predictions
    strongest = max(candidates, key=lambda p: p["target_probability"])
    closest = min(candidates, key=lambda p: abs(p["target_probability"] - 0.5))
    highest_total = max(
        candidates,
        key=lambda p: p["projected_away_runs"] + p["projected_home_runs"],
    )
    best_quality = max(candidates, key=lambda p: p["quality_score"])

    strongest_game = strongest["game"]
    closest_game = closest["game"]
    total_game = highest_total["game"]
    quality_game = best_quality["game"]
    section_heading(
        "Model dashboard",
        "Today’s Signals",
        "The slate’s strongest lean, tightest game, scoring ceiling and cleanest data profile.",
    )
    insight_columns = st.columns(4)
    insight_data = [
        (
            strongest,
            "Strongest model lean",
            f"{strongest['target_name']} {strongest['target_probability']*100:.1f}%",
            f"{strongest_game['away']['short_name']} at {strongest_game['home']['short_name']}",
            strongest["target_probability"] * 100.0,
            f"{strongest['target_probability']*100:.0f}",
            "%",
            probability_tone(strongest["target_probability"]),
        ),
        (
            closest,
            "Closest matchup",
            f"{closest['target_name']} {closest['target_probability']*100:.1f}%",
            f"{closest_game['away']['short_name']} {closest['away_probability']*100:.1f}% · {closest_game['home']['short_name']} {closest['home_probability']*100:.1f}%",
            closest["target_probability"] * 100.0,
            f"{closest['target_probability']*100:.0f}",
            "%",
            "ice",
        ),
        (
            highest_total,
            "Highest projected total",
            f"{highest_total['projected_away_runs'] + highest_total['projected_home_runs']:.1f} runs",
            f"{total_game['away']['short_name']} at {total_game['home']['short_name']}",
            clamp((highest_total["projected_away_runs"] + highest_total["projected_home_runs"]) / 12.0 * 100.0, 0.0, 100.0),
            f"{highest_total['projected_away_runs'] + highest_total['projected_home_runs']:.1f}",
            "runs",
            "warn",
        ),
        (
            best_quality,
            "Best data quality",
            f"{best_quality['quality_score']}/100",
            f"{quality_game['away']['short_name']} at {quality_game['home']['short_name']}",
            best_quality["quality_score"],
            f"{best_quality['quality_score']}",
            "grade",
            quality_tone(best_quality["quality_score"]),
        ),
    ]
    for index, (column, (prediction, label, value, detail, gauge_value, gauge_display, gauge_label, tone)) in enumerate(
        zip(insight_columns, insight_data)
    ):
        game = prediction["game"]
        signal_gauge = gauge_markup(
            gauge_value,
            gauge_label,
            kind="quality-gauge",
            tone=tone,
            display=gauge_display,
        )
        with column:
            with st.container(border=True, key=f"insight_{index}"):
                st.markdown(
                    html_block(f"""
                    <div class="slate-signal" style="{matchup_style(game)}">
                        <div class="slate-signal-copy">
                            <div class="slate-signal-label">{safe_text(label)}</div>
                            <div class="slate-signal-value">{safe_text(value)}</div>
                            <div class="slate-signal-detail">{safe_text(detail)}</div>
                            <div class="slate-signal-logos">
                                <img src="{safe_text(game['away']['logo'])}" alt="" loading="lazy">
                                <img src="{safe_text(game['home']['logo'])}" alt="" loading="lazy">
                            </div>
                        </div>
                        {signal_gauge}
                    </div>
                    """),
                    unsafe_allow_html=True,
                )


def render_compact_game_row(prediction: dict[str, Any], weather: dict[str, Any]) -> None:
    game = prediction["game"]
    away, home = game["away"], game["home"]
    live = game["live"]
    status = live["status"]
    game_dt = game.get("game_datetime_utc")
    start_text = game_dt.astimezone(ET).strftime("%-I:%M %p ET") if game_dt else "Time TBD"

    if status == "LIVE":
        outs = int(live.get("outs") or 0)
        status_label = "Live"
        status_class = "live"
        status_detail = (
            f"{live.get('status_label') or 'In progress'} · "
            f"{outs} {'out' if outs == 1 else 'outs'}"
        )
        score_label = "Current score"
        away_score = str(int(live.get("away_runs") or 0))
        home_score = str(int(live.get("home_runs") or 0))
    elif status == "FINAL":
        status_label = "Final"
        status_class = "final"
        status_detail = "Completed"
        score_label = "Final score"
        away_score = str(int(live.get("away_runs") or 0))
        home_score = str(int(live.get("home_runs") or 0))
    else:
        status_label = "Upcoming"
        status_class = "upcoming"
        status_detail = start_text
        score_label = "Projected score"
        away_score = f"{prediction['projected_away_runs']:.1f}"
        home_score = f"{prediction['projected_home_runs']:.1f}"

    away_pct = prediction["away_probability"] * 100.0
    home_pct = prediction["home_probability"] * 100.0
    fair_odds = (
        prediction["fair_away_odds"]
        if prediction["target_side"] == "away"
        else prediction["fair_home_odds"]
    )
    target = game[prediction["target_side"]]
    analysis_is_open = st.session_state.get("open_game_pk") == game["game_pk"]
    context = weather_text(weather, game["venue"])
    away_record = f"{int(away.get('wins') or 0)}-{int(away.get('losses') or 0)}"
    home_record = f"{int(home.get('wins') or 0)}-{int(home.get('losses') or 0)}"
    pick_gauge = gauge_markup(
        prediction["target_probability"] * 100.0,
        "model",
        kind="prediction-gauge",
        tone=probability_tone(prediction["target_probability"]),
    )
    data_gauge = gauge_markup(
        prediction["quality_score"],
        "quality",
        kind="quality-gauge",
        tone=quality_tone(prediction["quality_score"]),
        display=str(prediction["quality_score"]),
    )
    support_text = (prediction.get("support") or ["Balanced pregame inputs support this side."])[0]
    risk_text = (prediction.get("risks") or ["Baseball variance keeps this matchup live."])[0]
    away_pick_class = "is-pick" if prediction["target_side"] == "away" else ""
    home_pick_class = "is-pick" if prediction["target_side"] == "home" else ""
    if status in {"LIVE", "FINAL"}:
        game_line = (
            f"{away['short_name']} {away_score} – {home_score} {home['short_name']} · "
            f"{status_detail}"
        )
    else:
        game_line = (
            f"{start_text} · projected {away['short_name']} {away_score} – "
            f"{home_score} {home['short_name']}"
        )
    with st.container(border=True, key=f"matchup_row_{game['game_pk']}"):
        st.markdown(
            html_block(f"""
            <div class="match-card" style="{matchup_style(game)}">
                <div class="match-card-top">
                    <div class="match-status-wrap">
                        <span class="match-status {status_class}">{safe_text(status_label)}</span>
                        <span class="match-clock">{safe_text(game_line)}</span>
                    </div>
                    <div class="match-context">{safe_text(context)}</div>
                </div>
                <div class="match-comparison">
                    <div class="team-block away {away_pick_class}">
                        <img class="team-logo-large" src="{safe_text(away['logo'])}" alt="" loading="lazy">
                        <div class="team-copy">
                            <div class="team-name-large">{safe_text(away['name'])}</div>
                            <div class="team-meta">{safe_text(away_record)} · {safe_text(away.get('pitcher_name') or 'Starter TBD')}</div>
                            <div class="team-probability">{away_pct:.1f}% win probability</div>
                        </div>
                    </div>
                    <div class="forecast-core">
                        {pick_gauge}
                        <div class="forecast-label">Locked pick</div>
                        <div class="forecast-team">{safe_text(target['short_name'])}</div>
                        <div class="forecast-line">Fair line {safe_text(fmt_odds(fair_odds))}</div>
                    </div>
                    <div class="team-block home {home_pick_class}">
                        <img class="team-logo-large" src="{safe_text(home['logo'])}" alt="" loading="lazy">
                        <div class="team-copy">
                            <div class="team-name-large">{safe_text(home['name'])}</div>
                            <div class="team-meta">{safe_text(home_record)} · {safe_text(home.get('pitcher_name') or 'Starter TBD')}</div>
                            <div class="team-probability">{home_pct:.1f}% win probability</div>
                        </div>
                    </div>
                </div>
                <div class="match-signals">
                    <div class="signal-strip good">
                        <div class="signal-strip-label">Model support</div>
                        <div class="signal-strip-copy">{safe_text(support_text)}</div>
                    </div>
                    <div class="signal-strip bad">
                        <div class="signal-strip-label">Main risk</div>
                        <div class="signal-strip-copy">{safe_text(risk_text)}</div>
                    </div>
                    <div class="quality-lockup">
                        {data_gauge}
                        <div class="quality-lockup-copy">
                            <span>Data profile</span>
                            <strong>{safe_text(prediction['quality_label'])}</strong>
                        </div>
                    </div>
                </div>
            </div>
            """),
            unsafe_allow_html=True,
        )

        footer_column, action_column = st.columns([5.5, 1.15], vertical_alignment="center")
        with footer_column:
            st.markdown(
                html_block(f"""
                <div class="match-action-note"><strong style="color:{tone_color((prediction.get('research_selection') or {}).get('tone', 'ice'))}">{safe_text((prediction.get('research_selection') or {}).get('label', 'Forecast'))}</strong> · {safe_text(forecast_lock_label(prediction))}. All recorded picks stay in the main record.</div>
                """),
                unsafe_allow_html=True,
            )
        with action_column:
            st.button(
                "Hide analysis" if analysis_is_open else "View full analysis",
                key=f"toggle_analysis_{game['game_pk']}",
                on_click=toggle_game_analysis,
                args=(game["game_pk"],),
                help="Open this game's full model explanation directly below this row.",
                use_container_width=True,
            )


def render_advanced(
    prediction: dict[str, Any], weather: dict[str, Any], lineup: dict[str, Any]
) -> None:
    context = prediction.get("captured_context") or {}
    if prediction.get("snapshot_state") == "saved":
        weather = context.get("weather") or {}
        lineup = context.get("lineup") or {}
    game = prediction["game"]
    explanation = build_model_explanation(prediction, weather, lineup)
    target_side = prediction["target_side"]
    opponent_side = "home" if target_side == "away" else "away"
    target = game[target_side]
    opponent = game[opponent_side]
    target_fair_odds = (
        prediction["fair_away_odds"] if target_side == "away" else prediction["fair_home_odds"]
    )
    target_probability = prediction["target_probability"] * 100.0
    hero_gauge = gauge_markup(
        target_probability,
        "model",
        kind="prediction-gauge",
        tone=probability_tone(prediction["target_probability"]),
    )
    quality_class = quality_tone(prediction["quality_score"])
    if quality_class == "ice":
        quality_class = "warn"
    support_cards = "".join(
        f"<div class='analysis-signal-row good'><div class='analysis-signal-tag'>Support {index + 1}</div>"
        f"<div class='analysis-signal-copy'>{safe_text(item)}</div></div>"
        for index, item in enumerate(prediction.get("support") or [])
    )
    risk_cards = "".join(
        f"<div class='analysis-signal-row bad'><div class='analysis-signal-tag'>Risk {index + 1}</div>"
        f"<div class='analysis-signal-copy'>{safe_text(item)}</div></div>"
        for index, item in enumerate(prediction.get("risks") or [])
    )
    change_cards = "".join(
        f"<div class='analysis-signal-row warn'><div class='analysis-signal-tag'>Watch {index + 1}</div>"
        f"<div class='analysis-signal-copy'>{safe_text(item)}</div></div>"
        for index, item in enumerate(prediction.get("invalidation") or [])
    )

    away_pitch_score = (
        float(prediction["away_starter"]["quality_ra9"]) * .62
        + float(prediction["away_bullpen"]["quality_ra9"]) * .38
    )
    home_pitch_score = (
        float(prediction["home_starter"]["quality_ra9"]) * .62
        + float(prediction["home_bullpen"]["quality_ra9"]) * .38
    )
    away_pitch_class = "better" if away_pitch_score <= home_pitch_score else "worse"
    home_pitch_class = "better" if home_pitch_score < away_pitch_score else "worse"

    with st.container(key=f"analysis_panel_{game['game_pk']}"):
        st.markdown(
            html_block(f"""
            <div class="analysis-panel-heading">
                <div>
                    <div class="analysis-panel-label">Full matchup analysis</div>
                    <div class="analysis-panel-matchup">{safe_text(game['away']['short_name'])} at {safe_text(game['home']['short_name'])}</div>
                </div>
                <div class="analysis-lock-note">{safe_text(forecast_lock_label(prediction))}</div>
            </div>
            <div class="analysis-hero" style="{matchup_style(game)}">
                <div class="analysis-matchup-logos">
                    <img src="{safe_text(game['away']['logo'])}" alt="" loading="lazy">
                    <span class="analysis-vs">VS</span>
                    <img src="{safe_text(game['home']['logo'])}" alt="" loading="lazy">
                </div>
                <div>
                    <div class="analysis-eyebrow">{safe_text(forecast_lock_label(prediction))}</div>
                    <div class="analysis-title">{safe_text(target['name'])} over {safe_text(opponent['name'])}</div>
                    <div class="analysis-summary">{safe_text(explanation['summary'])}</div>
                </div>
                <div class="analysis-hero-gauge">{hero_gauge}</div>
            </div>
            <div class="analysis-stat-rail">
                <div class="analysis-stat good">
                    <div class="snapshot-label">Model selection</div>
                    <div class="snapshot-value">{safe_text(target['short_name'])} {target_probability:.1f}%</div>
                    <div class="snapshot-detail">{safe_text(forecast_lock_label(prediction))}</div>
                </div>
                <div class="analysis-stat">
                    <div class="snapshot-label">Projected score</div>
                    <div class="snapshot-value">{safe_text(game['away']['short_name'])} {prediction['projected_away_runs']:.1f} · {safe_text(game['home']['short_name'])} {prediction['projected_home_runs']:.1f}</div>
                    <div class="snapshot-detail">Monte Carlo run expectation</div>
                </div>
                <div class="analysis-stat">
                    <div class="snapshot-label">Fair moneyline</div>
                    <div class="snapshot-value">{safe_text(fmt_odds(target_fair_odds))}</div>
                    <div class="snapshot-detail">Model price before sportsbook margin</div>
                </div>
                <div class="analysis-stat {quality_class}">
                    <div class="snapshot-label">Data quality</div>
                    <div class="snapshot-value">{prediction['quality_score']}/100</div>
                    <div class="snapshot-detail">{safe_text(prediction['quality_label'])} · disagreement {prediction['model_agreement_gap']*100:.1f} pts</div>
                </div>
            </div>
            """),
            unsafe_allow_html=True,
        )

        if prediction.get("snapshot_state") == "legacy":
            st.info("Earlier-build pick: the original selection, percentage and projected score are preserved. Detailed inputs were not saved then, so the other panels show current context—not the original research.")
        elif prediction.get("snapshot_state") == "untracked":
            st.warning("Not recorded before scheduled first pitch. This estimate will not be counted as an original model pick.")
        selection = prediction.get("research_selection") or {}
        if selection.get("rule_version") == SHORTLIST_RULE_VERSION:
            st.caption(str(selection["label"]) + " · " + ("Meets the experimental research rule. No win or profit is guaranteed." if selection.get("qualifies") else " ".join(selection.get("reasons") or [])))
        why_tab, pitching_tab, context_tab, market_tab = st.tabs(
            ["Why the pick", "Pitching", "Game context", "Market & risks"]
        )

        with why_tab:
            st.markdown(
                html_block(f"""
                <div class="analysis-grid-two">
                    <div class="analysis-copy-card">
                        <div class="analysis-card-label">Probability build</div>
                        <div class="analysis-card-title">How the forecast was formed</div>
                        <div class="analysis-card-copy">{safe_text(explanation['simulation'])}</div>
                    </div>
                    <div class="analysis-copy-card">
                        <div class="analysis-card-label">Offensive matchup</div>
                        <div class="analysis-card-title">Run-production comparison</div>
                        <div class="analysis-card-copy">{safe_text(explanation['offense'])}</div>
                    </div>
                </div>
                <div class="analysis-subsection-title good">Strongest reasons behind the pick</div>
                <div class="analysis-signal-list">{support_cards}</div>
                """),
                unsafe_allow_html=True,
            )

        with pitching_tab:
            st.markdown(
                html_block(f"""
                <div class="pitch-compare">
                    <div class="pitch-team-card {away_pitch_class}">
                        <div class="pitch-team-head">
                            <img src="{safe_text(game['away']['logo'])}" alt="" loading="lazy">
                            <div><div class="pitch-team-name">{safe_text(game['away']['name'])}</div><div class="pitch-team-tag">Lower run-prevention grade is better</div></div>
                        </div>
                        <div class="pitch-metrics">
                            <div class="pitch-metric"><span>Starter grade</span><strong>{prediction['away_starter']['quality_ra9']:.2f}</strong></div>
                            <div class="pitch-metric"><span>Bullpen grade</span><strong>{prediction['away_bullpen']['quality_ra9']:.2f}</strong></div>
                        </div>
                    </div>
                    <div class="pitch-team-card {home_pitch_class}">
                        <div class="pitch-team-head">
                            <img src="{safe_text(game['home']['logo'])}" alt="" loading="lazy">
                            <div><div class="pitch-team-name">{safe_text(game['home']['name'])}</div><div class="pitch-team-tag">Lower run-prevention grade is better</div></div>
                        </div>
                        <div class="pitch-metrics">
                            <div class="pitch-metric"><span>Starter grade</span><strong>{prediction['home_starter']['quality_ra9']:.2f}</strong></div>
                            <div class="pitch-metric"><span>Bullpen grade</span><strong>{prediction['home_bullpen']['quality_ra9']:.2f}</strong></div>
                        </div>
                    </div>
                </div>
                <div class="analysis-grid-two">
                    <div class="analysis-copy-card"><div class="analysis-card-label">Starting pitchers</div><div class="analysis-card-copy">{safe_text(explanation['starters'])}</div></div>
                    <div class="analysis-copy-card"><div class="analysis-card-label">Bullpens</div><div class="analysis-card-copy">{safe_text(explanation['bullpen'])}</div></div>
                </div>
                """),
                unsafe_allow_html=True,
            )

        with context_tab:
            away_lineup = lineup.get("away") or {}
            home_lineup = lineup.get("home") or {}
            away_names = away_lineup.get("names") or []
            home_names = home_lineup.get("names") or []
            away_order = "".join(
                f"<li>{index + 1}. {safe_text(name)}</li>" for index, name in enumerate(away_names)
            ) or "<li>Batting order not confirmed</li>"
            home_order = "".join(
                f"<li>{index + 1}. {safe_text(name)}</li>" for index, name in enumerate(home_names)
            ) or "<li>Batting order not confirmed</li>"
            st.markdown(
                html_block(f"""
                <div class="analysis-grid-two">
                    <div class="analysis-copy-card"><div class="analysis-card-label">Park and weather</div><div class="analysis-card-copy">{safe_text(explanation['environment'])}</div></div>
                    <div class="analysis-copy-card {quality_class}"><div class="analysis-card-label">Confidence and missing data</div><div class="analysis-card-copy">{safe_text(explanation['confidence'])}</div></div>
                </div>
                <div class="analysis-grid-two">
                    <div class="analysis-copy-card">
                        <div class="analysis-card-label">{safe_text(game['away']['short_name'])} lineup · {'confirmed' if away_lineup.get('confirmed') else 'unconfirmed'}</div>
                        <ol class="lineup-list">{away_order}</ol>
                    </div>
                    <div class="analysis-copy-card">
                        <div class="analysis-card-label">{safe_text(game['home']['short_name'])} lineup · {'confirmed' if home_lineup.get('confirmed') else 'unconfirmed'}</div>
                        <ol class="lineup-list">{home_order}</ol>
                    </div>
                </div>
                """),
                unsafe_allow_html=True,
            )

        with market_tab:
            distribution = prediction["distribution"]
            st.markdown(
                html_block(f"""
                <div class="analysis-copy-card warn">
                    <div class="analysis-card-label">Price interpretation</div>
                    <div class="analysis-card-copy">{safe_text(explanation['market'])}</div>
                </div>
                <div class="analysis-stat-rail">
                    <div class="analysis-stat"><div class="snapshot-label">Fair away ML</div><div class="snapshot-value">{safe_text(fmt_odds(prediction['fair_away_odds']))}</div></div>
                    <div class="analysis-stat"><div class="snapshot-label">Fair home ML</div><div class="snapshot-value">{safe_text(fmt_odds(prediction['fair_home_odds']))}</div></div>
                    <div class="analysis-stat"><div class="snapshot-label">Over {distribution['total_line']}</div><div class="snapshot-value">{distribution['over_probability']*100:.1f}%</div></div>
                    <div class="analysis-stat"><div class="snapshot-label">Under {distribution['total_line']}</div><div class="snapshot-value">{distribution['under_probability']*100:.1f}%</div></div>
                </div>
                <div class="analysis-grid-two">
                    <div><div class="analysis-subsection-title bad">Bear case</div><div class="analysis-signal-list">{risk_cards}</div></div>
                    <div><div class="analysis-subsection-title warn">What could change the view</div><div class="analysis-signal-list">{change_cards}</div></div>
                </div>
                """),
                unsafe_allow_html=True,
            )


def build_slate_forecasts(games: list[dict[str, Any]], selected_date: date, simulations: int,
                          payload: dict[str, Any], odds_api_key: str = "") -> tuple[list[dict[str, Any]], dict, dict]:
    needed = [game for game in games if not isinstance(
        (payload["picks"].get(str(game["game_pk"])) or {}).get("frozen_prediction"), dict)]
    weather_by_game: dict = {}
    lineups_by_game: dict = {}
    fresh: dict = {}
    if needed:
        season, as_of = selected_date.year, selected_date.isoformat()
        team_ids = tuple(sorted({int(game[side]["id"]) for game in needed for side in ("away", "home") if game[side].get("id")}))
        pitcher_ids = tuple(sorted({int(game[side]["pitcher_id"]) for game in needed for side in ("away", "home") if game[side].get("pitcher_id")}))
        calls = {
            "teams": (cached_team_stats, (season, as_of)),
            "pitchers": (cached_pitchers, (pitcher_ids, season, as_of)),
            "bullpens": (cached_bullpens, (team_ids, season)),
            "statcast": (cached_statcast, (season,)),
            "parks": (cached_park_factors, (season,)),
            "weather": (cached_weather, (needed,)),
            "lineups": (cached_lineups, (tuple(game["game_pk"] for game in needed),)),
        }
        if odds_api_key:
            calls["odds"] = (cached_odds, (odds_api_key,))
        feeds: dict[str, Any] = {}
        required_error = None
        with ThreadPoolExecutor(max_workers=len(calls)) as executor:
            futures = {name: executor.submit(function, *arguments) for name, (function, arguments) in calls.items()}
            for name, future in futures.items():
                try:
                    feeds[name] = future.result()
                except Exception as exc:
                    feeds[name] = [] if name == "odds" else {}
                    if name == "teams":
                        required_error = exc
        if required_error or not feeds.get("teams"):
            raise DataSourceError("Team statistics were unavailable; no new forecasts were invented.")
        weather_by_game = feeds.get("weather") or {}
        lineups_by_game = feeds.get("lineups") or {}
        calibration = fit_calibration_challenger(payload["picks"].values(), datetime.now(ET))
        for game in needed:
            if any(not (feeds["teams"].get(game[side]["id"]) or {}).get("hitting") for side in ("away", "home")):
                raise DataSourceError("One of the teams is missing required hitting data; its forecast was withheld.")
            weather = weather_by_game.get(game["game_pk"], {"available": False, "controlled": False, "run_multiplier": 1.0})
            lineup = lineups_by_game.get(game["game_pk"], {})
            odds = match_moneyline_odds(game, feeds.get("odds") or [])
            prediction = build_game_prediction(game, feeds["teams"], feeds["pitchers"], feeds["statcast"],
                                               feeds["bullpens"], feeds["parks"], weather, lineup, odds,
                                               simulations=simulations, lock_pregame=True)
            fresh[game["game_pk"]] = attach_forecast_evidence(prediction, weather, lineup, calibration)
    predictions = []
    for game in games:
        entry = payload["picks"].get(str(game["game_pk"]))
        prediction = fresh.get(game["game_pk"]) or {"game": game}
        prediction = apply_frozen_forecast(prediction, entry)
        context = prediction.get("captured_context") or {}
        if prediction.get("snapshot_state") == "saved":
            weather_by_game[game["game_pk"]] = context.get("weather") or {}
            lineups_by_game[game["game_pk"]] = context.get("lineup") or {}
        predictions.append(prediction)
    return predictions, weather_by_game, lineups_by_game


def run_background_tracker(*, initialize: bool = False, grade_only: bool = False, seed_path: str | None = None) -> int:
    """Headless scheduled entry point. No dashboard or browser is required."""
    if seed_path:
        seed = Path(seed_path)
        if not seed.is_file() or seed.stat().st_size > TRACKER_MAX_BYTES:
            print("Seed backup is missing or too large.")
            return 1
        success, message = restore_prediction_tracker(seed.read_bytes())
        if not success:
            print(message)
            return 1
    if initialize:
        try:
            initialize_remote_tracker()
        except RemoteTrackerError as exc:
            print(str(exc))
            return 1
    remote = sync_remote_tracker(write=False)
    if remote not in {"ready", "not configured"}:
        print(remote)
        return 1
    before, status = sync_prediction_tracker([], datetime.now(ET))
    if not tracker_sync_can_publish(before, status):
        print(status)
        return 1
    grading_warning = status if status != "ready" else None
    capture_error = None
    captured = 0
    if not grade_only:
        try:
            now = datetime.now(ET)
            games = cached_schedule(now.date().isoformat())
            needed = [game for game in games if str(game["game_pk"]) not in before["picks"]
                      and _pregame_snapshot_allowed(game, now)
                      and (game["game_datetime_utc"] - now).total_seconds() <= 3 * 3600]
            if needed:
                predictions, _, _ = build_slate_forecasts(needed, now.date(), 30_000, before, secret_value("ODDS_API_KEY"))
                after, status = sync_prediction_tracker(predictions, datetime.now(ET), reconcile=False)
                captured = len(after["picks"]) - len(before["picks"])
                if status != "ready":
                    capture_error = status
        except (DataSourceError, ValueError) as exc:
            capture_error = str(exc)
    pushed = sync_remote_tracker(write=True, heartbeat=True)
    if pushed not in {"ready", "not configured"}:
        print(pushed)
        return 1
    latest, status = load_prediction_tracker()
    print(json.dumps({"build": TRACKER_BUILD, "captured": captured,
                      "record": tracker_record(latest["picks"].values()),
                      "checked_at_et": _tracker_timestamp(), "shared_storage": pushed,
                      "capture_error": capture_error, "grading_warning": grading_warning}, sort_keys=True))
    return 1 if capture_error or grading_warning or status != "ready" else 0


def run_dashboard() -> None:
    now_et = datetime.now(ET)
    page_token = str(time.monotonic_ns())
    initialize_page()
    startup_remote_status = sync_remote_tracker(write=False)
    today_et = now_et.date()
    scheduled_today = scheduled_update_at(today_et)
    refresh_tracker = daily_refresh_tracker()

    # Force one full data-cache refresh on the first app run at or after the daily
    # update time. If Community Cloud is asleep then, this runs immediately when the
    # next visitor wakes the app.
    if now_et >= scheduled_today and refresh_tracker.get("completed_for") != today_et.isoformat():
        st.cache_data.clear()
        refresh_tracker["completed_for"] = today_et.isoformat()
        st.session_state["slate_date"] = today_et

    # Keep an open browser session from remaining on yesterday's slate after midnight.
    if st.session_state.get("calendar_day") != today_et.isoformat():
        st.session_state["calendar_day"] = today_et.isoformat()
        st.session_state["slate_date"] = today_et

    next_update = next_scheduled_update(now_et)
    odds_api_key = secret_value("ODDS_API_KEY")

    brand_column, sync_column, refresh_column, settings_column = st.columns(
        [4.55, 1.32, 0.72, 0.9], vertical_alignment="center"
    )
    with brand_column:
        st.markdown(
            html_block("""
            <div class="quant-brand">
                <div class="quant-brand-mark">Q</div>
                <div>
                    <div class="quant-brand-heading">
                        <div class="quant-brand-title">MLB Quant Terminal</div>
                        <span class="quant-build">Build 24</span>
                    </div>
                    <div class="quant-brand-subtitle">Live scores · locked pregame forecasts · matchup intelligence</div>
                </div>
            </div>
            """),
            unsafe_allow_html=True,
        )
    with sync_column:
        st.markdown(
            html_block(f"""
            <div class="quant-sync">
                <span class="quant-sync-dot"></span>
                <span class="quant-sync-copy">
                    <span>Live data</span>
                    <small>{now_et.strftime('%-I:%M:%S %p ET')}</small>
                </span>
            </div>
            """),
            unsafe_allow_html=True,
        )
    with refresh_column:
        if st.button("Refresh", key="top_refresh", use_container_width=True, help="Refresh all data"):
            st.cache_data.clear()
            st.rerun()
    with settings_column:
        with st.popover("Settings", use_container_width=True):
            selected_date = st.date_input(
                "Slate date",
                min_value=today_et,
                max_value=today_et + timedelta(days=7),
                key="slate_date",
                help="Choose today's slate or an upcoming MLB date.",
            )
            simulations = st.select_slider(
                "Monte Carlo simulations",
                options=[10_000, 20_000, 30_000, 50_000, 75_000],
                value=30_000,
            )
            st.caption("Picks use pregame inputs. Live scores never change them.")
            if st.button("Force complete refresh", use_container_width=True):
                st.cache_data.clear()
                st.rerun()
            st.divider()
            st.markdown("**Connections**")
            st.caption("MLB + Baseball Savant connected\n\nGame-time weather connected")
            if odds_api_key:
                st.caption("Sportsbook comparison connected")
            else:
                st.caption("Sportsbook comparison needs an API key")
            st.markdown("**Scheduled update**")
            st.caption(
                f"Daily refresh {scheduled_today.strftime('%-I:%M %p ET')} · next "
                f"{next_update.strftime('%a, %b %-d at %-I:%M %p ET')}"
            )

    st.divider()
    as_of = selected_date.isoformat()
    try:
        with st.spinner("Syncing the MLB slate and official game states…"):
            games = cached_schedule(as_of)
    except DataSourceError as exc:
        st.error(f"The MLB schedule feed is currently unavailable: {exc}")
        render_live_tracker(page_started_at=page_token)
        st.stop()

    if not games:
        st.info("No MLB games were returned for this date.")
        render_live_tracker(page_started_at=page_token)
        st.stop()

    try:
        with st.spinner("Loading the slate and preserving saved pregame forecasts…"):
            tracker_before, tracker_before_status = load_prediction_tracker()
            predictions, weather_by_game, lineups_by_game = build_slate_forecasts(
                games, selected_date, simulations, tracker_before, odds_api_key
            )
    except (DataSourceError, ValueError) as exc:
        st.error(f"Forecast inputs could not be verified: {exc}")
        render_live_tracker(page_started_at=page_token)
        st.stop()

    priority = {"LIVE": 0, "PREVIEW": 1, "FINAL": 2}
    predictions.sort(
        key=lambda prediction: (
            priority[prediction["game"]["live"]["status"]],
            prediction["game"].get("game_datetime_utc") or datetime.max.replace(tzinfo=ET),
        )
    )

    tracker_payload, tracker_storage_status = sync_prediction_tracker(
        predictions, datetime.now(ET), reconcile=False
    )
    predictions = [apply_frozen_forecast(prediction, tracker_payload["picks"].get(str(prediction["game"]["game_pk"])))
                   for prediction in predictions]

    live_count = sum(p["game"]["live"]["status"] == "LIVE" for p in predictions)
    preview_count = sum(p["game"]["live"]["status"] == "PREVIEW" for p in predictions)
    final_count = sum(p["game"]["live"]["status"] == "FINAL" for p in predictions)
    render_game_center(predictions, selected_date)
    render_live_tracker(tracker_storage_status, page_started_at=page_token)

    render_slate_insights(predictions)
    st.markdown(
        html_block("""
        <div class="model-note">
            Probabilities, not promises. Every outcome can lose. The model reports uncertainty,
            leaves unavailable information missing, and never labels a prediction a guarantee.
        </div>
        """),
        unsafe_allow_html=True,
    )
    section_heading(
        "Game-by-game forecast",
        "Matchup Board",
        f"{len(predictions)} games · {live_count} live · {preview_count} upcoming · "
        f"{final_count} final · refreshed {datetime.now(ET).strftime('%-I:%M:%S %p ET')}",
    )

    filter_column, sort_column, search_column = st.columns([1.35, 1.1, 1.1], vertical_alignment="bottom")
    with filter_column:
        status_filter = st.radio(
            "Game status",
            ["All", "Live", "Upcoming", "Final"],
            horizontal=True,
            key="matchup_status_filter",
        )
    with sort_column:
        sort_mode = st.selectbox(
            "Sort matchups",
            ["Game time", "Strongest lean", "Highest data quality", "Closest matchup", "Stronger setups only"],
            key="matchup_sort_mode",
        )
    with search_column:
        team_search = st.text_input(
            "Find a team",
            placeholder="Team name…",
            key="matchup_team_search",
        ).strip().lower()

    status_map = {"Live": "LIVE", "Upcoming": "PREVIEW", "Final": "FINAL"}
    filtered_predictions = [
        prediction
        for prediction in predictions
        if (
            status_filter == "All"
            or prediction["game"]["live"]["status"] == status_map[status_filter]
        )
        and (
            not team_search
            or team_search in prediction["game"]["away"]["name"].lower()
            or team_search in prediction["game"]["home"]["name"].lower()
        )
    ]

    if sort_mode == "Stronger setups only":
        filtered_predictions = [p for p in filtered_predictions if (p.get("research_selection") or {}).get("qualifies")]
        filtered_predictions.sort(key=lambda p: p["target_probability"], reverse=True)
    elif sort_mode == "Strongest lean":
        filtered_predictions.sort(key=lambda p: p["target_probability"], reverse=True)
    elif sort_mode == "Highest data quality":
        filtered_predictions.sort(key=lambda p: p["quality_score"], reverse=True)
    elif sort_mode == "Closest matchup":
        filtered_predictions.sort(key=lambda p: abs(p["target_probability"] - 0.5))
    else:
        filtered_predictions.sort(
            key=lambda p: (
                priority[p["game"]["live"]["status"]],
                p["game"].get("game_datetime_utc") or datetime.max.replace(tzinfo=ET),
            )
        )

    st.caption(f"Showing {len(filtered_predictions)} of {len(predictions)} matchups")
    if not filtered_predictions:
        st.info("No matchups fit the selected filters.")

    for prediction in filtered_predictions:
        game_pk = prediction["game"]["game_pk"]
        weather = weather_by_game.get(game_pk, {})
        lineup = lineups_by_game.get(game_pk, {})
        render_compact_game_row(prediction, weather)
        analysis_is_open = st.session_state.get("open_game_pk") == game_pk
        if analysis_is_open:
            render_advanced(prediction, weather, lineup)

    st.markdown("---")
    with st.expander("Methodology, data sources and important limitations", expanded=False):
        st.markdown(
            """
    The app uses an interpretable ensemble rather than presenting an unvalidated model as “AI.” Pregame run estimates combine season-to-date and recent team offense, opposing starter ERA/FIP/xERA, bullpen relief splits, fielding, a rolling three-year park factor, game-time weather and home-field context. A negative-binomial Monte Carlo simulation produces a score distribution; its winner probability is blended with a separate record-based estimate and shrunk toward 50% to acknowledge uncertainty.

    Saved picks and their probabilities are restored from the tracker, with full input snapshots for Build 24 captures. Live scores never rewrite a saved forecast. Games first seen after scheduled first pitch are marked untracked and excluded from the record. Earlier-build detailed inputs were not saved, so those are not retroactively reconstructed.

    Current limits:

    - Confirmed lineups are detected, but this version does not yet rebuild team offense batter-by-batter.
    - Bullpen quality uses relief splits; individual reliever availability and warm-up data are not yet modeled.
    - Without an odds API key, the app cannot calculate real market edge, expected value or line movement.
    - The model must be walk-forward backtested and calibrated before anyone treats its estimates as proven betting signals.
    - The experimental stronger-setup rule and calibration challenger are scored prospectively; neither is advertised as a proven 70% model.
            """
        )
        st.markdown("**Primary sources**")
        for name, url in SOURCE_LINKS.items():
            st.markdown(f"- [{name}]({url})")
        st.caption("Open-Meteo weather data requires attribution under its published license. MLB and Statcast data remain subject to MLB terms and notices.")


if __name__ == "__main__":
    if "--sync-tracker" in sys.argv:
        import argparse
        parser = argparse.ArgumentParser(description="Capture pregame picks and reconcile official MLB finals.")
        parser.add_argument("--sync-tracker", action="store_true")
        parser.add_argument("--init-remote", action="store_true")
        parser.add_argument("--grade-only", action="store_true")
        parser.add_argument("--seed-backup")
        arguments = parser.parse_args()
        raise SystemExit(run_background_tracker(initialize=arguments.init_remote,
                                                grade_only=arguments.grade_only,
                                                seed_path=arguments.seed_backup))
    else:
        run_dashboard()
