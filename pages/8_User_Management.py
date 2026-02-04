import streamlit as st
import streamlit_authenticator as stauth
import yaml
from yaml.loader import SafeLoader
import bcrypt

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

st.set_page_config(page_title="NFP - User Management", layout="wide")

# Check authentication status from session state
if st.session_state.get("authentication_status"):
    # User is authenticated
    authenticator.logout(location='sidebar')
    st.sidebar.write(f'Welcome *{st.session_state["name"]}*')
    
    st.title("👥 User Management")
    
    st.subheader("Add New User")
    with st.form("add_user"):
        new_username = st.text_input("Username*")
        new_name = st.text_input("Full Name*")
        new_email = st.text_input("Email*")
        new_password = st.text_input("Password*", type="password")
        
        submitted = st.form_submit_button("Create User")
        
        if submitted:
            if new_username and new_name and new_email and new_password:
                if new_username in config['credentials']['usernames']:
                    st.error("Username already exists!")
                else:
                    # Hash the password
                    hashed_pw = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
                    
                    # Add to config
                    config['credentials']['usernames'][new_username] = {
                        'name': new_name,
                        'email': new_email,
                        'password': hashed_pw
                    }
                    
                    # Save to file
                    with open('config.yaml', 'w') as file:
                        yaml.dump(config, file, default_flow_style=False)
                    
                    st.success(f"✅ User '{new_username}' created!")
                    st.rerun()
            else:
                st.error("Please fill all fields")
    
    st.subheader("Current Users")
    
    users = config['credentials']['usernames']
    
    if users:
        for username, details in users.items():
            col_a, col_b = st.columns(2)
            with col_a:
                st.write(f"**{username}**")
            with col_b:
                if st.button("Delete", key=f"del_user_{username}"):
                    # Delete the user
                    del config['credentials']['usernames'][username]
                    # Save to file
                    with open('config.yaml', 'w') as file:
                        yaml.dump(config, file, default_flow_style=False)
                    st.success(f"✅ User '{username}' deleted!")
                    st.rerun()
    else:
        st.info("No users found.")

elif st.session_state.get("authentication_status") == False:
    st.error('Username/password is incorrect')
elif st.session_state.get("authentication_status") == None:
    st.warning('Please enter your username and password')