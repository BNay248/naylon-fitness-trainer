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
        name = st.text_input("Equipment Name*", placeholder="e.g., Barbell; Dumbbell; Resistance Band")
        description = st.text_area("Description", placeholder="Optional description")
        
        st.info("💡 Equipment attributes (weight ranges, adjustability, etc.) will be added in a future update")
        
        submitted = st.form_submit_button("Add Equipment")
        
        if submitted:
            if name:
                # Split by semicolons and create multiple equipment items
                equipment_names = [eq.strip() for eq in name.split(';') if eq.strip()]
                
                if equipment_names:
                    added_count = 0
                    for eq_name in equipment_names:
                        equipment_item = {
                            "name": eq_name,
                            "description": description.strip() if description else "",
                            "attributes": {}
                        }
                        db.db.equipment.insert_one(equipment_item)
                        added_count += 1
                    
                    if added_count == 1:
                        st.success(f"✅ Equipment '{equipment_names[0]}' added!")
                    else:
                        st.success(f"✅ {added_count} equipment items added!")
                    st.rerun()
                else:
                    st.error("Please enter at least one equipment name")
            else:
                st.error("Please enter equipment name(s)")
    
    st.subheader("All Equipment")
    
    equipment = list(db.db.equipment.find())
    
    if equipment:
        for item in equipment:
            with st.expander(f"🔧 {item['name']}"):
                if 'description' in item and item['description']:
                    st.write(f"**Description:** {item['description']}")
                
                # Display current characteristics
                characteristics = item.get('characteristics', {})
                if characteristics:
                    st.write("**Characteristics:**")
                    for char_name, variants in characteristics.items():
                        st.write(f"- **{char_name}:** {', '.join(variants) if isinstance(variants, list) else variants}")
                else:
                    st.write("*No characteristics defined yet*")
                
                # Add new characteristic
                st.markdown("**Add Characteristic**")
                with st.form(f"add_char_{str(item['_id'])}"):
                    char_name = st.text_input("Characteristic Name", placeholder="e.g., Weight, Type, Length")
                    char_variants = st.text_input("Variants (semicolon separated)", placeholder="e.g., 5;10;15;20;25;30")
                    
                    submitted_char = st.form_submit_button("Add Characteristic")
                    
                    if submitted_char:
                        if char_name and char_variants:
                            variants_list = [v.strip() for v in char_variants.split(';') if v.strip()]
                            
                            if not characteristics:
                                characteristics = {}
                            
                            characteristics[char_name] = variants_list
                            
                            db.db.equipment.update_one(
                                {"_id": item['_id']},
                                {"$set": {"characteristics": characteristics}}
                            )
                            st.success(f"✅ Characteristic '{char_name}' added!")
                            st.rerun()
                        else:
                            st.error("Please enter both characteristic name and variants")
                
                if st.button("Delete Equipment", key=f"del_eq_{str(item['_id'])}"):
                    db.db.equipment.delete_one({"_id": item['_id']})
                    st.success(f"✅ Equipment '{item['name']}' deleted!")
                    st.rerun()
    else:
        st.info("No equipment yet. Add some to get started!")

elif st.session_state.get("authentication_status") == False:
    st.error('Username/password is incorrect')
elif st.session_state.get("authentication_status") == None:
    st.warning('Please enter your username and password')