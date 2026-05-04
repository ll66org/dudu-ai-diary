"""兜兜的配图渲染器 v3 🐣 - HTML → PNG（杂志 × Awwwards × Dribbble 风）"""
import json
from pathlib import Path
from jinja2 import Template
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).parent.parent
OUTPUT = ROOT / "output"
TEMPLATE_FILE = ROOT / "templates" / "post.html.j2"


# ========== 主题色板（6 套，对应 accent_color）==========
# 参考 Awwwards / Dribbble 的高级配色，告别糖果色
THEMES = {
    "sunset": {  # 暖日落：适合工具更新、乐观选题
        "bg_a": "#FFF4EC", "bg_b": "#FFD9BE", "bg_c": "#FF9A6C",
        "ink": "#2A1810", "ink2": "#6B3A20",
        "accent": "#E85D2C", "accent2": "#FFB088",
        "before_bg": "#F5EEE6", "before_ink": "#8B7661",
        "after_bg": "#FFEDDE", "after_ink": "#C04A1C",
    },
    "ocean": {  # 深海蓝：适合设计哲学、思辨选题
        "bg_a": "#EEF4FA", "bg_b": "#BFD4EC", "bg_c": "#5A7FB8",
        "ink": "#0F1E35", "ink2": "#3A4E6F",
        "accent": "#1F4788", "accent2": "#8BA9D4",
        "before_bg": "#ECEEF2", "before_ink": "#6B7585",
        "after_bg": "#E6EFFA", "after_ink": "#1F4788",
    },
    "forest": {  # 墨绿：适合新兴工具挖掘、探索向
        "bg_a": "#EFF3EC", "bg_b": "#CADBC1", "bg_c": "#6B8B6A",
        "ink": "#142218", "ink2": "#3E5640",
        "accent": "#2F5D3A", "accent2": "#A8C4A2",
        "before_bg": "#EEEEEB", "before_ink": "#6B7066",
        "after_bg": "#E8F0E5", "after_ink": "#2F5D3A",
    },
    "plum": {  # 紫梅：适合视觉生成、艺术选题
        "bg_a": "#F4ECF2", "bg_b": "#D8BFD0", "bg_c": "#9B6B8E",
        "ink": "#2A1225", "ink2": "#5A2F50",
        "accent": "#8B2D6E", "accent2": "#D1A8C5",
        "before_bg": "#EFECEE", "before_ink": "#7A6570",
        "after_bg": "#F3E5EE", "after_ink": "#8B2D6E",
    },
    "mono": {  # 黑白高级灰：适合交互设计、严肃选题
        "bg_a": "#F5F3F0", "bg_b": "#E0DCD6", "bg_c": "#9E9A92",
        "ink": "#0A0A0A", "ink2": "#4A4A4A",
        "accent": "#0A0A0A", "accent2": "#9E9A92",
        "before_bg": "#EDEBE8", "before_ink": "#7A7872",
        "after_bg": "#FDFCF9", "after_ink": "#0A0A0A",
    },
    "coral": {  # 珊瑚红：适合热门爆款、惊喜向选题
        "bg_a": "#FFF0ED", "bg_b": "#FFCDC3", "bg_c": "#F07B6B",
        "ink": "#2D0E0A", "ink2": "#7A2A20",
        "accent": "#D93A2A", "accent2": "#FFA594",
        "before_bg": "#F4ECEB", "before_ink": "#8A6E6A",
        "after_bg": "#FFE5DF", "after_ink": "#D93A2A",
    },
}

DEFAULT_TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<style>
/* ========== 基础重置 ========== */
*{margin:0;padding:0;box-sizing:border-box;-webkit-font-smoothing:antialiased;-moz-osx-font-smoothing:grayscale}
html,body{background:transparent}
body{font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif}
.serif{font-family:"Times New Roman",Georgia,"Songti SC",serif;font-feature-settings:"ss01" on}

/* ========== 画布容器 ========== */
.canvas{display:flex;flex-direction:column;gap:32px;padding:32px;background:transparent}

