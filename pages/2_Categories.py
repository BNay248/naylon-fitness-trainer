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

st.set_page_config(page_title="NFP - Categories", layout="wide")

# Check authentication status from session state
if st.session_state.get("authentication_status"):
    # User is authenticated
    authenticator.logout(location='sidebar')
    st.sidebar.write(f'Welcome *{st.session_state["name"]}*')
    
    # Initialize database
    db = WorkoutDB()
    
    st.title("Manage Categories")
    
    st.subheader("Add Category")
    with st.form("add_category"):
        name = st.text_input("Category Name*", placeholder="e.g., Strength; Cardio; Mobility")
        description = st.text_area("Description", placeholder="Optional description")
        
        submitted = st.form_submit_button("Add Category")
        
        if submitted:
            if name:
                # Split by semicolons and create multiple categories
                category_names = [cat.strip() for cat in name.split(';') if cat.strip()]
                
                if category_names:
                    added_count = 0
                    for cat_name in category_names:
                        category = {
                            "name": cat_name,
                            "description": description.strip() if description else ""
                        }
                        db.db.categories.insert_one(category)
                        added_count += 1
                    st.rerun()
                else:
                    st.error("Please enter at least one category name")
            else:
                st.error("Please enter category name(s)")
    
    st.subheader("All Categories")
    
    categories = list(db.db.categories.find())
    
    if categories:
        df = pd.DataFrame(categories)
        
        for idx, row in df.iterrows():
            col_a, col_b, col_c = st.columns([3, 2, 1])
            with col_a:
                st.write(f"**{row['name']}**")
            with col_b:
                if 'description' in row and row['description']:
                    st.write(row['description'])
            with col_c:
                if st.button("Delete", key=f"del_cat_{str(row['_id'])}"):
                    db.db.categories.delete_one({"_id": row['_id']})
                    st.rerun()
    else:
        st.info("No categories yet. Add some to get started!")

elif st.session_state.get("authentication_status") == False:
    st.error('Username/password is incorrect')
elif st.session_state.get("authentication_status") == None:
    st.warning('Please enter your username and password')