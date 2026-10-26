"""Pantry drafts never write stock; only an explicit reviewed commit does."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session, selectinload

from ..chatgpt import (
    ConnectionError,
    access_credentials,
    account_models,
    credential_lock,
    read_credentials,
    save_credentials,
)
from ..config import get_settings
from ..db import get_session
from ..models import PantryItem, Recipe
from ..services.pantry import Candidate, canonical_name, photo_candidates, text_candidates

router = APIRouter(prefix="/pantry")
limiter = Limiter(key_func=get_remote_address)
SessionDep = Annotated[Session, Depends(get_session)]


class TextDraft(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    text: str = Field(min_length=1, max_length=12000)


class ReviewedItems(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: Literal["text", "photo"]
    items: list[Candidate] = Field(min_length=1, max_length=100)


@router.get("/capabilities")
def capabilities():
    path = Path(get_settings().forkit_chatgpt_credentials_path)
    try:
        value = read_credentials(path)
        return {
            "photo_enabled": bool(value.get("model")),
            "chatgpt_connected": True,
            "model": value.get("model"),
            "photo_provider": "ChatGPT",
        }
    except (OSError, ValueError, ConnectionError):
        return {
            "photo_enabled": False,
            "chatgpt_connected": False,
            "model": None,
            "photo_provider": "ChatGPT",
        }


@router.delete("/chatgpt", status_code=204)
def disconnect_chatgpt():
    path = Path(get_settings().forkit_chatgpt_credentials_path)
    with credential_lock(path):
        path.unlink(missing_ok=True)
    return Response(status_code=204)


@router.get("/chatgpt/models")
def models():
    try:
        return {
            "models": account_models(
                access_credentials(Path(get_settings().forkit_chatgpt_credentials_path))
            )
        }
    except (OSError, ValueError, ConnectionError) as exc:
        raise HTTPException(503, "Connect ChatGPT to choose a photo model") from exc


class ModelSelection(BaseModel):
    model: str = Field(min_length=1, max_length=200)


@router.put("/chatgpt/model")
def select_model(body: ModelSelection):
    path = Path(get_settings().forkit_chatgpt_credentials_path)
    try:
        available = account_models(access_credentials(path))
        if body.model not in {m["slug"] for m in available}:
            raise HTTPException(422, "Choose a model available to your ChatGPT account")
        with credential_lock(path):
            value = read_credentials(path)
            value["model"] = body.model
            save_credentials(path, value)
        return {"model": body.model}
    except (OSError, ValueError, ConnectionError) as exc:
        raise HTTPException(503, "ChatGPT connection needs attention") from exc


@router.get("")
def list_items(session: SessionDep):
    return {
        "items": [
            {
                "id": p.id,
                "name": p.name,
                "quantity": p.quantity,
                "unit": p.unit,
                "notes": p.notes,
                "source": p.source,
            }
            for p in session.scalars(select(PantryItem).order_by(PantryItem.name)).all()
        ]
    }


@router.post("/preview/text")
def preview_text(body: TextDraft):
    try:
        return {"items": [c.model_dump() for c in text_candidates(body.text)]}
    except ValidationError as exc:
        raise HTTPException(422, "Check ingredient names and keep each entry short") from exc


@router.post("/preview/photo")
@limiter.limit("5/minute")
async def preview_photo(request: Request):
    # Stream with an enforced cap even when Content-Length is absent or dishonest.
    if request.headers.get("content-type", "").split(";")[0] not in (
        "image/jpeg",
        "image/png",
        "image/webp",
    ):
        raise HTTPException(415, "Use a JPEG, PNG or WebP photo")
    data = bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data) > 8 * 1024 * 1024:
            raise HTTPException(413, "Photo must be smaller than 8 MB")
    items = await photo_candidates(bytes(data))
    return {"items": [c.model_dump() for c in items]}


@router.post("/items")
def commit_items(body: ReviewedItems, session: SessionDep):
    added = 0
    for item in body.items:
        canonical = canonical_name(item.name)
        if not canonical:
            raise HTTPException(422, "Enter an ingredient name")
        result = session.execute(
            insert(PantryItem)
            .values(**item.model_dump(), canonical=canonical, source=body.source)
            .on_conflict_do_nothing(index_elements=["canonical"])
        )
        added += result.rowcount
    session.commit()
    # Duplicate submissions cannot increment quantities or create duplicate stock.
    return {"added": added, "already_present": len(body.items) - added}


@router.delete("/items/{item_id}", status_code=204)
def remove_item(item_id: int, session: SessionDep):
    item = session.get(PantryItem, item_id)
    if item is None:
        raise HTTPException(404, "Ingredient not found")
    session.delete(item)
    session.commit()
    return Response(status_code=204)


@router.get("/recipes")
def matching_recipes(session: SessionDep):
    pantry = set(session.scalars(select(PantryItem.canonical)).all())
    if not pantry:
        return {"recipes": []}
    recipes = session.scalars(select(Recipe).options(selectinload(Recipe.ingredients))).all()
    matches = []
    for recipe in recipes:
        if not recipe.ingredients:
            continue
        matched, missing = [], []
        for ingredient in recipe.ingredients:
            # Same deterministic parser on both sides. Never match by substring.
            name = ingredient.item or ingredient.raw_text
            (matched if canonical_name(name) in pantry else missing).append(name)
        if matched:
            matches.append(
                {"id": recipe.id, "title": recipe.title, "matched": matched, "missing": missing}
            )
    matches.sort(key=lambda r: (len(r["missing"]), -len(r["matched"]), r["title"]))
    return {"recipes": matches[:30]}
