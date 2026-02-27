from __future__ import annotations

from typing import Iterable

from werkzeug.security import generate_password_hash

from firestore_db import get_firestore_client
from models import User


def _delete_collection(collection_path: str, batch_size: int = 200) -> int:
    db = get_firestore_client()
    col_ref = db.collection(collection_path)

    deleted = 0
    while True:
        docs = list(col_ref.limit(batch_size).stream())
        if not docs:
            break

        batch = db.batch()
        for d in docs:
            batch.delete(d.reference)
        batch.commit()
        deleted += len(docs)

    return deleted


def _delete_collections(collections: Iterable[str]) -> None:
    total = 0
    for name in collections:
        n = _delete_collection(name)
        total += n
        print(f"Deleted {n} docs from {name}")
    print(f"Deleted {total} docs total")


def clean_and_seed() -> None:
    collections = [
        "tqf5",
        "tqf3",
        "feedback",
        "sections",
        "courses",
        "term_programs",
        "terms",
        "programs",
        "faculties",
        "curriculum_uploads",
        "users",
    ]
    print("Cleaning Firestore collections...")
    _delete_collections(collections)

    print("Seeding initial users...")
    defaults = [
        {
            "id": "admin",
            "username": "admin",
            "password": "password",
            "full_name": "System Administrator",
            "roles": ["admin"],
        },
        {
            "id": "academic",
            "username": "academic",
            "password": "password",
            "full_name": "Academic Officer",
            "roles": ["academic"],
        },
    ]

    created = 0
    for d in defaults:
        if User.get_by_username(d["username"]):
            continue
        u = User(
            id=d["id"],
            username=d["username"],
            password_hash=generate_password_hash(d["password"]),
            full_name=d["full_name"],
            roles=d["roles"],
        )
        u.save()
        created += 1

    print(f"Initial users created: {created} created")


if __name__ == "__main__":
    clean_and_seed()
