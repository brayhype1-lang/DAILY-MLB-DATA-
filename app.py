def build_editorial_breakdown(away_team, home_team, away_stats, home_stats, park):
    woba_diff = away_stats["xwoba"] - home_stats["xwoba"]
    split_diff = home_stats["vs_lhp_wrc"] - away_stats["vs_lhp_wrc"] if home_stats.get("starter_hand") == "L" else 0
    
    base_home_prob = 0.52 + (woba_diff * 0.8) + (split_diff * 0.001) + (0.03 if park["run_mult"] > 1.05 else -0.02)
    home_prob = min(0.85, max(0.15, base_home_prob))
    away_prob = 1.0 - home_prob

    if home_prob >= away_prob:
        target, win_p = home_team, home_prob * 100
        edge_pitcher, other_pitcher = home_stats, away_stats
        edge_team_name, other_team_name = home_team, away_team
    else:
        target, win_p = away_team, away_prob * 100
        edge_pitcher, other_pitcher = away_stats, home_stats
        edge_team_name, other_team_name = away_team, home_team

    narrative = (
        f"The model projects <span class='highlight-txt'>{target}</span> to secure the victory with a "
        f"{win_p:.1f}% win probability, driven by a decisive edge on the mound and favorable contact metrics. "
        f"{edge_team_name}'s starter, <span class='highlight-txt'>{edge_pitcher['pitcher']}</span>, holds a distinct advantage "
        f"in expected slugging and suppression, carrying an ERA of {edge_pitcher['era']:.2f} and an xwOBA of {edge_pitcher['xwoba']:.3f} "
        f"against <span class='highlight-txt'>{other_team_name}</span>'s lineup, which counters with a hard-hit rate of {other_pitcher['hard_hit_pct']}% "
        f"and an xwOBA of {other_pitcher['xwoba']:.3f} under <span class='highlight-txt'>{park['name']}</span> park factors ({park['weather']['weather_desc']}). "
        f"Combined with recent 10-game momentum ({edge_team_name} L10: {edge_pitcher['l10_record']} vs {other_team_name} L10: {other_pitcher['l10_record']}), "
        f"the quantitative indicators point clearly toward a <span class='highlight-txt'>{target}</span> triumph."
    )

    return {
        "target": target, "win_prob": round(win_p, 1),
        "home_prob": home_prob, "away_prob": away_prob, "narrative": narrative,
    }
