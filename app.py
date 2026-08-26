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
import random


def bubble_markup(count: int = 24) -> str:
    """Return deterministic decorative bubbles so reruns do not jump around."""
    rng = random.Random(937)
    bubbles: list[str] = []
    for _ in range(count):
        size = rng.uniform(18, 94)
        left = rng.uniform(-3, 103)
        duration = rng.uniform(18, 42)
        delay = rng.uniform(0, 32)
        opacity = rng.uniform(0.08, 0.27)
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
    [data-testid="stMainBlockContainer"] { padding-left: .8rem; padding-right: .8rem; }
}

@media (max-width: 620px) {
    .insights-grid { grid-template-columns: 1fr; }
    .top-nav-sub, .top-nav-sync small { display: none; }
    .hero-card { padding: 1.1rem; }
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
st.title("⚾ MLB Quantitative Matchup & Winner Engine")
st.caption("Live MLB data · transparent probabilities · detailed matchup research")


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


def team_accents(team_id: int | None) -> tuple[str, str]:
    return TEAM_COLORS.get(int(team_id or 0), ("#22D3EE", "#5EEAD4"))


def matchup_style(game: dict[str, Any]) -> str:
    away_primary, away_secondary = team_accents(game["away"].get("id"))
    home_primary, home_secondary = team_accents(game["home"].get("id"))
    return (
        f"--away-primary:{away_primary};--away-secondary:{away_secondary};"
        f"--home-primary:{home_primary};--home-secondary:{home_secondary};"
    )


def confidence_class(label: str) -> str:
    normalized = (label or "").lower()
    if normalized.startswith("high"):
        return "quality-high"
    if normalized.startswith("moderate"):
        return "quality-moderate"
    return "quality-limited"


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
    """Render one compact scoreboard tile using only stable Streamlit widgets."""
    game = prediction["game"]
    away, home = game["away"], game["home"]
    live = game["live"]
    status = live["status"]
    game_dt = game.get("game_datetime_utc")
    start_text = game_dt.astimezone(ET).strftime("%-I:%M %p ET") if game_dt else "Time TBD"

    if status == "LIVE":
        status_text = f"🔴 {live.get('status_label') or 'LIVE'}"
        away_value = str(int(live.get("away_runs") or 0))
        home_value = str(int(live.get("home_runs") or 0))
        outs = int(live.get("outs") or 0)
        context_text = f"{outs} {'out' if outs == 1 else 'outs'} · {game['venue'].get('name') or 'Venue TBD'}"
    elif status == "FINAL":
        status_text = "✅ FINAL"
        away_value = str(int(live.get("away_runs") or 0))
        home_value = str(int(live.get("home_runs") or 0))
        context_text = game["venue"].get("name") or "Completed"
    else:
        status_text = f"🕒 {start_text}"
        away_value = f"{prediction['away_probability']*100:.0f}%"
        home_value = f"{prediction['home_probability']*100:.0f}%"
        context_text = (
            f"{away.get('pitcher_name') or 'Starter TBD'} vs "
            f"{home.get('pitcher_name') or 'Starter TBD'}"
        )

    with st.container(border=True):
        st.caption(status_text)
        for team, value in ((away, away_value), (home, home_value)):
            logo_column, team_column, value_column = st.columns(
                [0.16, 1.0, 0.22], vertical_alignment="center"
            )
            with logo_column:
                st.image(team["logo"], width=25)
            with team_column:
                st.markdown(f"**{team['short_name']}**")
                st.caption(f"{int(team.get('wins') or 0)}-{int(team.get('losses') or 0)}")
            with value_column:
                st.markdown(f"**{value}**")

        st.caption(context_text)
        st.caption(
            f"Lean: {prediction['target_name']} {prediction['target_probability']*100:.1f}% · "
            f"Data {prediction['quality_score']}/100"
        )
        analysis_is_open = st.session_state.get("open_game_pk") == game["game_pk"]
        st.button(
            "Close details" if analysis_is_open else "Game details",
            key=f"game_center_toggle_{game['game_pk']}",
            on_click=toggle_game_analysis,
            args=(game["game_pk"],),
            type="primary" if analysis_is_open else "secondary",
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


def render_game_center(predictions: list[dict[str, Any]]) -> None:
    live_games = [p for p in predictions if p["game"]["live"]["status"] == "LIVE"]
    upcoming_games = [p for p in predictions if p["game"]["live"]["status"] == "PREVIEW"]
    final_games = [p for p in predictions if p["game"]["live"]["status"] == "FINAL"]

    st.subheader("Today's Game Center")
    st.caption(
        f"{len(predictions)} games · {len(live_games)} live · "
        f"{len(upcoming_games)} upcoming · {len(final_games)} final"
    )

    live_tab, upcoming_tab, final_tab = st.tabs(
        [
            f"🔴 Live ({len(live_games)})",
            f"🕒 Upcoming ({len(upcoming_games)})",
            f"✅ Final ({len(final_games)})",
        ]
    )
    with live_tab:
        render_score_card_grid(live_games, "No games are live right now.")
    with upcoming_tab:
        render_score_card_grid(upcoming_games, "No upcoming games remain on this slate.")
    with final_tab:
        render_score_card_grid(final_games, "No games are final yet.")


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
    st.subheader("Daily Slate Insights")
    insight_columns = st.columns(4)
    insight_data = [
        (
            "🔥 Strongest lean",
            f"{strongest['target_name']} {strongest['target_probability']*100:.1f}%",
            f"{strongest_game['away']['short_name']} at {strongest_game['home']['short_name']}",
        ),
        (
            "⚖️ Closest matchup",
            f"{closest_game['away']['short_name']} {closest['away_probability']*100:.1f}%",
            f"{closest_game['home']['short_name']} {closest['home_probability']*100:.1f}%",
        ),
        (
            "📈 Highest total",
            f"{highest_total['projected_away_runs'] + highest_total['projected_home_runs']:.1f} runs",
            f"{total_game['away']['short_name']} at {total_game['home']['short_name']}",
        ),
        (
            "✅ Best data quality",
            f"{best_quality['quality_score']}/100",
            f"{quality_game['away']['short_name']} at {quality_game['home']['short_name']}",
        ),
    ]
    for column, (label, value, detail) in zip(insight_columns, insight_data):
        with column:
            with st.container(border=True):
                st.caption(label)
                st.markdown(f"#### {value}")
                st.caption(detail)


def render_compact_game_row(prediction: dict[str, Any], weather: dict[str, Any]) -> None:
    game = prediction["game"]
    away, home = game["away"], game["home"]
    live = game["live"]
    status = live["status"]
    game_dt = game.get("game_datetime_utc")
    start_text = game_dt.astimezone(ET).strftime("%-I:%M %p ET") if game_dt else "Time TBD"

    if status == "LIVE":
        status_class = "live"
        status_text = live.get("status_label") or "Live"
        score_label = "Current score"
        score_value = f"{away['short_name']} {int(live.get('away_runs') or 0)} · {home['short_name']} {int(live.get('home_runs') or 0)}"
    elif status == "FINAL":
        status_class = "final"
        status_text = "Final"
        score_label = "Final score"
        score_value = f"{away['short_name']} {int(live.get('away_runs') or 0)} · {home['short_name']} {int(live.get('home_runs') or 0)}"
    else:
        status_class = "preview"
        status_text = "Upcoming"
        score_label = "Projected runs"
        score_value = f"{away['short_name']} {prediction['projected_away_runs']:.1f} · {home['short_name']} {prediction['projected_home_runs']:.1f}"

    away_pct = prediction["away_probability"] * 100.0
    home_pct = prediction["home_probability"] * 100.0
    fair_odds = (
        prediction["fair_away_odds"]
        if prediction["target_side"] == "away"
        else prediction["fair_home_odds"]
    )
    context = weather_text(weather, game["venue"])
    with st.container(border=True):
        matchup_column, pick_column, score_column = st.columns([1.6, 0.75, 0.85])
        with matchup_column:
            st.markdown(f"#### {away['name']} at {home['name']}")
            st.caption(
                f"{status_text} · {start_text} · "
                f"{away.get('pitcher_name') or 'Starter TBD'} vs "
                f"{home.get('pitcher_name') or 'Starter TBD'} · {context}"
            )
            st.progress(
                prediction["away_probability"],
                text=f"{away['short_name']} {away_pct:.1f}%  |  {home['short_name']} {home_pct:.1f}%",
            )
        with pick_column:
            st.metric("Model lean", prediction["target_name"], f"{prediction['target_probability']*100:.1f}%")
            st.caption(f"Fair moneyline {fmt_odds(fair_odds)}")
        with score_column:
            st.metric(score_label, score_value)
            st.caption(f"Data quality: {prediction['quality_score']}/100 · {prediction['quality_label']}")


def render_advanced(
    prediction: dict[str, Any], weather: dict[str, Any], lineup: dict[str, Any]
) -> None:
    game = prediction["game"]
    explanation = build_model_explanation(prediction, weather, lineup)
    target_side = prediction["target_side"]
    target_fair_odds = (
        prediction["fair_away_odds"] if target_side == "away" else prediction["fair_home_odds"]
    )
    with st.expander(
        f"Full analysis · {game['away']['short_name']} at {game['home']['short_name']}",
        expanded=True,
    ):
        st.markdown("### Matchup at a glance")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Model lean", f"{prediction['target_probability']*100:.1f}%")
        c2.metric(
            "Projected score",
            f"{game['away']['short_name']} {prediction['projected_away_runs']:.1f} · "
            f"{game['home']['short_name']} {prediction['projected_home_runs']:.1f}",
        )
        c3.metric("Fair moneyline", fmt_odds(target_fair_odds))
        c4.metric(
            "Data quality",
            f"{prediction['quality_score']}/100",
            prediction["quality_label"],
        )
        st.caption(
            f"Model disagreement {prediction['model_agreement_gap']*100:.1f} points · "
            f"park {prediction['park_factor']:.3f} · weather {prediction['weather_factor']:.3f}"
        )

        with st.container(border=True):
            st.markdown(f"#### Verdict · {prediction['target_name']}")
            st.write(explanation["summary"])

        why_tab, pitching_tab, context_tab, market_tab = st.tabs(
            ["🎯 Why the Pick", "⚾ Pitching", "🌤️ Game Context", "💵 Market & Risks"]
        )

        with why_tab:
            why_left, why_right = st.columns(2)
            with why_left:
                with st.container(border=True):
                    st.markdown("#### Probability build")
                    st.write(explanation["simulation"])
            with why_right:
                with st.container(border=True):
                    st.markdown("#### Offensive matchup")
                    st.write(explanation["offense"])

            st.markdown("#### Strongest reasons behind the lean")
            support_columns = st.columns(min(3, max(1, len(prediction["support"]))))
            for index, item in enumerate(prediction["support"]):
                with support_columns[index % len(support_columns)]:
                    with st.container(border=True):
                        st.markdown(f"**Reason {index + 1}**")
                        st.write(item)

        with pitching_tab:
            starter_column, bullpen_column = st.columns(2)
            with starter_column:
                with st.container(border=True):
                    st.markdown("#### Starting-pitcher comparison")
                    st.write(explanation["starters"])
            with bullpen_column:
                with st.container(border=True):
                    st.markdown("#### Bullpen comparison")
                    st.write(explanation["bullpen"])

            starter_metrics = st.columns(4)
            starter_metrics[0].metric(
                f"{game['away']['short_name']} starter grade",
                f"{prediction['away_starter']['quality_ra9']:.2f}",
                help="Blended ERA/FIP/xERA/WHIP estimate; lower is better.",
            )
            starter_metrics[1].metric(
                f"{game['home']['short_name']} starter grade",
                f"{prediction['home_starter']['quality_ra9']:.2f}",
                help="Blended ERA/FIP/xERA/WHIP estimate; lower is better.",
            )
            starter_metrics[2].metric(
                f"{game['away']['short_name']} bullpen",
                f"{prediction['away_bullpen']['quality_ra9']:.2f}",
                help="Blended relief-pitching RA9; lower is better.",
            )
            starter_metrics[3].metric(
                f"{game['home']['short_name']} bullpen",
                f"{prediction['home_bullpen']['quality_ra9']:.2f}",
                help="Blended relief-pitching RA9; lower is better.",
            )

        with context_tab:
            context_left, context_right = st.columns(2)
            with context_left:
                with st.container(border=True):
                    st.markdown("#### Park and weather")
                    st.write(explanation["environment"])
            with context_right:
                with st.container(border=True):
                    st.markdown("#### Confidence and missing data")
                    st.write(explanation["confidence"])

            away_lineup = lineup.get("away") or {}
            home_lineup = lineup.get("home") or {}
            lineup_status = (
                f"{game['away']['short_name']}: "
                f"{'confirmed' if away_lineup.get('confirmed') else 'not confirmed'} · "
                f"{game['home']['short_name']}: "
                f"{'confirmed' if home_lineup.get('confirmed') else 'not confirmed'}"
            )
            st.markdown(f"#### Lineups · {lineup_status}")
            if away_lineup.get("names") or home_lineup.get("names"):
                lc1, lc2 = st.columns(2)
                with lc1:
                    with st.container(border=True):
                        st.markdown(f"**{game['away']['name']} batting order**")
                        st.markdown(
                            "\n".join(
                                f"{i+1}. {name}"
                                for i, name in enumerate(away_lineup.get("names", []))
                            )
                            or "Not available"
                        )
                with lc2:
                    with st.container(border=True):
                        st.markdown(f"**{game['home']['name']} batting order**")
                        st.markdown(
                            "\n".join(
                                f"{i+1}. {name}"
                                for i, name in enumerate(home_lineup.get("names", []))
                            )
                            or "Not available"
                        )

        with market_tab:
            distribution = prediction["distribution"]
            with st.container(border=True):
                st.markdown("#### Price interpretation")
                st.write(explanation["market"])

            market_columns = st.columns(4)
            market_columns[0].metric("Fair away ML", fmt_odds(prediction["fair_away_odds"]))
            market_columns[1].metric("Fair home ML", fmt_odds(prediction["fair_home_odds"]))
            market_columns[2].metric(
                f"Over {distribution['total_line']}",
                f"{distribution['over_probability']*100:.1f}%",
            )
            market_columns[3].metric(
                f"Under {distribution['total_line']}",
                f"{distribution['under_probability']*100:.1f}%",
            )

            risk_left, risk_right = st.columns(2)
            with risk_left:
                with st.container(border=True):
                    st.markdown("#### Bear case")
                    for item in prediction["risks"]:
                        st.markdown(f"- {item}")
            with risk_right:
                with st.container(border=True):
                    st.markdown("#### What would change the pick")
                    for item in prediction["invalidation"]:
                        st.markdown(f"- {item}")


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

with st.container(border=True):
    nav_brand, nav_date, nav_sync = st.columns([1.55, 1.35, 1.0], vertical_alignment="center")
    with nav_brand:
        st.markdown("#### ⚾ MLB Quant Terminal")
        st.caption("Daily matchup intelligence")
    with nav_date:
        previous_day, date_picker, next_day = st.columns([0.42, 2.4, 0.42], vertical_alignment="center")
        current_slate_date = st.session_state.get("slate_date", today_et)
        with previous_day:
            st.button(
                "‹",
                key="previous_slate_day",
                use_container_width=True,
                disabled=current_slate_date <= today_et,
                on_click=shift_slate_date,
                args=(-1,),
                help="Previous slate",
            )
        with date_picker:
            selected_date = st.date_input(
                "Slate date",
                min_value=today_et,
                max_value=today_et + timedelta(days=7),
                key="slate_date",
                label_visibility="collapsed",
                help="Choose today's slate or an upcoming MLB date.",
            )
        with next_day:
            st.button(
                "›",
                key="next_slate_day",
                use_container_width=True,
                disabled=current_slate_date >= today_et + timedelta(days=7),
                on_click=shift_slate_date,
                args=(1,),
                help="Next slate",
            )
    with nav_sync:
        sync_copy, sync_button = st.columns([1.45, 0.72], vertical_alignment="center")
        with sync_copy:
            st.caption(f"🟢 LIVE DATA SYNC\n\n{now_et.strftime('%-I:%M:%S %p ET')}")
        with sync_button:
            if st.button("↻", key="top_refresh", use_container_width=True, help="Refresh all data"):
                st.cache_data.clear()
                st.rerun()

with st.sidebar:
    st.markdown("### ⚙️ Model Controls")
    simulations = st.select_slider(
        "Monte Carlo simulations",
        options=[10_000, 20_000, 30_000, 50_000, 75_000],
        value=30_000,
    )
    st.caption("Use either refresh button for the newest live score and lineup data.")
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

as_of = selected_date.isoformat()
with st.container(border=True):
    st.caption("DAILY MLB COMMAND CENTER")
    st.header(f"{selected_date.strftime('%A, %B %-d')} Slate")
    st.write("Live scores · upcoming games · transparent probabilities · full matchup research")
    st.caption(
        f"{simulations:,} simulations per game · daily forced update "
        f"{scheduled_today.strftime('%-I:%M %p ET')}"
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
    # These feeds are independent. Running them concurrently keeps a cold
    # Community Cloud boot inside its startup window instead of making the
    # browser wait through every network timeout one after another.
    feed_defaults: dict[str, Any] = {
        "team_stats": {},
        "pitcher_profiles": {},
        "bullpen_stats": {},
        "pitcher_statcast": {},
        "park_factors": {},
        "weather_by_game": {},
        "lineups_by_game": {},
        "odds_events": [],
    }
    feed_calls: dict[str, tuple[Any, tuple[Any, ...]]] = {
        "team_stats": (cached_team_stats, (season, as_of)),
        "pitcher_profiles": (cached_pitchers, (pitcher_ids, season, as_of)),
        "bullpen_stats": (cached_bullpens, (team_ids, season)),
        "pitcher_statcast": (cached_statcast, (season,)),
        "park_factors": (cached_park_factors, (season,)),
        "weather_by_game": (cached_weather, (games,)),
        "lineups_by_game": (cached_lineups, (game_pks,)),
    }
    if odds_api_key:
        feed_calls["odds_events"] = (cached_odds, (odds_api_key,))

    required_feed_error: Exception | None = None
    with ThreadPoolExecutor(max_workers=len(feed_calls)) as executor:
        futures = {
            name: executor.submit(function, *arguments)
            for name, (function, arguments) in feed_calls.items()
        }
        for name, future in futures.items():
            try:
                feed_defaults[name] = future.result()
            except Exception as exc:  # Each source already normalizes network errors.
                if name == "team_stats":
                    required_feed_error = exc

    if required_feed_error is not None:
        st.error(
            "Team statistics are required for projections and could not be loaded: "
            f"{required_feed_error}"
        )
        st.stop()

    team_stats = feed_defaults["team_stats"]
    if not team_stats:
        st.error("Team statistics were empty. Predictions were withheld instead of substituting invented data.")
        st.stop()

    pitcher_profiles = feed_defaults["pitcher_profiles"]
    bullpen_stats = feed_defaults["bullpen_stats"]
    pitcher_statcast = feed_defaults["pitcher_statcast"]
    park_factors = feed_defaults["park_factors"]
    weather_by_game = feed_defaults["weather_by_game"]
    lineups_by_game = feed_defaults["lineups_by_game"]
    odds_events = feed_defaults["odds_events"]

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
render_game_center(predictions)

selected_prediction = next(
    (
        prediction
        for prediction in predictions
        if prediction["game"]["game_pk"] == st.session_state.get("open_game_pk")
    ),
    None,
)
if selected_prediction is not None:
    selected_game_pk = selected_prediction["game"]["game_pk"]
    selected_title, selected_close = st.columns([5.0, 1.0], vertical_alignment="center")
    with selected_title:
        st.subheader("Selected Matchup Analysis")
    with selected_close:
        st.button(
            "Close analysis",
            key="close_selected_analysis",
            on_click=toggle_game_analysis,
            args=(selected_game_pk,),
            use_container_width=True,
        )
    render_advanced(
        selected_prediction,
        weather_by_game.get(selected_game_pk, {}),
        lineups_by_game.get(selected_game_pk, {}),
    )

render_slate_insights(predictions)
st.warning(
    "Probabilities, not promises. Every outcome can lose. The app reports uncertainty, "
    "leaves missing fields missing, and does not label anything a lock or guarantee."
)
st.subheader("Complete Matchup Research")
st.caption(
    f"{len(predictions)} games · {live_count} live · {preview_count} upcoming · "
    f"{final_count} final · refreshed {datetime.now(ET).strftime('%-I:%M:%S %p ET')}"
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
        ["Game time", "Strongest lean", "Highest data quality", "Closest matchup"],
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

if sort_mode == "Strongest lean":
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
    st.button(
        "Hide full analysis" if analysis_is_open else "View full analysis",
        key=f"toggle_analysis_{game_pk}",
        on_click=toggle_game_analysis,
        args=(game_pk,),
        help="Load the full model explanation for this matchup.",
    )
    if analysis_is_open:
        st.caption("The selected full analysis is open above Daily Slate Insights.")

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
