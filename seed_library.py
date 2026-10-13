"""Loads library_data.py into the database: muscles, equipment, movement patterns and global exercises.

    python seed_library.py [mongodb-uri] [--existing-only] [--dry-run]

Everything is matched by name (after applying RENAMES), so it is safe to re-run: library items are added or updated, exercises in
EXISTING get their links set, and exercises in NEW are added (or, if one with that name already exists, only
their links are set). --existing-only skips adding NEW exercises; links to them are filled in on a later run.
"""
import sys
from typing import Dict, List

from db_manager import ADDED_GROUP_FIELDS, EQUIPMENT_TYPES, PATTERN_KINDS, TrainerDB, with_groups
from library_data import EQUIPMENT, EXISTING, MOVEMENT_PATTERNS, MUSCLE_GROUPS, NEW, RENAMES

METRIC_CODES = {"R": "Reps", "W": "Weight", "D": "Duration", "C": "Calories", "X": "Resistance", "M": "Distance"}
METRIC_ORDER = ["Reps", "Weight", "Duration", "Calories", "Resistance", "Distance"]


def validate() -> List[str]:
    """Every name an exercise refers to must be defined; returns the problems found."""
    problems = []
    muscles = {name for _, members in MUSCLE_GROUPS.values() for name, _ in members}
    equipment = {name for name, _, _ in EQUIPMENT}
    patterns = {name for name, _, _ in MOVEMENT_PATTERNS}
    exercises = [item["name"] for item in EXISTING + NEW]
    problems += [f"duplicate exercise: {name}" for name in {n for n in exercises if exercises.count(n) > 1}]
    problems += [f"bad equipment type: {name}" for name, kind, _ in EQUIPMENT if kind not in EQUIPMENT_TYPES]
    problems += [f"bad pattern kind: {name}" for name, kind, _ in MOVEMENT_PATTERNS if kind not in PATTERN_KINDS]
    for item in EXISTING + NEW:
        for key, known in (("equipment", equipment), ("patterns", patterns), ("primary", muscles), ("secondary", muscles), ("next", set(exercises))):
            problems += [f"{item['name']}: unknown {key} '{name}'" for name in item[key] if name not in known]
        problems += [f"{item['name']}: no primary muscle" for _ in [0] if not item["primary"]]
        problems += [f"{item['name']}: bad metric code '{code}'" for code in item["metrics"] if code not in METRIC_CODES]
        problems += [f"{item['name']}: muscle both primary and secondary" for _ in [0] if set(item["primary"]) & set(item["secondary"])]
    problems += [f"{item['name']}: new exercise without instructions" for item in NEW if not item["instructions"]]
    # An old name may be reused for a new exercise: a rename is skipped once its target exists.
    problems += [f"rename target not defined: {new}" for new in RENAMES.values() if new not in exercises]
    return problems


def upsert_items(db: TrainerDB, collection: str, rows: List[Dict], dry_run: bool) -> Dict[str, str]:
    """Adds or updates library items by name; returns name -> id."""
    found = {item["name"].lower(): str(item["_id"]) for item in db.get_items(collection)}
    ids, added = {}, 0
    for row in rows:
        item_id = found.get(row["name"].lower())
        if item_id:
            if not dry_run:
                db.update_item(collection, item_id, row)
        else:
            item_id = "dry-run" if dry_run else db.add_item(collection, row)
            added += 1
        ids[row["name"]] = item_id
    print(f"{collection}: {len(rows)} defined, {added} added")
    return ids


def rename_refs(node, names: Dict[str, str]) -> bool:
    """Renames every {exercise_id, name} reference (planned exercises, swaps, swapped_from) in place."""
    changed = False
    if isinstance(node, dict):
        if node.get("exercise_id") in names and node.get("name") != names[node["exercise_id"]]:
            node["name"] = names[node["exercise_id"]]
            changed = True
        for value in node.values():
            changed = rename_refs(value, names) or changed
    elif isinstance(node, list):
        for value in node:
            changed = rename_refs(value, names) or changed
    return changed


