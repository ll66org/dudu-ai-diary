"""dudu fetch v3 - 扩充信息源 + 降级策略 + 反重复 + 每日轮换"""
import os
import json
import yaml
import random
import hashlib
import feedparser
from datetime import datetime, timezone, timedelta
from pathlib import Path
from openai import OpenAI

ROOT = Path(__file__).parent.parent
CONFIG = ROOT / "sources" / "feeds.yaml"
TOPIC_POOL = ROOT / "sources" / "topic_pool.yaml"
MEMORY_FILE = ROOT / "memory" / "growth.json"
OUTPUT = ROOT / "output"
OUTPUT.mkdir(exist_ok=True)


def load_config():
    with open(CONFIG, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_topic_pool():
    if not TOPIC_POOL.exists():
        return None
    with open(TOPIC_POOL, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_memory():
    if MEMORY_FILE.exists():
        try:
            return json.loads(MEMORY_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"day_count": 0, "history": []}


def get_recent_history(memory, days=7):
    """取最近 N 天的选题历史，用于避重"""
    history = memory.get("history", [])
    return history[-days:] if history else []


def get_used_titles_and_tools(memory, days=7):
    """返回最近 N 天用过的 (titles, tools, angles) 用于硬排除"""
    recent = get_recent_history(memory, days)
    titles = [h.get("topic", "") for h in recent if h.get("topic")]
    tools = [h.get("source", "") for h in recent if h.get("source")]
    angles = [h.get("angle", "") for h in recent if h.get("angle")]
    return titles, tools, angles


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


def title_similar(a, b):
    """简单去重：标题重合 > 60% 认为是同一篇"""
    if not a or not b:
        return False
    a_set = set(a.lower().split())
    b_set = set(b.lower().split())
    if not a_set or not b_set:
        return False
    overlap = len(a_set & b_set) / min(len(a_set), len(b_set))
    return overlap > 0.6


def dedupe_against_history(candidates, used_titles):
    """把和历史重复的候选踢掉"""
    filtered = []
    for c in candidates:
        if any(title_similar(c["title"], ut) for ut in used_titles):
            print(f"  [skip] 和历史重复: {c['title'][:40]}")
            continue
        filtered.append(c)
    return filtered


def fetch_all():
    config = load_config()
    memory = load_memory()
    used_titles, used_tools, used_angles = get_used_titles_and_tools(memory, days=7)

    print(f"[dudu] 最近 7 天已用选题 {len(used_titles)} 个，已用工具 {len(used_tools)} 个")

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

    # 关键修复：在 RSS 抓到的候选中先去掉和最近 7 天历史重复的
    before_dedupe = len(candidates)
    candidates = dedupe_against_history(candidates, used_titles)
    print(f"[dudu] 去重后 {len(candidates)}/{before_dedupe} 条")

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
        "mode": "rss" if candidates else "fallback",
        "day_count": memory.get("day_count", 0) + 1,
        "used_titles": used_titles,
        "used_tools": used_tools,
    }

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(candidates, f, ensure_ascii=False, indent=2)
    with open(meta_file, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    print(f"\n[dudu] 共抓取到 {len(candidates)} 条候选内容")
    if candidates:
        print("[dudu] Top 3:")
        for i, c in enumerate(candidates[:3], 1):
            print(f"  {i}. [{c['source']}] {c['title'][:60]}")
        print("[dudu] RSS 模式，交给 compose.py 正常处理")
    else:
        print("\n[warn] 今日 RSS 没有新内容或全部和历史重复！")
        print("[dudu] 触发降级策略：设计向 AI 话题轮换模式")
        trigger_fallback(config, memory, used_titles, used_tools, used_angles)


def pick_today_angle(topic_pool, memory, used_angles):
    """
    按 day_count 轮换栏目，从栏目里挑一个没用过的 angle
    关键：保证每天不一样
    """
    day_count = memory.get("day_count", 0) + 1
    rotation = topic_pool.get("weekly_rotation", {})
    # 用 day_count-1 % 7 决定今天的栏目
    section_key = rotation.get(str((day_count - 1) % 7)) or rotation.get((day_count - 1) % 7)

    if not section_key or section_key not in topic_pool:
        # 兜底：随机挑一个栏目
        candidate_keys = [
            k for k in topic_pool.keys()
            if k not in ("weekly_rotation",) and isinstance(topic_pool[k], dict) and "angles" in topic_pool[k]
        ]
        section_key = random.choice(candidate_keys) if candidate_keys else None

    if not section_key:
        return None, None, []

    section = topic_pool[section_key]
    angles = section.get("angles", [])
    # 过滤掉最近用过的 angle
    unused = [a for a in angles if a not in used_angles]
    if not unused:
        # 如果全部用过了，给用过最久以前的那个（近似：全部随机）
        unused = angles

    # 用今天的日期作为随机种子，保证同一天运行多次结果一致，不同天自然不同
    today_seed = datetime.now().strftime("%Y%m%d")
    seed_int = int(hashlib.md5(today_seed.encode()).hexdigest(), 16) % (10**8)
    rng = random.Random(seed_int)
    picked_angle = rng.choice(unused)

    return section_key, section.get("description", ""), picked_angle


def trigger_fallback(config, memory, used_titles, used_tools, used_angles):
    """
    降级策略 v3：
    1. 按 day_count 轮换今天的栏目（7 个栏目循环）
    2. 在栏目里挑一个没用过的 angle
    3. 把"最近 7 天用过的工具/选题"告诉 AI，硬性要求避开
    """
    topic_pool = load_topic_pool()
    day_count = memory.get("day_count", 0) + 1

    if topic_pool:
        section_key, section_desc, picked_angle = pick_today_angle(
            topic_pool, memory, used_angles
        )
        print(f"[fallback] 今天的栏目: {section_key} ({section_desc})")
        print(f"[fallback] 今天的视角: {picked_angle}")
    else:
        section_key, section_desc, picked_angle = None, "", None

    fallback_tools = config.get("fallback_tools", [])
    if not fallback_tools and not picked_angle:
        print("[error] 没有配置 fallback_tools 也没有 topic_pool，跳过")
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

        # 构造 prompt：把历史、今日栏目、今日 angle 都塞进去
        history_brief = ""
        if used_titles:
            history_brief = f"""
【最近 7 天兜兜已经写过的选题（绝对不能重复！）】
{json.dumps(used_titles, ensure_ascii=False, indent=2)}

【最近 7 天兜兜已经写过的工具（今天务必换一个！）】
{json.dumps(used_tools, ensure_ascii=False, indent=2)}
"""

        angle_hint = ""
        if picked_angle:
            angle_hint = f"""
【今天的栏目】{section_key} - {section_desc}
【今天必须围绕这个视角】{picked_angle}

请围绕上面这个视角，挖掘一个设计师会感兴趣的具体内容。
"""

        today_str = datetime.now().strftime("%Y-%m-%d")
        prompt = f"""今天是 {today_str}，兜兜的第 {day_count} 天。兜兜发现今天 RSS 没有抓到新的设计向 AI 内容，触发了降级策略。

{angle_hint}

{history_brief}

可参考的工具候选池（仅作参考，今天的选题不一定要围绕这些工具；如果今日视角已经指向某个工具，就直接围绕它深挖）：
{json.dumps(tools_brief, ensure_ascii=False, indent=2)}

请按以下格式输出 JSON：
{{
  "selected_topic": {{
    "title": "一个非常具体的选题标题，不能泛泛而谈，要有数字/场景/对比",
    "source": "主要涉及的工具名或概念，如果是概念话题就写一个具体锚定词",
    "url": "相关工具的官网 URL（如果是纯概念话题，写 https://www.dudu-design.com）",
    "why_picked": "兜兜为什么选这个（1-2句话，要和今日视角强相关）",
    "designer_angle": "从设计师视角看这个话题的独特亮点",
    "fallback_mode": true,
    "angle": "{picked_angle or ''}",
    "section": "{section_key or ''}"
  }},
  "analysis": "对这个话题的深度分析，200-300字，包含：具体现象 + 设计师视角 + 兜兜的观察，必须有具体的工具名/数据/场景，不能空谈",
  "recommendation": "兜兜给设计师的具体建议，50字以内，要能直接动手做"
}}

硬性要求（违反直接作废重来）：
- 标题绝对不能和【最近 7 天已写选题】中任何一条相似
- 主角工具绝对不能是【最近 7 天已写工具】中出现频率最高的那一个
- 必须围绕今日视角展开，不能偏题
- 选一个你最有信心能给设计师带来价值的话题
- 分析要具体，有数字有细节，不要泛泛而谈
- 语言风格：兜兜是新生学习者，有好奇心，有态度，敢动手
- 输出严格合法的 JSON，不要任何额外说明"""

        print("[fallback] 调用 DeepSeek 生成话题分析...")

        resp = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {
                    "role": "system",
                    "content": "你是一个热情的设计 AI 助手，叫兜兜。用第一人称回答问题，有好奇心，有态度，语言生动活泼。你极度重视选题的新鲜感和差异化——绝不会和已经写过的选题重复。"
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.9,  # 提高温度增加随机性
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

        # 二次校验：如果 AI 还是生成了重复选题，给出 warning
        gen_title = result.get("selected_topic", {}).get("title", "")
        if any(title_similar(gen_title, ut) for ut in used_titles):
            print(f"[warn] AI 生成的选题仍然和历史相似：{gen_title}")
            print("[warn] 但已尽力，继续使用——建议人工检查")

        output_file = OUTPUT / "candidates.json"
        meta_file = OUTPUT / "fetch_meta.json"

        fallback_candidate = {
            "title": result["selected_topic"]["title"],
            "summary": result["analysis"],
            "url": result["selected_topic"].get("url", ""),
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
            "fallback_analysis": result.get("analysis", ""),
            "today_section": section_key,
            "today_angle": picked_angle,
            "used_titles_count": len(used_titles),
            "used_tools_count": len(used_tools),
        }
        with open(meta_file, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)

        print(f"[fallback] 已生成降级内容：{result['selected_topic']['source']}")
        print(f"[fallback] 话题：{result['selected_topic']['title']}")

    except Exception as e:
        print(f"[error] 降级策略失败: {e}")
        import traceback
        traceback.print_exc()
        with open(OUTPUT / "candidates.json", "w", encoding="utf-8") as f:
            json.dump([], f, ensure_ascii=False)
        with open(OUTPUT / "fetch_meta.json", "w", encoding="utf-8") as f:
            json.dump({"mode": "error", "error": str(e)}, f, ensure_ascii=False)


if __name__ == "__main__":
    fetch_all()
