#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build the 山海错 reader page (v4 — multi-chapter audio, sticky player, sync highlight)."""
import re
import html as html_lib
import json
import unicodedata
from pathlib import Path

SRC  = Path("novels/shanhai-cuo.md")
OUT  = Path("index.html")


# ────────────── 章节音频清单 ──────────────
# 凡是 "## 第N章 ..." 且存在 audio/chN_ts.json + audio/chN.mp3 就算"有声"
# 章节序号 = md 文件里出现顺序（从 0 开始；0 = 序，因为"序"在 md 里也算 ##）

CHAPTERS = []
def collect_chapters():
    chapters = []
    for ts_path in sorted(Path('audio').glob('ch*_ts.json')):
        m = re.match(r'ch(\d+)_ts\.json', ts_path.name)
        if not m: continue
        n = int(m.group(1))
        mp3 = ts_path.parent / f'ch{n}.mp3'
        if not mp3.exists():
            continue
        data = json.loads(ts_path.read_text(encoding='utf-8'))
        if not data:
            continue
        chapters.append({
            'n': n,
            'mp3': f'audio/ch{n}.mp3',
            'preview': f'audio/ch{n}_preview.mp3',
            'text': f'audio/ch{n}.txt',
            'duration': data[-1]['end'],
            'paragraphs': data,
        })
    return sorted(chapters, key=lambda c: c['n'])

CHAPTERS = collect_chapters()
print(f'发现 {len(CHAPTERS)} 个有声章节：')
for c in CHAPTERS:
    print(f'  第{c["n"]:02d}章 · {c["duration"]:.0f}s · {c["mp3"]}')


