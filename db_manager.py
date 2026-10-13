from pymongo import MongoClient, ASCENDING, DESCENDING
from datetime import datetime
from typing import List, Dict, Optional
from bson.objectid import ObjectId


def to_object_id(value: str) -> Optional[ObjectId]:
    try:
        return ObjectId(value)
    except Exception:
        return None


class TrainerDB:
    def __init__(self, connection_string="mongodb://localhost:27017/"):
        self.client = MongoClient(connection_string)
        self.db = self.client.workout_platform

    def ensure_indexes(self) -> None:
        self.db.workout_logs.create_index([("session_id", ASCENDING), ("created_at", DESCENDING)])
        self.db.workout_logs.create_index([("user_id", ASCENDING), ("created_at", DESCENDING)])
        self.db.workout_logs.create_index("client_id", sparse=True)
        self.db.sessions.create_index("client_id", sparse=True)
        self.db.sessions.create_index("assignees", sparse=True)

    # Exercise methods
    def add_exercise(self, exercise_data: Dict) -> str:
        result = self.db.exercises.insert_one(exercise_data)
        return str(result.inserted_id)

    def get_exercise(self, exercise_id: str) -> Optional[Dict]:
        oid = to_object_id(exercise_id)
        return self.db.exercises.find_one({"_id": oid}) if oid else None

    def get_all_exercises(self) -> List[Dict]:
        return sorted(self.db.exercises.find(), key=lambda item: str(item.get("name", "")).lower())

    def get_visible_exercises(self, usernames: List[str]) -> List[Dict]:
        """Global exercises (no owner) plus the personal exercises of the given users."""
        found = self.db.exercises.find({"owner": {"$in": [None, *usernames]}})
        return sorted(found, key=lambda item: str(item.get("name", "")).lower())

    def get_exercises_by_ids(self, exercise_ids: List[str]) -> List[Dict]:
        oids = [oid for oid in map(to_object_id, exercise_ids) if oid]
        return list(self.db.exercises.find({"_id": {"$in": oids}})) if oids else []

    def get_pending_exercises(self) -> List[Dict]:
        return sorted(self.db.exercises.find({"pending": True}), key=lambda item: str(item.get("name", "")).lower())

    def make_exercise_global(self, exercise_id: str) -> bool:
        oid = to_object_id(exercise_id)
        return bool(oid) and self.db.exercises.update_one({"_id": oid}, {"$unset": {"owner": "", "pending": ""}}).matched_count > 0

    def update_exercise(self, exercise_id: str, updates: Dict) -> bool:
        oid = to_object_id(exercise_id)
        return bool(oid) and self.db.exercises.update_one({"_id": oid}, {"$set": updates}).matched_count > 0

    def delete_exercise(self, exercise_id: str) -> bool:
        oid = to_object_id(exercise_id)
        return bool(oid) and self.db.exercises.delete_one({"_id": oid}).deleted_count > 0

    # Legacy client/coach profile collections (kept in sync for the Streamlit branch)
    def add_client(self, client_data: Dict) -> str:
        client_data.setdefault('history', [])
        result = self.db.clients.insert_one(client_data)
        return str(result.inserted_id)

    def add_coach(self, coach_data: Dict) -> str:
        coach_data.setdefault('assigned_sessions', [])
        result = self.db.coaches.insert_one(coach_data)
        return str(result.inserted_id)

    # User methods
    def add_user(self, user_data: Dict) -> str:
        result = self.db.users.insert_one(user_data)
        return str(result.inserted_id)

    def get_user_by_username(self, username: str) -> Optional[Dict]:
        return self.db.users.find_one({"username": username})

    def get_users_by_usernames(self, usernames: List[str]) -> Dict[str, Dict]:
        return {user["username"]: user for user in self.db.users.find({"username": {"$in": list(usernames)}})}

    def get_all_users(self) -> List[Dict]:
        return list(self.db.users.find())

    def update_user(self, username: str, updates: Dict) -> bool:
        result = self.db.users.update_one({"username": username}, {"$set": updates})
        return result.modified_count > 0

    def delete_user(self, username: str) -> bool:
        result = self.db.users.delete_one({"username": username})
        self.db.coaches.delete_many({"username": username})
        self.db.clients.delete_many({"username": username})
        self.db.users.update_many({}, {"$pull": {
            "clients": username, "coaches": username,
            "pending_client_requests": username, "pending_coach_requests": username,
        }})
        return result.deleted_count > 0

    # Coach <-> client relationships (usernames stored on both user documents)
    def request_client(self, coach: str, client: str) -> None:
        self.db.users.update_one({"username": client}, {"$addToSet": {"pending_coach_requests": coach}})
        self.db.users.update_one({"username": coach}, {"$addToSet": {"pending_client_requests": client}})

    def cancel_client_request(self, coach: str, client: str) -> None:
        self.db.users.update_one({"username": coach}, {"$pull": {"pending_client_requests": client}})
        self.db.users.update_one({"username": client}, {"$pull": {"pending_coach_requests": coach}})

    def accept_coach_request(self, coach: str, client: str) -> None:
        self.db.users.update_one({"username": client}, {"$pull": {"pending_coach_requests": coach}, "$addToSet": {"coaches": coach}})
        self.db.users.update_one({"username": coach}, {"$pull": {"pending_client_requests": client}, "$addToSet": {"clients": client}})

    def remove_relationship(self, coach: str, client: str) -> None:
        self.db.users.update_one({"username": coach}, {"$pull": {"clients": client}})
        self.db.users.update_one({"username": client}, {"$pull": {"coaches": coach}})

    # Session methods
    def add_session(self, session_data: Dict) -> str:
        session_data['created_at'] = datetime.now()
        result = self.db.sessions.insert_one(session_data)
        return str(result.inserted_id)

    def get_session(self, session_id: str) -> Optional[Dict]:
        oid = to_object_id(session_id)
        return self.db.sessions.find_one({"_id": oid}) if oid else None

    def get_session_by_client_id(self, client_id: str) -> Optional[Dict]:
        return self.db.sessions.find_one({"client_id": client_id})

    def get_sessions_for_users(self, usernames: List[str]) -> List[Dict]:
        usernames = list(usernames)
        sessions = self.db.sessions.find({"$or": [{"user_id": {"$in": usernames}}, {"assignees": {"$in": usernames}}]})
        return sorted(sessions, key=lambda item: str(item.get("name", "")).lower())

    def update_session(self, session_id: str, updates: Dict) -> bool:
        oid = to_object_id(session_id)
        return bool(oid) and self.db.sessions.update_one({"_id": oid}, {"$set": updates}).matched_count > 0

    def delete_session(self, session_id: str) -> bool:
        oid = to_object_id(session_id)
        return bool(oid) and self.db.sessions.delete_one({"_id": oid}).deleted_count > 0

    # Workout log methods (one document per completed/saved workout)
    def add_workout_log(self, session: Dict, supersets: List[Dict], logged_by: str,
                        client_id: Optional[str] = None, created_at: Optional[datetime] = None) -> str:
        if client_id:
            existing = self.db.workout_logs.find_one({"client_id": client_id})
            if existing:
                return str(existing["_id"])
        result = self.db.workout_logs.insert_one({
            "session_id": str(session.get("_id")),
            "session_name": session.get("name", ""),
            "user_id": session.get("user_id"),
            "logged_by": logged_by,
            "created_at": created_at or datetime.now(),
            "supersets": supersets,
            "client_id": client_id,
        })
        return str(result.inserted_id)

    def get_workout_logs_by_session(self, session_id: str, user_id: str) -> List[Dict]:
        return list(self.db.workout_logs.find({"session_id": session_id, "user_id": user_id}).sort("created_at", -1))

    def move_workout_logs(self, from_session_id: str, to_session_id: str, user_id: str) -> None:
        self.db.workout_logs.update_many({"session_id": from_session_id, "user_id": user_id}, {"$set": {"session_id": to_session_id}})

    def get_latest_exercise_log(self, user_id: str, exercise_name: str) -> Optional[Dict]:
        """Most recent logged rounds of an exercise for a user: {"created_at", "instances"}.

        Rounds swapped for another exercise count as that exercise, not the planned one, so a log
        where every round was swapped out is skipped and an older one is used."""
        logs = self.db.workout_logs.find(
            {"user_id": user_id, "$or": [{"supersets.exercises.name": exercise_name},
                                          {"supersets.exercises.instances.swap.name": exercise_name}]},
            sort=[("created_at", -1)],
        )
        for log in logs:
            for superset in log.get("supersets", []):
                for exercise in superset.get("exercises", []):
                    rounds = [{"metrics": instance.get("metrics", {})} for instance in exercise.get("instances", [])
                              if ((instance.get("swap") or {}).get("name") or exercise.get("name")) == exercise_name]
                    if rounds:
                        return {"created_at": log.get("created_at"), "instances": rounds}
        return None
