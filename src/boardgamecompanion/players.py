"""Profili dei giocatori fissi.

Le partite conservano i nomi così come sono stati scritti: un profilo si collega alle partite
tramite il proprio nome e gli alias (es. «Raffaella» con alias «Raffi»), senza riscrivere lo storico.
"""
from __future__ import annotations

import base64
import binascii
import json
import re
from datetime import UTC, datetime
from typing import Any

from boardgamecompanion.database import Database
from boardgamecompanion.personal_state import PersonalStateError, PersonalStateNotFound

# Colori degli avatar (palette categoriale validata sul fondo scuro dell'app); il nome è sempre accanto.
PLAYER_COLORS = ("#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300", "#9085e9", "#e66767")
MAX_ALIASES = 10
MAX_PHOTO_BYTES = 600_000
PHOTO_TYPES = {"image/jpeg": b"\xff\xd8\xff", "image/png": b"\x89PNG\r\n\x1a\n", "image/webp": b"RIFF"}


class PlayerError(PersonalStateError):
    pass


class PlayerNotFound(PersonalStateNotFound):
    pass


def name_key(value: Any) -> str:
    # Stessa normalizzazione della funzione SQL bgc_name_key registrata da Database.connect.
    return " ".join(str(value or "").split()).casefold()


def _clean_name(value: Any, field: str = "name") -> str:
    if not isinstance(value, str):
        raise PlayerError(f"{field} must be text")
    text = re.sub(r"\s+", " ", value).strip()
    if not text:
        raise PlayerError(f"{field} is required")
    if len(text) > 60:
        raise PlayerError(f"{field} is too long")
    return text


class PlayerResolver:
    """Associa i nomi scritti nelle partite al profilo corrispondente (nome o alias, senza maiuscole)."""

    def __init__(self, profiles: list[dict[str, Any]]):
        self.profiles = {int(profile["id"]): profile for profile in profiles}
        self.by_key: dict[str, dict[str, Any]] = {}
        for profile in profiles:
            for name in (profile["name"], *profile["aliases"]):
                self.by_key.setdefault(name_key(name), profile)

    def resolve(self, name: Any) -> dict[str, Any] | None:
        return self.by_key.get(name_key(name)) if name else None

    def keys_for(self, profile_id: int) -> set[str]:
        profile = self.profiles.get(int(profile_id))
        if profile is None:
            return set()
        return {name_key(name) for name in (profile["name"], *profile["aliases"])}


