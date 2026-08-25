import json
from datetime import datetime
import requests


def get_pitcher_season_stats(person_id):
  """Fetch actual season ERA and WHIP directly from MLB's player stats endpoint."""
  if not person_id:
    return 4.20, 1.28  # Default baseline if no starter is announced

  url = f"https://statsapi.mlb.com/api/v1/people/{person_id}/stats?stats=statsSingleSeason&group=pitching&season=2026"
  try:
    res = requests.get(url, timeout=5).json()
    stats_list = res.get("stats", [])
    if stats_list and stats_list[0].get("splits"):
      stat = stats_list[0]["splits"][0]["stat"]
      era = float(stat.get("era", 4.20))
      whip = float(stat.get("whip", 1.28))
      return era, whip
  except Exception:
    pass

  return 4.20, 1.28


def fetch_live_slate():
  # 1. Fetch today's schedule with team and pitcher IDs
  url = "https://statsapi.mlb.com/api/v1/schedule?sportId=1&hydrate=probablePitcher,team"
  res = requests.get(url).json()

  games_data = []
  dates = res.get("dates", [])

  if not dates:
    return {
        "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC"),
        "slate": [],
    }

  for g in dates[0].get("games", []):
    away = g.get("teams", {}).get("away", {})
    home = g.get("teams", {}).get("home", {})

    away_p = away.get("probablePitcher", {})
    home_p = home.get("probablePitcher", {})

    # 2. Fetch individual pitcher statistics using person IDs
    away_p_id = away_p.get("id")
    home_p_id = home_p.get("id")

    away_era, away_whip = get_pitcher_season_stats(away_p_id)
    home_era, home_whip = get_pitcher_season_stats(home_p_id)

    # 3. Calculate dynamic pitching quality rating
    # Lower rating indicates stronger pitching performance
    away_rating = (away_era * 0.65) + (away_whip * 3.2)
    home_rating = (home_era * 0.65) + (home_whip * 3.2)

    # Calculate differential (incorporating a +3% home field baseline advantage)
    rating_diff = home_rating - away_rating
    away_win_prob = round(47.0 + (rating_diff * 11.5), 1)
    away_win_prob = max(25.0, min(75.0, away_win_prob))
    home_win_prob = round(100.0 - away_win_prob, 1)

    # 4. Determine market edge angle
    if away_win_prob >= 55.5:
      rec_bet = f"{away.get('team', {}).get('name')} F5 Moneyline"
      conf = "HIGH"
    elif home_win_prob >= 55.5:
      rec_bet = f"{home.get('team', {}).get('name')} F5 Moneyline"
      conf = "HIGH"
    else:
      rec_bet = "NO EDGE / PASS"
      conf = "MEDIUM"

    games_data.append({
        "game_id": g.get("gamePk"),
        "away_team": away.get("team", {}).get("name"),
        "away_pitcher": away_p.get("fullName", "Unannounced Starter"),
        "away_era": away_era,
        "away_whip": away_whip,
        "away_prob": away_win_prob,
        "home_team": home.get("team", {}).get("name"),
        "home_pitcher": home_p.get("fullName", "Unannounced Starter"),
        "home_era": home_era,
        "home_whip": home_whip,
        "home_prob": home_win_prob,
        "recommended_bet": rec_bet,
        "confidence": conf,
    })

  return {
      "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC"),
      "slate": games_data,
  }


if __name__ == "__main__":
  payload = fetch_live_slate()
  with open("daily_mlb_data.json", "w") as f:
    json.dump(payload, f, indent=2)
  print(f"Processed {len(payload['slate'])} games with live pitcher stats.")
