import re
from copy import deepcopy
from time import sleep
import streamlit as st
import streamlit.components.v1 as components
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


def normalize_youtube_url(value):
    if not isinstance(value, str) or not value.strip():
        return None

    match = re.search(r"(?:youtube\.com\/(?:watch\?v=|embed\/|shorts\/)|youtu\.be\/)([A-Za-z0-9_-]{11})", value)
    if match:
        return f"https://www.youtube.com/embed/{match.group(1)}"
    return None


def get_exercise_video_url(exercise):
    exercise_details = None
    exercise_id = exercise.get("exercise_id")
    if exercise_id:
        exercise_details = db.get_exercise(exercise_id)

    if not exercise_details and exercise.get("name"):
        exercise_details = db.db.exercises.find_one({"name": exercise.get("name")})

    if not exercise_details:
        return None

    for field in ["video_url", "video_link", "youtube_url", "url", "link"]:
        value = exercise_details.get(field)
        if isinstance(value, str) and value.strip():
            return normalize_youtube_url(value)

    instructions = exercise_details.get("instructions", "")
    if isinstance(instructions, str):
        return normalize_youtube_url(instructions)

    return None


def coerce_int(value):
    if value is None or value == "":
        return 0
    return int(value)


def build_session_text(session):
    lines = [session.get("name", "Untitled Session")]
    for superset_idx, superset in enumerate(session.get("supersets", [])):
        exercises = superset.get("exercises", [])
        repeat_count = max(
            int(superset.get("repeats", 1)),
            max((len(exercise.get("instances", [])) for exercise in exercises), default=1),
        )
        lines.append(f"\nSuperset {superset_idx + 1} ({repeat_count} round(s)):")
        for exercise in exercises:
            exercise_name = exercise.get("name", "Untitled")
            # metrics = exercise.get("metrics", [])
            # instances = exercise.get("instances", [])
            lines.append(f"  {exercise_name}")
            # for repeat_idx in range(repeat_count):
            #     instance = instances[repeat_idx] if repeat_idx < len(instances) else {"metrics": {}}
            #     instance_metrics = instance.get("metrics", {})
            #     if metrics:
            #         values = ", ".join(f"{metric}: {instance_metrics.get(metric, 0)}" for metric in metrics)
            #     else:
            #         values = "no metrics configured"
            #     lines.append(f"    Round {repeat_idx + 1}: {values}")
    return "\n".join(lines)


def get_streamlit_button_theme():
    base = (st.get_option("theme.base") or "light").lower()
    primary_color = st.get_option("theme.primaryColor") or "#ff4b4b"
    background_color = st.get_option("theme.backgroundColor")
    text_color = st.get_option("theme.textColor")
    if base == "dark":
        background_color = background_color or "#0e1117"
        text_color = text_color or "#fafafa"
        border_color = "rgba(250, 250, 250, 0.2)"
    else:
        background_color = background_color or "#ffffff"
        text_color = text_color or "#31333f"
        border_color = "rgba(49, 51, 63, 0.2)"
    return background_color, text_color, border_color, primary_color