class PlayerProfiles:
    def __init__(self, database: Database):
        self.database = database

    @staticmethod
    def _row(row: Any) -> dict[str, Any]:
        try:
            aliases = json.loads(row["aliases_json"] or "[]")
        except ValueError:
            aliases = []
        return {
            "id": int(row["id"]),
            "name": row["name"],
            "aliases": [str(alias) for alias in aliases] if isinstance(aliases, list) else [],
            "description": row["description"],
            "color": row["color"] or PLAYER_COLORS[(int(row["id"]) - 1) % len(PLAYER_COLORS)],
            "has_photo": bool(row["photo_type"]),
            "photo_version": row["photo_updated_at"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    _COLUMNS = "id,name,aliases_json,description,color,photo_type,photo_updated_at,created_at,updated_at"

    def list(self, connection: Any | None = None) -> list[dict[str, Any]]:
        query = f"SELECT {self._COLUMNS} FROM player_profiles ORDER BY lower(name)"
        if connection is not None:
            return [self._row(row) for row in connection.execute(query)]
        with self.database.connect() as own:
            return [self._row(row) for row in own.execute(query)]

    def resolver(self, connection: Any | None = None) -> PlayerResolver:
        return PlayerResolver(self.list(connection))

    def get(self, player_id: int) -> dict[str, Any]:
        with self.database.connect() as connection:
            row = connection.execute(
                f"SELECT {self._COLUMNS} FROM player_profiles WHERE id=?", (int(player_id),)
            ).fetchone()
        if row is None:
            raise PlayerNotFound(f"Player #{player_id} not found")
        return self._row(row)

    def _validated(self, values: dict[str, Any], *, partial: bool) -> dict[str, Any]:
        result: dict[str, Any] = {}
        if "name" in values or not partial:
            result["name"] = _clean_name(values.get("name"))
        if "aliases" in values:
            raw = values["aliases"] or []
            if not isinstance(raw, list) or len(raw) > MAX_ALIASES:
                raise PlayerError(f"aliases must be a list of at most {MAX_ALIASES} names")
            aliases: list[str] = []
            for alias in raw:
                clean = _clean_name(alias, "alias")
                if name_key(clean) not in {name_key(item) for item in aliases}:
                    aliases.append(clean)
            result["aliases"] = aliases
        if "description" in values:
            text = values["description"]
            if text is not None and not isinstance(text, str):
                raise PlayerError("description must be text")
            text = (text or "").strip()
            if len(text) > 1000:
                raise PlayerError("description is too long")
            result["description"] = text or None
        if "color" in values:
            color = values["color"]
            if color is not None and color not in PLAYER_COLORS:
                raise PlayerError("color must be one of the palette colors")
            result["color"] = color
        return result

    def _check_unique(self, connection: Any, player_id: int | None, name: str, aliases: list[str]) -> None:
        keys = [name_key(name), *(name_key(alias) for alias in aliases)]
        taken = {}
        for profile in self.list(connection):
            if profile["id"] == player_id:
                continue
            for other in (profile["name"], *profile["aliases"]):
                taken[name_key(other)] = profile["name"]
        for key in keys:
            if key in taken:
                raise PlayerError(f"«{key}» è già usato dal profilo di {taken[key]}")

    def create(self, values: dict[str, Any]) -> dict[str, Any]:
        data = self._validated(values, partial=False)
        aliases = [alias for alias in data.get("aliases", []) if name_key(alias) != name_key(data["name"])]
        now = datetime.now(UTC).isoformat()
        with self.database.transaction(immediate=True) as connection:
            self._check_unique(connection, None, data["name"], aliases)
            cursor = connection.execute(
                "INSERT INTO player_profiles(name,name_key,aliases_json,description,color,created_at,updated_at) "
                "VALUES(?,?,?,?,?,?,?)",
                (data["name"], name_key(data["name"]), json.dumps(aliases, ensure_ascii=False),
                 data.get("description"), data.get("color"), now, now),
            )
            player_id = int(cursor.lastrowid)
        return self.get(player_id)

    def update(self, player_id: int, values: dict[str, Any]) -> dict[str, Any]:
        current = self.get(player_id)
        data = self._validated(values, partial=True)
        name = data.get("name", current["name"])
        aliases = data.get("aliases", current["aliases"])
        # Rinominare non scollega lo storico: il nome precedente resta come alias.
        if name_key(name) != name_key(current["name"]) and "aliases" not in data:
            aliases = [*aliases, current["name"]]
        aliases = [alias for alias in aliases if name_key(alias) != name_key(name)][:MAX_ALIASES]
        now = datetime.now(UTC).isoformat()
        with self.database.transaction(immediate=True) as connection:
            self._check_unique(connection, int(player_id), name, aliases)
            connection.execute(
                "UPDATE player_profiles SET name=?,name_key=?,aliases_json=?,description=?,color=?,updated_at=? WHERE id=?",
                (name, name_key(name), json.dumps(aliases, ensure_ascii=False),
                 data.get("description", current["description"]),
                 data["color"] if "color" in data else (current["color"] if current["color"] in PLAYER_COLORS else None),
                 now, int(player_id)),
            )
        return self.get(player_id)

    def delete(self, player_id: int) -> None:
        """Elimina solo il profilo: le partite e i nomi registrati restano intatti."""
        with self.database.transaction(immediate=True) as connection:
            cursor = connection.execute("DELETE FROM player_profiles WHERE id=?", (int(player_id),))
            if cursor.rowcount == 0:
                raise PlayerNotFound(f"Player #{player_id} not found")

    def set_photo(self, player_id: int, data_url: Any) -> dict[str, Any]:
        if not isinstance(data_url, str):
            raise PlayerError("photo must be a data URL")
        match = re.fullmatch(r"data:(image/(?:jpeg|png|webp));base64,([A-Za-z0-9+/=\s]+)", data_url.strip())
        if not match:
            raise PlayerError("photo must be a JPEG, PNG or WebP data URL")
        try:
            content = base64.b64decode(match.group(2), validate=False)
        except (binascii.Error, ValueError) as exc:
            raise PlayerError("photo is not valid base64") from exc
        kind = match.group(1)
        if not content or len(content) > MAX_PHOTO_BYTES:
            raise PlayerError("photo is too large")
        if not content.startswith(PHOTO_TYPES[kind]) or (kind == "image/webp" and content[8:12] != b"WEBP"):
            raise PlayerError("photo content does not match its type")
        now = datetime.now(UTC).isoformat()
        with self.database.transaction(immediate=True) as connection:
            cursor = connection.execute(
                "UPDATE player_profiles SET photo=?,photo_type=?,photo_updated_at=?,updated_at=? WHERE id=?",
                (content, kind, now, now, int(player_id)),
            )
            if cursor.rowcount == 0:
                raise PlayerNotFound(f"Player #{player_id} not found")
        return self.get(player_id)

    def clear_photo(self, player_id: int) -> dict[str, Any]:
        now = datetime.now(UTC).isoformat()
        with self.database.transaction(immediate=True) as connection:
            cursor = connection.execute(
                "UPDATE player_profiles SET photo=NULL,photo_type=NULL,photo_updated_at=NULL,updated_at=? WHERE id=?",
                (now, int(player_id)),
            )
            if cursor.rowcount == 0:
                raise PlayerNotFound(f"Player #{player_id} not found")
        return self.get(player_id)

    def photo(self, player_id: int) -> tuple[bytes, str]:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT photo, photo_type FROM player_profiles WHERE id=?", (int(player_id),)
            ).fetchone()
        if row is None or not row["photo_type"]:
            raise PlayerNotFound(f"Player #{player_id} has no photo")
        return bytes(row["photo"]), row["photo_type"]
