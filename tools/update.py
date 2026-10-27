#!/usr/bin/env python3
"""Daily update helper for Konsertkalender Norge.

The daily run only collects new concerts from the web. Everything else (reading the
page data, merging, removing duplicates and past concerts, venue bookkeeping, the
update summary, the time stamp and the script check) is done here, the same way
every day, so the run never has to read the page data itself or write new code.

Working copy and run state live in .kk/ (not committed).

  python3 tools/update.py start <artifact.html>   start a run from the page just read
  python3 tools/update.py add <batch.json>        add concerts / festivals / towns (repeat per source)
  python3 tools/update.py venues                  list venues to look up at Kartverket this run
  python3 tools/update.py positions <pos.json>    store the Kartverket results
  python3 tools/update.py geocode [--addresses <addr.json>]
                                                  look the venues up at Kartverket directly (no WebFetch,
                                                  so no permission prompts); addr.json = {"Venue|City": "Street 12"}
  python3 tools/update.py finish [--failed "A; B"] [--highlights "Artist (Scene); ..."]
                                                  write artifact.html with summary + time stamp
  python3 tools/update.py check <file.html>       check that every inline script parses

batch.json:
  {"source": "Eventworld",                       default source name for rows without one
   "concerts": [["2026-11-01","Artist","Venue","City","Genre"],          list or object rows;
                ["2026-11-02","Britallica (Britney Spears-metaltribute)","Kometen","Drammen","Metal","TicketTailor",true]],
                                                  6th = source name, 7th = true for a tribute concert
   "festivals": [{"name":"Tons of Rock","start":"2027-06-23","end":"2027-06-26","venue":"Ekebergsletta","city":"Oslo",
                  "url":"https://...","lineupComplete":false,
                  "lineup":[{"n":"Artist","g":"Metal","d":"2027-06-24","v":"Hovedscenen"}]}],
                                                  existing festival (same name + year): only new artists, new
                                                  days/stages, changed dates, url and lineupComplete are used
   "cities": {"Town": [lat, lon, "Fylke"]},       new towns (also added to HOMES unless "homes": false)
   "venue_url": {"Venue|City": "https://..."}}

pos.json:
  {"found": {"Venue|City": [lat, lon]}, "notfound": ["Venue|City"], "skip": ["Name|City"]}
"""
import json, os, re, sys, shutil, subprocess, unicodedata
from datetime import datetime, date
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KK = os.path.join(ROOT, ".kk")
PAGE = os.path.join(KK, "page.html")
STATE = os.path.join(KK, "state.json")
OUT = os.path.join(ROOT, "artifact.html")
TZ = ZoneInfo("Europe/Oslo")

GENRES = ["Pop", "Rock", "Indie", "Metal", "Folk", "Jazz", "Hiphop/R&B", "Elektronisk", "Country", "Klassisk", "Verdensmusikk"]
GENRE_MAP = {"latin & world": "Verdensmusikk", "world": "Verdensmusikk", "latin": "Verdensmusikk",
             "soul & r&b": "Hiphop/R&B", "hip-hop & rap": "Hiphop/R&B", "hip-hop": "Hiphop/R&B", "hiphop": "Hiphop/R&B",
             "rap": "Hiphop/R&B", "r&b": "Hiphop/R&B", "soul": "Hiphop/R&B", "punk & hardcore": "Rock", "punk": "Rock",
             "hardcore": "Rock", "blues": "Rock", "folk & acoustic": "Folk", "acoustic": "Folk", "viser": "Folk",
             "classical": "Klassisk", "electronic": "Elektronisk", "dance": "Elektronisk", "edm": "Elektronisk",
             "techno": "Elektronisk", "house": "Elektronisk", "heavy metal": "Metal", "hard rock": "Rock", "alternative": "Indie"}
FYLKER = ["Oslo", "Akershus", "Buskerud", "Østfold", "Vestfold", "Telemark", "Agder", "Rogaland", "Vestland",
          "Møre og Romsdal", "Trøndelag", "Nordland", "Troms", "Finnmark", "Innlandet"]
PRIORITY = {"Rockefeller|Oslo", "John Dee|Oslo", "Sentrum Scene|Oslo", "Oslo Spektrum|Oslo", "Unity Arena|Fornebu",
            "Union Scene|Drammen", "Kometen|Drammen", "Ekebergsletta|Oslo", "Valle Hovin|Oslo"}
BIG_CITIES = ["Oslo", "Drammen", "Bergen", "Trondheim", "Stavanger", "Kristiansand", "Fornebu"]
# venues that sources list under the wrong town
VENUE_TOWN = {"unity arena": "Fornebu", "ullensaker kulturhus": "Jessheim", "martins pub": "Lillestrøm",
              "fosnavåg konserthus": "Fosnavåg", "drenga stova": "Storebø", "drengastova": "Storebø"}
# venues that sources spell differently from the venue's own name
VENUE_NAME = {"drenga stova": "Drengastova"}  # Gamle Prestegården, Prestanesvegen 35, Storebø (Austevoll)
# same, but only when the source gives this town (the venue name is too common to move everywhere)
VENUE_TOWN_AT = {("kaien", "Førde"): "Sveio"}  # Kaien café, Tingvegen 74, Førde i Sveio
# preference when two NEW rows are the same concert: venue/organiser sites (0) > Eventworld > Songkick > TicketCo
PREF = {"Eventworld": 1, "Songkick": 2, "TicketCo": 3}
TRIBUTE_RE = re.compile(r"tribute|hyllest|candlelight", re.I)
WEEKDAYS = ["mandag", "tirsdag", "onsdag", "torsdag", "fredag", "lørdag", "søndag"]
MONTHS = ["jan", "feb", "mar", "apr", "mai", "jun", "jul", "aug", "sep", "okt", "nov", "des"]
CONSTS = ["DATA", "SOURCES", "VENUE_POS", "VENUE_URL", "CITY", "HOMES", "FESTS", "SUMMARY", "FAVS", "ADDED"]
DAY0 = date(2026, 1, 1)  # day numbers in ADDED count from here


