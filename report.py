"""Builds report.html — a standalone page, no server and no external assets.

Design: "night match". The page is read as an instrument panel for a floodlit
court — chalk-line rules instead of card shadows, a scoreboard strip instead of
generic tiles, optic-ball yellow as the single sharp accent. Instrument Serif
carries the display figures; IBM Plex Sans/Mono carry the data.

Fonts are inlined from fonts.css as base64 woff2 so the page renders identically
offline and never silently falls back.
"""

import base64
import csv
import datetime as dt
import html
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))

try:
    with open(os.path.join(HERE, "fonts.css"), encoding="utf-8") as _f:
        FONT_CSS = _f.read()
except FileNotFoundError:          # still renders, just in the fallback stack
    FONT_CSS = ""

LOCAL_HEAD = ('<!doctype html>\n<meta charset="utf-8">\n'
              '<meta name="viewport" content="width=device-width,initial-scale=1">\n')

TMPL = """<title>Used Racquets — Tennis Warehouse</title>
<style>
__FONTS__

:root{
  color-scheme:light;
  --plane:#f2f3ee; --surface:#fbfcf9; --raised:#fff;
  --ink:#101613; --ink2:#4a544d; --muted:#838d84;
  --line:#dfe3d9; --rule:#c3cabb;
  --accent:#0d5c52;            /* court teal */
  --ball:#c3dc22;              /* optic yellow, used as a fill under dark ink */
  --ball-ink:#101613;
  --good:#1c7a4a; --good-soft:#e6f2ea;
  --crit:#a8402a; --crit-soft:#f8ebe7;   /* clay */
  --warn-soft:#f7f0dc; --warn-ink:#6b5410;
  --glow:transparent;
  --display:'Instrument Serif',Georgia,'Times New Roman',serif;
  --sans:'IBM Plex Sans','Helvetica Neue',Helvetica,sans-serif;
  --mono:'IBM Plex Mono',ui-monospace,Menlo,monospace;
}
@media (prefers-color-scheme:dark){:root:where(:not([data-theme="light"])){
  color-scheme:dark;
  --plane:#08110f; --surface:#0e1a17; --raised:#152420;
  --ink:#eaf2ec; --ink2:#a7b5aa; --muted:#7d8d81;
  --line:#1d2c27; --rule:#2c403a;
  --accent:#43c3a8;
  --ball:#d9f24a; --ball-ink:#0a1210;
  --good:#4cc274; --good-soft:#0f2a1b;
  --crit:#e0705a; --crit-soft:#2b1512;
  --warn-soft:#2a2412; --warn-ink:#e3c76a;
  --glow:rgba(217,242,74,.05);
}}
:root[data-theme="dark"]{
  color-scheme:dark;
  --plane:#08110f; --surface:#0e1a17; --raised:#152420;
  --ink:#eaf2ec; --ink2:#a7b5aa; --muted:#7d8d81;
  --line:#1d2c27; --rule:#2c403a;
  --accent:#43c3a8;
  --ball:#d9f24a; --ball-ink:#0a1210;
  --good:#4cc274; --good-soft:#0f2a1b;
  --crit:#e0705a; --crit-soft:#2b1512;
  --warn-soft:#2a2412; --warn-ink:#e3c76a;
  --glow:rgba(217,242,74,.05);
}

*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;padding:0;background:var(--plane);color:var(--ink);
 font:400 15px/1.55 var(--sans);-webkit-font-smoothing:antialiased;
 background-image:radial-gradient(120% 60% at 50% -10%,var(--glow),transparent 70%);
 background-repeat:no-repeat}
.wrap{max-width:1280px;margin:0 auto;padding:44px 26px 80px}

/* ---------- header: eyebrow, display title, court baseline ---------- */
.eyebrow{display:flex;align-items:center;gap:8px;font:600 11px/1 var(--mono);
 letter-spacing:.16em;text-transform:uppercase;color:var(--muted);margin-bottom:14px}
.eyebrow .ball{width:8px;height:8px;border-radius:50%;background:var(--ball);
 box-shadow:0 0 0 3px color-mix(in srgb,var(--ball) 22%,transparent)}
h1{font:400 clamp(38px,6vw,58px)/1 var(--display);letter-spacing:-.01em;
 margin:0 0 12px;text-wrap:balance}
.meta{font:400 13px/1.6 var(--mono);color:var(--ink2);letter-spacing:-.01em}
.meta b{color:var(--ink);font-weight:600}
/* the court baseline: a heavy line shadowed by a hairline */
.baseline{height:0;border-top:2px solid var(--ink);box-shadow:0 3px 0 -2px var(--line);
 margin:22px 0 0}

/* ---------- scoreboard strip ---------- */
.board{display:grid;grid-template-columns:repeat(4,1fr);
 border-bottom:1px solid var(--line);margin-bottom:22px}
.cell{padding:17px 22px 17px 0;border-left:1px solid var(--line);padding-left:22px;
 animation:rise .5s cubic-bezier(.2,.7,.3,1) backwards}
.cell:first-child{border-left:0;padding-left:0}
.cell:nth-child(1){animation-delay:.02s} .cell:nth-child(2){animation-delay:.08s}
.cell:nth-child(3){animation-delay:.14s} .cell:nth-child(4){animation-delay:.2s}
.cell .lab{font:500 10.5px/1 var(--mono);letter-spacing:.13em;text-transform:uppercase;
 color:var(--muted);margin-bottom:11px}
.cell .val{font:400 40px/1 var(--display);letter-spacing:-.015em;display:block}
.cell .sub{font:400 12px/1.4 var(--sans);color:var(--muted);margin-top:7px;
 overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.cell.win .val{color:var(--good)}
.cell.alert .val{color:var(--crit)}
@keyframes rise{from{opacity:0;transform:translateY(9px)}to{opacity:1;transform:none}}

/* ---------- control deck ----------
   Two tiers: what you're looking at (views) above how you narrow it (refine). */
.deck{position:sticky;top:0;z-index:5;background:var(--plane);
 padding:10px 0 12px;margin-bottom:2px}
.deck::after{content:'';position:absolute;left:0;right:0;bottom:0;height:1px;
 background:var(--line)}
.deck-top{display:flex;flex-wrap:wrap;gap:12px;align-items:center;
 justify-content:space-between;margin-bottom:10px}
.deck-refine{display:flex;flex-wrap:wrap;gap:9px;align-items:center;min-width:0}
.deck-refine>*{min-width:0}
.deck-actions{display:flex;gap:14px;align-items:center;flex-wrap:wrap}

/* ---------- brand pills: one click, multi-select ---------- */
.brands{display:flex;flex-wrap:wrap;gap:6px;margin-top:9px}
.bpill{font:500 11.5px/1 var(--mono);letter-spacing:.08em;text-transform:uppercase;
 display:inline-flex;align-items:center;gap:7px;padding:8px 12px;cursor:pointer;
 border:1px solid var(--line);border-radius:20px;background:var(--surface);
 color:var(--ink2);transition:background .14s,color .14s,border-color .14s}
.bpill:hover{color:var(--ink);border-color:var(--rule)}
.bpill span{font-size:10px;color:var(--muted);font-variant-numeric:tabular-nums}
.bpill[aria-pressed="true"]{background:var(--ink);color:var(--plane);
 border-color:var(--ink)}
.bpill[aria-pressed="true"] span{color:var(--ball)}

/* ---------- saved searches: the user's own shortlist ---------- */
.saved{display:flex;flex-wrap:wrap;gap:6px;margin-top:9px;align-items:center}
.saved:empty{display:none}
.saved .slab{font:500 10px/1 var(--mono);letter-spacing:.13em;text-transform:uppercase;
 color:var(--muted);margin-right:4px}
.spill{display:inline-flex;align-items:center;gap:8px;cursor:pointer;
 font:500 12px/1 var(--sans);padding:7px 9px 7px 12px;border-radius:20px;
 border:1px solid var(--accent);background:none;color:var(--accent);
 transition:background .14s,color .14s}
.spill:hover{background:color-mix(in srgb,var(--accent) 10%,transparent)}
.spill[aria-pressed="true"]{background:var(--accent);color:var(--plane)}
.spill .n{font:600 11px/1 var(--mono);padding:2px 5px;border-radius:10px;
 background:color-mix(in srgb,var(--accent) 15%,transparent)}
.spill[aria-pressed="true"] .n{background:rgba(255,255,255,.22)}
.spill.none{border-color:var(--line);color:var(--muted)}
.spill.none .n{background:none;color:var(--muted)}
.spill.none:hover{background:color-mix(in srgb,var(--ink) 4%,transparent)}
.spill .x{font-size:12px;opacity:.6;padding:0 1px}
.spill .x:hover{opacity:1;color:var(--crit)}
.spill[aria-pressed="true"] .x:hover{color:var(--ball)}
.savebtn{font:500 11px/1 var(--mono);letter-spacing:.07em;text-transform:uppercase;
 background:none;border:1px dashed var(--accent);color:var(--accent);cursor:pointer;
 padding:6px 11px;border-radius:20px}
.savebtn:hover{background:color-mix(in srgb,var(--accent) 10%,transparent)}

/* model lines -- lighter than the brand pills, one tier down in the hierarchy */
.families{display:flex;flex-wrap:wrap;gap:4px;margin-top:6px;align-items:center}
.families:empty{display:none}
.families .flab{font:500 10px/1 var(--mono);letter-spacing:.13em;
 text-transform:uppercase;color:var(--muted);margin-right:4px}
.fpill{font:400 12px/1 var(--sans);padding:6px 11px;cursor:pointer;
 border:1px solid transparent;border-radius:20px;background:none;color:var(--ink2);
 transition:border-color .14s,color .14s,background .14s}
.fpill:hover{color:var(--ink);background:color-mix(in srgb,var(--ink) 5%,transparent)}
.fpill[aria-pressed="true"]{background:var(--ball);color:var(--ball-ink);
 border-color:var(--ball);font-weight:600}

/* active filters, shown only when something is on */
.chips[hidden]{display:none}
.chips{display:flex;flex-wrap:wrap;gap:7px;align-items:center;margin-top:10px}
.chip-f{display:inline-flex;align-items:center;gap:7px;font:500 11px/1 var(--mono);
 letter-spacing:.07em;text-transform:uppercase;padding:6px 8px 6px 11px;
 border-radius:20px;background:var(--surface);border:1px solid var(--rule);
 color:var(--ink2);animation:chipin .2s cubic-bezier(.2,.7,.3,1)}
@keyframes chipin{from{opacity:0;transform:scale(.9)}to{opacity:1;transform:none}}
.chip-f b{color:var(--ink);font-weight:600}
.chip-f button{border:0;background:none;cursor:pointer;color:var(--muted);
 font-size:13px;line-height:1;padding:0 2px}
.chip-f button:hover{color:var(--crit)}
.chips .clearall{font:500 11px/1 var(--mono);letter-spacing:.07em;
 text-transform:uppercase;background:none;border:0;cursor:pointer;
 color:var(--muted);text-decoration:underline;text-underline-offset:3px;padding:6px 4px}
.chips .clearall:hover{color:var(--ink)}

.bar{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin-bottom:6px}
.tabs{display:inline-flex;gap:2px;margin-right:6px}
.tabs button{font:500 13px/1 var(--mono);letter-spacing:.02em;border:0;background:none;
 color:var(--muted);padding:9px 13px;cursor:pointer;border-bottom:2px solid transparent;
 transition:color .15s,border-color .15s;text-transform:uppercase;font-size:11.5px;
 letter-spacing:.1em}
.tabs button:hover{color:var(--ink)}
.tabs button[aria-pressed="true"]{color:var(--ink);border-bottom-color:var(--ball)}
input,select{font:400 13.5px var(--sans);padding:9px 12px;border:1px solid var(--line);
 border-radius:7px;background:var(--surface);color:var(--ink)}
input::placeholder{color:var(--muted)}
input:focus-visible,select:focus-visible,button:focus-visible,a:focus-visible{
 outline:2px solid var(--accent);outline-offset:2px}
.qwrap{position:relative;display:flex;flex:1 1 200px;min-width:180px}
#q{width:100%}
.kbd,kbd{font:500 10.5px var(--mono);color:var(--muted);border:1px solid var(--line);
 border-radius:4px;padding:2px 5px;background:var(--plane)}
.kbd{position:absolute;right:10px;top:50%;transform:translateY(-50%);pointer-events:none}
.btn{font:600 12px/1 var(--mono);letter-spacing:.08em;text-transform:uppercase;
 padding:11px 17px;border-radius:7px;cursor:pointer;border:1px solid transparent;
 background:var(--ball);color:var(--ball-ink);text-decoration:none;
 display:inline-flex;align-items:center;gap:7px;white-space:nowrap;
 transition:transform .12s,filter .12s}
.btn:hover{filter:brightness(1.06);transform:translateY(-1px)}
.btn[aria-busy="true"]{opacity:.55;pointer-events:none}
.btn.ghost{background:none;color:var(--ink);border-color:var(--rule)}

.count{font:400 11.5px var(--mono);letter-spacing:.08em;text-transform:uppercase;
 color:var(--muted);margin:16px 0 9px}

/* ---------- table ---------- */
.scroll{overflow-x:auto;border-top:2px solid var(--ink)}
table{border-collapse:separate;border-spacing:0;width:100%;min-width:840px}
th,td{text-align:left;padding:13px 16px;white-space:nowrap;
 border-bottom:1px solid var(--line)}
th{font:500 10.5px/1 var(--mono);letter-spacing:.13em;text-transform:uppercase;
 color:var(--muted);cursor:pointer;user-select:none;position:sticky;top:0;z-index:3;
 background:var(--plane);padding-top:14px;padding-bottom:14px;
 border-bottom:1px solid var(--rule);transition:color .15s}
th:hover{color:var(--ink)}
th .ar{opacity:0;margin-left:5px;font-size:8px;vertical-align:middle}
th[data-on]{color:var(--ink)} th[data-on] .ar{opacity:1;color:var(--ball)}
tbody tr{animation:fade .4s ease backwards}
@keyframes fade{from{opacity:0}to{opacity:1}}
tbody tr:hover td{background:color-mix(in srgb,var(--ink) 3%,transparent)}
td.r{text-align:right}
.num{font:600 14.5px var(--mono);font-variant-numeric:tabular-nums;letter-spacing:-.02em}
.was{font:400 12.5px var(--mono);color:var(--muted);font-variant-numeric:tabular-nums}
.off{font:600 13px var(--mono);color:var(--good);font-variant-numeric:tabular-nums}

/* first column is the anchor: pinned, with a service-line accent on hover */
.name{white-space:normal;min-width:250px;max-width:340px;position:sticky;left:0;z-index:2;
 background:var(--plane);box-shadow:1px 0 0 var(--line)}
.nw{display:flex;align-items:center;gap:13px}
/* off-white rather than pure white: on the dark ground a column of #fff plates
   glares, and the racquets read just as well against it */
.pic{width:30px;height:64px;object-fit:contain;flex:none;border-radius:4px;
 background:#f6f7f3;border:1px solid var(--line);padding:2px;
 transition:transform .18s cubic-bezier(.2,.7,.3,1)}
.empty-pic{background:var(--surface)}
tbody tr:hover .pic{transform:scale(1.09)}
.name a{font:600 14.5px/1.35 var(--sans);color:var(--ink);text-decoration:none;
 display:block;position:relative}
.name a:hover{color:var(--accent)}
.name .brand{display:block;font:400 10.5px/1 var(--mono);letter-spacing:.12em;
 text-transform:uppercase;color:var(--muted);margin-top:6px}
tbody tr:hover .name{background:color-mix(in srgb,var(--ink) 3%,var(--plane))}
.name::before{content:'';position:absolute;left:0;top:0;bottom:0;width:2px;
 background:var(--ball);transform:scaleY(0);transform-origin:center;transition:transform .18s}
tbody tr:hover .name::before{transform:scaleY(1)}
tr.trap td{background:var(--crit-soft)}
tr.trap .name{background:var(--crit-soft)}
tr.trap:hover td,tr.trap:hover .name{background:color-mix(in srgb,var(--crit) 13%,transparent)}
tr.trap .name::before{background:var(--crit)}

/* square chips read as instrument markings, not soft UI pills */
.chip{display:inline-block;min-width:22px;text-align:center;font:600 11px/1 var(--mono);
 padding:5px 6px;border:1px solid var(--rule);border-radius:3px;color:var(--ink2)}
.tag{display:inline-flex;align-items:center;gap:5px;font:600 10.5px/1 var(--mono);
 letter-spacing:.08em;text-transform:uppercase;padding:5px 8px;border-radius:3px}
.t-low{background:var(--good-soft);color:var(--good)}
.t-below{background:var(--good-soft);color:var(--good)}
.t-new{background:color-mix(in srgb,var(--ball) 20%,transparent);color:var(--ink)}
.t-trap{background:var(--crit-soft);color:var(--crit)}
.dash,.quiet{font:400 11px var(--mono);letter-spacing:.06em;text-transform:uppercase;
 color:var(--muted)}
.med{font:400 11px var(--mono);color:var(--muted);font-variant-numeric:tabular-nums}
.grip{font:400 12.5px var(--mono);color:var(--ink2);font-variant-numeric:tabular-nums}

/* ---------- sparkline ---------- */
.spark{display:block;overflow:visible}
.spark path.ln{fill:none;stroke:var(--muted);stroke-width:1.75;stroke-linecap:round;
 stroke-linejoin:round}
.spark path.ar{fill:var(--accent);opacity:.10;stroke:none}
.spark circle{fill:var(--ball);stroke:var(--plane);stroke-width:2}
tr.trap .spark circle{fill:var(--crit)}
body.nospark .col-spark{display:none}
body.nosignal .col-signal{display:none}

/* ---------- merged price cell ---------- */
.pricecell{padding-top:11px;padding-bottom:11px}
.pricecell .p{display:block;font:600 17px/1.15 var(--mono);letter-spacing:-.02em;
 font-variant-numeric:tabular-nums}
.pricecell .psub{display:block;margin-top:3px;font:400 11.5px/1 var(--mono);
 color:var(--muted);font-variant-numeric:tabular-nums;white-space:nowrap}
.pricecell .psub s{text-decoration-thickness:1px}
.pricecell .psub .cut{color:var(--good);font-weight:600}
tr.trap .pricecell .psub{color:var(--crit)}

/* ---------- tooltip, notices, empty ---------- */
#tip{position:fixed;z-index:60;pointer-events:none;opacity:0;transition:opacity .12s;
 background:var(--raised);color:var(--ink);border:1px solid var(--rule);border-radius:8px;
 padding:10px 12px;font:400 12px/1.6 var(--mono);max-width:250px;
 box-shadow:0 10px 30px rgba(0,0,0,.22)}
#tip b{font-weight:600;font-variant-numeric:tabular-nums}
/* ---------- spec filter bar ---------- */
.specbtn{font:500 11.5px/1 var(--mono);letter-spacing:.1em;text-transform:uppercase;
 padding:10px 14px;border:1px solid var(--rule);border-radius:7px;cursor:pointer;
 background:var(--surface);color:var(--ink2);display:inline-flex;gap:7px;align-items:center}
.specbtn:hover{color:var(--ink)}
.specbtn[aria-expanded="true"]{background:var(--ink);color:var(--plane);border-color:var(--ink)}
#specn:not(:empty){background:var(--ball);color:var(--ball-ink);border-radius:20px;
 padding:1px 7px;font-size:10.5px}
.specbar[hidden]{display:none}
.specbar{display:flex;flex-wrap:wrap;gap:18px 26px;align-items:flex-end;
 padding:18px 20px;margin-top:12px;background:var(--surface);
 border:1px solid var(--line);border-radius:11px}
.sf{display:flex;flex-direction:column;gap:6px}
.sf label{font:500 10px/1 var(--mono);letter-spacing:.13em;text-transform:uppercase;
 color:var(--muted)}
.sf input{width:78px}
.sf:has(select) select{min-width:172px}
.sf>input{display:inline-block}
.sf:has(input+input){flex-direction:row;align-items:center;flex-wrap:wrap;gap:6px}
.sf:has(input+input) label{width:100%;margin-bottom:2px}
.btn.sm{padding:8px 13px;font-size:11px;align-self:center}

/* ---------- rating + expandable spec drawer ---------- */
.rate{margin-left:9px;color:var(--muted);letter-spacing:.06em}
.rate b{color:var(--ink2);font-weight:600}
tbody tr.row{cursor:pointer}
/* Absolutely placed so it costs no layout width and never indents the name. */
.name{position:relative}
.caret{position:absolute;right:9px;top:50%;transform:translateY(-50%);
 color:var(--muted);font-size:9px;opacity:0;transition:opacity .15s,transform .16s;
 pointer-events:none}
tr.row:hover .caret{opacity:.75}
tr.row.open .caret{opacity:1;color:var(--ball);transform:translateY(-50%) rotate(90deg)}
tr.det{display:none}
tr.det.open{display:table-row}
tr.det > td{background:color-mix(in srgb,var(--ink) 3%,transparent);
 padding:18px 22px 22px;border-bottom:1px solid var(--line)}
.specs{display:grid;grid-template-columns:repeat(auto-fit,minmax(168px,1fr));
 gap:14px 26px;max-width:1000px;white-space:normal}
.specs div{border-left:2px solid var(--line);padding-left:11px}
.specs dt{font:500 10px/1 var(--mono);letter-spacing:.13em;text-transform:uppercase;
 color:var(--muted);margin-bottom:5px}
.specs dd{margin:0;font:400 13.5px/1.4 var(--sans);color:var(--ink)}
.nospecs{font:400 13px var(--sans);color:var(--muted)}

/* ---------- thumbnail button + lightbox ---------- */
.picbtn{padding:0;border:0;background:none;cursor:zoom-in;display:block;line-height:0}
.units{display:inline-block;margin-left:9px;padding:2px 6px;border-radius:3px;
 background:color-mix(in srgb,var(--ball) 22%,transparent);color:var(--ink);
 letter-spacing:.08em}
.tog{display:inline-flex;align-items:center;gap:7px;font:400 12px var(--mono);
 letter-spacing:.05em;text-transform:uppercase;color:var(--ink2);cursor:pointer;
 white-space:nowrap}
.tog input{accent-color:var(--accent);width:15px;height:15px;padding:0}
/* an ID selector outranks the UA's [hidden]{display:none}, so restate it */
#lb[hidden]{display:none}
#lb{position:fixed;inset:0;z-index:100;display:flex;align-items:center;
 justify-content:center;padding:44px 20px;
 background:color-mix(in srgb,var(--plane) 88%,#000);
 backdrop-filter:blur(7px);animation:lbin .18s ease}
@keyframes lbin{from{opacity:0}to{opacity:1}}
#lb figure{margin:0;display:flex;flex-direction:column;align-items:center;gap:18px;
 max-height:100%}
#lbimg{max-height:76vh;max-width:min(420px,88vw);object-fit:contain;background:#f6f7f3;
 border:1px solid var(--line);border-radius:10px;padding:14px;
 box-shadow:0 24px 70px rgba(0,0,0,.28)}
#lbcap{font:400 15px/1.45 var(--sans);color:var(--ink);text-align:center;max-width:32ch}
#lbcap span{display:block;font:400 11.5px var(--mono);letter-spacing:.12em;
 text-transform:uppercase;color:var(--muted);margin-top:7px}
#lbclose{position:absolute;top:18px;right:20px;width:40px;height:40px;border-radius:50%;
 border:1px solid var(--rule);background:var(--surface);color:var(--ink);
 font-size:15px;cursor:pointer;line-height:1}
#lbclose:hover{background:var(--raised)}
.empty{padding:64px 20px;text-align:center;border-bottom:1px solid var(--line)}
.empty b{display:block;font:400 26px/1.2 var(--display);color:var(--ink);margin-bottom:7px}
.empty span{font:400 13px var(--sans);color:var(--muted)}
.stale,.howto{border-radius:9px;padding:14px 17px;margin-bottom:20px;
 font:400 13.5px/1.65 var(--sans)}
.stale{background:var(--warn-soft);color:var(--warn-ink);
 border:1px solid color-mix(in srgb,var(--warn-ink) 24%,transparent)}
.howto{background:var(--surface);border:1px solid var(--line)}
.howto b{font-weight:600}
.howto ol{margin:9px 0 11px 19px;padding:0}
.howto li{margin-bottom:5px}
.howto .row{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px}
.notes{margin-top:30px;padding-top:22px;border-top:1px solid var(--line);
 font:400 12.5px/1.75 var(--sans);color:var(--ink2);max-width:74ch}
.notes p{margin:0 0 9px}
.notes b{color:var(--ink);font-weight:600}
code{font:400 11.5px var(--mono);background:color-mix(in srgb,var(--ink) 7%,transparent);
 padding:2px 5px;border-radius:4px}

@media(max-width:900px){
  .wrap{padding:30px 16px 60px}
  .board{grid-template-columns:1fr 1fr}
  .cell{padding:16px 16px 16px 18px}
  .cell:nth-child(3),.cell:nth-child(4){border-top:1px solid var(--line)}
  .cell:nth-child(3){border-left:0;padding-left:0}
  .cell .val{font-size:32px}
  .col-qty{display:none}
  table{min-width:640px}
  .name{min-width:190px;max-width:230px}
  .nw{gap:9px} .pic{width:24px;height:52px}
}
@media(max-width:720px){
  /* The deck is too tall to pin on a phone -- it would cover the listings. */
  .deck{position:static}
}
@media(max-width:560px){
  .tabs{width:100%;justify-content:space-between;margin-right:0}
  .tabs button{padding:9px 6px;font-size:10.5px;letter-spacing:.06em}
  #refresh{margin-left:0;width:100%;justify-content:center}
}
@media (prefers-reduced-motion:reduce){
  *{animation:none!important;transition:none!important}
}
</style>

<div class="wrap">
  <div class="eyebrow"><span class="ball"></span>Tennis Warehouse · used market</div>
  <h1>Used Racquets</h1>
  <div class="meta">__SUB__</div>
  <div class="baseline"></div>

  <div class="board">__TILES__</div>
  <div id="staleness"></div>

  <div class="deck">
    <div class="deck-top">
      <div class="tabs" role="group" aria-label="Quick views">
        <button data-view="all" aria-pressed="true">All</button>
        <button data-view="deals">Deals</button>
        <button data-view="cheap">Under $150</button>
        <button data-view="trap">Avoid · __NTRAP__</button>
      </div>
      <div class="deck-actions">
        <label class="tog"><input type="checkbox" id="group" checked> Group identical</label>
        __REFRESHBTN__
      </div>
    </div>

    <div class="deck-refine">
      <div class="qwrap">
        <input type="search" id="q" placeholder="Search racquet…" aria-label="Search racquet name">
        <span class="kbd">/</span>
      </div>
      <button class="specbtn" id="specbtn" aria-expanded="false">Filter<span id="specn"></span></button>
    </div>

    <div class="saved" id="saved" role="group" aria-label="Saved searches"></div>
    <div class="brands" id="brands" role="group" aria-label="Filter by brand"></div>
    <div class="families" id="families" role="group" aria-label="Filter by model line"></div>

  <div class="specbar" id="specbar" hidden>
    <div class="sf"><label for="sortby">Sort by</label>
      <select id="sortby">
        <option value="discount_pct">Biggest discount</option>
        <option value="used_price">Cheapest first</option>
        <option value="rating">Best reviewed</option>
        <option value="swingweight">Swingweight</option>
        <option value="stiffness">Stiffness (flex)</option>
        <option value="head_in2">Head size</option>
        <option value="weight_oz">Strung weight</option>
        <option value="balance_pts">Balance</option>
      </select></div>
    <div class="sf"><label for="grade">Condition</label>
      <select id="grade"><option value="">Any grade</option>__GRADES__</select></div>
    <div class="sf"><label for="grip">Grip size</label>
      <select id="grip"><option value="">Any grip</option>__GRIPS__</select></div>
    <div class="sf"><label>Head in²</label>
      <input type="number" id="head_min" placeholder="min" step="1">
      <input type="number" id="head_max" placeholder="max" step="1"></div>
    <div class="sf"><label>Weight oz</label>
      <input type="number" id="wt_min" placeholder="min" step="0.1">
      <input type="number" id="wt_max" placeholder="max" step="0.1"></div>
    <div class="sf"><label>Swingweight</label>
      <input type="number" id="sw_min" placeholder="min" step="1">
      <input type="number" id="sw_max" placeholder="max" step="1"></div>
    <div class="sf"><label>Stiffness</label>
      <input type="number" id="st_min" placeholder="min" step="1">
      <input type="number" id="st_max" placeholder="max" step="1"></div>
    </div>

    <div class="chips" id="chips" hidden></div>
  </div>

  <div class="count" id="count"></div>

  <div class="scroll">
    <table>
      <thead><tr>
        <th data-k="racquet">Racquet<span class="ar">▼</span></th>
        <th class="r" data-k="used_price">Price<span class="ar">▼</span></th>
        <th data-k="grade">Grade<span class="ar">▼</span></th>
        <th data-k="grip">Grip<span class="ar">▼</span></th>
        <th class="col-signal" data-k="rank">Signal<span class="ar">▼</span></th>
        <th class="col-spark">Trend</th>
        <th class="col-qty r" data-k="in_stock">Qty<span class="ar">▼</span></th>
      </tr></thead>
      <tbody id="tb"></tbody>
    </table>
  </div>
  <div class="empty" id="empty" hidden><b>Nothing here</b>
    <span>No racquet matches every filter you've set.</span>
    <button class="btn ghost sm" id="clearall">Clear all filters</button></div>

  <div class="notes">__NOTES__</div>
</div>
<div id="tip" role="tooltip"></div>
<div id="lb" hidden>
  <button id="lbclose" aria-label="Close">✕</button>
  <figure>
    <img id="lbimg" alt="">
    <figcaption id="lbcap"></figcaption>
  </figure>
</div>

<script id="data" type="application/json">__DATA__</script>
<script id="series" type="application/json">__SERIES__</script>
<script id="thumbs" type="application/json">__THUMBS__</script>
<script>
const ROWS = JSON.parse(document.getElementById('data').textContent);
const SERIES = JSON.parse(document.getElementById('series').textContent);
const THUMBS = JSON.parse(document.getElementById('thumbs').textContent);
const WEB = __WEB__;
if (!Object.keys(SERIES).length) document.body.classList.add('nospark');

const RANK = {'LOWEST EVER':0,'BELOW USUAL':1,'':3,'typical':3,'high':4};
ROWS.forEach(r => {
  r.rank = r.new_cheaper ? 9 : (r.verdict ? RANK[r.verdict] : (r.is_new ? 2 : 3));
  r.key = r.racquet + '||' + r.grade;
  Object.assign(r, r.nspec || {});
});

const $ = id => document.getElementById(id);
// "Head Speed MP 2026 Racquet" -> "Head Speed MP 2026". Display only: the raw
// name is what history.csv and the grouping key are built from.
// Word-split rather than a word-boundary regex: this template is a plain
// Python string, so a backslash-b would arrive here as a backspace character.
const tidy = s => s.split(/\s+/).filter(w => !/^racquets?$/i.test(w)).join(' ');
let sortKey = 'discount_pct', sortDir = -1, view = 'all';
// Balance runs head-light (negative) to head-heavy, so ascending reads naturally.
const ASC = new Set(['used_price','stiffness','balance_pts']);

/* 12-point price trend: faint area, thin line, endpoint in the accent */
function spark(key){
  const pts = (SERIES[key] || []).slice(-12);
  if (pts.length < 2) return '<span class="dash">—</span>';
  const W = 78, H = 24, P = 3;
  const vals = pts.map(p => p[1]);
  const lo = Math.min(...vals), hi = Math.max(...vals), span = (hi - lo) || 1;
  const xy = pts.map((p,i) => [
    P + i * (W - 2*P) / (pts.length - 1),
    P + (H - 2*P) * (1 - (p[1] - lo) / span)
  ]);
  const d = xy.map((p,i) => (i?'L':'M') + p[0].toFixed(1) + ' ' + p[1].toFixed(1)).join(' ');
  const area = `${d} L${xy[xy.length-1][0].toFixed(1)} ${H} L${xy[0][0].toFixed(1)} ${H} Z`;
  const last = xy[xy.length-1];
  return `<svg class="spark" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}"
    data-key="${key.replace(/"/g,'&quot;')}" role="img"
    aria-label="Price trend over ${pts.length} days, low $${lo}, high $${hi}">
    <path class="ar" d="${area}"/><path class="ln" d="${d}"/>
    <circle cx="${last[0].toFixed(1)}" cy="${last[1].toFixed(1)}" r="3.5"/></svg>`;
}

/* Product shots are white-background JPEGs, so they sit on their own light
   plate rather than floating on the dark ground. */
function thumb(r){
  const src = THUMBS[r.code];
  if (!src) return '<div class="pic empty-pic" aria-hidden="true"></div>';
  return `<button class="picbtn" data-code="${r.code}" data-name="${r.racquet.replace(/"/g,'&quot;')}"
    aria-label="Enlarge ${r.racquet.replace(/"/g,'&quot;')}"><img class="pic" src="${src}"
    alt="" loading="lazy" decoding="async"></button>`;
}

const SPEC_LABELS = {head:'Head size', weight:'Strung weight', balance:'Balance',
  swingweight:'Swingweight', stiffness:'Stiffness', beam:'Beam width',
  length:'Length', composition:'Composition', power:'Power level',
  stroke:'Stroke style', swing:'Swing speed', griptype:'Grip', tension:'Tension'};

function details(r){
  const sp = r.specs || {};
  const cells = Object.keys(SPEC_LABELS).filter(k => sp[k])
    .map(k => `<div><dt>${SPEC_LABELS[k]}</dt><dd>${sp[k]}</dd></div>`);
  if (r.list_price && r.new_price && r.list_price > r.new_price)
    cells.unshift(`<div><dt>List price</dt><dd>$${r.list_price.toFixed(0)} ` +
      `<span style="color:var(--muted)">(new is $${r.new_price.toFixed(0)} today)</span></dd></div>`);
  if (r.rating)
    cells.unshift(`<div><dt>Owner rating</dt><dd>${r.rating} out of 5 ` +
      `<span style="color:var(--muted)">from ${r.reviews} reviews</span></dd></div>`);
  return cells.length
    ? `<dl class="specs">${cells.join('')}</dl>`
    : '<div class="nospecs">No specifications listed for this racquet.</div>';
}

const brandSel = new Set();

function buildBrands(){
  const counts = {};
  ROWS.forEach(r => counts[r.brand] = (counts[r.brand] || 0) + 1);
  $('brands').innerHTML =
    `<button class="bpill" data-brand="" aria-pressed="true">All<span>${ROWS.length}</span></button>` +
    Object.keys(counts).sort().map(n =>
      `<button class="bpill" data-brand="${n}" aria-pressed="false">${n}<span>${counts[n]}</span></button>`
    ).join('');
}

function syncBrands(){
  document.querySelectorAll('.bpill').forEach(b => b.setAttribute('aria-pressed',
    String(b.dataset.brand ? brandSel.has(b.dataset.brand) : brandSel.size === 0)));
}

$('brands').addEventListener('click', e => {
  const b = e.target.closest('.bpill');
  if (!b) return;
  if (!b.dataset.brand) brandSel.clear();            // the "All" pill
  else if (brandSel.has(b.dataset.brand)) brandSel.delete(b.dataset.brand);
  else brandSel.add(b.dataset.brand);
  syncBrands();
  render();
});

/* ---------- saved searches ----------
   A saved entry captures the whole filter state, not just the text, so
   "Blade 100L, grade A, 4 3/8" comes back exactly as you left it. Stored in
   localStorage, keyed to this file, so it survives every rebuild of the page. */
const SAVED_KEY = 'tw_saved_searches';
let canStore = true;
try { localStorage.setItem('tw_probe','1'); localStorage.removeItem('tw_probe'); }
catch (e) { canStore = false; }

function loadSaved(){
  if (!canStore) return [];
  try { return JSON.parse(localStorage.getItem(SAVED_KEY) || '[]'); }
  catch (e) { return []; }
}
function storeSaved(list){
  if (!canStore) return;
  try { localStorage.setItem(SAVED_KEY, JSON.stringify(list)); } catch (e) {}
}

function currentState(){
  const specs = {};
  SPEC_IDS.forEach(id => { if ($(id).value) specs[id] = $(id).value; });
  return {
    q: $('q').value.trim(),
    brands: [...brandSel].sort(),
    grade: $('grade').value,
    grip: $('grip').value,
    specs,
  };
}

function stateLabel(st){
  if (st.q) return st.q;
  const bits = st.brands.slice(0, 2).concat(
    st.grade ? [st.grade.replace('Grade ', 'Gr ')] : [],
    st.grip ? [st.grip] : []);
  return bits.join(' · ') || 'Filter set';
}

function sameState(a, b){
  return JSON.stringify(a) === JSON.stringify(b);
}

function applyState(st){
  $('q').value = st.q || '';
  $('grade').value = st.grade || '';
  $('grip').value = st.grip || '';
  SPEC_IDS.forEach(id => $(id).value = (st.specs && st.specs[id]) || '');
  brandSel.clear();
  (st.brands || []).forEach(b => brandSel.add(b));
  syncBrands();
  render();
}

function countMatches(st){
  const num = v => { const n = parseFloat(v); return isNaN(n) ? null : n; };
  const sp = st.specs || {};
  const inBand = (val, lo, hi) =>
    (lo == null && hi == null) ? true
    : (val == null ? false : (lo == null || val >= lo) && (hi == null || val <= hi));
  const q = (st.q || '').toLowerCase();
  return ROWS.filter(r =>
    (!q || r.racquet.toLowerCase().includes(q)) &&
    (!st.brands || !st.brands.length || st.brands.includes(r.brand)) &&
    (!st.grade || r.grade === st.grade) &&
    (!st.grip || r.grip === st.grip) &&
    inBand(r.head_in2, num(sp.head_min), num(sp.head_max)) &&
    inBand(r.weight_oz, num(sp.wt_min), num(sp.wt_max)) &&
    inBand(r.swingweight, num(sp.sw_min), num(sp.sw_max)) &&
    inBand(r.stiffness, num(sp.st_min), num(sp.st_max))
  ).length;
}

function buildSaved(){
  const list = loadSaved();
  const now = currentState();
  $('saved').innerHTML = list.length
    ? '<span class="slab">Saved</span>' + list.map((st, i) =>
        ((n) => `<span class="spill${n ? '' : ' none'}" role="button" tabindex="0"
           data-i="${i}" aria-pressed="${sameState(st, now)}"
           title="${n ? n + ' listing' + (n > 1 ? 's' : '') + ' right now' : 'Nothing in stock yet'}"
           >${stateLabel(st)}<span class="n">${n || '—'}</span>` +
        `<span class="x" data-del="${i}" role="button" aria-label="Remove">✕</span></span>`
        )(countMatches(st))
      ).join('')
    : '';
}

$('saved').addEventListener('click', e => {
  const del = e.target.closest('[data-del]');
  if (del) {
    const list = loadSaved();
    list.splice(Number(del.dataset.del), 1);
    storeSaved(list);
    buildSaved();
    return;
  }
  const pill = e.target.closest('.spill');
  if (pill) applyState(loadSaved()[Number(pill.dataset.i)]);
});

function saveCurrent(){
  const st = currentState();
  if (!st.q && !st.brands.length && !st.grade && !st.grip && !Object.keys(st.specs).length)
    return;                                     // nothing to save
  const list = loadSaved().filter(x => !sameState(x, st));
  list.unshift(st);
  storeSaved(list.slice(0, 12));
  buildSaved();
}

/* The model line is the word after the brand: "Head Gravity Pro 2025" -> Gravity.
   The list is rebuilt from whatever brands are selected, so it stays short and
   only ever offers lines that actually have stock. */
function familyOf(name){
  const w = name.split(/\s+/);
  return w.length > 1 ? w[1] : '';
}

function buildFamilies(){
  const pool = brandSel.size ? ROWS.filter(r => brandSel.has(r.brand)) : ROWS;
  const counts = {};
  pool.forEach(r => {
    const f = familyOf(r.racquet);
    if (f && !/^\d/.test(f)) counts[f] = (counts[f] || 0) + 1;
  });
  const top = Object.entries(counts)
    .filter(([, n]) => n >= 2)
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .slice(0, 10);
  const cur = $('q').value.trim().toLowerCase();
  $('families').innerHTML = top.length
    ? '<span class="flab">Lines</span>' + top.map(([f, n]) =>
        `<button class="fpill" data-fam="${f}" aria-pressed="${cur === f.toLowerCase()}">` +
        `${f} <span style="opacity:.55">${n}</span></button>`).join('')
    : '';
}

$('families').addEventListener('click', e => {
  const b = e.target.closest('.fpill');
  if (!b) return;
  const f = b.dataset.fam;
  // clicking the active line clears it, so the pills toggle
  $('q').value = ($('q').value.trim().toLowerCase() === f.toLowerCase()) ? '' : f;
  render();
});

function priceSub(r){
  if (!r.new_price) return '';
  const n = '$' + r.new_price.toFixed(0);
  if (r.new_cheaper) return `new is ${n}`;
  return `<s>${n}</s> <span class="cut">${r.discount_pct}% off</span>`;
}

function signal(r){
  if (r.new_cheaper) return '<span class="tag t-trap">⚠ buy new</span>';
  if (r.verdict==='LOWEST EVER') return '<span class="tag t-low">▼ lowest ever</span>';
  if (r.verdict==='BELOW USUAL') return '<span class="tag t-below">▼ below usual</span>';
  if (r.is_new) return '<span class="tag t-new">● new</span>';
  if (r.verdict==='high') return '<span class="quiet">above usual</span>';
  if (r.verdict==='typical') return '<span class="quiet">typical</span>';
  return '<span class="dash">—</span>';
}

/* Tennis Warehouse lists each physical racquet as its own SKU, so three copies
   of the same frame at the same grade, grip and price arrive as three rows.
   Grouping folds them into one and counts the units. */
function group(rows){
  const by = new Map();
  for (const r of rows) {
    const k = [r.racquet, r.grade, r.grip, r.used_price].join('|');
    const hit = by.get(k);
    if (hit) { hit.units += 1; hit.stock += (+r.in_stock || 0); }
    else by.set(k, Object.assign({}, r, {units:1, stock:(+r.in_stock||0)}));
  }
  return [...by.values()];
}

function render(){
  const q = $('q').value.toLowerCase().trim();
  const g = $('grade').value, gr = $('grip').value;

  let rows = ROWS.filter(r =>
    (!q || r.racquet.toLowerCase().includes(q)) &&
    (!brandSel.size || brandSel.has(r.brand)) &&
    (!g || r.grade===g) && (!gr || r.grip===gr) &&
    (view!=='trap' ? true : r.new_cheaper) &&
    (view!=='cheap' || (r.used_price<=150 && !r.new_cheaper)) &&
    (view!=='deals' || (!r.new_cheaper &&
      (r.is_new || r.verdict==='LOWEST EVER' || r.verdict==='BELOW USUAL'))));

  const nf = id => { const v = parseFloat($(id).value); return isNaN(v) ? null : v; };
  const band = (val, lo, hi) =>
    (lo === null && hi === null) ? true
    : (val == null ? false : (lo === null || val >= lo) && (hi === null || val <= hi));
  rows = rows.filter(r =>
    band(r.head_in2, nf('head_min'), nf('head_max')) &&
    band(r.weight_oz, nf('wt_min'), nf('wt_max')) &&
    band(r.swingweight, nf('sw_min'), nf('sw_max')) &&
    band(r.stiffness, nf('st_min'), nf('st_max')));

  const total = rows.length;
  if ($('group').checked) rows = group(rows);

  rows.sort((x,y)=>{
    if (view==='all' && x.new_cheaper !== y.new_cheaper) return x.new_cheaper ? 1 : -1;
    let a = x[sortKey], c = y[sortKey];
    if (a==null||a==='') a = sortDir<0 ? -Infinity : Infinity;
    if (c==null||c==='') c = sortDir<0 ? -Infinity : Infinity;
    return (typeof a==='string' ? a.localeCompare(c) : a-c) * sortDir;
  });

  const COLS = 7;
  $('tb').innerHTML = rows.map((r,i)=>`<tr class="row ${r.new_cheaper?'trap':''}"
    data-i="${i}" style="animation-delay:${Math.min(i*14,320)}ms">
    <td class="name"><div class="nw">${thumb(r)}<div>
      <a href="${r.url}" target="_blank" rel="noopener">${tidy(r.racquet)}</a>
      <span class="brand">${r.brand}${r.units>1?`<span class="units">${r.units} available</span>`:''}${
        r.rating?`<span class="rate"><b>${r.rating}</b>/5 · ${r.reviews}</span>`:''}</span>
      </div></div><span class="caret">▶</span></td>
    <td class="r pricecell">
      <span class="p">$${r.used_price.toFixed(0)}</span>
      <span class="psub">${priceSub(r)}</span></td>
    <td><span class="chip">${(r.grade||'—').replace('Grade ','')}</span></td>
    <td class="grip">${r.grip||'<span class="dash">—</span>'}</td>
    <td class="col-signal">${signal(r)}${r.median?` <span class="med">~$${Math.round(r.median)}</span>`:''}</td>
    <td class="col-spark">${spark(r.key)}</td>
    <td class="col-qty r num">${r.units>1?r.units:(r.in_stock??'')}</td></tr>
    <tr class="det" data-i="${i}"><td colspan="${COLS}">${details(r)}</td></tr>`).join('');

  const active = SPEC_IDS.concat(['grade','grip']).filter(id => $(id).value !== '').length;
  $('specn').textContent = active ? active : '';

  // The Signal column is dead until price history exists -- hide it rather than
  // showing a column of em-dashes.
  document.body.classList.toggle('nosignal',
    !rows.some(r => r.verdict || r.is_new));

  buildFamilies();
  buildSaved();
  drawChips();

  $('count').textContent = $('group').checked && rows.length !== total
    ? `${rows.length} of ${ROWS.length} listings · ${total - rows.length} duplicates folded in`
    : `${rows.length} of ${ROWS.length} listings`;
  $('empty').hidden = rows.length > 0;
}

const SPEC_CHIPS = {head_min:'Head ≥', head_max:'Head ≤', wt_min:'Weight ≥',
  wt_max:'Weight ≤', sw_min:'Swing ≥', sw_max:'Swing ≤',
  st_min:'Flex ≥', st_max:'Flex ≤'};

function chip(label, value, clear){
  return `<span class="chip-f">${label} <b>${value}</b>` +
    `<button data-clear="${clear}" aria-label="Remove ${label} filter">✕</button></span>`;
}

function drawChips(){
  const out = [];
  [['grade','Grade'],['grip','Grip']].forEach(([id,label]) => {
    // "Grade A" under a "Grade" label would read "Grade Grade A".
    if ($(id).value) out.push(chip(label, $(id).value.replace('Grade ', ''), id));
  });
  SPEC_IDS.forEach(id => {
    if ($(id).value) out.push(chip(SPEC_CHIPS[id], $(id).value, id));
  });
  const anyFilter = out.length || brandSel.size || $('q').value.trim();
  $('chips').innerHTML = anyFilter
    ? out.join('') +
      (canStore ? '<button class="savebtn" id="savecur">+ Save search</button>' : '') +
      '<button class="clearall" id="clearchips">Clear all</button>'
    : '';
  $('chips').hidden = !anyFilter;
}

function clearFilters(){
  ['q','grade','grip'].concat(SPEC_IDS).forEach(id => $(id).value = '');
  brandSel.clear();
  syncBrands();
  render();
}

$('chips').addEventListener('click', e => {
  const b = e.target.closest('[data-clear]');
  if (b) { $(b.dataset.clear).value = ''; render(); return; }
  if (e.target.id === 'clearchips') clearFilters();
  if (e.target.id === 'savecur') saveCurrent();
});
$('clearall').addEventListener('click', clearFilters);

/* ---- click a thumbnail for the full-size shot ----
   Locally the 400px images sit in thumbs_large/ next to this file, so the
   lightbox works offline; the published snapshot has no such folder and falls
   back to Tennis Warehouse's own resizer. */
const bigSrc = code => WEB
  ? `https://img.tennis-warehouse.com/watermark/rs.php?path=${code}-thumb.jpg&nw=400`
  : `thumbs_large/${code}.jpg`;

let lastFocus = null;
function openLb(code, name){
  lastFocus = document.activeElement;
  $('lbimg').src = bigSrc(code);
  $('lbimg').alt = tidy(name);
  $('lbcap').innerHTML = `${tidy(name)}<span>${code}</span>`;
  $('lb').hidden = false;
  $('lbclose').focus();
}
function closeLb(){
  $('lb').hidden = true;
  $('lbimg').removeAttribute('src');
  if (lastFocus) lastFocus.focus();
}
$('tb').addEventListener('click', e => {
  const b = e.target.closest('.picbtn');
  if (b) { openLb(b.dataset.code, b.dataset.name); return; }
  if (e.target.closest('a')) return;              // let the product link through
  const row = e.target.closest('tr.row');
  if (!row) return;
  const det = row.nextElementSibling;
  row.classList.toggle('open');
  if (det && det.classList.contains('det')) det.classList.toggle('open');
});
$('lbclose').addEventListener('click', closeLb);
$('lb').addEventListener('click', e => { if (e.target === $('lb')) closeLb(); });
// If the large file is missing, show the small one rather than a broken icon.
$('lbimg').addEventListener('error', function(){
  const code = $('lbcap').querySelector('span').textContent;
  if (THUMBS[code] && this.src !== THUMBS[code]) this.src = THUMBS[code];
});

/* hover layer for the sparklines */
const tip = $('tip');
document.addEventListener('mousemove', e => {
  const s = e.target.closest && e.target.closest('.spark');
  if (!s) { tip.style.opacity = 0; return; }
  const pts = SERIES[s.dataset.key] || [];
  const vals = pts.map(p=>p[1]);
  const med = [...vals].sort((a,b)=>a-b)[Math.floor(vals.length/2)];
  tip.innerHTML = `<b>$${Math.min(...vals)}</b> low · <b>$${med}</b> typical ·
    <b>$${Math.max(...vals)}</b> high<br>
    <span style="color:var(--muted)">${pts.length} days · latest ${pts[pts.length-1][0]}</span>`;
  tip.style.opacity = 1;
  tip.style.left = Math.min(e.clientX + 15, innerWidth - 264) + 'px';
  tip.style.top = (e.clientY + 18) + 'px';
});

document.querySelectorAll('th[data-k]').forEach(th => th.onclick = () => {
  const k = th.dataset.k;
  sortDir = (k===sortKey) ? -sortDir
          : (['racquet','brand','grade','grip'].includes(k) ? 1 : -1);
  sortKey = k;
  document.querySelectorAll('th[data-k]').forEach(o => {
    o.removeAttribute('data-on'); o.querySelector('.ar').textContent = '▼';
  });
  th.setAttribute('data-on','');
  th.querySelector('.ar').textContent = sortDir < 0 ? '▼' : '▲';
  render();
});

document.querySelectorAll('.tabs button').forEach(btn => btn.onclick = () => {
  document.querySelectorAll('.tabs button')
    .forEach(o => o.setAttribute('aria-pressed', o === btn));
  view = btn.dataset.view;
  render();
});

const SPEC_IDS = ['head_min','head_max','wt_min','wt_max','sw_min','sw_max','st_min','st_max'];
['q','grade','grip','group'].concat(SPEC_IDS)
  .forEach(id => $(id).addEventListener('input', render));

// The sort dropdown and the column headers drive the same sort state.
$('sortby').addEventListener('change', () => {
  sortKey = $('sortby').value;
  sortDir = ASC.has(sortKey) ? 1 : -1;
  document.querySelectorAll('th[data-k]').forEach(o => o.removeAttribute('data-on'));
  render();
});

$('specbtn').addEventListener('click', () => {
  const open = $('specbar').hidden;
  $('specbar').hidden = !open;
  $('specbtn').setAttribute('aria-expanded', String(open));
});


addEventListener('keydown', e => {
  if (e.key === '/' && document.activeElement !== $('q')) { e.preventDefault(); $('q').focus(); }
  if (e.key === 'Escape') {
    if (!$('lb').hidden) { closeLb(); return; }
    $('q').value = ''; $('q').blur(); render();
  }
});

const SCRAPED = new Date(__SCRAPED_ISO__);
__REFRESHJS__
const hrs = (Date.now() - SCRAPED) / 3.6e6;
const age = () => hrs < 48 ? Math.round(hrs)+' hours' : Math.round(hrs/24)+' days';
if (hrs > 12) $('staleness').innerHTML = `<div class="stale">__STALE__</div>`;

buildBrands();
render();
</script>
"""

