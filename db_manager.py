from pymongo import MongoClient
from datetime import datetime
from typing import List, Dict, Optional
from bson.objectid import ObjectId

class WorkoutDB:
    def __init__(self, connection_string="mongodb://localhost:27017/"):
        self.client = MongoClient(connection_string)
        self.db = self.client.workout_platform
        
    # Workout methods
    def add_workout(self, workout_data: Dict) -> str:
        result = self.db.workouts.insert_one(workout_data)
        return str(result.inserted_id)
    
    def get_workout(self, workout_id: str) -> Optional[Dict]:
        try:
            return self.db.workouts.find_one({"_id": ObjectId(workout_id)})
        except:
            return None
    
    def get_all_workouts(self) -> List[Dict]:
        return list(self.db.workouts.find())
    
    def update_workout(self, workout_id: str, updates: Dict) -> bool:
        try:
            result = self.db.workouts.update_one(
                {"_id": ObjectId(workout_id)},
                {"$set": updates}
            )
            return result.modified_count > 0
        except:
            return False
    
    def delete_workout(self, workout_id: str) -> bool:
        try:
            result = self.db.workouts.delete_one({"_id": ObjectId(workout_id)})
            return result.deleted_count > 0
        except:
            return False
    
    # Client methods
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
