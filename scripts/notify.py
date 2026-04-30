"""兜兜的邮件推送器 🐣"""
import os
import smtplib
import json
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.utils import formataddr
from email.header import Header
from pathlib import Path

ROOT = Path(__file__).parent.parent
OUTPUT = ROOT / "output"


def build_email(post_data):
    day = post_data["meta"]["day"]
    topic = post_data["selected_topic"]
    post = post_data["post"]
    voice = post_data.get("dudu_voice", "")

    subject = f"🐣 兜兜的第 {day} 天｜{post['title']}"

    html_body = f"""
<div style="font-family:-apple-system,'PingFang SC',sans-serif;max-width:640px;margin:0 auto;padding:24px;background:#FFF8F0;color:#333;">

  <div style="background:linear-gradient(135deg,#FFE5D9,#FFB5A0);padding:24px;border-radius:16px;margin-bottom:24px;text-align:center;">
    <div style="font-size:36px;">🐣</div>
    <div style="font-size:22px;font-weight:800;color:#5C2A1A;margin-top:8px;">兜兜的第 {day} 天</div>
    <div style="font-size:13px;color:#8B4A35;margin-top:4px;">{post_data["meta"]["generated_at"][:10]}</div>
  </div>

  <h2 style="color:#C04A2E;border-bottom:2px solid #FFD4C4;padding-bottom:8px;">📌 今日选题</h2>
  <p><strong>{topic["title"]}</strong></p>
  <p style="color:#666;font-size:13px;">来源: <a href="{topic["url"]}" style="color:#5B7FFF;">{topic["source"]}</a></p>
  <p>🐣 <strong>兜兜为什么选它</strong>: {topic["why_picked"]}</p>
  <p>🎨 <strong>设计师视角</strong>: {topic["designer_angle"]}</p>

  <h2 style="color:#C04A2E;border-bottom:2px solid #FFD4C4;padding-bottom:8px;margin-top:32px;">📝 完整文案（直接复制发布）</h2>
  <div style="background:#fff;padding:20px;border-radius:12px;border:1px dashed #FFD4C4;white-space:pre-wrap;line-height:1.8;font-size:14px;">{post["body"]}

{" ".join(post["tags"])}</div>

  <h2 style="color:#C04A2E;border-bottom:2px solid #FFD4C4;padding-bottom:8px;margin-top:32px;">🖼️ 三张配图（附件下载）</h2>
  <p style="color:#666;">已附上 3 张图：cover.png（封面）、compare.png（对比）、post.png（正文）</p>

  <h2 style="color:#C04A2E;border-bottom:2px solid #FFD4C4;padding-bottom:8px;margin-top:32px;">💌 兜兜的悄悄话</h2>
  <div style="background:linear-gradient(135deg,#FFF8E1,#FFECB3);padding:16px;border-radius:12px;font-size:14px;line-height:1.8;color:#5D4037;">
    {voice}
  </div>

  <h2 style="color:#C04A2E;border-bottom:2px solid #FFD4C4;padding-bottom:8px;margin-top:32px;">🎬 你要做的事（30 秒）</h2>
  <ol style="line-height:1.8;">
    <li>下载附件中的 3 张图</li>
    <li>打开小红书 App → 发布 → 上传 3 张图</li>
    <li>复制上面的文案 → 粘贴 → 发布（或定时 21:30）</li>
  </ol>

  <div style="margin-top:40px;padding-top:20px;border-top:1px dashed #FFD4C4;text-align:center;color:#999;font-size:13px;">
    —— 兜兜的第 {day} 天 🐣<br>
    <a href="https://github.com/ll66org/dudu-ai-diary" style="color:#5B7FFF;">查看仓库归档</a>
  </div>

</div>
"""
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
    msg["From"] = formataddr((str(Header("兜兜 🐣", "utf-8")), smtp_user))
    msg["To"] = mail_to
    msg["Subject"] = Header(subject, "utf-8")

    msg.attach(MIMEText(html_body, "html", "utf-8"))

    # 附图
    for img_name in ["cover.png", "compare.png", "post.png"]:
        img_path = OUTPUT / img_name
        if img_path.exists():
            with open(img_path, "rb") as f:
                img = MIMEImage(f.read())
                img.add_header("Content-Disposition", "attachment", filename=img_name)
                msg.attach(img)

    print(f"📬 发送邮件到 {mail_to} ...")
    with smtplib.SMTP_SSL(smtp_host, smtp_port) as smtp:
        smtp.login(smtp_user, smtp_pwd)
        smtp.sendmail(smtp_user, [mail_to], msg.as_string())

    print("✅ 邮件发送完成")


if __name__ == "__main__":
    send()
