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

"""Network and normalization layer for the MLB Quantitative Terminal.

Only observed source values are returned. Missing feeds remain missing; this
module never manufactures replacement statistics.
"""
import csv
import io
import json
import math
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
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
"""Transparent MLB game projection and simulation engine.

This is an evidence-based baseline model, not a guarantee and not a trained
"neural" system. It combines several independently interpretable estimates,
then deliberately shrinks pregame probabilities toward 50% to reflect model
uncertainty.
"""
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
    season_rpg = _rate(season, "runs", "gamesPlayed") or league["runs_per_game"]
    recent_rpg = _rate(recent, "runs", "gamesPlayed") or season_rpg
    ops = safe_float(season.get("ops"), league["ops"]) or league["ops"]

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
    home_runs = safe_float(stat.get("homeRuns"), 0.0) or 0.0
    walks = safe_float(stat.get("baseOnBalls"), 0.0) or 0.0
    hit_batters = safe_float(stat.get("hitByPitch"), 0.0) or 0.0
    strikeouts = safe_float(stat.get("strikeOuts"), 0.0) or 0.0
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
        "has_stats": bool(stat),
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
    distribution = simulate_score_distribution(
        game, away_mean, home_mean, simulations, total_line=total_line
    )
    record_home = _record_probability(game)
    sim_home = distribution["home_win"]
    status = game["live"]["status"]
    if status == "FINAL":
        home_probability = 1.0 if game["live"]["home_runs"] > game["live"]["away_runs"] else 0.0
    elif status == "LIVE":
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
    if moneyline_odds and status == "PREVIEW":
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
"""Visual system for the Streamlit dashboard."""

import random


def bubble_markup(count: int = 42) -> str:
    """Return deterministic decorative bubbles so reruns do not jump around."""
    rng = random.Random(937)
    bubbles: list[str] = []
    for _ in range(count):
        size = rng.uniform(18, 94)
        left = rng.uniform(-3, 103)
        duration = rng.uniform(18, 42)
        delay = rng.uniform(0, 32)
        opacity = rng.uniform(0.16, 0.52)
        wobble = rng.uniform(6, 12)
        bubbles.append(
            "<span class='quant-bubble' style='"
            f"left:{left:.2f}vw;width:{size:.1f}px;height:{size:.1f}px;"
            f"animation-duration:{duration:.1f}s,{wobble:.1f}s;"
            f"animation-delay:-{delay:.1f}s,-{delay:.1f}s;"
            f"opacity:{opacity:.2f}'></span>"
        )
    return "<div class='quant-bubbles'>" + "".join(bubbles) + "</div>"


