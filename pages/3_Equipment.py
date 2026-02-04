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

st.set_page_config(page_title="NFP - Equipment", layout="wide")

# Check authentication status from session state
if st.session_state.get("authentication_status"):
    # User is authenticated
    authenticator.logout(location='sidebar')
    st.sidebar.write(f'Welcome *{st.session_state["name"]}*')
    
    # Initialize database
    db = WorkoutDB()
    
    st.title("Manage Equipment")
    
    st.subheader("Add Equipment")
    with st.form("add_equipment"):
        name = st.text_input("Equipment Name*", placeholder="e.g., Barbell, Dumbbell, Resistance Band")
        description = st.text_area("Description", placeholder="Optional description")
        
        st.info("💡 Equipment attributes (weight ranges, adjustability, etc.) will be added in a future update")
        
        submitted = st.form_submit_button("Add Equipment")
        
        if submitted:
            if name:
                equipment_item = {
                    "name": name.strip(),
                    "description": description.strip() if description else "",
                    "attributes": {}
                }
                db.db.equipment.insert_one(equipment_item)
                st.success(f"✅ Equipment '{name}' added!")
                st.rerun()
            else:
                st.error("Please enter equipment name")
    
    st.subheader("All Equipment")
    
    equipment = list(db.db.equipment.find())
    
    if equipment:
        for item in equipment:
            with st.expander(f"🔧 {item['name']}"):
                if 'description' in item and item['description']:
                    st.write(f"**Description:** {item['description']}")
                
                st.write("*Attributes coming soon...*")
                
                if st.button("Delete", key=f"del_eq_{str(item['_id'])}"):
                    db.db.equipment.delete_one({"_id": item['_id']})
                    st.success(f"✅ Equipment '{item['name']}' deleted!")
                    st.rerun()
    else:
        st.info("No equipment yet. Add some to get started!")

elif st.session_state.get("authentication_status") == False:
    st.error('Username/password is incorrect')
elif st.session_state.get("authentication_status") == None:
    st.warning('Please enter your username and password')