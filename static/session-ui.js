// Session components shared by the Sessions page: the superset builder (create/edit) and the session card (log/history).

const MAX_REPEATS = 20;
const clone = value => JSON.parse(JSON.stringify(value));
const blankExercise = () => ({ exercise_id: '', name: '', metrics: [], note: '', targets: {}, instances: [] });
const blankSuperset = () => ({ repeats: 1, exercises: [blankExercise()] });

function roundCount(superset) {
  return Math.min(MAX_REPEATS, Math.max(1, Number(superset.repeats) || 1));
}

function toCount(value) {
  const number = Math.floor(Number(value));
  return Number.isFinite(number) && number > 0 ? number : 0;
}

// A metric value: non-negative, up to 2 decimal places (22.5 stays 22.5, 10.0 becomes 10), like the server's to_amount.
function toAmount(value) {
  const number = Number(value);
  return Number.isFinite(number) && number > 0 ? Math.round(number * 100) / 100 : 0;
}

// Positive targets for the exercise's metrics only, like the server's clean_targets.
function cleanTargets(targets, metrics) {
  return Object.fromEntries(metrics.filter(metric => toAmount((targets || {})[metric]) > 0).map(metric => [metric, toAmount(targets[metric])]));
}

function targetText(exercise) {
  const targets = exercise.targets || {};
  return (exercise.metrics || []).filter(metric => targets[metric]).map(metric => `${metric} ${targets[metric]}`).join(', ');
}

// Same comparison the server uses to decide whether a logged workout still fits the session.
// (Swaps are per round, so a logged entry keeps the planned exercise's id.)
function structureKey(supersets) {
  return JSON.stringify(supersets.map(superset => [roundCount(superset), superset.exercises.map(exercise => exercise.exercise_id)]));
}

// Client-side mirror of the server's with_instances: a swapped round keeps its old values.
function withLoggedValues(supersets, logged) {
  return supersets.map((superset, s) => ({ ...superset, exercises: superset.exercises.map((exercise, e) => {
    const entry = logged[s].exercises[e];
    if (entry.swapped_from) return exercise;
    return { ...exercise, instances: entry.instances.map((instance, round) =>
      instance.swap ? ((exercise.instances || [])[round] || { metrics: {} }) : { metrics: clone(instance.metrics) }) };
  }) }));
}

// Client-side mirror of the server's get_latest_exercise_log for one logged workout: the rounds done as each exercise, by id.
function roundsByExercise(supersets) {
  const found = {};
  supersets.forEach(superset => superset.exercises.forEach(exercise => {
    const here = {};
    exercise.instances.forEach(instance => {
      const id = instance.swap?.exercise_id || exercise.exercise_id;
      (here[id] = here[id] || []).push({ metrics: clone(instance.metrics) });
    });
    Object.entries(here).forEach(([id, instances]) => { if (!found[id]) found[id] = instances; });
  }));
  return found;
}

// Client-side mirror of the server's clean_structure, used to show queued creates/edits before they sync.
function normalizeStructure(supersets, catalog) {
  return supersets.map(superset => {
    const rounds = roundCount(superset);
    const exercises = superset.exercises.map(raw => {
      // Exercises outside this user's catalog (an athlete's personal ones, seen by their coach) are kept as-is.
      const exercise = catalog.byId[raw.exercise_id]
        || (raw.exercise_id && raw.name ? { id: raw.exercise_id, name: raw.name, metrics: raw.metrics || [] } : null);
      if (!exercise) return null;
      return {
        exercise_id: exercise.id,
        name: exercise.name,
        metrics: exercise.metrics,
        note: (raw.note || '').trim(),
        targets: cleanTargets(raw.targets, exercise.metrics),
        instances: Array.from({ length: rounds }, (_, round) => {
          const values = (raw.instances || [])[round]?.metrics || {};
          return { metrics: Object.fromEntries(exercise.metrics.filter(metric => metric in values).map(metric => [metric, toAmount(values[metric])])) };
        }),
      };
    }).filter(Boolean);
    return { repeats: rounds, exercises };
  }).filter(superset => superset.exercises.length);
}

function youtubeEmbed(value) {
  if (typeof value !== 'string') return null;
  const match = value.match(/(?:youtube\.com\/(?:watch\?v=|embed\/|shorts\/)|youtu\.be\/)([A-Za-z0-9_-]{11})/);
  return match ? `https://www.youtube.com/embed/${match[1]}` : null;
}

