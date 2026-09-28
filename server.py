import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import bcrypt
import yaml
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from jose import JWTError, jwt
from pydantic import BaseModel

from db_manager import TrainerDB

app = FastAPI()
db = TrainerDB()
db.ensure_indexes()

ALGORITHM = "HS256"
COOKIE_NAME = "trainer_session"
TOKEN_DAYS = 30
ADMINS = {name.strip() for name in os.environ.get("TRAINER_ADMINS", "brad").split(",") if name.strip()}
POSSIBLE_METRICS = ["Reps", "Weight", "Duration", "Calories", "Resistance", "Distance"]
MAX_REPEATS = 20


def load_secret() -> str:
    """JWT secret: env var, else the cookie key from the Streamlit config.yaml, else a generated file."""
    if os.environ.get("JWT_SECRET"):
        return os.environ["JWT_SECRET"]
    if os.path.exists("config.yaml"):
        with open("config.yaml") as file:
            key = ((yaml.safe_load(file) or {}).get("cookie") or {}).get("key")
        if key:
            return key
    if not os.path.exists(".jwt_secret"):
        with open(".jwt_secret", "w") as file:
            file.write(secrets.token_hex(32))
    with open(".jwt_secret") as file:
        return file.read().strip()


SECRET = load_secret()

app.mount("/static", StaticFiles(directory="static"), name="static")

# ==================== HELPERS ====================


def create_token(username: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=TOKEN_DAYS)
    return jwt.encode({"username": username, "exp": expire}, SECRET, algorithm=ALGORITHM)


def set_session_cookie(response: Response, username: str) -> None:
    response.set_cookie(COOKIE_NAME, create_token(username), httponly=True, max_age=86400 * TOKEN_DAYS, samesite="lax")


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


def clamp_repeats(value: Any) -> int:
    return min(MAX_REPEATS, max(1, to_int(value) or 1))


def clean_instances(instances: Any, metrics: List[str], rounds: int) -> List[Dict]:
    """Exactly `rounds` instances, keeping any provided values for the exercise's metrics."""
    instances = instances if isinstance(instances, list) else []
    cleaned = []
    for idx in range(rounds):
        values = instances[idx].get("metrics", {}) if idx < len(instances) and isinstance(instances[idx], dict) else {}
        cleaned.append({"metrics": {metric: to_int(values[metric]) for metric in metrics if metric in values}})
    return cleaned


def clean_structure(raw_supersets: Any) -> List[Dict]:
    """Validate a session's superset/exercise structure against the exercise catalog."""
    catalog = {str(item["_id"]): item for item in db.get_all_exercises()}
    by_name = {item.get("name"): item for item in catalog.values()}
    supersets = []
    for raw in raw_supersets if isinstance(raw_supersets, list) else []:
        repeats = clamp_repeats(raw.get("repeats"))
        exercises = []
        for raw_exercise in raw.get("exercises") or []:
            exercise = catalog.get(str(raw_exercise.get("exercise_id") or "")) or by_name.get(raw_exercise.get("name"))
            if not exercise:
                continue
            metrics = exercise.get("metrics") or []
            exercises.append({
                "exercise_id": str(exercise["_id"]),
                "name": exercise.get("name", ""),
                "metrics": metrics,
                "instances": clean_instances(raw_exercise.get("instances"), metrics, repeats),
            })
        if exercises:
            supersets.append({"repeats": repeats, "exercises": exercises})
    return supersets


def clean_snapshot(raw_supersets: Any) -> List[Dict]:
    """Sanitize a logged workout as the athlete saw it (no catalog lookup, so history stays exact)."""
    supersets = []
    for raw in raw_supersets if isinstance(raw_supersets, list) else []:
        repeats = clamp_repeats(raw.get("repeats"))
        exercises = []
        for raw_exercise in raw.get("exercises") or []:
            metrics = [str(metric) for metric in raw_exercise.get("metrics") or []]
            exercises.append({
                "exercise_id": str(raw_exercise.get("exercise_id") or ""),
                "name": str(raw_exercise.get("name") or ""),
                "metrics": metrics,
                "instances": clean_instances(raw_exercise.get("instances"), metrics, repeats),
            })
        supersets.append({"repeats": repeats, "exercises": exercises})
    return supersets


def structure_signature(supersets: List[Dict]) -> List:
    return [(superset.get("repeats"), [exercise.get("name") for exercise in superset.get("exercises", [])]) for superset in supersets]


def can_access_session(user: Dict, session: Dict) -> bool:
    owner = session.get("user_id")
    return owner == user["username"] or (user.get("role") == "coach" and owner in (user.get("clients") or []))


def get_accessible_session(session_id: str, user: Dict) -> Dict:
    session = db.get_session(session_id)
    if not session or not can_access_session(user, session):
        raise HTTPException(status_code=404, detail="Session not found")
    return session


