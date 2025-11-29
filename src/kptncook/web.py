from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .api import KptnCookClient, parse_id
from .config import settings
from .repositories import RecipeRepository

BASE_DIR = Path(__file__).parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(title="KptnCook Web", description="Web frontend for KptnCook data")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def get_repo() -> RecipeRepository:
    return RecipeRepository(settings.root)


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    repo = get_repo()
    recipes = repo.list()
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "recipes": recipes},
    )


@app.get("/recipes/{recipe_id}", response_class=HTMLResponse)
async def recipe_detail(request: Request, recipe_id: str):
    repo = get_repo()
    recipe = repo.get(recipe_id)
    if recipe is None:
        raise HTTPException(status_code=404, detail="Recipe not found")
    return templates.TemplateResponse(
        "recipe.html",
        {
            "request": request,
            "recipe": recipe,
            "localized_title": recipe.data.get("localizedTitle", {}),
            "ingredients": recipe.data.get("ingredients", []),
            "steps": recipe.data.get("steps", []),
        },
    )


@app.get("/ingredients", response_class=HTMLResponse)
async def list_ingredients(request: Request):
    repo = get_repo()
    ingredients = repo.list_ingredients()
    return templates.TemplateResponse(
        "ingredients.html",
        {"request": request, "ingredients": ingredients},
    )


@app.post("/actions/sync-today")
async def sync_today():
    client = KptnCookClient()
    recipes = client.list_today()
    repo = get_repo()
    repo.add_list(recipes)
    return RedirectResponse(url="/", status_code=303)


@app.post("/actions/search")
async def search_by_id(recipe_identifier: str = Form(...)):
    parsed = parse_id(recipe_identifier)
    if parsed is None:
        raise HTTPException(status_code=400, detail="Could not parse recipe id")
    client = KptnCookClient()
    recipes = client.get_by_ids([parsed])
    if recipes:
        repo = get_repo()
        repo.add_list(recipes)
    return RedirectResponse(url="/", status_code=303)


@app.post("/actions/backup-favorites")
async def backup_favorites():
    client = KptnCookClient()
    favorites = client.list_favorites()
    ids = [("oid", oid["identifier"]) for oid in favorites]
    recipes = client.get_by_ids(ids)
    repo = get_repo()
    repo.add_list(recipes)
    return RedirectResponse(url="/", status_code=303)
