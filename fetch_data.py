import json
from datetime import datetime
import pandas as pd
import requests


def get_advanced_slate():
  # MLB official API with full lineup & pitching hydrations
  url = "https://statsapi.mlb.com/api/v1/schedule?sportId=1&hydrate=probablePitcher,team,lineups,decisions"
  res = requests.get(url).json()

  games_data = []
  dates = res.get("dates", [])

  if not dates:
    return {
        "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC"),
        "total_games": 0,
        "slate": [],
    }

  for g in dates[0].get("games", []):
    away = g.get("teams", {}).get("away", {})
    home = g.get("teams", {}).get("home", {})

    away_p = away.get("probablePitcher", {})
    home_p = home.get("probablePitcher", {})

    away_p_id = away_p.get("id", None)
    home_p_id = home_p.get("id", None)

    edge_signal = "NEUTRAL / NO EDGE"
    target_bet = "PASS"

    if away_p_id and home_p_id:
      edge_signal = "STATCAST MATCHUP ACTIVE"
      target_bet = "EVALUATE STRIKEOUT PROPS OR F5 MONEYLINE"

    games_data.append({
        "game_id": g.get("gamePk"),
        "status": g.get("status", {}).get("detailedState", "Scheduled"),
        "venue": g.get("venue", {}).get("name", "Unknown"),
        "away_team": away.get("team", {}).get("name"),
        "away_record": (
            f"{away.get('leagueRecord', {}).get('wins', 0)}-{away.get('leagueRecord', {}).get('losses', 0)}"
        ),
        "away_pitcher": away_p.get("fullName", "TBD"),
        "away_pitcher_id": away_p_id,
        "home_team": home.get("team", {}).get("name"),
        "home_record": (
            f"{home.get('leagueRecord', {}).get('wins', 0)}-{home.get('leagueRecord', {}).get('losses', 0)}"
        ),
        "home_pitcher": home_p.get("fullName", "TBD"),
        "home_pitcher_id": home_p_id,
        "edge_signal": edge_signal,
        "recommended_angle": target_bet,
    })

  return {
      "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC"),
      "total_games": len(games_data),
      "slate": games_data,
  }


if __name__ == "__main__":
  data = get_advanced_slate()
  with open("daily_mlb_data.json", "w") as f:
    json.dump(data, f, indent=2)
  print(f"Data engine processed {data['total_games']} games.")