function exerciseVideo(exercise, catalog) {
  const details = catalog.byId[exercise.exercise_id];
  if (!details) return null;
  return youtubeEmbed(details.video_url) || youtubeEmbed(details.instructions);
}

// How well `to` stands in for `from`, 0 = not a match. Similarity is proportional (shared / combined), so a focused
// match beats one that merely works more muscles: movement patterns weigh most, then primary muscles, then all
// muscles. A substitute must be the same type of exercise (strength, mobility or cardio), work one of the
// original's primary muscles, and share a metric.
function swapScore(from, to) {
  const similarity = (a = [], b = []) => {
    const union = new Set([...a, ...b]);
    return union.size ? a.filter(id => b.includes(id)).length / union.size : 0;
  };
  const sharesAny = (a = [], b = []) => a.some(id => b.includes(id));
  const type = item => {
    const kinds = item.pattern_kinds || [];
    if (kinds.length && kinds.every(kind => kind === 'Mobility')) return 'mobility';
    if (kinds.length && kinds.every(kind => kind === 'Conditioning')) return 'cardio';
    return 'strength';
  };
  const allMuscles = item => [...(item.primary_muscle_ids || []), ...(item.secondary_muscle_ids || [])];
  if (type(from) !== type(to) || !sharesAny(from.primary_muscle_ids, allMuscles(to)) || !sharesAny(from.metrics, to.metrics)) return 0;
  return similarity(from.movement_pattern_ids, to.movement_pattern_ids) * 3
    + similarity(from.primary_muscle_ids, to.primary_muscle_ids) * 2
    + similarity(allMuscles(from), allMuscles(to));
}

// The closest substitutes for an exercise, best first.
function swapSuggestions(from, list, limit = 8) {
  return list.filter(item => item.id !== from.id)
    .map(item => ({ item, score: swapScore(from, item) }))
    .filter(({ score }) => score > 0)
    .sort((a, b) => b.score - a.score || a.item.name.localeCompare(b.item.name))
    .slice(0, limit).map(({ item }) => item);
}

// "New PR! Bench Press (Barbell): 105 Weight (was 100)" for one record from the log endpoint.
function recordText(record, athlete) {
  const who = athlete && athlete !== ME.username ? ` for ${athlete}` : '';
  const sameWeight = record.metric === 'Weight' && record.value === record.previous;
  const what = sameWeight ? `${record.reps} reps at ${record.value} (was ${record.previous_reps})`
    : record.metric === 'Reps' ? `${record.value} reps (was ${record.previous})`
      : `${record.metric} ${record.value} (was ${record.previous})`;
  return `🏆 New PR${who}! ${record.name}: ${what}`;
}

function makeCatalog(exercises) {
  return {
    list: exercises,
    byId: Object.fromEntries(exercises.map(item => [item.id, item])),
  };
}

function sessionCopyText(session) {
  const lines = [session.name || 'Untitled Session'];
  session.supersets.forEach((superset, idx) => {
    const rounds = Math.max(roundCount(superset), ...superset.exercises.map(ex => (ex.instances || []).length));
    lines.push(`\nSuperset ${idx + 1} (${rounds} round(s)):`);
    superset.exercises.forEach(exercise => {
      const target = targetText(exercise);
      lines.push(`  ${exercise.name || 'Untitled'}${target ? ` (target: ${target})` : ''}`);
      if (exercise.note) lines.push(`    Note: ${exercise.note}`);
    });
  });
  return lines.join('\n');
}

function logText(log) {
  const lines = [];
  log.supersets.forEach((superset, idx) => {
    lines.push(`Superset ${idx + 1}`);
    superset.exercises.forEach(exercise => {
      lines.push(`  ${exercise.name || 'Untitled'}${exercise.swapped_from ? ` (swapped in for ${exercise.swapped_from.name})` : ''}`);
      (exercise.instances || []).forEach((instance, round) => {
        const metrics = instance.swap ? instance.swap.metrics : exercise.metrics;
        const values = metrics.map(metric => `${metric}: ${(instance.metrics || {})[metric] ?? 0}`).join(', ') || 'no metrics';
        lines.push(`    Round ${round + 1}${instance.swap ? ` (${instance.swap.name} instead)` : ''}: ${values}`);
      });
    });
  });
  return lines.join('\n');
}

