const editor = document.querySelector('#plan-editor');
const existing = JSON.parse(document.querySelector('#plan-data').textContent) || {};
const days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];
const fixed = document.querySelector('#fixed-days');
const rotation = document.querySelector('#rotation-days');
const style = document.querySelector('#id_schedule_type');
const rows = document.querySelector('#plan-rows');
const error = document.querySelector('#plan-error');
days.forEach((day, i) => {
  const label = document.createElement('label');
  label.textContent = day;
  const input = document.createElement('input');
  input.dataset.weekday = i;
  input.id = `weekday-${i}`;
  input.name = `weekday-${i}`;
  input.autocomplete = 'off';
  label.htmlFor = input.id;
  input.value = existing.schedule_type === 'fixed' ? existing.schedule?.[String(i)] || 'Rest' : 'Rest';
  input.maxLength = 80;
  label.append(input);
  fixed.append(label);
});
if (existing.schedule_type === 'rotation' && Array.isArray(existing.schedule)) {
  document.querySelector('#rotation-input').value = existing.schedule.join(', ');
}
function scheduleValue() {
  return style.value === 'fixed'
    ? Object.fromEntries([...fixed.querySelectorAll('input')].map(input => [input.dataset.weekday, input.value.trim() || 'Rest']))
    : document.querySelector('#rotation-input').value.split(',').map(s => s.trim()).filter(Boolean);
}
function updateDays() {
  const names = [...new Set(Object.values(scheduleValue()))].filter(name => name !== 'Rest');
  const list = document.querySelector('#workout-day-names');
  list.replaceChildren(...names.map(name => {
    const option = document.createElement('option');
    option.value = name;
    return option;
  }));
}
function visibility() {
  fixed.hidden = style.value !== 'fixed';
  rotation.hidden = style.value !== 'rotation';
  updateDays();
}
style.addEventListener('change', visibility);
fixed.addEventListener('input', updateDays);
rotation.addEventListener('input', updateDays);
visibility();
function addRow(data = {}, focus = false) {
  const fragment = document.querySelector('#plan-row-template').content.cloneNode(true);
  const row = fragment.querySelector('.plan-row');
  const rowIndex = rows.children.length;
  row.querySelector('[data-field="day"]').value = Object.values(scheduleValue()).find(day => day !== 'Rest') || 'Workout';
  row.querySelectorAll('[data-field]').forEach(input => {
    input.name = `exercise-${rowIndex}-${input.dataset.field}`;
    if (data[input.dataset.field] != null) input.value = data[input.dataset.field];
  });
  const select = row.querySelector('[data-field="exercise"]');
  const updateActivity = () => {
    const cardio = select.selectedOptions[0]?.dataset.activity === 'cardio';
    row.querySelector('.strength-fields').hidden = cardio;
    row.querySelector('.cardio-fields').hidden = !cardio;
    row.querySelectorAll('.strength-fields input').forEach(input => { input.disabled = cardio; });
    row.querySelectorAll('.cardio-fields input').forEach(input => { input.disabled = !cardio; });
  };
  select.addEventListener('change', updateActivity);
  updateActivity();
  row.querySelector('.remove-row').addEventListener('click', () => {
    row.remove();
    document.querySelector('#add-plan-row').focus();
  });
  rows.append(fragment);
  if (focus) row.querySelector('select').focus();
}
document.querySelector('#add-plan-row').addEventListener('click', () => addRow({}, true));
if (Array.isArray(existing.exercises)) existing.exercises.forEach(data => addRow(data));
editor.addEventListener('submit', event => {
  const schedule = scheduleValue();
  const names = Object.values(schedule);
  const exercises = [...rows.querySelectorAll('.plan-row')].map((row, i) => {
    const value = { order: i + 1 };
    row.querySelectorAll('[data-field]:not(:disabled)').forEach(input => {
      value[input.dataset.field] = input.type === 'number'
        ? (input.value === '' ? null : Number(input.value)) : input.value.trim();
    });
    return value;
  });
  let message = '';
  if (!names.length) message = 'Add at least one day to your rotation.';
  else if (exercises.some(row => !names.includes(row.day) || row.day === 'Rest')) message = 'Each exercise needs a workout day from your schedule, other than Rest.';
  else if (exercises.some(row => row.rep_min > row.rep_max)) message = 'Minimum reps must be no higher than maximum reps.';
  error.textContent = message;
  error.hidden = !message;
  if (message) {
    event.preventDefault();
    error.scrollIntoView({ block: 'center' });
    return;
  }
  document.querySelector('#schedule-value').value = JSON.stringify(schedule);
  document.querySelector('#exercises-value').value = JSON.stringify(exercises);
});