def day_no(iso):
    return (date.fromisoformat(iso) - DAY0).days


def day_str(n):
    from datetime import timedelta
    return (DAY0 + timedelta(days=n)).isoformat()
NYTT = os.path.join(ROOT, "nytt.json")


def die(msg):
    sys.exit("update.py: " + msg)


def now():
    return datetime.now(TZ)


def today():
    return now().date().isoformat()


def norm(s):
    s = unicodedata.normalize("NFKC", str(s)).lower().strip()
    s = re.sub(r"^the\s+", "", s)
    return re.sub(r"[^\w]+", "", s)


def key(r):
    return r[0] + "|" + norm(r[1]) + "|" + norm(r[3])


# acts that are not concerts (talks, lectures) but show up in venue programmes: never added
NOT_CONCERT = {"hanswilhelmsteinfeld", "ingvardwilhelmsen"}  # foredrag / ikke konserter (Union Scene)
LOOSE_STOP = {"og", "and", "the", "med", "feat", "ft"}


def loose_same(a, b):
    """Same act written two ways on the same date and venue: one name starts with (or contains) the other (e.g. "The Dahmers" /
    "The Dahmers and Spiders", "Emma Steinbakken" / "Emma Steinbakken – Emmas Jul"), or the same words in another
    order or with another separator (brackets ignored)."""
    a2, b2 = re.sub(r"\(.*?\)", " ", a), re.sub(r"\(.*?\)", " ", b)
    na, nb = norm(a2), norm(b2)
    if na and nb and (na.startswith(nb) or nb.startswith(na)):
        return True
    if min(len(na), len(nb)) >= 5 and (na in nb or nb in na):  # "Darkest Hour" / "Frozen Soul og Darkest Hour"
        return True
    w = lambda x: frozenset(t for t in re.findall(r"\w+", x.lower()) if t not in LOOSE_STOP)
    return bool(w(a2)) and w(a2) == w(b2)


def dumps(v, compact=True):
    s = json.dumps(v, ensure_ascii=False, separators=(",", ":") if compact else None)
    return s.replace("</", "<\\/")


# ---------- page <-> data ----------

def read_page(path):
    lines = open(path, encoding="utf-8").read().split("\n")
    d, idx = {}, {}
    for i, l in enumerate(lines):
        m = re.match(r"const (\w+) = (.*);\s*$", l)
        if m and m.group(1) in CONSTS and m.group(1) not in d:
            d[m.group(1)] = json.loads(m.group(2))
            idx[m.group(1)] = i
        for c in ("skip", "notfound", "verified"):
            if l.startswith("// " + c + ":") and c not in idx:
                idx[c] = i
                body = l[len("// " + c + ":"):].strip()
                d[c] = [x.strip() for x in body.split("; ") if x.strip()] if body else []
    miss = [c for c in CONSTS + ["skip", "notfound", "verified"] if c not in idx]
    if miss:
        die("could not find in page: " + ", ".join(miss))
    d["notfound"] = dict(x.rsplit("@", 1) if "@" in x else (x, "2000-01-01") for x in d["notfound"])
    return lines, idx, d


def write_page(lines, idx, d, path):
    lines = list(lines)
    for c in CONSTS:
        lines[idx[c]] = "const %s = %s;" % (c, dumps(d[c], compact=(c != "SUMMARY")))
    lines[idx["skip"]] = "// skip: " + "; ".join(d["skip"])
    lines[idx["notfound"]] = "// notfound: " + "; ".join(k + "@" + v for k, v in d["notfound"].items())
    lines[idx["verified"]] = "// verified: " + "; ".join(d["verified"])
    open(path, "w", encoding="utf-8").write("\n".join(lines))


def load():
    if not os.path.exists(STATE):
        die("no run started – run: update.py start <artifact.html>")
    st = json.load(open(STATE, encoding="utf-8"))
    lines, idx, d = read_page(PAGE)
    return st, lines, idx, d


def save(st, lines, idx, d):
    write_page(lines, idx, d, PAGE)
    json.dump(st, open(STATE, "w", encoding="utf-8"), ensure_ascii=False)


def src_index(d, name):
    name = (name or "").strip() or "Ukjent"
    for i, s in enumerate(d["SOURCES"]):
        if s.lower() == name.lower():
            return i
    d["SOURCES"].append(name)
    return len(d["SOURCES"]) - 1


def src_name(d, i):
    return d["SOURCES"][i] if 0 <= i < len(d["SOURCES"]) else "?"


def fix_genre(g):
    g = (g or "").strip()
    for x in GENRES:
        if g.lower() == x.lower():
            return x, True
    if g.lower() in GENRE_MAP:
        return GENRE_MAP[g.lower()], True
    return "Pop", False


def venue_keys(d):
    ks = set()
    for r in d["DATA"]:
        ks.add(r[2] + "|" + r[3])
    for f in d["FESTS"]:  # festival stages ("v") are not looked up; their rows fall back to the town centre
        ks.add(f["venue"] + "|" + f["city"])
    return ks


def cities_used(d):
    return {r[3] for r in d["DATA"]} | {f["city"] for f in d["FESTS"]}


def fest_key(f):
    return norm(f["name"]) + "|" + str(f.get("start", ""))[:4]