async function copyToClipboard(text) {
  // navigator.clipboard only exists on https/localhost; fall back to execCommand on plain http.
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    const area = el('textarea', { style: 'position:fixed;opacity:0' });
    area.value = text;
    document.body.appendChild(area);
    area.select();
    let copied = false;
    try { copied = document.execCommand('copy'); } catch {}
    area.remove();
    return copied;
  }
}

// `value` may be null when a `placeholder` is given: the field stays blank showing the placeholder,
// and the −/+ buttons step from the placeholder's value. Decimals are allowed unless `integer` is set.
function numberStepper(value, onChange, { min = 0, max = Infinity, placeholder = null, integer = false } = {}) {
  const parse = integer ? toCount : toAmount;
  const input = el('input', { type: 'number', inputmode: integer ? 'numeric' : 'decimal', step: integer ? '1' : 'any', min, value: value == null ? '' : String(value) });
  if (placeholder != null) input.placeholder = String(placeholder);
  const current = () => parse(input.value === '' && placeholder != null ? placeholder : input.value);
  const set = next => {
    const clamped = Math.min(max, Math.max(min, parse(next)));
    input.value = String(clamped);
    onChange(clamped);
  };
  input.addEventListener('change', () => (input.value === '' && placeholder != null ? onChange(null) : set(input.value)));
  input.addEventListener('focus', () => input.select());
  return el('div', { class: 'stepper' },
    el('button', { type: 'button', onclick: () => set(current() - 1), 'aria-label': 'Decrease' }, '−'),
    input,
    el('button', { type: 'button', onclick: () => set(current() + 1), 'aria-label': 'Increase' }, '+'),
  );
}

// Tracks which <details> are open (by key) so re-renders from background sync don't collapse anything.
function trackedDetails(key, openKeys, props, ...children) {
  const node = el('details', { ...props, open: openKeys.has(key) }, ...children);
  node.addEventListener('toggle', () => { node.open ? openKeys.add(key) : openKeys.delete(key); });
  return node;
}

// ---------- Builder (create + edit structure) ----------

