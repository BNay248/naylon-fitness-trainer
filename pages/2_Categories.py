import streamlit as st
from db_manager import TrainerDB
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
    db = TrainerDB()

    @st.cache_data(show_spinner=False)
    def get_categories():
        return list(db.db.categories.find())
    
    st.title("Manage Categories")
    
    @st.fragment
    def add_category_form():
        st.subheader("Add Category")
        with st.container(border=True):
            name = st.text_input("Category Name*", placeholder="e.g., Strength; Cardio; Mobility", key="add_category_name")
            description = st.text_area("Description", placeholder="Optional description", key="add_category_description")
            
            if st.button("Add Category", key="submit_category"):
                if name:
                    # Split by semicolons and create multiple categories
                    category_names = [cat.strip() for cat in name.split(';') if cat.strip()]
                    
                    if category_names:
                        for cat_name in category_names:
                            category = {
                                "name": cat_name,
                                "description": description.strip() if description else ""
                            }
                            db.db.categories.insert_one(category)
                        get_categories.clear()
                        st.rerun(scope="app")
                    else:
                        st.error("Please enter at least one category name")
                else:
                    st.error("Please enter category name(s)")

    add_category_form()
    
    st.subheader("All Categories")
    
    categories = get_categories()
    
    if categories:
        for category in categories:
            col_delete, col_name = st.columns([1, 5])
            with col_delete:
                if st.button("🗑️", key=f"delete_category_{category['_id']}", help="Delete category"):
                    category_name = category['name']
                    # Remove this category from all exercises
                    db.db.exercises.update_many(
                        {"categories": category_name},
                        {"$pull": {"categories": category_name}}
                    )
                    # Then delete the category
                    db.db.categories.delete_one({"_id": category["_id"]})
                    get_categories.clear()
                    st.rerun(scope="app")
            with col_name:
                st.write(f"**{category['name']}**")
                if 'description' in category and category['description']:
                    st.write(f"_{category['description']}_")
    else:
        st.info("No categories yet. Add some to get started!")

elif st.session_state.get("authentication_status") == False:
    st.error('Username/password is incorrect')
elif st.session_state.get("authentication_status") == None:
    st.warning('Please enter your username and password')