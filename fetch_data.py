import json
from datetime import datetime
import requests


def get_advanced_slate():
  # Pull schedule with full season pitching stats
  url = "https://statsapi.mlb.com/api/v1/schedule?sportId=1&hydrate=probablePitcher(stats(type=season)),team,lineups"
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

    # Extract pitcher stats helper
    def extract_stats(pitcher_dict):
      stats = {"era": 4.50, "whip": 1.30, "so": 0, "ip": 1.0}
      for stat_group in pitcher_dict.get("stats", []):
        if stat_group.get("type", {}).get("displayName") == "season":
          s = stat_group.get("splits", [{}])[0].get("stat", {})
          stats["era"] = float(s.get("era", 4.50))
          stats["whip"] = float(s.get("whip", 1.30))
          stats["so"] = int(s.get("strikeOuts", 0))
          stats["ip"] = max(float(s.get("inningsPitched", 1.0)), 1.0)
      stats["k_per_ip"] = round(stats["so"] / stats["ip"], 2)
      return stats

    away_stats = extract_stats(away_p)
    home_stats = extract_stats(home_p)

    # ---------------- QUANTITATIVE MODEL CALCULATIONS ----------------
    # Base win rate derived from starting pitcher ERA/WHIP differential
    away_p_score = away_stats["era"] + (away_stats["whip"] * 2)
    home_p_score = home_stats["era"] + (home_stats["whip"] * 2)

    # Lower score is better for pitching
    pitching_diff = home_p_score - away_p_score
    away_win_prob = round(50 + (pitching_diff * 8), 1)
    away_win_prob = max(20.0, min(80.0, away_win_prob))
    home_win_prob = round(100 - away_win_prob, 1)

    # First 5 Innings (F5) Edge Calculation
    if away_win_prob >= 58.0:
      f5_edge = f"{away.get('team', {}).get('name')} F5 Moneyline"
      confidence = "HIGH"
    elif home_win_prob >= 58.0:
      f5_edge = f"{home.get('team', {}).get('name')} F5 Moneyline"
      confidence = "HIGH"
    else:
      f5_edge = "No High-Value Edge (Pass/Live Bet)"
      confidence = "MEDIUM"

    # Pitcher Strikeout Prop Target
    k_target = "None"
    if away_stats["k_per_ip"] >= 1.0:
      k_target = f"{away_p.get('fullName', 'Away Starter')} OVER K-Prop ({away_stats['k_per_ip']} K/IP)"
    elif home_stats["k_per_ip"] >= 1.0:
      k_target = f"{home_p.get('fullName', 'Home Starter')} OVER K-Prop ({home_stats['k_per_ip']} K/IP)"

    games_data.append({
        "game_id": g.get("gamePk"),
        "status": g.get("status", {}).get("detailedState", "Scheduled"),
        "venue": g.get("venue", {}).get("name", "Unknown"),
        "away_team": away.get("team", {}).get("name"),
        "away_record": (
            f"{away.get('leagueRecord', {}).get('wins', 0)}-{away.get('leagueRecord', {}).get('losses', 0)}"
        ),
        "away_pitcher": away_p.get("fullName", "TBD"),
        "away_era": away_stats["era"],
        "away_whip": away_stats["whip"],
        "away_win_prob": away_win_prob,
        "home_team": home.get("team", {}).get("name"),
        "home_record": (
            f"{home.get('leagueRecord', {}).get('wins', 0)}-{home.get('leagueRecord', {}).get('losses', 0)}"
        ),
        "home_pitcher": home_p.get("fullName", "TBD"),
        "home_era": home_stats["era"],
        "home_whip": home_stats["whip"],
        "home_win_prob": home_win_prob,
        "f5_edge": f5_edge,
        "confidence": confidence,
        "strikeout_prop": k_target,
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
