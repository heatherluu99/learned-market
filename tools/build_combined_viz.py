"""Combine every built page into one file, as tabs.

Each page is a complete document with its own <style> and its own globals -
`DATA`, `esc`, `STALL_COLOR` - so merging their markup would collide on the
first shared name. They are embedded verbatim instead and loaded into an
iframe from a Blob URL when a tab is first opened, which gives each one its
own document and its own scope, exactly as if it had been opened on its own.

Embedded as raw text rather than base64: the explorer alone is 15 MB of
inlined figures, and base64 would add a third again for nothing. The only
sequence that cannot appear inside a <script> block is a literal closing
script tag, so those are escaped on the way in and restored on the way out.

Tabs materialise lazily. Building four Blobs up front would hold ~16 MB twice
over before the reader has clicked anything.

    python tools/build_combined_viz.py
"""

from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
VIZ = REPO_ROOT / "viz"
OUT = VIZ / "millbrook.html"

#: Order is the reading order, not the build order: the market comes first
#: because it is the thing the rest is about.
PAGES = [
    ("market", "Market", "phase6_market.html",
     "Phase 6 — one 22-week season, replayed. Buyers remember where they last "
     "shopped."),
    ("structure", "Entry & Exit", "phase8_market.html",
     "Phase 8 — the same market with firms entering and leaving. Watch week 11."),
    ("agent", "Agent Inspector", "agent_inspector.html",
     "Phase 9d — every decision an LLM buyer made, with its own reasoning."),
    ("experiments", "Experiments", "experiment_explorer.html",
     "Every logged run, its figure, and the commits behind it."),
]


def main() -> int:
    blocks, tabs = [], []
    for key, label, filename, blurb in PAGES:
        path = VIZ / filename
        if not path.exists():
            print(f"  skipping {filename}: not built")
            continue
        # A literal </script> would close the block holding the document.
        text = path.read_text().replace("</script>", "<\\/script>")
        blocks.append(
            f'<script type="text/plain" id="src-{key}">{text}</script>')
        tabs.append({"key": key, "label": label, "blurb": blurb,
                     "kb": round(path.stat().st_size / 1024)})
        print(f"  {label:18s} {tabs[-1]['kb']:>6,} KB")

    shell = SHELL.replace("/*__TABS__*/", json.dumps(tabs))
    OUT.write_text(shell.replace("<!--__BLOCKS__-->", "\n".join(blocks)))
    print(f"\nWrote {OUT.relative_to(REPO_ROOT)} "
          f"({OUT.stat().st_size / 1048576:.1f} MB, {len(tabs)} tabs)")
    return 0


SHELL = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Millbrook Market</title>
<style>
  :root{
    --bg:#ffffff; --panel:#f6f7f9; --border:#e3e5ea;
    --text:#1a1d24; --text-2:#5b616e; --text-3:#8b909c;
    --accent:#3B3F8C; --accent-bg:#EEF0FA; --accent-border:#C9CDEF;
    --sans:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
  }
  *{box-sizing:border-box;}
  html,body{height:100%; margin:0;}
  body{background:var(--bg); color:var(--text); font-family:var(--sans);
       font-size:14px; display:flex; flex-direction:column;}
  header{padding:14px 22px 0; border-bottom:1px solid var(--border); flex:0 0 auto;}
  header h1{margin:0; font-size:19px; font-weight:700; letter-spacing:-0.01em;}
  header p{margin:4px 0 0; font-size:13px; color:var(--text-2);}
  nav{display:flex; gap:4px; margin-top:12px;}
  nav button{appearance:none; background:none; border:0; border-bottom:2px solid transparent;
    padding:8px 14px 9px; font:inherit; font-size:13.5px; color:var(--text-2);
    cursor:pointer; border-radius:6px 6px 0 0;}
  nav button:hover{background:var(--panel); color:var(--text);}
  nav button[aria-selected="true"]{color:var(--accent); font-weight:600;
    border-bottom-color:var(--accent); background:var(--accent-bg);}
  nav button .kb{color:var(--text-3); font-size:11px; margin-left:6px;}
  .blurb{padding:9px 22px; font-size:12.5px; color:var(--text-3);
         border-bottom:1px solid var(--border); flex:0 0 auto;}
  .stage{position:relative; flex:1 1 auto; min-height:0;}
  iframe{position:absolute; inset:0; width:100%; height:100%; border:0; background:var(--bg);}
  .loading{position:absolute; inset:0; display:grid; place-items:center;
           color:var(--text-3); font-size:13px;}
</style>
</head>
<body>
<header>
  <h1>Millbrook Market</h1>
  <p>An agent-based market simulation, and what it did and did not find.</p>
  <nav id="tabs" role="tablist"></nav>
</header>
<div class="blurb" id="blurb"></div>
<div class="stage" id="stage"><div class="loading">Loading…</div></div>

<!--__BLOCKS__-->

<script>
const TABS = /*__TABS__*/;
const urls = {};          // key -> blob URL, made on first open
let current = null;

function open(key){
  if(current === key) return;
  current = key;
  const tab = TABS.find(t => t.key === key);
  document.getElementById("blurb").textContent = tab.blurb;
  for(const b of document.querySelectorAll("nav button"))
    b.setAttribute("aria-selected", String(b.dataset.key === key));
  location.hash = key;

  const stage = document.getElementById("stage");
  if(!urls[key]){
    stage.innerHTML = '<div class="loading">Loading ' + tab.label + '…</div>';
    // Deferred a frame so the loading line actually paints before the main
    // thread goes away to build a blob that can be fifteen megabytes.
    requestAnimationFrame(() => requestAnimationFrame(() => {
      // The join target is split in two on purpose: written whole, the literal
    // closing tag would end this very script block, and the page would render
    // its own source as text from that point on.
    const raw = document.getElementById("src-" + key).textContent
                          .split("<\\\\/script>").join("<" + "/script>");
      urls[key] = URL.createObjectURL(new Blob([raw], {type: "text/html"}));
      show(key);
    }));
  } else show(key);
}

function show(key){
  if(current !== key) return;   // the reader moved on while this was building
  const frame = document.createElement("iframe");
  frame.src = urls[key];
  frame.title = TABS.find(t => t.key === key).label;
  const stage = document.getElementById("stage");
  stage.innerHTML = "";
  stage.appendChild(frame);
}

document.getElementById("tabs").innerHTML = TABS.map(t =>
  `<button role="tab" data-key="${t.key}" aria-selected="false">${t.label}` +
  `<span class="kb">${t.kb.toLocaleString()} KB</span></button>`).join("");
for(const b of document.querySelectorAll("nav button"))
  b.onclick = () => open(b.dataset.key);

const wanted = location.hash.replace("#", "");
open(TABS.some(t => t.key === wanted) ? wanted : TABS[0].key);
</script>
</body>
</html>
"""


if __name__ == "__main__":
    raise SystemExit(main())
