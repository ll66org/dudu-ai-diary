```python
"""兜兜的信息源抓取器 🐣"""
import os
import json
import yaml
import feedparser
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).parent.parent
CONFIG = ROOT / "sources" / "feeds.yaml"
OUTPUT = ROOT / "output"
OUTPUT.mkdir(exist_ok=True)


def load_config():
    with open(CONFIG, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def is_fresh(entry, days=3):
    """判断条目是否在指定天数内"""
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
    """关键词过滤"""
    text = (entry.get("title", "") + " " + entry.get("summary", "")).lower()
    if any(kw.lower() in text for kw in must_not):
        return False
    return any(kw.lower() in text for kw in must_one)


def fetch_all():
    config = load_config()
    must_one = config["filter_keywords"]["must_have_one_of"]
    must_not = config["filter_keywords"]["must_not_have"]

    candidates = []

    for category, sources in config.items():
        if category == "filter_keywords":
            continue
        if not isinstance(sources, list):
            continue

        for src in sources:
            try:
                print(f"🔍 抓取: {src['name']}")
                feed = feedparser.parse(src["url"])
                fresh_days = 1 if src.get("freshness") == "fresh" else 7

                for entry in feed.entries[:20]:
                    if not is_fresh(entry, days=fresh_days):
                        continue
                    if not matches_keywords(entry, must_one, must_not):
                        continue

                    candidates.append({
                        "title": entry.get("title", ""),
                        "summary": entry.get("summary", "")[:500],
                        "url": entry.get("link", ""),
                        "published": entry.get("published", ""),
                        "source": src["name"],
                        "source_weight": src.get("weight", "medium"),
                        "category": category,
                    })
            except Exception as e:
                print(f"  ⚠️ {src['name']} 抓取失败: {e}")

    # 按权重 + 时效性排序
    weight_map = {"high": 3, "medium": 2, "low": 1}
    candidates.sort(
        key=lambda x: (weight_map.get(x["source_weight"], 0), x["published"]),
        reverse=True,
    )

    # 取前 20 条作为兜兜的备选池
    candidates = candidates[:20]

    output_file = OUTPUT / "candidates.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(candidates, f, ensure_ascii=False, indent=2)

    print(f"\n✅ 抓取完成，共 {len(candidates)} 条候选选题")
    print(f"📁 已保存到: {output_file}")

    if not candidates:
        print("⚠️ 今天没抓到符合条件的内容，可能时效性 / 关键词需调整")
    else:
        print("\n🥇 Top 3 候选:")
        for i, c in enumerate(candidates[:3], 1):
            print(f"  {i}. [{c['source']}] {c['title'][:60]}")


if __name__ == "__main__":
    fetch_all()
📂 文件 6/9：scripts/compose.py
文件名：scripts/compose.py

python
复制
"""兜兜的文案生成器 🐣 - 调用 DeepSeek"""
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
    """加载兜兜的成长记忆"""
    if MEMORY_FILE.exists():
        return json.loads(MEMORY_FILE.read_text(encoding="utf-8"))
    return {"day_count": 0, "history": []}


def save_memory(mem):
    MEMORY_FILE.parent.mkdir(exist_ok=True)
    MEMORY_FILE.write_text(json.dumps(mem, ensure_ascii=False, indent=2), encoding="utf-8")


def load_candidates():
    f = OUTPUT / "candidates.json"
    if not f.exists():
        raise SystemExit("❌ 没有候选选题，请先跑 fetch.py")
    return json.loads(f.read_text(encoding="utf-8"))


def compose():
    client = OpenAI(
        api_key=os.environ["DEEPSEEK_API_KEY"],
        base_url="https://api.deepseek.com",
    )

    candidates = load_candidates()
    if not candidates:
        print("⚠️ 没有候选，今天没产出。")
        return

    memory = load_memory()
    day_count = memory["day_count"] + 1

    # 给 AI 看的备选池（前 10 条）
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

下面是兜兜的备选选题池（共 {len(candidates_brief)} 条），请你按「设计向 AI」的标准，
从中选出 1 条最适合的作为今天的日记主题，然后按系统提示词的要求输出完整的小红书帖子 JSON。

候选池：
{json.dumps(candidates_brief, ensure_ascii=False, indent=2)}

请输出严格合法的 JSON，不要任何额外说明。
JSON 中的 body 字段，请把签名档的 N 替换成 {day_count}。
"""

    print(f"🤖 调用 DeepSeek 生成兜兜的第 {day_count} 天日记...")

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
    # 容错：去掉可能的 markdown 包裹
    raw = re.sub(r"^```json\s*|\s*```$", "", raw.strip())
    result = json.loads(raw)

    # 注入元信息
    result["meta"] = {
        "day": day_count,
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }

    # 保存当天成稿
    today = datetime.now().strftime("%Y-%m-%d")
    post_file = POSTS_DIR / f"{today}-day-{day_count:03d}.json"
    post_file.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    # 保存供下游使用
    (OUTPUT / "post.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    # 更新成长记忆
    memory["day_count"] = day_count
    memory["history"].append({
        "day": day_count,
        "date": today,
        "topic": result["selected_topic"]["title"],
        "source": result["selected_topic"]["source"],
    })
    save_memory(memory)

    print(f"✅ 兜兜的第 {day_count} 天日记生成完毕")
    print(f"📌 选题: {result['selected_topic']['title']}")
    print(f"📁 已保存: {post_file}")


if __name__ == "__main__":
    compose()