// Returns a node that edits a copy of `initial` and hands the cleaned result to onSave({name, supersets, assigned_to}).
// `intro` is an optional node shown above the save button (e.g. who an edit applies to).
function sessionBuilder({ catalog, initial, saveLabel, onSave, onCancel, clients, intro }) {
  const state = {
    name: initial?.name || '',
    assignedTo: '',
    supersets: initial ? clone(initial.supersets) : [blankSuperset()],
  };
  const root = el('div', { class: 'builder' });

  function exerciseSelect(exercise) {
    const current = catalog.byId[exercise.exercise_id];
    // Not in this user's catalog (e.g. a client's personal exercise); keep it selectable so saving doesn't drop it.
    const outside = !current && exercise.exercise_id && exercise.name
      ? { id: exercise.exercise_id, name: exercise.name, metrics: exercise.metrics || [] } : null;
    const select = el('select', {
      onchange: () => {
        const chosen = catalog.byId[select.value] || (outside && select.value === outside.id ? outside : null);
        Object.assign(exercise, chosen
          ? { exercise_id: chosen.id, name: chosen.name, metrics: chosen.metrics, targets: {}, instances: [] }
          : blankExercise());
        render(); // show the note/target fields for the chosen exercise
      },
    },
      el('option', { value: '' }, 'Choose exercise…'),
      outside && el('option', { value: outside.id }, `${outside.name} (not in your list)`),
      catalog.list.map(item => el('option', { value: item.id }, item.name)),
    );
    select.value = (current || outside)?.id || '';
    return select;
  }

  // Coach instructions for one exercise in this session: a free-text note and a target per metric.
  function exerciseExtras(exercise) {
    exercise.targets = exercise.targets || {};
    return el('div', { class: 'exercise-extras' },
      el('input', {
        type: 'text', value: exercise.note || '', maxlength: 500, placeholder: 'Note (optional), e.g. hold at top for 5 seconds',
        oninput: e => { exercise.note = e.target.value; },
      }),
      (exercise.metrics || []).length > 0 && el('div', { class: 'metric-grid' }, exercise.metrics.map(metric => el('div', {},
        el('label', {}, `Target ${metric.toLowerCase()}`),
        el('input', {
          type: 'number', inputmode: 'decimal', step: 'any', min: 0, value: exercise.targets[metric] ?? '', placeholder: '–',
          oninput: e => {
            if (toAmount(e.target.value)) exercise.targets[metric] = toAmount(e.target.value);
            else delete exercise.targets[metric];
          },
        }),
      ))),
    );
  }

  function render() {
    const nameInput = el('input', { type: 'text', value: state.name, oninput: e => { state.name = e.target.value; } });
    mount(root,
      el('div', { class: 'field' }, el('label', {}, 'Session Name*'), nameInput),
      clients && (clients.length
        ? el('div', { class: 'field' },
          el('label', {}, 'Assign to client (optional)'),
          el('select', { onchange: e => { state.assignedTo = e.target.value; } },
            el('option', { value: '' }, 'Myself'),
            clients.map(client => el('option', { value: client.username, selected: client.username === state.assignedTo }, `${client.name} (${client.username})`)),
          ))
        : el('p', { class: 'muted field' }, 'No accepted clients yet.')),
      state.supersets.map((superset, supersetIdx) => el('div', { class: 'superset' },
        el('div', { class: 'superset-head' },
          el('span', { class: 'grow' }, `Superset ${supersetIdx + 1}`),
          el('span', { class: 'muted' }, 'Rounds'),
          el('div', { style: 'width:140px' }, numberStepper(roundCount(superset), value => { superset.repeats = value; }, { min: 1, max: MAX_REPEATS, integer: true })),
        ),
        superset.exercises.map((exercise, exerciseIdx) => el('div', { class: 'builder-exercise field' },
          el('div', { class: 'row' },
            el('div', { class: 'grow' }, exerciseSelect(exercise)),
            el('button', { type: 'button', class: 'small danger', onclick: () => { superset.exercises.splice(exerciseIdx, 1); render(); } }, 'Remove'),
          ),
          (exercise.exercise_id || exercise.name) && exerciseExtras(exercise),
        )),
        el('div', { class: 'buttons' },
          el('button', { type: 'button', onclick: () => { superset.exercises.push(blankExercise()); render(); } }, '+ Add Exercise'),
          el('button', { type: 'button', class: 'danger', onclick: () => { state.supersets.splice(supersetIdx, 1); render(); } }, 'Remove Superset'),
        ),
      )),
      el('div', { class: 'buttons' },
        el('button', { type: 'button', onclick: () => { state.supersets.push(blankSuperset()); render(); } }, '+ Add Superset'),
      ),
      intro,
      el('div', { class: 'buttons' },
        el('button', { type: 'button', class: 'primary', onclick: e => save(e.currentTarget) }, saveLabel),
        onCancel && el('button', { type: 'button', onclick: onCancel }, 'Cancel'),
      ),
    );
  }

  function save(button) {
    const supersets = state.supersets
      .map(superset => ({ repeats: roundCount(superset), exercises: superset.exercises.filter(ex => ex.exercise_id || ex.name) }))
      .filter(superset => superset.exercises.length);
    if (!state.name.trim()) return toast('Please enter a session name', 'error');
    if (!supersets.length) return toast('Please add at least one exercise', 'error');
    return withBusy(button, () => onSave({ name: state.name.trim(), supersets, assigned_to: state.assignedTo || null }));
  }

  render();
  return root;
}

// ---------- Session card (log a workout, history, edit, delete) ----------

// A swapped round carries its substitute's previous values (fetched when swapping), since the session doesn't list it.
function previousValues(session, exercise, round) {
  const swap = (exercise.instances || [])[round]?.swap;
  return roundValues(swap ? exercise.instances[round].previous : session.previous?.[exercise.exercise_id], swap ? swap.metrics : exercise.metrics, round);
}

function roundValues(previous, metrics, round) {
  if (!previous || !previous.instances?.length) return {};
  const values = previous.instances[Math.min(round, previous.instances.length - 1)].metrics || {};
  return Object.fromEntries(metrics.filter(metric => values[metric]).map(metric => [metric, values[metric]]));
}

