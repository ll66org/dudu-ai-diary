"""dudu compose v2 - 支持降级策略 + 修复空内容问题"""
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
        return json.loads(MEMORY_FILE.read_text(encoding="utf-8"))
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


def compose():
    client = OpenAI(
        api_key=os.environ["DEEPSEEK_API_KEY"],
        base_url="https://api.deepseek.com",
    )

    candidates = load_candidates()
    meta = load_meta()

    if not candidates:
        print("[warn] 没有任何候选内容，尝试降级生成...")
        return

    memory = load_memory()
    day_count = memory["day_count"] + 1

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
        }

        post_result = generate_post_from_analysis(client, result, day_count, is_fallback=True)

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

下面是兜兜的备选选题池（共 {len(candidates_brief)} 条），请按"设计向 AI"的标准，
从中选出 1 条最适合的作为今天的日记主题，然后按系统提示词的要求输出完整的小红书帖子 JSON。

候选池：
{json.dumps(candidates_brief, ensure_ascii=False, indent=2)}

请输出严格合法的 JSON，不要任何额外说明。
JSON 中的 body 字段，请把签名档的 N 替换成 {day_count}。"""

    print(f"[compose] calling DeepSeek...")

    resp = client.chat.completions.create(
        model="deepseek-chat",
        messages=[
            {"role": "system", "content": load_system_prompt()},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.7,
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
    })
    save_memory(memory)

    print(f"[done] day {day_count} composed")
    print(f"[topic] {result['selected_topic']['title']}")
    print(f"[saved] {post_file}")


def generate_post_from_analysis(client, fallback_result, day_count, is_fallback=False):
    """从降级模式的分析结果生成完整的小红书帖子"""
    topic = fallback_result["selected_topic"]
    analysis = fallback_result.get("analysis", "")
    recommendation = fallback_result.get("recommendation", "")

    prompt = f"""今天是兜兜的第 {day_count} 天，兜兜要做一期"设计工具深度分析"。

工具：{topic['source']}
深度分析内容：
{analysis}

兜兜的推荐：
{recommendation}

请基于以上内容，按以下 JSON 格式生成完整的小红书帖子：

{{
  "selected_topic": {{
    "title": "{topic['title']}",
    "source": "{topic['source']}",
    "url": "{topic['url']}",
    "why_picked": "{topic['why_picked']}",
    "designer_angle": "{topic['designer_angle']}"
  }},
  "post": {{
    "title": "小红书标题，要有吸引力，20字以内",
    "body": "小红书正文，300-500字，用兜兜的口吻，有好奇心，有态度，敢动手，结尾要有签名'—— 兜兜的第 {day_count} 天'",
    "tags": ["标签1", "标签2", "标签3"]
  }},
  "visuals": {{
    "cover": {{
      "headline": "封面大标题，10字以内",
      "subheadline": "副标题",
      "theme": "配色方案，如 warm-orange 或 fresh-blue"
    }},
    "compare": {{
      "before": "Before 描述",
      "after": "After 描述"
    }}
  }},
  "dudu_voice": "兜兜对这篇内容的真心话，50字以内，有个性"
}}

要求：
- 正文的语言风格：像 5-7 岁好奇心 + 18 岁表达力的设计师学徒
- 禁止用"业内人士都知道""保姆级""干货满满"等
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
        temperature=0.8,
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
                "tags": ["设计工具", "AI", "教程"],
            },
            "visuals": fallback_result.get("visuals", {
                "cover": {"headline": topic["title"], "subheadline": topic["source"]},
                "compare": {"before": "以前", "after": "现在"},
            }),
            "dudu_voice": recommendation,
        }

    return result


if __name__ == "__main__":
    compose()
