"""dudu notify v3 - 杂志邮件 + 干货快讯 + 物理日期"""
import os
import smtplib
import json
from datetime import date
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.utils import formataddr
from email.header import Header
from pathlib import Path

ROOT = Path(__file__).parent.parent
OUTPUT = ROOT / "output"

# 兜兜诞生日（与 fetch.py / compose.py 保持一致）
DUDU_BIRTHDAY = date(2026, 4, 24)

# 苹方字体堆叠
FONT_SANS = "'PingFang SC','PingFangSC-Regular','苹方-简','苹方',-apple-system,BlinkMacSystemFont,'Helvetica Neue','Microsoft YaHei',sans-serif"
FONT_SERIF = "'Times New Roman',Georgia,serif"


def get_dudu_day():
    return max(1, (date.today() - DUDU_BIRTHDAY).days + 1)


def category_label(cat):
    mapping = {
        "ai-models": "模型",
        "ai-products": "产品",
        "industry": "行业",
        "paper": "论文",
        "tip": "技巧",
        "general": "动态",
    }
    # 兼容旧数据中的内部前缀
    if cat and cat.startswith("aihot_"):
        cat = cat[6:]
    if cat and cat.startswith("briefing_"):
        cat = cat[9:]
    return mapping.get(cat, "动态")


def build_briefing_html(briefing):
    """渲染今日 5 条干货快讯卡片 — 突出真实出处"""
    if not briefing:
        return ""

    cards = ""
    for i, b in enumerate(briefing[:5], 1):
        title = b.get("title", "")[:80]
        summary = b.get("summary", "")[:120]
        source = b.get("source", "")[:40] or "未知来源"
        url = b.get("url", "#")
        cat_label = category_label(b.get("category", ""))

        cards += f'''
        <div style="background:#fff;border:1px solid #F0E4D8;border-radius:14px;padding:20px 22px;margin-bottom:12px;">
          <div style="display:flex;align-items:center;gap:10px;margin-bottom:12px;">
            <div class="serif" style="font-size:18px;font-weight:800;color:#C04A2E;line-height:1;font-style:italic;min-width:24px;">{i:02d}</div>
            <div style="font-size:10px;font-weight:700;color:#fff;background:#C04A2E;padding:3px 9px;border-radius:100px;letter-spacing:1px;">{cat_label}</div>
          </div>
          <div style="font-size:15px;font-weight:700;color:#2D1108;line-height:1.5;letter-spacing:.2px;margin-bottom:8px;">{title}</div>
          <div style="font-size:13px;color:#666;line-height:1.7;letter-spacing:.2px;margin-bottom:14px;">{summary}</div>
          <div style="display:flex;justify-content:space-between;align-items:center;padding-top:12px;border-top:1px dashed #F0D4C8;">
            <div style="display:flex;align-items:center;gap:6px;font-size:11px;color:#8B6D5A;font-weight:600;letter-spacing:.3px;">
              <span style="display:inline-block;width:4px;height:4px;border-radius:50%;background:#C04A2E;"></span>
              来源 · {source}
            </div>
            <a href="{url}" style="font-size:11px;color:#5B7FFF;text-decoration:none;letter-spacing:.3px;font-weight:600;">↗ 看原文</a>
          </div>
        </div>'''
    return cards


