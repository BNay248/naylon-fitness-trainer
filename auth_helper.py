import os
from time import sleep

import bcrypt
import streamlit as st
import streamlit_authenticator as stauth
import yaml
from yaml.loader import SafeLoader
from db_manager import TrainerDB

CONFIG_PATH = "config.yaml"


def load_config():
    if not os.path.exists(CONFIG_PATH):
        raise FileNotFoundError(f"{CONFIG_PATH} not found.")

    with open(CONFIG_PATH) as file:
        config = yaml.load(file, Loader=SafeLoader)

    if 'cookie' not in config:
        config['cookie'] = {'name': '', 'key': '', 'expiry_days': 30}

    return config


def save_config(config):
    with open(CONFIG_PATH, 'w') as file:
        yaml.dump(config, file, default_flow_style=False, sort_keys=False)


def build_user_credentials(db: TrainerDB):
    usernames = {}
    for user in db.get_all_users():
        username = user.get('username')
        password = user.get('password')
        if username and password:
            usernames[username] = {
                'name': user.get('name', ''),
                'email': user.get('email', ''),
                'password': password
            }
    return {'usernames': usernames}


def create_authenticator(config, db=None):
    if db is None:
        db = TrainerDB()

    return stauth.Authenticate(
        build_user_credentials(db),
        config['cookie']['name'],
        config['cookie']['key'],
        config['cookie']['expiry_days']
    )


def render_login_and_registration(authenticator, config, db=None):
    if db is None:
        db = TrainerDB()

    authenticator.login()

    if st.session_state.get("authentication_status") is not True:
        with st.expander("New here? Register an account", expanded=False):
            with st.form("register_user"):
                reg_username = st.text_input("Username*", key="register_username")
                reg_name = st.text_input("Full Name*", key="register_name")
                reg_email = st.text_input("Email*", key="register_email")
                reg_password = st.text_input("Password*", type="password", key="register_password")
                reg_confirm = st.text_input("Confirm Password*", type="password", key="register_password_confirm")
                submitted = st.form_submit_button("Create Account")

                if submitted:
                    if not reg_username or not reg_name or not reg_email or not reg_password or not reg_confirm:
                        st.error("Please fill all fields")
                    elif db.get_user_by_username(reg_username):
                        st.error("Username already exists!")
                    elif reg_password != reg_confirm:
                        st.error("Passwords do not match")
                    elif len(reg_password) < 6:
                        st.error("Password must be at least 6 characters")
                    else:
                        hashed_pw = bcrypt.hashpw(reg_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
                        db.add_user({
                            'username': reg_username,
                            'name': reg_name,
                            'email': reg_email,
                            'password': hashed_pw,
                            'role': 'client'
                        })
                        st.success("Registration complete. Please log in with your new credentials.")
                        sleep(3)
                        st.rerun()

    if st.session_state.get("authentication_status") is False:
        st.error("Username/password is incorrect")
    elif st.session_state.get("authentication_status") is None:
        st.warning("Please enter your username and password")
