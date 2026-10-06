// Session components shared by the Sessions page: the superset builder (create/edit) and the session card (log/history).

const MAX_REPEATS = 20;
const clone = value => JSON.parse(JSON.stringify(value));
const blankExercise = () => ({ exercise_id: '', name: '', metrics: [], instances: [] });
const blankSuperset = () => ({ repeats: 1, exercises: [blankExercise()] });

function roundCount(superset) {
  return Math.min(MAX_REPEATS, Math.max(1, Number(superset.repeats) || 1));
}

function toCount(value) {
  const number = Math.floor(Number(value));
  return Number.isFinite(number) && number > 0 ? number : 0;
}

// Same comparison the server uses to decide whether a logged workout still fits the session.
function structureKey(supersets) {
  return JSON.stringify(supersets.map(superset => [roundCount(superset), superset.exercises.map(exercise => exercise.name)]));
}

// Client-side mirror of the server's clean_structure, used to show queued creates/edits before they sync.
function normalizeStructure(supersets, catalog) {
  return supersets.map(superset => {
    const rounds = roundCount(superset);
    const exercises = superset.exercises.map(raw => {
      // Exercises outside this user's catalog (an athlete's personal ones, seen by their coach) are kept as-is.
      const exercise = catalog.byId[raw.exercise_id] || catalog.byName[raw.name]
        || (raw.exercise_id && raw.name ? { id: raw.exercise_id, name: raw.name, metrics: raw.metrics || [] } : null);
      if (!exercise) return null;
      return {
        exercise_id: exercise.id,
        name: exercise.name,
        metrics: exercise.metrics,
        instances: Array.from({ length: rounds }, (_, round) => {
          const values = (raw.instances || [])[round]?.metrics || {};
          return { metrics: Object.fromEntries(exercise.metrics.filter(metric => metric in values).map(metric => [metric, toCount(values[metric])])) };
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
  const details = catalog.byId[exercise.exercise_id] || catalog.byName[exercise.name];
  if (!details) return null;
  return youtubeEmbed(details.video_url) || youtubeEmbed(details.instructions);
}

function makeCatalog(exercises) {
  return {
    list: exercises,
    byId: Object.fromEntries(exercises.map(item => [item.id, item])),
    byName: Object.fromEntries(exercises.map(item => [item.name, item])),
  };
}

function sessionCopyText(session) {
  const lines = [session.name || 'Untitled Session'];
  session.supersets.forEach((superset, idx) => {
    const rounds = Math.max(roundCount(superset), ...superset.exercises.map(ex => (ex.instances || []).length));
    lines.push(`\nSuperset ${idx + 1} (${rounds} round(s)):`);
    superset.exercises.forEach(exercise => lines.push(`  ${exercise.name || 'Untitled'}`));
  });
  return lines.join('\n');
}

function logText(log) {
  const lines = [];
  log.supersets.forEach((superset, idx) => {
    lines.push(`Superset ${idx + 1}`);
    superset.exercises.forEach(exercise => {
      lines.push(`  ${exercise.name || 'Untitled'}`);
      (exercise.instances || []).forEach((instance, round) => {
        const values = exercise.metrics.map(metric => `${metric}: ${(instance.metrics || {})[metric] ?? 0}`).join(', ') || 'no metrics';
        lines.push(`    Round ${round + 1}: ${values}`);
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

function numberStepper(value, onChange, { min = 0, max = Infinity } = {}) {
  const input = el('input', { type: 'number', inputmode: 'numeric', min, value: String(value) });
  const set = next => {
    const clamped = Math.min(max, Math.max(min, toCount(next)));
    input.value = String(clamped);
    onChange(clamped);
  };
  input.addEventListener('change', () => set(input.value));
  input.addEventListener('focus', () => input.select());
  return el('div', { class: 'stepper' },
    el('button', { type: 'button', onclick: () => set(toCount(input.value) - 1), 'aria-label': 'Decrease' }, '−'),
    input,
    el('button', { type: 'button', onclick: () => set(toCount(input.value) + 1), 'aria-label': 'Increase' }, '+'),
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
function sessionBuilder({ catalog, initial, saveLabel, onSave, onCancel, clients }) {
  const state = {
    name: initial?.name || '',
    assignedTo: '',
    supersets: initial ? clone(initial.supersets) : [blankSuperset()],
  };
  const root = el('div', { class: 'builder' });

  function exerciseSelect(exercise) {
    // Legacy rows may only have a name; match it to the catalog.
    const current = catalog.byId[exercise.exercise_id] || catalog.byName[exercise.name];
    // Not in this user's catalog (e.g. a client's personal exercise); keep it selectable so saving doesn't drop it.
    const outside = !current && exercise.exercise_id && exercise.name
      ? { id: exercise.exercise_id, name: exercise.name, metrics: exercise.metrics || [] } : null;
    const select = el('select', {
      onchange: () => {
        const chosen = catalog.byId[select.value] || (outside && select.value === outside.id ? outside : null);
        Object.assign(exercise, chosen
          ? { exercise_id: chosen.id, name: chosen.name, metrics: chosen.metrics, instances: [] }
          : blankExercise());
      },
    },
      el('option', { value: '' }, 'Choose exercise…'),
      outside && el('option', { value: outside.id }, `${outside.name} (not in your list)`),
      catalog.list.map(item => el('option', { value: item.id }, item.name)),
    );
    select.value = (current || outside)?.id || '';
    return select;
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
          el('div', { style: 'width:140px' }, numberStepper(roundCount(superset), value => { superset.repeats = value; }, { min: 1, max: MAX_REPEATS })),
        ),
        superset.exercises.map((exercise, exerciseIdx) => el('div', { class: 'row field' },
          el('div', { class: 'grow' }, exerciseSelect(exercise)),
          el('button', { type: 'button', class: 'small danger', onclick: () => { superset.exercises.splice(exerciseIdx, 1); render(); } }, 'Remove'),
        )),
        el('div', { class: 'buttons' },
          el('button', { type: 'button', onclick: () => { superset.exercises.push(blankExercise()); render(); } }, '+ Add Exercise'),
          el('button', { type: 'button', class: 'danger', onclick: () => { state.supersets.splice(supersetIdx, 1); render(); } }, 'Remove Superset'),
        ),
      )),
      el('div', { class: 'buttons' },
        el('button', { type: 'button', onclick: () => { state.supersets.push(blankSuperset()); render(); } }, '+ Add Superset'),
      ),
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

function previousValues(session, exercise, round) {
  const previous = session.previous?.[exercise.name];
  if (!previous || !previous.instances.length) return {};
  const metrics = previous.instances[Math.min(round, previous.instances.length - 1)].metrics || {};
  return Object.fromEntries(exercise.metrics.filter(metric => metrics[metric]).map(metric => [metric, metrics[metric]]));
}

// Working copy of the session's metrics: one instance per round, prefilled from saved or previous values.
function workoutDraft(session) {
  return session.supersets.map(superset => ({
    repeats: roundCount(superset),
    exercises: superset.exercises.map(exercise => ({
      exercise_id: exercise.exercise_id,
      name: exercise.name,
      metrics: exercise.metrics || [],
      instances: Array.from({ length: roundCount(superset) }, (_, round) => {
        const saved = (exercise.instances || [])[round]?.metrics || {};
        const previous = previousValues(session, exercise, round);
        return { metrics: Object.fromEntries((exercise.metrics || []).map(metric => [metric, toCount(saved[metric] ?? previous[metric] ?? 0)])) };
      }),
    })),
  }));
}

// actions: {log(session, supersets), update(session, {name, supersets}), remove(session)}
// drafts:  {get(id), set(id, supersets), clear(id)} — unsaved workout values, kept across reloads.
// openKeys: Set of expanded section keys, shared across re-renders.
function sessionCard(session, { catalog, actions, drafts, openKeys, historyPending = 0 }) {
  const body = el('div', {});
  let mode = 'log';
  let showVideos = false;
  let confirmingDelete = false;
  const unsynced = session.pending || historyPending > 0;

  const card = trackedDetails(session.id, openKeys, { class: 'card', dataset: { sessionId: session.id } },
    el('summary', {},
      el('span', {}, session.name),
      el('span', { class: 'tag' }, `${session.supersets.length} superset(s)`),
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
        onCancel: () => { mode = 'log'; render(); },
        onSave: data => actions.update(session, { name: data.name, supersets: data.supersets }),
      }));
    }
    mount(body, toolbar(), logView(), historySection());
  }

  function toolbar() {
    if (confirmingDelete) {
      return el('div', { class: 'confirm' },
        el('div', {}, 'Delete this session? Its workout history is kept.'),
        el('div', { class: 'buttons' },
          el('button', { class: 'danger', onclick: e => withBusy(e.currentTarget, () => actions.remove(session)) }, 'Yes, delete'),
          el('button', { onclick: () => { confirmingDelete = false; render(); } }, 'Cancel'),
        ),
      );
    }
    return el('div', {},
      el('div', { class: 'buttons' },
        el('button', { onclick: () => { mode = 'edit'; render(); } }, 'Edit Session'),
        session.can_delete && el('button', { class: 'danger', onclick: () => { confirmingDelete = true; render(); } }, 'Delete Session'),
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

  function logView() {
    // Resume an unsaved draft only if the session layout hasn't changed underneath it.
    const stored = drafts.get(session.id);
    const draft = stored && structureKey(stored) === structureKey(session.supersets) ? stored : workoutDraft(session);
    const saveButton = el('button', { class: 'primary', onclick: () => withBusy(saveButton, () => actions.log(session, clone(draft))) }, 'Save Session');

    return el('div', {},
      draft.map((superset, supersetIdx) => trackedDetails(`${session.id}:superset:${supersetIdx}`, openKeys, { class: 'card' },
        el('summary', {}, `Superset ${supersetIdx + 1} • ${superset.repeats} round(s)`),
        superset.exercises.map(exercise => exerciseLog(exercise, superset.repeats, () => drafts.set(session.id, draft))),
      )),
      el('div', { class: 'buttons' }, saveButton),
    );
  }

  // One block per exercise: name/video once, then a row of inputs for each round.
  function exerciseLog(exercise, rounds, onEdit) {
    const video = showVideos && exerciseVideo(exercise, catalog);
    return el('div', { class: 'exercise-log' },
      el('div', { class: 'name' }, exercise.name || 'Untitled'),
      video && el('div', { class: 'video' }, el('iframe', { src: video, allowfullscreen: true, loading: 'lazy', title: exercise.name })),
      exercise.metrics.length
        ? Array.from({ length: rounds }, (_, round) => roundRow(exercise, round, onEdit))
        : el('div', { class: 'muted' }, 'No metrics configured for this exercise'),
    );
  }

  function roundRow(exercise, round, onEdit) {
    const previous = previousValues(session, exercise, round);
    const previousText = exercise.metrics.filter(metric => metric in previous).map(metric => `${metric}: ${previous[metric]}`).join(', ');
    const values = exercise.instances[round].metrics;
    return el('div', { class: 'round-row' },
      el('div', { class: 'round-title' }, `Round ${round + 1}`),
      el('div', { class: 'metric-grid' }, exercise.metrics.map(metric => el('div', {},
        el('label', {}, metric),
        numberStepper(values[metric], value => { values[metric] = value; onEdit(); }),
      ))),
      previousText && el('div', { class: 'muted' }, `Previous: ${previousText}`),
    );
  }

  function historySection() {
    const list = el('div', {}, el('div', { class: 'muted' }, 'Loading…'));
    const section = trackedDetails(`${session.id}:history`, openKeys, { class: 'card' }, el('summary', {}, 'History'), list);
    const load = async () => {
      if (!section.open) return;
      const waiting = historyPending > 0 && el('p', { class: 'muted' }, `${historyPending} workout(s) waiting to sync.`);
      if (session.id.startsWith('local-')) return mount(list, waiting || el('p', { class: 'muted' }, 'Not synced yet.'));
      try {
        const logs = await api('GET', `/api/sessions/${session.id}/history`);
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
