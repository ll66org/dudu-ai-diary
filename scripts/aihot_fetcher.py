"""兜兜的实时干货抓取器 - 拉真实 AI 资讯的精选池"""
import os
import json
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).parent.parent
OUTPUT = ROOT / "output"
OUTPUT.mkdir(exist_ok=True)

# 必须带浏览器 UA + 标识，否则会被 nginx 黑名单挡
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 dudu-diary/0.1.0"
)
BASE = "https://aihot.virxact.com"

# 设计师关心的关键词（用于二次过滤）
DESIGN_KEYWORDS = [
    # 工具类
    "figma", "cursor", "v0", "lovable", "bolt", "framer", "windsurf",
    "claude", "artifact", "midjourney", "recraft", "flux", "ideogram",
    "spline", "rive", "perplexity", "notebooklm", "devin",
    # 设计概念
    "design", "设计", "ui", "ux", "interface", "界面", "interaction", "交互",
    "prototype", "原型", "visual", "视觉", "logo", "动效", "motion",
    "generative ui", "agent ui", "对话", "多模态", "design system", "设计系统",
    # 视觉生成
    "image generation", "图像生成", "video generation", "视频生成",
    "icon", "图标", "vector", "矢量", "3d", "rendering",
    # 设计师工作流
    "d2c", "设计转代码", "tailwind", "shadcn", "design token",
]


def http_get(path, params=None, timeout=15):
    """带 UA 调 API"""
    url = BASE + path
    if params:
        params = {k: v for k, v in params.items() if v is not None}
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        print(f"  [briefing] HTTP {e.code}: {url}")
        return None
    except Exception as e:
        print(f"  [briefing] error: {e} ({url})")
        return None


def is_design_relevant(item):
    """判断这条 AI 资讯是否和设计师/视觉/交互相关"""
    text = (
        (item.get("title") or "")
        + " "
        + (item.get("title_en") or "")
        + " "
        + (item.get("summary") or "")
    ).lower()
    return any(kw in text for kw in DESIGN_KEYWORDS)


def fetch_aihot_selected(days=3, take=80):
    """
    拉最近 N 天的精选条目
    返回：{ "items": [...], "design_items": [...], "fetched_at": "..." }
    """
    since_dt = datetime.now(timezone.utc) - timedelta(days=days)
    since = since_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    print(f"[briefing] 拉取最近 {days} 天精选（since={since}, take={take}）...")
    data = http_get(
        "/api/public/items",
        {"mode": "selected", "since": since, "take": take},
    )

    if not data or "items" not in data:
        print("[briefing] 拉取失败或无数据")
        return None

    items = data["items"]
    print(f"[briefing] 共拿到 {len(items)} 条精选")

    # 二次过滤出设计师可能感兴趣的
    design_items = [it for it in items if is_design_relevant(it)]
    print(f"[briefing] 其中设计相关 {len(design_items)} 条")

    return {
        "items": items,
        "design_items": design_items,
        "fetched_at": datetime.utcnow().isoformat() + "Z",
        "since": since,
    }


def fetch_aihot_daily():
    """拉最新一期日报（5 个版块结构）"""
    print("[briefing] 拉取最新日报...")
    data = http_get("/api/public/daily")
    if not data:
        return None
    print(f"[briefing] 日报日期: {data.get('date')}, 版块数: {len(data.get('sections', []))}")
    return data


def build_briefing_from_aihot(aihot_result, top_n=5):
    """
    从 aihot 数据里挑 top_n 条做成"今日快讯"
    优先选设计相关；不够则补一般精选
    """
    if not aihot_result:
        return []

    design = aihot_result.get("design_items", [])
    rest = [
        it for it in aihot_result.get("items", [])
        if it not in design
    ]

    picked = design[:top_n]
    if len(picked) < top_n:
        picked.extend(rest[: top_n - len(picked)])

    briefing = []
    for it in picked[:top_n]:
        briefing.append({
            "title": it.get("title", ""),
            "summary": (it.get("summary") or "")[:160],
            "source": it.get("source", ""),
            "url": it.get("url", ""),
            "published_at": it.get("publishedAt", ""),
            "category": it.get("category", "") or "general",
        })
    return briefing


def pick_main_topic(aihot_result, used_titles):
    """
    从 aihot 里挑一个最适合做今天主题的条目
    要求：① 设计相关 ② 不和最近历史重复 ③ 摘要够长（信息密度）
    """
    if not aihot_result:
        return None

    design_items = aihot_result.get("design_items", [])

    def title_overlap(a, b):
        if not a or not b:
            return 0
        a_set = set(a.lower().split())
        b_set = set(b.lower().split())
        if not a_set or not b_set:
            return 0
        return len(a_set & b_set) / min(len(a_set), len(b_set))

    # 排除和历史相似的
    candidates = [
        it for it in design_items
        if not any(title_overlap(it.get("title", ""), ut) > 0.5 for ut in used_titles)
    ]

    if not candidates:
        candidates = design_items[:]

    # 按摘要长度 + 是否有 category 排序（信息密度高的优先）
    def score(item):
        s = 0
        if item.get("summary"):
            s += min(len(item["summary"]), 300)
        if item.get("category") in ("ai-products", "ai-models", "tip"):
            s += 50  # 设计师更关心这三类
        return s

    candidates.sort(key=score, reverse=True)
    return candidates[0] if candidates else None


if __name__ == "__main__":
    # 测试
    result = fetch_aihot_selected(days=3, take=50)
    if result:
        out = OUTPUT / "aihot_raw.json"
        out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n样本（前 5 条设计相关）：")
        for it in result["design_items"][:5]:
            print(f"  - [{it.get('category')}] {it.get('title', '')[:60]} | {it.get('source')}")
        print(f"\n输出: {out}")
