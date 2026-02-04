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

st.set_page_config(page_title="NFP - Workouts", layout="wide")

# Check authentication status from session state
if st.session_state.get("authentication_status"):
    # User is authenticated
    authenticator.logout(location='sidebar')
    st.sidebar.write(f'Welcome *{st.session_state["name"]}*')
    
    # Initialize database
    db = WorkoutDB()
    
    st.title("Manage Workouts")
    st.info("🚧 Workout management will be added after foundational data is set up")
    
    muscle_groups_count = db.db.muscle_groups.count_documents({})
    categories_count = db.db.categories.count_documents({})
    equipment_count = db.db.equipment.count_documents({})
    
    st.write("### Setup Progress")
    st.write(f"- **Muscle Groups:** {muscle_groups_count}")
    st.write(f"- **Categories:** {categories_count}")
    st.write(f"- **Equipment:** {equipment_count}")
    
    if muscle_groups_count > 0 and categories_count > 0 and equipment_count > 0:
        st.success("✅ Ready to start adding workouts!")
    else:
        st.warning("⚠️ Please add muscle groups, categories, and equipment first")

elif st.session_state.get("authentication_status") == False:
    st.error('Username/password is incorrect')
elif st.session_state.get("authentication_status") == None:
    st.warning('Please enter your username and password')