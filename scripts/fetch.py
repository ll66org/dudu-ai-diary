"""dudu fetch v4 - 物理日期 + AI HOT 干货源 + 多级降级"""
import os
import sys
import json
import yaml
import random
import hashlib
import feedparser
from datetime import datetime, timezone, timedelta, date
from pathlib import Path
from openai import OpenAI

# 引入 aihot 模块
sys.path.insert(0, str(Path(__file__).parent))
from aihot_fetcher import (
    fetch_aihot_selected,
    build_briefing_from_aihot,
    pick_main_topic,
)

ROOT = Path(__file__).parent.parent
CONFIG = ROOT / "sources" / "feeds.yaml"
TOPIC_POOL = ROOT / "sources" / "topic_pool.yaml"
MEMORY_FILE = ROOT / "memory" / "growth.json"
OUTPUT = ROOT / "output"
OUTPUT.mkdir(exist_ok=True)

# ========== 兜兜的诞生日（用户指定）==========
DUDU_BIRTHDAY = date(2026, 4, 24)


def get_dudu_day():
    """
    基于物理日期计算兜兜活了多少天
    不依赖 memory 文件，永远不会归零
    """
    today = date.today()
    delta = (today - DUDU_BIRTHDAY).days + 1
    return max(1, delta)  # 最少是第 1 天


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
    history = memory.get("history", [])
    return history[-days:] if history else []


def get_used_titles_and_tools(memory, days=7):
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
    if not a or not b:
        return False
    a_set = set(a.lower().split())
    b_set = set(b.lower().split())
    if not a_set or not b_set:
        return False
    overlap = len(a_set & b_set) / min(len(a_set), len(b_set))
    return overlap > 0.6


def dedupe_against_history(candidates, used_titles):
    filtered = []
    for c in candidates:
        if any(title_similar(c.get("title", ""), ut) for ut in used_titles):
            print(f"  [skip] 和历史重复: {c.get('title','')[:40]}")
            continue
        filtered.append(c)
    return filtered


# ====================================================
# 主流程：三级数据源
# 优先级 1: AI HOT 精选（最新干货） ← 新增
# 优先级 2: RSS 候选池
# 优先级 3: topic_pool 降级（只用栏目轮换）
# ====================================================