def serialize_session(session: Dict, user: Dict, previous_cache: Dict) -> Dict:
    owner = session.get("user_id")
    previous = {}
    for superset in session.get("supersets", []):
        for exercise in superset.get("exercises", []):
            name = exercise.get("name")
            key = (owner, name)
            if key not in previous_cache:
                previous_cache[key] = db.get_latest_exercise_log(owner, name)
            if previous_cache[key]:
                previous[name] = {"created_at": iso(previous_cache[key]["created_at"]), "instances": previous_cache[key]["instances"]}
    return {
        "id": str(session["_id"]),
        "name": session.get("name", "Untitled Session"),
        "user_id": owner,
        "coach_username": session.get("coach_username"),
        "created_at": iso(session.get("created_at")),
        "supersets": session.get("supersets", []),
        "version": session.get("version", 0),
        "can_delete": owner == user["username"] or session.get("coach_username") == user["username"],
        "previous": previous,
    }


def serialize_exercise(exercise: Dict) -> Dict:
    return {
        "id": str(exercise["_id"]),
        "name": exercise.get("name", ""),
        "instructions": exercise.get("instructions", ""),
        "video_url": exercise.get("video_url", ""),
        "metrics": exercise.get("metrics") or [],
    }

# ==================== PAGES ====================

PAGES = {"/": "index.html", "/exercises": "exercises.html", "/clients": "clients.html",
         "/coaches": "coaches.html", "/profile": "profile.html", "/admin": "admin.html"}

for route, filename in PAGES.items():
    app.add_api_route(route, (lambda filename=filename: FileResponse(f"static/{filename}")), methods=["GET"], include_in_schema=False)


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
    response.delete_cookie(COOKIE_NAME)
    return {"ok": True}


@app.get("/api/me")
def me(user: Dict = Depends(current_user)):
    return {
        "username": user["username"],
        "name": user.get("name", ""),
        "email": user.get("email", ""),
        "role": user.get("role", "client"),
        "is_admin": user["username"] in ADMINS,
    }


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


def exercise_fields(req: ExerciseRequest) -> Dict:
    if not req.name.strip() or not req.instructions.strip():
        raise HTTPException(status_code=400, detail="Please fill in all required fields")
    return {
        "name": req.name.strip(),
        "instructions": req.instructions,
        "video_url": req.video_url.strip(),
        "metrics": [metric for metric in POSSIBLE_METRICS if metric in req.metrics],
    }


@app.get("/api/exercises")
def list_exercises(user: Dict = Depends(current_user)):
    return [serialize_exercise(exercise) for exercise in db.get_all_exercises()]


@app.post("/api/exercises")
def create_exercise(req: ExerciseRequest, user: Dict = Depends(coach_user)):
    return {"id": db.add_exercise(exercise_fields(req))}


@app.put("/api/exercises/{exercise_id}")
def update_exercise(exercise_id: str, req: ExerciseRequest, user: Dict = Depends(coach_user)):
    if not db.update_exercise(exercise_id, exercise_fields(req)):
        raise HTTPException(status_code=404, detail="Exercise not found")
    return {"ok": True}


@app.delete("/api/exercises/{exercise_id}")
def delete_exercise(exercise_id: str, user: Dict = Depends(coach_user)):
    if not db.delete_exercise(exercise_id):
        raise HTTPException(status_code=404, detail="Exercise not found")
    return {"ok": True}

# ==================== SESSIONS ====================


class SessionRequest(BaseModel):
    name: str
    supersets: List[Dict]
    assigned_to: Optional[str] = None
    client_id: Optional[str] = None
    base_version: Optional[int] = None


class LogRequest(BaseModel):
    supersets: List[Dict]
    client_id: Optional[str] = None
    logged_at: Optional[str] = None
    session_name: Optional[str] = None
    user_id: Optional[str] = None


@app.get("/api/sessions")
def list_sessions(user: Dict = Depends(current_user)):
    cache: Dict = {}
    clients = [name for name in (user.get("clients") or []) if isinstance(name, str) and name] if user.get("role") == "coach" else []
    sessions = db.get_sessions_for_users([user["username"], *clients])
    by_owner: Dict[str, List[Dict]] = {}
    for session in sessions:
        by_owner.setdefault(session.get("user_id"), []).append(serialize_session(session, user, cache))
    return {
        "mine": by_owner.get(user["username"], []),
        "clients": [{**client, "sessions": by_owner.get(client["username"], [])} for client in display_names(clients)],
    }


def validated_structure(req: SessionRequest) -> Dict:
    name = req.name.strip()
    supersets = clean_structure(req.supersets)
    if not name:
        raise HTTPException(status_code=400, detail="Please enter a session name")
    if not supersets:
        raise HTTPException(status_code=400, detail="Please add at least one exercise")
    return {"name": name, "supersets": supersets}


