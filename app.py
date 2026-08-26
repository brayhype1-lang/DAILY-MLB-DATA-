# ------------------------------------------------------------------
# 5. DASHBOARD PRESENTATION & APP-STYLE SCORE CARDS
# ------------------------------------------------------------------
slate = load_full_slate()

if not slate:
    st.warning("No active games on today's MLB slate.")
else:
    evaluated_slate = []
    for g in slate:
        park = get_park_factor(g["home_team"])
        live_state = fetch_live_game_state(g["game_id"])
        analysis = build_editorial_breakdown(
            g["away_team"], g["home_team"], g["away_stats"], g["home_stats"], park, live_state=live_state
        )
        evaluated_slate.append({**g, "park": park, "analysis": analysis, "live": live_state})

    def game_sort_key(item):
        st_val = item["live"]["status"]
        priority = item["live"]["sort_priority"]
        if st_val == "LIVE":
            return (0, -priority)
        elif st_val == "PREVIEW":
            return (1, 0)
        else:
            return (2, 0)

    evaluated_slate.sort(key=game_sort_key)

    st.markdown(
        """
        <div class="hero-banner">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                <div>
                    <h1 style="margin:0; font-size: 1.7rem; font-weight: 900; color: #F8FAFC; letter-spacing: -0.02em;">⚾ MLB QUANTITATIVE INTELLIGENCE</h1>
                    <p style="margin:4px 0 0 0; color: #38BDF8; font-size: 0.88rem; font-weight: 600; font-family: 'JetBrains Mono', monospace;">LIVE SCOREBOARD • OUTS & BASERUNNER TRACKING • SMART SORTED</p>
                </div>
                <div style="text-align: right;">
                    <span style="background: rgba(56, 189, 248, 0.15); border: 1px solid rgba(56, 189, 248, 0.4); color: #38BDF8; padding: 6px 14px; border-radius: 10px; font-size: 0.78rem; font-weight: 700; font-family: 'JetBrains Mono', monospace;">
                        🟢 SYNC ACTIVE
                    </span>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Render score cards using responsive columns instead of a giant HTML string
    cols_per_row = 5
    for i in range(0, len(evaluated_slate), cols_per_row):
        row_games = evaluated_slate[i:i + cols_per_row]
        cols = st.columns(cols_per_row)
        
        for idx, g in enumerate(row_games):
            lv = g["live"]
            b1_cls = "base active" if lv.get("has_1b") else "base"
            b2_cls = "base active" if lv.get("has_2b") else "base"
            b3_cls = "base active" if lv.get("has_3b") else "base"

            bottom_info_html = ""
            if lv["status"] == "LIVE":
                bottom_info_html = f"""
                <div class="base-outs-row">
                    <div style="display: flex; align-items: center; gap: 4px;">
                        <span style="color: #64748B; font-size: 0.65rem;">BASES</span>
                        <span class="bases-diamond">
                            <span class="{b2_cls}" title="2nd Base"></span>
                            <span class="{b3_cls}" title="3rd Base"></span>
                            <span class="{b1_cls}" title="1st Base"></span>
                        </span>
                    </div>
                    <div>
                        <span style="color: #64748B; font-size: 0.65rem;">OUTS:</span> <b style="color: #F8FAFC;">{lv['outs']}</b>
                    </div>
                </div>
                """

            card_html = f"""
            <div class="score-card" style="width: 100%;">
                <div class="score-card-header">
                    <span>{lv['badge_html']}</span>
                </div>
                <div class="score-card-body">
                    <div class="team-row">
                        <div class="team-info">
                            <img src="{g['away_logo']}" width="18" height="18" style="object-fit: contain;" />
                            <span>{g['away_short']}</span>
                        </div>
                        <span style="font-family: 'JetBrains Mono', monospace; font-weight: 800; font-size: 0.9rem;">{lv['away_runs']}</span>
                    </div>
                    <div class="team-row">
                        <div class="team-info">
                            <img src="{g['home_logo']}" width="18" height="18" style="object-fit: contain;" />
                            <span>{g['home_short']}</span>
                        </div>
                        <span style="font-family: 'JetBrains Mono', monospace; font-weight: 800; font-size: 0.9rem;">{lv['home_runs']}</span>
                    </div>
                </div>
                {bottom_info_html}
            </div>
            """
            with cols[idx]:
                st.markdown(card_html, unsafe_allow_html=True)
