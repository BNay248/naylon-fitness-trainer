import math
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import bcrypt
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from jose import JWTError, jwt
from pydantic import BaseModel

from db_manager import (ADDED_GROUP_FIELDS, EQUIPMENT_TYPES, GROUP_FIELDS, LINK_FIELDS, MUSCLE_FIELDS,
                        PATTERN_KINDS, TrainerDB, unique, with_groups)

app = FastAPI()
db = TrainerDB()
db.ensure_indexes()

ALGORITHM = "HS256"
# Single sign-on with the nutrition tracker: both apps share this cookie, its secret and the users collection.
# COOKIE_DOMAIN (e.g. chowmeinframe.com) scopes it to every subdomain; unset, it stays on the current host (local dev).
COOKIE_NAME = "nfp_session"
LEGACY_COOKIES = ["trainer_session"]
COOKIE_DOMAIN = os.environ.get("COOKIE_DOMAIN") or None
TRACKER_URL = os.environ.get("TRACKER_URL", "")
TEMPLATES_URL = os.environ.get("TEMPLATES_URL", "")
TOKEN_DAYS = 30
ADMINS = {name.strip() for name in os.environ.get("TRAINER_ADMINS", "brad").split(",") if name.strip()}
POSSIBLE_METRICS = ["Reps", "Weight", "Duration", "Calories", "Resistance", "Distance"]
MAX_REPEATS = 20
MAX_NOTE = 500


# Signs login cookies (shared with the tracker), so it must be private: required from the environment, never defaulted.
SECRET = os.environ.get("JWT_SECRET", "")
if len(SECRET) < 32:
    raise RuntimeError("Set JWT_SECRET to a random value of at least 32 characters (e.g. `python3 -c \"import secrets; print(secrets.token_hex(32))\"`)")

app.mount("/static", StaticFiles(directory="static"), name="static")


@app.middleware("http")
async def revalidate_assets(request: Request, call_next):
    # Without this, browsers guess a cache lifetime for pages/JS/CSS and keep running old code after a deploy.
    # "no-cache" still allows caching, but every use is revalidated (a cheap 304 when nothing changed).
    response = await call_next(request)
    if not request.url.path.startswith("/api/"):
        response.headers.setdefault("Cache-Control", "no-cache")
    return response

# ==================== HELPERS ====================


def create_token(username: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=TOKEN_DAYS)
    return jwt.encode({"username": username, "exp": expire}, SECRET, algorithm=ALGORITHM)


def set_session_cookie(response: Response, username: str) -> None:
    response.set_cookie(COOKIE_NAME, create_token(username), httponly=True, max_age=86400 * TOKEN_DAYS, samesite="lax",
                        domain=COOKIE_DOMAIN, secure=bool(COOKIE_DOMAIN))


def current_user(request: Request) -> Dict:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        username = jwt.decode(token, SECRET, algorithms=[ALGORITHM])["username"]
    except (JWTError, KeyError):
        raise HTTPException(status_code=401, detail="Invalid session")
    user = db.get_user_by_username(username)
    if not user:
        raise HTTPException(status_code=401, detail="User no longer exists")
    return user


def coach_user(user: Dict = Depends(current_user)) -> Dict:
    if user.get("role") != "coach":
        raise HTTPException(status_code=403, detail="Coaches only")
    return user


def admin_user(user: Dict = Depends(current_user)) -> Dict:
    if user["username"] not in ADMINS:
        raise HTTPException(status_code=403, detail="Administrator only")
    return user


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def iso(value: Any) -> Optional[str]:
    # Stored datetimes are naive server-local time; attach the server's offset for the browser.
    return value.astimezone().isoformat() if isinstance(value, datetime) else None


def display_names(usernames: List[str]) -> List[Dict]:
    users = db.get_users_by_usernames(usernames)
    return [{"username": name, "name": users.get(name, {}).get("name", name)} for name in usernames]


def to_int(value: Any) -> int:
    try:
        return max(0, int(float(value)))
    except (TypeError, ValueError):
        return 0