def full_stylesheet() -> str:
    return """
<style>
@import url('https://fonts.googleapis.com/css2?family=Fredoka:wght@500;600;700&family=Outfit:wght@400;500;600;700;800&family=JetBrains+Mono:wght@500;700&display=swap');

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
    font-family: 'Outfit', sans-serif !important;
}

.stApp {
    color: var(--text);
    background:
        radial-gradient(circle at 15% 0%, rgba(14, 165, 233, .22), transparent 34%),
        radial-gradient(circle at 90% 15%, rgba(34, 211, 238, .12), transparent 32%),
        linear-gradient(145deg, var(--navy-0) 0%, var(--navy-2) 48%, #061224 100%);
}

[data-testid="stHeader"] { background: rgba(3, 8, 23, .45); }
[data-testid="stSidebar"] { background: rgba(3, 8, 23, .96); }
.main .block-container { max-width: 1540px; padding-top: 1.4rem; padding-bottom: 4rem; position: relative; z-index: 5; }
h1, h2, h3, h4 { font-family: 'Fredoka', sans-serif !important; }

.quant-bubbles {
    position: fixed; inset: 0; overflow: hidden; z-index: 0;
    pointer-events: none;
}
.quant-bubble {
    position: absolute; bottom: -130px; display: block; border-radius: 999px;
    border: 1px solid rgba(255,255,255,.30);
    background: radial-gradient(circle at 28% 25%, rgba(255,255,255,.34) 0 3%, rgba(125,211,252,.08) 24%, transparent 62%);
    box-shadow: inset 0 0 18px rgba(255,255,255,.12), 0 0 16px rgba(34,211,238,.10);
    backdrop-filter: blur(1px);
    animation-name: quantFloat, quantWobble;
    animation-timing-function: linear, ease-in-out;
    animation-iteration-count: infinite;
}
@keyframes quantFloat { from { transform: translateY(0); } to { transform: translateY(-125vh); } }
@keyframes quantWobble { 0%,100% { margin-left: 0; } 50% { margin-left: 34px; } }

.hero-card {
    position: relative; overflow: hidden; margin: .35rem 0 1.3rem;
    padding: 1.45rem 1.6rem; border-radius: 20px;
    border: 1px solid rgba(103,232,249,.55);
    background: linear-gradient(110deg, rgba(8,47,73,.82), rgba(14,116,144,.28), rgba(15,23,42,.78));
    box-shadow: 0 20px 55px rgba(0,0,0,.36), inset 0 1px 0 rgba(255,255,255,.15);
    backdrop-filter: blur(18px);
}
.hero-card:after {
    content: ''; position: absolute; inset: 0;
    background: linear-gradient(90deg, transparent, rgba(103,232,249,.08), transparent);
    pointer-events: none;
}
.hero-title { font: 700 clamp(1.35rem, 3vw, 2.25rem) 'Fredoka', sans-serif; letter-spacing: .02em; }
.hero-sub { margin-top: .35rem; color: #bae6fd; font-size: .96rem; }
.hero-meta { margin-top: .7rem; color: var(--muted); font: 600 .76rem 'JetBrains Mono', monospace; text-transform: uppercase; letter-spacing: .08em; }

.section-title { margin: 1.2rem 0 .75rem; font: 700 1.45rem 'Fredoka', sans-serif; }
.section-sub { color: var(--muted); margin-bottom: 1rem; }

.game-shell {
    margin: 1rem 0 1.35rem; padding: 1.15rem; border-radius: 18px;
    border: 1px solid rgba(34,211,238,.48);
    background: linear-gradient(135deg, rgba(6,24,46,.88), rgba(9,52,83,.65));
    box-shadow: 0 17px 45px rgba(0,0,0,.30), inset 0 1px 0 rgba(255,255,255,.09);
    backdrop-filter: blur(14px);
}
.game-top { display: flex; justify-content: space-between; align-items: flex-start; gap: 1rem; }
.matchup { display: flex; flex-wrap: wrap; align-items: center; gap: .55rem; font: 700 1.22rem 'Fredoka', sans-serif; }
.team-chip { display: inline-flex; align-items: center; gap: .45rem; }
.team-logo { width: 28px; height: 28px; object-fit: contain; }
.at-mark { color: #5eead4; font-family: 'JetBrains Mono', monospace; font-size: .95rem; }
.game-context { color: var(--muted); margin-top: .36rem; font-size: .86rem; }
.status-pill { white-space: nowrap; padding: .42rem .72rem; border-radius: 999px; font: 700 .7rem 'JetBrains Mono', monospace; letter-spacing: .04em; }
.status-live { color: #fecdd3; border: 1px solid rgba(251,113,133,.8); background: rgba(190,18,60,.3); box-shadow: 0 0 17px rgba(251,113,133,.34); }
.status-preview { color: #a5f3fc; border: 1px solid rgba(34,211,238,.52); background: rgba(8,145,178,.18); }
.status-final { color: #cbd5e1; border: 1px solid rgba(148,163,184,.45); background: rgba(51,65,85,.55); }

.pick-row { display: flex; flex-wrap: wrap; gap: .6rem; align-items: center; margin: .9rem 0 .8rem; }
.pick-pill { padding: .48rem .75rem; border-radius: 999px; color: #042f2e; background: linear-gradient(90deg, #5eead4, #22d3ee); font-weight: 800; box-shadow: 0 0 22px rgba(34,211,238,.34); }
.pick-prob { color: #99f6e4; font: 700 .84rem 'JetBrains Mono', monospace; }
.quality-pill { color: #cbd5e1; font: 600 .72rem 'JetBrains Mono', monospace; }

.prob-grid { display: grid; grid-template-columns: 1fr 1fr; gap: .85rem; margin: .65rem 0 1rem; }
.prob-label { display: flex; justify-content: space-between; margin-bottom: .28rem; font-size: .78rem; color: #cbd5e1; }
.prob-label strong { color: white; font-family: 'JetBrains Mono', monospace; }
.prob-track { height: 9px; border-radius: 99px; overflow: hidden; background: rgba(15,23,42,.9); border: 1px solid rgba(103,232,249,.25); }
.prob-fill { display: block; height: 100%; border-radius: inherit; background: linear-gradient(90deg, #0e7490, #67e8f9); box-shadow: 0 0 14px rgba(103,232,249,.6); }

.analysis-grid { display: grid; grid-template-columns: minmax(0,.9fr) minmax(0,.9fr) minmax(320px,1.3fr); gap: .85rem; }
.pitcher-card, .rationale-card {
    min-width: 0; border-radius: 14px; padding: .9rem;
    border: 1px solid rgba(34,211,238,.35); background: rgba(3,15,31,.54);
}
.pitcher-name { display: flex; justify-content: space-between; gap: .5rem; font-weight: 800; font-size: 1rem; }
.record { color: #5eead4; font: 600 .75rem 'JetBrains Mono', monospace; }
.metric-row { display: flex; flex-wrap: wrap; gap: .38rem; margin: .62rem 0; }
.metric { padding: .28rem .42rem; border-radius: 7px; border: 1px solid rgba(103,232,249,.40); color: #dbeafe; font: 600 .67rem 'JetBrains Mono', monospace; }
.metric.missing { color: #94a3b8; border-color: rgba(148,163,184,.28); }
.mini-title { margin: .65rem 0 .35rem; color: #a5f3fc; font: 700 .68rem 'JetBrains Mono', monospace; letter-spacing: .06em; }
.start-row { display: grid; grid-template-columns: 1.15fr .65fr .55fr .55fr; gap: .3rem; padding: .24rem 0; border-bottom: 1px solid rgba(148,163,184,.12); color: #cbd5e1; font: 600 .66rem 'JetBrains Mono', monospace; }
.start-row span:nth-child(n+2) { text-align: right; color: #99f6e4; }
.rationale-title { color: white; font: 700 .95rem 'Fredoka', sans-serif; margin-bottom: .55rem; }
.rationale-line { color: #cbd5e1; font-size: .82rem; line-height: 1.45; margin: .36rem 0; }
.rationale-line strong { color: #67e8f9; }
.source-line { margin-top: .7rem; color: #8296aa; font: 600 .64rem 'JetBrains Mono', monospace; }

.stButton > button {
    border-radius: 999px !important; border: 1px solid rgba(34,211,238,.65) !important;
    color: white !important; font-weight: 700 !important;
    background: linear-gradient(135deg, rgba(8,145,178,.35), rgba(15,23,42,.92)) !important;
}
.stButton > button:hover { border-color: #67e8f9 !important; box-shadow: 0 0 22px rgba(34,211,238,.35) !important; }
[data-testid="stExpander"] { border-color: rgba(34,211,238,.25) !important; background: rgba(3,15,31,.42) !important; }

.disclaimer { color: #cbd5e1; padding: .8rem 1rem; border-left: 3px solid #fbbf24; background: rgba(120,53,15,.15); border-radius: 8px; font-size: .83rem; }
.data-note { color: #94a3b8; font-size: .78rem; }

@media (max-width: 900px) {
    .analysis-grid { grid-template-columns: 1fr; }
    .prob-grid { grid-template-columns: 1fr; }
    .game-top { align-items: stretch; flex-direction: column; }
    .status-pill { align-self: flex-start; }
    .main .block-container { padding-left: .8rem; padding-right: .8rem; }
}
</style>
"""
"""MLB Quantitative Matchup & Winner Engine.

Run locally with: streamlit run app.py
"""
import html
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import streamlit as st

