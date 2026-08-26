#!/usr/bin/env python3
"""
Build script for the San Isidro Club — Ball in Play / Secuencias Largas dashboard.

Reads every .csv in DATA_DIR (one file = one partido, same format as the
original TOP 14 URBA export: Session Start Date, Event, Session Name,
Session Start, Session End, Tag Description, Tag Notes, Tag Start, Tag End,
Tag Duration (secs), Partido, Resultado, Rueda, Etapa).

Reads every logo image in LOGOS_DIR, resizes it to a small thumbnail and
base64-encodes it for inline embedding (no external image requests needed
once the site is published).

Injects both as JSON into template/dashboard_template.html and writes the
result to OUT_PATH (defaults to dist/index.html, which is what the GitHub
Actions workflow publishes to GitHub Pages).

Usage:
    python scripts/build_dashboard.py
    python scripts/build_dashboard.py --data-dir data --logos-dir assets/logos --out dist/index.html
"""
import argparse
import base64
import csv
import glob
import io
import json
import math
import os
import re
import statistics
import sys

try:
    from PIL import Image
except ImportError:
    print("ERROR: Pillow is required. Install with: pip install -r requirements.txt", file=sys.stderr)
    sys.exit(1)

# ---------------------------------------------------------------------------
# Club name -> logo filename mapping.
# Add new entries here (and drop a matching image into assets/logos/) whenever
# a new rival enters the fixture list. The key is matched against the
# "Partido" column after stripping a trailing " 2" / " 3" / " II" / " III"
# (second/third team suffix). If a club has no entry here, its own name
# (spaces preserved) is used as the lookup key against the logos folder.
# ---------------------------------------------------------------------------
CLUB_KEY_MAP = {
    "LPRC": "La_Plata",
    "LMRC": "Los_Matreros",
    "Los Tilos": "Los_Tilos",
    "Newman": "Newman",
    "Alumni": "Alumni",
    "Champagnat": "Champagnat",
    "BAC": "BAC",
    "CUBA": "CUBA",
    "BA": "BA",
    "CASI": "CASI",
    "Hindu": "Hindu",
    "Plaza": "Plaza",
    "CRBV": "CRBV",
}

OUTCOME_MAP = {
    "penal": "Penal", "try": "Try", "scrum": "Scrum", "line out": "Line Out",
    "drop in goal": "Drop Goal", "drop": "Drop Goal", "free kick": "Free Kick",
}

LOGO_THUMB_SIZE = (88, 88)
LOGO_HEADER_SIZE = (240, 240)


def to_sec(t):
    parts = [float(p) for p in t.split(":")]
    if len(parts) == 3:
        h, m, s = parts
        return h * 3600 + m * 60 + s
    m, s = parts
    return m * 60 + s


def clock_to_sec(t):
    h, m, s = [float(p) for p in t.split(":")]
    return h * 3600 + m * 60 + s


def fmt_mmss(sec):
    sec = round(sec)
    m, s = sec // 60, sec % 60
    return f"{m}:{s:02d}"


def parse_note(note):
    note = (note or "").strip()
    if not note:
        return None, None
    parts = note.split("-", 1)
    if len(parts) != 2:
        return None, None
    color_raw = parts[0].strip().lower()
    outcome_raw = parts[1].strip().lower()
    color = "green" if color_raw.startswith("verde") else ("red" if color_raw.startswith("rojo") else None)
    outcome = OUTCOME_MAP.get(outcome_raw, outcome_raw.title())
    return color, outcome


def club_key(partido):
    base = partido.strip()
    for suf in (" 2", " 3", " II", " III"):
        if base.endswith(suf):
            base = base[: -len(suf)]
            break
    return CLUB_KEY_MAP.get(base, base)


def categorize(dur):
    if dur < 30: return "<30s"
    if dur < 45: return "30-45s"
    if dur < 60: return "45-60s"
    if dur < 90: return "60-90s"
    if dur < 120: return "90-120s"
    return ">120s"


