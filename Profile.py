import streamlit as st
import streamlit_authenticator as stauth
import yaml
from yaml.loader import SafeLoader
import bcrypt

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
                stored_hash = config['credentials']['usernames'][username]['password']
                
                # Verify current password
                if bcrypt.checkpw(current_password.encode('utf-8'), stored_hash.encode('utf-8')):
                    # Check if new passwords match
                    if new_password == confirm_password:
                        if len(new_password) >= 6:
                            # Hash new password
                            new_hash = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
                            
                            # Update config
                            config['credentials']['usernames'][username]['password'] = new_hash
                            
                            # Save to file
                            with open('config.yaml', 'w') as file:
                                yaml.dump(config, file, default_flow_style=False)
                            
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

elif st.session_state.get("authentication_status") == False:
    st.error('Username/password is incorrect')
elif st.session_state.get("authentication_status") == None:
    st.warning('Please enter your username and password')