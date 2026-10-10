from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal


AvailabilityStatus = Literal[
    "official_catalog_no_specific_pdf",
    "rules_in_components",
    "physical_rule_sheet",
    "physical_rules_insert",
    "external_exact_manual",
    "official_page_no_dedicated_pdf",
    "physical_bounty_book",
    "rules_in_cards_reference",
]


@dataclass(frozen=True)
class RulebookAvailability:
    status: AvailabilityStatus
    label: str
    detail: str
    confidence: Literal["high", "medium"]
    action: Literal["retry_official", "open_external"]
    evidence_url: str
    external_url: str | None = None

    def as_payload(self) -> dict[str, object]:
        return asdict(self)


_AWAKEN_NO_SPECIFIC = RulebookAvailability(
    status="official_catalog_no_specific_pdf",
    label="Nessun regolamento specifico nel catalogo ufficiale",
    detail=(
        "Il catalogo ufficiale Awaken Realms è stato verificato e non pubblica "
        "un rulebook con corrispondenza esatta per questa espansione. Il gioco "
        "può usare il regolamento della famiglia/base o regole contenute nei componenti."
    ),
    confidence="high",
    action="retry_official",
    evidence_url="https://awakenrealms.com/data/files.json",
)

_AVAILABILITY: dict[int, RulebookAvailability] = {
    # Awaken Realms: exact official-catalog lookup completed with no expansion rulebook.
    404920: _AWAKEN_NO_SPECIFIC,  # Dragon Eclipse: #NoMystlingLeftBehind
    402543: _AWAKEN_NO_SPECIFIC,  # Dragon Eclipse: Foray into the Shadow Realms
    402544: _AWAKEN_NO_SPECIFIC,  # Dragon Eclipse: Untamed Arena
    291131: _AWAKEN_NO_SPECIFIC,  # Etherfields: Funeral Witch Campaign
    290840: _AWAKEN_NO_SPECIFIC,  # Etherfields: Sphinx Campaign
    351544: _AWAKEN_NO_SPECIFIC,  # Etherfields: Harpy & She-Wolf Campaigns
    274795: _AWAKEN_NO_SPECIFIC,  # Tainted Grail: Age of Legends & Last Knight
    267325: _AWAKEN_NO_SPECIFIC,  # Tainted Grail: Echoes of the Past
    267408: _AWAKEN_NO_SPECIFIC,  # Tainted Grail: Red Death

    # Monolith's official Batman GCC page exposes Arkham, Wayne Manor and Versus
    # booklets, but no dedicated Suicide Squad booklet.
    285922: RulebookAvailability(
        status="official_catalog_no_specific_pdf",
        label="Nessun booklet specifico pubblicato da Monolith",
        detail=(
            "La pagina ufficiale Batman GCC di Monolith è stata verificata: espone "
            "booklet per Arkham Asylum, Wayne Manor e Versus, ma non un booklet "
            "specifico per Suicide Squad."
        ),
        confidence="high",
        action="retry_official",
        evidence_url=(
            "https://monolithedition.com/en/portfolio/"
            "batman-gotham-city-chronicles/"
        ),
    ),

    # Chip Theory product/support pages describe these as encounter/card/book
    # content rather than expansions with a separate rulebook.
    239292: RulebookAvailability(
        status="rules_in_components",
        label="Regole nei componenti; nessun manuale autonomo",
        detail=(
            "40 Days in Daelore aggiunge Encounter cards e Baddie chips. Il prodotto "
            "ufficiale non elenca un regolamento separato."
        ),
        confidence="high",
        action="retry_official",
        evidence_url=(
            "https://chiptheorygames.com/products/"
            "40-days-in-daelore-additional-baddies-encounters-for-too-many-bones"
        ),
    ),
    349578: RulebookAvailability(
        status="rules_in_components",
        label="Regole nei componenti; nessun manuale autonomo",
        detail=(
            "Rage of Tyranny è composto da Tyrant cards/chips/dice, Encounter cards "
            "e Loot. Le regole specifiche sono veicolate dai componenti e dal supporto."
        ),
        confidence="high",
        action="retry_official",
        evidence_url="https://chiptheorygames.com/products/too-many-bones-rage-of-tyranny",
    ),
    349916: RulebookAvailability(
        status="rules_in_components",
        label="Regole nel libro/carte; nessun manuale autonomo",
        detail=(
            "The Automaton of Shale è un'avventura giocata nel pop-up book o nel "
            "gameplay pack di carte; il prodotto ufficiale non prevede un rulebook "
            "separato."
        ),
        confidence="high",
        action="retry_official",
        evidence_url=(
            "https://chiptheorygames.com/products/"
            "too-many-bones-the-automaton-of-shale"
        ),
    ),

    # These Diskwars expansions physically include a rule sheet. The current
    # publisher support material exposes the core rulebook/FAQ, not a verified
    # downloadable copy of the expansion sheet.
    156053: RulebookAvailability(
        status="physical_rule_sheet",
        label="Rule sheet fisico; PDF ufficiale non verificato",
        detail=(
            "Hammer and Hold include un rule sheet fisico. Non è stato trovato un "
            "PDF publisher-hosted verificabile; il supporto FFG pubblico rimanda "
            "al core rulebook e alle FAQ."
        ),
        confidence="high",
        action="retry_official",
        evidence_url=(
            "https://www.fantasyflightgames.com/ffg_content/diskwars/"
            "support/faq-updates/WHD_FAQ.pdf"
        ),
    ),
    156054: RulebookAvailability(
        status="physical_rule_sheet",
        label="Rule sheet fisico; PDF ufficiale non verificato",
        detail=(
            "Legions of Darkness include un rule sheet fisico. Non è stato trovato "
            "un PDF publisher-hosted verificabile; il supporto FFG pubblico rimanda "
            "al core rulebook e alle FAQ."
        ),
        confidence="high",
        action="retry_official",
        evidence_url=(
            "https://www.fantasyflightgames.com/ffg_content/diskwars/"
            "support/faq-updates/WHD_FAQ.pdf"
        ),
    ),
    174560: RulebookAvailability(
        status="physical_rules_insert",
        label="Rules insert fisico; PDF ufficiale non verificato",
        detail=(
            "The Great Devourer introduce regole Tyranid/Synapse tramite un rules "
            "insert della confezione. Il supporto pubblico FFG verificato espone "
            "core rules e FAQ, ma non è emerso un PDF ufficiale dell'insert."
        ),
        confidence="medium",
        action="retry_official",
        evidence_url=(
            "https://www.fantasyflightgames.com/en/more/"
            "warhammer-40k-conquest-organized-play/"
        ),
    ),

    # Dragori lists these Arena boxes as add-ons/components on the official
    # extras page, without a dedicated downloadable rulebook.
    312509: RulebookAvailability(
        status="official_page_no_dedicated_pdf",
        label="Add-on ufficiale senza rulebook pubblico dedicato",
        detail=(
            "Dragon Collection è presentata da Dragori come contenuto/add-on di Arena "
            "con miniature e modalità aggiuntive. La pagina ufficiale verificata non "
            "pubblica un PDF-rulebook dedicato."
        ),
        confidence="high",
        action="retry_official",
        evidence_url="https://dragorigames.com/arena-the-contest-extras/",
    ),
    309701: RulebookAvailability(
        status="official_page_no_dedicated_pdf",
        label="Add-on ufficiale senza rulebook pubblico dedicato",
        detail=(
            "Legendary Box è presentata da Dragori come box di eroi, villain, boss e "
            "miniature aggiuntive. La pagina ufficiale verificata non pubblica un "
            "PDF-rulebook dedicato."
        ),
        confidence="high",
        action="retry_official",
        evidence_url="https://dragorigames.com/arena-the-contest-extras/",
    ),
    303730: RulebookAvailability(
        status="official_page_no_dedicated_pdf",
        label="Add-on ufficiale senza rulebook pubblico dedicato",
        detail=(
            "Madness Box è presentata da Dragori come contenuto aggiuntivo per Arena/"
            "Tanares. La pagina ufficiale verificata non pubblica un PDF-rulebook "
            "dedicato."
        ),
        confidence="high",
        action="retry_official",
        evidence_url="https://dragorigames.com/arena-the-contest-extras/",
    ),

    # Middara bounty packs carry their scenario/build rules in the physical
    # Bounty Book. Old public Dropbox material is beta/playtest-era and must not
    # be promoted as the current retail rulebook.
    284955: RulebookAvailability(
        status="physical_bounty_book",
        label="Regole nel Bounty Book fisico",
        detail=(
            "The Cave Sickle Queen include il Bounty Book con build guide e regole "
            "per l'uso standalone. Non è stato verificato un PDF retail corrente "
            "publisher-hosted; i vecchi file pubblici erano materiale beta/playtest."
        ),
        confidence="high",
        action="retry_official",
        evidence_url=(
            "https://middara.com/products/"
            "the-cave-sickle-queen-bounty-pack"
        ),
    ),
    284716: RulebookAvailability(
        status="physical_bounty_book",
        label="Regole nel Bounty Book fisico",
        detail=(
            "The Pit Boss include le regole/build guide nel Bounty Book. Non è stato "
            "verificato un PDF retail corrente publisher-hosted."
        ),
        confidence="high",
        action="retry_official",
        evidence_url="https://middara.com/products/the-pit-boss-bounty-pack",
    ),

    # Modiphius lists no standalone rulebook for these Skyrim Adventure Game
    # expansions. Their product contents are cards, encounters, campaign material
    # and reference cards, while the base game explicitly includes the rulebook.
    350624: RulebookAvailability(
        status="rules_in_cards_reference",
        label="Regole in carte/materiali e reference card",
        detail=(
            "Dawnguard aggiunge fazioni, luoghi, carte, punchboard e reference cards; "
            "la pagina ufficiale Modiphius non elenca un rulebook autonomo. Richiede "
            "il gioco base."
        ),
        confidence="high",
        action="retry_official",
        evidence_url=(
            "https://modiphius.net/en-us/products/"
            "the-elder-scrolls-skyrim-adventure-board-game-dawnguard"
        ),
    ),
    350623: RulebookAvailability(
        status="rules_in_cards_reference",
        label="Regole in carte/materiali e reference card",
        detail=(
            "From the Ashes aggiunge incontri, mini-campagne, carte, punchboard e una "
            "reference card; la pagina ufficiale Modiphius non elenca un rulebook "
            "autonomo. Richiede il gioco base."
        ),
        confidence="high",
        action="retry_official",
        evidence_url=(
            "https://modiphius.net/products/"
            "the-elder-scrolls-skyrim-adventure-board-game-from-the-ashes"
        ),
    ),

    # Exact publisher manual mirrored externally. Keep it out of unattended
    # acquisition because the host is not the publisher.
    334888: RulebookAvailability(
        status="external_exact_manual",
        label="Manuale esatto reperito su mirror esterno",
        detail=(
            "Il manuale Tiny Epic Dungeons: Stories è stato verificato come documento "
            "esatto dell'espansione, ma la copia raggiungibile non è ospitata da "
            "Gamelyn. Perciò non viene auto-acquisita come fonte ufficiale."
        ),
        confidence="medium",
        action="open_external",
        evidence_url="https://www.boardgamesbot.com/tiny-epic-dungeons-stories/rules-pdf",
        external_url=(
            "https://www.boardgamesbot.com/assets/games-library/"
            "tiny-epic-dungeons-stories/manual_pt_br.pdf?raw=1"
        ),
    ),
}


def rulebook_availability_bgg_ids() -> frozenset[int]:
    """Return curated BGG IDs whose lack of a standalone PDF is already resolved."""

    return frozenset(_AVAILABILITY)


def get_rulebook_availability(bgg_id: int) -> dict[str, object] | None:
    item = _AVAILABILITY.get(int(bgg_id))
    return item.as_payload() if item is not None else None
