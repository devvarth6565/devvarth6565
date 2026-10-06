#!/usr/bin/env python3
"""Render the neofetch-style terminal card (animated avatar + live stats) on the profile README.

Pulls live GitHub stats (repos, stars, commits, contributions, lines of code)
and writes animated SVGs for dark and light mode. Standard library only, so the
GitHub Action needs no installs. Set GITHUB_TOKEN for higher rate limits and the
GraphQL-only "contributed to" count; without it the last known values in
assets/stats.json are reused for anything that cannot be fetched.
"""

import base64
import datetime as dt
import html
import json
import os
import re
import sys
import time
import urllib.request
from pathlib import Path

USER = "devvarth6565"
ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
TOKEN = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")

# ---------------------------------------------------------------- data ----


def _get(url, accept="application/vnd.github+json"):
    req = urllib.request.Request(url, headers={"Accept": accept, "User-Agent": USER})
    if TOKEN and "api.github.com" in url:
        req.add_header("Authorization", f"Bearer {TOKEN}")
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.status, r.read().decode()


def rest(path):
    return json.loads(_get(f"https://api.github.com{path}")[1])


def graphql(query, variables=None):
    body = json.dumps({"query": query, "variables": variables or {}}).encode()
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=body,
        headers={"Authorization": f"Bearer {TOKEN}", "User-Agent": USER},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())["data"]


def lines_of_code(repos):
    """Sum the user's additions/deletions across every repo they own or forked."""
    add = dele = 0
    pending = [r["name"] for r in repos]
    for attempt in range(8):
        retry = []
        for name in pending:
            status, body = _get(f"https://api.github.com/repos/{USER}/{name}/stats/contributors")
            if status == 202:  # GitHub is still computing the stats
                retry.append(name)
                continue
            for c in json.loads(body or "[]") or []:
                if (c.get("author") or {}).get("login", "").lower() == USER.lower():
                    add += sum(w["a"] for w in c["weeks"])
                    dele += sum(w["d"] for w in c["weeks"])
        if not retry:
            return add, dele
        pending = retry
        time.sleep(4 + attempt * 2)
    raise RuntimeError(f"stats still computing for {pending}")


def fetch_stats(cache):
    s = dict(cache)

    def attempt(key, fn):
        try:
            s.update(fn())
        except Exception as e:  # keep the cached value, never break the card
            print(f"[warn] {key}: {e}")

    user = rest(f"/users/{USER}")
    repos = rest(f"/users/{USER}/repos?per_page=100&type=owner")
    s["created_at"] = user["created_at"]
    s["repos"] = user["public_repos"]
    s["followers"] = user["followers"]
    s["stars"] = sum(r["stargazers_count"] for r in repos)

    attempt("commits", lambda: {
        "commits": rest(f"/search/commits?q=author:{USER}&per_page=1")["total_count"]})

    def contributions():
        page = _get(f"https://github.com/users/{USER}/contributions", "text/html")[1]
        m = re.search(r"([\d,]+)\s+contributions?\s+in the last year", page)
        return {"contributions": int(m.group(1).replace(",", ""))}
    attempt("contributions", contributions)

    def loc():
        a, d = lines_of_code(repos)
        return {"loc_add": a, "loc_del": d}
    attempt("loc", loc)

    if TOKEN:
        def contributed():
            q = """query($login:String!){user(login:$login){
                repositoriesContributedTo(first:1, includeUserRepositories:false,
                  contributionTypes:[COMMIT, PULL_REQUEST, REPOSITORY]){totalCount}}}"""
            d = graphql(q, {"login": USER})
            return {"contributed": d["user"]["repositoriesContributedTo"]["totalCount"]}
        attempt("contributed", contributed)

    return s


# -------------------------------------------------------------- layout ----

COLS = 66  # width of the info column, in characters


