// Shared pickers for the exercise library (exercise form, client profiles, templates).

const LEVELS = ['beginner', 'intermediate', 'advanced'];
const levelLabel = level => level ? level[0].toUpperCase() + level.slice(1) : '';

// A collapsible set of on/off chips in labelled sections ([{label, items}]); returns {node, read(), set(ids), reset()}.
function chipPicker(title, sections, selectedIds) {
  const selected = new Set(selectedIds || []);
  const summary = el('span', { class: 'muted' });
  const chips = [];
  const draw = () => {
    chips.forEach(({ chip, item }) => chip.classList.toggle('on', selected.has(item.id)));
    summary.textContent = selected.size ? `${selected.size} selected` : 'None selected';
  };
  const rows = sections.filter(section => section.items.length).map(section => el('div', { class: 'muscle-group' },
    el('span', { class: 'muted' }, section.label),
    el('div', { class: 'chips' }, section.items.map(item => {
      const chip = el('span', { class: 'chip', title: item.description || '', onclick: () => {
        selected.has(item.id) ? selected.delete(item.id) : selected.add(item.id);
        draw();
      } }, item.name);
      chips.push({ chip, item });
      return chip;
    }))));
  draw();
  return {
    node: el('details', { class: 'card' }, el('summary', {}, el('span', {}, title), summary),
      rows.length ? rows : el('p', { class: 'muted' }, 'Nothing has been set up yet.')),
    read: () => [...selected],
    set(ids) { selected.clear(); ids.forEach(id => selected.add(id)); draw(); },
    reset() { selected.clear(); draw(); },
  };
}

// Sections of library items by their type/kind, in the configured order.
const bySection = (items, key, order) => order.map(label => ({ label, items: items.filter(item => item[key] === label) }));

// Equipment picker sectioned by type, for a client's training profile.
const equipmentPicker = (library, selectedIds, title = 'Equipment') =>
  chipPicker(title, bySection(library.equipment, 'type', library.equipment_types), selectedIds);

// Difficulty level <select>.
const levelSelect = current => el('select', {}, LEVELS.map(level => el('option', { value: level, selected: level === current }, levelLabel(level))));
