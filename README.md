# Naylon Fitness Trainer

Plan training sessions, log workouts and see which muscles you're training.

Part of the **Naylon Fitness Portal**, three apps that share one login and one MongoDB database (`workout_platform`):

- [naylon-fitness-trainer](https://github.com/BNay248/naylon-fitness-trainer): sessions, workout logging, exercise library, coaching, muscle coverage
- [naylon-fitness-templates](https://github.com/BNay248/naylon-fitness-templates): slot-based workout templates with ranked suggestions
- [naylon-fitness-tracker](https://github.com/BNay248/naylon-fitness-tracker): calorie and protein tracking

## Features

- Sessions built from supersets and rounds, with per-exercise targets and notes
- Workout logging with previous values pre-filled, one-off swaps with similar-exercise suggestions, and automatic personal records
- An exercise library of 750+ exercises linked to muscles, equipment, movement patterns and progressions (`library_data.py`, loaded by `seed_library.py`)
- Coverage: a ranked heat list of weekly sets per muscle, planned (sessions x days per week) or actual (logged)
- Coaches and clients: coaches share sessions with clients, set their equipment and view their coverage
- Offline-first installable web app: changes queue locally and sync when back online

## Running it

Needs Python 3.10+ and MongoDB on `localhost:27017`.

```bash
python -m venv venv && venv/bin/pip install -r requirements.txt
JWT_SECRET=$(python -c "import secrets; print(secrets.token_hex(32))") venv/bin/uvicorn server:app --port 8501
```

### Configuration (environment variables)

| Variable | Purpose |
|---|---|
| `JWT_SECRET` | **Required.** At least 32 random characters; signs the shared login cookie. Use the same value in all three apps. |
| `COOKIE_DOMAIN` | Parent domain for single sign-on (e.g. `example.com`). Leave unset for local development. |
| `TRACKER_URL`, `TEMPLATES_URL` | Links to the other apps in the navigation. |
| `TRAINER_ADMINS` | Comma-separated usernames allowed on the Admin page. |
| `ADMIN_CONTACT` | Shown to users asking how to become a coach. |

## License

[PolyForm Noncommercial 1.0.0](LICENSE.md): free for personal and other non-commercial use. Commercial use, including selling it or running it as a paid service, needs the author's permission.

Required Notice: Copyright (c) 2026 Bradley Naylon (https://github.com/BNay248)