# ---------- commands ----------

def cmd_start(path):
    lines, idx, d = read_page(path)
    os.makedirs(KK, exist_ok=True)
    shutil.copyfile(path, PAGE)
    st = {"today": today(), "orig_keys": [key(r) for r in d["DATA"]], "added": [], "unknown_genre": [],
          "fest": {}, "fest_new": [], "fest_dates": [], "pos": {"added": [], "corrected": [], "same": [], "notfound": [], "skip": []}}
    json.dump(st, open(STATE, "w", encoding="utf-8"), ensure_ascii=False)
    t = st["today"]
    fut = [r for r in d["DATA"] if r[0] >= t]
    print("Start %s: %d konserter (%d fra i dag), %d festivaler, %d kilder, %d steder med posisjon"
          % (t, len(d["DATA"]), len(fut), len(d["FESTS"]), len(d["SOURCES"]), len(d["VENUE_POS"])))
    print("Festivaler (navn | datoer | artister, med dag | komplett):")
    for f in d["FESTS"]:
        lu = f.get("lineup", [])
        days = sum(1 for a in lu if isinstance(a, dict) and a.get("d"))
        print("  %s | %s–%s | %d, %d | %s" % (f["name"], f["start"], f["end"], len(lu), days, "ja" if f.get("lineupComplete") else "nei"))