# Everything below is emitted only for the local build -- it drives the Shortcut
# refresh button, which exists nowhere else. Kept out of the published page so
# it carries no dead shortcuts:// code.
REFRESH_JS = r"""
/* --- fetch new data -----------------------------------------------------
   Chrome follows the shortcuts:// link and runs the scrape. Safari refuses
   custom schemes from file:// pages and fails silently, so detect that (we
   still hold focus a moment later) and show how to run it by hand. */
const refresh = $('refresh');
if (refresh) {
  const showHowto = () => {
    $('staleness').innerHTML = `<div class="howto">
      <b>Safari won't launch the shortcut from a local file.</b>
      It blocks <code>shortcuts://</code> links for security. Run it one of these ways:
      <ol>
        <li>Press <kbd>⌘ Space</kbd>, type <b>Check Racquets</b>, press <kbd>Return</kbd></li>
        <li>Or double-click <code>Check Racquets.command</code> in Finder</li>
      </ol>
      Takes about 5 seconds, then come back and reload.
      <div class="row">
        <button class="btn" id="reloadNow">Reload page</button>
        <button class="btn ghost" id="copyCmd">Copy terminal command</button>
      </div></div>`;
    $('reloadNow').onclick = () => location.reload();
    $('copyCmd').onclick = async (e) => {
      try {
        await navigator.clipboard.writeText('shortcuts run "Check Racquets"');
        e.target.textContent = 'Copied';
      } catch { e.target.textContent = 'Press ⌘C to copy'; }
    };
  };
  refresh.addEventListener('click', () => {
    // A full scrape measures ~4-5s including Shortcuts launch. Reload just after
    // that; if the data turns out not to have moved, the check on load below
    // waits a little longer rather than us padding the countdown for everyone.
    sessionStorage.setItem('tw_refresh_at', String(Date.now()));
    sessionStorage.removeItem('tw_recheck');
    let left = 7;
    refresh.setAttribute('aria-busy','true');
    const tick = () => {
      refresh.textContent = left > 0 ? `Fetching… ${left}s` : 'Reloading…';
      if (left-- <= 0) { clearInterval(iv); location.reload(); }
    };
    tick();
    const iv = setInterval(tick, 1000);
    setTimeout(() => {
      if (!document.hasFocus()) return;   // Shortcuts took focus: it ran.
      clearInterval(iv);
      refresh.removeAttribute('aria-busy');
      refresh.textContent = '↻ Fetch new data';
      showHowto();
    }, 1500);
  });
}

/* --- did the refresh actually land? ---
   The countdown is tuned to a normal run. If the scrape was slow and this page
   is still the old build, wait a beat and reload once more instead of leaving
   stale numbers on screen. */
(function checkRefresh(){
  const asked = Number(sessionStorage.getItem('tw_refresh_at') || 0);
  if (!asked) return;
  if (SCRAPED.getTime() > asked) {           // fresh data arrived, we're done
    sessionStorage.removeItem('tw_refresh_at');
    sessionStorage.removeItem('tw_recheck');
    return;
  }
  const tries = Number(sessionStorage.getItem('tw_recheck') || 0);
  if (tries >= 3) {                          // give up rather than loop
    sessionStorage.removeItem('tw_refresh_at');
    sessionStorage.removeItem('tw_recheck');
    $('staleness').innerHTML = `<div class="stale">The refresh didn't come
      through. Run <b>Check Racquets</b> from Spotlight, then reload.</div>`;
    return;
  }
  sessionStorage.setItem('tw_recheck', String(tries + 1));
  $('staleness').innerHTML = '<div class="stale">Still fetching — reloading…</div>';
  setTimeout(() => location.reload(), 3000);
})();
"""


