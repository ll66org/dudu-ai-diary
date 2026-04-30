"""兜兜的信息源抓取器 dudu"""
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

    for category, sources in config.items():
        if category == "filter_keywords":
            continue
        if not isinstance(sources, list):
            continue

        for src in sources:
            try:
                print(f"[fetch] {src['name']}")
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
                print(f"  [warn] {src['name']} failed: {e}")

    weight_map = {"high": 3, "medium": 2, "low": 1}
    candidates.sort(
        key=lambda x: (weight_map.get(x["source_weight"], 0), x["published"]),
        reverse=True,
    )

    candidates = candidates[:20]

    output_file = OUTPUT / "candidates.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(candidates, f, ensure_ascii=False, indent=2)

    print(f"\n[done] {len(candidates)} candidates collected")
    print(f"[saved] {output_file}")

    if not candidates:
        print("[warn] no candidates today, may need to adjust freshness/keywords")
    else:
        print("\nTop 3 candidates:")
        for i, c in enumerate(candidates[:3], 1):
            print(f"  {i}. [{c['source']}] {c['title'][:60]}")


if __name__ == "__main__":
    fetch_all()
