from time import sleep

import streamlit as st
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
    authenticator.logout(location='sidebar')
    st.sidebar.write(f'Welcome *{st.session_state["name"]}*')

    db = TrainerDB()
    current_username = st.session_state.get("username")
    if current_username:
        current_user = db.get_user_by_username(current_username)
    else:
        st.error ("Error: No username found in session state.")
        st.stop()

    role = current_user.get("role", "client") if current_user else "client"

    st.title("Manage Coaches")

    st.subheader("Your current coaches")
    if current_user:
        current_coaches = current_user.get("coaches", []) or []
    else:
        st.error("Error: Current user data not found.")
        st.stop()
    if current_coaches:
        col1, col2 = st.columns(2)
        for coach_username in current_coaches:
            with col1:
                st.write(f"• {coach_username}")
            with col2:
                if st.button("Remove Coach", key=f"remove_coach_{coach_username}", use_container_width=True):
                    db.db.users.update_one({"username": current_username}, {"$pull": {"coaches": coach_username}})
                    db.db.users.update_one({"username": coach_username}, {"$pull": {"clients": current_username}})
                    st.success(f"{coach_username} has been removed from your coaches.")
                    sleep(.75)
                    st.rerun()
    else:
        st.caption("No coaches yet.")
    st.stop()

    st.subheader("Coach requests")
    if current_user:
        pending_requests = current_user.get("pending_coach_requests", []) or []
    else:
        st.error("Error: Current user data not found.")
        st.stop()
    if pending_requests:
        for coach_username in pending_requests:
            coach_user = db.get_user_by_username(coach_username) or {}
            display_name = coach_user.get("name", coach_username)
            col_a, col_b, col_c = st.columns([3, 1, 1])
            with col_a:
                st.write(f"**{display_name}** ({coach_username})")
            with col_b:
                if st.button("Accept", key=f"accept_coach_{coach_username}", use_container_width=True):
                    db.db.users.update_one({"username": current_username}, {"$pull": {"pending_coach_requests": coach_username}, "$addToSet": {"coaches": coach_username}})
                    db.db.users.update_one({"username": coach_username}, {"$pull": {"pending_client_requests": current_username}, "$addToSet": {"clients": current_username}})
                    st.success(f"You are now connected with {coach_username}.")
                    st.rerun()
            with col_c:
                if st.button("Decline", key=f"decline_coach_{coach_username}", use_container_width=True):
                    db.db.users.update_one({"username": current_username}, {"$pull": {"pending_coach_requests": coach_username}})
                    db.db.users.update_one({"username": coach_username}, {"$pull": {"pending_client_requests": current_username}})
                    st.info(f"Request from {coach_username} declined.")
                    st.rerun()
    else:
        st.caption("No coach requests right now.")

    st.subheader("Your current coaches")
    current_coaches = current_user.get("coaches", []) or []
    if current_coaches:
        for coach_username in current_coaches:
            st.write(f"• {coach_username}")
    else:
        st.caption("No coaches yet.")