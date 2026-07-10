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
    current_user = db.get_user_by_username(current_username) or {}
    role = current_user.get("role", "client")

    st.title("Manage Clients")

    if role != "coach":
        st.info("This page is for coaches to find and request clients.")
        st.subheader("Your current clients")
        current_clients = current_user.get("clients", []) or []
        if current_clients:
            for client_username in current_clients:
                st.write(f"• {client_username}")
        else:
            st.caption("No clients yet.")
        st.stop()

    st.info("Search for a client and send a request to connect.")

    search_query = st.text_input("Search by username or name", key="client_search")
    current_clients = set(current_user.get("clients", []) or [])
    pending_requests = set(current_user.get("pending_client_requests", []) or [])

    matching_clients = []
    for user in db.get_all_users():
        if user.get("username") == current_username:
            continue
        if user.get("role") != "client":
            continue

        username = user.get("username", "")
        if username in current_clients or username in pending_requests:
            continue

        name = user.get("name", "")
        query = search_query.strip().lower()
        if query and query not in username.lower() and query not in name.lower():
            continue

        matching_clients.append(user)

    if matching_clients:
        for user in matching_clients:
            username = user.get("username", "")
            name = user.get("name", "")
            col_a, col_b = st.columns([3, 1])
            with col_a:
                st.write(f"**{name}** ({username})")
            with col_b:
                if st.button("Request", key=f"request_client_{username}", use_container_width=True):
                    db.db.users.update_one({"username": username}, {"$addToSet": {"pending_coach_requests": current_username}})
                    db.db.users.update_one({"username": current_username}, {"$addToSet": {"pending_client_requests": username}})
                    st.success(f"Request sent to {username}.")
                    st.rerun()
    else:
        st.caption("No matching clients found.")

    st.subheader("Your current clients")
    current_clients = current_user.get("clients", []) or []
    if current_clients:
        for client_username in current_clients:
            st.write(f"• {client_username}")
    else:
        st.caption("No clients yet.")

    st.subheader("Pending requests sent")
    pending_requests = current_user.get("pending_client_requests", []) or []
    if pending_requests:
        for client_username in pending_requests:
            st.write(f"• {client_username}")
    else:
        st.caption("No pending requests.")