def apply_renames(db: TrainerDB, dry_run: bool) -> None:
    """Renames global exercises per RENAMES. Everything links by id; the name copies kept in sessions and
    workout logs are updated too so they show the new name."""
    by_name = {item["name"].lower(): item for item in db.get_visible_exercises([])}
    renamed = {}
    for old, new in RENAMES.items():
        exercise = by_name.get(old.lower())
        if exercise and new.lower() not in by_name:
            renamed[str(exercise["_id"])] = new
            print(f"rename: {old} -> {new}")
            if not dry_run:
                db.update_exercise(str(exercise["_id"]), {"name": new})
    if renamed and not dry_run:
        for collection in ("sessions", "workout_logs"):
            for doc in db.db[collection].find():
                if rename_refs(doc.get("supersets"), renamed):
                    db.db[collection].update_one({"_id": doc["_id"]}, {"$set": {"supersets": doc["supersets"]}})


def seed(db: TrainerDB, existing_only: bool = False, dry_run: bool = False) -> None:
    problems = validate()
    if problems:
        raise SystemExit("Library data has problems:\n  " + "\n  ".join(problems))
    apply_renames(db, dry_run)

    group_ids = upsert_items(db, "muscle_groups", [{"name": name, "description": text} for name, (text, _) in MUSCLE_GROUPS.items()], dry_run)
    muscle_ids = upsert_items(db, "muscles", [{"name": name, "description": text, "group_id": group_ids[group]}
                                              for group, (_, members) in MUSCLE_GROUPS.items() for name, text in members], dry_run)
    equipment_ids = upsert_items(db, "equipment", [{"name": n, "type": t, "description": d} for n, t, d in EQUIPMENT], dry_run)
    pattern_ids = upsert_items(db, "movement_patterns", [{"name": n, "kind": k, "description": d} for n, k, d in MOVEMENT_PATTERNS], dry_run)
    group_of = {muscle_ids[name]: group_ids[group] for group, (_, members) in MUSCLE_GROUPS.items() for name, _ in members}

    globals_by_name = {item["name"].lower(): item for item in db.get_visible_exercises([])}
    missing = [item["name"] for item in EXISTING if item["name"].lower() not in globals_by_name]
    if missing:
        print("Not in the database (skipped):", ", ".join(missing))

    added = 0
    if not existing_only:
        for item in NEW:
            if item["name"].lower() in globals_by_name:
                continue
            doc = {"name": item["name"], "instructions": item["instructions"], "video_url": item["video_url"],
                   "metrics": [m for m in METRIC_ORDER if m in {METRIC_CODES[c] for c in item["metrics"]}]}
            if not dry_run:
                doc["_id"] = db.db.exercises.insert_one(doc).inserted_id
            globals_by_name[item["name"].lower()] = doc
            added += 1
    print(f"exercises: {added} added")

    # Links, once every exercise exists so progressions resolve.
    linked = 0
    for item in EXISTING + ([] if existing_only else NEW):
        exercise = globals_by_name.get(item["name"].lower())
        if not exercise or "_id" not in exercise:
            continue
        fields = {
            "primary_muscle_ids": [muscle_ids[name] for name in item["primary"]],
            "secondary_muscle_ids": [muscle_ids[name] for name in item["secondary"]],
            **{field: exercise.get(field) or [] for field in ADDED_GROUP_FIELDS},
        }
        progressions = [globals_by_name[name.lower()] for name in item["next"] if name.lower() in globals_by_name]
        updates = {
            **with_groups(fields, group_of),
            "equipment_ids": [equipment_ids[name] for name in item["equipment"]],
            "movement_pattern_ids": [pattern_ids[name] for name in item["patterns"]],
            "progression_ids": [str(other["_id"]) for other in progressions if "_id" in other],
        }
        if not dry_run:
            db.update_exercise(str(exercise["_id"]), updates)
        linked += 1
    print(f"exercises: {linked} linked{' (dry run, nothing written)' if dry_run else ''}")


if __name__ == "__main__":
    args = [arg for arg in sys.argv[1:] if not arg.startswith("--")]
    trainer_db = TrainerDB(*args)
    trainer_db.ensure_indexes()
    seed(trainer_db, existing_only="--existing-only" in sys.argv, dry_run="--dry-run" in sys.argv)
