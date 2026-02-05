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

st.set_page_config(page_title="NFP - Equipment", layout="wide")

# Check authentication status from session state
if st.session_state.get("authentication_status"):
    # User is authenticated
    authenticator.logout(location='sidebar')
    st.sidebar.write(f'Welcome *{st.session_state["name"]}*')
    
    # Initialize database
    db = TrainerDB()

    @st.cache_data(show_spinner=False)
    def get_equipment():
        return list(db.db.equipment.find())
    
    st.title("Manage Equipment")
    
    @st.fragment
    def add_equipment_form():
        st.subheader("Add Equipment")
        with st.container(border=True):
            name = st.text_input("Equipment Name*", placeholder="e.g., Barbell; Dumbbell; Resistance Band", key="add_equipment_name")
            description = st.text_area("Description", placeholder="Optional description", key="add_equipment_description")
            
            if st.button("Add Equipment", key="submit_equipment"):
                if name:
                    # Split by semicolons and create multiple equipment items
                    equipment_names = [eq.strip() for eq in name.split(';') if eq.strip()]
                    
                    if equipment_names:
                        for eq_name in equipment_names:
                            equipment_item = {
                                "name": eq_name,
                                "description": description.strip() if description else "",
                                "characteristics": {}
                            }
                            db.db.equipment.insert_one(equipment_item)
                        get_equipment.clear()
                        st.rerun(scope="app")
                    else:
                        st.error("Please enter at least one equipment name")
                else:
                    st.error("Please enter equipment name(s)")

    add_equipment_form()
    
    st.subheader("All Equipment")
    
    equipment = get_equipment()
    
    if equipment:
        for item in equipment:
            @st.fragment
            def edit_equipment_fragment(eq=item):
                with st.expander(f"🔧 {eq['name']}"):
                    if 'description' in eq and eq['description']:
                        st.write(f"**Description:** {eq['description']}")
                    
                    # Display current characteristics
                    characteristics = eq.get('characteristics', {})
                    if characteristics:
                        st.write("**Characteristics:**")
                        for char_name, char_data in characteristics.items():
                            col1, col2 = st.columns([4, 1])
                            with col1:
                                if isinstance(char_data, dict):
                                    char_type = char_data.get('type', 'variant')
                                    if char_type == 'numeric':
                                        st.write(f"- **{char_name}:** Numeric (value entered in exercises)")
                                    else:  # variant
                                        variants = char_data.get('variants', [])
                                        st.write(f"- **{char_name}:** {', '.join(variants)}")
                                else:
                                    # Legacy format - assume variant
                                    st.write(f"- **{char_name}:** {', '.join(char_data) if isinstance(char_data, list) else char_data}")
                            with col2:
                                if st.button("🗑️", key=f"del_char_{str(eq['_id'])}_{char_name}", help=f"Delete {char_name}"):
                                    del characteristics[char_name]
                                    db.db.equipment.update_one(
                                        {"_id": eq["_id"]},
                                        {"$set": {"characteristics": characteristics}}
                                    )
                                    get_equipment.clear()
                                    st.rerun(scope="app")
                    else:
                        st.write("*No characteristics defined yet*")
                    
                    # Add new characteristic
                    st.markdown("**Add Characteristic**")
                    with st.container(border=True):
                        char_name = st.text_input("Characteristic Name", placeholder="e.g., Weight, Type, Length", key=f"char_name_{eq['_id']}")
                        char_type = st.selectbox("Data Type", ["Numeric", "Variant"], help="Numeric: Enter value in exercises | Variant: Choose from predefined options", key=f"char_type_{eq['_id']}")
                        
                        if char_type == "Variant":
                            char_variants = st.text_input("Variants (semicolon separated)", placeholder="e.g., Straight; Curved; EZ-Curl", key=f"char_variants_{eq['_id']}")
                        
                        if st.button("Add Characteristic", key=f"add_char_{eq['_id']}"):
                            if char_name:
                                if not characteristics:
                                    characteristics = {}
                                
                                if char_type == "Numeric":
                                    # For numeric, just store the name with type
                                    characteristics[char_name] = {"type": "numeric"}
                                else:  # Variant
                                    char_variants = st.session_state.get(f"char_variants_{eq['_id']}", "")
                                    if char_variants:
                                        variants_list = [v.strip() for v in char_variants.split(';') if v.strip()]
                                        characteristics[char_name] = {
                                            "type": "variant",
                                            "variants": variants_list
                                        }
                                    else:
                                        st.error("Please enter variants for variant type")
                                        st.stop()
                                
                                db.db.equipment.update_one(
                                    {"_id": eq["_id"]},
                                    {"$set": {"characteristics": characteristics}}
                                )
                                get_equipment.clear()
                                st.rerun(scope="app")
                            else:
                                st.error("Please enter characteristic name")
                    
                    if st.button("Delete Equipment", key=f"del_eq_{str(eq['_id'])}", width="stretch"):
                        equipment_name = eq['name']
                        # Remove this equipment from all exercises
                        db.db.exercises.update_many(
                            {"equipment": equipment_name},
                            {"$pull": {"equipment": equipment_name}}
                        )
                        # Then delete the equipment
                        db.db.equipment.delete_one({"_id": eq["_id"]})
                        get_equipment.clear()
                        st.rerun(scope="app")
            
            edit_equipment_fragment()
    else:
        st.info("No equipment yet. Add some to get started!")

elif st.session_state.get("authentication_status") == False:
    st.error('Username/password is incorrect')
elif st.session_state.get("authentication_status") == None:
    st.warning('Please enter your username and password')