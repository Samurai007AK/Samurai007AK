"""Checks that a new pull request in someone else's repo shows up in the trail.

Run:  python scripts/test_daily.py
"""

import datetime as dt
import os

from daily import QUERY, TRAIL_END, TRAIL_START, summarize, trail_markdown, trail_row, update_readme

NOW = dt.datetime(2026, 9, 20, tzinfo=dt.timezone.utc)


def pr(repo, state, merged, when, title="a fix"):
    return {"repository": {"nameWithOwner": repo}, "state": state, "merged": merged,
            "mergedAt": when if merged else None, "createdAt": when, "title": title,
            "url": f"https://github.com/{repo}/pull/1"}


def data(prs):
    return {"user": {"year": {"contributionCalendar": {"totalContributions": 10, "weeks": [
                {"contributionDays": [{"date": "2026-09-19", "contributionCount": 3}]}]}},
                     "month": {"commitContributionsByRepository": [{"contributions": {"totalCount": 5}}]},
                     "repositories": {"nodes": []}},
            "search": {"nodes": prs}}


def main():
    yesterday = summarize(data([pr("K4-LABS/gpumesh", "MERGED", True, "2026-09-08T00:00:00Z")]), NOW)
    assert [n for n, _ in yesterday["trail"]] == ["K4-LABS/gpumesh"], yesterday["trail"]

    # Tomorrow: one merged and one open pull request, both in repos never seen before.
    today = summarize(data([
        pr("K4-LABS/gpumesh", "MERGED", True, "2026-09-08T00:00:00Z"),
        pr("pytorch/pytorch", "MERGED", True, "2026-09-20T09:00:00Z", "fix autograd leak"),
        pr("kubernetes/kubernetes", "OPEN", False, "2026-09-20T10:00:00Z", "add a guard"),
    ]), NOW)
    names = [n for n, _ in today["trail"]]
    assert names == ["pytorch/pytorch", "K4-LABS/gpumesh", "kubernetes/kubernetes"], names
    assert today["merged"] == 2 and today["projects"] == 3

    # Every project becomes its own linked row pointing at my pull requests in that repo.
    block = trail_markdown(today, "Samurai007AK/Samurai007AK")
    assert block.count("<a href=") == 3, block
    assert "https://github.com/pytorch/pytorch/pulls?q=is%3Apr+author%3ASamurai007AK" in block
    assert "row-0-dark.svg" in block and "row-2-light.svg" in block

    # A closed-but-never-merged pull request is left out, and my own repos never enter the query.
    only_closed = summarize(data([pr("some/repo", "CLOSED", False, "2026-09-01T00:00:00Z")]), NOW)
    assert only_closed["trail"] == [], only_closed["trail"]
    assert "-user:" in open(os.path.join(os.path.dirname(__file__), "daily.py"), encoding="utf-8").read()
    assert "PullRequest" in QUERY

    theme = dict(paper="#fff", ink="#000", wash="#666", red="#b00", moon="#fff", moon_dark="#000", petal="#f99")
    row = trail_row("pytorch/pytorch", today["trail"][0][1], theme, NOW)
    assert "pytorch/pytorch" in row and "1 MERGED" in row and "today" in row

    # The README block is rewritten in place, and a second identical run reports no change.
    tmp = "test-readme.md"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(f"# hi\n{TRAIL_START}\nold\n{TRAIL_END}\nbye\n")
    assert update_readme(tmp, block) is True
    text = open(tmp, encoding="utf-8").read()
    assert "old" not in text and "pytorch/pytorch" in text and text.endswith("bye\n")
    assert update_readme(tmp, block) is False
    os.remove(tmp)
    print("ok: new pull requests appear in the trail, each row links to its repo")


if __name__ == "__main__":
    main()