/* ========== 通用尺寸（小红书 3:4 比例）==========
   宽 900 高 1200，@2x 输出 1800x2400，够清晰
*/
.card{width:900px;height:1200px;position:relative;overflow:hidden;border-radius:28px;box-shadow:0 30px 80px rgba(0,0,0,.12);background:#fff}

/* ======================================== */
/* ===== 01 · COVER · Awwwards 杂志封面 ===== */
/* ======================================== */
.cover{background:
    radial-gradient(ellipse 80% 60% at 100% 0%, {{ theme.bg_c }}40 0%, transparent 50%),
    radial-gradient(ellipse 60% 40% at 0% 100%, {{ theme.bg_b }}70 0%, transparent 50%),
    linear-gradient(160deg, {{ theme.bg_a }} 0%, {{ theme.bg_b }} 100%);
  padding:72px 68px}
.cover-grid{position:absolute;inset:0;background-image:
    linear-gradient({{ theme.ink }}08 1px,transparent 1px),
    linear-gradient(90deg,{{ theme.ink }}08 1px,transparent 1px);
  background-size:60px 60px;pointer-events:none}
.cover-blob{position:absolute;top:-120px;right:-120px;width:480px;height:480px;border-radius:50%;
  background:radial-gradient(circle,{{ theme.accent }}35 0%,transparent 70%);
  filter:blur(10px)}

/* 顶部栏 */
.cover-top{position:relative;display:flex;justify-content:space-between;align-items:center;padding-bottom:28px;border-bottom:1px solid {{ theme.ink }}22}
.cover-brand{display:flex;align-items:center;gap:12px}
.cover-brand-dot{width:12px;height:12px;border-radius:50%;background:{{ theme.accent }}}
.cover-brand-text{font-size:14px;font-weight:700;color:{{ theme.ink }};letter-spacing:3px}
.cover-date{font-size:13px;color:{{ theme.ink2 }};letter-spacing:2px;font-weight:500}

/* kicker 英文栏目名 */
.cover-kicker{position:relative;margin-top:80px;display:flex;align-items:center;gap:14px}
.cover-kicker-bar{width:52px;height:2px;background:{{ theme.accent }}}
.cover-kicker-text{font-size:13px;font-weight:800;color:{{ theme.accent }};letter-spacing:5px;font-family:"Times New Roman",Georgia,serif}

/* 超大期号 - Awwwards 经典 */
.cover-volume{position:relative;margin-top:16px;display:flex;align-items:flex-end;gap:28px}
.cover-vol-num{font-size:240px;line-height:.78;font-weight:900;color:{{ theme.ink }};letter-spacing:-16px;font-family:"Times New Roman",Georgia,serif;font-style:italic}
.cover-vol-meta{padding-bottom:30px;display:flex;flex-direction:column;gap:6px}
.cover-vol-label{font-size:12px;font-weight:800;color:{{ theme.ink2 }};letter-spacing:4px;font-family:"Times New Roman",Georgia,serif}
.cover-vol-sub{font-size:15px;color:{{ theme.ink }};font-weight:500}

/* 主标题 */
.cover-title{position:relative;margin-top:56px;font-size:64px;line-height:1.15;font-weight:900;color:{{ theme.ink }};letter-spacing:-2.5px;max-width:760px}
.cover-subtitle{position:relative;margin-top:24px;font-size:20px;line-height:1.55;color:{{ theme.ink2 }};font-weight:400;max-width:640px;letter-spacing:.3px}

/* 底部信息条 */
.cover-bottom{position:absolute;left:68px;right:68px;bottom:60px;display:flex;justify-content:space-between;align-items:flex-end;padding-top:22px;border-top:1px solid {{ theme.ink }}22}
.cover-bottom-left{display:flex;gap:40px}
.cover-bottom-cell .cell-label{font-size:10px;font-weight:800;color:{{ theme.ink2 }};letter-spacing:3px;margin-bottom:6px;font-family:"Times New Roman",Georgia,serif}
.cover-bottom-cell .cell-val{font-size:15px;font-weight:700;color:{{ theme.ink }};letter-spacing:.2px}
.cover-bottom-right{text-align:right}
.cover-quote-en{font-size:13px;font-style:italic;color:{{ theme.ink2 }};letter-spacing:.5px;max-width:280px;line-height:1.5;font-family:"Times New Roman",Georgia,serif}

/* emoji 装饰 */
.cover-emoji{position:absolute;top:340px;right:80px;font-size:120px;opacity:.95;filter:drop-shadow(0 10px 30px {{ theme.accent }}40);transform:rotate(-8deg)}


/* ================================================ */
/* ===== 02 · COMPARE · Dribbble 式对比卡 ===== */
/* ================================================ */
.compare{background:{{ theme.bg_a }};padding:70px 60px;display:flex;flex-direction:column}

.compare-head{display:flex;justify-content:space-between;align-items:center;padding-bottom:22px;border-bottom:1px solid {{ theme.ink }}22;margin-bottom:12px}
.compare-head-left{display:flex;align-items:center;gap:12px}
.compare-head-dot{width:8px;height:8px;border-radius:50%;background:{{ theme.accent }}}
.compare-head-kicker{font-size:12px;font-weight:800;color:{{ theme.accent }};letter-spacing:4px;font-family:"Times New Roman",Georgia,serif}
.compare-head-right{font-size:12px;color:{{ theme.ink2 }};letter-spacing:2px;font-weight:600;font-family:"Times New Roman",Georgia,serif}

.compare-title{font-size:48px;font-weight:900;color:{{ theme.ink }};line-height:1.15;letter-spacing:-1.5px;margin-top:20px;margin-bottom:6px}
.compare-subtitle{font-size:15px;color:{{ theme.ink2 }};font-weight:400;letter-spacing:.3px;margin-bottom:40px}

/* 左右对比主体 */
.compare-body{flex:1;display:grid;grid-template-columns:1fr 86px 1fr;gap:0;align-items:stretch;margin-bottom:36px}

/* 单边卡片 */
.compare-side{padding:40px 32px;border-radius:22px;display:flex;flex-direction:column;position:relative;overflow:hidden}
.compare-side.before{background:{{ theme.before_bg }}}
.compare-side.after{background:{{ theme.after_bg }};box-shadow:0 20px 50px {{ theme.accent }}25}
.compare-side.after::before{content:"";position:absolute;top:-30px;right:-30px;width:120px;height:120px;border-radius:50%;background:{{ theme.accent }}15}

/* 标签条 */
.cs-chip{display:inline-flex;align-items:center;gap:8px;padding:7px 14px;border-radius:100px;background:{{ theme.ink }};color:{{ theme.bg_a }};font-size:11px;font-weight:800;letter-spacing:2px;width:fit-content;font-family:"Times New Roman",Georgia,serif}
.compare-side.after .cs-chip{background:{{ theme.accent }};color:#fff}
.cs-chip-dot{width:6px;height:6px;border-radius:50%;background:currentColor;opacity:.7}

/* 标题 */
.cs-title{font-size:30px;font-weight:900;color:{{ theme.before_ink }};margin-top:22px;line-height:1.2;letter-spacing:-.8px}
.compare-side.after .cs-title{color:{{ theme.after_ink }}}

/* 描述 */
.cs-desc{font-size:15px;color:{{ theme.before_ink }};line-height:1.65;margin-top:14px;font-weight:500;letter-spacing:.2px}
.compare-side.after .cs-desc{color:{{ theme.ink }};font-weight:500}

/* 关键数据 - 超大数字感 */
.cs-metric-wrap{margin-top:auto;padding-top:28px;border-top:1px dashed {{ theme.ink }}22}
.cs-metric-label{font-size:10px;font-weight:800;color:{{ theme.before_ink }};letter-spacing:3px;margin-bottom:8px;font-family:"Times New Roman",Georgia,serif}
.compare-side.after .cs-metric-label{color:{{ theme.accent }}}
.cs-metric-val{font-size:42px;font-weight:900;color:{{ theme.before_ink }};line-height:1;letter-spacing:-1.5px;font-family:"Times New Roman",Georgia,serif;font-style:italic}
.compare-side.after .cs-metric-val{color:{{ theme.accent }}}

/* 中间箭头 */
.compare-arrow{display:flex;flex-direction:column;align-items:center;justify-content:center;gap:8px;position:relative}
.compare-arrow-line{position:absolute;top:50%;left:0;right:0;height:1px;background:repeating-linear-gradient(90deg,{{ theme.ink }}44 0,{{ theme.ink }}44 4px,transparent 4px,transparent 10px)}
.compare-arrow-badge{position:relative;width:60px;height:60px;border-radius:50%;background:{{ theme.ink }};color:{{ theme.bg_a }};display:flex;align-items:center;justify-content:center;font-size:22px;font-weight:900;box-shadow:0 8px 24px {{ theme.ink }}33;font-family:"Times New Roman",Georgia,serif}

/* 底部洞察条 */
.compare-insight{background:{{ theme.ink }};color:{{ theme.bg_a }};border-radius:18px;padding:24px 28px;display:flex;align-items:center;gap:18px}
.compare-insight-icon{flex-shrink:0;width:46px;height:46px;border-radius:50%;background:{{ theme.accent }};color:#fff;display:flex;align-items:center;justify-content:center;font-size:22px}
.compare-insight-text{flex:1}
.compare-insight-label{font-size:10px;font-weight:800;letter-spacing:3px;color:{{ theme.accent2 }};margin-bottom:4px;font-family:"Times New Roman",Georgia,serif}
.compare-insight-body{font-size:16px;font-weight:600;line-height:1.45;letter-spacing:.2px}


/* ==================================== */
/* ===== 03 · POST · 杂志内页 ===== */
/* ==================================== */
.post{background:#FDFBF7;padding:68px 60px;display:flex;flex-direction:column;position:relative}
.post::before{content:"";position:absolute;top:0;left:0;right:0;height:160px;background:linear-gradient(180deg,{{ theme.bg_a }},transparent)}

.post-head{position:relative;display:flex;justify-content:space-between;align-items:flex-start;padding-bottom:26px;border-bottom:2px solid {{ theme.ink }}}
.post-head-left{display:flex;flex-direction:column;gap:6px}
.post-kicker{font-size:11px;font-weight:800;color:{{ theme.accent }};letter-spacing:4px;font-family:"Times New Roman",Georgia,serif}
.post-author{display:flex;align-items:center;gap:10px;margin-top:4px}
.post-avatar{width:38px;height:38px;border-radius:50%;background:linear-gradient(135deg,{{ theme.bg_b }},{{ theme.accent2 }});display:flex;align-items:center;justify-content:center;font-size:20px;box-shadow:0 4px 14px {{ theme.accent }}30}
.post-author-meta{display:flex;flex-direction:column}
.post-author-name{font-size:13px;font-weight:800;color:{{ theme.ink }}}
.post-author-day{font-size:11px;color:{{ theme.ink2 }};letter-spacing:1px;font-family:"Times New Roman",Georgia,serif}
.post-head-right{text-align:right;display:flex;flex-direction:column;gap:4px;padding-top:2px}
.post-issue{font-size:11px;font-weight:800;color:{{ theme.ink2 }};letter-spacing:3px;font-family:"Times New Roman",Georgia,serif}
.post-issue-num{font-size:24px;font-weight:900;color:{{ theme.ink }};letter-spacing:-1px;font-family:"Times New Roman",Georgia,serif;font-style:italic;line-height:1}

/* 标题 */
.post-title{font-size:42px;font-weight:900;color:{{ theme.ink }};line-height:1.2;letter-spacing:-1.2px;margin-top:36px;margin-bottom:22px}

/* 大号引号 */
.post-pullquote{position:relative;padding:0 0 0 40px;margin-bottom:28px;border-left:3px solid {{ theme.accent }}}
.post-pullquote::before{content:"\201C";position:absolute;left:-8px;top:-30px;font-size:80px;color:{{ theme.accent }}33;font-family:"Times New Roman",Georgia,serif;line-height:1;font-weight:900}
.post-pullquote-text{font-size:18px;line-height:1.65;color:{{ theme.ink2 }};font-weight:500;font-style:italic;letter-spacing:.3px}

/* 正文 - 两栏网格 */
.post-body{font-size:16px;line-height:1.9;color:{{ theme.ink }};font-weight:400;letter-spacing:.3px;white-space:pre-wrap;margin-bottom:28px}
.post-body strong{color:{{ theme.accent }};font-weight:700}

/* 标签条 */
.post-tags{margin-top:auto;padding-top:26px;border-top:1px dashed {{ theme.ink }}33;display:flex;flex-wrap:wrap;gap:8px}
.post-tag{display:inline-block;padding:7px 14px;background:{{ theme.bg_a }};color:{{ theme.accent }};border-radius:100px;font-size:12px;font-weight:700;border:1px solid {{ theme.accent }}30}

/* 底部签名 */
.post-foot{display:flex;justify-content:space-between;align-items:center;margin-top:20px;padding-top:20px;border-top:1px solid {{ theme.ink }}22}
.post-foot-left{display:flex;align-items:center;gap:10px;font-size:11px;color:{{ theme.ink2 }};letter-spacing:2px;font-weight:600;font-family:"Times New Roman",Georgia,serif}
.post-foot-dot{width:6px;height:6px;border-radius:50%;background:{{ theme.accent }}}
.post-foot-right{font-size:11px;color:{{ theme.ink2 }};letter-spacing:3px;font-weight:600;font-family:"Times New Roman",Georgia,serif}

</style></head><body>
<div class="canvas">

<!-- ========== 01 · COVER ========== -->
<div class="card cover" id="cover">
  <div class="cover-grid"></div>
  <div class="cover-blob"></div>
  <div class="cover-emoji">{{ visuals.highlight_emoji }}</div>

  <div class="cover-top">
    <div class="cover-brand">
      <div class="cover-brand-dot"></div>
      <div class="cover-brand-text">DUDU&#39;S AI DIARY</div>
    </div>
    <div class="cover-date">{{ today_str }}</div>
  </div>

  <div class="cover-kicker">
    <div class="cover-kicker-bar"></div>
    <div class="cover-kicker-text">{{ visuals.cover_kicker }}</div>
  </div>

  <div class="cover-volume">
    <div class="cover-vol-num">{{ "%02d"|format(meta.day) }}</div>
    <div class="cover-vol-meta">
      <div class="cover-vol-label">VOLUME / 卷</div>
      <div class="cover-vol-sub">兜兜的第 {{ meta.day }} 天</div>
    </div>
  </div>

  <div class="cover-title">{{ visuals.cover_main_text }}</div>
  <div class="cover-subtitle">{{ visuals.cover_sub_text }}</div>

  <div class="cover-bottom">
    <div class="cover-bottom-left">
      <div class="cover-bottom-cell">
        <div class="cell-label">TOPIC</div>
        <div class="cell-val">{{ selected_topic.source[:20] }}</div>
      </div>
      <div class="cover-bottom-cell">
        <div class="cell-label">SERIES</div>
        <div class="cell-val">AI × DESIGN</div>
      </div>
    </div>
    <div class="cover-bottom-right">
      <div class="cover-quote-en">&ldquo;{{ visuals.cover_quote_en }}&rdquo;</div>
    </div>
  </div>
</div>


<!-- ========== 02 · COMPARE ========== -->
<div class="card compare" id="compare">
  <div class="compare-head">
    <div class="compare-head-left">
      <div class="compare-head-dot"></div>
      <div class="compare-head-kicker">CHAPTER 02 · COMPARISON</div>
    </div>
    <div class="compare-head-right">DAY {{ "%03d"|format(meta.day) }}</div>
  </div>

  <div class="compare-title">{{ visuals.compare_headline }}</div>
  <div class="compare-subtitle">左边是以前，右边是现在 —— 兜兜画的对比图 🎨</div>

  <div class="compare-body">
    <!-- BEFORE -->
    <div class="compare-side before">
      <div class="cs-chip">
        <div class="cs-chip-dot"></div>
        {{ visuals.compare_left_label }}
      </div>
      <div class="cs-title">{{ visuals.compare_left_title }}</div>
      <div class="cs-desc">{{ visuals.compare_left_desc }}</div>
      <div class="cs-metric-wrap">
        <div class="cs-metric-label">KEY METRIC</div>
        <div class="cs-metric-val">{{ visuals.compare_left_metric }}</div>
      </div>
    </div>

    <!-- 中间箭头 -->
    <div class="compare-arrow">
      <div class="compare-arrow-line"></div>
      <div class="compare-arrow-badge">→</div>
    </div>

    <!-- AFTER -->
    <div class="compare-side after">
      <div class="cs-chip">
        <div class="cs-chip-dot"></div>
        {{ visuals.compare_right_label }}
      </div>
      <div class="cs-title">{{ visuals.compare_right_title }}</div>
      <div class="cs-desc">{{ visuals.compare_right_desc }}</div>
      <div class="cs-metric-wrap">
        <div class="cs-metric-label">KEY METRIC</div>
        <div class="cs-metric-val">{{ visuals.compare_right_metric }}</div>
      </div>
    </div>
  </div>

  <!-- 洞察 -->
  <div class="compare-insight">
    <div class="compare-insight-icon">💡</div>
    <div class="compare-insight-text">
      <div class="compare-insight-label">DUDU&#39;S INSIGHT</div>
      <div class="compare-insight-body">{{ visuals.compare_insight }}</div>
    </div>
  </div>
</div>


<!-- ========== 03 · POST ========== -->
<div class="card post" id="post">
  <div class="post-head">
    <div class="post-head-left">
      <div class="post-kicker">CHAPTER 03 · FULL POST</div>
      <div class="post-author">
        <div class="post-avatar">🐣</div>
        <div class="post-author-meta">
          <div class="post-author-name">兜兜的AI日记</div>
          <div class="post-author-day">DAY {{ "%03d"|format(meta.day) }} · {{ today_str }}</div>
        </div>
      </div>
    </div>
    <div class="post-head-right">
      <div class="post-issue">ISSUE</div>
      <div class="post-issue-num">N°{{ "%02d"|format(meta.day) }}</div>
    </div>
  </div>

  <div class="post-title">{{ post.title }}</div>

  <div class="post-pullquote">
    <div class="post-pullquote-text">{{ selected_topic.why_picked }}</div>
  </div>

  <div class="post-body">{{ post.body }}</div>

  <div class="post-tags">
    {% for t in post.tags %}<span class="post-tag">{{ t }}</span>{% endfor %}
  </div>

  <div class="post-foot">
    <div class="post-foot-left">
      <div class="post-foot-dot"></div>
      POWERED BY DUSTIN &amp; DUDU
    </div>
    <div class="post-foot-right">@兜兜的AI日记</div>
  </div>
</div>

</div>
</body></html>
"""


def render():
    post_data = json.loads((OUTPUT / "post.json").read_text(encoding="utf-8"))

    # ========== 补齐 visuals 默认值（防止 AI 漏字段）==========
    visuals = post_data.setdefault("visuals", {})
    defaults = {
        "cover_kicker": "DAILY DESIGN NOTE",
        "cover_main_text": post_data.get("post", {}).get("title", "兜兜的日记")[:12],
        "cover_sub_text": post_data.get("selected_topic", {}).get("designer_angle", "")[:22],
        "cover_quote_en": "Design is thinking made visual.",
        "compare_headline": "一张图看懂区别",
        "compare_left_label": "BEFORE",
        "compare_left_title": "以前",
        "compare_left_desc": "设计师手动处理",
        "compare_left_metric": "耗时 2h",
        "compare_right_label": "AFTER",
        "compare_right_title": "现在",
        "compare_right_desc": "AI 一步到位",
        "compare_right_metric": "耗时 3min",
        "compare_insight": "AI 不是替代设计师，是把做判断的时间还给你。",
        "highlight_emoji": "✨",
        "accent_color": "sunset",
    }
    for k, v in defaults.items():
        if not visuals.get(k):
            visuals[k] = v

    # 选主题色
    accent_key = visuals.get("accent_color", "sunset")
    if accent_key not in THEMES:
        accent_key = "sunset"
    theme = THEMES[accent_key]

    # today_str
    from datetime import datetime
    today_str = datetime.now().strftime("%Y.%m.%d")

    # 渲染
    if TEMPLATE_FILE.exists():
        tpl_str = TEMPLATE_FILE.read_text(encoding="utf-8")
    else:
        tpl_str = DEFAULT_TEMPLATE

    html = Template(tpl_str).render(
        **post_data,
        theme=theme,
        today_str=today_str,
    )
    html_file = OUTPUT / "preview.html"
    html_file.write_text(html, encoding="utf-8")

    print(f"🎨 启动 Playwright 渲染配图 (主题: {accent_key})...")
    with sync_playwright() as p:
        browser = p.chromium.launch()
        # viewport 更大一点，保证卡片完整可见
        page = browser.new_page(viewport={"width": 1024, "height": 1400}, device_scale_factor=2)
        page.goto(f"file://{html_file.absolute()}")
        page.wait_for_load_state("networkidle")

        for el_id in ["cover", "compare", "post"]:
            elem = page.query_selector(f"#{el_id}")
            if elem:
                out = OUTPUT / f"{el_id}.png"
                # 使用 element.screenshot 精准裁剪到圆角卡片本身
                elem.screenshot(path=str(out), omit_background=True)
                print(f"  ✅ 已渲染: {out.name}")

        browser.close()

    print("✅ 配图渲染完成")


if __name__ == "__main__":
    render()
