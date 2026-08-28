from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

BG = "#050d16"
SURFACE = "#0b1724"
SURFACE_2 = "#102131"
BORDER = "rgba(255, 255, 255, 0.085)"
TEXT = "#f6f0e8"
MUTED = "#93a5b7"
ACCENT = "#e58a3a"
ACCENT_SOFT = "#f3b56f"
SUCCESS = "#55c98b"
GRID = "rgba(148, 163, 184, 0.105)"


def apply_theme() -> None:
    """Applique le design system sombre/cognac de RhumLog."""
    css = """
<style>
:root {
  --rhum-bg: __BG__;
  --rhum-surface: __SURFACE__;
  --rhum-surface-2: __SURFACE_2__;
  --rhum-border: __BORDER__;
  --rhum-text: __TEXT__;
  --rhum-muted: __MUTED__;
  --rhum-accent: __ACCENT__;
  --rhum-accent-soft: __ACCENT_SOFT__;
  --rhum-success: __SUCCESS__;
  --rhum-shadow: 0 20px 55px rgba(0,0,0,.24);
  --rhum-inner: inset 0 1px 0 rgba(255,255,255,.035);
}

html, body, [class*="css"] {
  font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}

html, body { background:#050d16; }

.stApp {
  background:
    radial-gradient(circle at 78% -14%, rgba(229,138,58,.12), transparent 29%),
    radial-gradient(circle at 17% 15%, rgba(30,86,124,.13), transparent 27%),
    radial-gradient(circle at 100% 65%, rgba(86,47,30,.07), transparent 32%),
    linear-gradient(180deg, #050d16 0%, #07121e 48%, #050d16 100%);
  color:var(--rhum-text);
}

[data-testid="stHeader"] {
  background:transparent !important;
  border:0;
}
[data-testid="stDecoration"] { display:none; }
[data-testid="stToolbar"] {
  margin:.45rem .7rem 0 0;
  padding:.18rem .28rem;
  border:1px solid rgba(255,255,255,.065);
  border-radius:12px;
  background:rgba(7,17,28,.58);
  backdrop-filter:blur(18px) saturate(130%);
  box-shadow:0 10px 28px rgba(0,0,0,.20);
}
[data-testid="stAppViewBlockContainer"] {
  padding-top:1.5rem;
  padding-bottom:4.5rem;
  max-width:1480px;
}

[data-testid="stSidebar"] {
  background:
    radial-gradient(circle at 18% 0%, rgba(229,138,58,.075), transparent 24%),
    linear-gradient(180deg, rgba(9,20,32,.995), rgba(6,15,25,.995));
  border-right:1px solid rgba(255,255,255,.07);
  box-shadow:16px 0 45px rgba(0,0,0,.18);
}
[data-testid="stSidebar"]::after {
  content:"";
  position:absolute;
  top:0;
  right:0;
  width:1px;
  height:100%;
  background:linear-gradient(180deg, transparent, rgba(229,138,58,.18) 23%, rgba(255,255,255,.05) 62%, transparent);
  pointer-events:none;
}
[data-testid="stSidebarContent"] { padding-top:1.05rem; }
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p { color:#c8d3dd; }

.rhum-brand {
  display:flex;
  align-items:center;
  gap:.72rem;
  padding:.32rem .2rem 1rem .2rem;
}
.rhum-brand-mark {
  flex:0 0 42px;
  width:42px;
  height:42px;
  display:grid;
  place-items:center;
  border-radius:14px;
  color:var(--rhum-accent-soft);
  border:1px solid rgba(229,138,58,.28);
  background:
    radial-gradient(circle at 36% 24%, rgba(255,255,255,.09), transparent 32%),
    linear-gradient(145deg, rgba(229,138,58,.12), rgba(229,138,58,.035));
  box-shadow:0 8px 26px rgba(229,138,58,.08), var(--rhum-inner);
}
.rhum-brand-mark svg { filter:drop-shadow(0 3px 10px rgba(229,138,58,.22)); }
.rhum-brand-copy { min-width:0; }
.rhum-brand-name {
  font-family:Georgia, "Times New Roman", serif;
  font-size:1.72rem;
  letter-spacing:.045em;
  color:#f7f0e8;
  line-height:1;
  text-transform:uppercase;
}
.rhum-brand-name span { color:var(--rhum-accent-soft); }
.rhum-brand-tag {
  color:var(--rhum-accent);
  font-size:.60rem;
  letter-spacing:.19em;
  text-transform:uppercase;
  margin-top:.43rem;
  white-space:nowrap;
}
.rhum-nav-section {
  margin:.95rem 0 .3rem;
  padding-left:.08rem;
  color:#6f8194;
  font-size:.63rem;
  font-weight:800;
  letter-spacing:.16em;
  text-transform:uppercase;
}

h1,h2,h3 { color:var(--rhum-text); letter-spacing:-.02em; }
h1 { font-family:Georgia, "Times New Roman", serif; }

.rhum-hero {
  position:relative;
  overflow:hidden;
  border:1px solid rgba(255,255,255,.075);
  border-radius:22px;
  padding:1.38rem 1.62rem;
  margin-bottom:1.18rem;
  background:
    linear-gradient(115deg, rgba(13,29,44,.97), rgba(7,18,30,.93)),
    radial-gradient(circle at 90% 20%, rgba(229,138,58,.18), transparent 30%);
  box-shadow:var(--rhum-shadow), var(--rhum-inner);
}
.rhum-hero::before {
  content:"";
  position:absolute;
  inset:0;
  pointer-events:none;
  background:
    radial-gradient(circle at 91% 15%, rgba(229,138,58,.18), transparent 22%),
    linear-gradient(90deg, transparent 0%, transparent 66%, rgba(255,255,255,.018) 100%);
}
.rhum-hero::after {
  content:"";
  position:absolute;
  left:0;
  top:0;
  bottom:0;
  width:2px;
  background:linear-gradient(180deg, transparent, var(--rhum-accent), transparent);
  opacity:.75;
}
.rhum-hero-orbit {
  position:absolute;
  right:4.5%;
  top:50%;
  width:150px;
  height:150px;
  transform:translateY(-50%);
  border:1px solid rgba(229,138,58,.10);
  border-radius:50%;
  box-shadow:0 0 0 24px rgba(229,138,58,.025),0 0 0 48px rgba(229,138,58,.012);
  opacity:.75;
}
.rhum-kicker {
  position:relative;
  z-index:1;
  color:var(--rhum-accent);
  font-size:.69rem;
  letter-spacing:.175em;
  text-transform:uppercase;
  font-weight:850;
}
.rhum-hero h1 {
  position:relative;
  z-index:1;
  margin:.2rem 0 .16rem;
  font-size:clamp(2rem,4vw,3.2rem);
  line-height:1.02;
  text-shadow:0 8px 24px rgba(0,0,0,.20);
}
.rhum-hero h1 span { color:var(--rhum-accent-soft); }
.rhum-hero p {
  position:relative;
  z-index:1;
  color:#aebdca;
  margin:.24rem 0 0;
  font-size:.94rem;
  line-height:1.55;
  max-width:980px;
}

.rhum-section-title {
  display:flex;
  align-items:center;
  gap:.58rem;
  margin:.55rem 0 .82rem;
  color:#f4eee7;
  font-size:1.02rem;
  font-weight:760;
}
.rhum-section-icon {
  width:28px;
  height:28px;
  display:grid;
  place-items:center;
  color:var(--rhum-accent-soft);
  border:1px solid rgba(229,138,58,.22);
  border-radius:9px;
  background:linear-gradient(145deg, rgba(229,138,58,.10), rgba(229,138,58,.035));
  box-shadow:0 6px 18px rgba(0,0,0,.12), var(--rhum-inner);
}

[data-testid="stMetric"] {
  position:relative;
  overflow:hidden;
  min-height:96px;
  background:linear-gradient(150deg, rgba(16,31,46,.95), rgba(9,20,32,.94));
  border:1px solid rgba(255,255,255,.075);
  border-radius:16px;
  padding:1rem 1.05rem;
  box-shadow:0 14px 32px rgba(0,0,0,.14), var(--rhum-inner);
}
[data-testid="stMetric"]::before {
  content:"";
  position:absolute;
  width:70px;
  height:70px;
  border-radius:50%;
  right:-28px;
  top:-34px;
  background:radial-gradient(circle, rgba(229,138,58,.11), transparent 68%);
}
[data-testid="stMetricLabel"] { color:#9fb0c0; min-height:2.35em; align-items:flex-start; }
[data-testid="stMetricLabel"] p {
  font-size:.73rem;
  font-weight:700;
  letter-spacing:.025em;
  line-height:1.24;
  white-space:normal !important;
  overflow:visible !important;
  text-overflow:clip !important;
  overflow-wrap:normal !important;
  word-break:normal !important;
  hyphens:none !important;
}
[data-testid="stMetricValue"] { color:#f8f4ee; font-family:Georgia, "Times New Roman", serif; font-size:1.58rem; }
[data-testid="stMetricDelta"] { color:var(--rhum-accent-soft); }

[data-testid="stVerticalBlockBorderWrapper"] {
  position:relative;
  overflow:hidden;
  border:1px solid rgba(255,255,255,.075) !important;
  background:linear-gradient(145deg, rgba(13,27,42,.94), rgba(8,19,31,.93)) !important;
  border-radius:18px !important;
  box-shadow:0 16px 38px rgba(0,0,0,.15), var(--rhum-inner);
  transition:border-color .18s ease, transform .18s ease, box-shadow .18s ease;
}
[data-testid="stVerticalBlockBorderWrapper"]::before {
  content:"";
  position:absolute;
  inset:0 0 auto 0;
  height:1px;
  background:linear-gradient(90deg, transparent, rgba(229,138,58,.18), rgba(255,255,255,.05), transparent);
  pointer-events:none;
}
[data-testid="stVerticalBlockBorderWrapper"]:hover {
  border-color:rgba(229,138,58,.14) !important;
  box-shadow:0 20px 44px rgba(0,0,0,.19), var(--rhum-inner);
}

.rhum-insight {
  display:flex;
  align-items:flex-start;
  gap:.72rem;
  padding:.88rem .95rem;
  border:1px solid rgba(255,255,255,.07);
  border-radius:13px;
  background:linear-gradient(135deg, rgba(255,255,255,.026), rgba(255,255,255,.014));
  margin-bottom:.55rem;
  box-shadow:var(--rhum-inner);
}
.rhum-insight-icon {
  flex:0 0 34px;
  width:34px;
  height:34px;
  display:grid;
  place-items:center;
  color:var(--rhum-accent-soft);
  border:1px solid rgba(229,138,58,.2);
  border-radius:11px;
  background:rgba(229,138,58,.065);
}
.rhum-insight-copy { min-width:0; }
.rhum-insight-title { color:#f6f0e8; font-weight:760; font-size:.91rem; }
.rhum-insight-body { color:#9fb0c0; font-size:.82rem; line-height:1.43; margin-top:.18rem; }
.rhum-insight-meta { color:var(--rhum-accent-soft); font-size:.74rem; margin-top:.35rem; }

.rhum-mini-stat { padding:.78rem .9rem; border-top:1px solid rgba(255,255,255,.08); }
.rhum-mini-stat .value { font-size:1.35rem;font-family:Georgia,serif;color:#f8f4ee; }
.rhum-mini-stat .label { font-size:.75rem;color:#899aaa;text-transform:uppercase;letter-spacing:.08em; }

.rhum-chip {
  display:inline-flex;
  align-items:center;
  gap:.3rem;
  padding:.24rem .52rem;
  margin-bottom:.48rem;
  border-radius:999px;
  border:1px solid rgba(255,255,255,.10);
  background:rgba(255,255,255,.035);
  color:#b7c5d2;
  font-size:.69rem;
  font-weight:750;
  letter-spacing:.035em;
  box-shadow:var(--rhum-inner);
}
.rhum-chip-owned { border-color:rgba(85,201,139,.28); color:#83dca9; background:rgba(85,201,139,.07); }
.rhum-chip-wishlist { border-color:rgba(229,138,58,.28); color:#f3b56f; background:rgba(229,138,58,.07); }
.rhum-chip-tasted { border-color:rgba(90,169,214,.30); color:#8bc6e8; background:rgba(90,169,214,.07); }
.rhum-chip-finished { color:#9aaabc; }

.rhum-card-title {
  min-height:3.05rem;
  color:#f7f2eb;
  font-family:Georgia, "Times New Roman", serif;
  font-weight:700;
  font-size:1.02rem;
  line-height:1.22;
  margin:.05rem 0 .15rem;
}
.rhum-card-meta { min-height:2.2rem;color:#8fa2b3;font-size:.76rem;line-height:1.35;margin-bottom:.45rem; }
.rhum-detail-title { color:#f7f2eb;font-family:Georgia,"Times New Roman",serif;font-size:clamp(1.8rem,3vw,2.7rem);line-height:1.05;margin:.15rem 0 .25rem; }
.rhum-detail-sub { color:#91a4b5;font-size:.9rem;margin-bottom:.65rem; }
.rhum-detail-note { color:#c5d0da;line-height:1.55;font-size:.88rem; }
.rhum-reco-rank { color:var(--rhum-accent);font-size:.68rem;font-weight:800;letter-spacing:.14em;text-transform:uppercase; }
.rhum-reco-name { min-height:3rem;color:#f7f2eb;font-family:Georgia,"Times New Roman",serif;font-size:1.08rem;line-height:1.2;margin:.18rem 0 .45rem; }
.rhum-reco-score { color:var(--rhum-accent-soft);font-family:Georgia,"Times New Roman",serif;font-size:2.05rem;line-height:1;margin:.15rem 0; }
.rhum-reco-sub { color:#8fa2b3;font-size:.75rem;line-height:1.45; }

.rhum-flow-card { min-height:154px;padding:.9rem .85rem;border:1px solid rgba(255,255,255,.07);border-radius:15px;background:linear-gradient(145deg,rgba(15,29,44,.92),rgba(9,19,31,.88));box-shadow:var(--rhum-inner); }
.rhum-flow-number { color:var(--rhum-accent);font-size:.66rem;letter-spacing:.14em;font-weight:800; }
.rhum-flow-title { color:#f5efe7;font-family:Georgia,"Times New Roman",serif;font-weight:700;font-size:1rem;margin:.32rem 0 .34rem; }
.rhum-flow-body { color:#91a4b5;font-size:.76rem;line-height:1.42; }
.rhum-architecture { padding:.35rem .15rem;text-align:center; }
.rhum-arch-node { display:flex;flex-direction:column;gap:.25rem;padding:.8rem 1rem;border:1px solid rgba(229,138,58,.18);background:rgba(229,138,58,.045);border-radius:13px;color:#f4eee7;box-shadow:var(--rhum-inner); }
.rhum-arch-node span { color:#91a4b5;font-size:.78rem; }
.rhum-arch-arrow { color:var(--rhum-accent);font-size:1.25rem;line-height:1.5; }
.rhum-arch-split { display:grid;grid-template-columns:1fr 1fr;gap:.7rem; }
.rhum-health-grid { display:grid;grid-template-columns:repeat(3,1fr);gap:.7rem; }
.rhum-health-card { padding:.9rem 1rem;border:1px solid rgba(255,255,255,.07);border-radius:14px;background:linear-gradient(145deg,rgba(255,255,255,.025),rgba(255,255,255,.012));box-shadow:var(--rhum-inner); }
.rhum-health-label { color:#899aaa;font-size:.68rem;text-transform:uppercase;letter-spacing:.1em; }
.rhum-health-value { color:#f6efe7;font-family:Georgia,serif;font-size:1.45rem;margin:.15rem 0; }
.rhum-health-note { color:#91a4b5;font-size:.75rem;line-height:1.4; }

.rhum-mode-pill {
  display:inline-flex;
  align-items:center;
  gap:.42rem;
  margin:.08rem 0 .52rem;
  padding:.38rem .62rem;
  border-radius:999px;
  border:1px solid rgba(255,255,255,.075);
  background:linear-gradient(90deg,rgba(255,255,255,.03),rgba(255,255,255,.015));
  color:#aebdca;
  font-size:.71rem;
  font-weight:700;
  box-shadow:var(--rhum-inner);
}
.rhum-mode-dot { width:7px;height:7px;border-radius:50%;background:var(--rhum-success);box-shadow:0 0 0 4px rgba(85,201,139,.10),0 0 18px rgba(85,201,139,.18); }
.rhum-mode-dot.demo { background:#5aa9d6;box-shadow:0 0 0 4px rgba(90,169,214,.10),0 0 18px rgba(90,169,214,.18); }

.stButton > button,.stDownloadButton > button {
  border-radius:10px;
  border:1px solid rgba(229,138,58,.24);
  background:linear-gradient(180deg,rgba(255,255,255,.025),rgba(255,255,255,.01));
  box-shadow:var(--rhum-inner);
  transition:transform .16s ease,border-color .16s ease,background .16s ease,box-shadow .16s ease;
}
.stButton > button:hover,.stDownloadButton > button:hover { transform:translateY(-1px);border-color:rgba(229,138,58,.42);box-shadow:0 8px 20px rgba(0,0,0,.13),var(--rhum-inner); }
.stButton > button[kind="primary"] { background:linear-gradient(100deg,#d97a31,#efa254);color:#101820;border:0;font-weight:800;box-shadow:0 9px 22px rgba(229,138,58,.17); }

[data-testid="stSidebar"] .stButton > button {
  min-height:2.34rem;
  justify-content:flex-start;
  padding:.37rem .68rem;
  border-color:transparent;
  background:transparent;
  color:#aebdca;
  font-weight:650;
  box-shadow:none;
}
[data-testid="stSidebar"] .stButton > button:hover { border-color:rgba(229,138,58,.14);background:rgba(229,138,58,.05);color:#f5efe7; }
[data-testid="stSidebar"] .stButton > button[kind="primary"] {
  background:linear-gradient(90deg,rgba(229,138,58,.19),rgba(229,138,58,.055));
  color:#f8f0e6;
  border:1px solid rgba(229,138,58,.24);
  box-shadow:inset 3px 0 0 rgba(229,138,58,.72),var(--rhum-inner);
}

[data-baseweb="tab-list"] {
  gap:.24rem;
  background:rgba(255,255,255,.022);
  border:1px solid rgba(255,255,255,.05);
  border-radius:12px;
  padding:.2rem;
  margin-bottom:.75rem;
  overflow-x:auto;
  scrollbar-width:thin;
  box-shadow:var(--rhum-inner);
}
[data-baseweb="tab"] { border-radius:9px;padding:.48rem .75rem;color:#96a8b8; }
[data-baseweb="tab"][aria-selected="true"] { background:linear-gradient(180deg,rgba(229,138,58,.12),rgba(229,138,58,.065));color:#f5efe7;box-shadow:var(--rhum-inner); }

[data-testid="stTextInput"] input,
[data-testid="stNumberInput"] input,
[data-baseweb="select"] > div,
[data-testid="stTextArea"] textarea {
  background:rgba(255,255,255,.03) !important;
  border-color:rgba(255,255,255,.075) !important;
  color:#f4eee7 !important;
  box-shadow:var(--rhum-inner);
}
[data-testid="stTextInput"] input:focus,
[data-testid="stNumberInput"] input:focus,
[data-testid="stTextArea"] textarea:focus { border-color:rgba(229,138,58,.42) !important;box-shadow:0 0 0 1px rgba(229,138,58,.15) !important; }

[data-testid="stExpander"] { border:1px solid rgba(255,255,255,.06) !important;border-radius:12px !important;background:rgba(255,255,255,.016);box-shadow:var(--rhum-inner); }
[data-testid="stAlert"] { border-radius:12px;border:1px solid rgba(255,255,255,.065);box-shadow:var(--rhum-inner); }
[data-testid="stProgress"] > div > div { background:rgba(255,255,255,.055) !important; }
[data-testid="stProgress"] > div > div > div > div { background:linear-gradient(90deg,#d8792f,#eda45b) !important;box-shadow:0 0 14px rgba(229,138,58,.18); }
[data-testid="stDataFrame"] { border:1px solid rgba(255,255,255,.065);border-radius:14px;overflow:hidden;box-shadow:var(--rhum-inner); }

.rhum-filter-summary { color:#91a4b5;font-size:.78rem;margin:.1rem 0 .8rem; }
.rhum-filter-summary b { color:#f2ece5; }
.rhum-empty { display:flex;align-items:flex-start;gap:.7rem;padding:1.15rem 1.2rem;border:1px dashed rgba(255,255,255,.10);border-radius:14px;background:rgba(255,255,255,.016); }
.rhum-empty-icon { flex:0 0 34px;width:34px;height:34px;display:grid;place-items:center;border-radius:11px;color:#8fb7d2;border:1px solid rgba(90,169,214,.18);background:rgba(90,169,214,.06); }
.rhum-empty-title { color:#f4eee7;font-weight:750;margin-bottom:.25rem; }
.rhum-empty-body { color:#91a4b5;font-size:.84rem;line-height:1.48; }
.rhum-footnote { color:#718397;font-size:.72rem;line-height:1.5; }

.rhum-stat-grid {
  display:grid;
  grid-template-columns:repeat(var(--rhum-stat-cols),minmax(0,1fr));
  gap:.72rem;
  margin:.1rem 0 1.08rem;
}
.rhum-stat-card {
  position:relative;
  min-width:0;
  min-height:108px;
  display:flex;
  align-items:center;
  gap:.82rem;
  padding:.86rem .92rem;
  overflow:hidden;
  border:1px solid rgba(255,255,255,.072);
  border-radius:16px;
  background:linear-gradient(150deg,rgba(16,31,46,.94),rgba(9,20,32,.93));
  box-shadow:0 13px 30px rgba(0,0,0,.13),var(--rhum-inner);
}
.rhum-stat-card::after {
  content:"";
  position:absolute;
  width:86px;
  height:86px;
  right:-42px;
  top:-42px;
  border-radius:50%;
  background:radial-gradient(circle,rgba(229,138,58,.09),transparent 68%);
}
.rhum-stat-icon {
  flex:0 0 48px;
  width:48px;
  height:48px;
  display:grid;
  place-items:center;
  color:var(--rhum-accent-soft);
  border-radius:50%;
  border:1px solid rgba(229,138,58,.28);
  background:
    radial-gradient(circle at 32% 24%,rgba(255,255,255,.08),transparent 33%),
    linear-gradient(145deg,rgba(229,138,58,.115),rgba(229,138,58,.035));
  box-shadow:0 8px 20px rgba(0,0,0,.13),var(--rhum-inner);
}
.rhum-stat-copy { min-width:0; }

/* Les grilles de 5–6 KPI conservent leurs colonnes, mais la carte devient
   verticale afin de rendre toute sa largeur au texte. */
.rhum-stat-grid--dense .rhum-stat-card {
  min-height:132px;
  flex-direction:column;
  align-items:flex-start;
  justify-content:center;
  gap:.48rem;
  padding:.76rem .82rem;
}
.rhum-stat-grid--dense .rhum-stat-icon {
  flex:0 0 34px;
  width:34px;
  height:34px;
}
.rhum-stat-grid--dense .rhum-stat-icon svg { width:17px;height:17px; }
.rhum-stat-grid--dense .rhum-stat-copy { width:100%; }
.rhum-stat-grid--dense .rhum-stat-label {
  min-height:2.5em;
  font-size:.62rem;
  line-height:1.25;
  letter-spacing:.052em;
}
.rhum-stat-grid--dense .rhum-stat-value {
  font-size:1.42rem;
  margin:.18rem 0 .08rem;
}
.rhum-stat-grid--dense .rhum-stat-note {
  font-size:.65rem;
  line-height:1.32;
  overflow-wrap:normal;
  word-break:normal;
  hyphens:none;
}
.rhum-stat-label {
  color:#8799aa;
  font-size:.65rem;
  font-weight:800;
  letter-spacing:.065em;
  line-height:1.22;
  text-transform:uppercase;
  white-space:normal;
  overflow:visible;
  text-overflow:clip;
  min-height:2.44em;
  display:flex;
  align-items:flex-start;
  overflow-wrap:normal;
  word-break:normal;
}
.rhum-stat-value {
  color:#f8f3ec;
  font-family:Georgia,"Times New Roman",serif;
  font-size:clamp(1.22rem,1.65vw,1.5rem);
  line-height:1.08;
  margin:.22rem 0 .1rem;
  white-space:nowrap;
  overflow:visible;
  text-overflow:clip;
}
.rhum-stat-note { color:#788b9e;font-size:.67rem;line-height:1.35; }
.rhum-eyebrow { color:#718397;font-size:.66rem;font-weight:800;letter-spacing:.12em;text-transform:uppercase;margin:.15rem 0 .4rem; }
.rhum-card-placeholder { width:78px;height:98px;margin:0 auto;display:flex;align-items:center;justify-content:center;border-radius:12px;border:1px dashed rgba(255,255,255,.09);background:linear-gradient(145deg,rgba(255,255,255,.024),rgba(255,255,255,.01));font-size:1.55rem;filter:saturate(.8);box-shadow:var(--rhum-inner); }
.rhum-score-row { display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:.55rem;margin:.7rem 0 .15rem; }
.rhum-score-cell { padding:.58rem .62rem;border-radius:10px;background:rgba(255,255,255,.02);border:1px solid rgba(255,255,255,.055);box-shadow:var(--rhum-inner); }
.rhum-score-cell b { color:#f4eee7;font-family:Georgia,serif;font-size:1.02rem; }
.rhum-score-cell span { display:block;color:#7f92a5;font-size:.64rem;text-transform:uppercase;letter-spacing:.075em;margin-top:.12rem; }
.rhum-toolbar-note { color:#7d91a4;font-size:.74rem;line-height:1.42;margin-top:.35rem; }

[data-testid="stVerticalBlockBorderWrapper"]:has(.rhum-card-title) { min-height:315px; }
[data-testid="stVerticalBlockBorderWrapper"]:has(.rhum-reco-name) { min-height:305px; }
[data-testid="stVerticalBlockBorderWrapper"]:has(.rhum-card-title) [data-testid="stImage"] img,
[data-testid="stVerticalBlockBorderWrapper"]:has(.rhum-reco-name) [data-testid="stImage"] img { max-height:98px;object-fit:contain;filter:drop-shadow(0 12px 20px rgba(0,0,0,.22)); }
[data-testid="stCaptionContainer"] { color:#7f92a5; }
[data-testid="stSidebar"] hr { margin:.85rem 0 .55rem; }
hr { border-color:rgba(255,255,255,.06); }

/* Scrollbars */
* { scrollbar-width:thin;scrollbar-color:rgba(229,138,58,.28) rgba(255,255,255,.025); }
*::-webkit-scrollbar { width:9px;height:9px; }
*::-webkit-scrollbar-track { background:rgba(255,255,255,.02); }
*::-webkit-scrollbar-thumb { background:linear-gradient(180deg,rgba(229,138,58,.34),rgba(229,138,58,.18));border-radius:999px;border:2px solid transparent;background-clip:padding-box; }

@media (max-width:1320px) and (min-width:1101px) {
  .rhum-stat-grid:not(.rhum-stat-grid--dense) .rhum-stat-card { gap:.62rem;padding:.82rem .74rem; }
  .rhum-stat-grid:not(.rhum-stat-grid--dense) .rhum-stat-icon { flex-basis:42px;width:42px;height:42px; }
  .rhum-stat-grid:not(.rhum-stat-grid--dense) .rhum-stat-label { font-size:.61rem;letter-spacing:.052em; }
  .rhum-stat-grid:not(.rhum-stat-grid--dense) .rhum-stat-note { font-size:.64rem; }
}
@media (max-width:1100px) {
  .rhum-stat-grid { grid-template-columns:repeat(2,minmax(0,1fr)); }
}
@media (max-width:900px) {
  [data-testid="stAppViewBlockContainer"] { padding-left:1rem;padding-right:1rem; }
  .rhum-hero { padding:1.05rem; }
  .rhum-hero-orbit { opacity:.35;right:-25px; }
  .rhum-arch-split,.rhum-health-grid { grid-template-columns:1fr; }
  .rhum-score-row { grid-template-columns:repeat(2,minmax(0,1fr)); }
}
@media (max-width:620px) {
  .rhum-stat-grid { grid-template-columns:1fr; }
  .rhum-stat-value { white-space:normal; }
  .rhum-stat-card { min-height:96px; }
}
</style>
    """
    replacements = {
        "__BG__": BG,
        "__SURFACE__": SURFACE,
        "__SURFACE_2__": SURFACE_2,
        "__BORDER__": BORDER,
        "__TEXT__": TEXT,
        "__MUTED__": MUTED,
        "__ACCENT__": ACCENT,
        "__ACCENT_SOFT__": ACCENT_SOFT,
        "__SUCCESS__": SUCCESS,
    }
    for token, value in replacements.items():
        css = css.replace(token, value)
    st.markdown(css, unsafe_allow_html=True)