def to_amount(value: Any) -> float:
    """A metric value: non-negative, up to 2 decimal places, and a plain int when whole (so 10.0 is stored as 10)."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0
    if not math.isfinite(number) or number <= 0:
        return 0
    number = round(number, 2)
    return int(number) if number.is_integer() else number


def clamp_repeats(value: Any) -> int:
    return min(MAX_REPEATS, max(1, to_int(value) or 1))


def clean_swap(value: Any) -> Optional[Dict]:
    """The exercise done instead of the planned one for a single round of a logged workout."""
    if not isinstance(value, dict) or not value.get("name"):
        return None
    return {"exercise_id": str(value.get("exercise_id") or ""), "name": str(value["name"]),
            "metrics": [str(metric) for metric in value.get("metrics") or []]}


def clean_instances(instances: Any, metrics: List[str], rounds: int, allow_swaps: bool = False) -> List[Dict]:
    """Exactly `rounds` instances, keeping any provided values for the exercise's metrics
    (or, for a swapped round of a logged workout, the substitute's metrics)."""
    instances = instances if isinstance(instances, list) else []
    cleaned = []
    for idx in range(rounds):
        raw = instances[idx] if idx < len(instances) and isinstance(instances[idx], dict) else {}
        values = raw.get("metrics") if isinstance(raw.get("metrics"), dict) else {}
        swap = clean_swap(raw.get("swap")) if allow_swaps else None
        instance = {"metrics": {metric: to_amount(values[metric]) for metric in (swap["metrics"] if swap else metrics) if metric in values}}
        if swap:
            instance["swap"] = swap
        cleaned.append(instance)
    return cleaned


def clean_note(value: Any) -> str:
    return str(value or "").strip()[:MAX_NOTE]


def clean_targets(targets: Any, metrics: List[str]) -> Dict[str, int]:
    targets = targets if isinstance(targets, dict) else {}
    return {metric: to_amount(targets[metric]) for metric in metrics if to_amount(targets.get(metric)) > 0}


def clean_structure(raw_supersets: Any, usernames: List[str], existing: Optional[List[Dict]] = None) -> List[Dict]:
    """Validate a session's superset/exercise structure against the exercises those users can see.

    Exercises already in the session (`existing`) stay allowed, e.g. a client's personal exercise in a shared copy."""
    catalog = {str(item["_id"]): item for item in db.get_visible_exercises(usernames)}
    kept_ids = {exercise.get("exercise_id") for superset in existing or [] for exercise in superset.get("exercises", [])}
    catalog.update({str(item["_id"]): item for item in db.get_exercises_by_ids([i for i in kept_ids if i and i not in catalog])})
    supersets = []
    for raw in raw_supersets if isinstance(raw_supersets, list) else []:
        repeats = clamp_repeats(raw.get("repeats"))
        exercises = []
        for raw_exercise in raw.get("exercises") or []:
            exercise = catalog.get(str(raw_exercise.get("exercise_id") or ""))
            if not exercise:
                continue
            metrics = exercise.get("metrics") or []
            exercises.append({
                "exercise_id": str(exercise["_id"]),
                "name": exercise.get("name", ""),
                "metrics": metrics,
                "note": clean_note(raw_exercise.get("note")),
                "targets": clean_targets(raw_exercise.get("targets"), metrics),
                "instances": clean_instances(raw_exercise.get("instances"), metrics, repeats),
            })
        if exercises:
            supersets.append({"repeats": repeats, "exercises": exercises})
    return supersets


def clean_swapped_from(value: Any) -> Optional[Dict]:
    """Older whole-exercise swaps: the entry is the substitute and this names the session's exercise it replaced.
    (Swaps are now stored per round, see clean_swap; this keeps workouts queued by older clients intact.)"""
    if not isinstance(value, dict) or not value.get("name"):
        return None
    return {"exercise_id": str(value.get("exercise_id") or ""), "name": str(value["name"])}


def clean_snapshot(raw_supersets: Any) -> List[Dict]:
    """Sanitize a logged workout as the athlete saw it (no catalog lookup, so history stays exact)."""
    supersets = []
    for raw in raw_supersets if isinstance(raw_supersets, list) else []:
        repeats = clamp_repeats(raw.get("repeats"))
        exercises = []
        for raw_exercise in raw.get("exercises") or []:
            metrics = [str(metric) for metric in raw_exercise.get("metrics") or []]
            exercise = {
                "exercise_id": str(raw_exercise.get("exercise_id") or ""),
                "name": str(raw_exercise.get("name") or ""),
                "metrics": metrics,
                "note": clean_note(raw_exercise.get("note")),
                "targets": clean_targets(raw_exercise.get("targets"), metrics),
                "instances": clean_instances(raw_exercise.get("instances"), metrics, repeats, allow_swaps=True),
            }
            swapped_from = clean_swapped_from(raw_exercise.get("swapped_from"))
            if swapped_from:
                exercise["swapped_from"] = swapped_from
            exercises.append(exercise)
        supersets.append({"repeats": repeats, "exercises": exercises})
    return supersets


def planned_id(exercise: Dict) -> Optional[str]:
    """The session's exercise this entry stands for: an older whole-exercise swap still counts as the exercise it replaced."""
    return (exercise.get("swapped_from") or {}).get("exercise_id") or exercise.get("exercise_id")


def structure_signature(supersets: List[Dict]) -> List:
    return [(superset.get("repeats"), [planned_id(exercise) for exercise in superset.get("exercises", [])]) for superset in supersets]


def session_athletes(session: Dict) -> List[str]:
    """Everyone using this session document: its owner plus anyone it's shared with (copy-on-write)."""
    return [session.get("user_id"), *[name for name in session.get("assignees") or [] if name != session.get("user_id")]]


def is_shared(session: Dict) -> bool:
    return len(session_athletes(session)) > 1


def reachable_athletes(user: Dict) -> List[str]:
    clients = [name for name in (user.get("clients") or []) if isinstance(name, str) and name] if user.get("role") == "coach" else []
    return [user["username"], *clients]


def can_act_for(user: Dict, athlete: Optional[str]) -> bool:
    return athlete in reachable_athletes(user)


def can_access_session(user: Dict, session: Dict) -> bool:
    return any(can_act_for(user, athlete) for athlete in session_athletes(session))


def get_accessible_session(session_id: str, user: Dict) -> Dict:
    session = db.get_session(session_id)
    if not session or not can_access_session(user, session):
        raise HTTPException(status_code=404, detail="Session not found")
    return session


def session_athlete(session: Dict, user: Dict, requested: Optional[str]) -> str:
    """Which athlete's view of the session a request is about (defaults to the user, else the owner)."""
    athletes = session_athletes(session)
    athlete = requested or (user["username"] if user["username"] in athletes else session.get("user_id"))
    if athlete not in athletes or not can_act_for(user, athlete):
        raise HTTPException(status_code=404, detail="Session not found")
    return athlete


def view_key(session: Dict, athlete: str) -> str:
    # Client-side key for one athlete's view; the owner's view keeps the bare id so existing drafts still match.
    session_id = str(session["_id"])
    return session_id if athlete == session.get("user_id") else f"{session_id}@{athlete}"


def without_values(supersets: List[Dict]) -> List[Dict]:
    return [{**superset, "exercises": [{**exercise, "instances": [{"metrics": {}} for _ in exercise.get("instances", [])]}
                                       for exercise in superset.get("exercises", [])]} for superset in supersets]


def serialize_session(session: Dict, athlete: str, user: Dict, previous_cache: Dict, names: Dict[str, str]) -> Dict:
    """One athlete's view of a session. Shared sessions carry no stored values; each athlete starts from their own previous ones.
    `previous` is keyed by exercise id."""
    previous = {}
    for superset in session.get("supersets", []):
        for exercise in superset.get("exercises", []):
            exercise_id = exercise.get("exercise_id")
            key = (athlete, exercise_id)
            if key not in previous_cache:
                previous_cache[key] = db.get_latest_exercise_log(athlete, exercise_id)
            if previous_cache[key]:
                previous[exercise_id] = {"created_at": iso(previous_cache[key]["created_at"]), "instances": previous_cache[key]["instances"]}
    shared = is_shared(session)
    others = [name for name in session_athletes(session) if name != athlete]
    return {
        "id": str(session["_id"]),
        "key": view_key(session, athlete),
        "name": session.get("name", "Untitled Session"),
        "user_id": athlete,
        "athlete_name": names.get(athlete, athlete),
        "coach_username": session.get("coach_username"),
        "created_at": iso(session.get("created_at")),
        "supersets": without_values(session.get("supersets", [])) if shared else session.get("supersets", []),
        "version": session.get("version", 0),
        "shared_with": [{"username": name, "name": names.get(name, name)} for name in others],
        "can_edit_all": shared and user.get("role") == "coach" and session.get("coach_username") == user["username"],
        "can_delete": can_act_for(user, athlete) or session.get("coach_username") == user["username"],
        "previous": previous,
    }


def serialize_exercise(exercise: Dict) -> Dict:
    return {
        "id": str(exercise["_id"]),
        "name": exercise.get("name", ""),
        "instructions": exercise.get("instructions", ""),
        "video_url": exercise.get("video_url", ""),
        "metrics": exercise.get("metrics") or [],
        "owner": exercise.get("owner"),
        "pending": bool(exercise.get("pending")),
        **{field: exercise.get(field) or [] for field in MUSCLE_FIELDS + ADDED_GROUP_FIELDS + GROUP_FIELDS + LINK_FIELDS},
    }

# ==================== PAGES ====================

PAGES = {"/": "index.html", "/exercises": "exercises.html", "/clients": "clients.html",
         "/coaches": "coaches.html", "/profile": "profile.html", "/admin": "admin.html",
         "/library": "library.html"}

for route, filename in PAGES.items():
    app.add_api_route(route, (lambda filename=filename: FileResponse(f"static/{filename}")), methods=["GET"], include_in_schema=False)


@app.get("/templates", include_in_schema=False)
def templates_moved():
    # Old bookmarks: templates moved to their own app.
    if not TEMPLATES_URL:
        raise HTTPException(status_code=404, detail="Not found")
    return RedirectResponse(TEMPLATES_URL)


@app.get("/sw.js", include_in_schema=False)
def service_worker():
    return FileResponse("static/sw.js", media_type="application/javascript")

# ==================== AUTH ====================


class LoginRequest(BaseModel):
    username: str
    password: str


class RegisterRequest(BaseModel):
    username: str
    name: str
    email: str
    password: str


class PasswordRequest(BaseModel):
    current_password: str
    new_password: str


@app.post("/api/login")
def login(req: LoginRequest, response: Response):
    user = db.get_user_by_username(req.username.strip())
    if not user or not user.get("password") or not bcrypt.checkpw(req.password.encode(), user["password"].encode()):
        raise HTTPException(status_code=401, detail="Username/password is incorrect")
    set_session_cookie(response, user["username"])
    return {"ok": True}


@app.post("/api/register")
def register(req: RegisterRequest, response: Response):
    username, name, email = req.username.strip(), req.name.strip(), req.email.strip()
    if not username or not name or not email or not req.password:
        raise HTTPException(status_code=400, detail="Please fill all fields")
    if db.get_user_by_username(username):
        raise HTTPException(status_code=400, detail="Username already exists")
    if len(req.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")
    db.add_user({"username": username, "name": name, "email": email, "password": hash_password(req.password), "role": "client"})
    set_session_cookie(response, username)
    return {"ok": True}


@app.post("/api/logout")
def logout(response: Response):
    response.delete_cookie(COOKIE_NAME, domain=COOKIE_DOMAIN, secure=bool(COOKIE_DOMAIN), httponly=True, samesite="lax")
    for name in LEGACY_COOKIES:
        response.delete_cookie(name)
    return {"ok": True}


@app.get("/api/me")
def me(user: Dict = Depends(current_user)):
    return {
        "username": user["username"],
        "name": user.get("name", ""),
        "email": user.get("email", ""),
        "role": user.get("role", "client"),
        "is_admin": user["username"] in ADMINS,
        "tracker_url": TRACKER_URL,
        "templates_url": TEMPLATES_URL,
        **training_profile(user),
    }


def training_profile(user: Dict) -> Dict:
    """What suggestions are tailored to: the equipment the client has."""
    return {"equipment_ids": user.get("equipment_ids") or []}


class EquipmentRequest(BaseModel):
    equipment_ids: List[str]


@app.put("/api/me/equipment")
def set_my_equipment(req: EquipmentRequest, user: Dict = Depends(current_user)):
    equipment = ids_in("equipment")
    db.update_user(user["username"], {"equipment_ids": unique(i for i in req.equipment_ids if i in equipment)})
    return {"ok": True}


@app.post("/api/password")
def change_password(req: PasswordRequest, user: Dict = Depends(current_user)):
    if not bcrypt.checkpw(req.current_password.encode(), user["password"].encode()):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    if len(req.new_password) < 6:
        raise HTTPException(status_code=400, detail="New password must be at least 6 characters")
    db.update_user(user["username"], {"password": hash_password(req.new_password)})
    return {"ok": True}

# ==================== EXERCISES ====================


class ExerciseRequest(BaseModel):
    name: str
    instructions: str
    video_url: str = ""
    metrics: List[str] = []
    primary_muscle_ids: List[str] = []
    secondary_muscle_ids: List[str] = []
    added_primary_group_ids: List[str] = []    # groups picked directly, not through one of their muscles
    added_secondary_group_ids: List[str] = []
    equipment_ids: List[str] = []
    movement_pattern_ids: List[str] = []
    progression_ids: List[str] = []           # the next-harder exercises


def ids_in(collection: str) -> set:
    return {str(item["_id"]) for item in db.get_items(collection)}


def muscle_group_lookup() -> Dict[str, str]:
    return {str(muscle["_id"]): muscle.get("group_id") for muscle in db.get_items("muscles")}


def muscle_fields(req: ExerciseRequest) -> Dict:
    group_of = muscle_group_lookup()
    group_ids = ids_in("muscle_groups")
    primary = unique(m for m in req.primary_muscle_ids if m in group_of)
    added_primary = unique(g for g in req.added_primary_group_ids if g in group_ids)
    return with_groups({
        "primary_muscle_ids": primary,
        "secondary_muscle_ids": unique(m for m in req.secondary_muscle_ids if m in group_of and m not in primary),
        "added_primary_group_ids": added_primary,
        "added_secondary_group_ids": unique(g for g in req.added_secondary_group_ids if g in group_ids and g not in added_primary),
    }, group_of)


def link_fields(req: ExerciseRequest, owner: Optional[str], exercise_id: Optional[str]) -> Dict:
    """Equipment, patterns and progressions, keeping only ids that exist. A global exercise can only progress
    to other global exercises; a personal one also to its owner's personal exercises."""
    equipment, patterns = ids_in("equipment"), ids_in("movement_patterns")
    reachable = {str(item["_id"]) for item in db.get_visible_exercises([owner] if owner else [])}
    return {
        "equipment_ids": unique(i for i in req.equipment_ids if i in equipment),
        "movement_pattern_ids": unique(i for i in req.movement_pattern_ids if i in patterns),
        "progression_ids": unique(i for i in req.progression_ids if i in reachable and i != exercise_id),
    }


def refresh_exercise_groups(exercises: List[Dict]) -> None:
    """Re-derives worked groups after a muscle moved group or was removed."""
    group_of = muscle_group_lookup()
    for exercise in exercises:
        fields = {field: exercise.get(field) or [] for field in MUSCLE_FIELDS + ADDED_GROUP_FIELDS}
        db.update_exercise(str(exercise["_id"]), with_groups(fields, group_of))


def exercise_fields(req: ExerciseRequest, owner: Optional[str], exercise_id: Optional[str] = None) -> Dict:
    if not req.name.strip() or not req.instructions.strip():
        raise HTTPException(status_code=400, detail="Please fill in all required fields")
    return {
        "name": req.name.strip(),
        "instructions": req.instructions,
        "video_url": req.video_url.strip(),
        "metrics": [metric for metric in POSSIBLE_METRICS if metric in req.metrics],
        **muscle_fields(req),
        **link_fields(req, owner, exercise_id),
    }


def check_name_free(name: str, exercises: List[Dict], exclude_id: Optional[str] = None) -> None:
    # Everything references exercises by id; unique names just keep the pickers unambiguous.
    if any(str(item["_id"]) != exclude_id and str(item.get("name", "")).lower() == name.lower() for item in exercises):
        raise HTTPException(status_code=409, detail=f"An exercise named \"{name}\" already exists")


def get_editable_exercise(exercise_id: str, user: Dict) -> Dict:
    """Coaches edit global exercises; everyone edits their own personal ones."""
    exercise = db.get_exercise(exercise_id)
    if not exercise or (exercise.get("owner") and exercise["owner"] != user["username"]):
        raise HTTPException(status_code=404, detail="Exercise not found")
    if not exercise.get("owner") and user.get("role") != "coach":
        raise HTTPException(status_code=403, detail="Only coaches can change the global exercise list")
    return exercise


def get_own_exercise(exercise_id: str, user: Dict) -> Dict:
    exercise = db.get_exercise(exercise_id)
    if not exercise or exercise.get("owner") != user["username"]:
        raise HTTPException(status_code=404, detail="Exercise not found")
    return exercise


def get_pending_exercise(exercise_id: str) -> Dict:
    exercise = db.get_exercise(exercise_id)
    if not exercise or not exercise.get("owner") or not exercise.get("pending"):
        raise HTTPException(status_code=404, detail="Request not found")
    return exercise


@app.get("/api/exercises")
def list_exercises(user: Dict = Depends(current_user)):
    # pattern_kinds (e.g. Mobility, Conditioning) let swap suggestions keep stretches and cardio apart from strength work.
    kind_of = {str(pattern["_id"]): pattern.get("kind") for pattern in db.get_items("movement_patterns")}
    return [{**serialize_exercise(exercise), "pattern_kinds": unique(kind_of[i] for i in exercise.get("movement_pattern_ids") or [] if kind_of.get(i))}
            for exercise in db.get_visible_exercises([user["username"]])]


@app.post("/api/exercises")
def create_exercise(req: ExerciseRequest, user: Dict = Depends(current_user)):
    """Coaches add to the global list; everyone else adds a personal exercise only they can see."""
    owner = None if user.get("role") == "coach" else user["username"]
    fields = exercise_fields(req, owner)
    check_name_free(fields["name"], db.get_visible_exercises([user["username"]]))
    if owner:
        fields["owner"] = owner
    return {"id": db.add_exercise(fields)}


@app.put("/api/exercises/{exercise_id}")
def update_exercise(exercise_id: str, req: ExerciseRequest, user: Dict = Depends(current_user)):
    exercise = get_editable_exercise(exercise_id, user)
    fields = exercise_fields(req, exercise.get("owner"), exercise_id)
    others = db.get_visible_exercises([exercise["owner"]] if exercise.get("owner") else [])
    check_name_free(fields["name"], others, exclude_id=exercise_id)
    db.update_exercise(exercise_id, fields)
    return {"ok": True}


@app.delete("/api/exercises/{exercise_id}")
def delete_exercise(exercise_id: str, user: Dict = Depends(current_user)):
    get_editable_exercise(exercise_id, user)
    db.delete_exercise(exercise_id)
    db.pull_from_exercises(["progression_ids"], exercise_id)
    return {"ok": True}


@app.post("/api/exercises/{exercise_id}/request")
def request_global_exercise(exercise_id: str, user: Dict = Depends(current_user)):
    get_own_exercise(exercise_id, user)
    db.update_exercise(exercise_id, {"pending": True})
    return {"ok": True}


@app.delete("/api/exercises/{exercise_id}/request")
def cancel_global_request(exercise_id: str, user: Dict = Depends(current_user)):
    get_own_exercise(exercise_id, user)
    db.update_exercise(exercise_id, {"pending": False})
    return {"ok": True}


@app.get("/api/exercise-requests")
def list_exercise_requests(user: Dict = Depends(coach_user)):
    pending = db.get_pending_exercises()
    names = {item["username"]: item["name"] for item in display_names(list({item["owner"] for item in pending}))}
    return [{**serialize_exercise(item), "owner_name": names.get(item["owner"], item["owner"])} for item in pending]


@app.post("/api/exercise-requests/{exercise_id}/approve")
def approve_exercise_request(exercise_id: str, user: Dict = Depends(coach_user)):
    """Moves the exercise into the global list. Its id is unchanged, so sessions already using it keep working."""
    exercise = get_pending_exercise(exercise_id)
    check_name_free(exercise.get("name", ""), db.get_visible_exercises([]), exclude_id=exercise_id)
    db.make_exercise_global(exercise_id)
    return {"ok": True}


@app.post("/api/exercise-requests/{exercise_id}/decline")
def decline_exercise_request(exercise_id: str, user: Dict = Depends(coach_user)):
    get_pending_exercise(exercise_id)
    db.update_exercise(exercise_id, {"pending": False})
    return {"ok": True}

# ==================== LIBRARY ====================
# Muscle groups, muscles, equipment and movement patterns: named items exercises link to by id.

LIBRARY = {
    "muscle-groups": {"collection": "muscle_groups", "label": "muscle group", "exercise_fields": ADDED_GROUP_FIELDS + GROUP_FIELDS},
    "muscles": {"collection": "muscles", "label": "muscle", "exercise_fields": MUSCLE_FIELDS},
    "equipment": {"collection": "equipment", "label": "equipment", "exercise_fields": ["equipment_ids"], "choice": ("type", EQUIPMENT_TYPES)},
    "movement-patterns": {"collection": "movement_patterns", "label": "movement pattern", "exercise_fields": ["movement_pattern_ids"],
                          "choice": ("kind", PATTERN_KINDS)},
}


class LibraryItemRequest(BaseModel):
    name: str
    description: str = ""
    group_id: str = ""  # muscles
    type: str = ""      # equipment
    kind: str = ""      # movement patterns


def serialize_item(item: Dict) -> Dict:
    extra = {key: item.get(key, "") for key in ("group_id", "type", "kind") if key in item}
    return {"id": str(item["_id"]), "name": item.get("name", ""), "description": item.get("description", ""), **extra}


def library_spec(kind: str) -> Dict:
    if kind not in LIBRARY:
        raise HTTPException(status_code=404, detail="Not found")
    return LIBRARY[kind]


def get_item_or_404(spec: Dict, item_id: str) -> Dict:
    item = db.get_item(spec["collection"], item_id)
    if not item:
        raise HTTPException(status_code=404, detail=f"{spec['label'].capitalize()} not found")
    return item


def library_fields(kind: str, req: LibraryItemRequest, exclude_id: Optional[str] = None) -> Dict:
    spec = library_spec(kind)
    name = req.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Please enter a name")
    if any(str(item["_id"]) != exclude_id and str(item.get("name", "")).lower() == name.lower() for item in db.get_items(spec["collection"])):
        raise HTTPException(status_code=409, detail=f"{spec['label'].capitalize()} \"{name}\" already exists")
    fields = {"name": name, "description": req.description.strip()}
    if kind == "muscles":
        if not db.get_item("muscle_groups", req.group_id):
            raise HTTPException(status_code=400, detail="Please choose a muscle group")
        fields["group_id"] = req.group_id
    if "choice" in spec:
        key, options = spec["choice"]
        value = getattr(req, key)
        if value not in options:
            raise HTTPException(status_code=400, detail=f"Please choose a {key}")
        fields[key] = value
    return fields


@app.get("/api/library")
def get_library(user: Dict = Depends(current_user)):
    return {
        **{spec["collection"]: [serialize_item(item) for item in db.get_items(spec["collection"])] for spec in LIBRARY.values()},
        "equipment_types": EQUIPMENT_TYPES,
        "pattern_kinds": PATTERN_KINDS,
    }


@app.post("/api/library/{kind}")
def create_library_item(kind: str, req: LibraryItemRequest, user: Dict = Depends(coach_user)):
    return {"id": db.add_item(library_spec(kind)["collection"], library_fields(kind, req))}


@app.put("/api/library/{kind}/{item_id}")
def update_library_item(kind: str, item_id: str, req: LibraryItemRequest, user: Dict = Depends(coach_user)):
    spec = library_spec(kind)
    item = get_item_or_404(spec, item_id)
    fields = library_fields(kind, req, item_id)
    db.update_item(spec["collection"], item_id, fields)
    if kind == "muscles" and fields["group_id"] != item.get("group_id"):
        refresh_exercise_groups(db.get_exercises_using(MUSCLE_FIELDS, item_id))
    return {"ok": True}


@app.delete("/api/library/{kind}/{item_id}")
def delete_library_item(kind: str, item_id: str, user: Dict = Depends(coach_user)):
    """Also removes the item from every exercise that links to it."""
    spec = library_spec(kind)
    get_item_or_404(spec, item_id)
    if kind == "muscle-groups":
        count = db.count_items("muscles", {"group_id": item_id})
        if count:
            raise HTTPException(status_code=409, detail=f"Move or delete the {count} muscle{'s' if count != 1 else ''} in this group first")
    affected = [str(exercise["_id"]) for exercise in db.get_exercises_using(spec["exercise_fields"], item_id)]
    db.delete_item(spec["collection"], item_id)
    db.pull_from_exercises(spec["exercise_fields"], item_id)
    if kind == "muscles":
        refresh_exercise_groups(db.get_exercises_by_ids(affected))
    return {"ok": True}

# ==================== TEMPLATES ====================
# Templates live in their own app now (TEMPLATES_URL, d:\projects	emplates). This only records template workouts
# that were queued offline in this app before the move, so they aren't lost; it can go once those have synced.


class TemplateLogRequest(BaseModel):
    supersets: List[Dict]
    client_id: Optional[str] = None
    logged_at: Optional[str] = None
    user_id: Optional[str] = None


@app.post("/api/templates/{template_id}/log")
def log_template_workout(template_id: str, req: TemplateLogRequest, user: Dict = Depends(current_user)):
    snapshot = clean_snapshot(req.supersets)
    if not any(superset["exercises"] for superset in snapshot):
        raise HTTPException(status_code=400, detail="Nothing to log")
    athlete = req.user_id or user["username"]
    if not can_act_for(user, athlete):
        raise HTTPException(status_code=404, detail="Athlete not found")
    template = db.get_template(template_id)
    prs = personal_records(athlete, snapshot)
    extra = {"template_id": template_id, "template_version": (template or {}).get("version")}
    log_id = db.add_workout_log({"_id": template_id, "name": (template or {}).get("name") or "Deleted template", "user_id": athlete},
                                snapshot, user["username"], req.client_id, parse_logged_at(req.logged_at), extra)
    return {"id": log_id, "prs": prs, "template_deleted": template is None}

# ==================== SESSIONS ====================


class SessionRequest(BaseModel):
    name: str
    supersets: List[Dict]
    assigned_to: Optional[str] = None
    client_id: Optional[str] = None
    base_version: Optional[int] = None
    athlete: Optional[str] = None  # which athlete's view is being edited
    scope: str = "athlete"         # "all" edits a shared session for everyone; otherwise a shared session is copied


class AssignRequest(BaseModel):
    usernames: List[str]


class LogRequest(BaseModel):
    supersets: List[Dict]
    client_id: Optional[str] = None
    logged_at: Optional[str] = None
    session_name: Optional[str] = None
    user_id: Optional[str] = None


@app.get("/api/sessions")
def list_sessions(user: Dict = Depends(current_user)):
    """Each session is listed once per athlete using it that this user can see (a shared session can appear several times)."""
    cache: Dict = {}
    reachable = reachable_athletes(user)
    clients = reachable[1:]
    sessions = db.get_sessions_for_users(reachable)
    names = {item["username"]: item["name"] for item in display_names(sorted({a for s in sessions for a in session_athletes(s) if a}))}
    by_owner: Dict[str, List[Dict]] = {}
    for session in sessions:
        for athlete in session_athletes(session):
            if athlete in reachable:
                by_owner.setdefault(athlete, []).append(serialize_session(session, athlete, user, cache, names))
    return {
        "mine": by_owner.get(user["username"], []),
        "clients": [{**client, "sessions": by_owner.get(client["username"], [])} for client in display_names(clients)],
    }


def validated_structure(req: SessionRequest, usernames: List[str], existing: Optional[List[Dict]] = None) -> Dict:
    name = req.name.strip()
    supersets = clean_structure(req.supersets, usernames, existing)
    if not name:
        raise HTTPException(status_code=400, detail="Please enter a session name")
    if not supersets:
        raise HTTPException(status_code=400, detail="Please add at least one exercise")
    return {"name": name, "supersets": supersets}


def check_coach_precedence(session: Dict, user: Dict, base_version: Optional[int]) -> None:
    """Offline edits carry the version they started from. An athlete's stale edit loses to any coach edit made since."""
    if base_version is None or user["username"] not in session_athletes(session) or user["username"] == session.get("coach_username"):
        return
    if base_version < session.get("coach_edit_version", 0):
        raise HTTPException(status_code=409, detail=f"Your coach changed \"{session.get('name')}\" while you were offline, so your change was discarded.")


@app.post("/api/sessions")
def create_session(req: SessionRequest, user: Dict = Depends(current_user)):
    if req.client_id:
        existing = db.get_session_by_client_id(req.client_id)
        if existing:
            return {"id": str(existing["_id"])}
    # The athlete's personal exercises are usable too, so a coach can build with them.
    document = {**validated_structure(req, [user["username"], req.assigned_to or user["username"]]), "user_id": user["username"], "coach_username": user["username"],
                "version": 0, "updated_by": user["username"], "client_id": req.client_id}
    if req.assigned_to:
        if user.get("role") != "coach" or req.assigned_to not in (user.get("clients") or []):
            raise HTTPException(status_code=400, detail="You can only assign sessions to your clients")
        document["user_id"] = document["assigned_to"] = req.assigned_to
        document["coach_edit_version"] = 0
    return {"id": db.add_session(document)}


def detach_athlete(session: Dict, athlete: str) -> None:
    """Take one athlete off a shared session; if they owned it, the next athlete becomes the owner."""
    athletes = [name for name in session_athletes(session) if name != athlete]
    db.update_session(str(session["_id"]), {"user_id": athletes[0], "assignees": athletes[1:]})


@app.put("/api/sessions/{session_id}")
def update_session(session_id: str, req: SessionRequest, user: Dict = Depends(current_user)):
    """Edits a session. A shared session is copied for the one athlete being edited (copy-on-write),
    unless the coach who created it edits it for everyone (scope "all")."""
    session = get_accessible_session(session_id, user)
    athlete = session_athlete(session, user, req.athlete)
    structure = validated_structure(req, [user["username"], *session_athletes(session)], session.get("supersets"))
    edit_all = req.scope == "all" and user.get("role") == "coach" and session.get("coach_username") == user["username"]
    check_coach_precedence(session, user, req.base_version)
    if is_shared(session) and not edit_all:
        variant = {**{k: v for k, v in session.items() if k not in ("_id", "client_id", "created_at")}, **structure,
                   "user_id": athlete, "assignees": [], "version": 0, "updated_by": user["username"], "coach_edit_version": 0}
        new_id = db.add_session(variant)
        detach_athlete(session, athlete)
        db.move_workout_logs(session_id, new_id, athlete)  # their history follows them to their own copy
        return {"ok": True, "version": 0, "id": new_id}
    version = session.get("version", 0) + 1
    updates = {**structure, "version": version, "updated_by": user["username"]}
    if edit_all or user["username"] not in session_athletes(session):
        updates["coach_edit_version"] = version
    db.update_session(session_id, updates)
    return {"ok": True, "version": version, "id": session_id}


@app.post("/api/sessions/{session_id}/assign")
def assign_session(session_id: str, req: AssignRequest, user: Dict = Depends(coach_user)):
    """Shares the session with more clients. They all use this one copy until someone's version is edited."""
    session = get_accessible_session(session_id, user)
    clients = user.get("clients") or []
    invalid = [name for name in req.usernames if name not in clients]
    if invalid:
        raise HTTPException(status_code=400, detail=f"Not your client: {', '.join(invalid)}")
    db.update_session(session_id, {"assignees": [name for name in dict.fromkeys([*session_athletes(session)[1:], *req.usernames]) if name != session.get("user_id")]})
    return {"ok": True}


@app.delete("/api/sessions/{session_id}")
def delete_session(session_id: str, base_version: Optional[int] = None, athlete: Optional[str] = None, user: Dict = Depends(current_user)):
    """Deletes the session, or for a shared session, removes it for that one athlete only."""
    session = get_accessible_session(session_id, user)
    athlete = session_athlete(session, user, athlete)
    if is_shared(session):
        detach_athlete(session, athlete)
        return {"ok": True}
    check_coach_precedence(session, user, base_version)
    db.delete_session(session_id)
    return {"ok": True}


def parse_logged_at(value: Optional[str]) -> datetime:
    now = datetime.now()
    try:
        logged_at = datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone().replace(tzinfo=None) if value else now
    except ValueError:
        return now
    return min(logged_at, now)


# The first of these an exercise logs decides what counts as a PR for it.
PR_METRICS = ["Weight", "Reps", "Distance", "Duration"]


def rounds_by_exercise(supersets: List[Dict]) -> Dict[str, Dict]:
    """Logged rounds grouped by the exercise actually done (a swapped round counts as its substitute)."""
    found: Dict[str, Dict] = {}
    for superset in supersets:
        for exercise in superset.get("exercises", []):
            for instance in exercise.get("instances", []):
                done = instance.get("swap") or exercise
                if done.get("exercise_id"):
                    entry = found.setdefault(done["exercise_id"], {"name": done.get("name", ""), "rounds": []})
                    entry["rounds"].append(instance.get("metrics") or {})
    return found


def best_round(rounds: List[Dict], metric: str) -> Optional[tuple]:
    """(top value, most reps at that value) across rounds, or None if the metric was never logged."""
    values = [(round_.get(metric) or 0, round_.get("Reps") or 0) for round_ in rounds if (round_.get(metric) or 0) > 0]
    return max(values) if values else None


def personal_records(athlete: str, supersets: List[Dict]) -> List[Dict]:
    """Exercises in a workout (not yet saved) that beat the athlete's previous best.

    Heavier weight is a PR, as is more reps at the same top weight; otherwise more reps, distance or duration.
    An exercise's first log is never a PR. On assisted machines more weight means more help, so reps decide."""
    current = rounds_by_exercise(supersets)
    history: Dict[str, List[Dict]] = {}
    for log in db.get_logs_with_exercises(athlete, list(current)):
        for exercise_id, entry in rounds_by_exercise(log.get("supersets", [])).items():
            history.setdefault(exercise_id, []).extend(entry["rounds"])
    records = []
    for exercise_id, entry in current.items():
        past = history.get(exercise_id)
        if not past:
            continue
        for metric in PR_METRICS:
            if metric == "Weight" and "assisted" in entry["name"].lower():
                continue
            now = best_round(entry["rounds"], metric)
            if not now:
                continue
            before = best_round(past, metric)
            if before and now > before:
                records.append({"exercise_id": exercise_id, "name": entry["name"], "metric": metric,
                                "value": now[0], "reps": now[1], "previous": before[0], "previous_reps": before[1]})
            break
    return records


@app.post("/api/sessions/{session_id}/log")
def log_workout(session_id: str, req: LogRequest, user: Dict = Depends(current_user)):
    """Record a workout. The session keeps the latest values only if its structure still matches.

    A workout synced after its session was deleted is still recorded, so offline work is never lost."""
    snapshot = clean_snapshot(req.supersets)
    if not any(superset["exercises"] for superset in snapshot):
        raise HTTPException(status_code=400, detail="Nothing to log")
    session = db.get_session(session_id)
    athlete = req.user_id or user["username"]
    if not can_act_for(user, athlete):
        raise HTTPException(status_code=404, detail="Session not found")
    prs = personal_records(athlete, snapshot)  # before saving, so this workout isn't compared with itself
    if session is None or athlete not in session_athletes(session):
        # Deleted, or no longer this athlete's (removed or copied while offline): keep the workout anyway.
        orphan = {"_id": session_id, "name": req.session_name or (session or {}).get("name") or "Deleted session", "user_id": athlete}
        log_id = db.add_workout_log(orphan, snapshot, user["username"], req.client_id, parse_logged_at(req.logged_at))
        return {"id": log_id, "session_updated": False, "session_deleted": True, "prs": prs}
    structure_matches = structure_signature(snapshot) == structure_signature(session.get("supersets", []))
    # A shared session holds no one's values; each athlete's start values come from their own logs.
    session_updated = structure_matches and not is_shared(session)
    if session_updated:
        db.update_session(session_id, {"supersets": with_instances(session.get("supersets", []), snapshot)})
    log_id = db.add_workout_log({**session, "user_id": athlete}, snapshot, user["username"], req.client_id, parse_logged_at(req.logged_at))
    return {"id": log_id, "session_updated": structure_matches, "session_deleted": False, "prs": prs}


def with_instances(supersets: List[Dict], snapshot: List[Dict]) -> List[Dict]:
    """The session's structure (notes, targets, …) with the logged values from a matching snapshot.

    A swapped round keeps its old values: the substitute's numbers don't belong to the planned exercise."""
    return [{**superset, "exercises": [{**exercise, "instances": merged_instances(exercise.get("instances", []), logged)}
                                       for exercise, logged in zip(superset.get("exercises", []), logged_superset["exercises"])]}
            for superset, logged_superset in zip(supersets, snapshot)]


def merged_instances(saved: List[Dict], logged: Dict) -> List[Dict]:
    if logged.get("swapped_from"):
        return saved
    return [(saved[idx] if idx < len(saved) else {"metrics": {}}) if instance.get("swap") else instance
            for idx, instance in enumerate(logged["instances"])]


@app.get("/api/previous")
def previous_exercise_values(exercise_id: str, athlete: Optional[str] = None, user: Dict = Depends(current_user)):
    """An athlete's most recent logged values for one exercise (used to prefill a one-off swap)."""
    athlete = athlete or user["username"]
    if not can_act_for(user, athlete):
        raise HTTPException(status_code=404, detail="Athlete not found")
    latest = db.get_latest_exercise_log(athlete, exercise_id)
    return {"created_at": iso(latest["created_at"]), "instances": latest["instances"]} if latest else None


@app.get("/api/sessions/{session_id}/history")
def session_history(session_id: str, athlete: Optional[str] = None, user: Dict = Depends(current_user)):
    athlete = session_athlete(get_accessible_session(session_id, user), user, athlete)
    return [{
        "id": str(log["_id"]),
        "created_at": iso(log.get("created_at")),
        "logged_by": log.get("logged_by"),
        "user_id": log.get("user_id"),
        "supersets": log.get("supersets", []),
    } for log in db.get_workout_logs_by_session(session_id, athlete)]

# ==================== CLIENTS (coach side) ====================


@app.get("/api/clients")
def list_clients(user: Dict = Depends(coach_user)):
    clients = user.get("clients") or []
    pending = user.get("pending_client_requests") or []
    excluded = {user["username"], *clients, *pending}
    candidates = [{"username": other["username"], "name": other.get("name", "")}
                  for other in db.get_all_users() if other.get("username") and other["username"] not in excluded]
    profiles = db.get_users_by_usernames(clients)
    return {
        "clients": [{**row, **training_profile(profiles.get(row["username"], {}))} for row in display_names(clients)],
        "pending": display_names(pending),
        "candidates": sorted(candidates, key=lambda item: item["name"].lower() or item["username"].lower()),
    }


class ClientProfileRequest(BaseModel):
    equipment_ids: List[str]


@app.put("/api/clients/{username}/profile")
def set_client_profile(username: str, req: ClientProfileRequest, user: Dict = Depends(coach_user)):
    """A coach sets one of their clients' equipment."""
    if username not in (user.get("clients") or []):
        raise HTTPException(status_code=404, detail="Client not found")
    equipment = ids_in("equipment")
    db.update_user(username, {"equipment_ids": unique(i for i in req.equipment_ids if i in equipment)})
    return {"ok": True}


@app.post("/api/clients/{username}/request")
def request_client(username: str, user: Dict = Depends(coach_user)):
    if username == user["username"] or not db.get_user_by_username(username):
        raise HTTPException(status_code=404, detail="User not found")
    db.request_client(user["username"], username)
    return {"ok": True}


@app.delete("/api/clients/{username}/request")
def cancel_client_request(username: str, user: Dict = Depends(coach_user)):
    db.cancel_client_request(user["username"], username)
    return {"ok": True}


@app.delete("/api/clients/{username}")
def remove_client(username: str, user: Dict = Depends(coach_user)):
    db.remove_relationship(user["username"], username)
    return {"ok": True}

# ==================== COACHES (client side) ====================


@app.get("/api/coaches")
def list_coaches(user: Dict = Depends(current_user)):
    return {
        "coaches": display_names(user.get("coaches") or []),
        "requests": display_names(user.get("pending_coach_requests") or []),
    }


@app.post("/api/coaches/{username}/accept")
def accept_coach(username: str, user: Dict = Depends(current_user)):
    if username not in (user.get("pending_coach_requests") or []):
        raise HTTPException(status_code=404, detail="Request not found")
    db.accept_coach_request(username, user["username"])
    return {"ok": True}


@app.post("/api/coaches/{username}/decline")
def decline_coach(username: str, user: Dict = Depends(current_user)):
    db.cancel_client_request(username, user["username"])
    return {"ok": True}


@app.delete("/api/coaches/{username}")
def remove_coach(username: str, user: Dict = Depends(current_user)):
    db.remove_relationship(username, user["username"])
    return {"ok": True}

# ==================== ADMIN ====================


class AdminUserRequest(BaseModel):
    username: str
    name: str
    email: str
    password: str
    coach: bool = False


def legacy_profile(user: Dict, role: str) -> Dict:
    return {"username": user["username"], "name": user.get("name", user["username"]), "email": user.get("email", ""), "role": role}


@app.get("/api/admin/users")
def admin_list_users(user: Dict = Depends(admin_user)):
    return [{"username": other["username"], "name": other.get("name", ""), "email": other.get("email", ""), "role": other.get("role", "client")}
            for other in db.get_all_users() if other.get("username")]


@app.post("/api/admin/users")
def admin_create_user(req: AdminUserRequest, user: Dict = Depends(admin_user)):
    username = req.username.strip()
    if not username or not req.name.strip() or not req.email.strip() or not req.password:
        raise HTTPException(status_code=400, detail="Please fill all fields")
    if db.get_user_by_username(username):
        raise HTTPException(status_code=400, detail="Username already exists")
    role = "coach" if req.coach else "client"
    new_user = {"username": username, "name": req.name.strip(), "email": req.email.strip(), "password": hash_password(req.password), "role": role}
    db.add_user(dict(new_user))
    (db.add_coach if req.coach else db.add_client)(legacy_profile(new_user, role))
    return {"ok": True, "role": role}


@app.post("/api/admin/users/{username}/toggle-coach")
def admin_toggle_coach(username: str, user: Dict = Depends(admin_user)):
    target = db.get_user_by_username(username)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    new_role = "client" if target.get("role") == "coach" else "coach"
    db.update_user(username, {"role": new_role})
    if new_role == "coach":
        db.add_coach(legacy_profile(target, new_role))
    else:
        db.db.coaches.delete_many({"username": username})
    return {"ok": True, "role": new_role}


@app.delete("/api/admin/users/{username}")
def admin_delete_user(username: str, user: Dict = Depends(admin_user)):
    if username == user["username"]:
        raise HTTPException(status_code=400, detail="You can't delete your own account")
    if not db.delete_user(username):
        raise HTTPException(status_code=404, detail="User not found")
    return {"ok": True}
