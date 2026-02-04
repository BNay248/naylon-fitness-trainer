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
    
    st.write("### Setup Progress")
    st.write(f"- **Muscle Groups:** {muscle_groups_count}")
    st.write(f"- **Categories:** {categories_count}")
    st.write(f"- **Equipment:** {equipment_count}")
    
    if muscle_groups_count > 0 and categories_count > 0 and equipment_count > 0:
        st.success("✅ Ready to manage exercises!")
        
        # Display existing exercises
        st.subheader("Existing Exercises")
        exercises = db.get_all_exercises()
        if exercises:
            for ex in exercises:
                with st.expander(f"**{ex['name']}**"):
                    if 'parent_id' in ex:
                        parent = db.get_exercise(ex['parent_id'])
                        st.write(f"**Variant of:** {parent['name'] if parent else 'Unknown'}")
                    st.write(f"**Instructions:** {ex['instructions']}")
                    # Get category names
                    cat_names = []
                    cat_ids = ex.get('category', [])
                    if isinstance(cat_ids, str):
                        cat_ids = [cat_ids]  # Handle old single category
                    for cat_id in cat_ids:
                        cat = db.get_category(cat_id)
                        if cat:
                            cat_names.append(cat['name'])
                    if cat_names:
                        st.write(f"**Categories:** {', '.join(cat_names)}")
                    else:
                        st.write("**Categories:** Unknown")
                    # Muscle groups
                    mg_names = []
                    for mg_id in ex.get('muscle_groups', []):
                        mg = db.get_muscle_group(mg_id)
                        if mg:
                            mg_names.append(mg['name'])
                    if mg_names:
                        st.write(f"**Muscle Groups:** {', '.join(mg_names)}")
                    # Additional muscles
                    additional_names = []
                    for m_id in ex.get('additional_muscles', []):
                        m = db.get_muscle(m_id)
                        if m:
                            additional_names.append(m['name'])
                    if additional_names:
                        st.write(f"**Additional Muscles:** {', '.join(additional_names)}")
                    # Equipment
                    eq_names = []
                    for eq_id in ex.get('equipment', []):
                        eq = db.get_equipment(eq_id)
                        if eq:
                            eq_names.append(eq['name'])
                    if eq_names:
                        st.write(f"**Equipment:** {', '.join(eq_names)}")
                        # Show equipment settings
                        equipment_settings = ex.get('equipment_settings', {})
                        if equipment_settings:
                            for eq_id, settings in equipment_settings.items():
                                eq = db.get_equipment(eq_id)
                                if eq:
                                    st.write(f"**{eq['name']} Settings:**")
                                    for char_name, value in settings.items():
                                        st.write(f"- {char_name}: {value}")
                    # Metrics
                    if ex.get('metrics'):
                        st.write("**Metrics:**")
                        for metric in ex['metrics']:
                            st.write(f"- {metric['name']} ({metric['type']})")
        else:
            st.info("No exercises added yet.")
        
        # Add new exercise form
        st.subheader("Add New Exercise")
        
        # Initialize defaults
        if 'exercise_defaults' not in st.session_state:
            st.session_state.exercise_defaults = {}
        
        is_variant = st.checkbox("Create as variant of existing exercise")
        
        if is_variant:
            exercises = db.get_all_exercises()
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
        
        with st.form("add_exercise"):
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
            default_metrics = st.session_state.exercise_defaults.get('metrics', [{}, {}, {}])
            while len(default_metrics) < 3:
                default_metrics.append({})
            
            col3, col4 = st.columns(2)
            with col3:
                metric1_name = st.text_input("Metric 1 Name", value=default_metrics[0].get('name', ''))
                metric2_name = st.text_input("Metric 2 Name", value=default_metrics[1].get('name', ''))
                metric3_name = st.text_input("Metric 3 Name", value=default_metrics[2].get('name', ''))
            with col4:
                metric1_type_index = 0 if default_metrics[0].get('type') == 'string' else 0
                metric1_type = st.selectbox("Type", ["numeric", "string"], index=metric1_type_index, key="m1")
                metric2_type_index = 0 if default_metrics[1].get('type') == 'string' else 0
                metric2_type = st.selectbox("Type", ["numeric", "string"], index=metric2_type_index, key="m2")
                metric3_type_index = 0 if default_metrics[2].get('type') == 'string' else 0
                metric3_type = st.selectbox("Type", ["numeric", "string"], index=metric3_type_index, key="m3")
            
            submitted = st.form_submit_button("Add Exercise")
        
        if submitted:
            if not name or not instructions or not selected_categories:
                st.error("Please fill in all required fields (Name, Instructions, Categories).")
            else:
                # Build metrics list
                metrics = []
                if metric1_name.strip():
                    metrics.append({"name": metric1_name.strip(), "type": metric1_type})
                if metric2_name.strip():
                    metrics.append({"name": metric2_name.strip(), "type": metric2_type})
                if metric3_name.strip():
                    metrics.append({"name": metric3_name.strip(), "type": metric3_type})
                
                # Build exercise data
                exercise_data = {
                    "name": name.strip(),
                    "instructions": instructions.strip(),
                    "category": [category_options[cat] for cat in selected_categories],
                    "muscle_groups": [mg_options[mg] for mg in selected_mg],
                    "additional_muscles": [additional_muscle_options[m] for m in selected_additional],
                    "equipment": [eq_options[eq] for eq in selected_eq],
                    "equipment_settings": equipment_settings,
                    "metrics": metrics
                }
                
                # Add parent_id if variant
                if is_variant:
                    exercise_data["parent_id"] = st.session_state.variant_parent_id
                
                # Add to database
                exercise_id = db.add_exercise(exercise_data)
                st.success(f"Exercise '{name}' added successfully!")
                
                # Clear defaults
                st.session_state.exercise_defaults = {}
                if 'variant_parent_id' in st.session_state:
                    del st.session_state.variant_parent_id
                if 'current_parent' in st.session_state:
                    st.session_state.current_parent = None
                
                st.rerun()  # Refresh to show the new exercise
    
    else:
        st.warning("⚠️ Please add muscle groups, categories, and equipment first")

elif st.session_state.get("authentication_status") == False:
    st.error('Username/password is incorrect')
elif st.session_state.get("authentication_status") == None:
    st.warning('Please enter your username and password')