def parse_csv_file(path, fallback_fecha):
    with open(path, encoding="utf-8-sig", newline="") as fh:
        rows = [r for r in csv.DictReader(fh) if (r.get("Tag Description") or "").strip() == "Ball in Play"]
    if not rows:
        return None, []

    def g(row, *keys):
        for k in keys:
            if k in row and row[k] is not None:
                return row[k].strip()
        return ""

    partido = g(rows[0], "Partido")
    resultado = g(rows[0], "Resultado", "Resultado ")
    rueda = g(rows[0], "Rueda")
    etapa = g(rows[0], "Etapa")
    session_start = g(rows[0], "Session Start")
    session_end = g(rows[0], "Session End")
    date_str = g(rows[0], "Session Start Date")
    session_name = g(rows[0], "Session Name")

    fecha = fallback_fecha
    m = re.search(r"(\d+)", session_name)
    if m:
        fecha = int(m.group(1))

    ck = club_key(partido)

    try:
        sstart, send = clock_to_sec(session_start), clock_to_sec(session_end)
        session_dur = send - sstart
        if session_dur < 0:
            session_dur += 24 * 3600
    except Exception:
        session_dur = None

    seqs = []
    issues = []
    n_calc_fallback = 0
    n_overlaps = 0
    prev_end = None
    for r in rows:
        try:
            st, en = to_sec(r["Tag Start"]), to_sec(r["Tag End"])
        except Exception:
            continue
        rep_dur_str = (r.get("Tag Duration (secs)") or "").strip()
        if rep_dur_str:
            dur = round(float(rep_dur_str), 1)
        else:
            dur = round(en - st, 1)
            n_calc_fallback += 1
        if prev_end is not None and st < prev_end - 0.5:
            n_overlaps += 1
        prev_end = en
        color, outcome = parse_note(r.get("Tag Notes"))
        seqs.append({"start": st, "end": en, "dur": dur, "note_color": color, "note_outcome": outcome})
    seqs.sort(key=lambda x: x["start"])

    if n_overlaps:
        issues.append(
            f"Fecha {fecha} ({partido}): {n_overlaps} secuencia(s) con timestamps Tag Start/Tag End "
            f"superpuestos entre filas. Se usó 'Tag Duration (secs)' (no End-Start) para no inflar el BiP."
        )
    if n_calc_fallback:
        issues.append(
            f"Fecha {fecha} ({partido}): {n_calc_fallback} fila(s) sin 'Tag Duration (secs)'; "
            f"se completó con (Tag End - Tag Start) solo para esas filas."
        )

    total_bip = sum(s["dur"] for s in seqs)
    pct_bip = (total_bip / session_dur * 100) if session_dur else None
    match_color = "green" if resultado == "Ganado" else ("red" if resultado == "Perdido" else "neutral")

    tagged_out = []
    long_seqs = []
    for s in seqs:
        if s["note_color"] and s["note_outcome"]:
            tagged_out.append({
                "fecha": fecha, "partido": partido, "club_key": ck, "resultado": resultado,
                "color": s["note_color"], "outcome": s["note_outcome"], "dur": s["dur"],
                "minute": round(s["start"] / 60.0, 1),
                "start_mmss": fmt_mmss(s["start"]), "end_mmss": fmt_mmss(s["end"]),
            })
        if s["dur"] > 60:
            minute = s["start"] / 60.0
            cat = "60-90s" if s["dur"] <= 90 else ("90-120s" if s["dur"] <= 120 else ">120s")
            long_seqs.append({
                "start": s["start"], "end": s["end"], "dur": s["dur"],
                "start_mmss": fmt_mmss(s["start"]), "end_mmss": fmt_mmss(s["end"]),
                "minute": round(minute, 1), "category": cat, "match_color": match_color,
                "color": s["note_color"] or "unclassified", "outcome": s["note_outcome"],
            })

    long_durs = [s["dur"] for s in long_seqs]
    total_long_time = sum(long_durs)
    n_green = sum(1 for s in long_seqs if s["color"] == "green")
    n_red = sum(1 for s in long_seqs if s["color"] == "red")
    n_classified = n_green + n_red

    match = {
        "fecha": fecha, "date": date_str, "partido": partido, "club_key": ck, "resultado": resultado,
        "rueda": rueda, "etapa": etapa, "session_start": session_start, "session_end": session_end,
        "session_dur_sec": round(session_dur, 1) if session_dur is not None else None,
        "session_dur_mmss": fmt_mmss(session_dur) if session_dur is not None else None,
        "total_bip_sec": round(total_bip, 1), "total_bip_mmss": fmt_mmss(total_bip),
        "total_bip_min": round(total_bip / 60, 2),
        "pct_bip": round(pct_bip, 1) if pct_bip is not None else None,
        "n_sequences": len(seqs), "n_long": len(long_seqs),
        "avg_long_dur": round(statistics.mean(long_durs), 1) if long_durs else 0,
        "max_long_dur": round(max(long_durs), 1) if long_durs else 0,
        "min_long_dur": round(min(long_durs), 1) if long_durs else 0,
        "total_long_time": round(total_long_time, 1),
        "pct_bip_from_long": round(total_long_time / total_bip * 100, 1) if total_bip else 0,
        "color": match_color,
        "n_classified": n_classified, "n_green": n_green, "n_red": n_red,
        "pct_green_of_classified": round(n_green / n_classified * 100, 1) if n_classified else None,
        "all_sequences": [{"start": s["start"], "end": s["end"], "dur": s["dur"]} for s in seqs],
        "long_sequences": long_seqs,
    }
    return match, issues, tagged_out


