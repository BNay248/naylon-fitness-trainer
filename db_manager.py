from pymongo import MongoClient
from datetime import datetime
from typing import List, Dict, Optional
from bson.objectid import ObjectId

class TrainerDB:
    def __init__(self, connection_string="mongodb://localhost:27017/"):
        self.client = MongoClient(connection_string)
        self.db = self.client.workout_platform
        
    # Exercise methods
    def add_exercise(self, exercise_data: Dict) -> str:
        result = self.db.exercises.insert_one(exercise_data)
        return str(result.inserted_id)
    
    def get_exercise(self, exercise_id: str) -> Optional[Dict]:
        try:
            return self.db.exercises.find_one({"_id": ObjectId(exercise_id)})
        except:
            return None
    
    def get_all_exercises(self) -> List[Dict]:
        return list(self.db.exercises.find())
    
    def update_exercise(self, exercise_id: str, updates: Dict) -> bool:
        try:
            result = self.db.exercises.update_one(
                {"_id": ObjectId(exercise_id)},
                {"$set": updates}
            )
            return result.modified_count > 0
        except:
            return False
    
    def delete_exercise(self, exercise_id: str) -> bool:
        try:
            result = self.db.exercises.delete_one({"_id": ObjectId(exercise_id)})
            return result.deleted_count > 0
        except:
            return False
    
    #Client methods
    def add_client(self, client_data: Dict) -> str:
        if 'history' not in client_data:
            client_data['history'] = []
        result = self.db.clients.insert_one(client_data)
        return str(result.inserted_id)
    
    def get_client(self, client_id: str) -> Optional[Dict]:
        try:
            return self.db.clients.find_one({"_id": ObjectId(client_id)})
        except:
            return None
    
    def get_all_clients(self) -> List[Dict]:
        return list(self.db.clients.find())
    
    def update_client(self, client_id: str, updates: Dict) -> bool:
        try:
            result = self.db.clients.update_one(
                {"_id": ObjectId(client_id)},
                {"$set": updates}
            )
            return result.modified_count > 0
        except:
            return False

    # User methods
    def add_user(self, user_data: Dict) -> str:
        result = self.db.users.insert_one(user_data)
        return str(result.inserted_id)

    def get_user_by_username(self, username: str) -> Optional[Dict]:
        return self.db.users.find_one({"username": username})

    def get_all_users(self) -> List[Dict]:
        return list(self.db.users.find())

    def delete_user_by_username(self, username: str) -> bool:
        result = self.db.users.delete_one({"username": username})
        return result.deleted_count > 0

    def update_user(self, username: str, updates: Dict) -> bool:
        result = self.db.users.update_one({"username": username}, {"$set": updates})
        return result.modified_count > 0

    # Coach methods
    def add_coach(self, coach_data: Dict) -> str:
        if 'assigned_sessions' not in coach_data:
            coach_data['assigned_sessions'] = []
        result = self.db.coaches.insert_one(coach_data)
        return str(result.inserted_id)
    
    def get_coach(self, coach_id: str) -> Optional[Dict]:
        try:
            return self.db.coaches.find_one({"_id": ObjectId(coach_id)})
        except:
            return None
    
    def get_all_coaches(self) -> List[Dict]:
        return list(self.db.coaches.find())
    
    def update_coach(self, coach_id: str, updates: Dict) -> bool:
        try:
            result = self.db.coaches.update_one(
                {"_id": ObjectId(coach_id)},
                {"$set": updates}
            )
            return result.modified_count > 0
        except:
            return False
    
    # Session methods
    def add_session(self, session_data: Dict) -> str:
        session_data['created_at'] = datetime.now()
        result = self.db.sessions.insert_one(session_data)
        return str(result.inserted_id)
    
    def get_session(self, session_id: str) -> Optional[Dict]:
        try:
            return self.db.sessions.find_one({"_id": ObjectId(session_id)})
        except:
            return None
    
    def get_sessions_by_client(self, client_id: str) -> List[Dict]:
        return list(self.db.sessions.find({"client_id": client_id}))
    
    def get_sessions_by_coach(self, coach_id: str) -> List[Dict]:
        return list(self.db.sessions.find({"coach_id": coach_id}))
    
    def get_all_sessions(self) -> List[Dict]:
        return list(self.db.sessions.find())
