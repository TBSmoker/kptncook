from datetime import date

from kptncook.repositories import IngredientRecord, RecipeInDb, RecipeRepository


def test_no_repository_file_returns_empty_list(tmpdir):
    repo = RecipeRepository(tmpdir)
    assert repo.list() == []


def test_entries_persist_in_sqlite(tmpdir):
    today = date.today()
    repo = RecipeRepository(tmpdir)
    data = {"_id": {"$oid": "1"}, "title": "test"}
    recipe = RecipeInDb(date=today, data=data)
    repo.add(recipe)

    [recipe_from_repo] = repo.list()
    assert recipe_from_repo.date == today
    assert recipe_from_repo.data == data
    assert repo.path.exists()


def test_add_recipe_list_to_repository(tmpdir):
    repo = RecipeRepository(tmpdir)
    data1 = {"_id": {"$oid": "1"}, "title": "test"}
    recipe1 = RecipeInDb(date=date.today(), data=data1)
    data2 = {"_id": {"$oid": "2"}, "title": "test"}
    recipe2 = RecipeInDb(date=date.today(), data=data2)
    recipes = [recipe1, recipe2]
    repo.add_list(recipes)
    assert len(repo.list()) == 2


def test_needs_to_be_synced(tmpdir):
    repo = RecipeRepository(tmpdir)
    today = date.today()
    assert repo.needs_to_be_synced(today)

    data = {"_id": {"$oid": "1"}, "title": "test"}
    recipe = RecipeInDb(date=today, data=data)
    repo.add(recipe)
    assert not repo.needs_to_be_synced(today)


def test_ingredients_are_reused(tmpdir):
    repo = RecipeRepository(tmpdir)
    base_details = {
        "typ": "tomato",
        "localizedTitle": {"de": "Tomate", "en": "Tomato"},
        "numberTitle": {"de": "Tomaten"},
        "category": "vegetable",
    }
    recipe1 = RecipeInDb(
        date=date.today(),
        data={
            "_id": {"$oid": "1"},
            "ingredients": [
                {"quantity": 1, "measure": "piece", "ingredient": base_details}
            ],
        },
    )
    recipe2 = RecipeInDb(
        date=date.today(),
        data={
            "_id": {"$oid": "2"},
            "ingredients": [
                {"quantity": 2, "measure": "piece", "ingredient": base_details}
            ],
        },
    )

    repo.add_list([recipe1, recipe2])
    ingredients = repo.list_ingredients()

    assert len(ingredients) == 1
    ingredient: IngredientRecord = ingredients[0]
    assert ingredient.localized_title.de == "Tomate"
    assert ingredient.localized_title.en == "Tomato"
