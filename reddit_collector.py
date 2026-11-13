"""
B-Litmus Reddit collector (read-only, official Reddit API via PRAW).

Collects public posts/comments that mention project-management tools, so we can
test how much opinion data exists per product. The same logic is used by the
Collector agent in the B-Litmus backend, one product at a time.

  python reddit_collector.py collect            # fetch and save to data/
  python reddit_collector.py collect --time-filter all --limit 100
  python reddit_collector.py prune              # drop items Reddit has removed

Env vars: REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USER_AGENT
"""
import argparse
import os
import re
import time
from datetime import datetime, timezone

import pandas as pd
import praw

COMMON_SUBS = ["projectmanagement", "Notion", "SaaS", "startups"]
TOOLS = {
    "ClickUp":  ["clickup"] + COMMON_SUBS,
    "Jira":     ["jira"] + COMMON_SUBS,
    "Trello":   ["trello"] + COMMON_SUBS,
    "Airtable": ["Airtable"] + COMMON_SUBS,
    "Todoist":  ["todoist"] + COMMON_SUBS,
}
REMOVED = ("[removed]", "[deleted]")
OUT = "data/reddit_pm_items.csv"


def make_reddit() -> praw.Reddit:
    return praw.Reddit(
        client_id=os.environ["REDDIT_CLIENT_ID"],
        client_secret=os.environ["REDDIT_CLIENT_SECRET"],
        user_agent=os.environ["REDDIT_USER_AGENT"],  # e.g. "b-litmus-fyp/0.1 by u/yourname"
    )


def iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def mentions(text: str, tool: str) -> bool:
    return bool(re.search(rf"\b{re.escape(tool)}\b", text or "", re.I))


def collect(reddit, args) -> pd.DataFrame:
    rows, seen = [], set()  # seen holds (tool, id), so one post can count for two tools
    now = iso(time.time())

    for tool, subs in TOOLS.items():
        for sub in subs:
            print(f"[{tool}] r/{sub}")
            try:
                for post in reddit.subreddit(sub).search(
                    tool, sort="relevance", time_filter=args.time_filter, limit=args.limit
                ):
                    if post.score < args.min_score or post.selftext in REMOVED:
                        continue
                    post_text = f"{post.title}\n{post.selftext}"
                    if (tool, post.id) not in seen and mentions(post_text, tool):
                        seen.add((tool, post.id))
                        rows.append(dict(
                            tool=tool, type="post", id=post.id, post_id=post.id,
                            subreddit=post.subreddit.display_name,
                            created_utc=iso(post.created_utc), score=post.score,
                            title=post.title, text=post.selftext,
                            url=f"https://reddit.com{post.permalink}", retrieved_at=now,
                        ))
                    if args.no_comments or post.num_comments == 0:
                        continue
                    post.comment_sort = "top"
                    post.comments.replace_more(limit=0)
                    for c in list(post.comments)[: args.comments_per_post]:
                        if (tool, c.id) in seen or c.score < args.min_score or c.body in REMOVED:
                            continue
                        if not mentions(c.body, tool):
                            continue
                        seen.add((tool, c.id))
                        # No usernames are stored: only public text and metadata.
                        rows.append(dict(
                            tool=tool, type="comment", id=c.id, post_id=post.id,
                            subreddit=post.subreddit.display_name,
                            created_utc=iso(c.created_utc), score=c.score,
                            title=post.title, text=c.body,
                            url=f"https://reddit.com{c.permalink}", retrieved_at=now,
                        ))
            except Exception as e:  # private/banned subs, transient errors
                print(f"  ! skipped r/{sub}: {e}")
                time.sleep(2)
    return pd.DataFrame(rows)


def recency_report(df: pd.DataFrame, recent_days: int) -> pd.DataFrame:
    df = df.copy()
    df["created_utc"] = pd.to_datetime(df["created_utc"], utc=True)
    cutoff = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=recent_days)
    df["recent"] = df["created_utc"] >= cutoff
    return (df.groupby("tool")
              .agg(items=("id", "count"), recent_ratio=("recent", "mean"),
                   subreddits=("subreddit", "nunique"))
              .round(2).sort_values("items", ascending=False))


def prune(reddit) -> None:
    """Remove stored items that were deleted or removed on Reddit."""
    df = pd.read_csv(OUT)
    names = [("t3_" if t == "post" else "t1_") + i for t, i in zip(df["type"], df["id"])]
    try:
        alive = set()
        for item in reddit.info(fullnames=names):
            text = getattr(item, "selftext", None) if item.fullname.startswith("t3_") else item.body
            if text in REMOVED or getattr(item, "removed_by_category", None):
                continue
            alive.add(item.fullname)
    except Exception as e:  # never wipe data because of a network error
        print(f"Prune skipped: {e}")
        return
    keep = df[[n in alive for n in names]]
    keep.to_csv(OUT, index=False)
    print(f"Kept {len(keep)} of {len(df)} items.")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("cmd", choices=["collect", "prune"])
    p.add_argument("--time-filter", default="all", choices=["day", "week", "month", "year", "all"])
    p.add_argument("--limit", type=int, default=100, help="posts per (tool, subreddit)")
    p.add_argument("--comments-per-post", type=int, default=10)
    p.add_argument("--min-score", type=int, default=1)
    p.add_argument("--recent-days", type=int, default=365)
    p.add_argument("--no-comments", action="store_true")
    a = p.parse_args()

    r = make_reddit()
    if a.cmd == "prune":
        prune(r)
    else:
        data = collect(r, a)
        if data.empty:
            print("No results. Try --time-filter all or a higher --limit.")
        else:
            os.makedirs("data", exist_ok=True)
            data.to_csv(OUT, index=False)
            print(f"\nSaved {len(data)} rows to {OUT}\n")
            print(recency_report(data, a.recent_days))
            if a.time_filter != "all":
                print("\nNote: recent_ratio is only meaningful with --time-filter all.")
