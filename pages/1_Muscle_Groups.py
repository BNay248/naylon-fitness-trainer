import streamlit as st
from db_manager import WorkoutDB
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
    db = WorkoutDB()
    
    st.title("Manage Muscles & Muscle Groups")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Manage Muscles")
        
        st.markdown("**Add Muscle**")
        with st.form("add_muscle"):
            muscle_name = st.text_input("Muscle Name*", placeholder="e.g., Biceps; Triceps; Quadriceps")
            muscle_description = st.text_area("Description", placeholder="Optional description")
            
            submitted_muscle = st.form_submit_button("Add Muscle")
            
            if submitted_muscle:
                if muscle_name:
                    # Split by semicolons and create multiple muscles
                    muscle_names = [m.strip() for m in muscle_name.split(';') if m.strip()]
                    
                    if muscle_names:
                        added_count = 0
                        for m_name in muscle_names:
                            muscle = {
                                "name": m_name,
                                "description": muscle_description.strip() if muscle_description else ""
                            }
                            db.db.muscles.insert_one(muscle)
                            added_count += 1
                        
                        if added_count == 1:
                            st.success(f"✅ Muscle '{muscle_names[0]}' added!")
                        else:
                            st.success(f"✅ {added_count} muscles added!")
                        st.rerun()
                    else:
                        st.error("Please enter at least one muscle name")
                else:
                    st.error("Please enter muscle name(s)")
        
        st.markdown("**All Muscles**")
        muscles = list(db.db.muscles.find())
        
        if muscles:
            df_muscles = pd.DataFrame(muscles)
            
            for idx, row in df_muscles.iterrows():
                col_a, col_b = st.columns([3, 1])
                with col_a:
                    st.write(f"**{row['name']}**")
                    if 'description' in row and row['description']:
                        st.write(f"_{row['description']}_")
                with col_b:
                    if st.button("Delete", key=f"del_m_{str(row['_id'])}"):
                        db.db.muscles.delete_one({"_id": row['_id']})
                        st.rerun()
        else:
            st.info("No muscles yet. Add some to get started!")
    
    with col2:
        st.subheader("Manage Muscle Groups")
        
        st.markdown("**Add Muscle Group**")
        with st.form("add_muscle_group"):
            name = st.text_input("Muscle Group Name*", placeholder="e.g., Arms; Legs; Chest")
            description = st.text_area("Description", placeholder="Optional description")
            
            submitted = st.form_submit_button("Add Muscle Group")
            
            if submitted:
                if name:
                    muscle_group = {
                        "name": name.strip(),
                        "description": description.strip() if description else "",
                        "muscles": []
                    }
                    db.db.muscle_groups.insert_one(muscle_group)
                    st.rerun()
                else:
                    st.error("Please enter a muscle group name")
        
        st.markdown("**All Muscle Groups**")
        
        # Get all muscles for multiselect options
        all_muscles = list(db.db.muscles.find())
        muscle_options = [muscle['name'] for muscle in all_muscles]
        muscle_dict = {muscle['name']: muscle['_id'] for muscle in all_muscles}
        reverse_muscle_dict = {str(muscle['_id']): muscle['name'] for muscle in all_muscles}
        
        muscle_groups = list(db.db.muscle_groups.find())
        
        if muscle_groups:
            df = pd.DataFrame(muscle_groups)
            
            for idx, row in df.iterrows():
                with st.expander(f"**{row['name']}**"):
                    if 'description' in row and row['description']:
                        st.write(f"**Description:** {row['description']}")
                    
                    # Current muscles in this group
                    current_muscle_ids = row.get('muscles', [])
                    current_muscle_names = [reverse_muscle_dict.get(str(mid), "Unknown") for mid in current_muscle_ids]
                    
                    st.write(f"**Current Muscles:** {', '.join(current_muscle_names) if current_muscle_names else 'None'}")
                    
                    # Multiselect to edit muscles
                    selected_muscles = st.multiselect(
                        f"Select muscles for {row['name']}",
                        options=muscle_options,
                        default=current_muscle_names,
                        key=f"edit_muscles_{str(row['_id'])}"
                    )
                    
                    if st.button(f"Update Muscles for {row['name']}", key=f"update_{str(row['_id'])}"):
                        # Convert selected names back to IDs
                        selected_ids = [muscle_dict[name] for name in selected_muscles if name in muscle_dict]
                        
                        # Update the muscle group
                        db.db.muscle_groups.update_one(
                            {"_id": row['_id']},
                            {"$set": {"muscles": selected_ids}}
                        )
                        st.success(f"✅ Muscles updated for '{row['name']}'!")
                        st.rerun()
                    
                    if st.button("Delete", key=f"del_mg_{str(row['_id'])}"):
                        db.db.muscle_groups.delete_one({"_id": row['_id']})
                        st.rerun()
        else:
            st.info("No muscle groups yet. Add some to get started!")

elif st.session_state.get("authentication_status") == False:
    st.error('Username/password is incorrect')
elif st.session_state.get("authentication_status") == None:
    st.warning('Please enter your username and password')