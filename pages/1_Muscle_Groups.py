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

st.set_page_config(page_title="NFP - Muscles", layout="wide")

# Check authentication status from session state
if st.session_state.get("authentication_status"):
    # User is authenticated
    authenticator.logout(location='sidebar')
    st.sidebar.write(f'Welcome *{st.session_state["name"]}*')
    
    # Initialize database
    db = TrainerDB()

    @st.cache_data(show_spinner=False)
    def get_muscles():
        return list(db.db.muscles.find())
    
    @st.cache_data(show_spinner=False)
    def get_muscle_groups():
        return list(db.db.muscle_groups.find())

    st.title("Manage Muscles & Muscle Groups")
    
    col1, col2 = st.columns(2)
    
    with col1:        
        @st.fragment
        def add_muscle_form():
            st.subheader("Add Muscle")
            with st.container(border=True):
                muscle_name = st.text_input("Muscle Name*", placeholder="e.g., Biceps; Triceps; Quadriceps", key="add_muscle_name")
                muscle_description = st.text_area("Description", placeholder="Optional description", key="add_muscle_description")
                
                if st.button("Add Muscle", key="submit_muscle"):
                    if muscle_name:
                        # Split by semicolons and create multiple muscles
                        muscle_names = [m.strip() for m in muscle_name.split(';') if m.strip()]
                        
                        if muscle_names:
                            for m_name in muscle_names:
                                muscle = {
                                    "name": m_name,
                                    "description": muscle_description.strip() if muscle_description else ""
                                }
                                db.db.muscles.insert_one(muscle)
                            get_muscles.clear()
                            st.rerun(scope="app")
                        else:
                            st.error("Please enter at least one muscle name")
                    else:
                        st.error("Please enter muscle name(s)")

        add_muscle_form()
        
        st.subheader("**All Muscles**")
        muscles = get_muscles()
        
        if muscles:
            muscles.sort(key=lambda x: x['name'])
            for muscle in muscles:
                st.markdown("---")
                col_delete, col_name = st.columns([1, 5])
                with col_delete:
                    if st.button("🗑️", key=f"delete_muscle_{muscle['_id']}", help="Delete muscle"):
                        muscle_name = muscle['name']
                        # Remove this muscle from all muscle groups
                        muscle_id = muscle['_id']
                        db.db.muscle_groups.update_many(
                            {"muscles": muscle_id},
                            {"$pull": {"muscles": muscle_id}}
                        )
                        # Remove this muscle from all exercises' additional muscles
                        db.db.exercises.update_many(
                            {"muscles": muscle_name},
                            {"$pull": {"muscles": muscle_name}}
                        )
                        # Then delete the muscle
                        db.db.muscles.delete_one({"_id": muscle_id})
                        get_muscles.clear()
                        get_muscle_groups.clear()  # Clear muscle groups cache too since they reference muscles
                        st.rerun(scope="app")
                with col_name:
                    st.write(f"**{muscle['name']}**")
                    if 'description' in muscle and muscle['description']:
                        st.write(f"_{muscle['description']}_")
        else:
            st.info("No muscles yet. Add some to get started!")
    
    with col2:
        @st.fragment
        def add_muscle_group_form():
            st.subheader("Add Muscle Group")
            with st.container(border=True):
                name = st.text_input("Muscle Group Name*", placeholder="e.g., Arms; Legs; Chest", key="add_muscle_group_name")
                description = st.text_area("Description", placeholder="Optional description", key="add_muscle_group_description")
                st.multiselect("Muscles", options=[muscle['name'] for muscle in get_muscles()], key="add_muscle_group_muscles")
                
                if st.button("Add Muscle Group", key="submit_muscle_group"):
                    if name:
                        muscle_group = {
                            "name": name.strip(),
                            "description": description.strip() if description else "",
                            "muscles": [muscle_dict[m] for m in st.session_state.get("add_muscle_group_muscles", []) if m in muscle_dict]
                        }
                        db.db.muscle_groups.insert_one(muscle_group)
                        get_muscle_groups.clear()
                        st.rerun(scope="app")
                    else:
                        st.error("Please enter a muscle group name")

        add_muscle_group_form()
        
        st.subheader("All Muscle Groups")
        
        # Get all muscles for multiselect options
        all_muscles = get_muscles()
        muscle_options = [muscle['name'] for muscle in all_muscles]
        muscle_dict = {muscle['name']: muscle['_id'] for muscle in all_muscles}
        reverse_muscle_dict = {str(muscle['_id']): muscle['name'] for muscle in all_muscles}
        
        muscle_groups = get_muscle_groups()
        
        if muscle_groups:
            muscle_groups.sort(key=lambda x: x['name'])
            for muscle_group in muscle_groups:
                @st.fragment
                def edit_muscle_group_fragment(mg=muscle_group):
                    with st.expander(f"{mg['name']}"):
                        if 'description' in mg and mg['description']:
                            st.write(f"**Description:** {mg['description']}")
                        
                        # Current muscles in this group
                        current_muscle_ids = mg.get('muscles', [])
                        current_muscle_names = [reverse_muscle_dict.get(str(mid), "Unknown") for mid in current_muscle_ids]
                        
                        st.write(f"**Current Muscles:** {', '.join(current_muscle_names) if current_muscle_names else 'None'}")
                        
                        # Edit form
                        col1, col2 = st.columns(2)
                        with col1:
                            edit_name = st.text_input("Name", value=mg.get('name', ''), key=f"edit_mg_name_{mg['_id']}")
                            edit_description = st.text_area("Description", value=mg.get('description', ''), key=f"edit_mg_desc_{mg['_id']}")
                        
                        with col2:
                            # Multiselect to edit muscles
                            selected_muscles = st.multiselect(
                                "Select muscles",
                                options=muscle_options,
                                default=current_muscle_names,
                                key=f"edit_mg_muscles_{mg['_id']}"
                            )
                        
                        col_save, col_delete = st.columns(2)
                        with col_save:
                            if st.button("Save", key=f"save_mg_{mg['_id']}", width="stretch"):
                                # Convert selected names back to IDs
                                selected_ids = [muscle_dict[name] for name in selected_muscles if name in muscle_dict]
                                
                                # Update the muscle group
                                db.db.muscle_groups.update_one(
                                    {"_id": mg["_id"]},
                                    {"$set": {"name": edit_name, "description": edit_description, "muscles": selected_ids}}
                                )
                                get_muscle_groups.clear()
                                st.rerun(scope="app")
                        with col_delete:
                            if st.button("Delete", key=f"delete_mg_{mg['_id']}", width="stretch"):
                                muscle_group_name = mg['name']
                                # Remove this muscle group from all exercises
                                db.db.exercises.update_many(
                                    {"muscle_groups": muscle_group_name},
                                    {"$pull": {"muscle_groups": muscle_group_name}}
                                )
                                # Then delete the muscle group
                                db.db.muscle_groups.delete_one({"_id": mg["_id"]})
                                get_muscle_groups.clear()
                                st.rerun(scope="app")
                
                edit_muscle_group_fragment()
        else:
            st.info("No muscle groups yet. Add some to get started!")

elif st.session_state.get("authentication_status") == False:
    st.error('Username/password is incorrect')
elif st.session_state.get("authentication_status") == None:
    st.warning('Please enter your username and password')