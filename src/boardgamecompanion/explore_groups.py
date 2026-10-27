"""Macro groups for BGG categories and mechanics shown in Esplora.

BGG exposes ~85 categories and ~190 mechanics; grouping them keeps the page
short and lets a whole family be selected at once. Names are matched
case-insensitively; unknown names fall back to keyword rules, then "other".
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

# (key, label, members)
CATEGORY_GROUPS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("fantastic", "Fantasy e fantascienza", (
        "Fantasy", "Science Fiction", "Space Exploration", "Horror", "Zombies",
        "Mythology",
    )),
    ("adventure", "Avventura ed esplorazione", (
        "Adventure", "Exploration", "Travel", "Nautical", "Pirates",
        "Aviation / Flight", "Maze",
    )),
    ("history", "Storia ed epoche", (
        "Prehistoric", "Ancient", "Medieval", "Renaissance", "Age of Reason",
        "Napoleonic", "Post-Napoleonic", "Pike and Shot", "American West",
        "Arabian", "Civil War", "American Civil War", "American Indian Wars",
        "American Revolutionary War",
    )),
    ("war", "Guerra e combattimento", (
        "Wargame", "Fighting", "World War I", "World War II", "Korean War",
        "Vietnam War", "Modern Warfare",
    )),
    ("economy", "Economia e costruzione", (
        "Economic", "City Building", "Civilization", "Industry / Manufacturing",
        "Farming", "Territory Building", "Trains", "Transportation", "Political",
        "Environmental",
    )),
    ("mystery", "Deduzione e inganno", (
        "Deduction", "Bluffing", "Negotiation", "Murder / Mystery",
        "Spies / Secret Agents", "Mafia",
    )),
    ("party", "Party e famiglia", (
        "Party Game", "Children's Game", "Humor", "Trivia", "Word Game",
        "Real-time", "Mature / Adult", "Music", "Educational",
    )),
    ("logic", "Logica e astratti", (
        "Abstract Strategy", "Puzzle", "Math", "Number", "Memory",
    )),
    ("format", "Carte, dadi e componenti", (
        "Card Game", "Dice", "Action / Dexterity", "Collectible Components",
        "Miniatures", "Electronic", "Print & Play", "Game System", "Book",
        "Expansion for Base-game", "Fan Expansion",
    )),
    ("theme", "Temi e cultura pop", (
        "Movies / TV / Radio theme", "Novel-based", "Comic Book / Strip",
        "Video Game Theme", "Animals", "Sports", "Racing", "Religious", "Medical",
    )),
)

MECHANIC_GROUPS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("cards", "Carte e draft", (
        "Hand Management", "Card Drafting", "Open Drafting", "Closed Drafting",
        "Deck, Bag, and Pool Building", "Deck Construction", "Trick-taking",
        "Ladder Climbing", "Melding and Splaying", "Multi-Use Cards",
        "Card Play Conflict Resolution", "Command Cards",
        "Campaign / Battle Card Driven", "Layering", "Hidden Card Placement",
    )),
    ("engine", "Motore ed economia", (
        "Engine Building", "Tableau Building", "Set Collection", "Contracts",
        "Income", "Loans", "Market", "Investment", "Stock Holding",
        "Commodity Speculation", "Increase Value of Unchosen Resources",
        "Delayed Purchase", "Victory Points as a Resource",
        "Automatic Resource Growth", "Ownership", "Resource to Move",
        "End Game Bonuses", "Mancala", "Upgrades", "Tech Trees / Tech Tracks",
        "Tags", "Hidden Victory Points", "Resource Queue", "Highest-Lowest Scoring",
        "Neighbor Scope", "Finale Ending",
    )),
    ("actions", "Azioni e turni", (
        "Worker Placement", "Worker Placement with Dice Workers",
        "Worker Placement, Different Worker Types", "Action Points",
        "Action Queue", "Action Drafting", "Action Retrieval", "Action Timer",
        "Action / Event", "Rondel", "Follow", "Variable Phase Order",
        "Simultaneous Action Selection", "Role Selection", "Time Track",
        "Interrupts", "Order Counters", "Passed Action Token", "Lose a Turn",
        "Once-Per-Game Abilities", "Programmed Movement", "Bingo",
    )),
    ("dice", "Dadi e fortuna", (
        "Dice Rolling", "Push Your Luck", "Re-rolling and Locking",
        "Die Icon Resolution", "Chit-Pull System", "Random Production",
        "Cube Tower", "Roll / Spin and Move", "Stat Check Resolution",
        "Critical Hits and Failures", "Lucky Draws",
    )),
    ("map", "Mappa e movimento", (
        "Grid Movement", "Hexagon Grid", "Square Grid", "Point to Point Movement",
        "Area Movement", "Modular Board", "Network and Route Building",
        "Pick-up and Deliver", "Map Addition", "Map Reduction", "Map Deformation",
        "Movement Points", "Movement Template", "Impulse Movement",
        "Relative Movement", "Measurement Movement", "Three Dimensional Movement",
        "Track Movement", "Moving Multiple Units", "Pattern Movement", "Race",
        "Crayon Rail System", "Pieces as Map", "Hidden Movement", "Slide/Push",
        "Slide / Push", "Facing",
    )),
    ("conflict", "Conflitto e territorio", (
        "Area Majority / Influence", "Take That", "Player Elimination",
        "Area-Impulse", "King of the Hill", "Kill Steal", "Zone of Control",
        "Line of Sight", "Ratio / Combat Results Table", "Simulation",
        "Minimap Resolution", "Force Commitment", "Siege", "Catch the Leader",
        "Secret Unit Deployment", "Tug of War", "Lane Battler",
        "Algorithmic Resolution",
    )),
    ("social", "Aste, bluff e trattative", (
        "Auction / Bidding", "Auction: Dutch", "Auction: English",
        "Auction: Fixed Placement", "Auction: Once Around", "Auction: Sealed Bid",
        "Auction: Turn Order Until Pass", "Auction: Dexterity",
        "Auction: Dutch Priority", "Auction: Multiple Lot",
        "Constrained Bidding", "Selection Order Bid", "Turn Order: Auction",
        "Betting and Bluffing", "Hidden Roles", "Negotiation", "Trading",
        "Bribery", "Alliances", "Deduction", "Voting", "Communication Limits",
        "Targeted Clues", "Player Judge", "Prisoner's Dilemma",
        "Traitor Game", "Questions and Answers",
        "Roles with Asymmetric Information", "I Cut, You Choose",
    )),
    ("spatial", "Tessere e schemi", (
        "Tile Placement", "Pattern Building", "Pattern Recognition",
        "Grid Coverage", "Enclosure", "Line Drawing", "Connections",
        "Paper-and-Pencil", "Matching", "Memory", "Drawing", "Square Grid Coverage",
        "Spelling", "Ordering",
    )),
    ("dexterity", "Abilità e tempo reale", (
        "Real-Time", "Speed Matching", "Stacking and Balancing", "Flicking",
        "Physical Removal", "Acting", "Singing", "Rock-Paper-Scissors",
        "Elapsed Real Time Ending", "Hot Potato", "Chaining", "Static Capture",
        "Bias",
    )),
    ("modes", "Cooperazione e narrazione", (
        "Cooperative Game", "Solo / Solitaire Game", "Semi-Cooperative Game",
        "Team-Based Game", "One vs. All", "Legacy Game",
        "Scenario / Mission / Campaign Game", "Narrative Choice / Paragraph",
        "Storytelling", "Role Playing", "Variable Player Powers",
        "Variable Set-up", "Events", "Score-and-Reset Game", "Single Loser Game",
        "Advantage Token", "Induction", "Sudden Death Ending", "Single Play",
    )),
)

# Fallback for names not listed above (BGG adds mechanics over time).
_MECHANIC_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("social", ("auction", "bid", "bluff", "negotiat", "vot")),
    ("actions", ("turn order", "worker", "action")),
    ("cards", ("card", "draft", "deck")),
    ("dice", ("dice", "die ", "roll", "luck")),
    ("map", ("movement", "grid", "map", "route", "board")),
    ("spatial", ("tile", "pattern", "placement")),
    ("modes", ("cooperative", "solo", "campaign", "narrative", "team")),
)
_CATEGORY_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("war", ("war",)),
    ("format", ("expansion", "card", "dice")),
    ("theme", ("theme",)),
)

OTHER_GROUP = ("other", "Altro")


def _index(groups):
    return {
        member.casefold(): key
        for key, _label, members in groups
        for member in members
    }


_CATEGORY_INDEX = _index(CATEGORY_GROUPS)
_MECHANIC_INDEX = _index(MECHANIC_GROUPS)


@lru_cache(maxsize=4096)
def group_key(kind: str, name: str) -> str:
    folded = str(name).strip().casefold()
    index, keywords = (
        (_CATEGORY_INDEX, _CATEGORY_KEYWORDS)
        if kind == "category"
        else (_MECHANIC_INDEX, _MECHANIC_KEYWORDS)
    )
    if folded in index:
        return index[folded]
    for key, words in keywords:
        if any(word in folded for word in words):
            return key
    return OTHER_GROUP[0]


def group_definitions(kind: str) -> list[dict[str, Any]]:
    groups = CATEGORY_GROUPS if kind == "category" else MECHANIC_GROUPS
    return [
        {"key": key, "label": label}
        for key, label, _members in groups
    ] + [{"key": OTHER_GROUP[0], "label": OTHER_GROUP[1]}]


def valid_group_keys(kind: str) -> set[str]:
    return {item["key"] for item in group_definitions(kind)}
