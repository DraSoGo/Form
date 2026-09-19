const editor = document.querySelector('#plan-editor');
const existing = JSON.parse(document.querySelector('#plan-data').textContent) || {};
const days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];
const fixed = document.querySelector('#fixed-days');
const rotation = document.querySelector('#rotation-days');
const style = document.querySelector('#id_schedule_type');
const rows = document.querySelector('#plan-rows');
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
function scheduledNames() {
  return [...new Set(Object.values(scheduleValue()))].filter(name => name !== 'Rest');
}
function setDayError(select, message) {
  const holder = select.closest('.day-field');
  const errorText = holder.querySelector('.day-error');
  errorText.textContent = message || '';
  errorText.hidden = !message;
}
// Rebuild every row's day <select> options from the current schedule.
// - Existing assignments that still exist are preserved and selected.
// - Assignments that no longer exist stay as an explicit invalid option
//   with an inline error explaining the mismatch.
// - No workout days at all: selector disabled with guidance.
function updateDays() {
  const names = scheduledNames();
  const preview = document.querySelector('#schedule-preview');
  preview.textContent = names.length
    ? `Scheduled workout days: ${names.join(' · ')}`
    : 'No workout days yet — exercises need at least one non-Rest day above.';
  rows.querySelectorAll('.plan-row').forEach(row => {
    const select = row.querySelector('[data-field="day"]');
    const current = select.dataset.current || select.value;
    select.replaceChildren(...names.map(name => {
      const option = document.createElement('option');
      option.value = name;
      option.textContent = name;
      return option;
    }));
    if (!names.length) {
      select.disabled = true;
      select.dataset.current = '';
      setDayError(select, 'Add at least one workout day to the weekly schedule first.');
      return;
    }
    select.disabled = false;
    if (names.includes(current)) {
      select.value = current;
      select.dataset.current = current;
      setDayError(select, '');
    } else if (current) {
      // Keep the stale assignment visible so the user sees exactly what
      // no longer matches, with a clear explanation.
      const stale = document.createElement('option');
      stale.value = current;
      stale.textContent = `${current} (not in schedule)`;
      select.prepend(stale);
      select.value = current;
      select.dataset.current = current;
      setDayError(select, `${current} is not in this weekly schedule. Add a ${current} day above or choose ${names[0]}.`);
    } else {
      select.value = names[0];
      select.dataset.current = names[0];
      setDayError(select, '');
    }
  });
  document.querySelector('#add-plan-row').disabled = !names.length;
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
  const names = scheduledNames();
  const daySelect = row.querySelector('[data-field="day"]');
  daySelect.dataset.current = data.day || names[0] || '';
  daySelect.replaceChildren(...names.map(name => {
    const option = document.createElement('option');
    option.value = name;
    option.textContent = name;
    return option;
  }));
  if (!names.length) daySelect.disabled = true;
  row.querySelectorAll('[data-field]').forEach(input => {
    input.name = `exercise-${rowIndex}-${input.dataset.field}`;
    if (data[input.dataset.field] != null) input.value = data[input.dataset.field];
  });
  const select = row.querySelector('[data-field="exercise"]');
  const updateActivity = (resetDuration = false) => {
    const cardio = select.selectedOptions[0]?.dataset.activity === 'cardio';
    row.querySelector('.strength-fields').hidden = cardio;
    row.querySelector('.cardio-fields').hidden = !cardio;
    row.querySelectorAll('.strength-fields input').forEach(input => { input.disabled = cardio; });
    row.querySelectorAll('.cardio-fields input').forEach(input => { input.disabled = !cardio; });
    const minutes = row.querySelector('[data-field="minutes"]');
    if (cardio && (resetDuration || data.minutes == null)) {
      minutes.value = select.selectedOptions[0]?.dataset.defaultMinutes || '20';
    }
  };
  select.addEventListener('change', () => updateActivity(true));
  daySelect.addEventListener('change', () => {
    daySelect.dataset.current = daySelect.value;
    setDayError(daySelect, '');
  });
  updateActivity();
  row.querySelector('.remove-row').addEventListener('click', () => {
    row.remove();
    document.querySelector('#add-plan-row').focus();
  });
  rows.append(fragment);
  updateDays();
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
  // Inline validation only: field-specific errors next to their inputs.
  let firstInvalid = null;
  if (!scheduledNames().length) {
    rows.querySelectorAll('[data-field="day"]').forEach(select =>
      setDayError(select, 'Add at least one workout day to the weekly schedule first.'));
    firstInvalid = document.querySelector('#fixed-days, #rotation-days');
  } else {
    exercises.forEach((row, i) => {
      const select = rows.querySelectorAll('.plan-row')[i].querySelector('[data-field="day"]');
      if (!names.includes(row.day) || row.day === 'Rest') {
        setDayError(select, `${row.day || 'This day'} is not in this weekly schedule. Add it above or choose ${scheduledNames()[0]}.`);
        firstInvalid ||= select;
      } else {
        setDayError(select, '');
      }
    });
    exercises.forEach((row, i) => {
      if (row.rep_min > row.rep_max) {
        const repMin = rows.querySelectorAll('.plan-row')[i].querySelector('[data-field="rep_min"]');
        repMin.setCustomValidity('Minimum reps must be no higher than maximum reps.');
        repMin.reportValidity();
        firstInvalid ||= repMin;
      }
    });
  }
  if (firstInvalid) {
    event.preventDefault();
    firstInvalid.scrollIntoView({ block: 'center' });
    firstInvalid.focus?.();
    return;
  }
  document.querySelector('#schedule-value').value = JSON.stringify(schedule);
  document.querySelector('#exercises-value').value = JSON.stringify(exercises);
});