def style_figure(fig: go.Figure, *, height: int | None = None, showlegend: bool | None = None) -> go.Figure:
    """Uniformise les graphiques Plotly avec le design system RhumLog."""
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color=TEXT, family="Inter, Arial, sans-serif", size=12),
        title=dict(font=dict(color=TEXT, family="Georgia, Times New Roman, serif", size=16), x=0.02, xanchor="left"),
        margin=dict(l=18, r=18, t=50, b=24),
        hovermode="closest",
        hoverlabel=dict(
            bgcolor="#102131",
            bordercolor="rgba(229,138,58,.72)",
            font_color=TEXT,
            font_family="Inter, Arial, sans-serif",
        ),
        legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(color="#b7c5d2", size=11)),
        colorway=[ACCENT, "#5aa9d6", "#7cc69d", "#b17ce2", "#e2c66b", "#d96b6b"],
    )
    if height is not None:
        fig.update_layout(height=height)
    if showlegend is not None:
        fig.update_layout(showlegend=showlegend)
    fig.update_xaxes(
        gridcolor=GRID,
        zerolinecolor=GRID,
        linecolor="rgba(148,163,184,.14)",
        tickfont=dict(color="#91a4b5"),
        title_font=dict(color="#9fb0c0"),
    )
    fig.update_yaxes(
        gridcolor=GRID,
        zerolinecolor=GRID,
        linecolor="rgba(148,163,184,.14)",
        tickfont=dict(color="#91a4b5"),
        title_font=dict(color="#9fb0c0"),
    )
    return fig
