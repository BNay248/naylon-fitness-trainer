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

# Check authentication status from session state
if st.session_state.get("authentication_status"):
    # User is authenticated
    authenticator.logout(location='sidebar')
    st.sidebar.write(f'Welcome *{st.session_state["name"]}*')
    
    # Initialize database
    db = WorkoutDB()
    
    st.title("Manage Muscle Groups")
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.subheader("All Muscle Groups")
        
        muscle_groups = list(db.db.muscle_groups.find())
        
        if muscle_groups:
            df = pd.DataFrame(muscle_groups)
            
            for idx, row in df.iterrows():
                col_a, col_b, col_c = st.columns([3, 2, 1])
                with col_a:
                    st.write(f"**{row['name']}**")
                with col_b:
                    if 'description' in row and row['description']:
                        st.write(row['description'])
                with col_c:
                    if st.button("Delete", key=f"del_mg_{str(row['_id'])}"):
                        db.db.muscle_groups.delete_one({"_id": row['_id']})
                        st.success(f"✅ Muscle group '{row['name']}' deleted!")
                        st.rerun()
        else:
            st.info("No muscle groups yet. Add some to get started!")
    
    with col2:
        st.subheader("Add Muscle Group")
        with st.form("add_muscle_group"):
            name = st.text_input("Muscle Group Name*", placeholder="e.g., Quadriceps, Chest, Core")
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

elif st.session_state.get("authentication_status") == False:
    st.error('Username/password is incorrect')
elif st.session_state.get("authentication_status") == None:
    st.warning('Please enter your username and password')