def build_dataset(data_dir):
    files = sorted(glob.glob(os.path.join(data_dir, "*.csv")))
    if not files:
        print(f"WARNING: no .csv files found in {data_dir}", file=sys.stderr)

    matches, issues, tagged_sequences = [], [], []
    for i, f in enumerate(files, start=1):
        result = parse_csv_file(f, fallback_fecha=i)
        if result is None or result[0] is None:
            issues.append(f"{os.path.basename(f)}: sin filas 'Ball in Play', se omitió.")
            continue
        match, file_issues, tagged = result
        matches.append(match)
        issues.extend(file_issues)
        tagged_sequences.extend(tagged)

    matches.sort(key=lambda m: m["fecha"])
    if not matches:
        return {
            "matches": [], "issues": issues, "kpi": {}, "cat_distribution": [],
            "rank_bip": [], "rank_long": [], "wl_compare": {}, "tagged_sequences": [],
            "outcome_breakdown": [],
        }

    bip_vals = [m["total_bip_min"] for m in matches]
    mean_bip = statistics.mean(bip_vals)
    median_bip = statistics.median(bip_vals)
    max_bip, min_bip = max(bip_vals), min(bip_vals)
    std_bip = statistics.stdev(bip_vals) if len(bip_vals) > 1 else 0.0
    cv_bip = (std_bip / mean_bip * 100) if mean_bip else 0.0
    max_match = next(m for m in matches if m["total_bip_min"] == max_bip)
    min_match = next(m for m in matches if m["total_bip_min"] == min_bip)

    all_long = [s for m in matches for s in m["long_sequences"]]
    n_long_total = len(all_long)
    if all_long:
        max_long_seq = max(all_long, key=lambda s: s["dur"])
        max_long_seq_fecha = next(m["fecha"] for m in matches if max_long_seq in m["long_sequences"])
    else:
        max_long_seq, max_long_seq_fecha = {"dur": 0}, None

    n_green_matches = sum(1 for m in matches if m["color"] == "green")
    n_red_matches = sum(1 for m in matches if m["color"] == "red")

    n_tagged = len(tagged_sequences)
    n_tagged_green = sum(1 for s in tagged_sequences if s["color"] == "green")
    pct_verde_real = round(n_tagged_green / n_tagged * 100, 1) if n_tagged else 0

    all_seqs_flat = [s for m in matches for s in m["all_sequences"]]
    cat_order = ["<30s", "30-45s", "45-60s", "60-90s", "90-120s", ">120s"]
    cat_counts = {c: 0 for c in cat_order}
    for s in all_seqs_flat:
        cat_counts[categorize(s["dur"])] += 1
    total_seqs_all = len(all_seqs_flat)
    cat_distribution = [
        {"category": c, "count": cat_counts[c],
         "pct_of_total": round(cat_counts[c] / total_seqs_all * 100, 1) if total_seqs_all else 0}
        for c in cat_order
    ]

    xs = [m["total_bip_min"] for m in matches]
    ys = [m["n_long"] for m in matches]
    if len(matches) > 1:
        mx, my = statistics.mean(xs), statistics.mean(ys)
        cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
        sx = math.sqrt(sum((x - mx) ** 2 for x in xs))
        sy = math.sqrt(sum((y - my) ** 2 for y in ys))
        pearson_r = cov / (sx * sy) if sx * sy else None
    else:
        pearson_r = None

    rank_bip = sorted(matches, key=lambda m: -m["total_bip_min"])
    rank_long = sorted(matches, key=lambda m: -m["n_long"])

    won = [m for m in matches if m["color"] == "green"]
    lost = [m for m in matches if m["color"] == "red"]

    def avg(lst, key):
        vals = [m[key] for m in lst]
        return round(statistics.mean(vals), 2) if vals else 0

    wl_compare = {
        "won": {"n": len(won), "avg_bip": avg(won, "total_bip_min"), "avg_n_long": avg(won, "n_long"),
                "avg_long_dur": avg(won, "avg_long_dur"), "avg_pct_bip_from_long": avg(won, "pct_bip_from_long")},
        "lost": {"n": len(lost), "avg_bip": avg(lost, "total_bip_min"), "avg_n_long": avg(lost, "n_long"),
                 "avg_long_dur": avg(lost, "avg_long_dur"), "avg_pct_bip_from_long": avg(lost, "pct_bip_from_long")},
    }

    outcome_order = ["Penal", "Try", "Scrum", "Line Out", "Drop Goal", "Free Kick"]
    seen_outcomes = {s["outcome"] for s in tagged_sequences if s["outcome"]}
    full_outcome_order = outcome_order + sorted(seen_outcomes - set(outcome_order))
    outcome_breakdown = []
    for o in full_outcome_order:
        gcount = sum(1 for s in tagged_sequences if s["outcome"] == o and s["color"] == "green")
        rcount = sum(1 for s in tagged_sequences if s["outcome"] == o and s["color"] == "red")
        if gcount + rcount:
            outcome_breakdown.append({"outcome": o, "green": gcount, "red": rcount, "total": gcount + rcount,
                                       "pct_green": round(gcount / (gcount + rcount) * 100, 1)})

    kpi = {
        "mean_bip": round(mean_bip, 2), "median_bip": round(median_bip, 2),
        "max_bip": round(max_bip, 2), "max_bip_match": f"Fecha {max_match['fecha']} vs {max_match['partido']}",
        "min_bip": round(min_bip, 2), "min_bip_match": f"Fecha {min_match['fecha']} vs {min_match['partido']}",
        "std_bip": round(std_bip, 2), "cv_bip": round(cv_bip, 1), "range_bip": round(max_bip - min_bip, 2),
        "n_long_total": n_long_total, "max_long_seq_dur": max_long_seq["dur"],
        "max_long_seq_match": f"Fecha {max_long_seq_fecha}" if max_long_seq_fecha else "—",
        "n_green_matches": n_green_matches, "n_red_matches": n_red_matches,
        "pearson_r": round(pearson_r, 3) if pearson_r is not None else None, "n_matches": len(matches),
        "n_tagged": n_tagged, "n_tagged_green": n_tagged_green, "pct_verde_real": pct_verde_real,
    }

    return {
        "matches": matches, "issues": issues, "kpi": kpi, "cat_distribution": cat_distribution,
        "rank_bip": [{"fecha": m["fecha"], "partido": m["partido"], "club_key": m["club_key"],
                      "total_bip_min": m["total_bip_min"], "resultado": m["resultado"]} for m in rank_bip],
        "rank_long": [{"fecha": m["fecha"], "partido": m["partido"], "club_key": m["club_key"],
                       "n_long": m["n_long"], "resultado": m["resultado"]} for m in rank_long],
        "wl_compare": wl_compare, "tagged_sequences": tagged_sequences, "outcome_breakdown": outcome_breakdown,
    }


