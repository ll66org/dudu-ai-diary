"""dudu compose - DeepSeek wrapper"""
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


def compose():
    client = OpenAI(
        api_key=os.environ["DEEPSEEK_API_KEY"],
        base_url="https://api.deepseek.com",
    )

    candidates = load_candidates()
    if not candidates:
        print("[warn] no candidates today")
        return

    memory = load_memory()
    day_count = memory["day_count"] + 1

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
JSON 中的 body 字段，请把签名档的 N 替换成 {day_count}。
"""

    print(f"[compose] day {day_count}, calling DeepSeek...")

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
    raw = re.sub(r"^```json\s*|\s*```$", "", raw.strip())
    result = json.loads(raw)

    result["meta"] = {
        "day": day_count,
        "generated_at": datetime.utcnow().isoformat() + "Z",
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


if __name__ == "__main__":
    compose()
