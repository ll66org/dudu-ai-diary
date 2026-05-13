"""dudu compose v4 - 物理日期 + 干货快讯 + 三段式正文"""
import os
import json
import re
from datetime import datetime, date
from pathlib import Path
from openai import OpenAI

ROOT = Path(__file__).parent.parent
OUTPUT = ROOT / "output"
PROMPT_FILE = ROOT / "prompts" / "dudu-system.md"
MEMORY_FILE = ROOT / "memory" / "growth.json"
POSTS_DIR = ROOT / "posts"
POSTS_DIR.mkdir(exist_ok=True)

# 兜兜诞生日，与 fetch.py 保持一致
DUDU_BIRTHDAY = date(2026, 4, 24)


def get_dudu_day():
    today = date.today()
    return max(1, (today - DUDU_BIRTHDAY).days + 1)


def load_system_prompt():
    return PROMPT_FILE.read_text(encoding="utf-8")


def load_memory():
    if MEMORY_FILE.exists():
        try:
            return json.loads(MEMORY_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"day_count": 0, "history": []}


def save_memory(mem):
    MEMORY_FILE.parent.mkdir(exist_ok=True)
    MEMORY_FILE.write_text(json.dumps(mem, ensure_ascii=False, indent=2), encoding="utf-8")


def load_candidates():
    f = OUTPUT / "candidates.json"
    if not f.exists():
        raise SystemExit("no candidates, run fetch.py first")
    return json.loads(f.read_text(encoding="utf-8"))


def load_meta():
    f = OUTPUT / "fetch_meta.json"
    if f.exists():
        return json.loads(f.read_text(encoding="utf-8"))
    return {}


def load_briefing():
    f = OUTPUT / "briefing.json"
    if f.exists():
        return json.loads(f.read_text(encoding="utf-8"))
    return []


def get_recent_history_brief(memory, days=7):
    history = memory.get("history", [])
    recent = history[-days:] if history else []
    if not recent:
        return "（这是兜兜成长路上前几天，还没有太多历史）"
    lines = []
    for h in recent:
        day = h.get("day", "?")
        topic = h.get("topic", "")
        source = h.get("source", "")
        lines.append(f"- Day {day}: [{source}] {topic}")
    return "\n".join(lines)


