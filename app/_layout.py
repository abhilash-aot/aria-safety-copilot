"""CSS theme — character-driven Safety Copilot with ambient motion."""
import streamlit as st


def inject_phone_css() -> None:
    st.markdown("""<style>

/* ── Base ─────────────────────────────────────────────────────────────── */
html,body,[class*="css"]{font-family:-apple-system,BlinkMacSystemFont,"Inter","Segoe UI",sans-serif;}

/* Streamlit ships a 60px opaque header that overlaps page titles.
   Make it transparent so content scrolls under it cleanly, and push
   the block-container below it so titles are fully visible. */
[data-testid="stHeader"]{background:transparent!important;}
.block-container{padding-top:3.4rem;padding-bottom:3rem;max-width:820px;animation:page-fade-in 0.6s ease-out;}
@media(max-width:480px){
  .block-container{padding:3rem 0.4rem 0.4rem!important;}
  .stButton button{width:100%;min-height:52px;}
}

/* ── Ambient aurora background (subtle, behind everything) ────────────── */
.stApp::before{
  content:"";position:fixed;inset:0;z-index:-1;pointer-events:none;
  background:
    radial-gradient(at 18% 8%,rgba(99,102,241,0.07),transparent 45%),
    radial-gradient(at 82% 95%,rgba(15,118,110,0.07),transparent 45%),
    radial-gradient(at 55% 55%,rgba(8,145,178,0.04),transparent 50%);
  animation:aurora 22s ease-in-out infinite alternate;
}
@keyframes aurora{
  0%  {transform:translate(0,0) scale(1);}
  50% {transform:translate(-30px,15px) scale(1.08);}
  100%{transform:translate(20px,-25px) scale(0.95);}
}
@keyframes page-fade-in{from{opacity:0;transform:translateY(8px);}to{opacity:1;transform:translateY(0);}}

/* ── Section headers (animated icon) ──────────────────────────────────── */
.section-header{
  font-weight:800;font-size:1.1rem;margin-top:26px;margin-bottom:12px;
  color:#0f172a;display:flex;align-items:center;gap:10px;letter-spacing:-0.01em;
}
.section-header::before{
  content:"";display:inline-block;width:4px;height:22px;border-radius:2px;
  background:linear-gradient(180deg,#0f766e 0%,#0891b2 100%);
  animation:bar-grow 0.5s cubic-bezier(0.34,1.56,0.64,1) both;
}
.section-icon{
  display:inline-block;font-size:1.15rem;
  animation:icon-float 3.2s ease-in-out infinite;
}
@keyframes bar-grow{from{height:0;}to{height:22px;}}
@keyframes icon-float{0%,100%{transform:translateY(0) rotate(0);}50%{transform:translateY(-3px) rotate(-3deg);}}

/* XL variant for the page highlight section */
.section-header-xl{
  font-size:1.45rem;margin-top:34px;margin-bottom:4px;
}
.section-header-xl::before{height:28px;width:5px;}
.section-header-xl .section-icon{font-size:1.4rem;}
.section-tag{
  margin-left:auto;font-size:0.65rem;font-weight:800;letter-spacing:0.15em;
  color:#0891b2;background:linear-gradient(135deg,#ccfbf1,#cffafe);
  padding:4px 9px;border-radius:12px;border:1px solid #67e8f9;
  animation:tag-shimmer 3s ease-in-out infinite;
}
@keyframes tag-shimmer{0%,100%{box-shadow:0 0 0 0 rgba(6,182,212,0.3);}50%{box-shadow:0 0 0 6px rgba(6,182,212,0);}}
.section-sub{
  color:#64748b;font-size:0.88rem;margin:0 0 8px 14px;
  animation:slide-in 0.5s ease-out both;
}

/* ── Hero v2 (solid title, one status strip) ──────────────────────────── */
.hero-v2{
  display:flex;flex-direction:column;justify-content:center;
  padding:6px 0 4px;min-height:90px;
}
.hero-v2-title{
  font-size:1.85rem;font-weight:900;letter-spacing:-0.025em;line-height:1.15;
  color:#0f172a;margin:0 0 3px 0;padding:0;
  animation:hero-title-in 0.5s cubic-bezier(0.34,1.56,0.64,1) both;
}
@keyframes hero-title-in{
  from{opacity:0;transform:translateY(-6px);}
  to  {opacity:1;transform:translateY(0);}
}
.hero-v2-sub{
  color:#64748b;font-size:0.9rem;font-weight:500;margin-bottom:10px;
  animation:slide-in 0.45s ease-out 0.08s both;
}
.hero-v2-sub b{color:#0f766e;font-weight:800;letter-spacing:0.02em;}
.hero-v2-sub-sep{color:#cbd5e1;margin:0 6px;}

.hero-v2-chips{
  display:flex;flex-wrap:wrap;gap:6px;align-items:center;
  animation:slide-in 0.45s ease-out 0.16s both;
}

/* State chip — colour reacts to day severity (set via --s custom prop) */
.hero-v2-state{
  display:inline-flex;align-items:center;gap:6px;
  padding:5px 11px;border-radius:12px;
  background:color-mix(in srgb, var(--s) 10%, white);
  border:1.5px solid var(--s);
  color:var(--s);
  font-size:0.74rem;font-weight:800;letter-spacing:0.08em;
}
.hero-v2-state-dot{
  width:7px;height:7px;border-radius:50%;background:var(--s);
  box-shadow:0 0 0 0 var(--s);
  animation:hero-state-pulse 1.5s ease-in-out infinite;
}
@keyframes hero-state-pulse{
  0%,100%{box-shadow:0 0 0 0 var(--s);}
  50%    {box-shadow:0 0 0 5px transparent;}
}

/* Info chips */
.hero-v2-chip{
  background:#f0fdfa;color:#0f766e;border:1px solid #99f6e4;
  padding:4px 10px;border-radius:12px;font-size:0.78rem;font-weight:600;
}
.hero-v2-chip b{color:#0f172a;font-variant-numeric:tabular-nums;}
.hero-v2-chip.chip-warn{background:#fff1f2;color:#be123c;border-color:#fecaca;}
.hero-v2-chip.chip-warn b{color:#7f1d1d;}
.hero-v2-chip.chip-ok{background:#ecfdf5;color:#047857;border-color:#86efac;}
.hero-v2-chip.chip-ok b{color:#065f46;}

/* Legacy aliases — keep so any third-page still using them renders */
.hero-title{font-size:1.75rem;font-weight:900;color:#0f172a;letter-spacing:-0.02em;}
.hero-sub  {color:#64748b;font-size:0.92rem;margin-bottom:6px;}

/* Section meta label (right-aligned small text in section headers) */
.section-meta{
  margin-left:auto;font-size:0.75rem;font-weight:600;color:#94a3b8;
  letter-spacing:0.02em;
}

/* (Brief v2 styles live inside the _sections.py component iframe — scoped there.) */
@keyframes blink{0%,100%{opacity:1}50%{opacity:0}}

/* ── Violation cards — staggered slide-in + hover lift ────────────────── */
@keyframes slide-in{from{opacity:0;transform:translateX(-16px);}to{opacity:1;transform:translateX(0);}}
@keyframes pulse-ring-critical{
  0%  {box-shadow:0 0 0 0 rgba(220,38,38,0.3);}
  70% {box-shadow:0 0 0 10px rgba(220,38,38,0);}
  100%{box-shadow:0 0 0 0 rgba(220,38,38,0);}
}
@keyframes pulse-ring-high{
  0%  {box-shadow:0 0 0 0 rgba(234,88,12,0.22);}
  70% {box-shadow:0 0 0 8px rgba(234,88,12,0);}
  100%{box-shadow:0 0 0 0 rgba(234,88,12,0);}
}

.violation-critical,.violation-high,.violation-medium,.violation-low{
  padding:13px 15px;margin-bottom:10px;border-radius:10px;
  transition:transform 0.22s cubic-bezier(0.34,1.56,0.64,1),box-shadow 0.22s;
  cursor:default;
}
.violation-critical:hover,.violation-high:hover,
.violation-medium:hover,.violation-low:hover{
  transform:translateX(4px);
}

.violation-critical{
  border-left:5px solid #dc2626;
  background:linear-gradient(90deg,#fff1f2 0%,#fef2f2 100%);
  animation:slide-in 0.3s ease-out both,pulse-ring-critical 2s ease-in-out infinite;
  box-shadow:0 2px 8px rgba(220,38,38,0.1);
}
.violation-critical:hover{box-shadow:0 6px 18px rgba(220,38,38,0.25);}
.violation-high{
  border-left:5px solid #ea580c;
  background:linear-gradient(90deg,#fff4ed 0%,#fff7ed 100%);
  animation:slide-in 0.3s ease-out both,pulse-ring-high 2.5s ease-in-out infinite;
  box-shadow:0 2px 6px rgba(234,88,12,0.09);
}
.violation-high:hover{box-shadow:0 6px 16px rgba(234,88,12,0.2);}
.violation-medium{
  border-left:5px solid #d97706;
  background:linear-gradient(90deg,#fefce8 0%,#fffbeb 100%);
  animation:slide-in 0.3s ease-out both;
  box-shadow:0 1px 4px rgba(217,119,6,0.07);
}
.violation-medium:hover{box-shadow:0 5px 14px rgba(217,119,6,0.16);}
.violation-low{
  border-left:5px solid #94a3b8;background:#f8fafc;
  animation:slide-in 0.3s ease-out both;
}
.violation-low:hover{box-shadow:0 4px 12px rgba(148,163,184,0.2);}

/* ── Fix badge pop ────────────────────────────────────────────────────── */
@keyframes pop-in{0%{transform:scale(0.6);opacity:0;}70%{transform:scale(1.1);}100%{transform:scale(1);opacity:1;}}
.fix-badge{animation:pop-in 0.4s cubic-bezier(0.34,1.56,0.64,1) both;}

/* ── Clean day banner ─────────────────────────────────────────────────── */
@keyframes celebrate-glow{
  0%,100%{box-shadow:0 0 0 0 rgba(16,185,129,0.22);}
  50%    {box-shadow:0 0 0 14px rgba(16,185,129,0);}
}
.clean-day-banner{
  background:linear-gradient(135deg,#f0fdf4 0%,#dcfce7 100%);
  border:1.5px solid #86efac;border-radius:16px;padding:26px;text-align:center;
  animation:slide-in 0.4s ease-out,celebrate-glow 2s ease-in-out infinite;
}

/* ── Metric cards with shimmer ────────────────────────────────────────── */
[data-testid="stMetric"]{
  background:linear-gradient(135deg,#f0fdfa 0%,#f8fafc 100%);
  border:1.5px solid #ccfbf1;padding:16px 18px;border-radius:14px;
  box-shadow:0 3px 10px rgba(15,118,110,0.08);
  position:relative;overflow:hidden;
  transition:transform 0.25s,box-shadow 0.25s;
}
[data-testid="stMetric"]::after{
  content:"";position:absolute;top:0;left:-100%;width:50%;height:100%;
  background:linear-gradient(90deg,transparent,rgba(15,118,110,0.09),transparent);
  animation:shimmer 4.5s ease-in-out infinite;
}
[data-testid="stMetric"]:hover{transform:translateY(-2px);box-shadow:0 8px 22px rgba(15,118,110,0.15);}
@keyframes shimmer{0%{left:-100%;}60%,100%{left:150%;}}
[data-testid="stMetricValue"]{color:#0f766e;font-weight:900;font-size:1.6rem;}
[data-testid="stMetricLabel"]{color:#475569;font-weight:600;font-size:0.82rem;}

/* ── Buttons with hover shimmer ───────────────────────────────────────── */
.stButton>button{
  background:linear-gradient(135deg,#0f766e 0%,#0891b2 100%);
  color:white;border:none;font-weight:700;border-radius:12px;letter-spacing:0.01em;
  transition:transform 0.15s,box-shadow 0.15s,background 0.2s;
  box-shadow:0 4px 14px rgba(15,118,110,0.3);
  position:relative;overflow:hidden;
}
.stButton>button::before{
  content:"";position:absolute;top:0;left:-100%;width:100%;height:100%;
  background:linear-gradient(90deg,transparent,rgba(255,255,255,0.25),transparent);
  transition:left 0.6s;
}
.stButton>button:hover::before{left:100%;}
.stButton>button:hover{
  background:linear-gradient(135deg,#115e59 0%,#0e7490 100%);
  transform:translateY(-2px);box-shadow:0 7px 22px rgba(15,118,110,0.42);
}
.stButton>button:active{transform:translateY(0);}
.stButton>button[kind="primary"]{background:linear-gradient(135deg,#0f766e 0%,#0891b2 100%);}

/* ── Sidebar ──────────────────────────────────────────────────────────── */
[data-testid="stSidebar"]{
  background:linear-gradient(180deg,#f0fdfa 0%,#f8fafc 100%);
  border-right:1px solid #ccfbf1;
}
[data-testid="stSidebar"] .stMarkdown p{animation:slide-in 0.4s ease-out both;}

/* ── ARIA sidebar brand header ────────────────────────────────────────── */
.aria-sb-header{
  display:flex;align-items:center;gap:11px;
  padding:14px 14px 12px;margin:-1rem -1rem 10px -1rem;
  background:linear-gradient(135deg,#0f172a 0%,#134e4a 55%,#0f766e 100%);
  background-size:200% 200%;
  animation:sb-brand-shift 10s ease-in-out infinite,slide-in 0.5s ease-out;
  border-bottom:1px solid rgba(103,232,249,0.25);
}
@keyframes sb-brand-shift{0%,100%{background-position:0% 50%;}50%{background-position:100% 50%;}}

.aria-sb-shield-wrap{
  position:relative;width:40px;height:40px;flex-shrink:0;
}
.aria-sb-shield-ring{
  position:absolute;inset:0;border-radius:50%;
  opacity:0.35;filter:blur(6px);
  animation:sb-ring-pulse 2s ease-in-out infinite;
}
@keyframes sb-ring-pulse{
  0%,100%{transform:scale(1);opacity:0.35;}
  50%    {transform:scale(1.25);opacity:0.55;}
}
.aria-sb-shield{
  position:relative;width:40px;height:40px;border-radius:50%;
  background:linear-gradient(135deg,#67e8f9,#0891b2);
  display:flex;align-items:center;justify-content:center;font-size:1.3rem;
  box-shadow:0 4px 14px rgba(8,145,178,0.45),inset 0 0 8px rgba(255,255,255,0.25);
  animation:sb-shield-float 3.5s ease-in-out infinite;
}
@keyframes sb-shield-float{
  0%,100%{transform:translateY(0) rotate(0);}
  50%    {transform:translateY(-2px) rotate(-3deg);}
}

.aria-sb-text{flex:1;min-width:0;}
.aria-sb-name{
  font-size:1.35rem;font-weight:900;letter-spacing:0.04em;line-height:1;
  background:linear-gradient(135deg,#67e8f9 0%,#a7f3d0 50%,#67e8f9 100%);
  background-size:200% auto;
  -webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;
  animation:sb-name-shimmer 4s ease-in-out infinite;
}
@keyframes sb-name-shimmer{0%,100%{background-position:0% 50%;}50%{background-position:100% 50%;}}
.aria-sb-sub{
  font-size:0.7rem;color:rgba(255,255,255,0.7);
  letter-spacing:0.15em;font-weight:700;text-transform:uppercase;margin-top:2px;
}

/* Status chip just under the header */
.aria-sb-status{
  display:flex;align-items:center;gap:7px;
  margin:-8px -1rem 12px -1rem;padding:7px 14px 9px;
  background:linear-gradient(180deg,rgba(15,23,42,0.95),rgba(15,23,42,0.8));
  border-bottom:1px solid rgba(255,255,255,0.08);
  font-family:-apple-system,BlinkMacSystemFont,"Inter",sans-serif;
}
.aria-sb-dot{
  width:8px;height:8px;border-radius:50%;background:var(--s);
  box-shadow:0 0 0 0 var(--s);
  animation:sb-dot-pulse 1.4s ease-in-out infinite;
}
@keyframes sb-dot-pulse{
  0%,100%{box-shadow:0 0 0 0 var(--s);opacity:1;}
  50%    {box-shadow:0 0 0 6px transparent;opacity:0.75;}
}
.aria-sb-label{
  font-size:0.68rem;font-weight:800;letter-spacing:0.1em;
  color:var(--s);flex:1;
}
.aria-sb-badge{
  background:var(--s);color:white;
  font-size:0.68rem;font-weight:800;
  padding:2px 8px;border-radius:10px;
  min-width:22px;text-align:center;
  box-shadow:0 2px 6px rgba(0,0,0,0.25);
}

/* Animated page nav links (both auto-nav and manual page_link) */
[data-testid="stSidebar"] a[data-testid="stSidebarNavLink"],
[data-testid="stSidebar"] [data-testid="stPageLink"] a,
[data-testid="stSidebar"] .stPageLink a{
  border-radius:8px;
  transition:background 0.2s,transform 0.2s,padding-left 0.2s;
  position:relative;
}
[data-testid="stSidebar"] a[data-testid="stSidebarNavLink"]:hover,
[data-testid="stSidebar"] [data-testid="stPageLink"] a:hover,
[data-testid="stSidebar"] .stPageLink a:hover{
  background:linear-gradient(90deg,rgba(15,118,110,0.09),transparent);
  transform:translateX(3px);
  padding-left:calc(1rem + 2px);
}

/* ── Rebrand the landing-page auto-nav link "copilot" → "🛡️ ARIA Home" ── */
/* Streamlit gives the landing <span> label="copilot"; we kill that text */
/* and replace with our own via ::before on the anchor. */
[data-testid="stSidebar"] a[data-testid="stSidebarNavLink"]:has(span[label="copilot"]){
  background:linear-gradient(90deg,rgba(15,118,110,0.12),rgba(8,145,178,0.04))!important;
  border-left:3px solid #0f766e;
  margin-bottom:6px;
  animation:aria-nav-glow 2.6s ease-in-out infinite;
}
[data-testid="stSidebar"] a[data-testid="stSidebarNavLink"]:has(span[label="copilot"]) span[label="copilot"]{
  font-size:0!important;                    /* hide original "copilot" */
  display:inline-flex;align-items:center;
}
[data-testid="stSidebar"] a[data-testid="stSidebarNavLink"]:has(span[label="copilot"]) span[label="copilot"]::before{
  content:"🛡️  ARIA Home";
  font-size:0.96rem;
  font-weight:800;
  color:#0f766e;
  letter-spacing:0.01em;
}
/* Tiny green "live" dot on the right of the ARIA Home link */
[data-testid="stSidebar"] a[data-testid="stSidebarNavLink"]:has(span[label="copilot"])::after{
  content:"";
  position:absolute;top:50%;right:12px;transform:translateY(-50%);
  width:7px;height:7px;border-radius:50%;background:#10b981;
  box-shadow:0 0 0 0 #10b981;
  animation:aria-nav-dot 1.5s ease-in-out infinite;
}
@keyframes aria-nav-glow{
  0%,100%{box-shadow:inset 3px 0 0 0 #0f766e,0 0 0 0 rgba(15,118,110,0);}
  50%    {box-shadow:inset 3px 0 0 0 #0f766e,0 0 14px 0 rgba(15,118,110,0.28);}
}
@keyframes aria-nav-dot{
  0%,100%{box-shadow:0 0 0 0 rgba(16,185,129,0.55);}
  50%    {box-shadow:0 0 0 5px rgba(16,185,129,0);}
}

/* ── Radio (map view toggle) ──────────────────────────────────────────── */
[data-testid="stRadio"] label{
  transition:transform 0.15s,color 0.15s;
}
[data-testid="stRadio"] label:hover{transform:translateY(-1px);}

/* ── Divider ──────────────────────────────────────────────────────────── */
hr{
  border:none;height:1px;margin:18px 0;
  background:linear-gradient(90deg,transparent,#ccfbf1 20%,#0f766e44 50%,#ccfbf1 80%,transparent);
  animation:slide-in 0.5s ease-out;
}

/* ── HIGHLIGHT PANEL — the hero of the page ───────────────────────────── */
.highlight-panel{
  background:linear-gradient(135deg,#0f172a 0%,#1e293b 50%,#0f766e 100%);
  background-size:200% 200%;animation:panel-shift 12s ease-in-out infinite;
  border-radius:20px;padding:22px 22px 18px;margin:6px 0 16px;
  color:white;box-shadow:0 14px 40px rgba(15,23,42,0.35);
  position:relative;overflow:hidden;
  animation:panel-enter 0.6s cubic-bezier(0.34,1.56,0.64,1) both,panel-shift 12s ease-in-out infinite;
}
.highlight-panel::before{
  content:"";position:absolute;inset:0;
  background:radial-gradient(at 80% 0%,rgba(103,232,249,0.25),transparent 50%),
             radial-gradient(at 0% 100%,rgba(16,185,129,0.18),transparent 50%);
  pointer-events:none;
}
@keyframes panel-shift{0%,100%{background-position:0% 50%;}50%{background-position:100% 50%;}}
@keyframes panel-enter{0%{opacity:0;transform:translateY(18px) scale(0.98);}100%{opacity:1;transform:translateY(0) scale(1);}}

.hero-caption{
  font-size:0.78rem;font-weight:700;letter-spacing:0.14em;text-transform:uppercase;
  color:rgba(255,255,255,0.7);margin-bottom:14px;text-align:center;
}

/* Before vs After comparison */
.compare-grid{
  display:grid;grid-template-columns:1fr auto 1fr;gap:12px;align-items:center;
  margin-bottom:18px;position:relative;z-index:1;
}
.compare-col{padding:12px 10px;border-radius:12px;text-align:center;}
.baseline-col{background:rgba(255,255,255,0.05);border:1px solid rgba(255,255,255,0.1);}
.aria-col{
  background:linear-gradient(135deg,rgba(20,184,166,0.25),rgba(8,145,178,0.25));
  border:1px solid rgba(103,232,249,0.35);
  box-shadow:inset 0 0 20px rgba(103,232,249,0.1);
}
.compare-label{
  font-size:0.7rem;font-weight:700;letter-spacing:0.1em;
  color:rgba(255,255,255,0.65);margin-bottom:6px;
}
.compare-value{
  font-size:2rem;font-weight:900;line-height:1;
  font-variant-numeric:tabular-nums;
}
.baseline-val{color:#fca5a5;}
.aria-val{color:#67e8f9;}
.compare-unit{font-size:0.95rem;font-weight:600;margin-left:4px;color:rgba(255,255,255,0.55);}
.compare-sub{
  font-size:0.75rem;color:rgba(255,255,255,0.6);margin-top:6px;
}
.compare-arrow{display:flex;justify-content:center;}
.arrow-badge{
  color:white;font-weight:900;font-size:0.88rem;
  padding:6px 10px;border-radius:12px;white-space:nowrap;
  box-shadow:0 3px 10px rgba(0,0,0,0.25);
  animation:arrow-glow 2s ease-in-out infinite;
}
@keyframes arrow-glow{0%,100%{box-shadow:0 3px 10px rgba(16,185,129,0.3);}50%{box-shadow:0 3px 20px rgba(16,185,129,0.7);}}

/* Hero stats row (under the compare) */
.hero-stats-row{
  display:grid;grid-template-columns:repeat(4,1fr);gap:10px;
  padding-top:14px;border-top:1px solid rgba(255,255,255,0.1);
  position:relative;z-index:1;
}
.hero-stat{
  text-align:center;padding:6px 4px;border-radius:10px;
  transition:transform 0.2s,background 0.2s;
}
.hero-stat:hover{transform:translateY(-2px);background:rgba(255,255,255,0.06);}
.hero-stat-icon{font-size:1.15rem;margin-bottom:2px;}
.hero-stat-val{
  font-size:1.25rem;font-weight:900;color:white;
  font-variant-numeric:tabular-nums;line-height:1.1;
}
.hero-stat-lbl{
  font-size:0.7rem;color:rgba(255,255,255,0.65);
  letter-spacing:0.04em;margin-top:2px;
}
.flagged-stat .hero-stat-val{color:#fca5a5;}

@media(max-width:600px){
  .compare-grid{grid-template-columns:1fr;gap:8px;}
  .compare-arrow{transform:rotate(90deg);padding:2px 0;}
  .hero-stats-row{grid-template-columns:repeat(2,1fr);}
  .compare-value{font-size:1.7rem;}
}

/* ── Map frame — glow around the map ──────────────────────────────────── */
.map-frame{
  border-radius:16px;padding:4px;
  background:linear-gradient(135deg,#0f766e,#0891b2,#6366f1,#0f766e);
  background-size:300% 300%;
  animation:frame-shift 9s ease-in-out infinite;
  box-shadow:0 8px 32px rgba(15,118,110,0.25);
  margin-top:8px;
}
.map-frame>iframe,.map-frame>div{
  border-radius:13px;overflow:hidden;
}
@keyframes frame-shift{0%,100%{background-position:0% 50%;}50%{background-position:100% 50%;}}

/* ── Per-route breakdown cards ────────────────────────────────────────── */
.route-breakdown{
  display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));
  gap:10px;margin-top:14px;
}
.route-card{
  background:white;border:1px solid #e2e8f0;border-left:4px solid #0f766e;
  border-radius:10px;padding:10px 12px;
  box-shadow:0 2px 8px rgba(15,23,42,0.06);
  transition:transform 0.2s,box-shadow 0.2s;
  animation:slide-in 0.4s ease-out both;
}
.route-card:hover{transform:translateY(-2px);box-shadow:0 6px 18px rgba(15,23,42,0.12);}
.route-card-top{display:flex;align-items:center;gap:8px;margin-bottom:4px;}
.route-dot{width:10px;height:10px;border-radius:50%;flex-shrink:0;box-shadow:0 0 6px currentColor;}
.route-driver{font-weight:800;font-size:0.88rem;color:#0f172a;}
.route-vehicle{font-size:0.75rem;color:#64748b;margin-left:auto;}
.route-card-stats{font-size:0.82rem;color:#475569;}
.route-stops b{color:#0f766e;font-size:0.95rem;}

/* ── Nav cards (deep-dive links on main page) ─────────────────────────── */
.nav-card-grid{
  display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:12px;margin-top:10px;
}
.nav-card{
  background:white;border:1px solid #e2e8f0;border-radius:14px;padding:16px;
  box-shadow:0 3px 12px rgba(15,23,42,0.06);
  transition:transform 0.25s,box-shadow 0.25s;
  animation:slide-in 0.4s ease-out both;
  position:relative;overflow:hidden;cursor:pointer;
}
.nav-card::before{
  content:"";position:absolute;top:0;left:0;right:0;height:3px;
}
.nav-card-fleet::before{background:linear-gradient(90deg,#0f766e,#0891b2);}
.nav-card-score::before{background:linear-gradient(90deg,#6366f1,#8b5cf6);}
.nav-card-audit::before{background:linear-gradient(90deg,#dc2626,#ea580c);}
.nav-card:hover{transform:translateY(-3px);box-shadow:0 10px 26px rgba(15,118,110,0.16);}
.nav-card-icon{font-size:1.6rem;margin-bottom:6px;animation:icon-float 3s ease-in-out infinite;}
.nav-card-title{font-weight:800;color:#0f172a;font-size:1rem;margin-bottom:2px;}
.nav-card-sub{color:#64748b;font-size:0.82rem;line-height:1.4;}

/* ── "Fixes applied — see Plan above" nudge in the Attention section ──── */
.attn-nudge{
  background:linear-gradient(90deg,#ecfdf5,#f0fdfa);
  border:1px solid #86efac;border-left:3px solid #10b981;
  color:#065f46;padding:9px 14px;border-radius:10px;
  margin:6px 0 12px;font-size:0.88rem;font-weight:600;
  animation:slide-in 0.4s ease-out;
}
.attn-nudge a{color:#047857;text-decoration:none;font-weight:700;}
.attn-nudge a:hover{text-decoration:underline;}

/* ── Login gate ───────────────────────────────────────────────────────── */
.login-card{
  text-align:center;padding:46px 24px 32px;margin:30px auto 22px;max-width:540px;
  background:linear-gradient(135deg,#f0fdfa 0%,#ecfeff 50%,#f0f9ff 100%);
  border:1.5px solid #99f6e4;border-radius:20px;
  box-shadow:0 12px 40px rgba(15,118,110,0.15);
  animation:splash-fade 0.4s ease-out;
}
.login-shield{
  font-size:3.6rem;line-height:1;
  filter:drop-shadow(0 6px 20px rgba(15,118,110,0.4));
  animation:splash-bounce 1.6s ease-in-out infinite;
}
.login-title{
  font-size:1.95rem;font-weight:900;color:#0f172a;
  letter-spacing:-0.025em;margin-top:14px;
}
.login-sub{
  color:#0f766e;font-size:0.86rem;font-weight:700;
  letter-spacing:0.04em;margin-top:4px;
}
.login-q{
  color:#475569;font-size:1rem;font-weight:600;
  margin:24px 0 14px;
}

/* ── Role chip in sidebar ─────────────────────────────────────────────── */
.role-chip{
  display:flex;align-items:center;gap:10px;
  margin:-1rem -1rem 8px -1rem;padding:10px 14px;
  background:linear-gradient(90deg,rgba(15,118,110,0.14),rgba(8,145,178,0.06));
  border-bottom:1px solid rgba(15,118,110,0.18);
}
.role-chip-icon{
  width:34px;height:34px;border-radius:10px;
  background:linear-gradient(135deg,#0f766e,#0891b2);
  color:white;font-size:1.05rem;
  display:flex;align-items:center;justify-content:center;flex-shrink:0;
  box-shadow:0 3px 10px rgba(15,118,110,0.35);
}
.role-chip-text{flex:1;min-width:0;}
.role-chip-label{font-weight:800;color:#0f172a;font-size:0.88rem;line-height:1.1;}
.role-chip-sub{
  font-size:0.62rem;font-weight:800;color:#0f766e;
  letter-spacing:0.14em;margin-top:2px;
}

/* ── Risk Snapshot — % of raw risk cleared; replaces 0/100 safety score ── */
.risk-snap{
  background:white;border:1px solid #e2e8f0;border-radius:14px;
  padding:14px 18px;margin:6px 0 18px;
  box-shadow:0 3px 12px rgba(15,23,42,0.06);
  animation:slide-in 0.4s ease-out;
}
.risk-snap-row{
  display:flex;justify-content:space-between;align-items:flex-start;
  gap:14px;margin-bottom:10px;
}
.risk-snap-label{
  font-size:0.7rem;font-weight:800;letter-spacing:0.14em;color:#475569;
  margin-bottom:2px;
}
.risk-snap-headline{
  font-size:1.05rem;font-weight:800;line-height:1.25;letter-spacing:-0.01em;
}
.risk-snap-sub{
  font-size:0.84rem;color:#64748b;margin-top:3px;
}
.risk-snap-pct{
  font-size:2rem;font-weight:900;line-height:1;
  font-variant-numeric:tabular-nums;flex-shrink:0;
}
.risk-snap-pct span{
  font-size:1rem;color:#94a3b8;font-weight:700;margin-left:2px;
}
.risk-snap-bar{
  width:100%;height:8px;background:#f1f5f9;border-radius:4px;overflow:hidden;
}
.risk-snap-fill{
  height:100%;border-radius:4px;
  animation:cap-grow 1s cubic-bezier(0.4,0,0.2,1) both;
}
.risk-snap-foot{
  display:flex;justify-content:space-between;
  font-size:0.74rem;color:#64748b;margin-top:6px;
}
.risk-snap-foot-label{font-weight:600;}
.risk-snap-foot-stat{color:#94a3b8;font-variant-numeric:tabular-nums;}

/* ── First-paint splash / skeleton ────────────────────────────────────── */
.app-splash{
  display:flex;flex-direction:column;align-items:center;justify-content:center;
  padding:54px 24px;margin:10px 0;
  background:linear-gradient(135deg,#f0fdfa 0%,#ecfeff 50%,#f0f9ff 100%);
  border:1.5px solid #99f6e4;border-radius:18px;
  box-shadow:0 6px 22px rgba(15,118,110,0.1);
  animation:splash-fade 0.25s ease-out;
}
@keyframes splash-fade{from{opacity:0;transform:translateY(6px);}to{opacity:1;transform:translateY(0);}}

.splash-shield{
  font-size:3.2rem;line-height:1;
  filter:drop-shadow(0 6px 18px rgba(15,118,110,0.35));
  animation:splash-bounce 1.5s ease-in-out infinite;
}
@keyframes splash-bounce{
  0%,100%{transform:translateY(0) scale(1);}
  50%    {transform:translateY(-10px) scale(1.06);}
}

.splash-title{
  font-size:1.65rem;font-weight:900;color:#0f172a;
  letter-spacing:-0.02em;margin-top:14px;
}
.splash-sub{
  color:#64748b;font-size:0.92rem;margin-top:4px;margin-bottom:22px;
  font-weight:500;
}

/* Indeterminate progress bar — slides a glowing chunk back and forth */
.splash-bar{
  width:220px;height:4px;background:#cbd5e1;border-radius:3px;overflow:hidden;
  position:relative;
}
.splash-bar::after{
  content:"";position:absolute;top:0;left:0;height:100%;width:45%;
  background:linear-gradient(90deg,#0f766e,#0891b2,#67e8f9);
  border-radius:3px;
  animation:splash-bar-slide 1.3s cubic-bezier(0.4,0,0.2,1) infinite;
  box-shadow:0 0 10px rgba(15,118,110,0.5);
}
@keyframes splash-bar-slide{
  0%  {left:-45%;}
  100%{left:100%;}
}

/* Fake paragraph skeleton rows underneath — hints at the briefing shape */
.splash-skel-wrap{
  display:flex;flex-direction:column;align-items:center;gap:9px;
  margin-top:26px;width:100%;max-width:480px;
}
.splash-skel-row{
  height:12px;border-radius:6px;
  background:linear-gradient(90deg,#e2e8f0 0%,#f1f5f9 50%,#e2e8f0 100%);
  background-size:200% 100%;
  animation:skel-shimmer 1.6s ease-in-out infinite;
}
@keyframes skel-shimmer{
  0%  {background-position:200% 0;}
  100%{background-position:-200% 0;}
}

/* ── Spinner (re-optimizing) ──────────────────────────────────────────── */
[data-testid="stSpinner"]>div{
  border-top-color:#0f766e!important;
}

</style>""", unsafe_allow_html=True)