def fetch_all():
    config = load_config()
    memory = load_memory()
    used_titles, used_tools, used_angles = get_used_titles_and_tools(memory, days=7)
    dudu_day = get_dudu_day()

    print(f"[dudu] 兜兜的第 {dudu_day} 天（基于物理日期 {DUDU_BIRTHDAY} 起算）")
    print(f"[dudu] 最近 7 天已用选题 {len(used_titles)} 个，已用工具 {len(used_tools)} 个")

    # ========== Step 1: 拉 AI HOT 精选（必拉）==========
    aihot_result = None
    try:
        aihot_result = fetch_aihot_selected(days=3, take=80)
    except Exception as e:
        print(f"[aihot] 拉取异常（不影响主流程）: {e}")

    today_briefing = []
    if aihot_result:
        today_briefing = build_briefing_from_aihot(aihot_result, top_n=5)
        print(f"[dudu] 今日快讯准备就绪，共 {len(today_briefing)} 条干货")
        for i, b in enumerate(today_briefing, 1):
            print(f"  {i}. [{b['category']}] {b['title'][:50]} | {b['source']}")

    # ========== Step 2: 用 aihot 优先选主题（如果有设计相关）==========
    aihot_main = None
    if aihot_result and aihot_result.get("design_items"):
        aihot_main = pick_main_topic(aihot_result, used_titles)
        if aihot_main:
            print(f"[dudu] 从 AI HOT 选定主题: {aihot_main.get('title', '')[:60]}")

    # ========== Step 3: 拉 RSS（作为 aihot 的补充）==========
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

    # 把 aihot 设计相关条目也并入 candidates（让 LLM 多一些选择）
    if aihot_result:
        for it in aihot_result.get("design_items", [])[:15]:
            candidates.append({
                "title": it.get("title", ""),
                "summary": (it.get("summary") or "")[:500],
                "url": it.get("url", ""),
                "published": it.get("publishedAt", ""),
                "source": f"AI HOT · {it.get('source', '')}",
                "source_weight": "high",
                "category": f"aihot_{it.get('category', 'general')}",
            })

    before_dedupe = len(candidates)
    candidates = dedupe_against_history(candidates, used_titles)
    print(f"[dudu] 去重后 {len(candidates)}/{before_dedupe} 条")

    weight_map = {"high": 3, "medium": 2, "low": 1}
    candidates.sort(
        key=lambda x: (weight_map.get(x["source_weight"], 0), x["published"]),
        reverse=True,
    )
    candidates = candidates[:25]

    # ========== Step 4: 决定走 rss 还是 fallback ==========
    has_data = bool(candidates)
    mode = "rss" if has_data else "fallback"

    output_file = OUTPUT / "candidates.json"
    meta_file = OUTPUT / "fetch_meta.json"
    briefing_file = OUTPUT / "briefing.json"

    meta = {
        "fetched_at": datetime.utcnow().isoformat() + "Z",
        "total_candidates": len(candidates),
        "source_stats": source_stats,
        "mode": mode,
        "dudu_day": dudu_day,  # ← 关键：物理日期
        "today_date": date.today().isoformat(),
        "used_titles": used_titles,
        "used_tools": used_tools,
        "aihot_total": len(aihot_result["items"]) if aihot_result else 0,
        "aihot_design": len(aihot_result["design_items"]) if aihot_result else 0,
        "briefing_count": len(today_briefing),
    }

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(candidates, f, ensure_ascii=False, indent=2)
    with open(meta_file, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    with open(briefing_file, "w", encoding="utf-8") as f:
        json.dump(today_briefing, f, ensure_ascii=False, indent=2)

    print(f"\n[dudu] 共 {len(candidates)} 条候选，{len(today_briefing)} 条快讯")

    if not has_data:
        print("\n[warn] 候选池为空，触发降级策略")
        trigger_fallback(config, memory, used_titles, used_tools, used_angles, dudu_day)


def pick_today_angle(topic_pool, memory, used_angles, dudu_day):
    """按物理 day 做轮换种子，保证天天不一样"""
    rotation = topic_pool.get("weekly_rotation", {})
    section_key = rotation.get((dudu_day - 1) % 7) or rotation.get(str((dudu_day - 1) % 7))

    if not section_key or section_key not in topic_pool:
        candidate_keys = [
            k for k in topic_pool.keys()
            if k != "weekly_rotation" and isinstance(topic_pool[k], dict) and "angles" in topic_pool[k]
        ]
        section_key = random.choice(candidate_keys) if candidate_keys else None

    if not section_key:
        return None, None, None

    section = topic_pool[section_key]
    angles = section.get("angles", [])
    unused = [a for a in angles if a not in used_angles]
    if not unused:
        unused = angles

    today_seed = date.today().strftime("%Y%m%d")
    seed_int = int(hashlib.md5(today_seed.encode()).hexdigest(), 16) % (10**8)
    rng = random.Random(seed_int)
    picked_angle = rng.choice(unused)

    return section_key, section.get("description", ""), picked_angle


def trigger_fallback(config, memory, used_titles, used_tools, used_angles, dudu_day):
    """
    降级 v4：保留栏目轮换，但 prompt 也喂 aihot 兜底
    """
    topic_pool = load_topic_pool()

    if topic_pool:
        section_key, section_desc, picked_angle = pick_today_angle(
            topic_pool, memory, used_angles, dudu_day
        )
        print(f"[fallback] 今天的栏目: {section_key}")
        print(f"[fallback] 今天的视角: {picked_angle}")
    else:
        section_key, section_desc, picked_angle = None, "", None

    fallback_tools = config.get("fallback_tools", [])
    if not fallback_tools and not picked_angle:
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
"""

        today_str = datetime.now().strftime("%Y-%m-%d")
        prompt = f"""今天是 {today_str}，兜兜的第 {dudu_day} 天（兜兜诞生于 2026-04-24）。
兜兜发现今天 RSS 没有抓到新的设计向 AI 内容，触发了降级策略。

{angle_hint}
{history_brief}

可参考的工具候选池：
{json.dumps(tools_brief, ensure_ascii=False, indent=2)}

请按以下格式输出 JSON：
{{
  "selected_topic": {{
    "title": "非常具体的选题标题",
    "source": "主要涉及的工具名或概念",
    "url": "相关工具的官网 URL",
    "why_picked": "兜兜为什么选这个（1-2句话）",
    "designer_angle": "设计师视角的独特亮点",
    "fallback_mode": true,
    "angle": "{picked_angle or ''}",
    "section": "{section_key or ''}"
  }},
  "analysis": "深度分析 200-300 字，必须有具体工具名/数据/场景",
  "recommendation": "兜兜给设计师的具体建议，50字以内"
}}

硬性要求：
- 必须围绕今日视角，不能偏题
- 输出严格合法的 JSON"""

        print("[fallback] 调用 DeepSeek 生成话题分析...")

        resp = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {
                    "role": "system",
                    "content": "你是一个热情的设计 AI 助手，叫兜兜。极度重视选题的新鲜感和差异化。"
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.9,
            response_format={"type": "json_object"},
        )

        raw = resp.choices[0].message.content.strip()
        if raw.startswith("```json"):
            raw = raw[7:]
        if raw.startswith("```"):
            raw = raw[3:]
        if raw.endswith("```"):
            raw = raw[:-3]
        result = json.loads(raw.strip())

        fallback_candidate = {
            "title": result["selected_topic"]["title"],
            "summary": result.get("analysis", ""),
            "url": result["selected_topic"].get("url", ""),
            "published": datetime.now().isoformat(),
            "source": result["selected_topic"]["source"],
            "source_weight": "high",
            "category": "fallback",
            "fallback_data": result,
        }

        with open(OUTPUT / "candidates.json", "w", encoding="utf-8") as f:
            json.dump([fallback_candidate], f, ensure_ascii=False, indent=2)

        meta = {
            "fetched_at": datetime.utcnow().isoformat() + "Z",
            "total_candidates": 1,
            "mode": "fallback",
            "dudu_day": dudu_day,
            "today_date": date.today().isoformat(),
            "today_section": section_key,
            "today_angle": picked_angle,
        }
        with open(OUTPUT / "fetch_meta.json", "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)

        print(f"[fallback] 已生成: {result['selected_topic']['title']}")

    except Exception as e:
        print(f"[error] 降级失败: {e}")
        import traceback
        traceback.print_exc()
        with open(OUTPUT / "candidates.json", "w", encoding="utf-8") as f:
            json.dump([], f, ensure_ascii=False)
        with open(OUTPUT / "fetch_meta.json", "w", encoding="utf-8") as f:
            json.dump({"mode": "error", "error": str(e), "dudu_day": dudu_day}, f, ensure_ascii=False)


if __name__ == "__main__":
    fetch_all()
