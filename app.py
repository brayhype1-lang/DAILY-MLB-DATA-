import json
import streamlit as st

st.set_page_config(
    page_title="MLB Quantitative Edge Model", page_icon="⚡", layout="wide"
)

st.title("⚡ MLB Algorithmic Edge & Prop Dashboard")

try:
  with open("daily_mlb_data.json", "r") as f:
    payload = json.load(f)

  st.caption(f"Last Model Sync: **{payload.get('last_updated')}**")
  slate = payload.get("slate", [])

  if slate:
    # ------------------ TOP SLATE HIGHLIGHTS ------------------
    st.markdown("## 🎯 Top High-Confidence Locks Today")

    high_conf_games = [g for g in slate if g["confidence"] == "HIGH"]

    if high_conf_games:
      c1, c2 = st.columns(2)
      for idx, game in enumerate(high_conf_games[:4]):
        col = c1 if idx % 2 == 0 else c2
        with col:
          st.success(
              f"🔥 **{game['f5_edge']}**\n\nMatchup: {game['away_team']} @"
              f" {game['home_team']}"
          )
    else:
      st.info(
          "No extreme pitch-mismatch locks found today. Standard slate model"
          " active below."
      )

    st.markdown("---")

    # ------------------ GAME BY GAME METRICS ------------------
    st.markdown("## 📊 Full Slate Model Projections")

    for game in slate:
      with st.expander(
          f"⚾ {game['away_team']} ({game['away_win_prob']}%) @ {game['home_team']} ({game['home_win_prob']}%)"
      ):

        col1, col2, col3 = st.columns(3)

        with col1:
          st.markdown(f"### 🔵 {game['away_team']}")
          st.write(f"**Pitcher:** {game['away_pitcher']}")
          st.write(f"**ERA:** {game['away_era']} | **WHIP:** {game['away_whip']}")
          st.progress(
              int(game["away_win_prob"]),
              text=f"Win Probability: {game['away_win_prob']}%",
          )

        with col2:
          st.markdown(f"### 🔴 {game['home_team']}")
          st.write(f"**Pitcher:** {game['home_pitcher']}")
          st.write(f"**ERA:** {game['home_era']} | **WHIP:** {game['home_whip']}")
          st.progress(
              int(game["home_win_prob"]),
              text=f"Win Probability: {game['home_win_prob']}%",
          )

        with col3:
          st.markdown("### 🎯 Model Outputs")
          st.write(f"**Primary Angle:** {game['f5_edge']}")
          st.write(f"**Model Confidence:** {game['confidence']}")
          st.write(f"**K-Prop Target:** {game['strikeout_prop']}")

  else:
    st.warning("No games found on today's slate.")

except FileNotFoundError:
  st.error(
      "Data payload missing. Trigger the workflow in your GitHub Actions tab!"
  )