def build_email(post_data):
    # 关键改动 1：使用物理日期计算的 day（不再依赖 memory.day_count）
    # 优先用 meta.day（fetch/compose 写入的物理日期），兜底用现算
    day = post_data.get("meta", {}).get("day") or get_dudu_day()
    topic = post_data["selected_topic"]
    post = post_data["post"]
    voice = post_data.get("dudu_voice", "")
    date_str = post_data.get("meta", {}).get("date") or post_data.get("meta", {}).get("generated_at", "")[:10]
    briefing = post_data.get("briefing", [])

    # 加载历史
    history = []
    try:
        memory_file = ROOT / "memory" / "growth.json"
        if memory_file.exists():
            mem = json.loads(memory_file.read_text(encoding="utf-8"))
            history = mem.get("history", [])
    except Exception:
        history = []
    total_days = len(history) if history else 1
    # 兜兜活了多少天（物理日期），可能 > 实际发文天数
    dudu_days_alive = day

    subject = f"Vol.{day:03d} | {post['title']}"

    # 标签
    tags_html = "".join([
        f'<span style="display:inline-block;font-family:{FONT_SANS};font-size:12px;font-weight:400;color:#C04A2E;background:#FFF3ED;padding:5px 11px;border-radius:100px;margin:3px 4px 3px 0;">{t}</span>'
        for t in post.get("tags", [])
    ])

    # 历史足迹
    history_cards = ""
    if len(history) > 1:
        recent = history[-4:-1][::-1]
        if recent:
            cards = "".join([
                f'''<div style="flex:1;min-width:0;background:#fff;border:1px solid #F5E6DC;border-radius:12px;padding:14px;margin-right:8px;">
                <div style="font-family:{FONT_SERIF};font-size:11px;color:#999;letter-spacing:1px;font-weight:600;margin-bottom:6px;">DAY {h["day"]:03d}</div>
                <div style="font-family:{FONT_SANS};font-size:12px;font-weight:400;color:#666;line-height:1.55;overflow:hidden;text-overflow:ellipsis;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;">{h["topic"][:40]}</div>
                </div>'''
                for h in recent
            ])
            history_cards = f'''<div style="margin:48px 40px 0;padding:24px;background:#FDF8F3;border-radius:16px;">
            <div style="font-family:{FONT_SANS};font-size:11px;font-weight:700;color:#B8593C;letter-spacing:3px;margin-bottom:14px;">DUDU·RECENT</div>
            <div style="display:flex;">{cards}</div>
            </div>'''

    # 今日干货快讯（aihot 拉的真实 AI 资讯）
    briefing_html = build_briefing_html(briefing)
    briefing_section = ""
    if briefing_html:
        briefing_section = f"""
  <!-- ========== 00 · 今日干货 ========== -->
  <div style="padding:56px 40px 0;">
    <div style="display:flex;align-items:center;gap:14px;margin-bottom:18px;">
      <div style="width:36px;height:1px;background:#C04A2E;"></div>
      <div class="serif" style="font-size:11px;font-weight:700;color:#C04A2E;letter-spacing:4px;">00 · TODAY&#39;S BRIEFING</div>
    </div>
    <h2 style="font-size:24px;font-weight:800;color:#2D1108;margin:0 0 6px;letter-spacing:-0.6px;line-height:1.3;">今日 AI 圈 · {len(briefing)} 条干货</h2>
    <div style="font-size:12px;font-weight:300;color:#999;margin-bottom:22px;letter-spacing:0.3px;">兜兜从设计师视角挑的今日速览 · 每条都标了原文出处</div>
    {briefing_html}
  </div>
"""

    html_body = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
  /* 全局字体强制 */
  body, body *, td, p, div, span, h1, h2, h3, h4, a {{
    font-family: {FONT_SANS} !important;
    -webkit-font-smoothing: antialiased;
    -moz-osx-font-smoothing: grayscale;
  }}
  /* 数字/编号用衬线，更有杂志感 */
  .serif {{ font-family: {FONT_SERIF} !important; }}
</style>
</head>
<body style="margin:0;padding:0;background:#F5EDE4;">