def render_copy_to_clipboard_button(session_id, text):
    import json

    escaped_text = json.dumps(text)
    button_id = f"copy_btn_{session_id}"
    background_color, text_color, border_color, primary_color = get_streamlit_button_theme()
    components.html(
        f"""
        <div style="width:100%; font-family:'Source Sans Pro', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;">
            <button id="{button_id}" style="
                width:100%;
                min-height:2.5rem;
                padding:0.25rem 0.75rem;
                border-radius:0.5rem;
                border:1px solid {border_color};
                background-color:{background_color};
                color:{text_color};
                font-family:inherit;
                font-size:1rem;
                font-weight:400;
                line-height:1.6;
                cursor:pointer;
                transition:color 0.2s, border-color 0.2s;
            ">Copy to Clipboard</button>
            <script>
                const btn = document.getElementById("{button_id}");
                const text = {escaped_text};
                const primaryColor = "{primary_color}";
                const defaultBorder = "{border_color}";
                const defaultColor = "{text_color}";
                btn.addEventListener("mouseenter", () => {{
                    btn.style.borderColor = primaryColor;
                    btn.style.color = primaryColor;
                }});
                btn.addEventListener("mouseleave", () => {{
                    btn.style.borderColor = defaultBorder;
                    btn.style.color = defaultColor;
                }});
                btn.addEventListener("click", async () => {{
                    let copied = false;
                    try {{
                        await navigator.clipboard.writeText(text);
                        copied = true;
                    }} catch (err) {{
                        try {{
                            const textarea = document.createElement("textarea");
                            textarea.value = text;
                            textarea.style.position = "fixed";
                            textarea.style.opacity = "0";
                            document.body.appendChild(textarea);
                            textarea.focus();
                            textarea.select();
                            copied = document.execCommand("copy");
                            document.body.removeChild(textarea);
                        }} catch (fallbackErr) {{
                            copied = false;
                        }}
                    }}
                    const originalText = btn.textContent;
                    btn.textContent = copied ? "Copied!" : "Copy failed";
                    setTimeout(() => {{ btn.textContent = originalText; }}, 1500);
                }});
            </script>
        </div>
        """,
        height=48,
    )


