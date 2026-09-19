"""Redraw the moving parts of the profile README: the ink painting, the
open-source trail and the stats card, each in a light and a dark version.

Usage:  GH_TOKEN=... GH_LOGIN=Samurai007AK python scripts/daily.py <out_dir>

Standard library only, so the GitHub Action needs no pip install.
"""

import datetime as dt
import json
import math
import os
import random
import sys
import textwrap
import urllib.request
from html import escape
from pathlib import Path

HERE = Path(__file__).resolve().parent

THEMES = {
    "light": dict(paper="#f3ead7", ink="#1d1a16", wash="#6b645a", red="#b3261e",
                  moon="#fffaf0", moon_dark="#1d1a16", petal="#d98a94"),
    "dark": dict(paper="#0f0e0d", ink="#ece4d3", wash="#a39a8b", red="#d0402f",
                 moon="#f1e8d2", moon_dark="#ece4d3", petal="#e3a2ab"),
}
SERIF = "Georgia, 'Times New Roman', serif"
SEAL_TEXT = "#f7f0e1"  # carved-out colour inside red seals, same in both themes
# Notebook outputs and generated HTML inflate byte counts without being hand-written code.
IGNORED_LANGS = {"Jupyter Notebook", "HTML"}

# Shared by every card: paper grain and a displacement that roughens edges like a brush.
DEFS = """<defs>
<filter id="grain" x="0" y="0" width="100%" height="100%">
  <feTurbulence type="fractalNoise" baseFrequency="0.9" numOctaves="2" seed="7"/>
  <feColorMatrix values="0 0 0 0 0.5  0 0 0 0 0.45  0 0 0 0 0.4  0 0 0 0.06 0"/>
</filter>
<filter id="brush" x="-5%" y="-5%" width="110%" height="110%">
  <feTurbulence type="fractalNoise" baseFrequency="0.035" numOctaves="3" seed="3" result="n"/>
  <feDisplacementMap in="SourceGraphic" in2="n" scale="5"/>
</filter>
</defs>"""


def svg(w, h, t, body):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}">'
            f'{DEFS}<clipPath id="card"><rect width="{w}" height="{h}" rx="10"/></clipPath>'
            f'<g clip-path="url(#card)"><rect width="{w}" height="{h}" fill="{t["paper"]}"/>'
            f'<rect width="{w}" height="{h}" filter="url(#grain)"/>{body}</g></svg>')


# ---------------------------------------------------------------- data

QUERY = """
query($login: String!, $month: DateTime!, $prs: String!) {
  user(login: $login) {
    year: contributionsCollection {
      contributionCalendar { totalContributions weeks { contributionDays { date contributionCount } } }
    }
    month: contributionsCollection(from: $month) {
      commitContributionsByRepository(maxRepositories: 25) { contributions { totalCount } }
    }
    repositories(ownerAffiliations: OWNER, isFork: false, first: 100) {
      nodes { languages(first: 10, orderBy: {field: SIZE, direction: DESC}) { edges { size node { name } } } }
    }
  }
  search(query: $prs, type: ISSUE, first: 100) {
    nodes { ... on PullRequest { title merged mergedAt createdAt state repository { nameWithOwner } } }
  }
}"""


