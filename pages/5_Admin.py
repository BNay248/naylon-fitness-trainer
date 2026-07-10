import streamlit as st
import bcrypt
from db_manager import TrainerDB
from auth_helper import load_config, create_authenticator, render_login_and_registration

# Page config
st.set_page_config(page_title="Naylon Fitness Portal", page_icon="NFP.jpg", layout="wide")

config = load_config()
db = TrainerDB()
authenticator = create_authenticator(config, db)
render_login_and_registration(authenticator, config, db)

# Check authentication status from session state
if st.session_state.get("authentication_status"):
    if st.session_state.get("username") != "brad":
        st.sidebar.write(f'Welcome *{st.session_state["name"]}*')
        st.error("Access denied. This page is only available to the administrator.")
        st.stop()

    st.sidebar.write(f'Welcome *{st.session_state["name"]}*')
    
    st.title("👥 User Management")
    
    st.subheader("Add New User")
    with st.form("add_user"):
        new_username = st.text_input("Username*")
        new_name = st.text_input("Full Name*")
        new_email = st.text_input("Email*")
        new_password = st.text_input("Password*", type="password")
        create_as_coach = st.toggle("Create as coach", value=False, help="Turn this on to create a coach account instead of a client account.")
        
        submitted = st.form_submit_button("Create User")
        
        if submitted:
            if new_username and new_name and new_email and new_password:
                if db.get_user_by_username(new_username):
                    st.error("Username already exists!")
                else:
                    hashed_pw = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
                    role = "coach" if create_as_coach else "client"
                    base_user_data = {
                        'username': new_username,
                        'name': new_name,
                        'email': new_email,
                        'password': hashed_pw,
                        'role': role
                    }
                    db.add_user(base_user_data)

                    if create_as_coach:
                        db.add_coach({
                            'username': new_username,
                            'name': new_name,
                            'email': new_email,
                            'role': role
                        })
                    else:
                        db.add_client({
                            'username': new_username,
                            'name': new_name,
                            'email': new_email,
                            'role': role
                        })

                    st.success(f"User created successfully as a {role}.")
                    st.rerun()
            else:
                st.error("Please fill all fields")
    
    st.subheader("Current Users")
    
    users = db.get_all_users()
    
    if users:
        for user in users:
            username = user.get('username')
            col_a, col_b = st.columns(2)
            with col_a:
                st.write(f"**{username}**")
            with col_b:
                if st.button("Delete", key=f"del_user_{username}"):
                    if isinstance(username, str):
                        db.delete_user_by_username(username)
                        st.success(f"User '{username}' deleted.")
                        st.rerun()
    else:
        st.info("No users found.")