"""dudu notify - magazine-style email"""
import os
import smtplib
import json
import base64
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.utils import formataddr
from email.header import Header
from pathlib import Path

ROOT = Path(__file__).parent.parent
OUTPUT = ROOT / "output"


def encode_image_cid(img_path):
    """读取图片并返回 base64 数据，用于内嵌"""
    if not img_path.exists():
        return None
    with open(img_path, "rb") as f:
        return base64.b64encode(f.read()).decode()


def build_email(post_data):
    day = post_data["meta"]["day"]
    topic = post_data["selected_topic"]
    post = post_data["post"]
    voice = post_data.get("dudu_voice", "")
    date_str = post_data["meta"]["generated_at"][:10]

    # 历史记录
    history = []
    try:
        memory_file = ROOT / "memory" / "growth.json"
        if memory_file.exists():
            mem = json.loads(memory_file.read_text(encoding="utf-8"))
            history = mem.get("history", [])
    except Exception:
        history = []

    total_days = len(history)

    subject = f"Vol.{day:03d} | {post['title']}"

    # 话题标签拼接
    tags_html = "".join([
        f'<span style="display:inline-block;font-size:12px;color:#C04A2E;background:#FFF3ED;'
        f'padding:4px 10px;border-radius:100px;margin:3px 4px 3px 0;font-weight:500;">{t}</span>'
        for t in post.get("tags", [])
    ])

    # 历史浏览卡（最多显示最近 3 篇）
    history_cards = ""
    if len(history) > 1:
        recent = history[-4:-1][::-1]  # 最近 3 篇（不含今天）
        if recent:
            cards = "".join([
                f'''
                <div style="flex:1;min-width:0;background:#fff;border:1px solid #F5E6DC;
                border-radius:12px;padding:12px;margin-right:8px;">
                  <div style="font-size:10px;color:#999;letter-spacing:1px;margin-bottom:4px;">DAY {h["day"]:03d}</div>
                  <div style="font-size:12px;color:#666;line-height:1.4;
                  overflow:hidden;text-overflow:ellipsis;display:-webkit-box;
                  -webkit-line-clamp:2;-webkit-box-orient:vertical;">{h["topic"][:40]}</div>
                </div>
                ''' for h in recent
            ])
            history_cards = f'''
            <div style="margin-top:40px;padding:20px;background:#FDF8F3;border-radius:16px;">
              <div style="font-size:11px;color:#B8593C;letter-spacing:2px;font-weight:700;margin-bottom:10px;">
                兜兜的成长足迹 · RECENT
              </div>
              <div style="display:flex;">{cards}</div>
            </div>
            '''

    html_body = f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#F5EDE4;font-family:-apple-system,BlinkMacSystemFont,'PingFang SC','Microsoft YaHei',sans-serif;">

