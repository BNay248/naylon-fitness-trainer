// Offline support for the Sessions page.
//
// Every session change (create, edit, delete, log workout) is written to a per-user queue in localStorage first,
// shown immediately by overlaying the queue on the last data fetched from the server, and then sent in order.
// Anything the server rejects (e.g. an athlete's edit that lost to a newer coach edit) is dropped with a notice.

function uuid() {
  if (window.crypto && crypto.randomUUID) return crypto.randomUUID();
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, c => {
    const r = Math.random() * 16 | 0;
    return (c === 'x' ? r : (r & 0x3 | 0x8)).toString(16);
  });
}

const store = {
  key: name => `trainer:${ME.username}:${name}`,
  get(name, fallback) {
    try { return JSON.parse(localStorage.getItem(store.key(name))) ?? fallback; } catch { return fallback; }
  },
  set(name, value) {
    try { localStorage.setItem(store.key(name), JSON.stringify(value)); } catch {}
  },
};

const drafts = {
  get: id => store.get('drafts', {})[id] || null,
  set(id, value) { const all = store.get('drafts', {}); all[id] = value; store.set('drafts', all); },
  clear(id) { const all = store.get('drafts', {}); delete all[id]; store.set('drafts', all); },
  rename(from, to) { const all = store.get('drafts', {}); if (all[from]) { all[to] = all[from]; delete all[from]; store.set('drafts', all); } },
};

const SyncQueue = {
  load: () => store.get('queue', []),
  save: queue => store.set('queue', queue),

  push(op) {
    const queue = SyncQueue.load();
    queue.push({ id: uuid(), queued_at: new Date().toISOString(), ...op });
    SyncQueue.save(queue);
  },

  inFlight: null,

  // Deleting a session that never reached the server just cancels everything queued for it —
  // unless its create is being sent right now, in which case a delete is queued behind it.
  dropLocalSession(localId) {
    const queue = SyncQueue.load().filter(op => op.session_id !== localId);
    const create = queue.find(op => op.kind === 'create' && op.local_id === localId);
    if (create && create.id === SyncQueue.inFlight) {
      SyncQueue.save(queue);
      SyncQueue.push({ kind: 'delete', session_id: localId, base_version: 0 });
    } else {
      SyncQueue.save(queue.filter(op => op !== create));
    }
    drafts.clear(localId);
  },
};

// Apply queued operations to server data so the UI reflects changes that haven't synced yet.
function overlayQueue(serverData, queue, catalog) {
  const data = clone(serverData);
  const groups = () => [data.mine, ...data.clients.map(client => client.sessions)];
  const find = id => groups().flat().find(session => session.id === id);
  const pendingLogs = {};

  for (const op of queue) {
    if (op.kind === 'create') {
      const owner = op.body.assigned_to || ME.username;
      const session = {
        id: op.local_id, name: op.body.name, user_id: owner, coach_username: ME.username, version: 0,
        supersets: normalizeStructure(op.body.supersets, catalog), can_delete: true, previous: {}, pending: true,
      };
      const group = owner === ME.username ? data.mine : data.clients.find(client => client.username === owner)?.sessions;
      if (group) group.push(session);
    } else if (op.kind === 'update') {
      const session = find(op.session_id);
      if (session) Object.assign(session, { name: op.body.name, supersets: normalizeStructure(op.body.supersets, catalog), pending: true });
    } else if (op.kind === 'delete') {
      for (const group of groups()) {
        const idx = group.findIndex(session => session.id === op.session_id);
        if (idx >= 0) group.splice(idx, 1);
      }
    } else if (op.kind === 'log') {
      pendingLogs[op.session_id] = (pendingLogs[op.session_id] || 0) + 1;
      const session = find(op.session_id);
      if (!session) continue;
      if (structureKey(session.supersets) === structureKey(op.body.supersets)) session.supersets = clone(op.body.supersets);
      for (const superset of op.body.supersets) {
        for (const exercise of superset.exercises) {
          session.previous[exercise.name] = { created_at: op.body.logged_at, instances: clone(exercise.instances) };
        }
      }
    }
  }
  const byName = (a, b) => a.name.toLowerCase().localeCompare(b.name.toLowerCase());
  groups().forEach(group => group.sort(byName));
  return { data, pendingLogs };
}