def _cell(label, value, sub, cls=""):
    return (f'<div class="cell {cls}"><div class="lab">{label}</div>'
            f'<span class="val">{value}</span><div class="sub">{sub}</div></div>')


def load_thumbs(thumb_dir, codes):
    """{code: data URI} for the cached racquet thumbnails we actually need."""
    if not thumb_dir or not os.path.isdir(thumb_dir):
        return {}
    out = {}
    for code in codes:
        path = os.path.join(thumb_dir, f"{code}.jpg")
        if not os.path.exists(path):
            continue
        with open(path, "rb") as f:
            out[code] = "data:image/jpeg;base64," + base64.b64encode(f.read()).decode()
    return out


def load_series(hist_path):
    """{racquet||grade: [[date, min price that day], ...]} for the sparklines."""
    by_day = {}
    if not os.path.exists(hist_path):
        return {}
    with open(hist_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            try:
                price = float(row["used_price"])
            except (ValueError, KeyError):
                continue
            key = f"{row['racquet']}||{row['grade']}"
            day = by_day.setdefault(key, {})
            day[row["date"]] = min(day.get(row["date"], price), price)
    return {k: [[d, v[d]] for d in sorted(v)] for k, v in by_day.items()}


# How the page will be served, which decides three things: whether it carries
# its own doctype, whether it offers the Shortcut refresh button, and what the
# staleness banner tells you to do about old prices.
#   local    -- opened from disk on the Mac; the Shortcut can refresh it
#   pages    -- GitHub Pages; refreshes itself every 6h, no Shortcut available
#   artifact -- a published Claude artifact; frozen, and wrapped in its own head
STALE_MSG = {
    "local": "These prices are ${age()} old. "
             "Run the <b>Check Racquets</b> shortcut to refresh.",
    "pages": "These prices are ${age()} old — the scheduled refresh may have "
             "failed. Check the live listing before buying.",
    "artifact": "Snapshot taken ${age()} ago. This page shows prices as they "
                "were then — it does not update on its own, so check the live "
                "listing before buying.",
}


def write_html(listings, path, days, hist_path, mode="local", thumb_dir=None):
    # Only a published artifact is wrapped in someone else's <head> and has no
    # thumbs_large/ beside it; Pages serves a plain file and ships the folder.
    web = mode == "artifact"
    now = dt.datetime.now()
    stamp = now.strftime("%a %b %-d at %-I:%M %p")
    n_new = sum(bool(r.get("is_new")) for r in listings)
    n_trap = sum(bool(r.get("new_cheaper")) for r in listings)
    racquets = len({r["racquet"] for r in listings})

    # Display only -- history keys and grouping still use the full stored name.
    tidy = lambda n: " ".join(w for w in n.split()
                              if w.lower().strip(",") not in ("racquet", "racquets"))
    real = [r for r in listings
            if not r.get("new_cheaper") and r.get("discount_pct") != ""]
    best = max(real, key=lambda r: r["discount_pct"]) if real else None

    sub = (f"Scraped <b>{stamp}</b> · {len(listings)} listings across {racquets} "
           f"racquets · {days} day{'s' if days != 1 else ''} of price history")

    board = (
        _cell("Listings", len(listings), f"across {racquets} racquets") +
        _cell("New or repriced", n_new, "since your last check") +
        (_cell("Best discount", f"{best['discount_pct']}%",
               html.escape(tidy(best["racquet"])), "win") if best else
         _cell("Best discount", "—", "no data")) +
        _cell("Avoid", n_trap, "used costs more than new", "alert" if n_trap else "")
    )

    opts = lambda vals: "".join(f"<option>{html.escape(v)}</option>"
                                for v in sorted(v for v in vals if v))

    notes = []
    if days < 4:
        notes.append("<p><b>Price history is still building.</b> The <i>lowest ever</i> "
                     "and <i>below usual</i> signals need a few days of recorded prices "
                     "before they can fire, so most rows currently read <i>new</i>. The "
                     "Trend column appears once there are two days to compare.</p>")
    else:
        notes.append("<p>Signals compare each listing against that same racquet and "
                     "grade's own past prices, not a fixed threshold. <b>~$</b> is its "
                     "typical price so far; hover a trend line for low, typical and "
                     "high.</p>")
    notes.append("<p><b>Off %</b> is measured against Tennis Warehouse's current price, "
                 "which is often already marked down — so the real saving against list "
                 "price is usually bigger.</p>")
    if n_trap:
        notes.append(f"<p><b>{n_trap} listing{'s' if n_trap != 1 else ''} marked "
                     "&ldquo;buy new&rdquo;</b> cost as much as or more than the same "
                     "racquet brand new, because the new one is on clearance. They sink "
                     "to the bottom of every sort — see them on their own under "
                     "<b>Avoid</b>.</p>")
    if web:
        notes.append(f"<p>This is a <b>snapshot</b> taken {stamp}. Prices and "
                     "availability change daily — every racquet name links through to "
                     "the live listing.</p>")
    notes.append("<p>Press <code>/</code> to search, <code>Esc</code> to clear. Click "
                 "any column heading to sort.</p>")

    thumbs = load_thumbs(thumb_dir, {r.get("code") for r in listings if r.get("code")})

    series = load_series(hist_path)
    keys = {f"{r['racquet']}||{r['grade']}" for r in listings}
    series = {k: v for k, v in series.items() if k in keys and len(v) >= 2}

    payload = json.dumps([
        {k: r[k] for k in ("brand", "racquet", "grade", "grip", "used_price",
                           "new_price", "discount_pct", "in_stock", "url",
                           "is_new", "verdict", "median", "new_cheaper", "code",
                           "list_price", "rating", "reviews", "specs", "nspec")}
        for r in listings
    ]).replace("<", "\\u003c")

    page = (("" if web else LOCAL_HEAD) + TMPL
            .replace("__FONTS__", FONT_CSS)
            .replace("__WEB__", "true" if web else "false")
            # The Shortcut only exists on the Mac, so the button is local-only.
            .replace("__REFRESHBTN__", '' if mode != "local" else
                     '<a class="btn" id="refresh" '
                     'href="shortcuts://run-shortcut?name=Check%20Racquets" '
                     'title="Re-scrape Tennis Warehouse">↻ Fetch new data</a>')
            .replace("__STALE__", STALE_MSG[mode])
            .replace("__REFRESHJS__", REFRESH_JS if mode == "local" else "")
            .replace("__SUB__", sub)
            .replace("__TILES__", board)
            .replace("__NTRAP__", str(n_trap))
            .replace("__BRANDS__", opts({r["brand"] for r in listings}))
            .replace("__GRADES__", opts({r["grade"] for r in listings}))
            .replace("__GRIPS__", opts({r["grip"] for r in listings}))
            .replace("__NOTES__", "".join(notes))
            .replace("__SERIES__", json.dumps(series).replace("<", "\\u003c"))
            .replace("__THUMBS__", json.dumps(thumbs).replace("<", "\\u003c"))
            .replace("__SCRAPED_ISO__", json.dumps(now.isoformat()))
            .replace("__DATA__", payload))

    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(page)
    os.replace(tmp, path)