def uptime(created):
    start = dt.date.fromisoformat(created[:10])
    today = dt.date.today()
    months = (today.year - start.year) * 12 + today.month - start.month
    if today.day < start.day:
        months -= 1
    anchor_month = start.month + months
    anchor = dt.date(start.year + (anchor_month - 1) // 12, (anchor_month - 1) % 12 + 1, 1)
    anchor = anchor.replace(day=min(start.day, 28))
    days = (today - anchor).days
    y, m = divmod(months, 12)
    plural = lambda n, w: f"{n} {w}{'' if n == 1 else 's'}"
    parts = ([plural(y, "year")] if y else []) + [plural(m, "month"), plural(days, "day")]
    return ", ".join(parts)


def fmt(n):
    return "—" if n is None else f"{n:,}"


def build_lines(s):
    """Each line is a list of (css_class, text) segments."""
    L = []

    def kv(key, value, vcls="v"):
        keys = key.split(".")
        dots = COLS - len(key) - 2 - len(value) - 2
        seg = []
        for i, k in enumerate(keys):
            if i:
                seg.append(("p", "."))
            seg.append(("k", k))
        seg += [("p", ": "), ("d", "." * max(dots, 1) + " "), (vcls, value)]
        L.append(seg)

    def header(title):
        L.append([("p", "- "), ("h", title), ("p", " " + "─" * (COLS - len(title) - 4))])

    def blank():
        L.append([])

    L.append([("g", "devvarth@github"), ("p", " " + "─" * (COLS - 17))])
    kv("OS", "macOS, Linux, Android")
    kv("Uptime", uptime(s["created_at"]))
    kv("Host", "India, Planet Earth")
    kv("Kernel", "Full-Stack Engineer · AI Agent Builder")
    kv("IDE", "VS Code, Cursor, Claude Code")
    blank()
    kv("Languages.Code", "TypeScript, JavaScript, Python, Java")
    kv("Languages.Real", "English, Hindi")
    blank()
    kv("Stack.Frontend", "Next.js, React 19, Tailwind, shadcn/ui")
    kv("Stack.Backend", "Node, Express, tRPC, Drizzle, Prisma")
    kv("Stack.AI", "AI SDK, OpenAI, Groq, AgentKit, MCP")
    kv("Stack.Cloud", "Neon, MongoDB, Vercel, Daytona, E2B")
    blank()
    kv("Now.Building", "agents that write & run code")
    kv("Now.Learning", "MCP servers, LangGraph, RAG, evals")
    kv("Contact.Email", "devvarthsinghwork@gmail.com")
    blank()
    header("GitHub Stats")

    def pair(k1, v1, k2, v2):
        left_w = 34
        d1 = max(left_w - len(k1) - 2 - len(v1) - 2, 1)
        d2 = max(COLS - left_w - 3 - len(k2) - 2 - len(v2) - 1, 1)
        L.append([("k", k1), ("p", ": "), ("d", "." * d1 + " "), ("v", v1), ("p", " | "),
                  ("k", k2), ("p", ": "), ("d", "." * d2 + " "), ("v", v2)])

    contributed = s.get("contributed")
    repo_val = f"{s['repos']}" + (f" {{Contrib: {contributed}}}" if contributed else "")
    pair("Repos", repo_val, "Stars", fmt(s["stars"]))
    pair("Commits", fmt(s.get("commits")), "Contributions", fmt(s.get("contributions")))
    a, d = s.get("loc_add"), s.get("loc_del")
    if a is not None:
        net, extra = fmt(a - d), f" ( {a:,}++, {d:,}-- )"
        dots = max(COLS - len("Lines of Code") - 2 - len(net) - len(extra) - 2, 1)
        L.append([("k", "Lines of Code"), ("p", ": "), ("d", "." * dots + " "), ("v", net),
                  ("p", " ( "), ("add", f"{a:,}++"), ("p", ", "), ("del", f"{d:,}--"), ("p", " )")])
    return L


# ----------------------------------------------------------------- svg ----

THEMES = {
    "dark": dict(bg="#0d1117", panel="#161b22", bar="#1f2630", border="#30363d", text="#c9d1d9",
                 key="#ffa657", val="#a5d6ff", dot="#484f58", head="#d2a8ff", green="#3fb950",
                 add="#3fb950", dele="#f85149", muted="#8b949e",
                 grad=("#00e5ff", "#7c4dff", "#ff4ecd"), scan="#00e5ff"),
    "light": dict(bg="#ffffff", panel="#f6f8fa", bar="#eaeef2", border="#d0d7de", text="#24292f",
                  key="#953800", val="#0a3069", dot="#afb8c1", head="#8250df", green="#1a7f37",
                  add="#1a7f37", dele="#cf222e", muted="#57606a",
                  grad=("#0969da", "#8250df", "#bf3989"), scan="#8250df"),
}

FONT = "ConsolasFallback,Consolas,'SF Mono',Menlo,'DejaVu Sans Mono','Courier New',monospace"
W = 1000
BAR = 34
AV_CX, AV_R = 195, 92  # avatar centre x and photo radius
INFO_FS, INFO_LH, INFO_X = 14, 19, 400
PAD_TOP = 28


def render(theme, lines, avatar_uri):
    t = THEMES[theme]
    n = len(lines) + 2  # prompt line + info + trailing prompt
    body_h = n * INFO_LH
    H = int(BAR + PAD_TOP + body_h + 26)
    info_y0 = BAR + PAD_TOP + 2
    cx, R = AV_CX, AV_R
    cy = BAR + PAD_TOP + body_h / 2 - 48  # leave room for the name plate below

    prefix_w = 6 * INFO_FS * 0.6  # width of the "➜ ~ $ " prompt
    cmd_x = INFO_X + prefix_w
    cmd = f"neofetch --user {USER}"
    cmd_w = len(cmd) * INFO_FS * 0.6
    type_dur = 0.9
    steps = ";".join(f"{cmd_w * i / len(cmd):.1f}" for i in range(len(cmd) + 1))
    start = type_dur + 0.25  # info lines start once the command is typed

    out = []
    a = out.append
    a(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
      f'font-family="{FONT}" role="img" aria-label="neofetch card for {USER}">')
    a(f"""<style>
.k{{fill:{t['key']}}} .v{{fill:{t['val']}}} .d{{fill:{t['dot']}}} .p{{fill:{t['text']}}}
.h{{fill:{t['head']};font-weight:700}} .g{{fill:{t['green']};font-weight:700}}
.add{{fill:{t['add']}}} .del{{fill:{t['dele']}}} .m{{fill:{t['muted']}}}
.ln{{opacity:0;animation:in .35s ease-out forwards}}
@keyframes in{{from{{opacity:0;transform:translateX(-6px)}}to{{opacity:1;transform:none}}}}
@keyframes glow{{0%,100%{{opacity:.55}}50%{{opacity:1}}}}
.edge{{animation:glow 4s ease-in-out infinite}}
.pop{{opacity:0;transform-box:fill-box;transform-origin:center;animation:pop .9s cubic-bezier(.2,.9,.3,1.3) .2s forwards}}
@keyframes pop{{from{{opacity:0;transform:scale(.6)}}to{{opacity:1;transform:none}}}}
.pulse{{transform-box:fill-box;transform-origin:center;animation:pulse 2s ease-out infinite}}
@keyframes pulse{{0%{{opacity:.8;transform:scale(1)}}100%{{opacity:0;transform:scale(3)}}}}
text{{white-space:pre}}
</style>""")
    g1, g2, g3 = t["grad"]
    a(f"""<defs>
<linearGradient id="holo" x1="0" y1="0" x2="1" y2="1">
  <stop offset="0" stop-color="{g1}" stop-opacity=".22"/><stop offset=".55" stop-color="{g2}" stop-opacity="0"/><stop offset="1" stop-color="{g3}" stop-opacity=".25"/>
</linearGradient>
<radialGradient id="aura"><stop offset=".55" stop-color="{g2}" stop-opacity=".35"/><stop offset="1" stop-color="{g2}" stop-opacity="0"/></radialGradient>
<clipPath id="face"><circle cx="{cx}" cy="{cy:.1f}" r="{R}"/></clipPath>
<filter id="blur" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="3"/></filter>
<linearGradient id="edge" x1="0" y1="0" x2="1" y2="0">
  <stop offset="0" stop-color="{g1}"/><stop offset=".5" stop-color="{g2}"/><stop offset="1" stop-color="{g3}"/>
</linearGradient>
<linearGradient id="beam" x1="0" y1="0" x2="0" y2="1">
  <stop offset="0" stop-color="{t['scan']}" stop-opacity="0"/><stop offset="1" stop-color="{t['scan']}" stop-opacity=".55"/>
</linearGradient>
<clipPath id="typed"><rect x="{cmd_x:.1f}" y="{info_y0 - 8}" width="0" height="24">
  <animate attributeName="width" values="{steps}" begin=".2s" dur="{type_dur}s" fill="freeze" calcMode="discrete"/>
</rect></clipPath>
<pattern id="crt" width="4" height="4" patternUnits="userSpaceOnUse"><rect width="4" height="1" fill="{t['text']}" opacity=".035"/></pattern>
</defs>""")

    # window
    a(f'<rect x=".5" y=".5" width="{W - 1}" height="{H - 1}" rx="12" fill="{t["panel"]}" stroke="{t["border"]}"/>')
    a(f'<rect class="edge" x="1" y="1" width="{W - 2}" height="{H - 2}" rx="12" fill="none" stroke="url(#edge)" stroke-width="1.5"/>')
    a(f'<path d="M1 {BAR}V13a12 12 0 0 1 12-12h{W - 26}a12 12 0 0 1 12 12V{BAR}z" fill="{t["bar"]}"/>')
    a(f'<line x1="1" y1="{BAR}" x2="{W - 1}" y2="{BAR}" stroke="{t["border"]}"/>')
    for i, c in enumerate(("#ff5f56", "#ffbd2e", "#27c93f")):
        a(f'<circle cx="{22 + i * 20}" cy="{BAR / 2}" r="6" fill="{c}"/>')
    a(f'<text x="{W / 2}" y="{BAR / 2 + 4.5}" text-anchor="middle" font-size="13" class="m">'
      f'devvarth@github: ~/{USER} — zsh</text>')

    # holographic avatar: photo in a glowing ring with orbiting tech tags
    spin = lambda r0, r1, dur: (f'<animateTransform attributeName="transform" type="rotate" '
                                f'from="{r0} {cx} {cy:.1f}" to="{r1} {cx} {cy:.1f}" dur="{dur}s" repeatCount="indefinite"/>')
    a('<g class="pop">')
    a(f'<circle cx="{cx}" cy="{cy:.1f}" r="{R + 70}" fill="url(#aura)">'
      f'<animate attributeName="r" values="{R + 62};{R + 74};{R + 62}" dur="5s" repeatCount="indefinite"/></circle>')
    # HUD corner brackets
    b, L = R + 66, 18
    for sx, sy in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
        x, y0 = cx + sx * b, cy + sy * b
        a(f'<path d="M{x:.1f} {y0 - sy * L:.1f}V{y0:.1f}H{x - sx * L:.1f}" fill="none" stroke="{g1}" stroke-width="2" opacity=".8"/>')
    a(f'<circle cx="{cx}" cy="{cy:.1f}" r="{R + 50}" fill="none" stroke="{t["border"]}" stroke-width="1"/>')
    a(f'<circle cx="{cx}" cy="{cy:.1f}" r="{R + 30}" fill="none" stroke="{g1}" stroke-width="1.2" '
      f'stroke-dasharray="2 7" opacity=".8">{spin(360, 0, 40)}</circle>')
    a(f'<circle cx="{cx}" cy="{cy:.1f}" r="{R + 14}" fill="none" stroke="url(#edge)" stroke-width="6" '
      f'stroke-dasharray="120 40 50 40" stroke-linecap="round" filter="url(#blur)" opacity=".7">{spin(0, 360, 9)}</circle>')
    a(f'<circle cx="{cx}" cy="{cy:.1f}" r="{R + 14}" fill="none" stroke="url(#edge)" stroke-width="3" '
      f'stroke-dasharray="120 40 50 40" stroke-linecap="round">{spin(0, 360, 9)}</circle>')
    a(f'<circle cx="{cx}" cy="{cy:.1f}" r="{R + 4}" fill="{t["bg"]}" stroke="{t["border"]}"/>')
    a(f'<image href="{avatar_uri}" x="{cx - R}" y="{cy - R:.1f}" width="{2 * R}" height="{2 * R}" '
      f'clip-path="url(#face)" preserveAspectRatio="xMidYMid slice"/>')
    a(f'<circle cx="{cx}" cy="{cy:.1f}" r="{R}" fill="url(#holo)"/>')
    a(f'<rect x="{cx - R}" y="{cy - R - 20:.1f}" width="{2 * R}" height="20" fill="url(#beam)" clip-path="url(#face)" opacity=".45">'
      f'<animate attributeName="y" values="{cy - R - 20:.1f};{cy + R:.1f}" dur="3.2s" repeatCount="indefinite"/></rect>')
    # orbiting tags
    orbit_r = R + 50
    path = f"M{cx - orbit_r} {cy:.1f}a{orbit_r} {orbit_r} 0 1 1 {2 * orbit_r} 0a{orbit_r} {orbit_r} 0 1 1 {-2 * orbit_r} 0"
    tags = ("AI", "TS", "PY", "JS", "SQL")
    for i, tag in enumerate(tags):
        col = (g1, g2, g3, g1, g2)[i]
        w = 12 + len(tag) * 7.5
        a(f'<g><rect x="{-w / 2:.1f}" y="-11" width="{w:.1f}" height="22" rx="11" fill="{t["panel"]}" stroke="{col}" stroke-width="1.5"/>'
          f'<text x="0" y="4.5" text-anchor="middle" font-size="12" font-weight="700" fill="{col}">{tag}</text>'
          f'<animateMotion path="{path}" dur="30s" begin="-{i * 30 / len(tags):.1f}s" repeatCount="indefinite"/></g>')
    # name plate
    ny = cy + R + 92
    a(f'<text x="{cx}" y="{ny:.1f}" text-anchor="middle" font-size="22" font-weight="700" letter-spacing="3" fill="url(#edge)">DEVVARTH SINGH</text>')
    a(f'<text x="{cx}" y="{ny + 22:.1f}" text-anchor="middle" font-size="12.5" class="m">full-stack · ai agents · open source</text>')
    pw, py = 196, ny + 38
    a(f'<rect x="{cx - pw / 2}" y="{py:.1f}" width="{pw}" height="24" rx="12" fill="{t["bg"]}" stroke="{t["border"]}"/>')
    a(f'<circle class="pulse" cx="{cx - pw / 2 + 16}" cy="{py + 12:.1f}" r="4" fill="{t["green"]}"/>')
    a(f'<circle cx="{cx - pw / 2 + 16}" cy="{py + 12:.1f}" r="4" fill="{t["green"]}"/>')
    a(f'<text x="{cx - pw / 2 + 28}" y="{py + 16.5:.1f}" font-size="12" class="p">online · open to collabs</text>')
    a('</g>')

    # info column
    prompt = '<tspan class="g">➜ </tspan><tspan class="h">~</tspan><tspan class="p"> $ </tspan>'

    y = info_y0 + 10
    a(f'<text x="{INFO_X}" y="{y}" font-size="{INFO_FS}" xml:space="preserve">{prompt}</text>')
    a(f'<text clip-path="url(#typed)" x="{cmd_x:.1f}" y="{y}" font-size="{INFO_FS}" class="p" '
      f'xml:space="preserve">{html.escape(cmd)}</text>')

    for i, segs in enumerate(lines):
        y += INFO_LH
        if not segs:
            continue
        spans = "".join(f'<tspan class="{c}">{html.escape(txt)}</tspan>' for c, txt in segs)
        a(f'<text class="ln" style="animation-delay:{start + i * 0.07:.2f}s" x="{INFO_X}" y="{y}" '
          f'font-size="{INFO_FS}" xml:space="preserve">{spans}</text>')

    y += INFO_LH
    end = start + len(lines) * 0.07
    a(f'<text class="ln" style="animation-delay:{end:.2f}s" x="{INFO_X}" y="{y}" font-size="{INFO_FS}" xml:space="preserve">{prompt}</text>')
    a(f'<rect class="ln" style="animation-delay:{end:.2f}s" x="{cmd_x + 1:.1f}" y="{y - 13}" width="8" height="16" fill="{t["green"]}">'
      f'<animate attributeName="fill-opacity" values="1;1;0;0" keyTimes="0;.5;.5;1" dur="1s" repeatCount="indefinite"/></rect>')

    a(f'<rect x="1" y="{BAR}" width="{W - 2}" height="{H - BAR - 1}" rx="12" fill="url(#crt)" pointer-events="none"/>')
    a("</svg>")
    return "\n".join(out)


def main():
    cache_file = ASSETS / "stats.json"
    cache = json.loads(cache_file.read_text()) if cache_file.exists() else {}
    # --offline re-renders from the cached stats without touching the API
    stats = cache if "--offline" in sys.argv else fetch_stats(cache)
    cache_file.write_text(json.dumps(stats, indent=2) + "\n")

    avatar_uri = "data:image/jpeg;base64," + base64.b64encode((ASSETS / "avatar.jpg").read_bytes()).decode()
    lines = build_lines(stats)
    for theme in THEMES:
        svg = render(theme, lines, avatar_uri)
        (ASSETS / f"neofetch-{theme}.svg").write_text(svg)
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
