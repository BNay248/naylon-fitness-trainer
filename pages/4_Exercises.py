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
    
    st.title("Manage Exercises")
    
    muscle_groups_count = db.db.muscle_groups.count_documents({})
    categories_count = db.db.categories.count_documents({})
    equipment_count = db.db.equipment.count_documents({})
    
    # Initialize data early
    exercises = db.get_all_exercises()
        
    # Add new exercise form
    st.subheader("Add New Exercise")
    
    # Initialize defaults
    if 'exercise_defaults' not in st.session_state:
        st.session_state.exercise_defaults = {}
    
    is_variant = st.checkbox("Create as variant of existing exercise")
    
    if is_variant:
        if exercises:
            parent_options = {ex['name']: str(ex['_id']) for ex in exercises}
            
            # Track current parent to detect changes
            if 'current_parent' not in st.session_state:
                st.session_state.current_parent = None
            
            selected_parent = st.selectbox("Select Parent Exercise", options=list(parent_options.keys()))
            
            # Load parent data automatically when parent changes
            if selected_parent != st.session_state.current_parent:
                st.session_state.current_parent = selected_parent
                parent_id = parent_options[selected_parent]
                parent_data = db.get_exercise(parent_id)
                if parent_data:
                    st.session_state.exercise_defaults = {
                        'name': parent_data['name'] + ' Variant',
                        'instructions': parent_data['instructions'],
                        'category': parent_data['category'],
                        'muscle_groups': parent_data.get('muscle_groups', []),
                        'additional_muscles': parent_data.get('additional_muscles', []),
                        'equipment': parent_data.get('equipment', []),
                        'equipment_settings': parent_data.get('equipment_settings', {}),
                        'metrics': parent_data.get('metrics', [])
                    }
                    st.session_state.variant_parent_id = parent_id
                    st.info(f"Loaded data from '{parent_data['name']}'. Modify as needed.")
                else:
                    st.error("Parent exercise not found.")
        else:
            st.warning("No exercises available to create variants from.")
    
    # Metrics management for add form
    if 'add_metrics' not in st.session_state:
        st.session_state['add_metrics'] = st.session_state.exercise_defaults.get('metrics', [])
    else:
        # Sync with defaults if changed
        if st.session_state.exercise_defaults.get('metrics', []) != st.session_state['add_metrics']:
            st.session_state['add_metrics'] = st.session_state.exercise_defaults.get('metrics', [])
    
    # Add metric buttons
    col_add_num, col_add_str = st.columns(2)
    with col_add_num:
        if st.button("Add Numeric Metric"):
            st.session_state['add_metrics'].append({'name': '', 'type': 'numeric'})
            st.rerun()
    with col_add_str:
        if st.button("Add String Metric"):
            st.session_state['add_metrics'].append({'name': '', 'type': 'string'})
            st.rerun()
    
    # Handle delete for add metrics
    if 'add_delete_index' in st.session_state:
        del st.session_state['add_metrics'][st.session_state['add_delete_index']]
        del st.session_state['add_delete_index']
        st.rerun()
    
    with st.container():
        col1, col2 = st.columns(2)
        with col1:
            default_name = st.session_state.exercise_defaults.get('name', '')
            name = st.text_input("Exercise Name *", value=default_name, help="Required field")
            
            default_instructions = st.session_state.exercise_defaults.get('instructions', '')
            instructions = st.text_area("Instructions *", value=default_instructions, help="Required field")
            
            # Category
            categories = db.get_all_categories()
            if categories:
                category_options = {cat['name']: str(cat['_id']) for cat in categories}
                default_category_names = []
                if 'category' in st.session_state.exercise_defaults:
                    cat_ids = st.session_state.exercise_defaults['category']
                    if isinstance(cat_ids, list):
                        for cat_id in cat_ids:
                            cat = db.get_category(cat_id)
                            if cat:
                                default_category_names.append(cat['name'])
                    else:
                        cat = db.get_category(cat_ids)
                        if cat:
                            default_category_names.append(cat['name'])
                
                selected_categories = st.multiselect("Categories *", options=list(category_options.keys()), default=default_category_names, help="Required field")
            else:
                st.error("No categories available. Please add categories first.")
                selected_categories = []
        
        with col2:
            # Muscle Groups
            muscle_groups = db.get_all_muscle_groups()
            if muscle_groups:
                mg_options = {mg['name']: str(mg['_id']) for mg in muscle_groups}
                default_mg_names = []
                if 'muscle_groups' in st.session_state.exercise_defaults:
                    for mg_id in st.session_state.exercise_defaults['muscle_groups']:
                        mg = db.get_muscle_group(mg_id)
                        if mg:
                            default_mg_names.append(mg['name'])
                
                selected_mg = st.multiselect("Muscle Groups", options=list(mg_options.keys()), default=default_mg_names)
            else:
                selected_mg = []
            
            # Equipment
            equipment = db.get_all_equipment()
            if equipment:
                eq_options = {eq['name']: str(eq['_id']) for eq in equipment}
                default_eq_names = []
                if 'equipment' in st.session_state.exercise_defaults:
                    for eq_id in st.session_state.exercise_defaults['equipment']:
                        eq = db.get_equipment(eq_id)
                        if eq:
                            default_eq_names.append(eq['name'])
                
                selected_eq = st.multiselect("Equipment", options=list(eq_options.keys()), default=default_eq_names)
            else:
                selected_eq = []
            
            # Equipment characteristics
            equipment_settings = {}
            if selected_eq:
                st.write("**Equipment Characteristics:**")
                for eq_name in selected_eq:
                    eq_id = eq_options[eq_name]
                    eq_data = db.get_equipment(eq_id)
                    if eq_data and 'characteristics' in eq_data:
                        st.write(f"**{eq_name}:**")
                        equipment_settings[eq_id] = {}
                        for char_name, char_data in eq_data['characteristics'].items():
                            if isinstance(char_data, dict):
                                char_type = char_data.get('type', 'variant')
                                if char_type == 'numeric':
                                    value = st.number_input(f"{char_name}", key=f"{eq_id}_{char_name}")
                                    equipment_settings[eq_id][char_name] = value
                                elif char_type == 'variant':
                                    variants = char_data.get('variants', [])
                                    value = st.selectbox(f"{char_name}", options=variants, key=f"{eq_id}_{char_name}")
                                    equipment_settings[eq_id][char_name] = value
                            else:
                                # Legacy format - assume variant
                                variants = char_data if isinstance(char_data, list) else []
                                value = st.selectbox(f"{char_name}", options=variants, key=f"{eq_id}_{char_name}")
                                equipment_settings[eq_id][char_name] = value
            
            # Additional Muscles - multiselect from muscles not in selected muscle groups
            all_muscles = db.get_all_muscles()
            selected_group_names = set(selected_mg)  # selected_mg is list of group names
            additional_muscle_options = {}
            for m in all_muscles:
                if m.get('group') not in selected_group_names:
                    additional_muscle_options[m['name']] = str(m['_id'])
            
            default_additional_names = []
            if 'additional_muscles' in st.session_state.exercise_defaults:
                for m_id in st.session_state.exercise_defaults['additional_muscles']:
                    m = db.get_muscle(m_id)
                    if m and m['name'] in additional_muscle_options:
                        default_additional_names.append(m['name'])
            
            selected_additional = st.multiselect("Additional Muscles", options=list(additional_muscle_options.keys()), default=default_additional_names)
        
        # Metrics
        st.write("**Metrics** (optional)")
        metrics = []
        for i, metric in enumerate(st.session_state['add_metrics']):
            col1, col2, col3 = st.columns([3, 1, 1])
            with col1:
                name_metric = st.text_input(f"Metric {i+1} Name", value=metric['name'], key=f"add_metric_name_{i}")
            with col2:
                type_index = 0 if metric['type'] == 'numeric' else 1
                type_metric = st.selectbox("Type", ["numeric", "string"], index=type_index, key=f"add_metric_type_{i}")
            with col3:
                if st.button("🗑️", key=f"add_metric_delete_{i}"):
                    st.session_state['add_delete_index'] = i
                    st.rerun()
            metrics.append({"name": name_metric, "type": type_metric})
        
        if st.button("Add Exercise"):
            if not name or not instructions or not selected_categories:
                st.error("Please fill in all required fields (Name, Instructions, Categories).")
            else:
                # Build metrics list (filter out empty names)
                final_metrics = [m for m in metrics if m['name'].strip()]
                
                # Build exercise data
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
                
                # Add parent_id if variant
                if is_variant:
                    exercise_data["parent_id"] = st.session_state.variant_parent_id
                
                # Add to database
                exercise_id = db.add_exercise(exercise_data)
                
                # Clear defaults and metrics
                st.session_state.exercise_defaults = {}
                st.session_state['add_metrics'] = []
                if 'variant_parent_id' in st.session_state:
                    del st.session_state.variant_parent_id
                if 'current_parent' in st.session_state:
                    st.session_state.current_parent = None
                
                st.rerun()  # Refresh to show the new exercise
    
    # Display existing exercises
    st.subheader("Existing Exercises")
    
    @st.fragment
    def display_exercise(ex):
        with st.expander(f"**{ex['name']}**"):
            # Metrics management for edit form
            edit_metrics_key = f'edit_metrics_{ex["_id"]}'
            if edit_metrics_key not in st.session_state:
                st.session_state[edit_metrics_key] = ex.get('metrics', [])
            
            # Add metric buttons
            col_add_num, col_add_str = st.columns(2)
            with col_add_num:
                if st.button("Add Numeric Metric", key=f"add_num_{ex['_id']}"):
                    st.session_state[edit_metrics_key].append({'name': '', 'type': 'numeric'})
                    st.rerun()
            with col_add_str:
                if st.button("Add String Metric", key=f"add_str_{ex['_id']}"):
                    st.session_state[edit_metrics_key].append({'name': '', 'type': 'string'})
                    st.rerun()
            
            # Handle delete for edit metrics
            if 'edit_delete_index' in st.session_state:
                ex_id, idx = st.session_state['edit_delete_index']
                del st.session_state[f'edit_metrics_{ex_id}'][idx]
                del st.session_state['edit_delete_index']
                st.rerun()
            
            # Always show edit form with pre-populated values
            with st.container():
                col1, col2 = st.columns(2)
                with col1:
                    # Name is read-only
                    st.text_input("Exercise Name", value=ex['name'], disabled=True, help="Name cannot be changed")
                    
                    instructions = st.text_area("Instructions *", value=ex['instructions'], help="Required field")
                    
                    # Category
                    categories = db.get_all_categories()
                    if categories:
                        category_options = {cat['name']: str(cat['_id']) for cat in categories}
                        current_cat_names = []
                        cat_ids = ex.get('category', [])
                        if isinstance(cat_ids, str):
                            cat_ids = [cat_ids]
                        for cat_id in cat_ids:
                            cat = db.get_category(cat_id)
                            if cat:
                                current_cat_names.append(cat['name'])
                        
                        selected_categories = st.multiselect("Categories *", options=list(category_options.keys()), default=current_cat_names, help="Required field")
                    else:
                        selected_categories = []
                
                with col2:
                    # Muscle Groups
                    muscle_groups = db.get_all_muscle_groups()
                    if muscle_groups:
                        mg_options = {mg['name']: str(mg['_id']) for mg in muscle_groups}
                        current_mg_names = []
                        for mg_id in ex.get('muscle_groups', []):
                            mg = db.get_muscle_group(mg_id)
                            if mg:
                                current_mg_names.append(mg['name'])
                        
                        selected_mg = st.multiselect("Muscle Groups", options=list(mg_options.keys()), default=current_mg_names)
                    else:
                        selected_mg = []
                    
                    # Equipment
                    equipment = db.get_all_equipment()
                    if equipment:
                        eq_options = {eq['name']: str(eq['_id']) for eq in equipment}
                        current_eq_names = []
                        for eq_id in ex.get('equipment', []):
                            eq = db.get_equipment(eq_id)
                            if eq:
                                current_eq_names.append(eq['name'])
                        
                        selected_eq = st.multiselect("Equipment", options=list(eq_options.keys()), default=current_eq_names)
                    else:
                        selected_eq = []
                    
                    # Equipment characteristics
                    equipment_settings = {}
                    if selected_eq:
                        st.write("**Equipment Characteristics:**")
                        for eq_name in selected_eq:
                            eq_id = eq_options[eq_name]
                            eq_data = db.get_equipment(eq_id)
                            if eq_data and 'characteristics' in eq_data:
                                st.write(f"**{eq_name}:**")
                                equipment_settings[eq_id] = {}
                                for char_name, char_data in eq_data['characteristics'].items():
                                    if isinstance(char_data, dict):
                                        char_type = char_data.get('type', 'variant')
                                        if char_type == 'numeric':
                                            # Get current value
                                            current_value = ex.get('equipment_settings', {}).get(eq_id, {}).get(char_name, 0)
                                            value = st.number_input(f"{char_name}", value=current_value, key=f"edit_{eq_id}_{char_name}")
                                            equipment_settings[eq_id][char_name] = value
                                        elif char_type == 'variant':
                                            variants = char_data.get('variants', [])
                                            current_value = ex.get('equipment_settings', {}).get(eq_id, {}).get(char_name, variants[0] if variants else '')
                                            value = st.selectbox(f"{char_name}", options=variants, index=variants.index(current_value) if current_value in variants else 0, key=f"edit_{eq_id}_{char_name}")
                                            equipment_settings[eq_id][char_name] = value
                    
                    # Additional Muscles
                    all_muscles = db.get_all_muscles()
                    additional_muscle_options = {m['name']: str(m['_id']) for m in all_muscles}
                    
                    current_additional_names = []
                    for m_id in ex.get('additional_muscles', []):
                        m = db.get_muscle(m_id)
                        if m:
                            current_additional_names.append(m['name'])
                    
                    selected_additional = st.multiselect("Additional Muscles", options=list(additional_muscle_options.keys()), default=current_additional_names)
                
                # Metrics
                st.write("**Metrics** (optional)")
                metrics = []
                for i, metric in enumerate(st.session_state[edit_metrics_key]):
                    col1, col2, col3 = st.columns([3, 1, 1])
                    with col1:
                        name_metric = st.text_input(f"Metric {i+1} Name", value=metric['name'], key=f"edit_metric_name_{ex['_id']}_{i}")
                    with col2:
                        type_index = 0 if metric['type'] == 'numeric' else 1
                        type_metric = st.selectbox("Type", ["numeric", "string"], index=type_index, key=f"edit_metric_type_{ex['_id']}_{i}")
                    with col3:
                        if st.button("🗑️", key=f"edit_metric_delete_{ex['_id']}_{i}"):
                            st.session_state['edit_delete_index'] = (str(ex['_id']), i)
                            st.rerun()
                    metrics.append({"name": name_metric, "type": type_metric})
                
                if st.button("Save Changes", key=f"save_{ex['_id']}"):
                    if not instructions or not selected_categories:
                        st.error("Please fill in all required fields (Instructions, Categories).")
                    else:
                        # Build metrics list (filter out empty names)
                        final_metrics = [m for m in metrics if m['name'].strip()]
                        
                        # Build update data
                        update_data = {
                            "instructions": instructions.strip(),
                            "category": [category_options[cat] for cat in selected_categories],
                            "muscle_groups": [mg_options[mg] for mg in selected_mg],
                            "additional_muscles": [additional_muscle_options[m] for m in selected_additional],
                            "equipment": [eq_options[eq] for eq in selected_eq],
                            "equipment_settings": equipment_settings,
                            "metrics": final_metrics
                        }
                        
                        # Update in database
                        success = db.update_exercise(str(ex['_id']), update_data)
                        if success:
                            st.success("Exercise updated successfully!")
                            st.rerun()
                        else:
                            st.error("Failed to update exercise.")

    if exercises:
        for ex in exercises:
            display_exercise(ex)
    else:
        st.info("No exercises yet. Add some to get started!")
        
elif st.session_state.get("authentication_status") == False:
    st.error('Username/password is incorrect')
elif st.session_state.get("authentication_status") == None:
    st.warning('Please enter your username and password')