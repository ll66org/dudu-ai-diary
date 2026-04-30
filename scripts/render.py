"""兜兜的配图渲染器 🐣 - HTML → PNG"""
import json
from pathlib import Path
from jinja2 import Template
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).parent.parent
OUTPUT = ROOT / "output"
TEMPLATE_FILE = ROOT / "templates" / "post.html.j2"


# 内嵌模板（如果 templates/post.html.j2 不存在则用这个）
DEFAULT_TEMPLATE = r"""
<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><style>
*{margin:0;padding:0;box-sizing:border-box;-webkit-font-smoothing:antialiased}
body{font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;margin:0;padding:0;background:transparent}
.canvas{display:flex;flex-direction:column;gap:20px;padding:30px;background:linear-gradient(135deg,#FFF8F0,#FFE8E0)}

.cover{width:360px;height:480px;background:linear-gradient(160deg,#FFE5D9,#FFD4C4 45%,#FFB5A0);border-radius:20px;box-shadow:0 20px 60px rgba(255,150,120,.25);position:relative;overflow:hidden;padding:28px;display:flex;flex-direction:column;justify-content:space-between}
.cover::before{content:"";position:absolute;top:-50px;right:-50px;width:200px;height:200px;background:radial-gradient(circle,rgba(255,255,255,.5),transparent 70%);border-radius:50%}
.cover-tag{display:inline-block;background:rgba(255,255,255,.75);padding:6px 14px;border-radius:100px;font-size:12px;color:#B8593C;font-weight:600;width:fit-content;z-index:1}
.cover-emoji{font-size:64px;text-align:center;z-index:1;margin:8px 0}
.cover-title{font-size:30px;font-weight:800;color:#5C2A1A;line-height:1.3;z-index:1;letter-spacing:-.5px}
.cover-sub{font-size:13px;color:#8B4A35;z-index:1;line-height:1.5;margin-top:8px}
.cover-foot{display:flex;justify-content:space-between;align-items:center;z-index:1;margin-top:6px}
.cover-day{font-size:13px;color:#B8593C;font-weight:700}
.cover-account{font-size:12px;color:rgba(92,42,26,.6)}

.compare{width:360px;background:#fff;border-radius:20px;box-shadow:0 8px 30px rgba(0,0,0,.06);overflow:hidden}
.compare-head{background:linear-gradient(90deg,#FFE5D9,#FFD4C4);padding:14px;text-align:center;font-weight:700;color:#5C2A1A;font-size:15px}
.compare-body{display:grid;grid-template-columns:1fr 1fr}
.compare-side{padding:32px 18px;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;gap:10px;min-height:260px}
.compare-side.before{background:#F5F5F5}
.compare-side.after{background:linear-gradient(135deg,#FFF8E1,#FFE0B2)}
.compare-label{font-size:13px;color:#999;font-weight:600}
.compare-side.after .compare-label{color:#E65100}
.compare-text{font-size:15px;color:#555;line-height:1.5;font-weight:600}
.compare-side.after .compare-text{color:#5D4037}

.post{width:360px;background:#fff;border-radius:16px;box-shadow:0 8px 30px rgba(0,0,0,.06);padding:24px}
.post-header{display:flex;align-items:center;gap:10px;margin-bottom:16px}
.avatar{width:38px;height:38px;border-radius:50%;background:linear-gradient(135deg,#FFD4C4,#FFB5A0);display:flex;align-items:center;justify-content:center;font-size:22px}
.author{font-size:14px;font-weight:600;color:#333}
.meta{font-size:12px;color:#999;margin-top:2px}
.post-title{font-size:17px;font-weight:700;color:#222;line-height:1.5;margin-bottom:14px}
.post-body{font-size:14.5px;color:#444;line-height:1.85;white-space:pre-wrap}
.signature{text-align:center;margin-top:20px;padding-top:16px;border-top:1px dashed #f0d4c8;font-size:13px;color:#999}
</style></head><body><div class="canvas">

<div class="cover" id="cover">
  <span class="cover-tag">🐣 兜兜的 AI 日记</span>
  <div class="cover-emoji">{{ visuals.highlight_emoji }}</div>
  <div>
    <div class="cover-title">{{ visuals.cover_main_text }}</div>
    <div class="cover-sub">{{ visuals.cover_sub_text }}</div>
  </div>
  <div class="cover-foot">
    <span class="cover-day">DAY {{ "%03d"|format(meta.day) }}</span>
    <span class="cover-account">@兜兜的AI日记</span>
  </div>
</div>

<div class="compare" id="compare">
  <div class="compare-head">兜兜画了个对比 🎨</div>
  <div class="compare-body">
    <div class="compare-side before">
      <div class="compare-label">{{ visuals.compare_left_label }}</div>
      <div class="compare-text">{{ visuals.compare_left_desc }}</div>
    </div>
    <div class="compare-side after">
      <div class="compare-label">{{ visuals.compare_right_label }}</div>
      <div class="compare-text">{{ visuals.compare_right_desc }}</div>
    </div>
  </div>
</div>

<div class="post" id="post">
  <div class="post-header">
    <div class="avatar">🐣</div>
    <div>
      <div class="author">兜兜的AI日记</div>
      <div class="meta">第 {{ meta.day }} 天</div>
    </div>
  </div>
  <div class="post-title">{{ post.title }}</div>
  <div class="post-body">{{ post.body }}</div>
</div>

</div></body></html>
"""


def render():
    post_data = json.loads((OUTPUT / "post.json").read_text(encoding="utf-8"))

    if TEMPLATE_FILE.exists():
        tpl_str = TEMPLATE_FILE.read_text(encoding="utf-8")
    else:
        tpl_str = DEFAULT_TEMPLATE

    html = Template(tpl_str).render(**post_data)
    html_file = OUTPUT / "preview.html"
    html_file.write_text(html, encoding="utf-8")

    print("🎨 启动 Playwright 渲染配图...")
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 420, "height": 800}, device_scale_factor=2)
        page.goto(f"file://{html_file.absolute()}")
        page.wait_for_load_state("networkidle")

        for el_id in ["cover", "compare", "post"]:
            elem = page.query_selector(f"#{el_id}")
            if elem:
                out = OUTPUT / f"{el_id}.png"
                elem.screenshot(path=str(out))
                print(f"  ✅ 已渲染: {out.name}")

        browser.close()

    print("✅ 配图渲染完成")


if __name__ == "__main__":
    render()
