from copy import deepcopy
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
        current_user = db.get_user_by_username(current_username) or {}
    else:
        st.error ("Error: No username found in session state.")
        st.stop()
    role = current_user.get("role", "client") if current_user else "client"

    st.title("Manage Clients")

    if role != "coach":
        st.info("This page is for coaches to find and request clients.\n If you'd like to become a coach, please contact the administrator (bradleynaylon@yahoo.com).")

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
                        edit_mode_key = f"editing_client_session_{session_id}"
                        edit_mode = st.session_state.get(edit_mode_key, False)

                        st.subheader(session.get("name", "Untitled Session"))
                        if not edit_mode:
                            if st.button("Edit Session", key=f"edit_client_session_{session_id}", use_container_width=True):
                                st.session_state[edit_mode_key] = True
                                st.rerun()
                        else:
                            session_name = st.text_input("Session Name*", value=session.get("name", ""), key=f"client_session_name_{session_id}")
                            session_edit = {"name": session_name, "supersets": deepcopy(session.get("supersets", []))}
                            exercise_options = sorted(list(db.db.exercises.find()), key=lambda item: str(item.get("name", "")).lower())

                            for superset_idx, superset in enumerate(session_edit["supersets"]):
                                with st.container(border=True):
                                    st.markdown(f"**Superset {superset_idx + 1}**")
                                    repeats = st.number_input(
                                        "Repeat this superset",
                                        min_value=1,
                                        max_value=20,
                                        value=int(superset.get("repeats", 1)),
                                        step=1,
                                        format="%d",
                                        key=f"client_superset_repeats_{session_id}_{superset_idx}",
                                    )
                                    superset["repeats"] = int(repeats)

                                    exercises = superset.setdefault("exercises", [])
                                    for exercise_idx, exercise in enumerate(exercises):
                                        col_left, col_right = st.columns([4, 1])
                                        with col_left:
                                            exercise_names = [item.get("name", "") for item in exercise_options]
                                            chosen_name = exercise.get("name") or ""
                                            if chosen_name not in exercise_names:
                                                chosen_name = exercise_names[0] if exercise_names else ""
                                            selected_exercise_name = st.selectbox(
                                                "Exercise",
                                                options=exercise_names,
                                                index=exercise_names.index(chosen_name) if chosen_name in exercise_names else 0,
                                                key=f"client_exercise_select_{session_id}_{superset_idx}_{exercise_idx}",
                                            )
                                            exercise["name"] = selected_exercise_name
                                            selected_exercise = next((item for item in exercise_options if item.get("name") == selected_exercise_name), None)
                                            if selected_exercise:
                                                exercise["exercise_id"] = str(selected_exercise.get("_id"))
                                                exercise["metrics"] = selected_exercise.get("metrics", [])
                                        with col_right:
                                            if st.button("Remove", key=f"client_remove_exercise_{session_id}_{superset_idx}_{exercise_idx}", use_container_width=True):
                                                exercises.pop(exercise_idx)
                                                st.rerun()

                                    if st.button("Add Exercise", key=f"client_add_exercise_{session_id}_{superset_idx}", use_container_width=True):
                                        exercises.append({"exercise_id": "", "name": "", "metrics": []})
                                        st.rerun()

                            if st.button("Add Superset", key=f"client_add_superset_{session_id}", use_container_width=True):
                                session_edit["supersets"].append({"repeats": 1, "exercises": [{"exercise_id": "", "name": "", "metrics": []}]})
                                st.rerun()

                            col_save, col_cancel = st.columns(2)
                            with col_save:
                                if st.button("Save Changes", key=f"client_save_session_{session_id}", use_container_width=True):
                                    valid_supersets = []
                                    for superset in session_edit["supersets"]:
                                        exercise_rows = []
                                        for exercise in superset.get("exercises", []):
                                            if not exercise.get("name"):
                                                continue
                                            exercise_rows.append({
                                                "exercise_id": exercise.get("exercise_id", ""),
                                                "name": exercise.get("name", ""),
                                                "metrics": exercise.get("metrics", []),
                                                "instances": exercise.get("instances", [{"metrics": {}} for _ in range(int(superset.get("repeats", 1)))])
                                            })
                                        if exercise_rows:
                                            valid_supersets.append({"repeats": int(superset.get("repeats", 1)), "exercises": exercise_rows})

                                    if not session_name or not session_name.strip():
                                        st.error("Please enter a session name")
                                    elif not valid_supersets:
                                        st.error("Please add at least one exercise")
                                    else:
                                        db.db.sessions.update_one(
                                            {"_id": session.get("_id")},
                                            {"$set": {"name": session_name.strip(), "supersets": valid_supersets}},
                                        )
                                        st.session_state.pop(edit_mode_key, None)
                                        st.success("Session updated")
                                        st.rerun()
                            with col_cancel:
                                if st.button("Cancel", key=f"client_cancel_session_{session_id}", use_container_width=True):
                                    st.session_state.pop(edit_mode_key, None)
                                    st.rerun()
                else:
                    st.caption("No sessions assigned to this client yet.")
                if st.button("Remove Client", key=f"remove_client_{client_username}", use_container_width=True):
                    db.db.users.update_one({"username": current_username}, {"$pull": {"clients": client_username}})
                    db.db.users.update_one({"username": client_username}, {"$pull": {"coaches": current_username}})
                    st.success(f"{client_username} has been removed from your clients.")
                    sleep(2)
                    st.rerun()
    else:
        st.caption("No clients yet.")

    st.subheader("Pending requests sent")
    pending_requests = current_user.get("pending_client_requests", []) or []
    if pending_requests:
        for client_username in pending_requests:
            st.write(f"• {client_username}")
    else:
        st.caption("No pending requests.")