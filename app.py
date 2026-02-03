import streamlit as st
from db_manager import WorkoutDB
import pandas as pd

# Initialize database
db = WorkoutDB()

st.set_page_config(page_title="Trainer Platform", layout="wide")

st.title("🏋️ Trainer Platform")

# Sidebar navigation
page = st.sidebar.selectbox("Navigation", ["Workouts", "Clients", "Coaches", "Sessions"])

# ==================== WORKOUTS PAGE ====================
if page == "Workouts":
    st.header("Manage Workouts")
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.subheader("All Workouts")
        workouts = db.get_all_workouts()
        
        if workouts:
            # Convert to DataFrame for better display
            df = pd.DataFrame(workouts)
            if '_id' in df.columns:
                df['_id'] = df['_id'].astype(str)
            st.dataframe(df, use_container_width=True)
        else:
            st.info("No workouts yet. Add one to get started!")
    
    with col2:
        st.subheader("Add New Workout")
        with st.form("add_workout"):
            name = st.text_input("Workout Name*")
            category = st.selectbox("Category*", ["strength", "cardio", "flexibility", "sport", "functional"])
            difficulty = st.slider("Difficulty", 1, 10, 5)
            
            muscle_groups = st.multiselect(
                "Muscle Groups",
                ["chest", "back", "shoulders", "arms", "core", "legs", "glutes", "full_body"]
            )
            
            equipment = st.multiselect(
                "Equipment",
                ["barbell", "dumbbell", "kettlebell", "resistance_band", "bodyweight", "machine", "cable"]
            )
            
            tags = st.text_input("Tags (comma-separated)", placeholder="compound, push, etc.")
            
            notes = st.text_area("Notes")
            
            submitted = st.form_submit_button("Add Workout")
            
            if submitted:
                if name and category:
                    workout = {
                        "name": name,
                        "category": category,
                        "difficulty": difficulty,
                        "muscle_groups": muscle_groups,
                        "equipment": equipment,
                        "tags": [t.strip() for t in tags.split(",") if t.strip()],
                        "notes": notes
                    }
                    workout_id = db.add_workout(workout)
                    st.success(f"✅ Workout added! ID: {workout_id}")
                    st.rerun()
                else:
                    st.error("Please fill in required fields (Name, Category)")

# ==================== CLIENTS PAGE ====================
elif page == "Clients":
    st.header("Manage Clients")
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.subheader("All Clients")
        clients = db.get_all_clients()
        
        if clients:
            df = pd.DataFrame(clients)
            if '_id' in df.columns:
                df['_id'] = df['_id'].astype(str)
            st.dataframe(df, use_container_width=True)
        else:
            st.info("No clients yet. Add one to get started!")
    
    with col2:
        st.subheader("Add New Client")
        with st.form("add_client"):
            name = st.text_input("Client Name*")
            fitness_level = st.slider("Fitness Level", 1, 10, 5)
            
            goals = st.multiselect(
                "Goals",
                ["strength", "hypertrophy", "endurance", "weight_loss", "athletic_performance", "general_fitness"]
            )
            
            notes = st.text_area("Notes")
            
            submitted = st.form_submit_button("Add Client")
            
            if submitted:
                if name:
                    client = {
                        "name": name,
                        "fitness_level": fitness_level,
                        "goals": goals,
                        "notes": notes,
                        "history": []
                    }
                    client_id = db.add_client(client)
                    st.success(f"✅ Client added! ID: {client_id}")
                    st.rerun()
                else:
                    st.error("Please enter a client name")

# ==================== COACHES PAGE ====================
elif page == "Coaches":
    st.header("Manage Coaches")
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.subheader("All Coaches")
        coaches = db.get_all_coaches()
        
        if coaches:
            df = pd.DataFrame(coaches)
            if '_id' in df.columns:
                df['_id'] = df['_id'].astype(str)
            st.dataframe(df, use_container_width=True)
        else:
            st.info("No coaches yet. Add one to get started!")
    
    with col2:
        st.subheader("Add New Coach")
        with st.form("add_coach"):
            name = st.text_input("Coach Name*")
            
            style_tags = st.multiselect(
                "Coaching Style",
                ["progressive_overload", "functional", "bodybuilding", "powerlifting", "crossfit", "athletic"]
            )
            
            specialties = st.text_input("Specialties (comma-separated)")
            
            submitted = st.form_submit_button("Add Coach")
            
            if submitted:
                if name:
                    coach = {
                        "name": name,
                        "style_tags": style_tags,
                        "specialties": [s.strip() for s in specialties.split(",") if s.strip()],
                        "assigned_sessions": []
                    }
                    coach_id = db.add_coach(coach)
                    st.success(f"✅ Coach added! ID: {coach_id}")
                    st.rerun()
                else:
                    st.error("Please enter a coach name")

# ==================== SESSIONS PAGE ====================
elif page == "Sessions":
    st.header("Training Sessions")
    
    st.subheader("Create New Session")
    
    clients = db.get_all_clients()
    coaches = db.get_all_coaches()
    workouts = db.get_all_workouts()
    
    if not clients or not coaches or not workouts:
        st.warning("⚠️ You need at least one client, coach, and workout to create a session.")
    else:
        with st.form("create_session"):
            client = st.selectbox("Client", options=[str(c['_id']) for c in clients], format_func=lambda x: next((c['name'] for c in clients if str(c['_id']) == x), x))
            coach = st.selectbox("Coach", options=[str(c['_id']) for c in coaches], format_func=lambda x: next((c['name'] for c in coaches if str(c['_id']) == x), x))
            
            st.write("Select 9 workouts for this session:")
            selected_workouts = st.multiselect(
                "Workouts",
                options=[str(w['_id']) for w in workouts],
                format_func=lambda x: next((w['name'] for w in workouts if str(w['_id']) == x), x),
                max_selections=9
            )
            
            notes = st.text_area("Session Notes")
            
            submitted = st.form_submit_button("Create Session")
            
            if submitted:
                if len(selected_workouts) == 9:
                    session = {
                        "client_id": client,
                        "coach_id": coach,
                        "workout_ids": selected_workouts,
                        "notes": notes
                    }
                    session_id = db.add_session(session)
                    st.success(f"✅ Session created! ID: {session_id}")
                    st.rerun()
                else:
                    st.error(f"Please select exactly 9 workouts (currently selected: {len(selected_workouts)})")
    
    st.divider()
    
    st.subheader("All Sessions")
    sessions = db.get_all_sessions()
    
    if sessions:
        for session in sessions:
            with st.expander(f"Session {str(session['_id'])} - {session['created_at']}"):
                st.write(f"**Client ID:** {session['client_id']}")
                st.write(f"**Coach ID:** {session['coach_id']}")
                st.write(f"**Workouts:** {len(session['workout_ids'])}")
                if session.get('notes'):
                    st.write(f"**Notes:** {session['notes']}")
    else:
        st.info("No sessions yet.")