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

        role_value = user.get("role")
        if role_value == "coach":
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
            client_user = db.get_user_by_username(client_username) or {}
            with st.expander(f"{client_user.get('name', client_username)} ({client_username})"):
                client_sessions = list(db.db.sessions.find({"assigned_to": client_username, "coach_username": current_username}))
                if client_sessions:
                    for session in sorted(client_sessions, key=lambda item: str(item.get("name", "")).lower()):
                        session_id = str(session.get("_id"))
                        st.subheader(session.get("name", "Untitled Session"))
                        for superset_idx, superset in enumerate(session.get("supersets", [])):
                            with st.container(border=True):
                                st.markdown(f"**Superset {superset_idx + 1}**")
                                for exercise_idx, exercise in enumerate(superset.get("exercises", [])):
                                    exercise_name = exercise.get("name", "Untitled")
                                    metrics = exercise.get("metrics", [])
                                    st.markdown(f"**{exercise_name}**")
                                    for instance_idx, instance in enumerate(exercise.get("instances", [])):
                                        instance_metrics = instance.get("metrics", {})
                                        if metrics:
                                            cols = st.columns(len(metrics))
                                            for col_idx, metric in enumerate(metrics):
                                                widget_key = f"coach_edit_{client_username}_{session_id}_{superset_idx}_{exercise_idx}_{instance_idx}_{metric}"
                                                with cols[col_idx]:
                                                    current_value = instance_metrics.get(metric, 0)
                                                    updated_value = st.number_input(
                                                        metric,
                                                        min_value=0,
                                                        value=int(current_value) if current_value not in [None, ""] else 0,
                                                        step=1,
                                                        format="%d",
                                                        key=widget_key,
                                                    )
                                                    instance_metrics[metric] = int(updated_value)
                                    st.caption("")
                        if st.button("Save Session", key=f"save_client_session_{session_id}", use_container_width=True):
                            db.db.sessions.update_one({"_id": session.get("_id")}, {"$set": {"supersets": session.get("supersets", [])}})
                            st.success(f"Saved {session.get('name', 'session')}")
                            st.rerun()
                else:
                    st.caption("No sessions assigned to this client yet.")
    else:
        st.caption("No clients yet.")

    st.subheader("Pending requests sent")
    pending_requests = current_user.get("pending_client_requests", []) or []
    if pending_requests:
        for client_username in pending_requests:
            st.write(f"• {client_username}")
    else:
        st.caption("No pending requests.")