try:
    from streamlit_autorefresh import st_autorefresh
except ImportError:  # pragma: no cover - only used when a deployment omits the optional helper
    st_autorefresh = None


ET = ZoneInfo("America/New_York")

# Change these two numbers if you want a different daily forced-update time.
# The app also keeps live scores, lineups, weather and odds on their shorter TTLs.
DAILY_REFRESH_HOUR_ET = 8
DAILY_REFRESH_MINUTE_ET = 0
LIVE_REFRESH_SECONDS = 30

st.set_page_config(
    page_title="MLB Quantitative Matchup & Winner Engine",
    page_icon="⚾",
    layout="wide",
    initial_sidebar_state="collapsed",
)
st.markdown(full_stylesheet() + bubble_markup(), unsafe_allow_html=True)


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

    if status == "FINAL":
        summary = (
            f"This game is final. {target['name']} is shown as the result winner; the probability "
            "is no longer a pregame forecast."
        )
    elif status == "LIVE":
        summary = (
            f"The live model makes {target['name']} {lean_description(target_probability)} at "
            f"{target_probability*100:.1f}%. It starts from the current score, inning, outs and "
            "occupied bases, then simulates the innings remaining."
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
    else:
        market = (
            f"The model's fair moneyline for {target['name']} is {fmt_odds(target_fair_odds)}. "
            "No verified sportsbook price is connected, so this is a matchup projection only; "
            "the app is not claiming that a bet has positive value."
        )

    return {
        "summary": summary,
        "simulation": simulation,
        "offense": offense,
        "starters": starters,
        "bullpen": bullpen,
        "environment": environment,
        "confidence": confidence,
        "market": market,
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
        f"<div class='rationale-line'><strong>+</strong> {safe_text(reason)}</div>"
        for reason in support[:3]
    )
    risk_html = "".join(
        f"<div class='rationale-line'><strong>Risk:</strong> {safe_text(reason)}</div>"
        for reason in risks[:2]
    )

    value = prediction.get("value")
    value_label = "Market check" if value else "Fair-price context"
    market_html = (
        f"<div class='rationale-line'><strong>{safe_text(value_label)}:</strong> "
        f"{safe_text(explanation['market'])}</div>"
    )

    score_text = (
        f"Projected median score: {away['short_name']} {prediction['distribution']['median_away']:.0f}, "
        f"{home['short_name']} {prediction['distribution']['median_home']:.0f}."
    )
    rationale = f"""
    <div class="rationale-card">
        <div class="rationale-title">Model Explanation · Short Version</div>
        <div class="rationale-line"><strong>Verdict:</strong> {safe_text(explanation['summary'])}</div>
        <div class="rationale-line"><strong>Score:</strong> {safe_text(score_text)}</div>
        <div class="rationale-line"><strong>Model branches:</strong> {safe_text(explanation['simulation'])}</div>
        {support_html}
        {risk_html}
        {market_html}
        <div class="source-line">DATA QUALITY {prediction['quality_score']}/100 · {safe_text(prediction['quality_label'])} · open INSPECT MODEL DETAILS for the full calculation story</div>
    </div>
    """

    markup = f"""
    <div class="game-shell">
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
                <div class="prob-track"><span class="prob-fill" style="width:{away_pct:.1f}%"></span></div>
            </div>
            <div>
                <div class="prob-label"><span>{safe_text(home['short_name'])}</span><strong>{home_pct:.1f}%</strong></div>
                <div class="prob-track"><span class="prob-fill" style="width:{home_pct:.1f}%"></span></div>
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


def render_advanced(
    prediction: dict[str, Any], weather: dict[str, Any], lineup: dict[str, Any]
) -> None:
    game = prediction["game"]
    explanation = build_model_explanation(prediction, weather, lineup)
    with st.expander(
        f"Inspect full model explanation · {game['away']['short_name']} at {game['home']['short_name']}",
        expanded=False,
    ):
        st.markdown("#### How the model reached this probability")
        st.info(explanation["summary"])
        st.markdown(f"**1. Simulation and second opinion**  \n{explanation['simulation']}")
        st.markdown(f"**2. Team offense**  \n{explanation['offense']}")
        st.markdown(f"**3. Starting pitchers**  \n{explanation['starters']}")
        st.markdown(f"**4. Bullpens**  \n{explanation['bullpen']}")
        st.markdown(f"**5. Park and weather**  \n{explanation['environment']}")
        st.markdown(f"**6. Confidence and missing information**  \n{explanation['confidence']}")
        st.markdown(f"**7. Sportsbook-value test**  \n{explanation['market']}")
        st.warning(f"What would make the model reconsider: {explanation['changes']}")

        st.markdown("#### Numerical model details")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric(
            "Projected runs",
            f"{prediction['projected_away_runs']:.2f}–{prediction['projected_home_runs']:.2f}",
        )
        c2.metric("Park run factor", f"{prediction['park_factor']:.3f}")
        c3.metric("Weather factor", f"{prediction['weather_factor']:.3f}")
        c4.metric("Model disagreement", f"{prediction['model_agreement_gap']*100:.1f} pp")

        left, middle, right = st.columns(3)
        with left:
            st.markdown("#### Bull case")
            for item in prediction["support"]:
                st.markdown(f"- {item}")
        with middle:
            st.markdown("#### Bear case")
            for item in prediction["risks"]:
                st.markdown(f"- {item}")
        with right:
            st.markdown("#### Invalidation conditions")
            for item in prediction["invalidation"]:
                st.markdown(f"- {item}")

        st.markdown("#### Market and simulation")
        distribution = prediction["distribution"]
        market_columns = st.columns(4)
        market_columns[0].metric("Fair away ML", fmt_odds(prediction["fair_away_odds"]))
        market_columns[1].metric("Fair home ML", fmt_odds(prediction["fair_home_odds"]))
        market_columns[2].metric(
            f"Over {distribution['total_line']}", f"{distribution['over_probability']*100:.1f}%"
        )
        market_columns[3].metric(
            f"Under {distribution['total_line']}", f"{distribution['under_probability']*100:.1f}%"
        )

        away_lineup = lineup.get("away") or {}
        home_lineup = lineup.get("home") or {}
        st.markdown(
            f"**Lineups:** {game['away']['short_name']} "
            f"{'confirmed' if away_lineup.get('confirmed') else 'not confirmed'} · "
            f"{game['home']['short_name']} "
            f"{'confirmed' if home_lineup.get('confirmed') else 'not confirmed'}"
        )
        if away_lineup.get("names") or home_lineup.get("names"):
            lc1, lc2 = st.columns(2)
            lc1.markdown("**Away batting order**\n\n" + "\n".join(f"{i+1}. {name}" for i, name in enumerate(away_lineup.get("names", []))))
            lc2.markdown("**Home batting order**\n\n" + "\n".join(f"{i+1}. {name}" for i, name in enumerate(home_lineup.get("names", []))))


now_et = datetime.now(ET)
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

with st.sidebar:
    st.markdown("### ⚙️ Terminal Controls")
    selected_date = st.date_input(
        "Slate date",
        min_value=today_et,
        max_value=today_et + timedelta(days=7),
        key="slate_date",
        help="The live prediction screen is intentionally limited to current and upcoming slates.",
    )
    simulations = st.select_slider(
        "Monte Carlo simulations",
        options=[10_000, 20_000, 30_000, 50_000, 75_000],
        value=30_000,
    )
    auto_refresh = st.toggle("Auto-refresh live games every 30 seconds", value=True)
    if st.button("🔄 Force complete data refresh", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
    st.markdown("---")
    st.markdown("### Data Connections")
    st.success("MLB + Baseball Savant enabled")
    st.success("Game-time weather enabled")
    if odds_api_key:
        st.success("Sportsbook comparison enabled")
    else:
        st.info("Sportsbook odds disabled until an API key is added")
    st.markdown("---")
    st.markdown("### Scheduled Update")
    st.success(
        f"Daily forced refresh: {scheduled_today.strftime('%-I:%M %p ET')}"
    )
    st.caption(f"Next scheduled update: {next_update.strftime('%a, %b %-d at %-I:%M %p ET')}")
    st.caption(
        "To change the time, edit DAILY_REFRESH_HOUR_ET and "
        "DAILY_REFRESH_MINUTE_ET near the top of app.py."
    )

if st_autorefresh is not None:
    milliseconds_to_daily_update = max(
        1_000, int((next_update - now_et).total_seconds() * 1_000)
    )
    refresh_interval = (
        LIVE_REFRESH_SECONDS * 1_000
        if auto_refresh
        else min(milliseconds_to_daily_update, 3_600_000)
    )
    st_autorefresh(interval=refresh_interval, limit=None, key="terminal_clock_refresh")

as_of = selected_date.isoformat()
st.markdown(
    f"""
    <div class="hero-card">
        <div class="hero-title">⚾ MLB Quantitative Matchup & Winner Engine</div>
        <div class="hero-sub">Real-source slate predictions · transparent matchup components · live game-state simulations</div>
        <div class="hero-meta">SLATE {safe_text(selected_date.strftime('%A · %B %-d, %Y'))} · {simulations:,} SIMULATIONS PER GAME · DAILY FORCED UPDATE {safe_text(scheduled_today.strftime('%-I:%M %p ET'))}</div>
    </div>
    """,
    unsafe_allow_html=True,
)
st.markdown(
    "<div class='disclaimer'><strong>Probabilities, not promises.</strong> Every outcome can lose. "
    "The app reports uncertainty, leaves missing fields missing and does not label anything a lock or guarantee. "
    "Only risk money you can afford to lose.</div>",
    unsafe_allow_html=True,
)

try:
    with st.spinner("Syncing the MLB slate and official game states…"):
        games = cached_schedule(as_of)
except DataSourceError as exc:
    st.error(f"The MLB schedule feed is currently unavailable: {exc}")
    st.stop()

if not games:
    st.info("No MLB games were returned for this date.")
    st.stop()

season = selected_date.year
team_ids = tuple(sorted({int(game[side]["id"]) for game in games for side in ("away", "home") if game[side].get("id")}))
pitcher_ids = tuple(sorted({int(game[side]["pitcher_id"]) for game in games for side in ("away", "home") if game[side].get("pitcher_id")}))
game_pks = tuple(game["game_pk"] for game in games)

with st.spinner("Building real-stat pitcher, offense, bullpen, park and weather profiles…"):
    try:
        team_stats = cached_team_stats(season, as_of)
    except DataSourceError as exc:
        st.error(f"Team statistics are required for projections and could not be loaded: {exc}")
        st.stop()
    if not team_stats:
        st.error("Team statistics were empty. Predictions were withheld instead of substituting invented data.")
        st.stop()

    pitcher_profiles = cached_pitchers(pitcher_ids, season, as_of)
    bullpen_stats = cached_bullpens(team_ids, season)
    try:
        pitcher_statcast = cached_statcast(season)
    except DataSourceError:
        pitcher_statcast = {}
    try:
        park_factors = cached_park_factors(season)
    except DataSourceError:
        park_factors = {}
    weather_by_game = cached_weather(games)
    lineups_by_game = cached_lineups(game_pks)
    try:
        odds_events = cached_odds(odds_api_key) if odds_api_key else []
    except DataSourceError:
        odds_events = []

predictions: list[dict[str, Any]] = []
for game in games:
    weather = weather_by_game.get(
        game["game_pk"], {"available": False, "controlled": False, "run_multiplier": 1.0}
    )
    lineup = lineups_by_game.get(game["game_pk"], {})
    odds = match_moneyline_odds(game, odds_events) if odds_events else None
    predictions.append(
        build_game_prediction(
            game,
            team_stats,
            pitcher_profiles,
            pitcher_statcast,
            bullpen_stats,
            park_factors,
            weather,
            lineup,
            odds,
            simulations=simulations,
        )
    )

priority = {"LIVE": 0, "PREVIEW": 1, "FINAL": 2}
predictions.sort(
    key=lambda prediction: (
        priority[prediction["game"]["live"]["status"]],
        prediction["game"].get("game_datetime_utc") or datetime.max.replace(tzinfo=ET),
    )
)

live_count = sum(p["game"]["live"]["status"] == "LIVE" for p in predictions)
preview_count = sum(p["game"]["live"]["status"] == "PREVIEW" for p in predictions)
final_count = sum(p["game"]["live"]["status"] == "FINAL" for p in predictions)
st.markdown("<div class='section-title'>📊 Complete Slate Breakdown & Model Winner Leans</div>", unsafe_allow_html=True)
st.markdown(
    f"<div class='section-sub'>{len(predictions)} games · {live_count} live · {preview_count} upcoming · {final_count} final · refreshed {datetime.now(ET).strftime('%-I:%M:%S %p ET')}</div>",
    unsafe_allow_html=True,
)

for prediction in predictions:
    game_pk = prediction["game"]["game_pk"]
    weather = weather_by_game.get(game_pk, {})
    lineup = lineups_by_game.get(game_pk, {})
    st.markdown(render_game(prediction, weather, lineup), unsafe_allow_html=True)
    render_advanced(prediction, weather, lineup)

st.markdown("---")
with st.expander("Methodology, data sources and important limitations", expanded=False):
    st.markdown(
        """
The app uses an interpretable ensemble rather than presenting an unvalidated model as “AI.” Pregame run estimates combine season-to-date and recent team offense, opposing starter ERA/FIP/xERA, bullpen relief splits, fielding, a rolling three-year park factor, game-time weather and home-field context. A negative-binomial Monte Carlo simulation produces a score distribution; its winner probability is blended with a separate record-based estimate and shrunk toward 50% to acknowledge uncertainty.

Current limits:

- Confirmed lineups are detected, but this version does not yet rebuild team offense batter-by-batter.
- Bullpen quality uses relief splits; individual reliever availability and warm-up data are not yet modeled.
- Without an odds API key, the app cannot calculate real market edge, expected value or line movement.
- The model must be walk-forward backtested and calibrated before anyone treats its estimates as proven betting signals.
        """
    )
    st.markdown("**Primary sources**")
    for name, url in SOURCE_LINKS.items():
        st.markdown(f"- [{name}]({url})")
    st.caption("Open-Meteo weather data requires attribution under its published license. MLB and Statcast data remain subject to MLB terms and notices.")
