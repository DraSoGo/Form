// Plan editor · schedule-only (exercises are edited on each day's page).
const editor = document.querySelector('#plan-editor');
const existing = JSON.parse(document.querySelector('#plan-data').textContent) || {};
const days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];
const fixed = document.querySelector('#fixed-days');
const rotation = document.querySelector('#rotation-days');
const style = document.querySelector('#id_schedule_type');

// Build the seven weekday inputs (fixed schedule only).
days.forEach((day, i) => {
  const label = document.createElement('label');
  label.textContent = day;
  const input = document.createElement('input');
  input.dataset.weekday = i;
  input.id = `weekday-${i}`;
  input.name = `weekday-${i}`;
  input.autocomplete = 'off';
  label.htmlFor = input.id;
  input.value = existing.schedule_type === 'fixed' ? (existing.schedule?.[String(i)] || 'Rest') : 'Rest';
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

function updatePreview() {
  const names = scheduledNames();
  const preview = document.querySelector('#schedule-preview');
  preview.textContent = names.length
    ? `Scheduled workout days: ${names.join(' · ')}`
    : 'No workout days yet — pick at least one non-Rest day above before saving.';
}

function visibility() {
  fixed.hidden = style.value !== 'fixed';
  rotation.hidden = style.value !== 'rotation';
  updatePreview();
}

style.addEventListener('change', visibility);
fixed.addEventListener('input', updatePreview);
rotation.addEventListener('input', updatePreview);
visibility();

// Pre-fill the hidden `exercises` field with the current plan's exercises so
// saving the schedule preserves them untouched. Day-page edits rewrite this
// value on their own.
document.querySelector('#exercises-value').value = JSON.stringify(
  Array.isArray(existing.exercises) ? existing.exercises : []
);

editor.addEventListener('submit', event => {
  const schedule = scheduleValue();
  // Inline validation only — surface the "at least one non-Rest day" rule
  // before letting the form submit.
  if (!scheduledNames().length) {
    event.preventDefault();
    document.querySelector('#schedule-preview').scrollIntoView({ block: 'center' });
    (style.value === 'fixed' ? fixed.querySelector('input') : document.querySelector('#rotation-input')).focus();
    return;
  }
  document.querySelector('#schedule-value').value = JSON.stringify(schedule);
  // `exercises-value` stays as the passthrough — set once on load and not
  // rewritten from row inputs (no rows here; edited per-day on day pages).
});