// Send queued operations one at a time, in order. Stops at the first network/server failure and retries later.
let flushing = null;
function flushQueue(onNotice) {
  flushing = flushing || (async () => {
    let queue = SyncQueue.load();
    while (queue.length) {
      const op = queue[0];
      let result = null;
      let drop = false;
      try {
        SyncQueue.inFlight = op.id;
        result = await sendOp(op);
      } catch (err) {
        if (err.status === 0 || err.status === 401 || err.status >= 500) break; // offline, logged out, or server down
        onNotice(err.message);
        drop = true;
      }
      queue = SyncQueue.load().filter(next => next.id !== op.id); // re-read: it may have changed while awaiting
      if (op.kind === 'create' && drop) {
        queue = queue.filter(next => next.session_id !== op.local_id);
      } else if (op.kind === 'create') {
        // Point everything queued against the temporary id at the real session.
        queue.forEach(next => { if (next.session_id === op.local_id) next.session_id = result.id; });
        drafts.rename(op.local_id, result.id);
        renameOpenKeys(op.local_id, result.id);
      }
      SyncQueue.inFlight = null;
      SyncQueue.save(queue);
      if (!drop && op.kind === 'log') {
        const name = op.body.session_name;
        if (result.session_deleted) onNotice(`"${name}" was deleted before your workout synced. The workout was still recorded.`);
        else if (!result.session_updated) onNotice(`"${name}" was changed before your workout synced, so it was saved to history only.`);
      }
    }
  })().finally(() => { flushing = null; SyncQueue.inFlight = null; });
  return flushing;
}

function sendOp(op) {
  const id = encodeURIComponent(op.session_id || '');
  switch (op.kind) {
    case 'create': return api('POST', '/api/sessions', { ...op.body, client_id: op.id });
    case 'update': return api('PUT', `/api/sessions/${id}`, { ...op.body, base_version: op.base_version });
    case 'delete': return api('DELETE', `/api/sessions/${id}?base_version=${op.base_version}`);
    case 'log': return api('POST', `/api/sessions/${id}/log`, { ...op.body, client_id: op.id });
  }
  return Promise.resolve();
}

// Open-section keys are prefixed with the session id; carry them over when a local session gets its real id.
const openKeys = new Set();
function renameOpenKeys(from, to) {
  [...openKeys].filter(key => key === from || key.startsWith(`${from}:`)).forEach(key => {
    openKeys.delete(key);
    openKeys.add(to + key.slice(from.length));
  });
}

// Bottom banner: shows while offline or while changes wait to sync (after a short delay, to avoid flicker).
let bannerTimer = null;
function updateSyncBanner(offline) {
  const banner = document.getElementById('sync-status') || document.body.appendChild(el('div', { id: 'sync-status', class: 'status-banner' }));
  const describe = () => {
    const count = SyncQueue.load().length;
    if (count) return `${count} change${count === 1 ? '' : 's'} waiting to sync${offline ? ' (offline)' : ''}…`;
    return offline ? 'Offline: showing saved data' : '';
  };
  if (!describe()) {
    clearTimeout(bannerTimer);
    bannerTimer = null;
    banner.classList.remove('visible');
    return;
  }
  if (banner.classList.contains('visible')) { banner.textContent = describe(); return; }
  if (bannerTimer) return;
  bannerTimer = setTimeout(() => {
    bannerTimer = null;
    const text = describe();
    banner.textContent = text;
    banner.classList.toggle('visible', !!text);
  }, 3000);
}