# Check authentication status from session state
if st.session_state.get("authentication_status"):
    authenticator.logout(location='sidebar')
    st.sidebar.write(f'Welcome *{st.session_state["name"]}*')

    db = TrainerDB()
    username = st.session_state.get("username", "")
    current_user = db.get_user_by_username(username) or {}
    current_role = current_user.get("role", "client")
    accepted_clients = [client for client in (current_user.get("clients", []) or []) if isinstance(client, str) and client]

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

    def build_session_document(session_name, supersets, assigned_to=None):
        target_user_id = assigned_to or username
        document = {
            "name": session_name,
            "user_id": target_user_id,
            "coach_username": username,
            "created_at": datetime.now(),
            "supersets": supersets,
        }
        if assigned_to:
            document["assigned_to"] = assigned_to
        return document

    @st.fragment
    def render_create_session_form():
        with st.expander("Create New Session", expanded=False):
            st.caption("Build a session with supersets and repeated exercise rounds.")
            session_name = st.text_input("Session Name*", key=f"new_session_name_{username}")

            assigned_client = ""
            if current_role == "coach":
                if accepted_clients:
                    assigned_client = st.selectbox(
                        "Assign to client (optional)",
                        options=[""] + accepted_clients,
                        format_func=lambda value: "Myself" if not value else value,
                        key=f"assign_client_{username}",
                    )
                else:
                    st.caption("No accepted clients yet.")

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
                        step=1,
                        format="%d",
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
                    db.db.sessions.insert_one(build_session_document(session_name.strip(), valid_supersets, assigned_client or None))
                    st.session_state.pop(f"new_session_name_{username}", None)
                    st.session_state["new_session_supersets"] = [{"repeats": 1, "exercises": [{"exercise_id": "", "name": "", "metrics": []}]}]
                    st.success("Session created")
                    st.rerun(scope="app")

    @st.fragment
    def render_session_card(session, coach_view: bool = False):
        session_id = str(session.get("_id"))
        edit_mode = st.session_state.get(f"editing_session_{session_id}", False)

        @st.fragment
        def render_superset_content(superset_idx, superset):
            with st.expander(f"Superset {superset_idx + 1} • {superset.get('repeats', 1)} round(s)", expanded=False):
                st.caption(f"Repeat this superset {superset.get('repeats', 1)} time(s)")
                exercises = superset.get("exercises", [])
                repeat_count = max(int(superset.get("repeats", 1)), max((len(exercise.get("instances", [])) for exercise in exercises), default=1))

                for repeat_idx in range(repeat_count):
                    if repeat_idx > 0:
                        st.divider()
                    st.markdown(f"***Repeat {repeat_idx + 1}***")
                    for exercise_idx, exercise in enumerate(exercises):
                        exercise_name = exercise.get("name", "Untitled")
                        metrics = exercise.get("metrics", [])
                        previous_metrics = get_previous_metrics(exercise_name, metrics, get_user_sessions())
                        st.markdown(f"**{exercise_name}**")
                        if previous_metrics:
                            previous_text = ", ".join([f"{metric}: {previous_metrics[metric]}" for metric in metrics if metric in previous_metrics])
                            st.caption(f"Previous: {previous_text}")

                        video_url = get_exercise_video_url(exercise)
                        if show_videos and video_url:
                            st.caption("Demo video")
                            components.iframe(video_url, width=560, height=315, scrolling=False)

                        instances = exercise.get("instances", [])
                        instance = instances[repeat_idx] if repeat_idx < len(instances) else {"metrics": {}}
                        instance_metrics = instance.get("metrics", {})
                        if metrics:
                            cols = st.columns(len(metrics))
                            for col_idx, metric in enumerate(metrics):
                                current_value = instance_metrics.get(metric)
                                if current_value in [None, ""]:
                                    current_value = previous_metrics.get(metric, 0)
                                numeric_value = coerce_int(current_value)
                                widget_key = field_key(session_id, superset_idx, exercise_idx, repeat_idx, metric)
                                with cols[col_idx]:
                                    st.number_input(
                                        metric,
                                        min_value=0,
                                        value=numeric_value,
                                        step=1,
                                        format="%d",
                                        key=widget_key,
                                    )
                        else:
                            st.caption("No metrics configured for this exercise")

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
                button_col_1, button_col_2 = st.columns([1, 1])
                with button_col_1:
                    if st.button("Edit Session" if not edit_mode else "Stop Editing", key=f"edit_{session_id}", use_container_width=True):
                        if edit_mode:
                            st.session_state.pop(f"editing_session_{session_id}", None)
                            st.session_state.pop(f"session_edit_{session_id}", None)
                        else:
                            st.session_state[f"editing_session_{session_id}"] = True
                            st.session_state[f"session_edit_{session_id}"] = deepcopy(session)
                        st.rerun(scope="fragment")
                with button_col_2:
                    if not coach_view:
                        if st.button("Delete Session", key=f"delete_{session_id}", use_container_width=True):
                            st.session_state[f"delete_confirm_{session_id}"] = True
                            st.rerun(scope="fragment")

                render_copy_to_clipboard_button(session_id, build_session_text(session))

            show_videos = st.session_state.get(f"show_videos_toggle_{session_id}", False)
            if not edit_mode:
                show_videos = st.checkbox("Show videos", value=show_videos, key=f"show_videos_toggle_{session_id}")

            if edit_mode:
                session_edit = st.session_state.setdefault(f"session_edit_{session_id}", deepcopy(session))
                session_name = st.text_input("Session Name*", value=session_edit.get("name", ""), key=f"edit_session_name_{session_id}")
                session_edit["name"] = session_name

                exercise_options = get_exercises()
                supersets = session_edit.setdefault("supersets", [])
                for superset_idx, superset in enumerate(supersets):
                    with st.container(border=True):
                        st.markdown(f"**Superset {superset_idx + 1}**")
                        repeats = st.number_input(
                            "Repeat this superset",
                            min_value=1,
                            max_value=20,
                            value=int(superset.get("repeats", 1)),
                            step=1,
                            format="%d",
                            key=f"edit_superset_repeats_{session_id}_{superset_idx}",
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
                                    key=f"edit_exercise_select_{session_id}_{superset_idx}_{exercise_idx}",
                                )
                                exercise["name"] = selected_exercise_name

                                selected_exercise = next((item for item in exercise_options if item.get("name") == selected_exercise_name), None)
                                if selected_exercise:
                                    exercise["exercise_id"] = str(selected_exercise.get("_id"))
                                    exercise["metrics"] = selected_exercise.get("metrics", [])
                            with col_right:
                                if st.button("Remove", key=f"edit_remove_exercise_{session_id}_{superset_idx}_{exercise_idx}", use_container_width=True):
                                    exercises.pop(exercise_idx)
                                    st.rerun(scope="fragment")

                        if st.button("Add Exercise", key=f"edit_add_exercise_{session_id}_{superset_idx}", use_container_width=True):
                            exercises.append({"exercise_id": "", "name": "", "metrics": []})
                            st.rerun(scope="fragment")

                        if st.button("Remove Superset", key=f"edit_remove_superset_{session_id}_{superset_idx}", use_container_width=True):
                            supersets.pop(superset_idx)
                            st.rerun(scope="fragment")

                if st.button("Add Superset", key=f"edit_add_superset_{session_id}", use_container_width=True):
                    supersets.append({"repeats": 1, "exercises": [{"exercise_id": "", "name": "", "metrics": []}]})
                    st.rerun(scope="fragment")

                col_save, col_cancel = st.columns(2)
                with col_save:
                    if st.button("Save Changes", key=f"save_edit_{session_id}", use_container_width=True):
                        valid_supersets = []
                        for superset in supersets:
                            exercise_rows = []
                            for exercise in superset.get("exercises", []):
                                if not exercise.get("name"):
                                    continue
                                existing_instances = exercise.get("instances", [])
                                if existing_instances:
                                    instances = []
                                    for instance in existing_instances:
                                        metric_values = {}
                                        for metric in exercise.get("metrics", []):
                                            metric_value = instance.get("metrics", {}).get(metric)
                                            metric_values[metric] = metric_value if metric_value not in [None, ""] else 0
                                        instances.append({"metrics": metric_values})
                                else:
                                    instances = [{"metrics": {}} for _ in range(int(superset.get("repeats", 1)))]
                                exercise_rows.append({
                                    "exercise_id": exercise.get("exercise_id", ""),
                                    "name": exercise.get("name", ""),
                                    "metrics": exercise.get("metrics", []),
                                    "instances": instances,
                                })
                            if exercise_rows:
                                valid_supersets.append({
                                    "repeats": int(superset.get("repeats", 1)),
                                    "exercises": exercise_rows,
                                })

                        if not session_name or not session_name.strip():
                            st.error("Please enter a session name")
                        elif not valid_supersets:
                            st.error("Please add at least one exercise")
                        else:
                            db.db.sessions.update_one(
                                {"_id": session.get("_id")},
                                {"$set": {"name": session_name.strip(), "supersets": valid_supersets}},
                            )
                            st.session_state.pop(f"editing_session_{session_id}", None)
                            st.session_state.pop(f"session_edit_{session_id}", None)
                            st.success("Session updated")
                            st.rerun(scope="app")
                with col_cancel:
                    if st.button("Cancel", key=f"cancel_edit_{session_id}", use_container_width=True):
                        st.session_state.pop(f"editing_session_{session_id}", None)
                        st.session_state.pop(f"session_edit_{session_id}", None)
                        st.rerun(scope="fragment")
            else:
                for superset_idx, superset in enumerate(session.get("supersets", [])):
                    render_superset_content(superset_idx, superset)

                if st.button("Save Session", key=f"save_session_{session_id}", use_container_width=True):
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
                    sleep(.75)
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
            render_session_card(session, False)
    if current_role == "coach":
        st.divider()
        st.subheader("Client Sessions")
        for client_username in accepted_clients:
            with st.expander(f"{client_username}", expanded=False):
                client_sessions = list(db.db.sessions.find({"user_id": client_username}))
                if client_sessions:
                    for session in client_sessions:
                        if session.get("coach_username") == username:
                            render_session_card(session, False)
                        else: 
                            render_session_card(session, True)
                else:
                    st.caption("No sessions assigned to this client yet.")