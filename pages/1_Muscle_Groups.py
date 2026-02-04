import streamlit as st
from db_manager import WorkoutDB
import pandas as pd
import streamlit_authenticator as stauth
import yaml
from yaml.loader import SafeLoader

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
            muscle_name = st.text_input("Muscle Name*", placeholder="e.g., Biceps, Triceps, Quadriceps")
            muscle_description = st.text_area("Description", placeholder="Optional description")
            
            submitted_muscle = st.form_submit_button("Add Muscle")
            
            if submitted_muscle:
                if muscle_name:
                    muscle = {
                        "name": muscle_name.strip(),
                        "description": muscle_description.strip() if muscle_description else ""
                    }
                    db.db.muscles.insert_one(muscle)
                    st.success(f"✅ Muscle '{muscle_name}' added!")
                    st.rerun()
                else:
                    st.error("Please enter a muscle name")
        
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
                        st.success(f"✅ Muscle '{row['name']}' deleted!")
                        st.rerun()
        else:
            st.info("No muscles yet. Add some to get started!")
    
    with col2:
        st.subheader("Manage Muscle Groups")
        
        st.markdown("**Add Muscle Group**")
        with st.form("add_muscle_group"):
            name = st.text_input("Muscle Group Name*", placeholder="e.g., Arms, Legs, Chest")
            description = st.text_area("Description", placeholder="Optional description")
            
            submitted = st.form_submit_button("Add Muscle Group")
            
            if submitted:
                if name:
                    muscle_group = {
                        "name": name.strip(),
                        "description": description.strip() if description else ""
                    }
                    db.db.muscle_groups.insert_one(muscle_group)
                    st.success(f"✅ Muscle group '{name}' added!")
                    st.rerun()
                else:
                    st.error("Please enter a muscle group name")
        
        st.markdown("**All Muscle Groups**")
        muscle_groups = list(db.db.muscle_groups.find())
        
        if muscle_groups:
            df = pd.DataFrame(muscle_groups)
            
            for idx, row in df.iterrows():
                col_a, col_b = st.columns([3, 1])
                with col_a:
                    st.write(f"**{row['name']}**")
                    if 'description' in row and row['description']:
                        st.write(f"_{row['description']}_")
                with col_b:
                    if st.button("Delete", key=f"del_mg_{str(row['_id'])}"):
                        db.db.muscle_groups.delete_one({"_id": row['_id']})
                        st.success(f"✅ Muscle group '{row['name']}' deleted!")
                        st.rerun()
        else:
            st.info("No muscle groups yet. Add some to get started!")

elif st.session_state.get("authentication_status") == False:
    st.error('Username/password is incorrect')
elif st.session_state.get("authentication_status") == None:
    st.warning('Please enter your username and password')