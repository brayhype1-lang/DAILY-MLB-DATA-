import json
import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="MLB Daily Data Tracker", page_icon="⚾", layout="wide"
)

st.title("⚾ Daily MLB Schedule & Data Dashboard")

try:
  # Load the JSON file created by GitHub Actions
  with open("daily_mlb_data.json", "r") as f:
    payload = json.load(f)

  st.success(f"**Last Data Update:** {payload.get('last_updated', 'N/A')}")

  # Parse schedule games
  dates = payload.get("mlb_schedule", {}).get("dates", [])

  if dates:
    games = dates[0].get("games", [])
    st.subheader(f"Scheduled Games for Today ({len(games)} Games)")

    game_list = []
    for game in games:
      game_list.append({
          "Status": game.get("status", {}).get("detailedState", "Scheduled"),
          "Away Team": game.get("teams", {})
          .get("away", {})
          .get("team", {})
          .get("name"),
          "Home Team": game.get("teams", {})
          .get("home", {})
          .get("team", {})
          .get("name"),
          "Venue": game.get("venue", {}).get("name"),
          "Game Time (UTC)": game.get("gameDate"),
      })

    df = pd.DataFrame(game_list)
    st.dataframe(df, use_container_width=True)
  else:
    st.info("No games scheduled or data empty for today.")

except FileNotFoundError:
  st.warning(
      "The `daily_mlb_data.json` file hasn't been generated yet. Go to the"
      " 'Actions' tab in GitHub and run the workflow once!"
  )
