import streamlit as st
import bcrypt
from db_manager import TrainerDB
from auth_helper import load_config, create_authenticator, render_login_and_registration

# Must be the first Streamlit command
st.set_page_config(page_title="Naylon Fitness Portal", page_icon="NFP.jpg", layout="wide")

config = load_config()
db = TrainerDB()
authenticator = create_authenticator(config, db)
render_login_and_registration(authenticator, config, db)

if st.session_state.get("authentication_status"):
    # User is authenticated
    authenticator.logout(location='sidebar')
    st.sidebar.write(f'Welcome *{st.session_state["name"]}*')
    
    st.title("🏋️ Trainer Platform - Admin Dashboard")
    st.write("Welcome to the admin panel. Use the sidebar to navigate to different sections.")
    
    st.divider()
    
    # Password change section
    st.subheader("🔐 Change Password")
    
    col1, col2 = st.columns([1, 2])
    
    with col1:
        with st.form("change_password"):
            current_password = st.text_input("Current Password", type="password")
            new_password = st.text_input("New Password", type="password")
            confirm_password = st.text_input("Confirm New Password", type="password")
            
            submitted = st.form_submit_button("Update Password")
            
            if submitted:
                username = st.session_state["username"]
                user_record = db.get_user_by_username(username)
                if not user_record:
                    st.error("User record not found.")
                else:
                    stored_hash = user_record['password']
                    
                    # Verify current password
                    if bcrypt.checkpw(current_password.encode('utf-8'), stored_hash.encode('utf-8')):
                        # Check if new passwords match
                        if new_password == confirm_password:
                            if len(new_password) >= 6:
                                # Hash new password
                                new_hash = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
                                
                                # Update database
                                db.update_user(username, {'password': new_hash})
                                
                                st.success("✅ Password updated successfully!")
                            else:
                                st.error("New password must be at least 6 characters")
                        else:
                            st.error("New passwords don't match")
                    else:
                        st.error("Current password is incorrect")
    
    with col2:
        st.info("""
        **Password Requirements:**
        - Minimum 6 characters
        - You'll need to log in again after changing your password
        """)