import re
import fitz
import pandas as pd
import numpy as np
import streamlit as st

st.set_page_config(page_title="SA Racing Wizard", layout="wide")
st.title("South African Horseracing Prediction Engine")
st.caption("Supports 4Racing ComputaForm (Vaal, Turffontein, KZN) and Race Coast / TAB (Cape Town, Fairview).")

uploaded_pdf = st.file_uploader("Upload South African ComputaForm / Race Coast PDF", type=["pdf"])

c1, c2, c3, c4, c5 = st.columns(5)
w_speed = c1.slider("Speed & Weight", 0.0, 1.0, 0.35, 0.05)
w_class = c2.slider("Class & MR Drop", 0.0, 1.0, 0.25, 0.05)
w_form = c3.slider("Form & Fitness", 0.0, 1.0, 0.20, 0.05)
w_draw = c4.slider("Draw Bias", 0.0, 1.0, 0.10, 0.05)
w_gear = c5.slider("Gear Upgrades", 0.0, 1.0, 0.10, 0.05)

generate_clicked = st.button("Recalculate Top 3 Picks, Dark Horses & Value Bets", type="primary", use_container_width=True)


def parse_4racing_page(text, page_idx, seen_races):
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    title = ""
    if page_idx == 0:
        for ln in lines:
            if any(k in ln.upper() for k in ["TAB ", "TURFFONTEIN", "VAAL", "GREYVILLE", "SCOTTSVILLE", "FAIRVIEW"]):
                title = ln
                break

    if "No L3 Name" not in text or "R-1-2-3" not in text or "COMPUTAFORM AT A GLANCE" in text or "HOW TO READ" in text:
        return [], title

    dist_m = re.search(r"\b(\d{4})m\b", text)
    race_dist = int(dist_m.group(1)) if dist_m else 1200

    ref_m = re.search(r"Race Ref:\s*(\d+)", text)
    race_ref = ref_m.group(1) if ref_m else str(page_idx)
    if race_ref in seen_races:
        return [], title
    seen_races.add(race_ref)
    current_race = len(seen_races)

    cf_map, sp_map = {}, {}
    for ln in lines:
        m_rate = re.match(r"^(\d{1,2})\s+([A-Za-z\s\'\-\’]+?)\s+(\d{2,3})\b", ln)
        if not m_rate:
            continue
        h_key = m_rate.group(2).strip().upper()
        val = float(m_rate.group(3))
        if h_key not in cf_map:
            cf_map[h_key] = val
        elif h_key not in sp_map:
            sp_map[h_key] = val

    row_re = re.compile(
        r"^(?P<No>\d{1,2})\s+"
        r"(?:(?P<L3>[0-9pq]+)\s+)?"
        r"(?P<Horse>[A-Z0-9\'\-\’]+(?:\s+[A-Z0-9\'\-\’]+)*?)\s+"
        r"(?P<Runs>\d+)-(?P<Wins>\d+)-(?P<Places2>\d+)-(?P<Places3>\d+)\s+"
        r"(?P<F3>\d+)%\s+"
        r"R(?P<Earn>[\d,]+)\s+"
        r"R(?P<AveEarn>[\d,]+)\s+"
        r"\d[A-Za-z]{1,3}\s+"
        r"(?P<Wt>\d{2}(?:\.\d)?)(?:-\d\.\d|\+\d\.\d)?\s+"
        r"(?P<Draw>\d{1,2})\s+"
        r".*?"
        r"(?P<HMR>\d{2,3}|--)\s+"
        r"(?P<CMR>\d{2,3}|--)\s+"
        r"(?P<Comment>.*?)\s+"
        r"(?P<OddsNum>\d+)-(?P<OddsDen>\d+)$"
    )

    page_runners = []
    for ln in lines:
        rm = row_re.match(ln)
        if not rm:
            continue
        horse_name = rm.group("Horse").strip().upper()
        runs = int(rm.group("Runs"))
        wins = int(rm.group("Wins"))
        places = int(rm.group("Places2")) + int(rm.group("Places3"))
        earn = int(rm.group("Earn").replace(",", ""))
        ave_earn = int(rm.group("AveEarn").replace(",", ""))
        hmr = int(rm.group("HMR")) if rm.group("HMR").isdigit() else 0
        cmr = int(rm.group("CMR")) if rm.group("CMR").isdigit() else 0
        l3_str = rm.group("L3") or ""
        l3_digits = [int(ch) if ch != "0" else 10 for ch in l3_str if ch.isdigit()]
        avg_pos = float(np.mean(l3_digits)) if l3_digits else 6.5
        odds_num, odds_den = float(rm.group("OddsNum")), float(rm.group("OddsDen"))
        fcst_odds = round(odds_num / odds_den, 2) if odds_den > 0 else 15.0
        comment = rm.group("Comment").strip()
        gear_boost = 1.0 if any(g in comment.lower() for g in ["blinkers", "headgear", "tongue", "cheek"]) else 0.0
        mr_drop = max(0, hmr - cmr) if (hmr > 0 and cmr > 0) else 0

        page_runners.append({
            "Race": current_race, "Dist": race_dist, "No": int(rm.group("No")),
            "Horse": horse_name, "Draw": int(rm.group("Draw")), "Wt": float(rm.group("Wt")),
            "MR": cmr, "MR_Drop":
