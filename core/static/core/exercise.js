const exerciseForm = document.querySelector('[data-exercise-form]');
if (exerciseForm) {
  const activity = exerciseForm.querySelector('#id_activity_type');
  const minutes = exerciseForm.querySelector('#id_default_minutes');
  const cardioFields = exerciseForm.querySelector('[data-cardio-fields]');
  const strengthFields = exerciseForm.querySelector('[data-strength-fields]');
  const cardioNote = exerciseForm.querySelector('[data-cardio-note]');
  const updateExerciseType = () => {
    const cardio = activity.value === 'cardio';
    cardioFields.hidden = !cardio;
    strengthFields.hidden = cardio;
    cardioNote.hidden = !cardio;
    minutes.required = cardio;
    if (cardio && !minutes.value) minutes.value = '20';
  };
  activity.addEventListener('change', updateExerciseType);
  updateExerciseType();
}
