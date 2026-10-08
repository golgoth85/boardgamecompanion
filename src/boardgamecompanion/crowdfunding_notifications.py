from __future__ import annotations

import re
import unicodedata
from datetime import UTC, datetime
from typing import Any

from boardgamecompanion.database import Database
from boardgamecompanion.notifications import NotificationStore

_STOPWORDS = frozenset(
    {
        "the", "a", "an", "of", "and", "or", "board", "game", "games",
        "edition", "new", "campaign", "kickstarter", "gamefound", "deluxe",
        "second", "reprint", "relaunch",
    }
)
_TOKEN_RE = re.compile(r"[a-z0-9]+", re.I)


def _tokens(value: str) -> tuple[str, ...]:
    normalized = unicodedata.normalize("NFKD", str(value or ""))
    words = [
        token.casefold()
        for token in _TOKEN_RE.findall(normalized)
        if token.casefold() not in _STOPWORDS and len(token) >= 2
    ]
    return tuple(dict.fromkeys(words))


def _matches_title(candidate: str, target: str) -> bool:
    left = _tokens(candidate)
    right = _tokens(target)
    if not left or not right:
        return False
    left_set, right_set = set(left), set(right)
    if len(right_set) == 1:
        return next(iter(right_set)) in left_set
    if right_set.issubset(left_set):
        return True
    intersection = len(left_set & right_set)
    coverage = intersection / len(right_set)
    precision = intersection / len(left_set)
    return coverage >= 0.8 and precision >= 0.45


class CrowdfundingNotificationProducer:
    def __init__(self, database: Database):
        self.database = database
        self.notifications = NotificationStore(database)

    def _targets(self) -> list[dict[str, Any]]:
        targets: list[dict[str, Any]] = []
        with self.database.connect() as connection:
            games = connection.execute(
                """
                SELECT g.bgg_id,g.title,g.original_title,COALESCE(MAX(c.own),0) AS own
                FROM board_games g
                LEFT JOIN collection_entries c ON c.board_game_id=g.id
                WHERE COALESCE(g.item_type,'standalone')!='expansion'
                GROUP BY g.id,g.bgg_id,g.title,g.original_title
                """
            ).fetchall()
            wishlist = connection.execute(
                """
                SELECT bgg_id,title,target_url,source_kind,source_key
                FROM personal_wishlist
                """
            ).fetchall()
        for row in games:
            targets.append(
                {
                    "kind": "owned" if row["own"] else "known",
                    "bgg_id": int(row["bgg_id"]),
                    "title": row["title"],
                    "aliases": [
                        value
                        for value in (row["title"], row["original_title"])
                        if value
                    ],
                    "target_url": None,
                }
            )
        for row in wishlist:
            targets.append(
                {
                    "kind": "wishlist",
                    "bgg_id": int(row["bgg_id"]) if row["bgg_id"] else None,
                    "title": row["title"],
                    "aliases": [row["title"]],
                    "target_url": row["target_url"],
                    "source_kind": row["source_kind"],
                    "source_key": row["source_key"],
                }
            )
        return targets

    @staticmethod
    def _match_campaign(
        campaign: dict[str, Any],
        targets: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        # Description text can mention many unrelated games. Matching it as
        # though it were the project title generates false notifications.
        haystack = str(campaign.get("title") or "").strip()
        if not haystack:
            return None
        matches = [
            target
            for target in targets
            if any(_matches_title(haystack, alias) for alias in target["aliases"])
        ]
        if not matches:
            return None
        matches.sort(
            key=lambda target: (
                0 if target["kind"] == "wishlist" else 1,
                0 if target["kind"] == "owned" else 1,
                -len(_tokens(target["title"])),
            )
        )
        return matches[0]

    def scan(self, campaigns: list[dict[str, Any]]) -> dict[str, int]:
        targets = self._targets()
        current = datetime.now(UTC).isoformat()
        with self.database.connect() as connection:
            baseline = connection.execute(
                """
                SELECT 1 FROM notification_scan_state
                WHERE producer='crowdfunding'
                """
            ).fetchone() is None
            known = {
                row["campaign_key"]
                for row in connection.execute(
                    "SELECT campaign_key FROM crowdfunding_watch_state"
                ).fetchall()
            }

        matched = created = notified = 0
        for campaign in campaigns:
            target = self._match_campaign(campaign, targets)
            if target is None:
                continue
            matched += 1
            campaign_key = str(
                campaign.get("id")
                or campaign.get("project_url")
                or f"{campaign.get('platform')}:{campaign.get('title')}"
            ).strip()
            if not campaign_key:
                continue
            title = str(campaign.get("title") or "Nuova campagna").strip()
            target_url = str(campaign.get("project_url") or "").strip()
            platform = str(campaign.get("platform") or "").strip() or None
            is_new = campaign_key not in known
            with self.database.transaction(immediate=True) as connection:
                connection.execute(
                    """
                    INSERT INTO crowdfunding_watch_state(
                        campaign_key,title,platform,target_url,related_bgg_id,
                        first_seen_at,last_seen_at
                    ) VALUES(?,?,?,?,?,?,?)
                    ON CONFLICT(campaign_key) DO UPDATE SET
                        title=excluded.title,
                        platform=excluded.platform,
                        target_url=excluded.target_url,
                        related_bgg_id=excluded.related_bgg_id,
                        last_seen_at=excluded.last_seen_at
                    """,
                    (
                        campaign_key,
                        title,
                        platform,
                        target_url or None,
                        target.get("bgg_id"),
                        current,
                        current,
                    ),
                )
            if not is_new:
                continue
            created += 1
            same_wishlist_campaign = bool(
                target.get("kind") == "wishlist"
                and target.get("target_url")
                and target_url
                and str(target["target_url"]).rstrip("/") == target_url.rstrip("/")
            )
            if baseline or same_wishlist_campaign:
                continue
            self.notifications.create_once(
                category="crowdfunding",
                dedupe_key=f"crowdfunding:{campaign_key}",
                title=f"Nuovo crowdfunding: {title}",
                body=f"Collegato a {target['title']}.",
                target_url=target_url or "/crowdfunding",
                related_bgg_id=target.get("bgg_id"),
                metadata={
                    "platform": platform,
                    "campaign_key": campaign_key,
                    "matched_title": target["title"],
                    "matched_kind": target["kind"],
                },
            )
            notified += 1
        # Record the first successful discovery independently of matches.
        # Empty provider output can be transient and should not establish the
        # baseline; a nonempty unrelated result is still a valid first scan.
        if baseline and any(
            isinstance(item, dict)
            and str(item.get("id") or item.get("project_url") or "").strip()
            for item in campaigns
        ):
            with self.database.transaction(immediate=True) as connection:
                connection.execute(
                    """
                    INSERT OR IGNORE INTO notification_scan_state(
                        producer,initialized_at
                    ) VALUES('crowdfunding',?)
                    """,
                    (current,),
                )
        return {
            "matched": matched,
            "created": created,
            "notified": notified,
        }
