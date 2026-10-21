from pymongo import MongoClient, ASCENDING, DESCENDING
from datetime import datetime
from typing import List, Dict, Optional
from bson.objectid import ObjectId


def to_object_id(value: str) -> Optional[ObjectId]:
    try:
        return ObjectId(value)
    except Exception:
        return None


# Exercise fields holding muscle / muscle group ids (as strings, like the other cross-references).
# The *_group_ids fields are what the exercise works: the groups added directly (added_*) plus the
# group of every listed muscle, with primary winning over secondary.
MUSCLE_FIELDS = ["primary_muscle_ids", "secondary_muscle_ids"]
GROUP_FIELDS = ["primary_group_ids", "secondary_group_ids"]
ADDED_GROUP_FIELDS = ["added_primary_group_ids", "added_secondary_group_ids"]
# Other library links: equipment used, movement patterns, and the next-harder exercises (easier ones are the reverse links).
LINK_FIELDS = ["equipment_ids", "movement_pattern_ids", "progression_ids"]
EQUIPMENT_TYPES = ["Free Weight", "Machine", "Cable", "Bodyweight", "Accessory", "Cardio"]
PATTERN_KINDS = ["Compound", "Isolation", "Core", "Power", "Skill", "Mobility", "Conditioning"]


def unique(values) -> List[str]:
    return list(dict.fromkeys(values))


def with_groups(fields: Dict, group_of: Dict[str, str]) -> Dict:
    """Fills the worked groups: groups added directly plus each muscle's group. Primary beats secondary."""
    primary = unique(fields["added_primary_group_ids"] + [group_of[m] for m in fields["primary_muscle_ids"] if m in group_of])
    secondary = [group for group in unique(fields["added_secondary_group_ids"] + [group_of[m] for m in fields["secondary_muscle_ids"] if m in group_of])
                 if group not in primary]
    return {**fields, "primary_group_ids": primary, "secondary_group_ids": secondary}


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
        self.db.muscles.create_index("group_id")
        for field in MUSCLE_FIELDS + GROUP_FIELDS + LINK_FIELDS:
            self.db.exercises.create_index(field, sparse=True)

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

    def get_exercises_using(self, fields: List[str], value: str) -> List[Dict]:
        return list(self.db.exercises.find({"$or": [{field: value} for field in fields]}))

    def pull_from_exercises(self, fields: List[str], value: str) -> None:
        self.db.exercises.update_many({}, {"$pull": {field: value for field in fields}})

    # Library collections (muscle_groups, muscles, equipment, movement_patterns): named documents
    # that exercises reference by id. Every muscle belongs to one group via group_id.
    def add_item(self, collection: str, data: Dict) -> str:
        return str(self.db[collection].insert_one(data).inserted_id)

    def get_item(self, collection: str, item_id: str) -> Optional[Dict]:
        oid = to_object_id(item_id)
        return self.db[collection].find_one({"_id": oid}) if oid else None

    def get_items(self, collection: str) -> List[Dict]:
        return sorted(self.db[collection].find(), key=lambda item: str(item.get("name", "")).lower())

    def count_items(self, collection: str, query: Dict) -> int:
        return self.db[collection].count_documents(query)

    def update_item(self, collection: str, item_id: str, updates: Dict) -> bool:
        oid = to_object_id(item_id)
        return bool(oid) and self.db[collection].update_one({"_id": oid}, {"$set": updates}).matched_count > 0

    def delete_item(self, collection: str, item_id: str) -> bool:
        oid = to_object_id(item_id)
        return bool(oid) and self.db[collection].delete_one({"_id": oid}).deleted_count > 0

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

    # Templates are managed by the templates app; this is only read when recording a workout queued before the move.
    def get_template(self, template_id: str) -> Optional[Dict]:
        oid = to_object_id(template_id)
        return self.db.templates.find_one({"_id": oid}) if oid else None

    # Workout log methods (one document per completed/saved workout)
    def add_workout_log(self, session: Dict, supersets: List[Dict], logged_by: str,
                        client_id: Optional[str] = None, created_at: Optional[datetime] = None, extra: Optional[Dict] = None) -> str:
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
            **(extra or {}),
        })
        return str(result.inserted_id)

    def get_logs_with_exercises(self, user_id: str, exercise_ids: List[str]) -> List[Dict]:
        """A user's logs that include any of these exercises, planned or swapped in."""
        return list(self.db.workout_logs.find(
            {"user_id": user_id, "$or": [{"supersets.exercises.exercise_id": {"$in": exercise_ids}},
                                         {"supersets.exercises.instances.swap.exercise_id": {"$in": exercise_ids}}]},
            {"supersets": 1},
        ))

    def get_workout_logs_by_session(self, session_id: str, user_id: str) -> List[Dict]:
        return list(self.db.workout_logs.find({"session_id": session_id, "user_id": user_id}).sort("created_at", -1))

    def move_workout_logs(self, from_session_id: str, to_session_id: str, user_id: str) -> None:
        self.db.workout_logs.update_many({"session_id": from_session_id, "user_id": user_id}, {"$set": {"session_id": to_session_id}})

    def get_latest_exercise_log(self, user_id: str, exercise_id: str) -> Optional[Dict]:
        """Most recent logged rounds of an exercise for a user: {"created_at", "instances"}.

        Rounds swapped for another exercise count as that exercise, not the planned one, so a log
        where every round was swapped out is skipped and an older one is used."""
        logs = self.db.workout_logs.find(
            {"user_id": user_id, "$or": [{"supersets.exercises.exercise_id": exercise_id},
                                          {"supersets.exercises.instances.swap.exercise_id": exercise_id}]},
            sort=[("created_at", -1)],
        )
        for log in logs:
            for superset in log.get("supersets", []):
                for exercise in superset.get("exercises", []):
                    rounds = [{"metrics": instance.get("metrics", {})} for instance in exercise.get("instances", [])
                              if ((instance.get("swap") or {}).get("exercise_id") or exercise.get("exercise_id")) == exercise_id]
                    if rounds:
                        return {"created_at": log.get("created_at"), "instances": rounds}
        return None