def check_coach_precedence(session: Dict, user: Dict, base_version: Optional[int]) -> None:
    """Offline edits carry the version they started from. An athlete's stale edit loses to any coach edit made since."""
    if base_version is None or user["username"] != session.get("user_id"):
        return
    if base_version < session.get("coach_edit_version", 0):
        raise HTTPException(status_code=409, detail=f"Your coach changed \"{session.get('name')}\" while you were offline, so your change was discarded.")


@app.post("/api/sessions")
def create_session(req: SessionRequest, user: Dict = Depends(current_user)):
    if req.client_id:
        existing = db.get_session_by_client_id(req.client_id)
        if existing:
            return {"id": str(existing["_id"])}
    document = {**validated_structure(req), "user_id": user["username"], "coach_username": user["username"],
                "version": 0, "updated_by": user["username"], "client_id": req.client_id}
    if req.assigned_to:
        if user.get("role") != "coach" or req.assigned_to not in (user.get("clients") or []):
            raise HTTPException(status_code=400, detail="You can only assign sessions to your clients")
        document["user_id"] = document["assigned_to"] = req.assigned_to
        document["coach_edit_version"] = 0
    return {"id": db.add_session(document)}


@app.put("/api/sessions/{session_id}")
def update_session(session_id: str, req: SessionRequest, user: Dict = Depends(current_user)):
    session = get_accessible_session(session_id, user)
    check_coach_precedence(session, user, req.base_version)
    version = session.get("version", 0) + 1
    updates = {**validated_structure(req), "version": version, "updated_by": user["username"]}
    if user["username"] != session.get("user_id"):
        updates["coach_edit_version"] = version
    db.update_session(session_id, updates)
    return {"ok": True, "version": version}


@app.delete("/api/sessions/{session_id}")
def delete_session(session_id: str, base_version: Optional[int] = None, user: Dict = Depends(current_user)):
    session = get_accessible_session(session_id, user)
    if session.get("user_id") != user["username"] and session.get("coach_username") != user["username"]:
        raise HTTPException(status_code=403, detail="Only the athlete or the coach who created it can delete this session")
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


@app.post("/api/sessions/{session_id}/log")
def log_workout(session_id: str, req: LogRequest, user: Dict = Depends(current_user)):
    """Record a workout. The session keeps the latest values only if its structure still matches.

    A workout synced after its session was deleted is still recorded, so offline work is never lost."""
    snapshot = clean_snapshot(req.supersets)
    if not any(superset["exercises"] for superset in snapshot):
        raise HTTPException(status_code=400, detail="Nothing to log")
    session = db.get_session(session_id)
    if session is None:
        athlete = req.user_id or user["username"]
        if athlete != user["username"] and athlete not in (user.get("clients") or []):
            raise HTTPException(status_code=404, detail="Session not found")
        orphan = {"_id": session_id, "name": req.session_name or "Deleted session", "user_id": athlete}
        log_id = db.add_workout_log(orphan, snapshot, user["username"], req.client_id, parse_logged_at(req.logged_at))
        return {"id": log_id, "session_updated": False, "session_deleted": True}
    if not can_access_session(user, session):
        raise HTTPException(status_code=404, detail="Session not found")
    structure_matches = structure_signature(snapshot) == structure_signature(session.get("supersets", []))
    if structure_matches:
        db.update_session(session_id, {"supersets": snapshot})
    log_id = db.add_workout_log(session, snapshot, user["username"], req.client_id, parse_logged_at(req.logged_at))
    return {"id": log_id, "session_updated": structure_matches, "session_deleted": False}


@app.get("/api/sessions/{session_id}/history")
def session_history(session_id: str, user: Dict = Depends(current_user)):
    get_accessible_session(session_id, user)
    return [{
        "id": str(log["_id"]),
        "created_at": iso(log.get("created_at")),
        "logged_by": log.get("logged_by"),
        "user_id": log.get("user_id"),
        "supersets": log.get("supersets", []),
    } for log in db.get_workout_logs_by_session(session_id)]

# ==================== CLIENTS (coach side) ====================


@app.get("/api/clients")
def list_clients(user: Dict = Depends(coach_user)):
    clients = user.get("clients") or []
    pending = user.get("pending_client_requests") or []
    excluded = {user["username"], *clients, *pending}
    candidates = [{"username": other["username"], "name": other.get("name", "")}
                  for other in db.get_all_users() if other.get("username") and other["username"] not in excluded]
    return {
        "clients": display_names(clients),
        "pending": display_names(pending),
        "candidates": sorted(candidates, key=lambda item: item["name"].lower() or item["username"].lower()),
    }


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
