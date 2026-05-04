"""dudu compose v3 - 降级策略 + 反重复 + 历史注入"""
import os
import json
import re
from datetime import datetime
from pathlib import Path
from openai import OpenAI

ROOT = Path(__file__).parent.parent
OUTPUT = ROOT / "output"
PROMPT_FILE = ROOT / "prompts" / "dudu-system.md"
MEMORY_FILE = ROOT / "memory" / "growth.json"
POSTS_DIR = ROOT / "posts"
POSTS_DIR.mkdir(exist_ok=True)


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


def get_recent_history_brief(memory, days=7):
    """取最近 N 天的历史，转成给 AI 看的简短提示"""
    history = memory.get("history", [])
    recent = history[-days:] if history else []
    if not recent:
        return "（这是兜兜的第一篇，还没有历史）"
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

    if not candidates:
        print("[warn] 没有任何候选内容，退出")
        return

    memory = load_memory()
    day_count = memory["day_count"] + 1
    history_brief = get_recent_history_brief(memory, days=7)
    used_titles = [h.get("topic", "") for h in memory.get("history", [])[-7:]]
    used_sources = [h.get("source", "") for h in memory.get("history", [])[-7:]]

    is_fallback = meta.get("mode") == "fallback" or any(
        c.get("fallback_mode") for c in candidates
    )

    first_candidate = candidates[0]

    # ========== 降级模式 ==========
    if is_fallback and first_candidate.get("fallback_data"):
        print(f"[compose] 降级模式: {first_candidate['source']}")
        result = first_candidate["fallback_data"]

        result["meta"] = {
            "day": day_count,
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "mode": "fallback",
            "angle": result.get("selected_topic", {}).get("angle", ""),
            "section": result.get("selected_topic", {}).get("section", ""),
        }

        post_result = generate_post_from_analysis(
            client, result, day_count, history_brief, is_fallback=True
        )

        # 把 meta 补回 post_result
        post_result["meta"] = result["meta"]

        today = datetime.now().strftime("%Y-%m-%d")
        post_file = POSTS_DIR / f"{today}-day-{day_count:03d}.json"
        post_file.write_text(json.dumps(post_result, ensure_ascii=False, indent=2), encoding="utf-8")
        (OUTPUT / "post.json").write_text(json.dumps(post_result, ensure_ascii=False, indent=2), encoding="utf-8")

        memory["day_count"] = day_count
        memory["history"].append({
            "day": day_count,
            "date": today,
            "topic": post_result["selected_topic"]["title"],
            "source": post_result["selected_topic"]["source"],
            "mode": "fallback",
            "angle": result.get("selected_topic", {}).get("angle", ""),
            "section": result.get("selected_topic", {}).get("section", ""),
        })
        save_memory(memory)

        print(f"[done] day {day_count} (降级模式) composed")
        print(f"[topic] {post_result['selected_topic']['title']}")
        print(f"[saved] {post_file}")
        return

    # ========== RSS 正常模式 ==========
    print(f"[compose] RSS 模式，day {day_count}，共 {len(candidates)} 条候选")

    candidates_brief = [
        {
            "title": c["title"],
            "summary": c["summary"][:200],
            "source": c["source"],
            "url": c["url"],
        }
        for c in candidates[:10]
    ]

    user_prompt = f"""今天是兜兜的第 {day_count} 天。

【兜兜最近 7 天已经写过的选题（绝对不能重复！必须选一个新角度）】
{history_brief}

下面是兜兜今天的备选选题池（共 {len(candidates_brief)} 条），请按"设计向 AI"的标准，
从中选出 1 条**和上面历史完全不一样**的作为今天的日记主题，然后按系统提示词的要求输出完整的小红书帖子 JSON。

候选池：
{json.dumps(candidates_brief, ensure_ascii=False, indent=2)}

硬性要求：
- 选出的选题标题必须和最近 7 天的历史选题**没有任何语义重合**
- 主角工具/概念尽量和最近 3 天不同
- 如果候选池全部和历史重复，选一条最边缘、最不相关的，并在 why_picked 里说明"今天的信息池有点重复，兜兜挑了个冷门角度"
- 输出严格合法的 JSON，不要任何额外说明
- JSON 中的 body 字段，请把签名档的 N 替换成 {day_count}"""

    print("[compose] calling DeepSeek...")

    resp = client.chat.completions.create(
        model="deepseek-chat",
        messages=[
            {"role": "system", "content": load_system_prompt()},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.8,  # 稍微提高一点
        response_format={"type": "json_object"},
    )

    raw = resp.choices[0].message.content
    raw = re.sub(r"^\`\`\`json\s*|\s*\`\`\`$", "", raw.strip())
    result = json.loads(raw)

    result["meta"] = {
        "day": day_count,
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "mode": "rss",
    }

    today = datetime.now().strftime("%Y-%m-%d")
    post_file = POSTS_DIR / f"{today}-day-{day_count:03d}.json"
    post_file.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUTPUT / "post.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    memory["day_count"] = day_count
    memory["history"].append({
        "day": day_count,
        "date": today,
        "topic": result["selected_topic"]["title"],
        "source": result["selected_topic"]["source"],
        "mode": "rss",
    })
    save_memory(memory)

    print(f"[done] day {day_count} composed")
    print(f"[topic] {result['selected_topic']['title']}")
    print(f"[saved] {post_file}")


def generate_post_from_analysis(client, fallback_result, day_count, history_brief, is_fallback=False):
    """从降级模式的分析结果生成完整的小红书帖子"""
    topic = fallback_result["selected_topic"]
    analysis = fallback_result.get("analysis", "")
    recommendation = fallback_result.get("recommendation", "")

    prompt = f"""今天是兜兜的第 {day_count} 天，兜兜要做一期"设计向深度分享"。

【最近 7 天兜兜写过的选题（参考，别撞车）】
{history_brief}

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
    "title": "小红书标题，带 🐣，20字以内，要有吸引力",
    "body": "小红书正文，300-500字，用兜兜的口吻，有好奇心，有态度，敢动手，要包含：钩子 + 3个具体要点 + 💭兜兜的小思考 + 一个提问收尾 + 签名 '—— 兜兜的第 {day_count} 天'",
    "tags": ["#标签1", "#标签2", "#标签3"]
  }},
  "visuals": {{
    "cover_main_text": "封面主标题（最多 12 字）",
    "cover_sub_text": "封面副标题（最多 20 字）",
    "compare_left_label": "对比左侧标题（旧/没 AI）",
    "compare_left_desc": "对比左侧描述",
    "compare_right_label": "对比右侧标题（新/有 AI）",
    "compare_right_desc": "对比右侧描述",
    "highlight_emoji": "1个表达情绪的 emoji"
  }},
  "dudu_voice": "兜兜对这篇内容的真心话，50字以内，有个性"
}}

硬性要求：
- 正文的语言风格：5-7 岁好奇心 + 18 岁表达力的设计学徒
- 禁止用"业内人士都知道""保姆级""干货满满""家人们"等老套用语
- 要有具体的工具名、数字或场景，不能泛泛而谈
- 必须和上面历史选题保持差异化
- 输出严格合法的 JSON，不要任何额外说明"""

    resp = client.chat.completions.create(
        model="deepseek-chat",
        messages=[
            {
                "role": "system",
                "content": "你是一个热情的设计 AI 助手，叫兜兜。有好奇心，有态度，语言生动活泼，用第一人称回答问题。"
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
        print("[warn] JSON 解析失败，使用简化格式")
        result = {
            "selected_topic": topic,
            "post": {
                "title": topic["title"],
                "body": f"{analysis}\n\n{recommendation}\n\n—— 兜兜的第 {day_count} 天",
                "tags": ["#设计工具", "#AI", "#教程"],
            },
            "visuals": {
                "cover_main_text": topic["title"][:12],
                "cover_sub_text": topic.get("designer_angle", "")[:20],
                "compare_left_label": "以前",
                "compare_left_desc": "手动",
                "compare_right_label": "现在",
                "compare_right_desc": "AI 加持",
                "highlight_emoji": "✨",
            },
            "dudu_voice": recommendation[:50],
        }

    return result


if __name__ == "__main__":
    compose()
