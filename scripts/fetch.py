"""dudu fetch v2 - 扩充信息源 + 降级策略"""
import os
import json
import yaml
import feedparser
from datetime import datetime, timezone, timedelta
from pathlib import Path
from openai import OpenAI

ROOT = Path(__file__).parent.parent
CONFIG = ROOT / "sources" / "feeds.yaml"
OUTPUT = ROOT / "output"
OUTPUT.mkdir(exist_ok=True)


def load_config():
    with open(CONFIG, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def is_fresh(entry, days=3):
    try:
        published = entry.get("published_parsed") or entry.get("updated_parsed")
        if not published:
            return False
        pub_time = datetime(*published[:6], tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        return (now - pub_time) <= timedelta(days=days)
    except Exception:
        return False


def matches_keywords(entry, must_one, must_not):
    text = (entry.get("title", "") + " " + entry.get("summary", "")).lower()
    if any(kw.lower() in text for kw in must_not):
        return False
    return any(kw.lower() in text for kw in must_one)


def fetch_all():
    config = load_config()
    must_one = config["filter_keywords"]["must_have_one_of"]
    must_not = config["filter_keywords"]["must_not_have"]

    candidates = []
    source_stats = {}

    for category, sources in config.items():
        if category in ("filter_keywords", "fallback_tools"):
            continue
        if not isinstance(sources, list):
            continue
        for src in sources:
            src_name = src["name"]
            try:
                print(f"[fetch] {src_name}")
                feed = feedparser.parse(src["url"])
                fresh_days = 1 if src.get("freshness") == "fresh" else 7
                found = 0
                for entry in feed.entries[:30]:
                    if not is_fresh(entry, days=fresh_days):
                        continue
                    if not matches_keywords(entry, must_one, must_not):
                        continue
                    candidates.append({
                        "title": entry.get("title", ""),
                        "summary": entry.get("summary", "")[:500],
                        "url": entry.get("link", ""),
                        "published": entry.get("published", ""),
                        "source": src_name,
                        "source_weight": src.get("weight", "medium"),
                        "category": category,
                    })
                    found += 1
                source_stats[src_name] = {"found": found, "total": len(feed.entries)}
                print(f"  -> {found}/{min(len(feed.entries), 30)} matched")
            except Exception as e:
                source_stats[src_name] = {"error": str(e)}
                print(f"  [warn] {src_name} failed: {e}")

    weight_map = {"high": 3, "medium": 2, "low": 1}
    candidates.sort(
        key=lambda x: (weight_map.get(x["source_weight"], 0), x["published"]),
        reverse=True,
    )
    candidates = candidates[:20]

    output_file = OUTPUT / "candidates.json"
    meta_file = OUTPUT / "fetch_meta.json"

    meta = {
        "fetched_at": datetime.utcnow().isoformat() + "Z",
        "total_candidates": len(candidates),
        "source_stats": source_stats,
        "mode": "rss",
    }

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(candidates, f, ensure_ascii=False, indent=2)
    with open(meta_file, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    print(f"\n[dudu] 共抓取到 {len(candidates)} 条候选内容")
    if candidates:
        print(f"[dudu] Top 3:")
        for i, c in enumerate(candidates[:3], 1):
            print(f"  {i}. [{c['source']}] {c['title'][:60]}")
        print(f"\n[dudu] RSS 模式，交给 compose.py 正常处理")
    else:
        print("\n[warn] 今日 RSS 没有新内容！")
        print("[dudu] 触发降级策略：设计工具深度分析模式")
        trigger_fallback(config)


def trigger_fallback(config):
    """降级策略：当日历没有新内容时，用 AI 分析主流设计工具近期更新"""
    fallback_tools = config.get("fallback_tools", [])
    if not fallback_tools:
        print("[error] 没有配置 fallback_tools，跳过")
        return

    tools_brief = [
        {"name": t["name"], "description": t["description"], "focus": t["recent_focus"]}
        for t in fallback_tools
    ]

    try:
        client = OpenAI(
            api_key=os.environ["DEEPSEEK_API_KEY"],
            base_url="https://api.deepseek.com",
        )

        prompt = f"""今天是兜兜的第 N 天。兜兜发现今天 RSS 没有抓到新的设计向 AI 内容，触发了降级策略。

兜兜的任务是：从以下 10 个主流设计 AI 工具中，选出 1 个，分析它最近的更新亮点，生成一期"工具深度分析"内容。

工具列表：
{json.dumps(tools_brief, ensure_ascii=False, indent=2)}

请按以下格式输出 JSON：
{{
  "selected_topic": {{
    "title": "选题标题",
    "source": "工具名",
    "url": "工具官网URL",
    "why_picked": "兜兜为什么选这个工具，1-2句话",
    "designer_angle": "从设计师视角看这个工具的亮点",
    "fallback_mode": true
  }},
  "analysis": "对这个工具的深度分析，200-300字，包含：最近更新 + 设计师怎么用 + 兜兜的观察",
  "recommendation": "兜兜给设计师的建议，50字以内"
}}

要求：
- 选一个你最有信心能给设计师带来价值的工具
- 分析要具体，有数字有细节，不要泛泛而谈
- 语言风格：兜兜是新生学习者，有好奇心，有态度，敢动手
- 输出严格合法的 JSON，不要任何额外说明"""

        print("[fallback] 调用 DeepSeek 生成工具分析...")

        resp = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {
                    "role": "system",
                    "content": "你是一个热情的设计 AI 助手，叫兜兜。用第一人称回答问题，有好奇心，有态度，语言生动活泼。"
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.8,
            response_format={"type": "json_object"},
        )

        raw = resp.choices[0].message.content
        raw = raw.strip()
        if raw.startswith("```json"):
            raw = raw[7:]
        if raw.startswith("```"):
            raw = raw[3:]
        if raw.endswith("```"):
            raw = raw[:-3]
        result = json.loads(raw.strip())

        output_file = OUTPUT / "candidates.json"
        meta_file = OUTPUT / "fetch_meta.json"

        fallback_candidate = {
            "title": result["selected_topic"]["title"],
            "summary": result["analysis"],
            "url": result["selected_topic"]["url"],
            "published": datetime.now().isoformat(),
            "source": result["selected_topic"]["source"],
            "source_weight": "high",
            "category": "fallback",
            "fallback_data": result,
        }

        with open(output_file, "w", encoding="utf-8") as f:
            json.dump([fallback_candidate], f, ensure_ascii=False, indent=2)

        meta = {
            "fetched_at": datetime.utcnow().isoformat() + "Z",
            "total_candidates": 1,
            "mode": "fallback",
            "fallback_tool": result["selected_topic"]["source"],
            "fallback_analysis": result["analysis"],
        }
        with open(meta_file, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)

        print(f"[fallback] 已生成降级内容：{result['selected_topic']['source']}")
        print(f"[fallback] 话题：{result['selected_topic']['title']}")

    except Exception as e:
        print(f"[error] 降级策略失败: {e}")
        with open(OUTPUT / "candidates.json", "w", encoding="utf-8") as f:
            json.dump([], f, ensure_ascii=False)
        with open(OUTPUT / "fetch_meta.json", "w", encoding="utf-8") as f:
            json.dump({"mode": "error", "error": str(e)}, f, ensure_ascii=False)


if __name__ == "__main__":
    fetch_all()