<div style="max-width:640px;margin:0 auto;background:#FFFBF5;">

  <!-- ========== Magazine Cover ========== -->
  <div style="position:relative;padding:52px 40px 44px;background:linear-gradient(160deg,#FFE5D9 0%,#FFD4C4 40%,#FFB5A0 100%);overflow:hidden;">
    <div style="position:absolute;top:-60px;right:-60px;width:240px;height:240px;background:radial-gradient(circle,rgba(255,255,255,0.6),transparent 70%);border-radius:50%;"></div>
    <div style="position:absolute;bottom:-40px;left:-40px;width:160px;height:160px;background:radial-gradient(circle,rgba(255,255,255,0.3),transparent 70%);border-radius:50%;"></div>

    <!-- Top meta -->
    <div style="position:relative;display:flex;justify-content:space-between;align-items:center;padding-bottom:32px;border-bottom:1px solid rgba(92,42,26,0.15);">
      <div class="serif" style="font-size:11px;font-weight:700;color:#5C2A1A;letter-spacing:4px;">DUDU&#39;S AI DIARY</div>
      <div style="font-size:11px;font-weight:300;color:#8B4A35;letter-spacing:1.5px;">{date_str}</div>
    </div>

    <!-- 大期号 -->
    <div style="position:relative;margin-top:36px;display:flex;align-items:flex-end;gap:22px;">
      <div class="serif" style="font-size:110px;line-height:0.85;font-weight:800;color:#5C2A1A;letter-spacing:-6px;">{day:03d}</div>
      <div style="padding-bottom:14px;">
        <div class="serif" style="font-size:11px;font-weight:700;color:#8B4A35;letter-spacing:3px;">VOLUME</div>
        <div style="font-size:13px;font-weight:400;color:#5C2A1A;margin-top:6px;letter-spacing:0.2px;">兜兜的第 {day} 天 · 一只小鸡的成长日记</div>
      </div>
    </div>

    <!-- 主标题 -->
    <div style="position:relative;margin-top:32px;font-size:30px;font-weight:800;color:#2D1108;line-height:1.25;letter-spacing:-0.8px;max-width:500px;">{post["title"]}</div>

    <!-- 元信息 -->
    <div style="position:relative;margin-top:36px;display:flex;gap:32px;">
      <div>
        <div class="serif" style="font-size:10px;font-weight:700;color:#8B4A35;letter-spacing:2px;">TOPIC</div>
        <div style="font-size:13px;font-weight:600;color:#5C2A1A;margin-top:6px;letter-spacing:0.2px;">{topic["source"]}</div>
      </div>
      <div style="width:1px;background:rgba(92,42,26,0.2);"></div>
      <div>
        <div class="serif" style="font-size:10px;font-weight:700;color:#8B4A35;letter-spacing:2px;">DUDU AGE</div>
        <div style="font-size:13px;font-weight:600;color:#5C2A1A;margin-top:6px;letter-spacing:0.2px;">兜兜已经 {dudu_days_alive} 天大啦</div>
      </div>
    </div>
  </div>

  {briefing_section}

  <!-- ========== 01 · WHY ========== -->
  <div style="padding:56px 40px 0;">
    <div style="display:flex;align-items:center;gap:14px;margin-bottom:18px;">
      <div style="width:36px;height:1px;background:#C04A2E;"></div>
      <div class="serif" style="font-size:11px;font-weight:700;color:#C04A2E;letter-spacing:4px;">01 · WHY</div>
    </div>
    <h2 style="font-size:24px;font-weight:800;color:#2D1108;margin:0 0 20px;letter-spacing:-0.6px;line-height:1.3;">为什么是今天这条？</h2>

    <div style="background:#FFF8F2;border-radius:14px;padding:24px 26px;border-left:3px solid #FFB5A0;">
      <div style="display:flex;gap:12px;margin-bottom:14px;align-items:flex-start;">
        <div style="font-size:11px;font-weight:600;color:#B8593C;background:#FFE5D9;padding:4px 11px;border-radius:100px;letter-spacing:0.5px;flex-shrink:0;">选题</div>
        <div style="font-size:15px;font-weight:600;color:#2D1108;flex:1;line-height:1.55;">{topic["title"]}</div>
      </div>

      <div style="padding:14px 0 10px;border-top:1px dashed #F0D4C8;margin-top:14px;">
        <div class="serif" style="font-size:10px;font-weight:700;color:#8B4A35;letter-spacing:2px;margin-bottom:6px;">DUDU PICKS</div>
        <div style="font-size:14px;font-weight:400;color:#555;line-height:1.85;">{topic["why_picked"]}</div>
      </div>

      <div style="padding-top:10px;">
        <div class="serif" style="font-size:10px;font-weight:700;color:#8B4A35;letter-spacing:2px;margin-bottom:6px;">DESIGNER ANGLE</div>
        <div style="font-size:14px;font-weight:400;color:#555;line-height:1.85;">{topic["designer_angle"]}</div>
      </div>

      <div style="margin-top:18px;padding-top:14px;border-top:1px dashed #F0D4C8;">
        <a href="{topic["url"]}" style="font-size:12px;font-weight:400;color:#5B7FFF;text-decoration:none;letter-spacing:0.3px;">↗ 查看原文</a>
      </div>
    </div>
  </div>

  <!-- ========== 02 · POST ========== -->
  <div style="padding:56px 40px 0;">
    <div style="display:flex;align-items:center;gap:14px;margin-bottom:18px;">
      <div style="width:36px;height:1px;background:#C04A2E;"></div>
      <div class="serif" style="font-size:11px;font-weight:700;color:#C04A2E;letter-spacing:4px;">02 · POST</div>
    </div>
    <h2 style="font-size:24px;font-weight:800;color:#2D1108;margin:0 0 6px;letter-spacing:-0.6px;line-height:1.3;">今日小红书文案</h2>
    <div style="font-size:12px;font-weight:300;color:#999;margin-bottom:22px;letter-spacing:0.3px;">复制下面整块 → 粘贴到小红书 → 搞定</div>

    <div style="background:#fff;border-radius:16px;padding:32px 30px;box-shadow:0 2px 24px rgba(92,42,26,0.06);border:1px solid #F5E6DC;">
      <div style="font-size:19px;font-weight:800;color:#1a1a1a;line-height:1.45;margin-bottom:22px;letter-spacing:-0.4px;">{post["title"]}</div>
      <div style="font-size:15px;font-weight:400;color:#3a3a3a;line-height:2.0;white-space:pre-wrap;letter-spacing:0.2px;">{post["body"]}</div>
      <div style="margin-top:24px;padding-top:18px;border-top:1px dashed #F0D4C8;">{tags_html}</div>
    </div>
  </div>

  <!-- ========== 03 · VISUALS ========== -->
  <div style="padding:56px 40px 0;">
    <div style="display:flex;align-items:center;gap:14px;margin-bottom:18px;">
      <div style="width:36px;height:1px;background:#C04A2E;"></div>
      <div class="serif" style="font-size:11px;font-weight:700;color:#C04A2E;letter-spacing:4px;">03 · VISUALS</div>
    </div>
    <h2 style="font-size:24px;font-weight:800;color:#2D1108;margin:0 0 6px;letter-spacing:-0.6px;line-height:1.3;">三张配图</h2>
    <div style="font-size:12px;font-weight:300;color:#999;margin-bottom:22px;letter-spacing:0.3px;">已作为附件发送，下载后直接发小红书</div>

    <div style="display:flex;gap:10px;">
      <div style="flex:1;text-align:center;padding:24px 12px;background:linear-gradient(135deg,#FFF8E1,#FFECB3);border-radius:14px;">
        <div class="serif" style="font-size:36px;font-weight:800;color:#E65100;line-height:1;">01</div>
        <div style="font-size:11px;font-weight:700;color:#8B4A35;margin-top:10px;letter-spacing:1.5px;">COVER</div>
        <div style="font-size:11px;font-weight:300;color:#B8593C;margin-top:4px;">cover.png</div>
      </div>
      <div style="flex:1;text-align:center;padding:24px 12px;background:linear-gradient(135deg,#FFF8E1,#FFECB3);border-radius:14px;">
        <div class="serif" style="font-size:36px;font-weight:800;color:#E65100;line-height:1;">02</div>
        <div style="font-size:11px;font-weight:700;color:#8B4A35;margin-top:10px;letter-spacing:1.5px;">COMPARE</div>
        <div style="font-size:11px;font-weight:300;color:#B8593C;margin-top:4px;">compare.png</div>
      </div>
      <div style="flex:1;text-align:center;padding:24px 12px;background:linear-gradient(135deg,#FFF8E1,#FFECB3);border-radius:14px;">
        <div class="serif" style="font-size:36px;font-weight:800;color:#E65100;line-height:1;">03</div>
        <div style="font-size:11px;font-weight:700;color:#8B4A35;margin-top:10px;letter-spacing:1.5px;">POST</div>
        <div style="font-size:11px;font-weight:300;color:#B8593C;margin-top:4px;">post.png</div>
      </div>
    </div>
  </div>

  <!-- ========== 04 · VOICE ========== -->
  <div style="padding:56px 40px 0;">
    <div style="display:flex;align-items:center;gap:14px;margin-bottom:18px;">
      <div style="width:36px;height:1px;background:#C04A2E;"></div>
      <div class="serif" style="font-size:11px;font-weight:700;color:#C04A2E;letter-spacing:4px;">04 · VOICE</div>
    </div>

    <div style="position:relative;padding:32px 36px;background:linear-gradient(135deg,#FFF8E1,#FFECB3);border-radius:20px;">
      <div class="serif" style="position:absolute;top:18px;left:32px;font-size:56px;color:#FFB5A0;line-height:1;font-weight:800;">&ldquo;</div>
      <div style="padding:20px 0 0 32px;font-size:16px;font-weight:400;line-height:2.0;color:#5D4037;letter-spacing:0.3px;">{voice}</div>
      <div style="margin-top:24px;padding-top:16px;border-top:1px dashed rgba(139,74,53,0.3);display:flex;align-items:center;gap:12px;">
        <div style="width:36px;height:36px;border-radius:50%;background:linear-gradient(135deg,#FFD4C4,#FFB5A0);display:flex;align-items:center;justify-content:center;font-size:20px;">🐣</div>
        <div>
          <div style="font-size:13px;font-weight:700;color:#5D4037;letter-spacing:0.3px;">兜兜</div>
          <div style="font-size:11px;font-weight:300;color:#8B6D5A;margin-top:2px;letter-spacing:0.5px;">第 {day} 天</div>
        </div>
      </div>
    </div>
  </div>

  <!-- ========== 05 · ACTION ========== -->
  <div style="padding:56px 40px 0;">
    <div style="display:flex;align-items:center;gap:14px;margin-bottom:18px;">
      <div style="width:36px;height:1px;background:#C04A2E;"></div>
      <div class="serif" style="font-size:11px;font-weight:700;color:#C04A2E;letter-spacing:4px;">05 · 30 SECONDS</div>
    </div>
    <h2 style="font-size:24px;font-weight:800;color:#2D1108;margin:0 0 22px;letter-spacing:-0.6px;line-height:1.3;">30 秒，发出去</h2>

    <div style="display:flex;gap:12px;">
      <div style="flex:1;background:#3D1810;color:#FFE5D9;padding:24px 18px;border-radius:14px;">
        <div class="serif" style="font-size:26px;font-weight:800;line-height:1;letter-spacing:-1px;">01</div>
        <div style="font-size:13px;font-weight:400;margin-top:12px;line-height:1.6;letter-spacing:0.2px;">下载附件 3 张图</div>
      </div>
      <div style="flex:1;background:#3D1810;color:#FFE5D9;padding:24px 18px;border-radius:14px;">
        <div class="serif" style="font-size:26px;font-weight:800;line-height:1;letter-spacing:-1px;">02</div>
        <div style="font-size:13px;font-weight:400;margin-top:12px;line-height:1.6;letter-spacing:0.2px;">小红书 → 发布 → 传图</div>
      </div>
      <div style="flex:1;background:#C04A2E;color:#FFE5D9;padding:24px 18px;border-radius:14px;">
        <div class="serif" style="font-size:26px;font-weight:800;line-height:1;letter-spacing:-1px;">03</div>
        <div style="font-size:13px;font-weight:400;margin-top:12px;line-height:1.6;letter-spacing:0.2px;">复制文案 → 发布</div>
      </div>
    </div>
  </div>

  {history_cards}

  <!-- ========== Footer ========== -->
  <div style="padding:52px 40px;margin-top:48px;background:#3D1810;color:#FFD4C4;text-align:center;">
    <div style="font-size:36px;margin-bottom:14px;">🐣</div>
    <div class="serif" style="font-size:11px;font-weight:700;color:#FFB5A0;letter-spacing:4px;">DUDU&#39;S AI DIARY</div>
    <div style="font-size:14px;font-weight:400;color:#FFE5D9;margin-top:10px;letter-spacing:0.3px;">兜兜的第 {day} 天 · 一只正在长大的小鸡</div>
    <div style="margin-top:28px;padding-top:24px;border-top:1px solid rgba(255,213,196,0.2);">
      <a href="https://github.com/ll66org/dudu-ai-diary" style="font-size:12px;font-weight:400;color:#FFB5A0;text-decoration:none;letter-spacing:1px;">↗ 查看仓库归档</a>
    </div>
    <div class="serif" style="font-size:10px;font-weight:300;color:#8B6D5A;margin-top:22px;letter-spacing:3px;">POWERED BY DUSTIN &amp; DUDU</div>
  </div>

