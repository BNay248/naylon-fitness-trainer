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

# Cached data functions
@st.cache_data
def get_all_exercises():
    db = TrainerDB()
    return db.get_all_exercises()

@st.cache_data
def get_all_categories():
    db = TrainerDB()
    return db.get_all_categories()

@st.cache_data
def get_all_muscle_groups():
    db = TrainerDB()
    return db.get_all_muscle_groups()

@st.cache_data
def get_all_equipment():
    db = TrainerDB()
    return db.get_all_equipment()

@st.cache_data
def get_all_muscles():
    db = TrainerDB()
    return db.get_all_muscles()

# Check authentication status
if st.session_state.get("authentication_status"):
    # User is authenticated
    authenticator.logout(location='sidebar')
    st.sidebar.write(f'Welcome *{st.session_state["name"]}*')
    
    # Get data
    exercises = get_all_exercises()
    categories = get_all_categories()
    muscle_groups = get_all_muscle_groups()
    equipment = get_all_equipment()
    all_muscles = get_all_muscles()
    
    st.title("Manage Exercises")
    
    # Add new exercise form
    st.subheader("Add New Exercise")
    
    # Variant selection
    is_variant = st.checkbox("Create as variant of existing exercise")
    defaults = {}
    if is_variant and exercises:
        parent_options = [ex['name'] for ex in exercises]
        selected_parent = st.selectbox("Select Parent Exercise", options=parent_options)
        parent = next((ex for ex in exercises if ex['name'] == selected_parent), None)
        if parent:
            defaults = {
                'name': parent['name'] + ' Variant',
                'instructions': parent['instructions'],
                'category': parent.get('category', []),
                'muscle_groups': parent.get('muscle_groups', []),
                'additional_muscles': parent.get('additional_muscles', []),
                'equipment': parent.get('equipment', []),
                'equipment_settings': parent.get('equipment_settings', {}),
                'metrics': parent.get('metrics', [])
            }
    
    with st.form("add_exercise_form"):
        # Name and instructions
        name = st.text_input("Exercise Name *", value=defaults.get('name', ''))
        instructions = st.text_area("Instructions *", value=defaults.get('instructions', ''))
        
        # Categories
        category_options = {cat['name']: str(cat['_id']) for cat in categories}
        default_cat_names = []
        if 'category' in defaults:
            cat_ids = defaults['category']
            if isinstance(cat_ids, list):
                for cat_id in cat_ids:
                    cat = next((c for c in categories if str(c['_id']) == cat_id), None)
                    if cat:
                        default_cat_names.append(cat['name'])
            else:
                cat = next((c for c in categories if str(c['_id']) == cat_ids), None)
                if cat:
                    default_cat_names.append(cat['name'])
        selected_categories = st.multiselect("Categories *", options=list(category_options.keys()), default=default_cat_names)
        
        # Muscle Groups
        mg_options = {mg['name']: str(mg['_id']) for mg in muscle_groups}
        default_mg_names = []
        if 'muscle_groups' in defaults:
            for mg_id in defaults['muscle_groups']:
                mg = next((m for m in muscle_groups if str(m['_id']) == mg_id), None)
                if mg:
                    default_mg_names.append(mg['name'])
        selected_mg = st.multiselect("Muscle Groups", options=list(mg_options.keys()), default=default_mg_names)
        
        # Additional Muscles
        selected_group_ids = set()
        for name in selected_mg:
            if name in mg_options:
                selected_group_ids.add(mg_options[name])
        additional_muscle_options = {}
        for m in all_muscles:
            if m.get('group') not in selected_group_ids:
                additional_muscle_options[m['name']] = str(m['_id'])
        default_additional_names = []
        if 'additional_muscles' in defaults:
            for m_id in defaults['additional_muscles']:
                m = next((mus for mus in all_muscles if str(mus['_id']) == m_id), None)
                if m and m['name'] in additional_muscle_options:
                    default_additional_names.append(m['name'])
        selected_additional = st.multiselect("Additional Muscles", options=list(additional_muscle_options.keys()), default=default_additional_names)
        
        # Equipment
        eq_options = {eq['name']: str(eq['_id']) for eq in equipment}
        default_eq_names = []
        if 'equipment' in defaults:
            for eq_id in defaults['equipment']:
                eq = next((e for e in equipment if str(e['_id']) == eq_id), None)
                if eq:
                    default_eq_names.append(eq['name'])
        selected_eq = st.multiselect("Equipment", options=list(eq_options.keys()), default=default_eq_names)
        
        # Equipment Characteristics
        equipment_settings = {}
        if selected_eq:
            st.write("**Equipment Characteristics:**")
            for eq_name in selected_eq:
                eq_id = eq_options[eq_name]
                eq_data = next((e for e in equipment if str(e['_id']) == eq_id), None)
                if eq_data and 'characteristics' in eq_data:
                    st.write(f"**{eq_name}:**")
                    equipment_settings[eq_id] = {}
                    for char_name, char_data in eq_data['characteristics'].items():
                        if isinstance(char_data, dict):
                            char_type = char_data.get('type', 'variant')
                            if char_type == 'numeric':
                                current_value = defaults.get('equipment_settings', {}).get(eq_id, {}).get(char_name, 0)
                                value = st.number_input(f"{char_name}", value=int(current_value), step=1, format="%d")
                                equipment_settings[eq_id][char_name] = value
                            elif char_type == 'variant':
                                variants = char_data.get('variants', [])
                                current_value = defaults.get('equipment_settings', {}).get(eq_id, {}).get(char_name, variants[0] if variants else '')
                                value = st.selectbox(f"{char_name}", options=variants, index=variants.index(current_value) if current_value in variants else 0)
                                equipment_settings[eq_id][char_name] = value
                        else:
                            variants = char_data if isinstance(char_data, list) else []
                            current_value = defaults.get('equipment_settings', {}).get(eq_id, {}).get(char_name, variants[0] if variants else '')
                            value = st.selectbox(f"{char_name}", options=variants, index=variants.index(current_value) if current_value in variants else 0)
                            equipment_settings[eq_id][char_name] = value
        
        # Metrics
        st.write("**Metrics** (optional)")
        default_metrics = defaults.get('metrics', [])
        num_metrics = st.number_input("Number of Metrics", min_value=0, value=len(default_metrics), step=1)
        metrics = []
        for i in range(int(num_metrics)):
            if i < len(default_metrics):
                default_name = default_metrics[i].get('name', '')
                default_type = default_metrics[i].get('type', 'numeric')
            else:
                default_name = ''
                default_type = 'numeric'
            name_metric = st.text_input(f"Metric {i+1} Name", value=default_name)
            type_options = ["numeric", "string"]
            type_index = 0 if default_type == 'numeric' else 1
            type_metric = st.selectbox(f"Metric {i+1} Type", options=type_options, index=type_index)
            metrics.append({"name": name_metric, "type": type_metric})
        
        submitted = st.form_submit_button("Add Exercise")
        if submitted:
            if not name or not instructions or not selected_categories:
                st.error("Please fill in all required fields (Name, Instructions, Categories).")
            else:
                final_metrics = [m for m in metrics if m['name'].strip()]
                exercise_data = {
                    "name": name.strip(),
                    "instructions": instructions.strip(),
                    "category": [category_options[cat] for cat in selected_categories],
                    "muscle_groups": [mg_options[mg] for mg in selected_mg],
                    "additional_muscles": [additional_muscle_options[m] for m in selected_additional],
                    "equipment": [eq_options[eq] for eq in selected_eq],
                    "equipment_settings": equipment_settings,
                    "metrics": final_metrics
                }
                if is_variant and 'parent' in locals() and parent:
                    exercise_data["parent_id"] = str(parent['_id'])
                db = TrainerDB()
                exercise_id = db.add_exercise(exercise_data)
                st.success("Exercise added successfully!")
                st.cache_data.clear()  # Clear cache to refresh data
                st.rerun()
    
    # Display existing exercises
    st.subheader("Existing Exercises")
    
    if exercises:
        for ex in exercises:
            with st.expander(f"**{ex['name']}**"):
                with st.form(f"edit_form_{ex['_id']}"):
                    # Name (read-only)
                    st.text_input("Exercise Name", value=ex['name'], disabled=True)
                    
                    # Instructions
                    instructions = st.text_area("Instructions *", value=ex['instructions'])
                    
                    # Categories
                    current_cat_names = []
                    cat_ids = ex.get('category', [])
                    if isinstance(cat_ids, str):
                        cat_ids = [cat_ids]
                    for cat_id in cat_ids:
                        cat = next((c for c in categories if str(c['_id']) == cat_id), None)
                        if cat:
                            current_cat_names.append(cat['name'])
                    selected_categories = st.multiselect("Categories *", options=list(category_options.keys()), default=current_cat_names, key=f"edit_cat_{ex['_id']}")
                    
                    # Muscle Groups
                    current_mg_names = []
                    for mg_id in ex.get('muscle_groups', []):
                        mg = next((m for m in muscle_groups if str(m['_id']) == mg_id), None)
                        if mg:
                            current_mg_names.append(mg['name'])
                    selected_mg = st.multiselect("Muscle Groups", options=list(mg_options.keys()), default=current_mg_names, key=f"edit_mg_{ex['_id']}")
                    
                    # Additional Muscles
                    selected_group_ids = set()
                    for name in selected_mg:
                        if name in mg_options:
                            selected_group_ids.add(mg_options[name])
                    additional_muscle_options = {}
                    for m in all_muscles:
                        if m.get('group') not in selected_group_ids:
                            additional_muscle_options[m['name']] = str(m['_id'])
                    current_additional_names = []
                    for m_id in ex.get('additional_muscles', []):
                        m = next((mus for mus in all_muscles if str(mus['_id']) == m_id), None)
                        if m:
                            current_additional_names.append(m['name'])
                    selected_additional = st.multiselect("Additional Muscles", options=list(additional_muscle_options.keys()), default=current_additional_names, key=f"edit_add_{ex['_id']}")
                    
                    # Equipment
                    current_eq_names = []
                    for eq_id in ex.get('equipment', []):
                        eq = next((e for e in equipment if str(e['_id']) == eq_id), None)
                        if eq:
                            current_eq_names.append(eq['name'])
                    selected_eq = st.multiselect("Equipment", options=list(eq_options.keys()), default=current_eq_names, key=f"edit_eq_{ex['_id']}")
                    
                    # Equipment Characteristics
                    equipment_settings = {}
                    if selected_eq:
                        st.write("**Equipment Characteristics:**")
                        for eq_name in selected_eq:
                            eq_id = eq_options[eq_name]
                            eq_data = next((e for e in equipment if str(e['_id']) == eq_id), None)
                            if eq_data and 'characteristics' in eq_data:
                                st.write(f"**{eq_name}:**")
                                equipment_settings[eq_id] = {}
                                for char_name, char_data in eq_data['characteristics'].items():
                                    if isinstance(char_data, dict):
                                        char_type = char_data.get('type', 'variant')
                                        if char_type == 'numeric':
                                            current_value = ex.get('equipment_settings', {}).get(eq_id, {}).get(char_name, 0)
                                            value = st.number_input(f"{char_name}", value=int(current_value), step=1, format="%d", key=f"edit_char_num_{ex['_id']}_{eq_id}_{char_name}")
                                            equipment_settings[eq_id][char_name] = value
                                        elif char_type == 'variant':
                                            variants = char_data.get('variants', [])
                                            current_value = ex.get('equipment_settings', {}).get(eq_id, {}).get(char_name, variants[0] if variants else '')
                                            value = st.selectbox(f"{char_name}", options=variants, index=variants.index(current_value) if current_value in variants else 0, key=f"edit_char_var_{ex['_id']}_{eq_id}_{char_name}")
                                            equipment_settings[eq_id][char_name] = value
                                    else:
                                        variants = char_data if isinstance(char_data, list) else []
                                        current_value = ex.get('equipment_settings', {}).get(eq_id, {}).get(char_name, variants[0] if variants else '')
                                        value = st.selectbox(f"{char_name}", options=variants, index=variants.index(current_value) if current_value in variants else 0, key=f"edit_char_legacy_{ex['_id']}_{eq_id}_{char_name}")
                                        equipment_settings[eq_id][char_name] = value
                    
                    # Metrics
                    st.write("**Metrics** (optional)")
                    current_metrics = ex.get('metrics', [])
                    num_metrics = st.number_input("Number of Metrics", min_value=0, value=len(current_metrics), step=1, key=f"edit_num_metrics_{ex['_id']}")
                    metrics = []
                    for i in range(int(num_metrics)):
                        if i < len(current_metrics):
                            default_name = current_metrics[i].get('name', '')
                            default_type = current_metrics[i].get('type', 'numeric')
                        else:
                            default_name = ''
                            default_type = 'numeric'
                        name_metric = st.text_input(f"Metric {i+1} Name", value=default_name, key=f"edit_metric_name_{ex['_id']}_{i}")
                        type_options = ["numeric", "string"]
                        type_index = 0 if default_type == 'numeric' else 1
                        type_metric = st.selectbox(f"Metric {i+1} Type", options=type_options, index=type_index, key=f"edit_metric_type_{ex['_id']}_{i}")
                        metrics.append({"name": name_metric, "type": type_metric})
                    
                    submitted = st.form_submit_button("Save Changes")
                    if submitted:
                        if not instructions or not selected_categories:
                            st.error("Please fill in all required fields (Instructions, Categories).")
                        else:
                            final_metrics = [m for m in metrics if m['name'].strip()]
                            update_data = {
                                "instructions": instructions.strip(),
                                "category": [category_options[cat] for cat in selected_categories],
                                "muscle_groups": [mg_options[mg] for mg in selected_mg],
                                "additional_muscles": [additional_muscle_options[m] for m in selected_additional],
                                "equipment": [eq_options[eq] for eq in selected_eq],
                                "equipment_settings": equipment_settings,
                                "metrics": final_metrics
                            }
                            db = TrainerDB()
                            success = db.update_exercise(str(ex['_id']), update_data)
                            if success:
                                st.success("Exercise updated successfully!")
                                st.cache_data.clear()  # Clear cache to refresh data
                                st.rerun()
                            else:
                                st.error("Failed to update exercise.")
    else:
        st.info("No exercises yet. Add some to get started!")
        
elif st.session_state.get("authentication_status") == False:
    st.error('Username/password is incorrect')
elif st.session_state.get("authentication_status") == None:
    st.warning('Please enter your username and password')