import streamlit as st
from db_manager import TrainerDB
import pandas as pd
import streamlit_authenticator as stauth
import yaml
from yaml.loader import SafeLoader

# Page config
st.set_page_config(page_title="Naylon Fitness Portal", page_icon="NFP.jpg", layout="wide")

# Load authentication config
with open('config.yaml') as file:
    config = yaml.load(file, Loader=SafeLoader)

# Create authenticator
authenticator = stauth.Authenticate(
    config['credentials'],
    config['cookie']['name'],
    config['cookie']['key'],
    config['cookie']['expiry_days']
)

# Login widget
authenticator.login()

st.set_page_config(page_title="NFP - Exercises", layout="wide")

# Check authentication status from session state
if st.session_state.get("authentication_status"):
    # User is authenticated
    authenticator.logout(location='sidebar')
    st.sidebar.write(f'Welcome *{st.session_state["name"]}*')
    
    # Initialize database
    db = TrainerDB()

    @st.cache_data(show_spinner=False)
    def get_data():
        categories = list(db.db.categories.find())
        muscle_groups = list(db.db.muscle_groups.find())
        muscles = list(db.db.muscles.find())
        equipment = list(db.db.equipment.find())
        category_names = [cat['name'] for cat in categories]
        muscle_group_names = [mg['name'] for mg in muscle_groups]
        muscle_names = [m['name'] for m in muscles]
        equipment_names = [eq['name'] for eq in equipment]
        return categories, muscle_groups, muscles, equipment, category_names, muscle_group_names, muscle_names, equipment_names
    
    @st.cache_data(show_spinner=False)
    def get_exercises():
        exercises = list(db.db.exercises.find())
        return exercises

    categories, muscle_groups, muscles, equipment, category_names, muscle_group_names, muscle_names, equipment_names = get_data()
    
    possible_metrics = ["Reps", "Weight", "Duration", "Calories", "Resistance", "Distance"]
    
    st.title("Manage Exercises")
    
    @st.fragment
    def exercise_creation_form():
        st.subheader("Add Exercise")
        if st.button("Refresh Data", key="refresh_data"):
            get_data.clear()
            st.rerun(scope="app")
        with st.container(border=True):
            col1, col2 = st.columns(2)
            with col1:
                selected_name = st.text_input("Exercise Name*", key="create_exercise_name")
                selected_instructions = st.text_area("Instructions*", key="create_exercise_description")
                selected_categories = st.multiselect("Categories*", options=category_names, key="create_exercise_categories", default=None)
            with col2:
                selected_muscle_groups = st.multiselect("Muscle Groups*", options=muscle_group_names, key="create_exercise_muscle_groups", default=None)
                
                # Get muscles that are already in the selected muscle groups
                excluded_muscle_ids = set()
                if selected_muscle_groups:
                    for group_name in selected_muscle_groups:
                        group_doc = next((mg for mg in muscle_groups if mg['name'] == group_name), None)
                        if group_doc and "muscles" in group_doc:
                            excluded_muscle_ids.update(group_doc["muscles"])
                
                # Get all muscles not in the excluded IDs
                available_muscles = []
                for muscle in muscles:
                    if muscle["_id"] not in excluded_muscle_ids:
                        available_muscles.append(muscle["name"])
                
                selected_muscles = st.multiselect("Additional Muscles*", options=available_muscles, default=[m for m in st.session_state.get("create_exercise_muscles", []) if m in available_muscles], key="create_exercise_muscles")
                selected_equipment = st.multiselect("Equipment", options=equipment_names, key="create_exercise_equipment", default=None)
                if selected_equipment:
                    st.markdown("**Equipment Characteristics**")
                    for eq_name in selected_equipment:
                        # Find the equipment object
                        eq_obj = next((eq for eq in equipment if eq['name'] == eq_name), None)
                        if eq_obj and 'characteristics' in eq_obj:
                            with st.expander(f"⚙️ {eq_name} Settings"):
                                for char_name, char_data in eq_obj['characteristics'].items():
                                    if isinstance(char_data, dict) and char_data.get('type') == 'numeric':
                                        # Numeric characteristic - number input for integers
                                        st.number_input(
                                            f"{char_name}",
                                            min_value=0,
                                            step=1,
                                            key=f"exercise_equipment_{eq_name}_{char_name}",
                                            help=f"Enter {char_name} value for {eq_name}"
                                        )
                                    elif isinstance(char_data, dict) and char_data.get('type') == 'variant':
                                        # Variant characteristic - selectbox with predefined options
                                        variants = char_data.get('variants', [])
                                        st.selectbox(
                                            f"{char_name}",
                                            options=variants,
                                            key=f"exercise_equipment_{eq_name}_{char_name}",
                                            help=f"Select {char_name} for {eq_name}"
                                        )
                                    else:
                                        # Fallback - text input for any other type
                                        st.text_input(
                                            f"{char_name}",
                                            key=f"exercise_equipment_{eq_name}_{char_name}",
                                            help=f"Enter {char_name} for {eq_name}"
                                        )
            selected_metrics = st.segmented_control("Metrics", options=possible_metrics, selection_mode="multi", width="stretch", key="create_exercise_metrics")
            if st.button("Add Exercise", key="submit_exercise", width="stretch"):
                if not selected_name or not selected_instructions or not selected_categories or not selected_muscle_groups:
                    st.error("Please fill in all required fields")
                    st.stop()
                
                # Collect equipment characteristics
                equipment_characteristics = {}
                for eq_name in selected_equipment:
                    eq_obj = next((eq for eq in equipment if eq['name'] == eq_name), None)
                    if eq_obj and 'characteristics' in eq_obj:
                        eq_chars = {}
                        for char_name, char_data in eq_obj['characteristics'].items():
                            key = f"exercise_equipment_{eq_name}_{char_name}"
                            value = st.session_state.get(key, "")
                            if value:
                                eq_chars[char_name] = value
                        if eq_chars:
                            equipment_characteristics[eq_name] = eq_chars
                
                # Create exercise item
                exercise_item = {
                    "name": selected_name,
                    "instructions": selected_instructions,
                    "categories": selected_categories,
                    "muscle_groups": selected_muscle_groups,
                    "muscles": selected_muscles,
                    "equipment": selected_equipment,
                    "equipment_characteristics": equipment_characteristics,
                    "metrics": selected_metrics
                }
                
                # Insert into database
                db.db.exercises.insert_one(exercise_item)
                get_exercises.clear()  # Clear cache to refresh exercise list
                st.rerun(scope="app")

    exercise_creation_form()

    # Display existing exercises
    st.subheader("All Exercises")
    exercises = get_exercises()
    for exercise in exercises:
        with st.expander(f"{exercise['name']}"):
            col1, col2 = st.columns(2)
            with col1:
                edit_name = st.text_input("Exercise Name*", value=exercise.get('name', ''), key=f"edit_{exercise['_id']}_name")
                edit_instructions = st.text_area("Instructions*", value=exercise.get('instructions', ''), key=f"edit_{exercise['_id']}_instructions")
                edit_categories = st.multiselect("Categories*", options=category_names, default=exercise.get('categories', []), key=f"edit_{exercise['_id']}_categories")
            with col2:
                edit_muscle_groups = st.multiselect("Muscle Groups*", options=muscle_group_names, default=exercise.get('muscle_groups', []), key=f"edit_{exercise['_id']}_muscle_groups")
                
                # Get muscles that are already in the selected muscle groups
                excluded_muscle_ids = set()
                if edit_muscle_groups:
                    for group_name in edit_muscle_groups:
                        group_doc = next((mg for mg in muscle_groups if mg['name'] == group_name), None)
                        if group_doc and "muscles" in group_doc:
                            excluded_muscle_ids.update(group_doc["muscles"])
                
                # Get all muscles not in the excluded IDs
                available_muscles = []
                for muscle in muscles:
                    if muscle["_id"] not in excluded_muscle_ids:
                        available_muscles.append(muscle["name"])
                
                edit_muscles = st.multiselect("Additional Muscles*", options=available_muscles, default=[m for m in exercise.get('muscles', []) if m in available_muscles], key=f"edit_{exercise['_id']}_muscles")
                edit_equipment = st.multiselect("Equipment", options=equipment_names, default=exercise.get('equipment', []), key=f"edit_{exercise['_id']}_equipment")
                if edit_equipment:
                    st.markdown("**Equipment Characteristics**")
                    for eq_name in edit_equipment:
                        # Find the equipment object
                        eq_obj = next((eq for eq in equipment if eq['name'] == eq_name), None)
                        if eq_obj and 'characteristics' in eq_obj:
                            with st.expander(f"⚙️ {eq_name} Settings"):
                                for char_name, char_data in eq_obj['characteristics'].items():
                                    stored_value = exercise.get('equipment_characteristics', {}).get(eq_name, {}).get(char_name, '')
                                    if isinstance(char_data, dict) and char_data.get('type') == 'numeric':
                                        # Numeric characteristic - number input for integers
                                        st.number_input(
                                            f"{char_name}",
                                            min_value=0,
                                            step=1,
                                            value=int(stored_value) if stored_value else 0,
                                            key=f"edit_{exercise['_id']}_equipment_{eq_name}_{char_name}",
                                            help=f"Enter {char_name} value for {eq_name}"
                                        )
                                    elif isinstance(char_data, dict) and char_data.get('type') == 'variant':
                                        # Variant characteristic - selectbox with predefined options
                                        variants = char_data.get('variants', [])
                                        st.selectbox(
                                            f"{char_name}",
                                            options=variants,
                                            index=variants.index(stored_value) if stored_value in variants else 0,
                                            key=f"edit_{exercise['_id']}_equipment_{eq_name}_{char_name}",
                                            help=f"Select {char_name} for {eq_name}"
                                        )
                                    else:
                                        # Fallback - text input for any other type
                                        st.text_input(
                                            f"{char_name}",
                                            value=stored_value,
                                            key=f"edit_{exercise['_id']}_equipment_{eq_name}_{char_name}",
                                            help=f"Enter {char_name} for {eq_name}"
                                        )
            edit_metrics = st.segmented_control("Metrics", options=possible_metrics, selection_mode="multi", default=exercise.get('metrics', []), key=f"edit_{exercise['_id']}_metrics")
            col_save, col_delete = st.columns(2)
            with col_save:
                if st.button("Save", key=f"save_{exercise['_id']}", width="stretch"):
                    # Collect equipment characteristics
                    equipment_characteristics = {}
                    for eq_name in edit_equipment:
                        eq_obj = next((eq for eq in equipment if eq['name'] == eq_name), None)
                        if eq_obj and 'characteristics' in eq_obj:
                            eq_chars = {}
                            for char_name, char_data in eq_obj['characteristics'].items():
                                key = f"edit_{exercise['_id']}_equipment_{eq_name}_{char_name}"
                                value = st.session_state.get(key, "")
                                if value:
                                    eq_chars[char_name] = value
                            if eq_chars:
                                equipment_characteristics[eq_name] = eq_chars
                    
                    # Update exercise item
                    update_data = {
                        "name": edit_name,
                        "instructions": edit_instructions,
                        "categories": edit_categories,
                        "muscle_groups": edit_muscle_groups,
                        "muscles": edit_muscles,
                        "equipment": edit_equipment,
                        "equipment_characteristics": equipment_characteristics,
                        "metrics": edit_metrics
                    }
                    
                    # Update in database
                    db.db.exercises.update_one({"_id": exercise["_id"]}, {"$set": update_data})
                    get_exercises.clear()  # Clear cache to refresh exercise list
                    st.rerun(scope="app")
            with col_delete:
                if st.button("Delete", key=f"delete_{exercise['_id']}", width="stretch"):
                    db.db.exercises.delete_one({"_id": exercise["_id"]})
                    get_exercises.clear()
                    st.rerun(scope="app")
        
elif st.session_state.get("authentication_status") == False:
    st.error('Username/password is incorrect')
elif st.session_state.get("authentication_status") == None:
    st.warning('Please enter your username and password')