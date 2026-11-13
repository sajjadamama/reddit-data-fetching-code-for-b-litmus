# B-Litmus Reddit collector

Part of **B-Litmus**, an AI market-intelligence platform for SaaS
(FAST-NUCES Chiniot-Faisalabad final year project, 2026, non-commercial).

This script uses the **official Reddit API (PRAW), read-only**. It never posts,
comments, votes or messages. It finds public posts and comments that mention a
SaaS product (currently project-management tools: ClickUp, Jira, Trello,
Airtable, Todoist) so the platform can analyze sentiment, aspects and themes.

## What it stores
Public text, subreddit, score, timestamp and permalink. **No usernames.**
Reddit content is used only for analysis. It is not used to train models,
sold, or redistributed, and it is not committed to this repository.

## Setup
```bash
pip install -r requirements.txt
export REDDIT_CLIENT_ID="..."
export REDDIT_CLIENT_SECRET="..."
export REDDIT_USER_AGENT="b-litmus-fyp/0.1 by u/YOUR_REDDIT_USERNAME"
```

## Usage
```bash
python reddit_collector.py collect --time-filter all   # saves to data/
python reddit_collector.py prune                       # drops items removed on Reddit
```
The report at the end shows items per tool and the share from the last 365 days.

In the B-Litmus backend, the same logic runs per analysis request, one product
at a time, with a small request volume, and respects Reddit rate limits.