<div style="max-width:640px;margin:0 auto;background:#FFFBF5;">

  <!-- Magazine Cover Header -->
  <div style="position:relative;padding:48px 40px 40px;background:linear-gradient(160deg,#FFE5D9 0%,#FFD4C4 40%,#FFB5A0 100%);overflow:hidden;">
    <div style="position:absolute;top:-60px;right:-60px;width:240px;height:240px;
    background:radial-gradient(circle,rgba(255,255,255,0.6),transparent 70%);border-radius:50%;"></div>
    <div style="position:absolute;bottom:-40px;left:-40px;width:160px;height:160px;
    background:radial-gradient(circle,rgba(255,255,255,0.3),transparent 70%);border-radius:50%;"></div>

    <!-- Top meta -->
    <div style="position:relative;display:flex;justify-content:space-between;align-items:center;
    padding-bottom:32px;border-bottom:1px solid rgba(92,42,26,0.15);">
      <div style="font-size:11px;color:#5C2A1A;letter-spacing:3px;font-weight:700;">DUDU'S AI DIARY</div>
      <div style="font-size:11px;color:#8B4A35;letter-spacing:1px;">{date_str}</div>
    </div>

    <!-- Issue number -->
    <div style="position:relative;margin-top:32px;display:flex;align-items:flex-end;gap:20px;">
      <div style="font-size:100px;line-height:0.9;font-weight:800;color:#5C2A1A;letter-spacing:-4px;font-family:Georgia,serif;">
        {day:03d}
      </div>
      <div style="padding-bottom:12px;">
        <div style="font-size:11px;color:#8B4A35;letter-spacing:2px;font-weight:700;">VOLUME</div>
        <div style="font-size:13px;color:#5C2A1A;margin-top:4px;">兜兜的第 {day} 天 · 一只小鸡的成长日记</div>
      </div>
    </div>

    <!-- Title -->
    <div style="position:relative;margin-top:28px;font-size:26px;font-weight:800;color:#3D1810;
    line-height:1.3;letter-spacing:-0.5px;max-width:480px;">
      {post["title"]}
    </div>

    <!-- Stats -->
    <div style="position:relative;margin-top:32px;display:flex;gap:24px;">
      <div>
        <div style="font-size:10px;color:#8B4A35;letter-spacing:1.5px;font-weight:700;">TOPIC</div>
        <div style="font-size:13px;color:#5C2A1A;margin-top:4px;font-weight:600;">{topic["source"]}</div>
      </div>
      <div style="width:1px;background:rgba(92,42,26,0.2);"></div>
      <div>
        <div style="font-size:10px;color:#8B4A35;letter-spacing:1.5px;font-weight:700;">STREAK</div>
        <div style="font-size:13px;color:#5C2A1A;margin-top:4px;font-weight:600;">已连更 {total_days} 天</div>
      </div>
    </div>
  </div>

  <!-- Section 01: Why This Topic -->
  <div style="padding:40px 40px 0;">
    <div style="display:flex;align-items:center;gap:12px;margin-bottom:20px;">
      <div style="width:32px;height:1px;background:#C04A2E;"></div>
      <div style="font-size:11px;color:#C04A2E;letter-spacing:3px;font-weight:700;">01 · WHY</div>
    </div>
    <h2 style="font-size:20px;color:#3D1810;margin:0 0 16px;font-weight:700;letter-spacing:-0.3px;">
      为什么是今天这条？
    </h2>

    <div style="background:#FFF8F2;border-radius:14px;padding:20px 22px;border-left:3px solid #FFB5A0;">
      <div style="display:flex;gap:10px;margin-bottom:10px;">
        <div style="font-size:11px;color:#B8593C;background:#FFE5D9;padding:3px 10px;border-radius:100px;font-weight:600;">选题</div>
        <div style="font-size:14px;color:#3D1810;font-weight:600;flex:1;line-height:1.5;">{topic["title"]}</div>
      </div>
      <div style="padding:10px 0 8px;border-top:1px dashed #F0D4C8;margin-top:12px;">
        <div style="font-size:11px;color:#8B4A35;letter-spacing:1.5px;font-weight:700;margin-bottom:4px;">DUDU PICKS</div>
        <div style="font-size:14px;color:#555;line-height:1.7;">{topic["why_picked"]}</div>
      </div>
      <div style="padding-top:8px;">
        <div style="font-size:11px;color:#8B4A35;letter-spacing:1.5px;font-weight:700;margin-bottom:4px;">DESIGNER ANGLE</div>
        <div style="font-size:14px;color:#555;line-height:1.7;">{topic["designer_angle"]}</div>
      </div>
      <div style="margin-top:14px;padding-top:12px;border-top:1px dashed #F0D4C8;">
        <a href="{topic["url"]}" style="font-size:12px;color:#5B7FFF;text-decoration:none;">
          ↗ 原文链接
        </a>
      </div>
    </div>
  </div>

  <!-- Section 02: The Post -->
  <div style="padding:48px 40px 0;">
    <div style="display:flex;align-items:center;gap:12px;margin-bottom:20px;">
      <div style="width:32px;height:1px;background:#C04A2E;"></div>
      <div style="font-size:11px;color:#C04A2E;letter-spacing:3px;font-weight:700;">02 · POST</div>
    </div>
    <h2 style="font-size:20px;color:#3D1810;margin:0 0 6px;font-weight:700;letter-spacing:-0.3px;">
      今日小红书文案
    </h2>
    <div style="font-size:12px;color:#999;margin-bottom:18px;">复制下面整块 → 粘贴到小红书 → 搞定</div>

    <div style="background:#fff;border-radius:16px;padding:28px;box-shadow:0 2px 20px rgba(92,42,26,0.06);border:1px solid #F5E6DC;">
      <div style="font-size:17px;color:#222;font-weight:700;line-height:1.5;margin-bottom:18px;letter-spacing:-0.2px;">
        {post["title"]}
      </div>
      <div style="font-size:15px;color:#444;line-height:1.9;white-space:pre-wrap;">{post["body"]}</div>
      <div style="margin-top:20px;padding-top:16px;border-top:1px dashed #F0D4C8;">
        {tags_html}
      </div>
    </div>
  </div>

  <!-- Section 03: Visuals -->
  <div style="padding:48px 40px 0;">
    <div style="display:flex;align-items:center;gap:12px;margin-bottom:20px;">
      <div style="width:32px;height:1px;background:#C04A2E;"></div>
      <div style="font-size:11px;color:#C04A2E;letter-spacing:3px;font-weight:700;">03 · VISUALS</div>
    </div>
    <h2 style="font-size:20px;color:#3D1810;margin:0 0 6px;font-weight:700;letter-spacing:-0.3px;">
      三张配图
    </h2>
    <div style="font-size:12px;color:#999;margin-bottom:20px;">已作为附件发送，下载后直接发小红书</div>

    <div style="display:flex;gap:10px;">
      <div style="flex:1;text-align:center;padding:20px 12px;background:linear-gradient(135deg,#FFF8E1,#FFECB3);border-radius:12px;">
        <div style="font-size:32px;font-weight:800;color:#E65100;line-height:1;font-family:Georgia,serif;">01</div>
        <div style="font-size:11px;color:#8B4A35;margin-top:8px;letter-spacing:1px;font-weight:600;">COVER</div>
        <div style="font-size:11px;color:#B8593C;margin-top:4px;">cover.png</div>
      </div>
      <div style="flex:1;text-align:center;padding:20px 12px;background:linear-gradient(135deg,#FFF8E1,#FFECB3);border-radius:12px;">
        <div style="font-size:32px;font-weight:800;color:#E65100;line-height:1;font-family:Georgia,serif;">02</div>
        <div style="font-size:11px;color:#8B4A35;margin-top:8px;letter-spacing:1px;font-weight:600;">COMPARE</div>
        <div style="font-size:11px;color:#B8593C;margin-top:4px;">compare.png</div>
      </div>
      <div style="flex:1;text-align:center;padding:20px 12px;background:linear-gradient(135deg,#FFF8E1,#FFECB3);border-radius:12px;">
        <div style="font-size:32px;font-weight:800;color:#E65100;line-height:1;font-family:Georgia,serif;">03</div>
        <div style="font-size:11px;color:#8B4A35;margin-top:8px;letter-spacing:1px;font-weight:600;">POST</div>
        <div style="font-size:11px;color:#B8593C;margin-top:4px;">post.png</div>
      </div>
    </div>
  </div>

  <!-- Section 04: Dudu's Voice -->
  <div style="padding:48px 40px 0;">
    <div style="display:flex;align-items:center;gap:12px;margin-bottom:20px;">
      <div style="width:32px;height:1px;background:#C04A2E;"></div>
      <div style="font-size:11px;color:#C04A2E;letter-spacing:3px;font-weight:700;">04 · VOICE</div>
    </div>

    <div style="position:relative;padding:28px 32px;background:linear-gradient(135deg,#FFF8E1,#FFECB3);border-radius:20px;">
      <div style="position:absolute;top:16px;left:28px;font-size:48px;color:#FFB5A0;line-height:1;font-family:Georgia,serif;">"</div>
      <div style="padding:16px 0 0 28px;font-size:15px;line-height:1.9;color:#5D4037;font-style:italic;">
        {voice}
      </div>
      <div style="margin-top:20px;padding-top:14px;border-top:1px dashed rgba(139,74,53,0.3);display:flex;align-items:center;gap:10px;">
        <div style="width:32px;height:32px;border-radius:50%;background:linear-gradient(135deg,#FFD4C4,#FFB5A0);display:flex;align-items:center;justify-content:center;font-size:18px;">🐣</div>
        <div>
          <div style="font-size:12px;color:#5D4037;font-weight:700;">兜兜</div>
          <div style="font-size:11px;color:#8B6D5A;">第 {day} 天</div>
        </div>
      </div>
    </div>
  </div>

  <!-- Section 05: Action -->
  <div style="padding:48px 40px 0;">
    <div style="display:flex;align-items:center;gap:12px;margin-bottom:20px;">
      <div style="width:32px;height:1px;background:#C04A2E;"></div>
      <div style="font-size:11px;color:#C04A2E;letter-spacing:3px;font-weight:700;">05 · 30 SECONDS</div>
    </div>
    <h2 style="font-size:20px;color:#3D1810;margin:0 0 20px;font-weight:700;letter-spacing:-0.3px;">
      30 秒，发出去
    </h2>

    <div style="display:flex;gap:12px;">
      <div style="flex:1;background:#3D1810;color:#FFE5D9;padding:20px 16px;border-radius:14px;">
        <div style="font-size:22px;font-weight:800;font-family:Georgia,serif;line-height:1;">01</div>
        <div style="font-size:13px;margin-top:10px;line-height:1.5;">下载附件 3 张图</div>
      </div>
      <div style="flex:1;background:#3D1810;color:#FFE5D9;padding:20px 16px;border-radius:14px;">
        <div style="font-size:22px;font-weight:800;font-family:Georgia,serif;line-height:1;">02</div>
        <div style="font-size:13px;margin-top:10px;line-height:1.5;">小红书 → 发布 → 传图</div>
      </div>
      <div style="flex:1;background:#C04A2E;color:#FFE5D9;padding:20px 16px;border-radius:14px;">
        <div style="font-size:22px;font-weight:800;font-family:Georgia,serif;line-height:1;">03</div>
        <div style="font-size:13px;margin-top:10px;line-height:1.5;">复制文案 → 发布</div>
      </div>
    </div>
  </div>

  {history_cards if history_cards else ''}

  <!-- Footer -->
  <div style="padding:48px 40px;margin-top:40px;background:#3D1810;color:#FFD4C4;text-align:center;">
    <div style="font-size:32px;margin-bottom:12px;">🐣</div>
    <div style="font-size:11px;letter-spacing:3px;color:#FFB5A0;font-weight:700;">DUDU'S AI DIARY</div>
    <div style="font-size:14px;color:#FFE5D9;margin-top:8px;">兜兜的第 {day} 天 · 一只正在长大的小鸡</div>
    <div style="margin-top:24px;padding-top:24px;border-top:1px solid rgba(255,213,196,0.2);">
      <a href="https://github.com/ll66org/dudu-ai-diary" style="font-size:12px;color:#FFB5A0;text-decoration:none;letter-spacing:1px;">
        ↗ 查看仓库归档
      </a>
    </div>
    <div style="font-size:10px;color:#8B6D5A;margin-top:20px;letter-spacing:2px;">
      POWERED BY DUSTIN & DUDU
    </div>
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
