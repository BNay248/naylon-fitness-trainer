import streamlit as st
from db_manager import WorkoutDB
import pandas as pd
import streamlit_authenticator as stauth
import yaml
from yaml.loader import SafeLoader

# Must be the first Streamlit command
st.set_page_config(page_title="Trainer Platform - Admin", layout="wide")

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
    
    st.title("🏋️ Trainer Platform - Admin Setup")
    
    # Sidebar navigation
    page = st.sidebar.selectbox("Navigation", [
        "Muscle Groups",
        "Categories", 
        "Equipment",
        "Workouts",
        "Clients",
        "Coaches",
        "Sessions"
    ])
    
    # ==================== MUSCLE GROUPS PAGE ====================
    if page == "Muscle Groups":
        st.header("Manage Muscle Groups")
        
        col1, col2 = st.columns([2, 1])
        
        with col1:
            st.subheader("All Muscle Groups")
            
            # Get or create muscle groups collection
            muscle_groups = list(db.db.muscle_groups.find())
            
            if muscle_groups:
                df = pd.DataFrame(muscle_groups)
                if '_id' in df.columns:
                    df['_id'] = df['_id'].astype(str)
                
                # Add delete buttons
                for idx, row in df.iterrows():
                    col_a, col_b, col_c = st.columns([3, 2, 1])
                    with col_a:
                        st.write(f"**{row['name']}**")
                    with col_b:
                        if 'description' in row and row['description']:
                            st.write(row['description'])
                    with col_c:
                        if st.button("Delete", key=f"del_mg_{row['_id']}"):
                            db.db.muscle_groups.delete_one({"_id": row['_id']})
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
    
    # ==================== CATEGORIES PAGE ====================
    elif page == "Categories":
        st.header("Manage Categories")
        
        col1, col2 = st.columns([2, 1])
        
        with col1:
            st.subheader("All Categories")
            
            categories = list(db.db.categories.find())
            
            if categories:
                df = pd.DataFrame(categories)
                if '_id' in df.columns:
                    df['_id'] = df['_id'].astype(str)
                
                for idx, row in df.iterrows():
                    col_a, col_b, col_c = st.columns([3, 2, 1])
                    with col_a:
                        st.write(f"**{row['name']}**")
                    with col_b:
                        if 'description' in row and row['description']:
                            st.write(row['description'])
                    with col_c:
                        if st.button("Delete", key=f"del_cat_{row['_id']}"):
                            db.db.categories.delete_one({"_id": row['_id']})
                            st.rerun()
            else:
                st.info("No categories yet. Add some to get started!")
        
        with col2:
            st.subheader("Add Category")
            with st.form("add_category"):
                name = st.text_input("Category Name*", placeholder="e.g., Strength, Cardio, Mobility")
                description = st.text_area("Description", placeholder="Optional description")
                
                submitted = st.form_submit_button("Add Category")
                
                if submitted:
                    if name:
                        category = {
                            "name": name.strip(),
                            "description": description.strip() if description else ""
                        }
                        db.db.categories.insert_one(category)
                        st.success(f"✅ Category '{name}' added!")
                        st.rerun()
                    else:
                        st.error("Please enter a category name")
    
    # ==================== EQUIPMENT PAGE ====================
    elif page == "Equipment":
        st.header("Manage Equipment")
        
        col1, col2 = st.columns([2, 1])
        
        with col1:
            st.subheader("All Equipment")
            
            equipment = list(db.db.equipment.find())
            
            if equipment:
                for item in equipment:
                    with st.expander(f"🔧 {item['name']}"):
                        if 'description' in item and item['description']:
                            st.write(f"**Description:** {item['description']}")
                        
                        # Placeholder for attributes - we'll add this later
                        st.write("*Attributes coming soon...*")
                        
                        if st.button("Delete", key=f"del_eq_{item['_id']}"):
                            db.db.equipment.delete_one({"_id": item['_id']})
                            st.rerun()
            else:
                st.info("No equipment yet. Add some to get started!")
        
        with col2:
            st.subheader("Add Equipment")
            with st.form("add_equipment"):
                name = st.text_input("Equipment Name*", placeholder="e.g., Barbell, Dumbbell, Resistance Band")
                description = st.text_area("Description", placeholder="Optional description")
                
                # Placeholder for future attributes
                st.info("💡 Equipment attributes (weight ranges, adjustability, etc.) will be added in a future update")
                
                submitted = st.form_submit_button("Add Equipment")
                
                if submitted:
                    if name:
                        equipment_item = {
                            "name": name.strip(),
                            "description": description.strip() if description else "",
                            "attributes": {}  # Placeholder for future attributes
                        }
                        db.db.equipment.insert_one(equipment_item)
                        st.success(f"✅ Equipment '{name}' added!")
                        st.rerun()
                    else:
                        st.error("Please enter equipment name")
    
    # ==================== WORKOUTS PAGE ====================
    elif page == "Workouts":
        st.header("Manage Workouts")
        st.info("🚧 Workout management will be added after foundational data is set up")
        
        # Show what's available
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
    
    # ==================== CLIENTS PAGE ====================
    elif page == "Clients":
        st.header("Manage Clients")
        st.info("🚧 Client management coming soon")
    
    # ==================== COACHES PAGE ====================
    elif page == "Coaches":
        st.header("Manage Coaches")
        st.info("🚧 Coach management coming soon")
    
    # ==================== SESSIONS PAGE ====================
    elif page == "Sessions":
        st.header("Training Sessions")
        st.info("🚧 Session management coming soon")

elif st.session_state.get("authentication_status") == False:
    st.error('Username/password is incorrect')
elif st.session_state.get("authentication_status") == None:
    st.warning('Please enter your username and password')