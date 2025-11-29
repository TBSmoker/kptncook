"""
SQLite-backed repositories for persisting recipes and ingredients.

The database is structured so that ingredients are stored once and can be
referenced by multiple recipes. Localized strings are persisted per language to
retain multi-language data.
"""

from __future__ import annotations

import json
import shutil
import sqlite3
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from typing import Iterator

from pydantic import BaseModel

from .models import LocalizedString


class RecipeInDb(BaseModel):
    date: date
    data: dict

    @property
    def id(self):
        return self.data["_id"]["$oid"]


class IngredientRecord(BaseModel):
    key: str
    typ: str | None = None
    category: str | None = None
    localized_title: LocalizedString
    number_title: LocalizedString | None = None
    uncountable_title: LocalizedString | None = None


class RecipeRepository:
    name: str = "kptncook.db"

    def __init__(self, base_dir: Path):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    @property
    def path(self) -> Path:
        return self.base_dir / self.name

    @property
    def backup_path(self) -> Path:
        return self.base_dir / f"{self.name}.backup"

    def create_backup(self):
        if self.path.exists():
            shutil.copyfile(self.path, self.backup_path)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        with sqlite3.connect(self.path) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON;")
            yield conn

    def _ensure_schema(self):
        if not self.path.parent.exists():
            self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS recipes (
                    id TEXT PRIMARY KEY,
                    date TEXT NOT NULL,
                    title_en TEXT,
                    title_de TEXT,
                    title_es TEXT,
                    title_fr TEXT,
                    title_pt TEXT,
                    raw_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS ingredients (
                    key TEXT PRIMARY KEY,
                    typ TEXT,
                    category TEXT,
                    title_en TEXT,
                    title_de TEXT,
                    title_es TEXT,
                    title_fr TEXT,
                    title_pt TEXT,
                    number_title_en TEXT,
                    number_title_de TEXT,
                    number_title_es TEXT,
                    number_title_fr TEXT,
                    number_title_pt TEXT,
                    uncountable_title_en TEXT,
                    uncountable_title_de TEXT,
                    uncountable_title_es TEXT,
                    uncountable_title_fr TEXT,
                    uncountable_title_pt TEXT
                );

                CREATE TABLE IF NOT EXISTS recipe_ingredients (
                    recipe_id TEXT NOT NULL,
                    ingredient_key TEXT NOT NULL,
                    quantity REAL,
                    measure TEXT,
                    position INTEGER NOT NULL,
                    PRIMARY KEY (recipe_id, position),
                    FOREIGN KEY (recipe_id) REFERENCES recipes(id) ON DELETE CASCADE,
                    FOREIGN KEY (ingredient_key) REFERENCES ingredients(key) ON DELETE CASCADE
                );
                """
            )

    def _localized_values(self, values: dict | None) -> tuple[str | None, ...]:
        values = values or {}
        return (
            values.get("en"),
            values.get("de"),
            values.get("es"),
            values.get("fr"),
            values.get("pt"),
        )

    def _canonical_ingredient_key(self, ingredient_details: dict) -> str:
        if ingredient_details.get("typ"):
            return str(ingredient_details["typ"])
        localized = ingredient_details.get("localizedTitle", {})
        for lang in ("en", "de", "es", "fr", "pt"):
            title = localized.get(lang)
            if title:
                return "_".join(title.lower().split())
        raise ValueError("Ingredient is missing both typ and localizedTitle")

    def _upsert_ingredient(self, conn: sqlite3.Connection, ingredient_details: dict):
        key = self._canonical_ingredient_key(ingredient_details)
        localized_title = self._localized_values(ingredient_details.get("localizedTitle"))
        number_title = self._localized_values(ingredient_details.get("numberTitle"))
        uncountable_title = self._localized_values(
            ingredient_details.get("uncountableTitle")
        )
        conn.execute(
            """
            INSERT INTO ingredients (
                key, typ, category,
                title_en, title_de, title_es, title_fr, title_pt,
                number_title_en, number_title_de, number_title_es, number_title_fr, number_title_pt,
                uncountable_title_en, uncountable_title_de, uncountable_title_es, uncountable_title_fr, uncountable_title_pt
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                typ=excluded.typ,
                category=excluded.category,
                title_en=excluded.title_en,
                title_de=excluded.title_de,
                title_es=excluded.title_es,
                title_fr=excluded.title_fr,
                title_pt=excluded.title_pt,
                number_title_en=excluded.number_title_en,
                number_title_de=excluded.number_title_de,
                number_title_es=excluded.number_title_es,
                number_title_fr=excluded.number_title_fr,
                number_title_pt=excluded.number_title_pt,
                uncountable_title_en=excluded.uncountable_title_en,
                uncountable_title_de=excluded.uncountable_title_de,
                uncountable_title_es=excluded.uncountable_title_es,
                uncountable_title_fr=excluded.uncountable_title_fr,
                uncountable_title_pt=excluded.uncountable_title_pt
            ;
            """,
            (
                key,
                ingredient_details.get("typ"),
                ingredient_details.get("category"),
                *localized_title,
                *number_title,
                *uncountable_title,
            ),
        )
        return key

    def _upsert_recipe(self, conn: sqlite3.Connection, recipe: RecipeInDb):
        recipe_id = recipe.id
        raw_json = json.dumps(recipe.data)
        localized_title = self._localized_values(recipe.data.get("localizedTitle"))
        conn.execute(
            """
            INSERT INTO recipes (
                id, date, title_en, title_de, title_es, title_fr, title_pt, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                date=excluded.date,
                title_en=excluded.title_en,
                title_de=excluded.title_de,
                title_es=excluded.title_es,
                title_fr=excluded.title_fr,
                title_pt=excluded.title_pt,
                raw_json=excluded.raw_json
            ;
            """,
            (
                recipe_id,
                recipe.date.isoformat(),
                *localized_title,
                raw_json,
            ),
        )
        conn.execute(
            "DELETE FROM recipe_ingredients WHERE recipe_id = ?;", (recipe_id,)
        )
        for position, ingredient in enumerate(recipe.data.get("ingredients", [])):
            ingredient_details = ingredient.get("ingredient", {})
            ingredient_key = self._upsert_ingredient(conn, ingredient_details)
            conn.execute(
                """
                INSERT INTO recipe_ingredients (
                    recipe_id, ingredient_key, quantity, measure, position
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(recipe_id, position) DO UPDATE SET
                    ingredient_key=excluded.ingredient_key,
                    quantity=excluded.quantity,
                    measure=excluded.measure
                ;
                """,
                (
                    recipe_id,
                    ingredient_key,
                    ingredient.get("quantity"),
                    ingredient.get("measure"),
                    position,
                ),
            )

    def list_by_id(self):
        by_id = {}
        for recipe in self.list():
            by_id[recipe.id] = recipe
        return by_id

    def needs_to_be_synced(self, _date: date):
        """
        Return True if there are no recipes for date.
        """
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM recipes WHERE date = ? LIMIT 1;", (_date.isoformat(),)
            ).fetchone()
        return row is None

    def add(self, recipe: RecipeInDb):
        self.create_backup()
        with self._connect() as conn:
            self._upsert_recipe(conn, recipe)

    def add_list(self, recipes: list[RecipeInDb]):
        self.create_backup()
        with self._connect() as conn:
            for recipe in recipes:
                self._upsert_recipe(conn, recipe)

    def _rows_to_recipes(self, rows: list[sqlite3.Row]) -> list[RecipeInDb]:
        recipes = []
        for row in rows:
            recipes.append(
                RecipeInDb(
                    date=date.fromisoformat(row["date"]),
                    data=json.loads(row["raw_json"]),
                )
            )
        return recipes

    def list(self):
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT date, raw_json FROM recipes ORDER BY date DESC, id ASC;"
            ).fetchall()
        return self._rows_to_recipes(rows)

    def get(self, recipe_id: str) -> RecipeInDb | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT date, raw_json FROM recipes WHERE id = ? LIMIT 1;",
                (recipe_id,),
            ).fetchone()
        if row is None:
            return None
        return self._rows_to_recipes([row])[0]

    def list_ingredients(self) -> list[IngredientRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM ingredients ORDER BY COALESCE(title_de, title_en, typ);"
            ).fetchall()
        ingredients = []
        for row in rows:
            localized_title = LocalizedString(
                en=row["title_en"],
                de=row["title_de"],
                es=row["title_es"],
                fr=row["title_fr"],
                pt=row["title_pt"],
            )
            number_title = LocalizedString(
                en=row["number_title_en"],
                de=row["number_title_de"],
                es=row["number_title_es"],
                fr=row["number_title_fr"],
                pt=row["number_title_pt"],
            )
            uncountable_title = LocalizedString(
                en=row["uncountable_title_en"],
                de=row["uncountable_title_de"],
                es=row["uncountable_title_es"],
                fr=row["uncountable_title_fr"],
                pt=row["uncountable_title_pt"],
            )
            ingredients.append(
                IngredientRecord(
                    key=row["key"],
                    typ=row["typ"],
                    category=row["category"],
                    localized_title=localized_title,
                    number_title=number_title
                    if any(number_title.model_dump().values())
                    else None,
                    uncountable_title=uncountable_title
                    if any(uncountable_title.model_dump().values())
                    else None,
                )
            )
        return ingredients