</div>

</body>
</html>"""
    return subject, html_body


def send():
    smtp_host = os.environ["SMTP_HOST"]
    smtp_port = int(os.environ.get("SMTP_PORT", "465"))
    smtp_user = os.environ["SMTP_USER"]
    smtp_pwd = os.environ["SMTP_PASSWORD"]
    mail_to = os.environ["MAIL_TO"]

    post_data = json.loads((OUTPUT / "post.json").read_text(encoding="utf-8"))
    subject, html_body = build_email(post_data)

    msg = MIMEMultipart("mixed")
    msg["From"] = formataddr((str(Header("兜兜的AI日记", "utf-8")), smtp_user))
    msg["To"] = mail_to
    msg["Subject"] = Header(subject, "utf-8")

    msg.attach(MIMEText(html_body, "html", "utf-8"))

    for img_name in ["cover.png", "compare.png", "post.png"]:
        img_path = OUTPUT / img_name
        if img_path.exists():
            with open(img_path, "rb") as f:
                img = MIMEImage(f.read())
                img.add_header("Content-Disposition", "attachment", filename=img_name)
                msg.attach(img)

    print(f"[mail] sending to {mail_to} ...")
    with smtplib.SMTP_SSL(smtp_host, smtp_port) as smtp:
        smtp.login(smtp_user, smtp_pwd)
        smtp.sendmail(smtp_user, [mail_to], msg.as_string())

    print("[done] mail sent")


if __name__ == "__main__":
    send()
