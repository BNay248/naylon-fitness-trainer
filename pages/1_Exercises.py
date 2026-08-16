import streamlit as st
from db_manager import TrainerDB
import pandas as pd
from auth_helper import load_config, create_authenticator, render_login_and_registration

# Page config
st.set_page_config(page_title="Naylon Fitness Portal", page_icon="NFP.jpg", layout="wide")

config = load_config()
db = TrainerDB()
authenticator = create_authenticator(config, db)
render_login_and_registration(authenticator, config, db)

# Check authentication status from session state
if st.session_state.get("authentication_status"):
    # User is authenticated
    authenticator.logout(location='sidebar')
    st.sidebar.write(f'Welcome *{st.session_state["name"]}*')
    
    # Initialize database
    db = TrainerDB()
    current_username = st.session_state.get("username")
    if current_username:
        current_user = db.get_user_by_username(current_username)
    else:
        st.error ("Error: No username found in session state.")
        st.stop()
    if current_user:
        role = current_user.get("role", "client") if current_user else "client"
        if role != "coach":
            st.info("This page is for coaches to manage exercises. If you'd like to become a coach, please contact the administrator (bradleynaylon@yahoo.com).")
            st.stop()
    else:
        st.error("Error: Current user data not found.")
        st.stop()
    
    def get_exercises():
        exercises = list(db.db.exercises.find())
        return exercises
    
    possible_metrics = ["Reps", "Weight", "Duration", "Calories", "Resistance", "Distance"]
    
    st.title("Manage Exercises")
    
    @st.fragment
    def exercise_creation_form():
        st.subheader("Add Exercise")
        if st.button("Refresh Data", key="refresh_data"):
            st.rerun(scope="app")

        #Container for exercise creation form
        with st.container(border=True):
            selected_name = st.text_input("Exercise Name*", key="create_exercise_name")
            selected_instructions = st.text_area("Instructions*", key="create_exercise_description")
            selected_video_url = st.text_input("Video URL (optional)", key="create_exercise_video_url")
            #Metrics
            selected_metrics = st.segmented_control("Metrics", options=possible_metrics, selection_mode="multi", width="stretch", key="create_exercise_metrics")
            if st.button("Add Exercise", key="submit_exercise", width="stretch"):
                if not selected_name or not selected_instructions:
                    st.error("Please fill in all required fields")
                    st.stop()
                
                # Create exercise item
                exercise_item = {
                    "name": selected_name,
                    "instructions": selected_instructions,
                    "video_url": selected_video_url.strip() if selected_video_url else "",
                    "metrics": selected_metrics
                }
                
                # Insert into database
                db.db.exercises.insert_one(exercise_item)
                st.toast("Exercise added successfully", icon="✅")

    exercise_creation_form()

    # Display existing exercises
    st.subheader("All Exercises")

    @st.fragment
    def render_exercise_editor(exercise):
        with st.expander(f"{exercise['name']}"):
            edit_name = st.text_input("Exercise Name*", value=exercise.get('name', ''), key=f"edit_{exercise['_id']}_name")
            edit_instructions = st.text_area("Instructions*", value=exercise.get('instructions', ''), key=f"edit_{exercise['_id']}_instructions")
            edit_video_url = st.text_input("Video URL (optional)", value=exercise.get('video_url', ''), key=f"edit_{exercise['_id']}_video_url")
            edit_metrics = st.segmented_control("Metrics", options=possible_metrics, selection_mode="multi", default=exercise.get('metrics', []), key=f"edit_{exercise['_id']}_metrics")
            col_save, col_delete = st.columns(2)
            with col_save:
                if st.button("Save", key=f"save_{exercise['_id']}", width="stretch"):
                    update_data = {
                        "name": edit_name,
                        "instructions": edit_instructions,
                        "video_url": edit_video_url.strip() if edit_video_url else "",
                        "metrics": edit_metrics
                    }
                    db.db.exercises.update_one({"_id": exercise["_id"]}, {"$set": update_data})
                    st.rerun(scope="app")
            with col_delete:
                if st.button("Delete", key=f"delete_{exercise['_id']}", width="stretch"):
                    db.db.exercises.delete_one({"_id": exercise["_id"]})
                    st.rerun(scope="app")

    exercises = get_exercises()
    for exercise in exercises:
        render_exercise_editor(exercise)