def build_logos(logos_dir):
    logos = {}
    if not os.path.isdir(logos_dir):
        return logos
    for path in sorted(glob.glob(os.path.join(logos_dir, "*"))):
        if not path.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
            continue
        name = os.path.splitext(os.path.basename(path))[0]
        try:
            im = Image.open(path).convert("RGBA")
        except Exception as e:
            print(f"WARNING: could not read logo {path}: {e}", file=sys.stderr)
            continue

        thumb = im.copy()
        thumb.thumbnail(LOGO_THUMB_SIZE, Image.LANCZOS)
        buf = io.BytesIO()
        thumb.save(buf, format="PNG", optimize=True)
        logos[name] = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")

        if name.upper() == "SIC":
            header = im.copy()
            header.thumbnail(LOGO_HEADER_SIZE, Image.LANCZOS)
            buf2 = io.BytesIO()
            header.save(buf2, format="PNG", optimize=True)
            logos["SIC_header"] = "data:image/png;base64," + base64.b64encode(buf2.getvalue()).decode("ascii")
    return logos


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default="data")
    ap.add_argument("--logos-dir", default="assets/logos")
    ap.add_argument("--template", default="template/dashboard_template.html")
    ap.add_argument("--out", default="dist/index.html")
    args = ap.parse_args()

    print(f"Reading match CSVs from: {args.data_dir}")
    dataset = build_dataset(args.data_dir)
    print(f"  -> {len(dataset['matches'])} partidos, "
          f"{sum(m['n_sequences'] for m in dataset['matches'])} secuencias, "
          f"{len(dataset['tagged_sequences'])} clasificadas Verde/Rojo")
    for issue in dataset["issues"]:
        print(f"  [aviso] {issue}")

    print(f"Reading logos from: {args.logos_dir}")
    logos = build_logos(args.logos_dir)
    print(f"  -> {len(logos)} logos embebidos")

    with open(args.template, encoding="utf-8") as f:
        template = f.read()

    html = template.replace("__DATA_JSON__", json.dumps(dataset, ensure_ascii=False))
    html = html.replace("__LOGOS_JSON__", json.dumps(logos))

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Dashboard escrito en: {args.out} ({len(html)/1024:.0f} KB)")


if __name__ == "__main__":
    main()