// Working copy of the session's metrics: one instance per round. Metrics with a target start blank (the target shows
// as a placeholder); the rest are prefilled from saved or previous values.
function workoutDraft(session) {
  return session.supersets.map(superset => ({
    repeats: roundCount(superset),
    exercises: superset.exercises.map(exercise => draftExercise(session, exercise, roundCount(superset))),
  }));
}

function draftExercise(session, exercise, rounds) {
  return {
    exercise_id: exercise.exercise_id,
    name: exercise.name,
    metrics: exercise.metrics || [],
    note: exercise.note || '',
    targets: exercise.targets || {},
    instances: Array.from({ length: rounds }, (_, round) => {
      const saved = (exercise.instances || [])[round]?.metrics || {};
      const previous = previousValues(session, exercise, round);
      return { metrics: Object.fromEntries((exercise.metrics || []).map(metric => [metric,
        (exercise.targets || {})[metric] ? null : toAmount(saved[metric] ?? previous[metric] ?? 0)])) };
    }),
  };
}

// One round done as `chosen` instead of the planned exercise, this time only. Prefilled from `previous` ({instances}
// from /api/previous, or null); the planned exercise's targets don't carry over, since its weights etc. may not apply.
function swappedRound(chosen, round, previous) {
  const metrics = chosen.metrics || [];
  const values = roundValues(previous, metrics, round);
  return {
    swap: { exercise_id: chosen.id, name: chosen.name, metrics },
    previous: previous?.instances?.length ? previous : null,
    metrics: Object.fromEntries(metrics.map(metric => [metric, toAmount(values[metric] ?? 0)])),
  };
}

// The workout as it gets logged: fields left blank count as having hit the target, and fetched previous values are dropped.
function withTargetsFilled(draft) {
  const filled = clone(draft);
  filled.forEach(superset => superset.exercises.forEach(exercise => exercise.instances.forEach(instance => {
    delete instance.previous;
    for (const metric of Object.keys(instance.metrics)) {
      if (instance.metrics[metric] == null) instance.metrics[metric] = toAmount((exercise.targets || {})[metric]);
    }
  })));
  return filled;
}