def fetch(login, token, now):
    variables = {
        "login": login,
        "month": (now - dt.timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        # ponytail: first 100 PRs only, paginate if the trail ever outgrows it
        "prs": f"is:pr author:{login} -user:{login} sort:updated-desc",
    }
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": QUERY, "variables": variables}).encode(),
        headers={"Authorization": f"bearer {token}", "User-Agent": "profile-ink"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        warn_if_expiring(resp.headers.get("github-authentication-token-expiration"), now)
        body = json.load(resp)
    if body.get("errors"):
        sys.exit(f"GraphQL errors: {body['errors']}")
    return body["data"]


def warn_if_expiring(header, now):
    if not header:
        print("::notice::Token has no expiry header (GITHUB_TOKEN or a non-expiring token).")
        return
    expires = dt.datetime.strptime(header.replace(" UTC", ""), "%Y-%m-%d %H:%M:%S").replace(tzinfo=dt.timezone.utc)
    days = (expires - now).days
    if days < 30:
        print(f"::warning::PROFILE_TOKEN expires in {days} days ({header}). Create a new one and update the secret.")
    else:
        print(f"Token valid for {days} more days.")


def summarize(data, now):
    user = data["user"]
    days = [d for w in user["year"]["contributionCalendar"]["weeks"] for d in w["contributionDays"]]
    counts = [d["contributionCount"] for d in days]
    longest = best = 0
    for c in counts:
        best = best + 1 if c else 0
        longest = max(longest, best)

    langs = {}
    for repo in user["repositories"]["nodes"]:
        for e in repo["languages"]["edges"]:
            if e["node"]["name"] in IGNORED_LANGS:
                continue
            langs[e["node"]["name"]] = langs.get(e["node"]["name"], 0) + e["size"]
    total = sum(langs.values()) or 1
    top = sorted(langs.items(), key=lambda kv: -kv[1])[:6]

    repos = {}
    for pr in data["search"]["nodes"]:
        if not pr or (pr["state"] == "CLOSED" and not pr["merged"]):
            continue
        r = repos.setdefault(pr["repository"]["nameWithOwner"],
                             dict(merged=0, open=0, last="", title=""))
        r["merged" if pr["merged"] else "open"] += 1
        when = pr["mergedAt"] or pr["createdAt"]
        if when > r["last"]:
            r["last"], r["title"] = when, pr["title"]
    # Projects with merged work first, newest activity first within each group.
    trail = sorted(repos.items(), key=lambda kv: kv[1]["last"], reverse=True)
    trail.sort(key=lambda kv: kv[1]["merged"] == 0)
    month_ago = (now - dt.timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
    recent_merges = [pr for pr in data["search"]["nodes"]
                     if pr and pr["merged"] and pr["mergedAt"] >= month_ago]

    return dict(
        contributions=user["year"]["contributionCalendar"]["totalContributions"],
        active=sum(1 for c in counts if c), longest=longest,
        stalks=[r["contributions"]["totalCount"] for r in user["month"]["commitContributionsByRepository"]],
        merged=sum(r["merged"] for _, r in trail),
        projects=len(trail),
        trail=trail[:8],
        recent_merges=recent_merges,
        langs=[(name, size / total) for name, size in top],
    )


# ---------------------------------------------------------------- painting

def moon_phase(now):
    ref = dt.datetime(2000, 1, 6, 18, 14, tzinfo=dt.timezone.utc)  # a known new moon
    return ((now - ref).total_seconds() / 86400 / 29.530588853) % 1


def moon(cx, cy, r, p, t):
    lit = (1 - math.cos(2 * math.pi * p)) / 2
    rx = abs(1 - 2 * lit) * r
    top, bot = f"{cx},{cy - r}", f"{cx},{cy + r}"
    waxing = p < 0.5
    limb = 1 if waxing else 0
    term = (0 if lit < 0.5 else 1) if waxing else (1 if lit < 0.5 else 0)
    shape = f"M{top} A{r},{r} 0 0 {limb} {bot} A{rx:.1f},{r} 0 0 {term} {top}Z"
    return (f'<circle cx="{cx}" cy="{cy}" r="{r + 10}" fill="{t["moon"]}" opacity="0.25"/>'
            f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{t["moon_dark"]}" opacity="0.10"/>'
            f'<path d="{shape}" fill="{t["moon"]}"/>'
            f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{t["wash"]}" stroke-width="0.8" opacity="0.6"/>')


def ridge(rng, x0, x1, base, amp, n=90):
    peaks = [(rng.uniform(0.15, 0.85), rng.uniform(0.08, 0.2), rng.uniform(0.5, 1)) for _ in range(3)]
    pts = []
    for i in range(n + 1):
        u = i / n
        h = sum(a * math.exp(-((u - c) / w) ** 2) for c, w, a in peaks)
        h += 0.04 * math.sin(u * 40 + peaks[0][0] * 9)
        pts.append(f"{x0 + (x1 - x0) * u:.1f},{base - amp * h:.1f}")
    return "M" + " L".join(pts) + f" L{x1},{base + 80} L{x0},{base + 80}Z"


def mountains(rng, t, width):
    # Fade both sides so the range dissolves into the paper instead of ending in a hard edge.
    out = ['<linearGradient id="fadeg" x1="0" y1="0" x2="1" y2="0">'
           '<stop offset="0" stop-color="#fff" stop-opacity="0"/><stop offset="0.15" stop-color="#fff"/>'
           '<stop offset="0.85" stop-color="#fff"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient>'
           f'<mask id="fade"><rect x="-20" y="0" width="{width + 40}" height="600" fill="url(#fadeg)"/></mask>'
           '<g mask="url(#fade)">']
    for i, (base, amp, alpha) in enumerate([(245, 120, 0.22), (285, 80, 0.4), (325, 42, 0.62)]):
        out.append(f'<linearGradient id="m{i}" x1="0" y1="0" x2="0" y2="1">'
                   f'<stop offset="0" stop-color="{t["ink"]}" stop-opacity="{alpha}"/>'
                   f'<stop offset="0.55" stop-color="{t["ink"]}" stop-opacity="{alpha * 0.35}"/>'
                   f'<stop offset="1" stop-color="{t["ink"]}" stop-opacity="0"/></linearGradient>'
                   f'<path d="{ridge(rng, -20, width + 20, base, amp)}" fill="url(#m{i})" filter="url(#brush)"/>')
    out.append(f'<linearGradient id="mist" x1="0" y1="0" x2="0" y2="1">'
               f'<stop offset="0" stop-color="{t["paper"]}" stop-opacity="0"/>'
               f'<stop offset="0.5" stop-color="{t["paper"]}" stop-opacity="0.75"/>'
               f'<stop offset="1" stop-color="{t["paper"]}" stop-opacity="0"/></linearGradient>'
               f'<rect x="-20" y="215" width="{width + 40}" height="70" fill="url(#mist)"/></g>')
    return "".join(out)


def leaf(x, y, length, angle, t, alpha):
    w = length * 0.13
    d = f"M0,0 Q{length * 0.45:.1f},{-w:.1f} {length:.1f},0 Q{length * 0.45:.1f},{w:.1f} 0,0Z"
    return (f'<path d="{d}" fill="{t["ink"]}" opacity="{alpha:.2f}" '
            f'transform="translate({x:.1f},{y:.1f}) rotate({angle:.0f})"/>')


def bamboo(rng, x, commits, t, ground):
    height = min(300, 110 + 42 * math.log2(1 + commits))
    width = rng.uniform(6, 9)
    alpha = rng.uniform(0.7, 0.95)
    out, y = [], ground
    while y > ground - height:
        seg = rng.uniform(26, 40)
        top = max(y - seg, ground - height)
        out.append(f'<rect x="{x - width / 2:.1f}" y="{top:.1f}" width="{width:.1f}" height="{y - top - 2.5:.1f}" '
                   f'rx="2" fill="{t["ink"]}" opacity="{alpha:.2f}"/>')
        out.append(f'<path d="M{x - width / 2 - 2:.1f},{top - 1:.1f} h{width + 4:.1f}" stroke="{t["ink"]}" '
                   f'stroke-width="1.6" opacity="{alpha:.2f}"/>')
        if y < ground - 70 and rng.random() < 0.55:
            side = rng.choice([-1, 1])
            for _ in range(rng.randint(2, 4)):
                ang = rng.uniform(10, 45) if side > 0 else rng.uniform(135, 170)  # leaves droop
                out.append(leaf(x, top, rng.uniform(28, 48), ang, t, alpha * rng.uniform(0.6, 1)))
        y = top
    return "".join(out)


def seal(x, y, size, t, glyph=True):
    if glyph:
        d = (HERE / "seal.txt").read_text().strip()
        inner = (f'<path d="{d}" fill="{SEAL_TEXT}" '
                 f'transform="translate({x + size * 0.1:.1f},{y + size * 0.1:.1f}) scale({size / 100 * 0.8:.3f})"/>')
    else:
        inner = (f'<rect x="{x + size * 0.18:.1f}" y="{y + size * 0.18:.1f}" width="{size * 0.64:.1f}" '
                 f'height="{size * 0.64:.1f}" fill="none" stroke="{SEAL_TEXT}" stroke-width="1.4"/>')
    return (f'<g filter="url(#brush)"><rect x="{x}" y="{y}" width="{size}" height="{size}" rx="2" '
            f'fill="{t["red"]}"/>{inner}</g>')


# One quote per day, in order, so none repeats until the list runs out.
# Kept short on purpose: the quote card fits two lines, so stay at about 60 characters.
QUOTES = [
    ("The important thing is not to stop questioning.", "Albert Einstein"),
    ("What I cannot create, I do not understand.", "Richard Feynman"),
    ("I have no special talents. I am only passionately curious.", "Albert Einstein"),
    ("Nothing in life is to be feared, it is only to be understood.", "Marie Curie"),
    ("Simplicity is prerequisite for reliability.", "Edsger W. Dijkstra"),
    ("Premature optimization is the root of all evil.", "Donald Knuth"),
    ("Talk is cheap. Show me the code.", "Linus Torvalds"),
    ("Make it work, make it right, make it fast.", "Kent Beck"),
    ("Do nothing that is of no use.", "Miyamoto Musashi"),
    ("Think lightly of yourself and deeply of the world.", "Miyamoto Musashi"),
    ("Fall seven times, stand up eight.", "Japanese proverb"),
    ("Arise, awake, and stop not till the goal is reached.", "Swami Vivekananda"),
    ("You have to dream before your dreams can come true.", "A. P. J. Abdul Kalam"),
    ("The unexamined life is not worth living.", "Socrates"),
    ("Knowing is not enough; we must apply.", "Johann Wolfgang von Goethe"),
    ("Doubt is not a pleasant condition, but certainty is absurd.", "Voltaire"),
    ("The perfect is the enemy of the good.", "Voltaire"),
    ("Well begun is half done.", "Aristotle"),
    ("Knowledge is power.", "Francis Bacon"),
    ("Dare to know.", "Immanuel Kant"),
]
assert all(len(q) <= 62 for q, _ in QUOTES), "quote too long for the card"


def painting(s, t, now):
    W, H, PW = 840, 320, 300
    rng = random.Random(now.date().isoformat())
    body = [f'<svg x="0" y="0" width="{PW}" height="{H}" viewBox="0 0 {PW} 360" preserveAspectRatio="xMidYMax slice">'
            f'{mountains(rng, t, PW)}{moon(220, 70, 24, moon_phase(now), t)}']
    if now.month in (3, 4, 5):
        for _ in range(12):
            px, py = rng.uniform(10, PW - 10), rng.uniform(20, 300)
            body.append(f'<ellipse cx="{px:.1f}" cy="{py:.1f}" rx="3.2" ry="1.8" fill="{t["petal"]}" '
                        f'opacity="{rng.uniform(0.5, 0.9):.2f}" transform="rotate({rng.uniform(0, 180):.0f} {px:.1f} {py:.1f})"/>')
    for i, commits in enumerate(sorted(s["stalks"][:6], key=lambda c: rng.random()) or [0]):
        body.append(bamboo(rng, 30 + i * 26 + rng.uniform(-4, 4), commits, t, 344))
    body.append('</svg>')
    body.append(f'<rect x="{PW}" y="0" width="6" height="{H}" fill="{t["red"]}" opacity="0.9"/>')

    quote, author = QUOTES[now.date().toordinal() % len(QUOTES)]
    lines = textwrap.wrap(quote, 34)
    y = H / 2 - (len(lines) - 1) * 18 + 4
    body.append(f'<text x="{PW + 50}" y="{y - 34:.0f}" font-family="{SERIF}" font-size="64" fill="{t["red"]}">&#8220;</text>')
    for i, line in enumerate(lines):
        body.append(f'<text x="{PW + 56}" y="{y + i * 36:.0f}" font-family="{SERIF}" font-size="25" font-style="italic" '
                    f'fill="{t["ink"]}">{escape(line)}</text>')
    body.append(f'<text x="{PW + 56}" y="{y + len(lines) * 36 + 6:.0f}" font-family="{SERIF}" font-size="12" '
                f'letter-spacing="2.5" fill="{t["wash"]}">{escape(author.upper())}</text>')
    for i in range(min(len(s["recent_merges"]), 7)):
        body.append(seal(W - 44 - i * 24, H - 42, 18, t, glyph=False))
    return svg(W, H, t, "".join(body))


# ---------------------------------------------------------------- trail + stats

def ago(iso, now):
    d = (now - dt.datetime.fromisoformat(iso.replace("Z", "+00:00"))).days
    return "today" if d < 1 else f"{d}d ago" if d < 60 else f"{d // 30}mo ago"


def trail(s, t, now):
    W, row = 840, 54
    H = 30 + row * len(s["trail"]) + 26
    out = []
    for i, (name, r) in enumerate(s["trail"]):
        y = 22 + i * row
        merged = r["merged"] > 0
        label = f'{r["merged"]} MERGED' if merged else f'{r["open"]} OPEN'
        box = (f'<rect x="24" y="{y + 6}" width="92" height="26" rx="2" fill="{t["red"]}"/>' if merged else
               f'<rect x="24.5" y="{y + 6.5}" width="91" height="25" rx="2" fill="none" stroke="{t["ink"]}"/>')
        out.append(f'<g filter="url(#brush)">{box}</g>')
        out.append(f'<text x="70" y="{y + 23}" text-anchor="middle" font-family="{SERIF}" font-size="11" '
                   f'letter-spacing="1.5" fill="{SEAL_TEXT if merged else t["ink"]}">{label}</text>')
        title = r["title"] if len(r["title"]) <= 78 else r["title"][:75] + "..."
        out.append(f'<text x="136" y="{y + 18}" font-family="{SERIF}" font-size="16" font-weight="bold" '
                   f'fill="{t["ink"]}">{escape(name)}</text>')
        out.append(f'<text x="136" y="{y + 38}" font-family="{SERIF}" font-size="13" fill="{t["wash"]}">'
                   f'{escape(title)}</text>')
        extra = f'+{r["open"]} open · ' if merged and r["open"] else ""
        out.append(f'<text x="{W - 24}" y="{y + 18}" text-anchor="end" font-family="{SERIF}" font-size="12" '
                   f'fill="{t["wash"]}">{extra}{ago(r["last"], now)}</text>')
        if i:
            out.append(f'<path d="M136,{y - 2} H{W - 24}" stroke="{t["wash"]}" stroke-width="0.6" opacity="0.35"/>')
    out.append(f'<text x="{W / 2}" y="{H - 14}" text-anchor="middle" font-family="{SERIF}" font-size="11" '
               f'letter-spacing="2" fill="{t["wash"]}">PULL REQUESTS TO OTHER PEOPLE\'S PROJECTS · REDRAWN DAILY</text>')
    return svg(W, H, t, "".join(out))


def stats(s, t, now):
    W, H = 840, 270
    nums = [(s["contributions"], "CONTRIBUTIONS", "last 12 months"),
            (s["active"], "ACTIVE DAYS", "last 12 months"),
            (s["longest"], "LONGEST STREAK", "days, last 12 months"),
            (s["merged"], "MERGED UPSTREAM", "pull requests"),
            (s["projects"], "PROJECTS", "contributed to")]
    out = []
    for i, (n, label, sub) in enumerate(nums):
        cx = 84 + 168 * i
        out.append(f'<text x="{cx}" y="66" text-anchor="middle" font-family="{SERIF}" font-size="38" '
                   f'fill="{t["red"] if i == 0 else t["ink"]}">{n:,}</text>')
        out.append(f'<text x="{cx}" y="92" text-anchor="middle" font-family="{SERIF}" font-size="11" '
                   f'letter-spacing="2" fill="{t["ink"]}">{label}</text>')
        out.append(f'<text x="{cx}" y="108" text-anchor="middle" font-family="{SERIF}" font-size="11" '
                   f'font-style="italic" fill="{t["wash"]}">{sub}</text>')
    out.append(f'<path d="M40,134 H{W - 40}" stroke="{t["wash"]}" stroke-width="1" opacity="0.5"/>')
    out.append(f'<text x="40" y="162" font-family="{SERIF}" font-size="11" letter-spacing="2" fill="{t["wash"]}">'
               f'LANGUAGES BY CODE SIZE · PUBLIC AND PRIVATE REPOS</text>')
    shares = s["langs"]
    scale = (W - 80) / (sum(f for _, f in shares) or 1)
    x = 40.0
    for i, (name, frac) in enumerate(shares):
        color, alpha = (t["red"], 0.9) if i == 0 else (t["ink"], 0.85 - i * 0.13)
        w = frac * scale
        out.append(f'<rect x="{x:.1f}" y="176" width="{max(w - 3, 2):.1f}" height="18" rx="3" fill="{color}" '
                   f'opacity="{alpha:.2f}" filter="url(#brush)"/>')
        lx, ly = 40 + (i % 3) * 260, 224 + (i // 3) * 22
        out.append(f'<rect x="{lx}" y="{ly - 10}" width="12" height="12" rx="2" fill="{color}" opacity="{alpha:.2f}"/>')
        out.append(f'<text x="{lx + 20}" y="{ly}" font-family="{SERIF}" font-size="13" fill="{t["ink"]}">'
                   f'{escape(name)} <tspan fill="{t["wash"]}">{frac * 100:.1f}%</tspan></text>')
        x += w
    return svg(W, H, t, "".join(out))


def main():
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "dist")
    out.mkdir(parents=True, exist_ok=True)
    token = os.environ.get("GH_TOKEN") or sys.exit("GH_TOKEN is not set")
    login = os.environ.get("GH_LOGIN", "Samurai007AK")
    now = dt.datetime.now(dt.timezone.utc)
    s = summarize(fetch(login, token, now), now)
    for name, t in THEMES.items():
        (out / f"painting-{name}.svg").write_text(painting(s, t, now), encoding="utf-8")
        (out / f"trail-{name}.svg").write_text(trail(s, t, now), encoding="utf-8")
        (out / f"stats-{name}.svg").write_text(stats(s, t, now), encoding="utf-8")
    print(f"Drew {len(s['stalks'])} stalks, {len(s['trail'])} trail rows, {s['contributions']} contributions.")


if __name__ == "__main__":
    main()