def esc(s): return html_lib.escape(s)
def inline(s):
    s = esc(s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<em>\1</em>", s)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    return s


# ────────────── MD→HTML ──────────────

def md_to_html(md: str):
    """Skip the first H1 (we render hero instead). All H2s become chapter-h.
    Returns: (body_html, {ch_n: title}, {ch_n: kind})"""
    titles = {}   # ch_n -> md heading 文本
    kinds = {}    # ch_n -> 'main' or 'extra'

    by_n = {c['n']: c for c in CHAPTERS}
    chapter_ts = {}
    for c in CHAPTERS:
        d = {}
        for e in c['paragraphs']:
            key = ''.join(ch for ch in e['text'] if not unicodedata.category(ch).startswith('Zs'))
            d[key[:18]] = e
        chapter_ts[c['n']] = d

    lines = md.split("\n")
    out = []
    para = []
    para_in_chapter = None

    def flush():
        nonlocal para_in_chapter
        if not para:
            return
        text = ' '.join(para)
        ch = para_in_chapter
        key = ''.join(c for c in text if not unicodedata.category(c).startswith('Zs'))
        attrs = ''
        if ch is not None and ch in chapter_ts:
            entry = chapter_ts[ch].get(key[:18])
            if entry:
                attrs = f' data-t="{entry["start"]:.1f}" data-i="{entry["i"]}" data-chapter="{ch}"'
        out.append(f"<p{attrs}>{inline(text)}</p>")
        para.clear()
        para_in_chapter = None

    chapter_n = -1
    skipped_h1 = False
    for raw in lines:
        line = raw.rstrip("\r")
        if not line.strip():
            flush(); continue
        if line.strip() == "---":
            flush(); out.append("<hr/>"); continue
        m = re.match(r"^(#{1,6})\s+(.*)$", line)
        if m:
            flush()
            level = len(m.group(1))
            text = m.group(2).strip()
            anchor = re.sub(r"\s+", "-", text)
            if level == 1:
                if not skipped_h1:
                    skipped_h1 = True
                    continue
                out.append(f'<h1 id="{anchor}">{inline(text)}</h1>')
            elif level == 2:
                chapter_n += 1
                attrs = f'class="chapter-h" data-chapter="{chapter_n}" id="{anchor}"'
                if chapter_n in by_n:
                    attrs += ' data-audio="1"'
                    attrs += f' data-mp3="{by_n[chapter_n]["mp3"]}"'
                titles[chapter_n] = text
                is_main = bool(re.match(r'^第[一二三四五六七八九十百零\d]+章(\s|$)', text)) \
                    or text in ('序', '尾声', '后记')
                kinds[chapter_n] = 'main' if is_main else 'extra'
                out.append(f'<h2 {attrs}>{inline(text)}</h2>')
                para_in_chapter = None  # 重置，因为切到新章
            elif level == 3:
                out.append(f'<h3 id="{anchor}">{inline(text)}</h3>')
            else:
                out.append(f'<h{level} id="{anchor}">{inline(text)}</h{level}>')
            continue
        if para_in_chapter is None and chapter_n >= 0:
            para_in_chapter = chapter_n
        para.append(line.strip())
    flush()
    return "\n".join(out), titles, kinds


# ────────────── TOC ──────────────

def build_toc(body):
    # 包含所有 h2.chapter-h，不管有无 audio
    items = re.findall(r'<h2 class="chapter-h"[^>]*id="([^"]+)"[^>]*>([^<]+)</h2>', body)
    if not items: return "", []

    lis = []
    drawer = []
    for i, (a, t) in enumerate(items):
        # 看这个 h2 是否带 data-audio
        # (简单起见直接重新匹配)
        m_h2 = re.search(r'<h2 class="chapter-h"[^>]*id="' + re.escape(a) + r'"[^>]*>', body)
        has_audio = 'data-audio="1"' in (m_h2.group(0) if m_h2 else '')
        icon = '<span class="toc-mic" title="本章有朗读">🔊</span>' if has_audio else ''
        lis.append(f'<li><a href="#{a}"><span class="toc-num">{i+1:02d}</span><span class="toc-title">{t}</span>{icon}</a></li>')
        drawer.append(f'<li><a href="#{a}"><span class="toc-num">{i+1:02d}</span><span>{t}</span>{icon}</a></li>')

    side = f'<nav class="sidebar-toc" aria-label="章节目录"><h3>目录 · {len(items)} 章</h3><ol>{"".join(lis)}</ol></nav>'
    drawer_html = f'<aside class="drawer" id="drawer" aria-label="章节目录"><h3>目录 · {len(items)} 章</h3><ol>{"".join(drawer)}</ol></aside>'
    return side, drawer_html


# ────────────── CSS ──────────────

CSS = r"""
:root {
  --bg:        #f6efdf;
  --paper:     #fbf6e9;
  --ink:       #1f1a14;
  --ink-soft:  #5e5243;
  --ink-faint: #8a7a64;
  --accent:    #a93226;
  --accent-soft: #c05545;
  --rule:      #d4c8a8;
  --rule-soft: #ebe1c6;
  --highlight: rgba(169, 50, 38, 0.07);
  --highlight-strong: rgba(169, 50, 38, 0.16);
  --shadow:    0 1px 3px rgba(50, 30, 10, 0.06), 0 12px 32px rgba(50, 30, 10, 0.08);
  --serif:     "Source Han Serif SC", "Songti SC", "Noto Serif CJK SC", "STSong", "PingFang SC", serif;
  --sans:      "PingFang SC", "Hiragino Sans GB", "Source Han Sans SC", system-ui, sans-serif;
}
html.dark {
  --bg:        #14110b;
  --paper:     #1c1812;
  --ink:       #ece1c5;
  --ink-soft:  #b8a78a;
  --ink-faint: #7a6a55;
  --accent:    #d97560;
  --accent-soft: #e89176;
  --rule:      #3a3022;
  --rule-soft: #2a221a;
  --highlight: rgba(217, 117, 96, 0.10);
  --highlight-strong: rgba(217, 117, 96, 0.22);
  --shadow:    0 1px 3px rgba(0,0,0,0.4), 0 12px 32px rgba(0,0,0,0.3);
}

*,*::before,*::after { box-sizing: border-box; }
html, body {
  margin: 0; padding: 0;
  background: var(--bg); color: var(--ink);
  font-family: var(--serif);
  line-height: 2;
  font-size: 18px;
  -webkit-font-smoothing: antialiased;
  text-rendering: optimizeLegibility;
  scroll-behavior: smooth;
}
body { padding-bottom: 110px; }
a { color: var(--accent); text-decoration: none; }
a:hover { background: var(--highlight); }
button { font-family: var(--sans); cursor: pointer; }
::selection { background: var(--accent); color: #fff; }

/* === topbar === */
.topbar {
  position: fixed; top: 0; left: 0; right: 0;
  height: 60px; padding: 0 24px;
  display: flex; align-items: center; gap: 14px;
  background: rgba(246, 239, 223, 0.86);
  backdrop-filter: saturate(160%) blur(16px);
  -webkit-backdrop-filter: saturate(160%) blur(16px);
  border-bottom: 1px solid var(--rule);
  z-index: 100;
}
html.dark .topbar { background: rgba(20, 17, 11, 0.86); }
.topbar .brand {
  font-family: var(--serif); font-weight: 700;
  font-size: 18px; letter-spacing: 0.05em;
  color: var(--accent);
}
.topbar .brand small {
  display: block; font-family: var(--sans);
  font-weight: 400; font-size: 11px;
  letter-spacing: 0.1em;
  color: var(--ink-faint);
  margin-top: -2px;
}
.topbar-spacer { flex: 1; }
.progress-wrap {
  flex: 1; max-width: 360px; height: 4px;
  background: var(--rule-soft);
  border-radius: 2px; overflow: hidden;
  position: relative; cursor: pointer;
}
.progress-fill {
  height: 100%; width: 0%;
  background: linear-gradient(90deg, var(--accent), var(--accent-soft));
  transition: width 0.2s linear;
}
.progress-time {
  font-family: var(--sans); font-size: 12px;
  color: var(--ink-soft);
  min-width: 110px; text-align: center;
  font-variant-numeric: tabular-nums;
}
.progress-time .ch-label { color: var(--ink-faint); margin-right: 6px; }
.icon-btn {
  background: transparent;
  border: 1px solid var(--rule);
  border-radius: 999px;
  width: 38px; height: 38px;
  color: var(--ink-soft);
  display: inline-flex; align-items: center; justify-content: center;
  transition: all 0.15s;
}
.icon-btn:hover { background: var(--accent); color: #fff; border-color: var(--accent); }
.icon-btn svg { width: 18px; height: 18px; }
.menu-btn {
  display: none;
  background: transparent;
  border: 1px solid var(--rule);
  border-radius: 6px;
  width: 40px; height: 38px;
  color: var(--ink-soft);
  align-items: center; justify-content: center;
}

/* === layout === */
.layout {
  display: grid;
  grid-template-columns: 240px minmax(0, 1fr) 280px;
  gap: 36px;
  max-width: 1240px;
  margin: 60px auto 0;
  padding: 40px 28px 40px;
  align-items: start;
}

/* === 左侧目录 === */
.sidebar-toc {
  position: sticky; top: 92px;
  padding: 14px 0;
  border-right: 1px solid var(--rule-soft);
  padding-right: 16px;
  font-family: var(--sans);
  font-size: 13px;
}
.sidebar-toc h3 {
  margin: 0 0 16px;
  font-family: var(--serif);
  font-size: 17px;
  color: var(--accent);
  letter-spacing: 0.1em;
}
.sidebar-toc ol { list-style: none; padding: 0; margin: 0; max-height: calc(100vh - 200px); overflow-y: auto; }
.sidebar-toc li { margin: 0; }
.sidebar-toc li a {
  display: flex; gap: 10px;
  padding: 8px 10px;
  border-radius: 6px;
  color: var(--ink-soft);
  border: none;
  line-height: 1.5;
  align-items: baseline;
}
.sidebar-toc li a:hover { background: var(--highlight); color: var(--accent); }
.sidebar-toc li a.active { background: var(--highlight-strong); color: var(--accent); font-weight: 600; }
.sidebar-toc li a .toc-mic { font-size: 11px; opacity: 0.7; margin-left: auto; }
.toc-num { font-variant-numeric: tabular-nums; font-size: 11px; color: var(--ink-faint); min-width: 22px; }
.sidebar-toc .toc-title { flex: 1; }
.sidebar-toc::-webkit-scrollbar { width: 4px; }
.sidebar-toc::-webkit-scrollbar-thumb { background: var(--rule); border-radius: 2px; }

/* === 主文章 === */
main.article {
  background: var(--paper);
  padding: 60px 56px 80px;
  border-radius: 6px;
  box-shadow: var(--shadow);
  min-width: 0;
}
.hero {
  text-align: center;
  padding-bottom: 40px;
  border-bottom: 1px solid var(--rule);
  margin-bottom: 56px;
}
.hero h1 {
  font-size: 48px;
  margin: 0 0 16px;
  letter-spacing: 0.15em;
  color: var(--ink);
  font-weight: 700;
  position: relative;
  display: inline-block;
}
.hero h1::before, .hero h1::after {
  content: '';
  display: inline-block;
  width: 28px; height: 1px;
  background: var(--accent);
  vertical-align: middle;
  margin: 0 16px;
}
.hero .book-sub {
  color: var(--ink-faint);
  font-family: var(--sans);
  font-size: 12px;
  letter-spacing: 0.3em;
  text-transform: uppercase;
  margin: 12px 0 0;
  text-indent: 0;
}
.hero .book-meta {
  margin-top: 24px;
  display: flex; justify-content: center; gap: 18px;
  font-family: var(--sans);
  font-size: 12px;
  color: var(--ink-faint);
  text-indent: 0;
}
.hero .book-meta strong { color: var(--ink); }
.hero .play-cta {
  display: inline-flex; gap: 8px; align-items: center;
  margin-top: 28px; padding: 10px 22px;
  border: 1px solid var(--accent);
  background: var(--accent);
  color: #fff;
  border-radius: 999px;
  font-family: var(--sans);
  font-size: 13px;
  font-weight: 600;
  letter-spacing: 0.05em;
}
.hero .play-cta:hover { background: var(--accent-soft); border-color: var(--accent-soft); color: #fff; }

main.article h2.chapter-h {
  font-size: 28px;
  margin: 64px 0 24px;
  padding: 18px 0 12px;
  border-bottom: 2px solid var(--accent);
  color: var(--accent);
  letter-spacing: 0.05em;
  position: relative;
  scroll-margin-top: 96px;
}
main.article h2.chapter-h::before {
  content: '';
  display: inline-block;
  width: 12px; height: 12px;
  background: var(--accent);
  margin-right: 14px;
  vertical-align: 3px;
  border-radius: 2px;
}
main.article h2.chapter-h[data-audio="1"]::after {
  content: '🔊 本章有朗读';
  font-family: var(--sans);
  font-size: 11px;
  margin-left: 12px;
  vertical-align: middle;
  background: var(--highlight-strong);
  color: var(--accent);
  padding: 4px 10px;
  border-radius: 999px;
  letter-spacing: 0.05em;
  font-weight: 400;
}
main.article h3 {
  font-size: 20px;
  margin: 36px 0 12px;
  color: var(--ink);
  border-left: 3px solid var(--accent);
  padding-left: 12px;
}
main.article h4 {
  font-size: 17px;
  color: var(--ink-soft);
  margin: 28px 0 8px;
  font-weight: 600;
}
main.article p {
  margin: 14px 0;
  text-indent: 2em;
  text-align: justify;
  text-justify: inter-ideograph;
  position: relative;
  padding: 3px 6px;
  margin-left: -6px;
  margin-right: -6px;
  border-radius: 4px;
  transition: background 0.45s ease, color 0.45s ease;
}
main.article p[data-t] { scroll-margin-top: 120px; cursor: pointer; }
main.article p.reading { background: var(--highlight-strong); }
main.article p.spoken { background: var(--highlight); }
main.article hr {
  border: none;
  border-top: 1px dashed var(--rule);
  margin: 40px auto;
  width: 60%;
}
main.article strong { color: var(--accent); font-weight: 700; }
main.article em {
  color: var(--ink-soft); font-style: normal;
  background: linear-gradient(transparent 60%, rgba(169,50,38,0.12) 60%);
  padding: 0 2px;
}
main.article code {
  font-family: "Menlo", "Consolas", monospace;
  background: var(--rule-soft);
  padding: 1px 6px; border-radius: 3px; font-size: 0.9em;
}

.chapter-meta-bar {
  display: flex;
  justify-content: space-between; align-items: center;
  margin: 24px 0 32px;
  padding: 12px 14px;
  background: rgba(169,50,38,0.05);
  border-left: 3px solid var(--accent);
  border-radius: 0 6px 6px 0;
  font-family: var(--sans);
  font-size: 13px;
  color: var(--ink-soft);
  text-indent: 0;
}
.chapter-meta-bar strong { color: var(--ink); }
.chapter-meta-bar a { border: none; color: var(--accent); }

/* === 右侧栏 === */
.sidebar-right { position: sticky; top: 92px; font-family: var(--sans); font-size: 13px; }
.sidebar-right section {
  background: var(--paper);
  border: 1px solid var(--rule);
  border-radius: 6px;
  padding: 16px 18px;
  margin-bottom: 14px;
  box-shadow: var(--shadow);
}
.sidebar-right h4 {
  margin: 0 0 10px;
  font-family: var(--serif);
  font-size: 14px;
  color: var(--accent);
  letter-spacing: 0.05em;
}
.sidebar-right p { color: var(--ink-soft); margin: 0 0 6px; line-height: 1.6; }
.sidebar-right a {
  display: block; padding: 4px 0;
  color: var(--ink-soft); border: none;
}
.sidebar-right a:hover { color: var(--accent); }
.sidebar-right kbd {
  display: inline-block;
  border: 1px solid var(--rule);
  border-bottom-width: 2px;
  border-radius: 4px;
  padding: 1px 6px;
  font-family: var(--sans);
  font-size: 11px;
  background: var(--bg);
  color: var(--ink-soft);
  margin: 0 2px;
}

/* === 播放器 === */
.player {
  position: fixed; bottom: 0; left: 0; right: 0;
  background: rgba(246, 239, 223, 0.96);
  backdrop-filter: saturate(160%) blur(20px);
  -webkit-backdrop-filter: saturate(160%) blur(20px);
  border-top: 1px solid var(--rule);
  padding: 12px 24px 16px;
  z-index: 90;
  display: flex;
  gap: 12px;
  align-items: center;
}
html.dark .player { background: rgba(20, 17, 11, 0.96); }
.player-btn {
  width: 44px; height: 44px;
  border-radius: 999px; border: none;
  background: var(--accent); color: #fff;
  display: inline-flex; align-items: center; justify-content: center;
  flex-shrink: 0;
  transition: transform 0.1s, background 0.15s;
  box-shadow: 0 2px 8px rgba(169, 50, 38, 0.3);
}
.player-btn:hover { background: var(--accent-soft); }
.player-btn:active { transform: scale(0.96); }
.player-btn svg { width: 18px; height: 18px; }
.player-mini {
  width: 36px; height: 36px;
  background: transparent; color: var(--ink-soft);
  border: 1px solid var(--rule); box-shadow: none;
}
.player-mini:hover { background: var(--accent); color: #fff; border-color: var(--accent); }
.player-info {
  flex: 1; min-width: 0;
  display: flex; flex-direction: column; gap: 6px;
}
.player-now {
  font-family: var(--sans); font-size: 13px;
  color: var(--ink-soft);
  display: flex; justify-content: space-between; gap: 12px;
}
.player-now .title { font-weight: 600; color: var(--ink); }
.player-now .timer { font-variant-numeric: tabular-nums; font-size: 12px; }
.player-bar {
  height: 4px;
  background: var(--rule-soft);
  border-radius: 2px; overflow: hidden;
  cursor: pointer; position: relative;
}
.player-bar-fill {
  height: 100%; width: 0%;
  background: linear-gradient(90deg, var(--accent), var(--accent-soft));
  transition: width 0.15s linear;
}
.player-bar-buf {
  position: absolute; top: 0; left: 0;
  height: 100%; width: 0;
  background: var(--rule); opacity: 0.5;
}
.player-quote {
  font-family: var(--serif);
  font-size: 13px;
  color: var(--ink-soft);
  font-style: italic;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  min-height: 18px;
  padding: 0 4px;
}
.player-quote::before { content: "「"; color: var(--accent); margin-right: 2px; }
.player-quote::after { content: "」"; color: var(--accent); margin-left: 2px; }

.player-extra { display: flex; gap: 6px; align-items: center; flex-shrink: 0; }
.speed-select, .chapter-select {
  font-family: var(--sans); font-size: 12px;
  border: 1px solid var(--rule);
  background: transparent; color: var(--ink-soft);
  border-radius: 999px;
  padding: 4px 10px; cursor: pointer;
}

/* === 端 === */
.colophon {
  margin-top: 60px;
  padding-top: 28px;
  border-top: 1px dashed var(--rule);
  text-align: center;
  font-family: var(--sans);
  font-size: 12px;
  color: var(--ink-faint);
  text-indent: 0;
  letter-spacing: 0.05em;
}
.colophon .stamp {
  display: inline-block;
  border: 2px solid var(--accent);
  color: var(--accent);
  padding: 4px 14px;
  margin-top: 8px;
  font-weight: 600;
  letter-spacing: 0.3em;
  transform: rotate(-2deg);
  opacity: 0.85;
}

/* === 字号档 === */
body.size-lg { font-size: 20px; }
body.size-lg main.article h1 { font-size: 56px; }
body.size-lg h2.chapter-h { font-size: 32px; }

body.size-sm { font-size: 16px; }
body.size-sm main.article h1 { font-size: 42px; }
body.size-sm h2.chapter-h { font-size: 26px; }

/* === 移动端 === */
@media (max-width: 1023px) {
  .layout {
    grid-template-columns: 1fr;
    padding: 32px 18px 60px;
    gap: 0;
  }
  .sidebar-toc, .sidebar-right { display: none; }
  main.article { padding: 36px 24px 60px; }
  .menu-btn { display: inline-flex; }
  .progress-wrap { max-width: none; }
  .progress-time { min-width: auto; }

  .scrim {
    position: fixed; inset: 60px 0 110px 0;
    background: rgba(0,0,0,0.4);
    opacity: 0; pointer-events: none;
    z-index: 70;
    transition: opacity 0.3s ease;
  }
  .scrim.open { opacity: 1; pointer-events: auto; }
  .drawer {
    position: fixed;
    top: 60px; left: 0; bottom: 110px;
    width: 84%; max-width: 320px;
    background: var(--paper);
    border-right: 1px solid var(--rule);
    padding: 24px;
    overflow-y: auto;
    transform: translateX(-100%);
    transition: transform 0.3s ease;
    z-index: 80;
    box-shadow: 4px 0 24px rgba(0,0,0,0.15);
  }
  .drawer.open { transform: translateX(0); }
  .drawer h3 {
    font-family: var(--serif);
    color: var(--accent);
    font-size: 20px;
    margin: 0 0 20px;
    letter-spacing: 0.1em;
  }
  .drawer ol { list-style: none; padding: 0; margin: 0; }
  .drawer li a {
    display: flex; gap: 12px;
    padding: 12px 8px;
    border-radius: 6px;
    color: var(--ink);
    border-bottom: 1px solid var(--rule-soft);
    font-family: var(--sans);
    font-size: 14px;
  }
  .drawer .toc-num { color: var(--ink-faint); }
  .drawer .toc-mic { margin-left: auto; opacity: 0.7; font-size: 11px; }
}

@media (max-width: 640px) {
  body { font-size: 17px; }
  main.article { padding: 28px 18px 60px; }
  main.article h1 { font-size: 36px; letter-spacing: 0.05em; }
  h2.chapter-h { font-size: 22px !important; }
  h2.chapter-h[data-audio="1"]::after { display: block; margin-left: 0; margin-top: 6px; width: max-content; }
  main.article p { text-indent: 2em; padding: 4px 0; margin-left: 0; margin-right: 0; }
  .topbar { padding: 0 12px; gap: 8px; height: 56px; }
  .topbar .brand { font-size: 16px; }
  .topbar .brand small { display: none; }
  .topbar-spacer { display: none; }
  .progress-wrap { flex: 1; }
  .progress-time { font-size: 11px; }
  .player { padding: 10px 12px 12px; gap: 8px; height: 100px; }
  .player-info { gap: 4px; }
  .player-quote { display: none; }
  .speed-select, .chapter-select { display: none; }
  .chapter-meta-bar { flex-direction: column; gap: 8px; align-items: flex-start; }
  .hero h1 { font-size: 32px !important; }
  .hero h1::before, .hero h1::after { width: 16px; margin: 0 8px; }
  .play-cta { font-size: 12px !important; padding: 8px 16px !important; }
}

@media (max-width: 380px) {
  body { font-size: 16px; }
  main.article { padding: 24px 14px 60px; }
  .hero h1 { font-size: 28px !important; }
}
"""


# ────────────── JS ──────────────

JS_HEAD = r"""
(function(){
  'use strict';

  const $ = (id) => document.getElementById(id);
  const audio       = $('audio');
  const playBtn     = $('play-btn');
  const playIcon    = $('play-icon');
  const backBtn     = $('back-10');
  const fwdBtn      = $('fwd-10');
  const barBuf      = $('bar-buf');
  const barFill     = $('bar-fill');
  const bar         = document.querySelector('.player-bar');
  const topFill     = $('top-fill');
  const topBar      = document.querySelector('.progress-wrap');
  const cur         = $('cur-time');
  const curB        = $('cur-time-b');
  const dur         = $('dur-time');
  const durB        = $('dur-time-b');
  const chLabel     = $('ch-label');
  const quoteEl     = $('quote');
  const speedSel    = $('speed');
  const chSel       = $('chapter-select');
  const menuBtn     = $('menu-btn');
  const drawer      = $('drawer');
  const scrim       = $('scrim');

  // ── 当前章节状态 ──
  let currentChapter = 0;   // 默认 0 = 第一章（数字 1）
  let loadingChapter = false;

  // 收集所有带 audio 的章节
  const chapterMap = new Map();  // chapter_n -> mp3 url
"""

JS_FOOT = r"""

  // ── 段落数据：按 chapter 分组 ──
  const paras = Array.from(document.querySelectorAll('main.article p[data-t]'));
  // 每个段落的 chapter 与 t
  paras.forEach(p => {
    p.dataset.tNum = p.dataset.t;
  });

  function parasOf(chap){
    return paras.filter(p => parseInt(p.dataset.chapter, 10) === chap);
  }

  function findActivePara(chap, t){
    const list = parasOf(chap);
    let lo = 0, hi = list.length - 1, idx = -1;
    while (lo <= hi){
      const mid = (lo + hi) >> 1;
      if (parseFloat(list[mid].dataset.t) <= t){ idx = mid; lo = mid + 1; }
      else hi = mid - 1;
    }
    return idx >= 0 ? list[idx] : null;
  }

  let activeP = null;
  let lastP   = null;
  let userScrollingTimer = null;
  let autoFollow = true;

  function clearHighlight(){
    if (lastP){ lastP.classList.remove('reading','spoken'); lastP = null; }
    activeP = null;
    quoteEl.textContent = '点击播放 · 开始同步朗读';
  }

  function updateHighlight(t){
    const curP = findActivePara(currentChapter, t);
    if (!curP || curP === activeP) return;

    if (lastP){ lastP.classList.remove('reading'); lastP.classList.add('spoken'); }
    curP.classList.remove('spoken'); curP.classList.add('reading');
    activeP = curP; lastP = curP;

    const txt = curP.textContent.trim().replace(/\s+/g,' ').slice(0, 90);
    quoteEl.textContent = txt;

    if (autoFollow && !audio.paused){
      const r = curP.getBoundingClientRect();
      if (r.top < 90 || r.bottom > window.innerHeight - 140){
        if (userScrollingTimer) return;
        userScrollingTimer = setTimeout(()=>{
          curP.scrollIntoView({ behavior: 'smooth', block: 'center' });
          userScrollingTimer = null;
        }, 100);
      }
    }
  }

  let scrollTimer = null;
  window.addEventListener('scroll', ()=>{
    autoFollow = false;
    clearTimeout(scrollTimer);
    scrollTimer = setTimeout(()=>{ autoFollow = true; }, 5000);
  }, { passive: true });

  // ── 工具 ──
  function fmt(s){
    if (!isFinite(s) || s < 0) return '0:00';
    const m = Math.floor(s/60), x = Math.floor(s%60);
    return m + ':' + String(x).padStart(2,'0');
  }

  function setPlayingIcon(playing){
    playIcon.innerHTML = playing
      ? '<svg viewBox="0 0 24 24"><path fill="currentColor" d="M6 5h4v14H6zM14 5h4v14h-4z"/></svg>'
      : '<svg viewBox="0 0 24 24"><path fill="currentColor" d="M8 5v14l11-7z"/></svg>';
  }

  function toggle(){
    if (audio.paused) audio.play().catch(()=>{});
    else audio.pause();
  }
  playBtn.addEventListener('click', toggle);
  backBtn.addEventListener('click', () => { audio.currentTime = Math.max(0, audio.currentTime - 10); });
  fwdBtn .addEventListener('click', () => { audio.currentTime = Math.min((audio.duration||0)+1, audio.currentTime + 10); });

  audio.addEventListener('play',  ()=> setPlayingIcon(true));
  audio.addEventListener('pause', ()=> setPlayingIcon(false));
  audio.addEventListener('ended', ()=> {
    setPlayingIcon(false);
    // 自动跳下一章
    const next = findNextAudioChapter(currentChapter);
    if (next !== null && next !== currentChapter){
      switchToChapter(next, true);
    } else {
      clearHighlight();
    }
  });

  audio.addEventListener('loadedmetadata', ()=>{
    const t = fmt(audio.duration);
    dur.textContent = t;
    if (durB) durB.textContent = t;
  });

  audio.addEventListener('timeupdate', ()=>{
    const t = audio.currentTime;
    const d = audio.duration || 0;
    const pct = d ? (t / d) * 100 : 0;
    barFill.style.width = pct + '%';
    topFill.style.width = pct + '%';
    const f = fmt(t);
    cur.textContent = f;
    if (curB) curB.textContent = f;
    updateHighlight(t);
  });

  audio.addEventListener('progress', ()=>{
    if (audio.buffered.length){
      const end = audio.buffered.end(audio.buffered.length - 1);
      barBuf.style.width = ((end / (audio.duration||1)) * 100) + '%';
    }
  });

  function seekFromEvent(el, ev){
    const r = el.getBoundingClientRect();
    const ratio = (ev.clientX - r.left) / r.width;
    if (audio.duration) audio.currentTime = Math.max(0, Math.min(audio.duration, ratio * audio.duration));
  }
  bar.addEventListener('click',    e => seekFromEvent(bar,    e));
  topBar.addEventListener('click', e => seekFromEvent(topBar, e));

  // 段落点击：切到该段所属章节 + 跳转时间
  paras.forEach(p => {
    p.addEventListener('click', ()=>{
      const ch = parseInt(p.dataset.chapter, 10);
      const t  = parseFloat(p.dataset.t);
      switchToChapter(ch, false);
      audio.currentTime = t;
      if (audio.paused) audio.play();
      autoFollow = true;
    });
  });

  // ── 章节切换 ──
  function switchToChapter(ch, autoplay){
    if (!chapterMap.has(ch)) {
      // 章节没音频，找下一个有的
      const fallback = findNextAudioChapter(ch) ?? findPrevAudioChapter(ch);
      if (fallback === null) {
        // 没有任何有声章节，保持原状
        return;
      }
      ch = fallback;
    }
    if (ch === currentChapter && !loadingChapter) {
      // 同章节：可能仅是 highlight
      updateHighlight(audio.currentTime);
      return;
    }
    loadingChapter = true;
    currentChapter = ch;
    const src = chapterMap.get(ch);
    audio.src = src;
    audio.load();

    // 更新章节标签（顶栏 + player）
    const h2 = document.querySelector('h2.chapter-h[data-chapter="' + ch + '"]');
    const title = h2 ? h2.textContent : '第 ' + (ch+1) + ' 章';
    const titleEl = document.querySelector('.player-now .title');
    if (titleEl) titleEl.textContent = title;
    if (chLabel) {
      // 顶栏短一点：优先显示 dropdown 同款短标签
      // 先看 select option
      const opt = chSel && chSel.querySelector(`option[value="${ch}"]`);
      let lbl = opt ? opt.textContent : title;
      // 去掉最后 " · 时长" 部分
      lbl = lbl.replace(/\s*·\s*\d+:\d+\s*$/, '');
      // 如果太长 (>14 字) 就截断
      if (lbl.length > 14) lbl = lbl.slice(0, 13) + '…';
      chLabel.textContent = lbl;
    }
    if (chSel) chSel.value = String(ch);

    audio.addEventListener('loadedmetadata', function onMeta(){
      audio.removeEventListener('loadedmetadata', onMeta);
      loadingChapter = false;
      // 自动滚到章节开头
      const h2 = document.querySelector('h2.chapter-h[data-chapter="' + ch + '"]');
      if (h2 && autoplay !== false){
        // 让用户能看到当前章节
        // 不主动滚，避免突兀
      }
      audio.currentTime = 0;
      if (autoplay) {
        audio.play().catch(()=>{});
      }
    });
    clearHighlight();
  }

  function findNextAudioChapter(fromCh){
    const all = Array.from(chapterMap.keys()).sort((a,b)=>a-b);
    return all.find(c => c > fromCh) ?? null;
  }
  function findPrevAudioChapter(fromCh){
    const all = Array.from(chapterMap.keys()).sort((a,b)=>b-a);
    return all.find(c => c < fromCh) ?? null;
  }

  // 章节下拉
  if (chSel) {
    chSel.addEventListener('change', () => {
      const ch = parseInt(chSel.value, 10);
      switchToChapter(ch, true);
    });
  }

  // 章节跟踪（高亮当前章节在目录里）
  const chapterHs = Array.from(document.querySelectorAll('h2.chapter-h'));
  const tocLinks  = Array.from(document.querySelectorAll('.sidebar-toc a[href^="#"], .drawer a[href^="#"]'));
  const topLinks  = tocLinks.filter(a => a.closest('.sidebar-toc'));
  function activeChapter(){
    const offset = window.innerHeight * 0.4;
    let activeId = null;
    for (const h of chapterHs){
      const r = h.getBoundingClientRect();
      if (r.top < offset && r.bottom > 0) activeId = h.id;
    }
    if (!activeId) return;
    topLinks.forEach(a => a.classList.toggle('active', a.getAttribute('href') === '#' + activeId));
  }
  window.addEventListener('scroll', activeChapter, { passive: true });
  activeChapter();

  // Hero 上的"立即听第一章"
  const heroCta = document.querySelector('.hero .play-cta');
  if (heroCta) heroCta.addEventListener('click', e => {
    e.preventDefault();
    if (chapterMap.size === 0) return;
    const first = Math.min(...chapterMap.keys());
    switchToChapter(first, true);
  });

  // h2.chapter-h 上的"本章有朗读"点击
  document.querySelectorAll('h2.chapter-h[data-audio="1"]').forEach(h => {
    h.style.cursor = 'pointer';
    h.addEventListener('click', () => {
      const ch = parseInt(h.dataset.chapter, 10);
      switchToChapter(ch, true);
    });
  });

  // 字号
  const SIZES  = ['','size-sm','size-lg'];
  let sizeIdx  = 0;
  $('size-btn').addEventListener('click', () => {
    document.body.classList.remove('size-sm','size-lg');
    sizeIdx = (sizeIdx + 1) % SIZES.length;
    if (SIZES[sizeIdx]) document.body.classList.add(SIZES[sizeIdx]);
    try{localStorage.setItem('shanSize', SIZES[sizeIdx]);}catch(e){}
  });
  try{
    const s = localStorage.getItem('shanSize');
    if (s){ document.body.classList.remove('size-sm','size-lg'); document.body.classList.add(s); sizeIdx = SIZES.indexOf(s); }
  }catch(e){}

  // 主题
  $('theme-btn').addEventListener('click', () => {
    document.documentElement.classList.toggle('dark');
    try{localStorage.setItem('shanDark', document.documentElement.classList.contains('dark')?'1':'0');}catch(e){}
  });
  try{
    if (localStorage.getItem('shanDark') === '1') document.documentElement.classList.add('dark');
  }catch(e){}

  // 速度
  speedSel.addEventListener('change', () => { audio.playbackRate = parseFloat(speedSel.value); });
  audio.playbackRate = parseFloat(speedSel.value);

  // 移动端抽屉
  function openDrawer(){ drawer.classList.add('open'); scrim.classList.add('open'); }
  function closeDrawer(){ drawer.classList.remove('open'); scrim.classList.remove('open'); }
  menuBtn.addEventListener('click', openDrawer);
  scrim.addEventListener('click', closeDrawer);
  drawer.querySelectorAll('a').forEach(a => a.addEventListener('click', closeDrawer));

  // 键盘快捷键
  document.addEventListener('keydown', e => {
    if (e.target.matches('input,textarea,select')) return;
    if (e.code === 'Space'){ e.preventDefault(); toggle(); }
    else if (e.code === 'ArrowLeft') { audio.currentTime = Math.max(0, audio.currentTime - 5); }
    else if (e.code === 'ArrowRight'){ audio.currentTime = Math.min((audio.duration||0)+1, audio.currentTime + 5); }
  });

  setPlayingIcon(false);
  // 初始章节标签
  setTimeout(() => {
    const h2 = document.querySelector('h2.chapter-h[data-chapter="0"]');
    if (h2 && chLabel) {
      const m = h2.textContent.match(/第[一二三四五六七八九十百千零〇\d]+章/);
      chLabel.textContent = m ? m[0] : h2.textContent;
    }
  }, 0);
})();
"""


def make_js(titles: dict, kinds: dict):
    """组装 JS，注入 chapterMap 数据。"""
    chapter_entries = []
    for c in CHAPTERS:
        chapter_entries.append(f"  chapterMap.set({c['n']}, {json.dumps(c['mp3'])});")
    chapter_map_js = "\n".join(chapter_entries)

    # 章节下拉选项：根据 md 标题分类
    ch_opts_js = ""
    if CHAPTERS:
        opts = []
        for c in CHAPTERS:
            n = c['n']
            title = titles.get(n, f'第{n}章')
            kind = kinds.get(n, 'extra')
            dur_str = fmt_min(c['duration'])
            if kind == 'main':
                # 主故事：直接展示 md 标题
                opts.append(f'<option value="{n}">{esc(title)} · {dur_str}</option>')
            else:
                # 附录类
                # 短化标题：去掉 "附录："、"再附录："、"八、" 等前缀
                t = title
                t = re.sub(r'^(?:再?附录(?:[一二三四五六七八九十])?[：:]?)', '', t).strip()
                t = re.sub(r'^([一二三四五六七八九十]+、)\s*', '', t).strip()
                # 按 n 大致判断"卷"：13-18 = 主外 (附录/人物志等)
                # 19-23 = 卷二范围；24-29 = 跋+附录；30-31 = 卷三+终跋
                prefix = '主外·'
                if 19 <= n <= 23:
                    prefix = '卷二·'
                elif 24 <= n <= 29:
                    prefix = '跋·'
                elif n >= 30:
                    prefix = '卷三·'
                opts.append(f'<option value="{n}">{esc(prefix)}{esc(t)} · {dur_str}</option>')
        ch_opts_js = "\n      ".join(opts)

    head = JS_HEAD + "\n" + chapter_map_js + "\n"
    return head + "\n" + JS_FOOT, ch_opts_js


def fmt_min(secs):
    m = int(secs // 60); s = int(secs % 60)
    return f"{m}:{s:02d}"


# ────────────── 文档组装 ──────────────

def assemble():
    md   = SRC.read_text(encoding="utf-8")
    body, md_chap_titles, md_chap_kinds = md_to_html(md)
    side, drawer_html = build_toc(body)

    # 统计有声章节数
    n_audio = len(CHAPTERS)
    n_chapters_total = len(re.findall(r'<h2 class="chapter-h"', body))

    js_str, ch_options_html = make_js(titles=md_chap_titles, kinds=md_chap_kinds)

    # 右边栏：有声章节列表
    chapter_list_html = ""
    if CHAPTERS:
        items = []
        for c in CHAPTERS:
            h2 = re.search(r'<h2 class="chapter-h"[^>]*id="([^"]+)"[^>]*>([^<]+)</h2>', body)
        # 简化：直接用 CHAPTERS 列表
        items = []
        for c in CHAPTERS:
            items.append(
                f'<a href="#" data-play-ch="{c["n"]}">▶ 第{c["n"]:02d}章 · {fmt_min(c["duration"])}</a>'
            )
        chapter_list_html = "<section><h4>🎧 有声章节</h4>" + "".join(items) + "</section>"

    # 顶栏初次显示"第一章"
    initial_label = "第一章" if CHAPTERS else "无朗读"

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>山海错 · 一部仿韩寒《长安乱》风格的小说</title>
<meta name="description" content="《山海错》—— 一部仿韩寒《长安乱》风格的中篇武侠小说，附带同步朗读">
<meta name="theme-color" content="#f6efdf">
<link rel="preload" href="audio/ch1.mp3" as="audio">
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' fill='%23a93226'/%3E%3Ctext x='16' y='23' text-anchor='middle' fill='white' font-family='serif' font-weight='700' font-size='20'%3E错%3C/text%3E%3C/svg%3E">
<style>{CSS}</style>
</head>
<body>

<header class="topbar" role="banner">
  <button id="menu-btn" class="menu-btn" aria-label="章节目录">
    <svg viewBox="0 0 24 24" fill="currentColor"><path d="M3 6h18v2H3zM3 11h18v2H3zM3 16h18v2H3z"/></svg>
  </button>
  <div class="brand">山海错<small>仿 · 长安乱</small></div>
  <div class="topbar-spacer"></div>
  <div class="progress-wrap" title="点击跳转">
    <div class="progress-fill" id="top-fill"></div>
  </div>
  <div class="progress-time"><span class="ch-label" id="ch-label">载入中…</span>· <span id="cur-time">0:00</span> / <span id="dur-time">--:--</span></div>
  <button id="size-btn" class="icon-btn" aria-label="字号">
    <svg viewBox="0 0 24 24" fill="currentColor"><path d="M9 4v3h5v12h3V7h5V4H9zm-6 8h3v7h3v-7h3V9H3v3z"/></svg>
  </button>
  <button id="theme-btn" class="icon-btn" aria-label="切换夜间">
    <svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 3a9 9 0 109 9 7 7 0 01-9-9z"/></svg>
  </button>
</header>

<div class="layout">

  {side}

  <main class="article">
    <div class="hero">
      <h1>山海错</h1>
      <p class="book-sub">仿 · 韩寒 · 长安乱 · 风格中篇</p>
      <div class="book-meta">
        <span>全本 <strong>{n_chapters_total}</strong> 章</span>
        <span>·</span>
        <span>约 <strong>10</strong> 万字</span>
        <span>·</span>
        <span><strong>{n_audio}</strong> 章有同步朗读</span>
      </div>
      <a href="#" class="play-cta">
        <svg viewBox="0 0 24 24" fill="currentColor" width="14" height="14"><path d="M8 5v14l11-7z"/></svg>
        立即听第一章（17 分钟）
      </a>
    </div>

    {body}

    <div class="colophon">
      《山海错》· 仿韩寒《长安乱》之作<br>
      <span class="stamp">完</span>
    </div>
  </main>

  <aside class="sidebar-right">
    {chapter_list_html}
    <section>
      <h4>⌨️ 快捷键</h4>
      <p><kbd>Space</kbd> 播放/暂停</p>
      <p><kbd>←</kbd> 后退 5 秒</p>
      <p><kbd>→</kbd> 前进 5 秒</p>
      <p>点击段落跳到该处</p>
    </section>
    <section>
      <h4>📜 故事</h4>
      <p>方无咎，听雪剑门第十九代掌门。一个啃树皮啃得像练剑的八岁孩子，被他师父从山下捡回来，一辈子在下山与上山之间打转。</p>
    </section>
  </aside>

</div>

<div class="scrim" id="scrim"></div>
{drawer_html}

<audio id="audio" preload="metadata"></audio>

<footer class="player" role="region" aria-label="播放器">
  <button id="back-10" class="player-btn player-mini" aria-label="后退 10 秒">
    <svg viewBox="0 0 24 24" fill="currentColor"><path d="M11 6l-5 5 5 5V11c3.31 0 6 2.69 6 6s-2.69 6-6 6-6-2.69-6-6H3c0 4.42 3.58 8 8 8s8-3.58 8-8-3.58-8-8-8V6z"/></svg>
  </button>
  <button id="play-btn" class="player-btn" aria-label="播放/暂停">
    <svg id="play-icon" viewBox="0 0 24 24"><path fill="currentColor" d="M8 5v14l11-7z"/></svg>
  </button>
  <button id="fwd-10" class="player-btn player-mini" aria-label="前进 10 秒">
    <svg viewBox="0 0 24 24" fill="currentColor"><path d="M13 6v3c3.31 0 6 2.69 6 6s-2.69 6-6 6-6-2.69-6-6H5c0 4.42 3.58 8 8 8s8-3.58 8-8-3.58-8-8-8V6z"/></svg>
  </button>
  <div class="player-info">
    <div class="player-now">
      <span class="title">第一章 · 山上的人</span>
      <span class="timer"><span id="cur-time-b">0:00</span> / <span id="dur-time-b">--:--</span></span>
    </div>
    <div class="player-bar">
      <div class="player-bar-buf" id="bar-buf"></div>
      <div class="player-bar-fill" id="bar-fill"></div>
    </div>
    <div class="player-quote" id="quote">点击播放 · 开始同步朗读</div>
  </div>
  <div class="player-extra">
    <select id="chapter-select" class="chapter-select" aria-label="选择章节">
      {ch_options_html}
    </select>
    <select id="speed" class="speed-select" aria-label="播放速度">
      <option value="0.8">0.8×</option>
      <option value="0.9">0.9×</option>
      <option value="1" selected>1×</option>
      <option value="1.1">1.1×</option>
      <option value="1.25">1.25×</option>
      <option value="1.5">1.5×</option>
    </select>
  </div>
</footer>

<script>{js_str}</script>
</body>
</html>
"""


if __name__ == "__main__":
    import os
    html = assemble()
    OUT.write_text(html, encoding="utf-8")
    print(f"\n✓ 已生成 {OUT} ({os.path.getsize(OUT):,} 字节)")