// actions: {log(session, supersets), update(session, {name, supersets, athlete, scope}), remove(session), assign(session, usernames)}
// drafts:  {get(key), set(key, supersets), clear(key)} — unsaved workout values, kept across reloads.
// openKeys: Set of expanded section keys, shared across re-renders.
// clients: the coach's clients [{username, name}], used to assign the session; omitted for non-coaches.
// A session object is one athlete's view (session.user_id); a shared session appears once per athlete, so
// per-view state is keyed by session.key rather than the session id.
function sessionCard(session, { catalog, actions, drafts, openKeys, clients = null, historyPending = 0 }) {
  const key = session.key || session.id;
  const sharedWith = session.shared_with || [];
  const athleteName = session.user_id === ME.username ? 'you' : (session.athlete_name || session.user_id);
  const body = el('div', {});
  let mode = 'log';
  let showVideos = false;
  let confirmingDelete = false;
  let assigning = null; // Set of usernames picked in the assign panel while it's open
  let editScope = session.can_edit_all ? 'all' : 'athlete';
  let swapping = null; // "superset:exercise" index whose swap picker is open
  const unsynced = session.pending || historyPending > 0;

  const card = trackedDetails(key, openKeys, { class: 'card', dataset: { sessionId: session.id } },
    el('summary', {},
      el('span', {}, session.name),
      el('span', { class: 'tag' }, `${session.supersets.length} superset(s)`),
      sharedWith.length > 0 && el('span', { class: 'tag' }, 'Shared'),
      unsynced && el('span', { class: 'tag pending' }, 'Not synced')),
    body,
  );
  // Build the body lazily so long lists stay fast.
  const ensureBody = () => { if (card.open && !body.childElementCount) render(); };
  card.addEventListener('toggle', ensureBody);
  ensureBody();

  function render() {
    if (mode === 'edit') {
      return mount(body, sessionBuilder({
        catalog,
        initial: session,
        saveLabel: 'Save Changes',
        intro: scopeChooser(),
        onCancel: () => { mode = 'log'; render(); },
        onSave: data => actions.update(session, { name: data.name, supersets: data.supersets, athlete: session.user_id, scope: editScope }),
      }));
    }
    mount(body, toolbar(), sharedNote(), logView(), historySection());
  }

  function sharedNote() {
    if (!sharedWith.length) return null;
    return el('p', { class: 'muted' }, `Shared with ${sharedWith.map(other => other.name).join(', ')}. Editing it makes a separate copy unless the coach edits it for everyone.`);
  }

  // Who an edit to a shared session applies to. The coach who made it can change everyone's; anyone else gets their own copy.
  function scopeChooser() {
    if (!sharedWith.length) return null;
    if (!session.can_edit_all) {
      return el('p', { class: 'info' }, `This session is shared, so saving makes a separate copy for ${athleteName}. Everyone else keeps the original.`);
    }
    const option = (value, label) => el('label', { class: 'check' },
      el('input', { type: 'radio', name: `scope-${key}`, checked: editScope === value, onchange: () => { editScope = value; } }), label);
    return el('div', { class: 'field' },
      el('label', {}, 'Apply changes to'),
      option('all', `Everyone using this session (${sharedWith.length + 1} people)`),
      option('athlete', `Only ${athleteName} (makes a separate copy)`),
    );
  }

  function toolbar() {
    if (confirmingDelete) {
      return el('div', { class: 'confirm' },
        el('div', {}, sharedWith.length
          ? `Remove this session for ${athleteName}? ${sharedWith.map(other => other.name).join(', ')} keep it.`
          : 'Delete this session? Its workout history is kept.'),
        el('div', { class: 'buttons' },
          el('button', { class: 'danger', onclick: e => withBusy(e.currentTarget, () => actions.remove(session)) }, sharedWith.length ? 'Yes, remove' : 'Yes, delete'),
          el('button', { onclick: () => { confirmingDelete = false; render(); } }, 'Cancel'),
        ),
      );
    }
    if (assigning) return assignPanel();
    const canAssign = clients && clients.length > 0 && !session.id.startsWith('local-');
    return el('div', {},
      el('div', { class: 'buttons' },
        el('button', { onclick: () => { mode = 'edit'; render(); } }, 'Edit Session'),
        canAssign && el('button', { onclick: () => { assigning = new Set(); render(); } }, 'Assign to Clients'),
        session.can_delete && el('button', { class: 'danger', onclick: () => { confirmingDelete = true; render(); } }, sharedWith.length ? 'Remove Session' : 'Delete Session'),
        el('button', { onclick: async e => {
          const button = e.currentTarget;
          const copied = await copyToClipboard(sessionCopyText(session));
          button.textContent = copied ? 'Copied!' : 'Copy failed';
          setTimeout(() => { button.textContent = 'Copy to Clipboard'; }, 1500);
        } }, 'Copy to Clipboard'),
      ),
      el('label', { class: 'check' },
        el('input', { type: 'checkbox', checked: showVideos, onchange: e => { showVideos = e.target.checked; render(); } }),
        'Show videos'),
    );
  }

  function assignPanel() {
    const using = new Set([session.user_id, ...sharedWith.map(other => other.username)]);
    const available = clients.filter(client => !using.has(client.username));
    return el('div', { class: 'confirm' },
      el('div', {}, 'Share this session with:'),
      available.length
        ? available.map(client => el('label', { class: 'check' },
          el('input', { type: 'checkbox', checked: assigning.has(client.username), onchange: e => {
            e.target.checked ? assigning.add(client.username) : assigning.delete(client.username);
          } }),
          `${client.name} (${client.username})`))
        : el('p', { class: 'muted' }, 'All your clients already have this session.'),
      el('p', { class: 'muted' }, 'They all use this session until someone edits their own copy.'),
      el('div', { class: 'buttons' },
        available.length > 0 && el('button', { class: 'primary', onclick: e => {
          if (!assigning.size) return toast('Pick at least one client', 'error');
          const usernames = [...assigning];
          assigning = null;
          return withBusy(e.currentTarget, () => actions.assign(session, usernames));
        } }, 'Assign'),
        el('button', { onclick: () => { assigning = null; render(); } }, 'Cancel'),
      ),
    );
  }

  function logView() {
    // Resume an unsaved draft only if the session layout hasn't changed underneath it.
    const stored = drafts.get(key);
    const draft = stored && structureKey(stored) === structureKey(session.supersets) ? stored : workoutDraft(session);
    // Notes and targets always come from the session, so edits show up even over an older draft.
    draft.forEach((superset, s) => superset.exercises.forEach((exercise, e) => {
      const current = session.supersets[s].exercises[e];
      exercise.note = current.note || '';
      exercise.targets = current.targets || {};
    }));
    const saveDraft = () => drafts.set(key, draft);
    const saveButton = el('button', { class: 'primary', onclick: () => withBusy(saveButton, () => actions.log(session, withTargetsFilled(draft))) }, 'Save Session');

    return el('div', {},
      draft.map((superset, supersetIdx) => trackedDetails(`${key}:superset:${supersetIdx}`, openKeys, { class: 'card' },
        el('summary', {}, `Superset ${supersetIdx + 1} • ${superset.repeats} round(s)`),
        superset.exercises.map((exercise, exerciseIdx) => {
          const at = `${supersetIdx}:${exerciseIdx}`;
          const original = session.supersets[supersetIdx].exercises[exerciseIdx];
          const change = (rounds, instanceFor) => {
            rounds.forEach(round => { exercise.instances[round] = instanceFor(round); });
            swapping = null;
            saveDraft();
            render();
          };
          return exerciseLog(exercise, superset.repeats, saveDraft, {
            picker: swapping?.at === at ? swapping : null,
            // From the exercise (from = null) every round is picked; from a round, that round and the ones after it.
            open: from => {
              swapping = { at, from, rounds: new Set(Array.from({ length: superset.repeats }, (_, round) => round).filter(round => round >= (from ?? 0))) };
              render();
            },
            close: () => { swapping = null; render(); },
            apply: (chosen, rounds, previous) => change(rounds, round => swappedRound(chosen, round, previous)),
            undo: rounds => change(rounds, round => draftExercise(session, original, superset.repeats).instances[round]),
          });
        }),
      )),
      el('div', { class: 'buttons' }, saveButton),
    );
  }

  // One block per exercise: name/note/video once, then a row of inputs for each round.
  // Any round can be swapped for another exercise for this workout only; the exercise's Swap button swaps them all.
  function exerciseLog(exercise, rounds, onEdit, swap) {
    const swappedRounds = exercise.instances.map((instance, round) => instance.swap ? round : null).filter(round => round != null);
    const substitutes = [...new Map(swappedRounds.map(round => exercise.instances[round].swap).map(item => [item.exercise_id, item])).values()];
    const videos = showVideos ? [exercise, ...substitutes]
      .map(item => [item.name, exerciseVideo(item, catalog)]).filter(([, video]) => video) : [];
    const target = targetText(exercise);
    return el('div', { class: 'exercise-log' },
      el('div', { class: 'row' },
        el('div', { class: 'name grow' }, exercise.name || 'Untitled', swappedRounds.length > 0 && el('span', { class: 'tag swapped' }, 'Swapped')),
        !swap.picker && swappedRounds.length > 0 && el('button', { type: 'button', class: 'small', onclick: () => swap.undo(swappedRounds) }, 'Undo swaps'),
        !swap.picker && el('button', { type: 'button', class: 'small', onclick: () => swap.open(null) }, 'Swap'),
      ),
      swap.picker && swap.picker.from == null && swapPicker(exercise, rounds, swap),
      exercise.note && el('div', { class: 'exercise-note' }, exercise.note),
      target && el('div', { class: 'muted' }, `Target: ${target}`),
      videos.map(([name, video]) => el('div', { class: 'video' }, el('iframe', { src: video, allowfullscreen: true, loading: 'lazy', title: name }))),
      Array.from({ length: rounds }, (_, round) => roundRow(exercise, round, rounds, onEdit, swap)),
    );
  }

  // Choose a substitute for some rounds of this workout only (machine taken, injury, …). The session itself is unchanged.
  function swapPicker(exercise, rounds, swap) {
    const picked = swap.picker.rounds;
    const planned = catalog.byId[exercise.exercise_id];
    const matches = planned ? swapSuggestions(planned, catalog.list) : [];
    const options = items => items.filter(item => item.id !== exercise.exercise_id).map(item => el('option', { value: item.id }, item.name));
    const select = el('select', {},
      el('option', { value: '' }, 'Do instead…'),
      matches.length ? [el('optgroup', { label: 'Best matches' }, options(matches)), el('optgroup', { label: 'All exercises' }, options(catalog.list))]
        : options(catalog.list),
    );
    const chips = rounds > 1 && el('div', { class: 'chips field' }, Array.from({ length: rounds }, (_, round) => {
      const chip = el('span', { class: `chip${picked.has(round) ? ' on' : ''}`, onclick: () => {
        picked.has(round) ? picked.delete(round) : picked.add(round);
        chip.classList.toggle('on', picked.has(round));
      } }, `Round ${round + 1}`);
      return chip;
    }));
    const choose = async () => {
      const chosen = catalog.byId[select.value];
      if (!chosen) return toast('Pick an exercise to swap in', 'error');
      if (!picked.size) return toast('Pick at least one round', 'error');
      let previous = null;
      try {
        previous = await api('GET', `/api/previous?exercise_id=${encodeURIComponent(chosen.id)}&athlete=${encodeURIComponent(session.user_id)}`);
      } catch (err) {
        if (err.status !== 0) throw err; // offline: swap anyway, just without previous values
      }
      swap.apply(chosen, [...picked], previous);
    };
    return el('div', { class: 'confirm' },
      el('div', { class: 'field' }, `Swap ${exercise.name} for this workout only:`),
      el('div', { class: 'field' }, select),
      chips,
      el('div', { class: 'buttons' },
        el('button', { type: 'button', class: 'primary', onclick: e => withBusy(e.currentTarget, choose) }, 'Swap'),
        el('button', { type: 'button', onclick: swap.close }, 'Cancel'),
      ),
    );
  }

  function roundRow(exercise, round, rounds, onEdit, swap) {
    const instance = exercise.instances[round];
    const metrics = instance.swap ? instance.swap.metrics : exercise.metrics;
    const previous = previousValues(session, exercise, round);
    const previousText = metrics.filter(metric => metric in previous).map(metric => `${metric}: ${previous[metric]}`).join(', ');
    const targets = instance.swap ? {} : exercise.targets || {};
    return el('div', { class: 'round-row' },
      el('div', { class: 'row' },
        el('div', { class: 'round-title grow' }, `Round ${round + 1}`, instance.swap && el('span', { class: 'swapped-name' }, ` · ${instance.swap.name} instead`)),
        !swap.picker && (instance.swap
          ? el('button', { type: 'button', class: 'small', onclick: () => swap.undo([round]) }, 'Undo')
          : rounds > 1 && el('button', { type: 'button', class: 'small', onclick: () => swap.open(round) }, 'Swap')),
      ),
      swap.picker?.from === round && swapPicker(exercise, rounds, swap),
      metrics.length
        ? el('div', { class: 'metric-grid' }, metrics.map(metric => el('div', {},
          el('label', {}, metric),
          numberStepper(instance.metrics[metric], value => { instance.metrics[metric] = value; onEdit(); }, { placeholder: targets[metric] || null }),
        )))
        : el('div', { class: 'muted' }, 'No metrics configured for this exercise'),
      previousText && el('div', { class: 'muted' }, `Previous: ${previousText}`),
    );
  }

  function historySection() {
    const list = el('div', {}, el('div', { class: 'muted' }, 'Loading…'));
    const section = trackedDetails(`${key}:history`, openKeys, { class: 'card' }, el('summary', {}, 'History'), list);
    const load = async () => {
      if (!section.open) return;
      const waiting = historyPending > 0 && el('p', { class: 'muted' }, `${historyPending} workout(s) waiting to sync.`);
      if (session.id.startsWith('local-')) return mount(list, waiting || el('p', { class: 'muted' }, 'Not synced yet.'));
      try {
        const logs = await api('GET', `/api/sessions/${session.id}/history?athlete=${encodeURIComponent(session.user_id)}`);
        mount(list, waiting, logs.length
          ? logs.map(log => el('div', { class: 'history-entry' },
            el('strong', {}, formatDate(log.created_at)),
            log.logged_by && log.logged_by !== log.user_id && el('span', { class: 'muted' }, ` (logged by ${log.logged_by})`),
            el('pre', {}, logText(log)),
          ))
          : !waiting && el('div', { class: 'muted' }, 'No workouts logged yet. Press Save Session after a workout to record it.'));
      } catch (err) {
        mount(list, waiting, el('div', { class: 'muted' }, err.status === 0 ? 'History is unavailable offline.' : err.message));
      }
    };
    section.addEventListener('toggle', load);
    load();
    return section;
  }

  return card;
}
