import streamlit as st
from datetime import datetime
from db_manager import TrainerDB
from auth_helper import load_config, create_authenticator, render_login_and_registration

# Page config
st.set_page_config(page_title="Naylon Fitness Portal", page_icon="NFP.jpg", layout="wide")

config = load_config()
db = TrainerDB()
authenticator = create_authenticator(config, db)
render_login_and_registration(authenticator, config, db)


def field_key(session_id, superset_idx, exercise_idx, instance_idx, metric):
    return f"{session_id}_{superset_idx}_{exercise_idx}_{instance_idx}_{metric}".replace(" ", "_").replace("-", "_")


# Check authentication status from session state
if st.session_state.get("authentication_status"):
    authenticator.logout(location='sidebar')
    st.sidebar.write(f'Welcome *{st.session_state["name"]}*')

    db = TrainerDB()
    username = st.session_state.get("username", "")

    def get_exercises():
        return sorted(list(db.db.exercises.find()), key=lambda item: str(item.get("name", "")).lower())

    def get_user_sessions():
        sessions = list(db.db.sessions.find({"user_id": username}))
        return sorted(sessions, key=lambda item: str(item.get("name", "")).lower())

    def get_previous_metrics(exercise_name, metrics, sessions):
        previous_values = {}
        for session in reversed(sessions):
            for superset in session.get("supersets", []):
                for exercise in superset.get("exercises", []):
                    if exercise.get("name") != exercise_name:
                        continue
                    for instance in exercise.get("instances", []):
                        for metric in metrics:
                            metric_value = instance.get("metrics", {}).get(metric)
                            if metric_value not in [None, "", 0]:
                                previous_values[metric] = metric_value
                        if len(previous_values) >= len(metrics):
                            return previous_values
        return previous_values

    def build_session_document(session_name, supersets):
        return {
            "name": session_name,
            "user_id": username,
            "created_at": datetime.now(),
            "supersets": supersets,
        }

    @st.fragment
    def render_create_session_form():
        with st.expander("Create New Session", expanded=False):
            st.caption("Build a session with supersets and repeated exercise rounds.")
            session_name = st.text_input("Session Name*", key=f"new_session_name_{username}")

            if "new_session_supersets" not in st.session_state:
                st.session_state["new_session_supersets"] = [{"repeats": 1, "exercises": [{"exercise_id": "", "name": "", "metrics": []}]}]

            supersets = st.session_state["new_session_supersets"]
            exercise_options = get_exercises()

            for superset_idx, superset in enumerate(supersets):
                with st.container(border=True):
                    st.markdown(f"**Superset {superset_idx + 1}**")
                    repeats = st.number_input(
                        "Repeat this superset",
                        min_value=1,
                        max_value=20,
                        value=int(superset.get("repeats", 1)),
                        key=f"new_superset_repeats_{username}_{superset_idx}",
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
                                key=f"new_exercise_select_{username}_{superset_idx}_{exercise_idx}",
                            )
                            exercise["name"] = selected_exercise_name

                            selected_exercise = next((item for item in exercise_options if item.get("name") == selected_exercise_name), None)
                            if selected_exercise:
                                exercise["exercise_id"] = str(selected_exercise.get("_id"))
                                exercise["metrics"] = selected_exercise.get("metrics", [])
                        with col_right:
                            if st.button("Remove", key=f"remove_exercise_{username}_{superset_idx}_{exercise_idx}", use_container_width=True):
                                exercises.pop(exercise_idx)
                                st.rerun(scope="fragment")

                    if st.button("Add Exercise", key=f"add_exercise_{username}_{superset_idx}", use_container_width=True):
                        exercises.append({"exercise_id": "", "name": "", "metrics": []})
                        st.rerun(scope="fragment")

                    if st.button("Remove Superset", key=f"remove_superset_{username}_{superset_idx}", use_container_width=True):
                        supersets.pop(superset_idx)
                        st.rerun(scope="fragment")

            if st.button("Add Superset", key=f"add_superset_{username}", use_container_width=True):
                supersets.append({"repeats": 1, "exercises": [{"exercise_id": "", "name": "", "metrics": []}]})
                st.rerun(scope="fragment")

            if st.button("Create Session", key=f"create_session_{username}", use_container_width=True):
                valid_supersets = []
                for superset in supersets:
                    exercise_rows = []
                    for exercise in superset.get("exercises", []):
                        if not exercise.get("name"):
                            continue
                        exercise_rows.append({
                            "exercise_id": exercise.get("exercise_id", ""),
                            "name": exercise.get("name", ""),
                            "metrics": exercise.get("metrics", []),
                            "instances": [{"metrics": {}} for _ in range(int(superset.get("repeats", 1)))],
                        })
                    if exercise_rows:
                        valid_supersets.append({"repeats": int(superset.get("repeats", 1)), "exercises": exercise_rows})

                if not session_name.strip():
                    st.error("Please enter a session name")
                elif not valid_supersets:
                    st.error("Please add at least one exercise")
                else:
                    db.db.sessions.insert_one(build_session_document(session_name.strip(), valid_supersets))
                    st.session_state.pop(f"new_session_name_{username}", None)
                    st.session_state["new_session_supersets"] = [{"repeats": 1, "exercises": [{"exercise_id": "", "name": "", "metrics": []}]}]
                    st.success("Session created")
                    st.rerun(scope="app")

    @st.fragment
    def render_session_card(session):
        session_id = str(session.get("_id"))
        with st.expander(f"{session.get('name', 'Untitled Session')}", expanded=False):
            st.caption(f"{len(session.get('supersets', []))} superset(s)")

            if st.session_state.get(f"delete_confirm_{session_id}"):
                st.warning("Delete this session?")
                col_yes, col_no = st.columns(2)
                with col_yes:
                    if st.button("Yes, delete", key=f"confirm_delete_{session_id}", use_container_width=True):
                        db.db.sessions.delete_one({"_id": session.get("_id")})
                        st.rerun(scope="app")
                with col_no:
                    if st.button("Cancel", key=f"cancel_delete_{session_id}", use_container_width=True):
                        st.session_state.pop(f"delete_confirm_{session_id}", None)
                        st.rerun(scope="fragment")
            else:
                if st.button("Delete Session", key=f"delete_{session_id}", use_container_width=True):
                    st.session_state[f"delete_confirm_{session_id}"] = True
                    st.rerun(scope="fragment")

            for superset_idx, superset in enumerate(session.get("supersets", [])):
                st.markdown(f"### Superset {superset_idx + 1}")
                st.caption(f"Repeat this superset {superset.get('repeats', 1)} time(s)")
                for exercise_idx, exercise in enumerate(superset.get("exercises", [])):
                    exercise_name = exercise.get("name", "Untitled")
                    metrics = exercise.get("metrics", [])
                    previous_metrics = get_previous_metrics(exercise_name, metrics, get_user_sessions())
                    st.markdown(f"**{exercise_name}**")
                    if previous_metrics:
                        previous_text = ", ".join([f"{metric}: {previous_metrics[metric]}" for metric in metrics if metric in previous_metrics])
                        st.caption(f"Previous: {previous_text}")

                    for instance_idx, instance in enumerate(exercise.get("instances", [])):
                        st.caption(f"Round {instance_idx + 1}")
                        instance_metrics = instance.get("metrics", {})
                        for metric in metrics:
                            current_value = instance_metrics.get(metric)
                            if current_value in [None, ""]:
                                current_value = previous_metrics.get(metric, 0)
                            widget_key = field_key(session_id, superset_idx, exercise_idx, instance_idx, metric)
                            st.number_input(
                                metric,
                                min_value=0.0,
                                value=float(current_value) if current_value not in [None, ""] else 0.0,
                                step=1.0,
                                key=widget_key,
                            )

            if st.button("Save Session", key=f"save_{session_id}", use_container_width=True):
                updated_supersets = []
                for superset_idx, superset in enumerate(session.get("supersets", [])):
                    updated_exercises = []
                    for exercise_idx, exercise in enumerate(superset.get("exercises", [])):
                        instances = []
                        for instance_idx, instance in enumerate(exercise.get("instances", [])):
                            metric_values = {}
                            for metric in exercise.get("metrics", []):
                                widget_key = field_key(session_id, superset_idx, exercise_idx, instance_idx, metric)
                                metric_values[metric] = st.session_state.get(widget_key, instance.get("metrics", {}).get(metric, 0))
                            instances.append({"metrics": metric_values})
                        updated_exercises.append({
                            "exercise_id": exercise.get("exercise_id", ""),
                            "name": exercise.get("name", ""),
                            "metrics": exercise.get("metrics", []),
                            "instances": instances,
                        })
                    updated_supersets.append({
                        "repeats": superset.get("repeats", 1),
                        "exercises": updated_exercises,
                    })
                db.db.sessions.update_one({"_id": session.get("_id")}, {"$set": {"supersets": updated_supersets}})
                st.success("Session saved")
                st.rerun(scope="app")

    st.title("Training Sessions")
    st.info("Build your weekly workout flow with supersets and repeat-based exercise rounds.")
    render_create_session_form()

    st.subheader("Your Sessions")
    user_sessions = get_user_sessions()
    if not user_sessions:
        st.caption("No sessions yet. Create your first one above.")
    else:
        for session in user_sessions:
            render_session_card(session)