def compose():
    client = OpenAI(
        api_key=os.environ["DEEPSEEK_API_KEY"],
        base_url="https://api.deepseek.com",
    )

    candidates = load_candidates()
    meta = load_meta()
    briefing = load_briefing()

    # 关键：使用物理日期计算的 day，不再依赖 memory.day_count
    dudu_day = meta.get("dudu_day") or get_dudu_day()
    today = date.today().isoformat()

    print(f"[compose] 兜兜的第 {dudu_day} 天（物理日期）")
    print(f"[compose] 今日快讯 {len(briefing)} 条")

    if not candidates:
        print("[warn] 没有任何候选内容，退出")
        return

    memory = load_memory()
    history_brief = get_recent_history_brief(memory, days=7)

    is_fallback = meta.get("mode") == "fallback" or any(
        c.get("fallback_mode") for c in candidates
    )

    first_candidate = candidates[0]

    # ========== 降级模式 ==========
    if is_fallback and first_candidate.get("fallback_data"):
        print(f"[compose] 降级模式: {first_candidate['source']}")
        result = first_candidate["fallback_data"]

        post_result = generate_post_from_analysis(
            client, result, dudu_day, history_brief, briefing
        )

        post_result["meta"] = {
            "day": dudu_day,
            "date": today,
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "mode": "fallback",
            "angle": result.get("selected_topic", {}).get("angle", ""),
            "section": result.get("selected_topic", {}).get("section", ""),
        }
        post_result["briefing"] = briefing  # 把快讯一并塞进去给 notify 用

        post_file = POSTS_DIR / f"{today}-day-{dudu_day:03d}.json"
        post_file.write_text(json.dumps(post_result, ensure_ascii=False, indent=2), encoding="utf-8")
        (OUTPUT / "post.json").write_text(json.dumps(post_result, ensure_ascii=False, indent=2), encoding="utf-8")

        # memory 仍然记录历史用于反重复，但不再用 day_count 计算第几天
        memory["day_count"] = dudu_day
        memory["history"].append({
            "day": dudu_day,
            "date": today,
            "topic": post_result["selected_topic"]["title"],
            "source": post_result["selected_topic"]["source"],
            "mode": "fallback",
            "angle": result.get("selected_topic", {}).get("angle", ""),
            "section": result.get("selected_topic", {}).get("section", ""),
        })
        save_memory(memory)

        print(f"[done] day {dudu_day} (降级模式) composed")
        print(f"[topic] {post_result['selected_topic']['title']}")
        return

    # ========== 主流程：今日精选 / RSS ==========
    print(f"[compose] 主模式 day {dudu_day}，候选 {len(candidates)} 条")

    candidates_brief = [
        {
            "title": c["title"],
            "summary": c["summary"][:200],
            "source": c["source"],
            "url": c["url"],
            "category": c.get("category", ""),
        }
        for c in candidates[:12]
    ]

    # ★ 关键改动：主题必须从今日 briefing 头部挑选，保证邮件「今日干货」和「主题」是一体的
    # briefing 是已经按设计师相关度排序的真实新闻，主题就在 top-3 里选
    briefing_for_prompt = ""
    locked_topic_hint = ""
    if briefing:
        items_text = "\n".join([
            f"  [{i+1}] {b['title']}\n      来源: {b['source']}\n      链接: {b['url']}\n      摘要: {b.get('summary','')[:160]}"
            for i, b in enumerate(briefing[:5])
        ])
        briefing_for_prompt = f"""
【今日 AI 圈 5 条真实快讯（已按设计师相关度排序，必读）】
{items_text}
"""
        locked_topic_hint = """
【选题硬约束 — 务必遵守】
今天的主题（selected_topic）必须从上面 5 条快讯的 [1]、[2]、[3] 中三选一。
- 优先选 [1]，除非 [1] 和最近 7 天选题重复
- 主题的 title / source / url 必须直接复用快讯中的对应字段（保持事实一致性）
- 这样做的目的：邮件首屏 "今日 5 条干货" 和正文主题形成一体，用户先扫快讯再看深度解读
"""

    user_prompt = f"""今天是兜兜的第 {dudu_day} 天（兜兜诞生于 2026-04-24）。

【兜兜最近 7 天写过的选题（绝对不能重复）】
{history_brief}

{briefing_for_prompt}

{locked_topic_hint}

【备用候选池（仅当上面 5 条快讯全部和历史重复时才用，正常情况不要碰）】
{json.dumps(candidates_brief[:6], ensure_ascii=False, indent=2)}

【内容硬性要求】
1. selected_topic 必须直接来自今日 5 条快讯之一（优先 [1]）—— title / source / url 字段照搬
2. 正文 body 必须用三段式结构：
   - 第一段（钩子+事实）：直接说今天 AI 圈这件具体的事（要带原文里出现的产品名/数据/场景）
   - 第二段（兜兜解读）：从设计师视角看这件事意味着什么，给出 2-3 个具体观察（用 ▸ 列出）
   - 第三段（💭 兜兜动手建议）：1 个 5 分钟可试的具体动作
3. 不要写成"我感觉""我觉得 AI 真有意思"这种空话，每段都要有具体名词
4. visuals.compare_left/right 也要紧扣今日选题（不要用通用的"以前/现在"模板）
5. body 字段签名档替换为"—— 兜兜的第 {dudu_day} 天"

输出严格合法的 JSON，不要额外说明。"""

    print("[compose] calling DeepSeek...")

    resp = client.chat.completions.create(
        model="deepseek-chat",
        messages=[
            {"role": "system", "content": load_system_prompt()},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.8,
        response_format={"type": "json_object"},
    )

    raw = resp.choices[0].message.content
    raw = re.sub(r"^\`\`\`json\s*|\s*\`\`\`$", "", raw.strip())
    result = json.loads(raw)

    result["meta"] = {
        "day": dudu_day,
        "date": today,
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "mode": meta.get("mode", "rss"),
    }

    # ★ 兜底校验：主题必须在今日 briefing 里。如果 LLM 自由发挥跑偏了，强制纠正
    if briefing:
        briefing_urls = {b.get("url", "") for b in briefing if b.get("url")}
        briefing_titles = {b.get("title", "") for b in briefing if b.get("title")}
        chosen_url = result.get("selected_topic", {}).get("url", "")
        chosen_title = result.get("selected_topic", {}).get("title", "")
        if chosen_url not in briefing_urls and chosen_title not in briefing_titles:
            print(f"[warn] LLM 选题脱离 briefing，强制纠正为 briefing[0]")
            print(f"       原选题: {chosen_title[:50]}")
            print(f"       新选题: {briefing[0].get('title', '')[:50]}")
            top = briefing[0]
            result["selected_topic"]["title"] = top.get("title", "")
            result["selected_topic"]["source"] = top.get("source", "")
            result["selected_topic"]["url"] = top.get("url", "")
            # 提示用户：why_picked / designer_angle 仍由 LLM 写，但事实层用 briefing 真实数据
            if not result["selected_topic"].get("why_picked"):
                result["selected_topic"]["why_picked"] = f"今天 AI 圈最值得设计师关注的一条 — {top.get('source','')}发的"

    result["briefing"] = briefing

    post_file = POSTS_DIR / f"{today}-day-{dudu_day:03d}.json"
    post_file.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUTPUT / "post.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    memory["day_count"] = dudu_day
    memory["history"].append({
        "day": dudu_day,
        "date": today,
        "topic": result["selected_topic"]["title"],
        "source": result["selected_topic"]["source"],
        "mode": meta.get("mode", "rss"),
    })
    save_memory(memory)

    print(f"[done] day {dudu_day} composed")
    print(f"[topic] {result['selected_topic']['title']}")


def generate_post_from_analysis(client, fallback_result, dudu_day, history_brief, briefing):
    topic = fallback_result["selected_topic"]
    analysis = fallback_result.get("analysis", "")
    recommendation = fallback_result.get("recommendation", "")

    briefing_brief = ""
    if briefing:
        items_text = "\n".join([
            f"  {i+1}. {b['title']} | {b['source']}"
            for i, b in enumerate(briefing[:5])
        ])
        briefing_brief = f"\n【今日 AI 圈快讯（参考）】\n{items_text}\n"

    prompt = f"""今天是兜兜的第 {dudu_day} 天，兜兜要做一期"设计向深度分享"。

【最近 7 天兜兜写过的选题】
{history_brief}
{briefing_brief}

今天的话题：{topic['title']}
涉及工具/概念：{topic['source']}
深度分析：
{analysis}

兜兜的推荐：
{recommendation}

请基于以上内容，按以下 JSON 格式生成完整的小红书帖子：

{{
  "selected_topic": {{
    "title": "{topic['title']}",
    "source": "{topic['source']}",
    "url": "{topic.get('url', '')}",
    "why_picked": "{topic.get('why_picked', '')}",
    "designer_angle": "{topic.get('designer_angle', '')}"
  }},
  "post": {{
    "title": "小红书标题，带 🐣，20字以内",
    "body": "三段式正文：第一段（钩子+具体事实，要有产品名/数据），第二段（兜兜的设计师视角解读 2-3 点观察），第三段（💭 兜兜动手建议，1 个 5 分钟可试的具体动作）。结尾签名 '—— 兜兜的第 {dudu_day} 天'",
    "tags": ["#标签1", "#标签2", "#标签3"]
  }},
  "visuals": {{
    "cover_kicker": "英文栏目名，4-14字符",
    "cover_main_text": "封面主标题（最多 12 字）",
    "cover_sub_text": "封面副标题（最多 20 字）",
    "cover_quote_en": "封面左下英文短句，6-10 个单词",
    "compare_headline": "对比图顶部小标题，6-10字",
    "compare_left_label": "BEFORE / MANUAL 等英文大写",
    "compare_left_title": "左侧中文标题（4-8字）",
    "compare_left_desc": "左侧具体描述（12-22字）",
    "compare_left_metric": "左侧关键数据（4-8字）",
    "compare_right_label": "AFTER / AI 等英文大写",
    "compare_right_title": "右侧中文标题（4-8字）",
    "compare_right_desc": "右侧具体描述（12-22字）",
    "compare_right_metric": "右侧关键数据（4-8字）",
    "compare_insight": "对比下方一句洞察（16-28字）",
    "highlight_emoji": "1个emoji",
    "accent_color": "sunset/ocean/forest/plum/mono/coral 六选一"
  }},
  "dudu_voice": "兜兜的真心话，50字以内"
}}

硬性要求：
- 正文必须有具体工具名/数字/场景，不能空谈
- 输出严格合法的 JSON"""

    resp = client.chat.completions.create(
        model="deepseek-chat",
        messages=[
            {
                "role": "system",
                "content": "你是一个热情的设计 AI 助手，叫兜兜。"
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0.85,
        response_format={"type": "json_object"},
    )

    raw = resp.choices[0].message.content
    raw = re.sub(r"^\`\`\`json\s*|\s*\`\`\`$", "", raw.strip())

    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        result = {
            "selected_topic": topic,
            "post": {
                "title": topic["title"],
                "body": f"{analysis}\n\n{recommendation}\n\n—— 兜兜的第 {dudu_day} 天",
                "tags": ["#设计工具", "#AI"],
            },
            "visuals": {
                "cover_kicker": "DEEP DIVE",
                "cover_main_text": topic["title"][:12],
                "cover_sub_text": topic.get("designer_angle", "")[:20],
                "cover_quote_en": "Design is thinking made visual.",
                "compare_headline": "一张图看懂区别",
                "compare_left_label": "BEFORE",
                "compare_left_title": "手动",
                "compare_left_desc": "设计师逐个调整",
                "compare_left_metric": "耗时 2h",
                "compare_right_label": "AFTER",
                "compare_right_title": "AI 加持",
                "compare_right_desc": "一句话出稿",
                "compare_right_metric": "耗时 3min",
                "compare_insight": recommendation[:28],
                "highlight_emoji": "✨",
                "accent_color": "sunset",
            },
            "dudu_voice": recommendation[:50],
        }

    return result


if __name__ == "__main__":
    compose()