def cmd_add(path):
    st, lines, idx, d = load()
    b = json.load(open(path, encoding="utf-8"))
    t = st["today"]
    default_src = b.get("source", "")
    orig = set(st["orig_keys"])
    have = {key(r): i for i, r in enumerate(d["DATA"])}
    added_now = {a["k"]: a for a in st["added"]}
    rep = {"new": [], "dup": 0, "past": 0, "bad": [], "replaced": 0, "genre": [], "nocity": set()}

    # towns first, so new concerts can use them
    for town, v in (b.get("cities") or {}).items():
        if not (isinstance(v, list) and len(v) >= 3 and v[2] in FYLKER):
            rep["bad"].append("by %s: trenger [lat, lon, fylke] med gyldig fylke" % town)
            continue
        if town not in d["CITY"]:
            d["CITY"][town] = [round(float(v[0]), 3), round(float(v[1]), 3), v[2]]
            if b.get("homes", True) and town not in d["HOMES"]:
                d["HOMES"][town] = [round(float(v[0]), 3), round(float(v[1]), 3)]
    for k, u in (b.get("venue_url") or {}).items():
        d["VENUE_URL"].setdefault(k, u)

    venues_by_city = {}
    for r in d["DATA"]:
        venues_by_city.setdefault((r[3], r[2].lower()), r[2])

    for raw in b.get("concerts") or []:
        if isinstance(raw, dict):
            raw = [raw.get("date"), raw.get("artist"), raw.get("venue"), raw.get("city"), raw.get("genre"),
                   raw.get("source"), raw.get("tribute", False)]
        raw = list(raw) + [None] * (7 - len(raw))
        dt, artist, venue, city, genre, src, trib = raw[:7]
        if not (isinstance(dt, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", dt) and artist and venue and city):
            rep["bad"].append("rad mangler dato/artist/sted/by: %s" % json.dumps(raw[:4], ensure_ascii=False))
            continue
        artist, venue, city = str(artist).strip(), str(venue).strip(), str(city).strip()
        if dt < t:
            rep["past"] += 1
            continue
        if norm(artist) in NOT_CONCERT:
            continue
        city = VENUE_TOWN.get(venue.lower(), city)
        city = VENUE_TOWN_AT.get((venue.lower(), city), city)
        venue = VENUE_NAME.get(venue.lower(), venue)
        venue = venues_by_city.get((city, venue.lower()), venue)
        g, ok = fix_genre(genre)
        if not ok and genre:
            rep["genre"].append("%s: «%s» → Pop" % (artist, genre))
        src = src or default_src
        row = [dt, artist, venue, city, g, src_index(d, src)]
        k = key(row)
        if k in have:
            if k not in orig and k in added_now and PREF.get(src, 0) < PREF.get(src_name(d, d["DATA"][have[k]][5]), 0):
                d["DATA"][have[k]] = row
                added_now[k].update(src=src, venue=venue)
                rep["replaced"] += 1
            else:
                rep["dup"] += 1
            continue
        near = next((j for j, r in enumerate(d["DATA"]) if r[0] == dt and r[3] == city
                     and r[2].lower() == venue.lower() and loose_same(r[1], artist)), None)
        if near is not None:  # same concert under another name: keep one row, with the longest name
            r = d["DATA"][near]
            if len(artist) > len(r[1]):
                ok_ = key(r)
                r[1] = artist
                nk = key(r)
                have.pop(ok_, None)
                have[nk] = near
                if ok_ in added_now:
                    a_ = added_now.pop(ok_)
                    a_.update(k=nk, artist=artist)
                    added_now[nk] = a_
            rep["dup"] += 1
            continue
        have[k] = len(d["DATA"])
        d["DATA"].append(row)
        venues_by_city.setdefault((city, venue.lower()), venue)
        a = {"k": k, "date": dt, "artist": artist, "venue": venue, "city": city, "src": src,
             "tribute": bool(trib) or bool(TRIBUTE_RE.search(artist))}
        added_now[k] = a
        st["added"].append(a)
        rep["new"].append(a)
        if city not in d["CITY"]:
            rep["nocity"].add(city)

    # festivals
    fests = {fest_key(f): f for f in d["FESTS"]}
    for nf in b.get("festivals") or []:
        if not all(nf.get(x) for x in ("name", "start", "end")):
            rep["bad"].append("festival mangler name/start/end: %s" % nf.get("name"))
            continue
        lu = []
        for a in nf.get("lineup") or []:
            a = {"n": a, "g": "Pop", "d": ""} if isinstance(a, str) else dict(a)
            a["g"], _ = fix_genre(a.get("g"))
            a.setdefault("d", "")
            lu.append({k: a[k] for k in ("n", "g", "d", "v") if k in a and (k != "v" or a[k])})
        fk = fest_key(nf)
        rec = st["fest"].setdefault(nf["name"], {"artists": 0, "days": 0})
        f = fests.get(fk)
        if not f:
            f = {"name": nf["name"], "start": nf["start"], "end": nf["end"], "venue": nf.get("venue") or "Flere scener",
                 "city": nf.get("city") or "Oslo", "src": src_index(d, nf.get("source") or default_src or nf["name"]),
                 "url": nf.get("url") or "", "lineupComplete": bool(nf.get("lineupComplete")), "lineup": []}
            d["FESTS"].append(f)
            fests[fk] = f
            st["fest_new"].append([f["name"], "%s (%s–%s, %s)" % (f["name"], short_date(f["start"]), short_date(f["end"]), f["city"])])
            if f["city"] not in d["CITY"]:
                rep["nocity"].add(f["city"])
        else:
            if (nf["start"], nf["end"]) != (f["start"], f["end"]):
                st["fest_dates"].append("%s: nye datoer %s–%s" % (f["name"], nf["start"], nf["end"]))
                f["start"], f["end"] = nf["start"], nf["end"]
            if nf.get("url") and nf["url"] != f.get("url") and not (f.get("url") and "tons of rock" in f["name"].lower()):
                f["url"] = nf["url"]
            if "lineupComplete" in nf:
                f["lineupComplete"] = bool(nf["lineupComplete"])
        f["lineup"] = [({"n": a, "g": "Pop", "d": ""} if isinstance(a, str) else a) for a in f.get("lineup", [])]
        byname = {norm(a["n"]): a for a in f["lineup"]}
        na = nd = 0
        for a in lu:
            old = byname.get(norm(a["n"]))
            if not old:
                f["lineup"].append(a)
                byname[norm(a["n"])] = a
                na += 1
                st.setdefault("fest_added", []).append([f["name"], a["n"], f["venue"], f["city"], a.get("d", ""), f["start"], f["end"]])
            else:
                if a.get("d") and a["d"] != old.get("d"):
                    old["d"] = a["d"]
                    nd += 1
                if a.get("v") and a["v"] != old.get("v"):
                    old["v"] = a["v"]
        rec["artists"] += na
        rec["days"] += nd
        rep.setdefault("fest", []).append("%s: +%d nye artister, +%d spilledager (%d artister i alt)"
                                          % (f["name"], na, nd, len(f["lineup"])))

    save(st, lines, idx, d)
    out = ["+%d nye, %d fantes fra før, %d passerte hoppet over" % (len(rep["new"]), rep["dup"], rep["past"])]
    if rep["replaced"]:
        out.append("%d erstattet med bedre kilde" % rep["replaced"])
    if rep["new"]:
        out.append("Nye: " + "; ".join("%s (%s, %s)" % (a["artist"], a["venue"], a["city"]) for a in rep["new"][:12])
                   + ("; … og %d til" % (len(rep["new"]) - 12) if len(rep["new"]) > 12 else ""))
    for f in rep.get("fest", []):
        out.append("Festival " + f)
    if rep["genre"]:
        out.append("Ukjent sjanger satt til Pop: " + "; ".join(rep["genre"][:10]))
    if rep["nocity"]:
        out.append("MANGLER BY i CITY (legg til i \"cities\"): " + ", ".join(sorted(rep["nocity"])))
    for x in rep["bad"]:
        out.append("HOPPET OVER: " + x)
    print("\n".join(out))


def todo_venues(d, st):
    ks = venue_keys(d)
    skip, verified, nf = set(d["skip"]), set(d["verified"]), d["notfound"]
    t = date.fromisoformat(st["today"])
    def rank(k):
        v, c = k.rsplit("|", 1)
        return (0 if k in PRIORITY else 1, BIG_CITIES.index(c) if c in BIG_CITIES else 99, k)
    a = sorted([k for k in ks if k not in d["VENUE_POS"] and k not in nf and k not in skip and k not in verified], key=rank)
    b_ = sorted([k for k in ks if k in d["VENUE_POS"] and k not in verified and k not in nf and k not in skip], key=rank)
    c_ = sorted([k for k in nf if k in ks and k not in verified and k not in skip
                 and (t - date.fromisoformat(nf[k])).days >= 7], key=lambda k: (nf[k], k))
    out = [("ny", k) for k in a] + [("ikke verifisert", k) for k in b_] + [("prøv igjen", k) for k in c_]
    return out[:25]


def cmd_venues():
    st, lines, idx, d = load()
    todo = todo_venues(d, st)
    if not todo:
        print("Ingen spillesteder å slå opp i dag.")
        return
    print("Slå opp disse hos Kartverket (maks 25), i denne rekkefølgen:")
    for kind, k in todo:
        print("  %s  [%s]" % (k, kind))


def cmd_positions(path):
    st, lines, idx, d = load()
    apply_positions(st, d, json.load(open(path, encoding="utf-8")))
    save(st, lines, idx, d)


def apply_positions(st, d, p):
    rec = st["pos"]
    for k, v in (p.get("found") or {}).items():
        if "|" not in k or not (isinstance(v, list) and len(v) == 2):
            print("HOPPET OVER posisjon: %s" % k)
            continue
        new = [round(float(v[0]), 4), round(float(v[1]), 4)]
        if not (57.5 < new[0] < 71.5 and 4 < new[1] < 31.5):
            print("HOPPET OVER posisjon utenfor Norge: %s %s" % (k, new))
            continue
        old = d["VENUE_POS"].get(k)
        d["VENUE_POS"][k] = new
        if k not in d["verified"]:
            d["verified"].append(k)
        d["notfound"].pop(k, None)
        if old is None:
            rec["added"].append(k)
        elif abs(old[0] - new[0]) > 0.0005 or abs(old[1] - new[1]) > 0.001:
            rec["corrected"].append(k)
        else:
            rec["same"].append(k)
    for k in p.get("notfound") or []:
        d["notfound"][k] = st["today"]
        rec["notfound"].append(k)
    for k in p.get("skip") or []:
        if k not in d["skip"]:
            d["skip"].append(k)
            rec["skip"].append(k)
        d["notfound"].pop(k, None)
    print("Posisjoner: %d lagt til, %d korrigert, %d uendret, %d ikke funnet, %d satt til skip"
          % (len(rec["added"]), len(rec["corrected"]), len(rec["same"]), len(rec["notfound"]), len(rec["skip"])))


class NoNet(Exception):
    pass


def kv_get(url):
    """GET a Kartverket URL with curl (goes through the workspace proxy; no WebFetch, no prompt)."""
    r = subprocess.run(["curl", "-sS", "-f", "-m", "20", url], capture_output=True, text=True)
    if r.returncode != 0:
        raise NoNet(r.stderr.strip()[:200])
    return json.loads(r.stdout)


def km(a, b):
    from math import radians, cos, sqrt
    dy = (a[0] - b[0]) * 111.2
    dx = (a[1] - b[1]) * 111.2 * cos(radians((a[0] + b[0]) / 2))
    return sqrt(dx * dx + dy * dy)


def near(pt, ref, lim=30):
    return ref is None or km(pt, ref) <= lim


def geo_name(venue, town, ref):
    from urllib.parse import quote
    base = "https://ws.geonorge.no/stedsnavn/v1/navn?utkoordsys=4258&treffPerSide=5&sok=" + quote(venue)
    for url in (base + "&kommunenavn=" + quote(town), base):
        for n in kv_get(url).get("navn") or []:
            rp = n.get("representasjonspunkt") or {}
            if "nord" in rp and "øst" in rp:
                pt = [rp["nord"], rp["øst"]]
                if near(pt, ref):
                    return pt
    return None


def geo_addr(addr, ref):
    from urllib.parse import quote
    url = "https://ws.geonorge.no/adresser/v1/sok?utkoordsys=4258&treffPerSide=5&sok=" + quote(addr)
    for a in kv_get(url).get("adresser") or []:
        rp = a.get("representasjonspunkt") or {}
        if "lat" in rp and "lon" in rp:
            pt = [rp["lat"], rp["lon"]]
            if near(pt, ref):
                return pt
    return None


def cmd_geocode(addr_path):
    st, lines, idx, d = load()
    todo = [k for _, k in todo_venues(d, st)]
    if not todo:
        print("Ingen spillesteder å slå opp i dag.")
        return
    addrs = json.load(open(addr_path, encoding="utf-8")) if addr_path else {}
    found, missing = {}, []
    try:
        for k in todo:
            venue, town = k.rsplit("|", 1)
            c = d["CITY"].get(town)
            ref = [c[0], c[1]] if c else None
            pt = geo_addr(addrs[k] + " " + town, ref) if addrs.get(k) else None
            if pt is None:
                pt = geo_name(venue, town, ref)
            if pt:
                found[k] = pt
            else:
                missing.append(k)
    except NoNet as e:
        print("Kartverket kunne ikke nås (%s). Hopper over posisjoner i dag; prøv igjen i morgen. "
              "List \"Kartverket (posisjoner)\" under --failed." % e)
        if not found:
            return
    p = {"found": found}
    if addr_path:
        p["notfound"] = missing  # tried with name and address: wait a week before the next try
    apply_positions(st, d, p)
    save(st, lines, idx, d)
    if missing and not addr_path:
        print("UTEN TREFF (kan få gateadresse fra et WebSearch-resultat, så geocode --addresses):")
        for k in missing:
            print("  " + k)


def short_date(s):
    y, m, dd = s.split("-")
    return "%d. %s" % (int(dd), MONTHS[int(m) - 1])


def pl(n, one, many):
    return "%d %s" % (n, one if n == 1 else many)


def cap(items, n=8):
    return items if len(items) <= n else items[:n - 1] + ["… og %d til" % (len(items) - n + 1)]


FAVS = os.path.join(ROOT, "favoritter.json")


def fav_words(s):
    """Same normalising as the page: lower case, leading "The" dropped, everything but letters/digits -> one space."""
    s = unicodedata.normalize("NFKC", str(s)).lower().strip()
    r = re.sub(r"\s+", " ", s)
    s = re.sub(r"^the\s+", "", s)
    return " ".join(re.findall(r"[^\W_]+", s)) or r  # a name of signs only (the band "!!!") keeps its signs


def fav_file():
    """favoritter.json as it is in the repo (stars, artists, venues, and "seen": the last update day the user has
    looked at on the website, as a day number – the Claude app starts from it)."""
    try:
        f = json.load(open(FAVS, encoding="utf-8"))
    except Exception:
        f = {}
    out = {k: [x for x in f.get(k) or [] if isinstance(x, str)] for k in ("stars", "artists", "venues")}
    if isinstance(f.get("seen"), int) and f["seen"] > 0:
        out["seen"] = f["seen"]
    if f.get("push") is False:  # push notification switched off in the calendar's settings (absent = on)
        out["push"] = False
    return out


def load_favs():
    """Favourite artists and venues from favoritter.json (written by the page on every device)."""
    try:
        f = json.load(open(FAVS, encoding="utf-8"))
    except Exception:
        return [], set()
    arts = [fav_words(a) for a in f.get("artists") or [] if fav_words(a)]
    vens = {str(v).strip().lower() for v in f.get("venues") or []}
    return arts, vens


def fav_artist(name, arts):
    """Same rule as the page: same name, or the favourite's name as whole words inside a longer act name."""
    n = fav_words(name)
    c = n.replace(" ", "")  # "a-ha" = "aha": the whole name written with or without spaces/dashes
    if any(k == n or k.replace(" ", "") == c for k in arts):
        return True
    raw = unicodedata.normalize("NFKC", str(name)).lower().strip()
    if any(not re.search(r"[^\W_]", k) and (raw == k or (raw.startswith(k) and re.match(r"[\s(–-]", raw[len(k):])))
           for k in arts):  # sign-only favourite like "!!!" matches "!!! (Chk Chk Chk)"
        return True
    # a tribute concert counts only for the tribute band itself, never for the artist it pays tribute to
    tr = bool(FAV_TRIB_RE.search(str(name)))
    t = own_name(name) if tr else n
    if not t:
        return False
    s, tc = " " + t + " ", t.replace(" ", "")
    return any((k == t or k.replace(" ", "") == tc or (len(k) >= 4 and " " + k + " " in s)) and not (tr and trib_to(n, t, k))
               for k in arts)


def trib_to(n, t, k):
    """True when a tribute act names the artist it honours ("abba hyllest", "spiller ac dc", "tribute til …"),
    looking only after the band's own name t (so "Bon Scotch (tribute til …)" is still Bon Scotch)."""
    s = " " + (n[len(t):] if t and n.startswith(t) else n) + " "
    return any(" " + x + " " in s for x in (k + " hyllest", k + " tribute", "tribute to " + k, "tribute til " + k,
                                             "hyllest til " + k, "music of " + k, "best of " + k, "spiller " + k,
                                             "synger " + k, "plays " + k))


# for favourites, "The Music of ABBA", "The Best of …" and "X synger Y" count as tributes too (same rule as the page)
FAV_TRIB_RE = re.compile(r"tribute|hyllest|candlelight|music of|best of|\bsynger\b|\bspiller\b|\bplays\b", re.I)


def own_name(name):
    """A tribute act's own name: before any bracket, dash or colon, and before "(a) tribute"/"hyllest"."""
    s = re.split(r"\s+[–-]\s+|\s*\(|:\s", str(name))[0]
    m = re.search(r"\b(a\s+)?(tribute|hyllest|candlelight)\b|\b(the\s+)?(music|best) of\b|\b(synger|spiller|plays)\b", s, re.I)
    return fav_words(s[:m.start()] if m else s)


def check_scripts(path):
    s = open(path, encoding="utf-8").read()
    blocks = re.findall(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", s, re.S)
    tmp = os.path.join(KK if os.path.isdir(KK) else ROOT, "_blocks.json")
    json.dump(blocks, open(tmp, "w", encoding="utf-8"))
    js = ("const b=JSON.parse(require('fs').readFileSync(process.argv[1],'utf8'));let bad=0;"
          "b.forEach((x,i)=>{try{new Function(x)}catch(e){bad++;console.log('script '+i+': '+e.message)}});"
          "console.log(b.length+' skript, '+bad+' feil');process.exit(bad?1:0)")
    r = subprocess.run(["node", "-e", js, tmp], capture_output=True, text=True)
    os.remove(tmp)
    return r.returncode == 0, (r.stdout + r.stderr).strip()


def cmd_finish(failed, highlights):
    st, lines, idx, d = load()
    old_c = (d.get("ADDED") or {}).get("c") or []
    n_start = len(st["orig_keys"])
    prev_day = {}
    for i, r in enumerate(d["DATA"]):
        if i < n_start and i < len(old_c) and old_c[i]:
            prev_day[key(r)] = old_c[i]
    t = st["today"]
    n0 = len(d["DATA"])
    d["DATA"] = [r for r in d["DATA"] if r[0] >= t]
    removed = n0 - len(d["DATA"])
    fests_gone = [f["name"] for f in d["FESTS"] if f["end"] < t]
    d["FESTS"] = [f for f in d["FESTS"] if f["end"] >= t]
    d["DATA"].sort(key=lambda r: (r[0], r[3].lower(), r[1].lower()))
    d["FESTS"].sort(key=lambda f: (f["start"], f["name"]))
    ks = venue_keys(d)
    d["skip"] = [k for k in d["skip"] if k in ks]
    d["notfound"] = {k: v for k, v in d["notfound"].items() if k in ks}
    missing = sorted(c for c in cities_used(d) if c not in d["CITY"])
    if missing:
        die("disse byene mangler i CITY – legg dem til med add {\"cities\": …} og kjør finish igjen: " + ", ".join(missing))

    live = {key(r) for r in d["DATA"]}
    added = [a for a in st["added"] if a["k"] in live]
    trib = [a for a in added if a["tribute"]]
    by_src = {}
    for a in added:
        s = a["src"] if a["src"] in ("Eventworld", "Songkick", "TicketCo", "Fever") else "spillesteder og arrangører"
        by_src[s] = by_src.get(s, 0) + 1
    order = ["Songkick", "TicketCo", "Fever", "Eventworld", "spillesteder og arrangører"]
    src_txt = ", ".join("%d fra %s" % (by_src[s], s) for s in sorted(by_src, key=lambda s: (-by_src[s], order.index(s))))
    prio = [a for a in added if a["venue"] + "|" + a["city"] in PRIORITY]
    fest_lines, fest_head = [], []
    alive = {f["name"] for f in d["FESTS"]}
    for name, txt in st["fest_new"]:
        if name in alive:
            fest_lines.append("Ny festival: " + txt)
    for name, r in st["fest"].items():
        if name not in alive:
            continue
        if r["artists"]:
            fest_lines.append("%s: %s" % (name, pl(r["artists"], "ny artist", "nye artister")))
            fest_head.append((r["artists"], name))
        if r["days"]:
            fest_lines.append("%s: spilledag fylt inn for %s" % (name, pl(r["days"], "artist", "artister")))
    fest_lines += st["fest_dates"]
    if fests_gone:
        fest_lines.append("Ferdige festivaler fjernet: " + ", ".join(fests_gone))
    pos = st["pos"]
    pos_lines = []
    chk = len(pos["added"]) + len(pos["corrected"]) + len(pos["same"])
    if chk:
        pos_lines.append("%s sjekket mot Kartverket: %d lagt til, %d korrigert"
                         % (pl(chk, "posisjon", "posisjoner"), len(pos["added"]), len(pos["corrected"])))
        named = [k.replace("|", ", ") for k in (pos["corrected"] + pos["added"])[:4]]
        if named:
            pos_lines.append("Bl.a. " + "; ".join(named))
    if pos["notfound"]:
        pos_lines.append("Ikke funnet denne gangen: " + "; ".join(k.replace("|", ", ") for k in pos["notfound"][:5])
                         + (" … og %d til" % (len(pos["notfound"]) - 5) if len(pos["notfound"]) > 5 else ""))

    arts, vens = load_favs()
    fav_items = []
    for a in added:
        if fav_artist(a["artist"], arts):
            fav_items.append("♥ %s (%s, %s, %s)" % (a["artist"], a["venue"], a["city"], short_date(a["date"])))
        elif (a["venue"] + "|" + a["city"]).lower() in vens:
            fav_items.append("📍 %s: %s (%s)" % (a["venue"], a["artist"], short_date(a["date"])))
    for fname, artist, fven, fcity, day, fs, fe in st.get("fest_added", []):
        if fname not in alive:
            continue
        if fav_artist(artist, arts):
            fav_items.append("♥ %s spiller på %s (%s)" % (artist, fname, short_date(day) if day else short_date(fs) + "–" + short_date(fe)))
        elif (fven + "|" + fcity).lower() in vens:
            fav_items.append("📍 %s: %s (%s)" % (fname, artist, short_date(day) if day else "dag ikke kjent"))
    for name, txt in st["fest_new"]:
        f = next((x for x in d["FESTS"] if x["name"] == name), None)
        if f and (f["venue"] + "|" + f["city"]).lower() in vens:
            fav_items.append("📍 Ny festival på %s: %s" % (f["venue"], txt))

    secs = []
    if fav_items:
        secs.append({"t": "Nytt fra favorittene", "items": fav_items})  # always the full list
    if added or removed:
        items = []
        if added:
            items.append("%s: %s" % (pl(len(added), "ny konsert", "nye konserter"), src_txt))
            hl = [h.strip() for h in (highlights or "").split(";") if h.strip()]
            if not hl:
                big = sorted(added, key=lambda a: (0 if a["venue"] + "|" + a["city"] in PRIORITY else 1,
                                                    BIG_CITIES.index(a["city"]) if a["city"] in BIG_CITIES else 99, a["date"]))
                hl = ["%s (%s)" % (a["artist"], a["venue"]) for a in big[:3]]
            items.append("Bl.a. " + ", ".join(hl))
        if removed:
            items.append(pl(removed, "passert konsert er fjernet", "passerte konserter er fjernet"))
        secs.append({"t": "Nye konserter", "items": items})
    if prio:
        secs.append({"t": "Prioriterte scener", "items": ["%s (%s, %s)" % (a["artist"], a["venue"], short_date(a["date"])) for a in prio]})
    if trib:
        secs.append({"t": "Tributekonserter", "items": ["%s (%s, %s)" % (a["artist"], a["venue"], a["city"]) for a in trib]})
    if fest_lines:
        secs.append({"t": "Festivaler", "items": fest_lines})
    if pos_lines:
        secs.append({"t": "Spillesteder", "items": pos_lines})
    fl = [x.strip() for x in (failed or "").split(";") if x.strip()]
    if fl:
        secs.append({"t": "Kunne ikke sjekkes", "items": fl})
    for s in secs:
        s["items"] = [i.replace("</", "< /") for i in s["items"]]

    if added:
        parts = [pl(len(added), "ny konsert", "nye konserter")]
        if trib:
            parts.append(pl(len(trib), "tributekonsert", "tributekonserter"))
        if fest_head:
            n, name = max(fest_head)
            parts.append("%s: %s" % (name, pl(n, "ny artist", "nye artister")))
        elif any(nm in alive for nm, _ in st["fest_new"]):
            parts.append(pl(sum(1 for nm, _ in st["fest_new"] if nm in alive), "ny festival", "nye festivaler"))
        head = " · ".join(parts)
    elif fest_head:
        n, name = max(fest_head)
        head = "Ingen nye konserter i dag · %s: %s" % (name, pl(n, "ny artist", "nye artister"))
    else:
        head = "Ingen nye konserter i dag"
    if fav_items:
        head = "%s fra favorittene · %s" % (pl(len(fav_items), "nyhet", "nyheter"), head)
    d["SUMMARY"] = {"head": head, "sections": secs}

    # ADDED: the day each concert / festival artist came in, as a day number (days since 2026-01-01, 0 = from before
    # this was tracked). "c" runs parallel to DATA (same order), "f" is {"Festival|Artist": day}. No time limit: a
    # mark stays until the concert has passed. The page and Mine sider use it to show what is new from the
    # favourites since the user last looked on that device.
    tn = day_no(t)
    new_keys = {a["k"] for a in added}
    c = []
    for r in d["DATA"]:
        c.append(tn if key(r) in new_keys else prev_day.get(key(r), 0))
    live_fa = {}
    for f in d["FESTS"]:
        for a_ in f.get("lineup", []):
            n = a_["n"] if isinstance(a_, dict) else a_
            live_fa[f["name"] + "|" + n] = (f, n)
    fd = {k: v for k, v in ((d.get("ADDED") or {}).get("f") or {}).items() if k in live_fa}
    for fname, artist, *_ in st.get("fest_added", []):
        if fname + "|" + artist in live_fa:
            fd[fname + "|" + artist] = tn
    d["ADDED"] = {"day": t, "c": c, "f": fd}
    ids = {}
    live_ids = {}
    for r, v in zip(d["DATA"], c):
        if v:
            k = r[0] + "|" + r[1] + "|" + r[2]
            ids[k] = day_str(v)
            live_ids[k] = ("c", r)
    for k, v in fd.items():
        ids["fa|" + k] = day_str(v)
        live_ids["fa|" + k] = ("f",) + live_fa[k]
    fav_new = []
    for k, v in ids.items():
        x = live_ids[k]
        if x[0] == "c":
            r = x[1]
            if fav_artist(r[1], arts):
                fav_new.append({"d": v, "t": "♥ %s (%s, %s)" % (r[1], r[2], short_date(r[0]))})
            elif (r[2] + "|" + r[3]).lower() in vens:
                fav_new.append({"d": v, "t": "📍 %s: %s (%s)" % (r[2], r[1], short_date(r[0]))})
        else:
            f, n = x[1], x[2]
            if fav_artist(n, arts) or (f["venue"] + "|" + f["city"]).lower() in vens:
                fav_new.append({"d": v, "t": "%s %s på %s" % ("♥" if fav_artist(n, arts) else "📍", n, f["name"])})
    fav_new.sort(key=lambda x: (x["d"], x["t"]), reverse=True)
    json.dump({"day": t, "fav": fav_new}, open(NYTT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    d["FAVS"] = fav_file()  # the Claude app shows the favourites as they are this morning

    n = now()
    stamp = "%s %s kl. %s" % (WEEKDAYS[n.weekday()], n.strftime("%d.%m.%Y"), n.strftime("%H.%M"))
    write_page(lines, idx, d, OUT)
    s = open(OUT, encoding="utf-8").read()
    esc = head.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    s, c1 = re.subn(r'(<b id="upd">)[^<]*(</b>)', lambda m: m.group(1) + stamp + m.group(2), s, count=1)
    s, c2 = re.subn(r'(<span class="nt" id="sum">)[^<]*(</span>)', lambda m: m.group(1) + esc + m.group(2), s, count=1)
    if not (c1 and c2):
        die("fant ikke tidsstempel eller sammendragsboks i siden")
    open(OUT, "w", encoding="utf-8").write(s)
    ok, msg = check_scripts(OUT)
    if not ok:
        die("skriptsjekk feilet – artifact.html er IKKE klar: " + msg)

    print("artifact.html klar (%s). %s" % (stamp, msg))
    print("HEAD: " + head)
    print("MELDING:")
    print("\n".join(["- " + s_["t"] + ": " + " | ".join(s_["items"]) for s_ in secs]) or "- Ingen endringer")
    print("Totalt: %d konserter, %d festivaler" % (len(d["DATA"]), len(d["FESTS"])))
    if fav_items and fav_file().get("push") is False:
        print("Push-varsel er slått av i kalenderens innstillinger, så det sendes ikke.")
        print("VARSEL: (ingen)")
    elif fav_items:
        names = []
        for i in fav_items:
            nm = re.sub(r"^\S+\s+", "", i)
            nm = nm.split(":", 1)[1].strip() if nm.startswith(tuple(v.split("|")[0] for v in fav_file()["venues"])) and ":" in nm else nm
            names.append(re.sub(r"\s*\(.*$", "", nm))
        uniq = list(dict.fromkeys(names))
        txt = ", ".join(uniq[:4]) + (" og %d til" % (len(uniq) - 4) if len(uniq) > 4 else "")
        print("VARSEL: Konsertkalender: %s fra favorittene – %s" % (pl(len(fav_items), "nyhet", "nyheter"), txt))
    else:
        print("VARSEL: (ingen)")


def main(a):
    if len(a) < 1:
        die(__doc__)
    c = a[0]
    if c == "start" and len(a) == 2:
        cmd_start(a[1])
    elif c == "add" and len(a) == 2:
        cmd_add(a[1])
    elif c == "venues":
        cmd_venues()
    elif c == "positions" and len(a) == 2:
        cmd_positions(a[1])
    elif c == "geocode" and len(a) in (1, 3) and (len(a) == 1 or a[1] == "--addresses"):
        cmd_geocode(a[2] if len(a) == 3 else None)
    elif c == "finish":
        opts = dict(zip(a[1::2], a[2::2]))
        cmd_finish(opts.get("--failed"), opts.get("--highlights"))
    elif c == "check" and len(a) == 2:
        ok, msg = check_scripts(a[1])
        print(msg)
        sys.exit(0 if ok else 1)
    else:
        die(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
