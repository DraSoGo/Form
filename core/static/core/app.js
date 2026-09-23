// Original behaviors: service worker, nav aria-current, rest timer,
// trend charts. Everything below is additive on top of the original.
if('serviceWorker' in navigator) navigator.serviceWorker.register('/sw.js');
document.querySelectorAll('nav a').forEach(a=>{if(location.pathname===a.getAttribute('href'))a.setAttribute('aria-current','page')});
let deadline=0; const output=document.querySelector('#timer');
function timer(seconds){deadline=seconds?Date.now()+seconds*1000:0;updateTimer()}
function updateTimer(){if(!output)return;if(!deadline){output.textContent='Ready';return}const left=Math.max(0,Math.ceil((deadline-Date.now())/1000));output.textContent=Math.floor(left/60)+':'+String(left%60).padStart(2,'0');if(!left){deadline=0;output.textContent='Rest complete';if(navigator.vibrate)navigator.vibrate([200,100,200]);try{const c=new(window.AudioContext||window.webkitAudioContext)();const o=c.createOscillator();o.connect(c.destination);o.start();o.stop(c.currentTime+.25)}catch{}}}
document.querySelectorAll('[data-timer]').forEach(b=>b.addEventListener('click',()=>timer(Number(b.dataset.timer))));if(output){setInterval(updateTimer,250);const rest=Number(new URLSearchParams(location.search).get('rest'));if(rest>0&&rest<=3600)timer(rest)}
const chartData=document.querySelector('#chart-data');if(chartData){const charts=JSON.parse(chartData.textContent);const holder=document.querySelector('#charts');Object.entries(charts).forEach(([name,points])=>{const card=document.createElement('section');card.className='card';const h=document.createElement('h2');h.textContent=name;card.append(h);if(!points.length){const p=document.createElement('p');p.textContent='No data in this period.';card.append(p)}else{const vals=points.map(p=>p.value),lo=Math.min(...vals),hi=Math.max(...vals),spread=hi-lo||1;const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');svg.setAttribute('viewBox','0 0 400 140');svg.setAttribute('role','img');svg.setAttribute('aria-label',name+'; range '+lo+' to '+hi);svg.classList.add('chart');const line=document.createElementNS(svg.namespaceURI,'polyline');line.setAttribute('points',points.map((p,i)=>(10+i*380/Math.max(1,points.length-1))+','+(125-(p.value-lo)/spread*110)).join(' '));line.setAttribute('fill','none');line.setAttribute('stroke','currentColor');line.setAttribute('stroke-width','3');svg.append(line);card.append(svg);const p=document.createElement('p');p.className='chart-labels';p.textContent=points[0].date+' → '+points.at(-1).date+' · '+lo.toFixed(1)+'–'+hi.toFixed(1);card.append(p);const details=document.createElement('details');const summary=document.createElement('summary');summary.textContent='View values';details.append(summary);points.forEach(point=>{const value=document.createElement('p');value.textContent=point.date+': '+point.value.toFixed(1);details.append(value)});card.append(details)}holder.append(card)})}

// =========================================================================
// Global confirm (CSP-safe replacement for inline onclick="confirm()")
// -------------------------------------------------------------------------
// Any button with data-confirm asks before doing its thing. Delegated on
// document so buttons inside server-rendered forms and JS-built tables
// are covered without inline handlers (script-src 'self').
// =========================================================================
document.addEventListener('click', (e) => {
  const btn = e.target.closest('button[data-confirm]');
  if (!btn) return;
  if (!window.confirm(btn.dataset.confirm)) e.preventDefault();
});

// =========================================================================
// Mirror <details class="pr-item"> open state onto the summary's
// aria-expanded (CSP-safe; no inline ontoggle attributes).
// =========================================================================
document.addEventListener('toggle', (e) => {
  const d = e.target;
  if (!(d instanceof HTMLDetailsElement) || !d.classList.contains('pr-item')) return;
  d.querySelector('.pr-row')?.setAttribute('aria-expanded', String(d.open));
}, true);

// =========================================================================
// Day-detail add-exercise form: toggle strength/cardio fields from the
// select's data-activity (moved out of an inline <script> for CSP).
// =========================================================================
(function initDayAddForm(){
  const form = document.getElementById('day-add-form');
  if (!form) return;
  const select = document.getElementById('day-exercise-select');
  const strength = form.querySelector('.strength-fields');
  const cardio = form.querySelector('.cardio-fields');
  const minutes = form.querySelector('input[name="minutes"]');
  if (!select || !strength || !cardio) return;
  const update = () => {
    const isCardio = select.selectedOptions[0]?.dataset.activity === 'cardio';
    strength.hidden = isCardio;
    cardio.hidden = !isCardio;
    strength.querySelectorAll('input').forEach(i => { i.disabled = isCardio; });
    cardio.querySelectorAll('input').forEach(i => { i.disabled = !isCardio; });
    if (isCardio && minutes && !minutes.value) {
      minutes.value = select.selectedOptions[0]?.dataset.defaultMinutes || '20';
    }
  };
  select.addEventListener('change', update);
  update();
})();

// =========================================================================
// Muscle map (body-muscles library)
// -------------------------------------------------------------------------
// Reads muscle_regions (asset id → 0..10 intensity) and muscle_groups
// (canonical group summary) from the JSON <script> tags emitted by the
// muscle_map.html partial, then renders a BodyChart with our green-first
// color scale. Click → live summary. Front/Back toggle reuses the same
// chart instance.
// =========================================================================

(function initMuscleMap(){
  const host = document.getElementById('muscle-chart');
  if (!host || !window.BodyMuscles || !BodyMuscles.BodyChart) return;

  const regionsEl  = document.getElementById('muscle-map-regions');
  const groupsEl   = document.getElementById('muscle-map-groups');
  if (!regionsEl || !groupsEl) return;

  let regions;
  let groups;
  try {
    regions = JSON.parse(regionsEl.textContent);
    groups  = JSON.parse(groupsEl.textContent);
  } catch (e) { return; }

  // Green-first scale for the DARK theme (overrides the library's
  // yellow→orange→red). intensity 0 → dark-neutral; 1–2 → subtle green;
  // 3–5 → mid-green; 6–7 → amber; 8–10 → muted red. Colors verified to
  // pass AA contrast on the dark surface (#18211b) and must mirror the
  // CSS legend swatches in app.css.
  // Green → red intensity ramp: brand greens at low load, rising heat to
  // red. Must mirror the CSS legend swatches in app.css.
  const SCALE = [
    '#3a463d', // 0  no data
    '#4a6b3c', // 1
    '#5d8a4e', // 2  low
    '#74a55f', // 3
    '#8bbf6e', // 4  moderate
    '#a3d47e', // 5
    '#d9b23e', // 6
    '#e0a233', // 7  high
    '#d98356', // 8
    '#d96a4e', // 9
    '#c94b40', // 10 very high
  ];
  function colorFor(intensity) {
    const i = Math.max(0, Math.min(10, Math.round(intensity || 0)));
    return SCALE[i];
  }

  // Build the bodyState mapping only for visible (current-view) regions.
  // We assign every known library id; the library filters by view.
  function buildBodyState() {
    const state = {};
    for (const id in regions) {
      const v = Number(regions[id]);
      state[id] = { intensity: v, selected: false };
    }
    return state;
  }

  // Wire click → live summary line. The library renders paths with
  // class="body-chart-muscle" and inline <title> nodes; we rely on the
  // library's onMuscleClick callback for the data.
  const summary = document.getElementById('muscle-summary');
  const LEVEL_LABELS = ['No data', 'Low', 'Low', 'Moderate', 'Moderate', 'Moderate', 'High', 'High', 'Very high', 'Very high', 'Very high'];
  function intensityForGroup(key) {
    // All regions of a group share the same intensity; take the first.
    for (const id in regions) {
      if (REGION_TO_GROUP[id] === key) return Number(regions[id] || 0);
    }
    return 0;
  }
  function setSummary(name, group, key) {
    if (!summary) return;
    if (!group) {
      summary.textContent = `${name}: no data in the last 7 days.`;
      return;
    }
    const direct   = Number(group.direct   || 0);
    const indirect = Number(group.indirect || 0);
    const intensity = key ? intensityForGroup(key) : 0;
    const level = LEVEL_LABELS[Math.max(0, Math.min(10, Math.round(intensity)))];
    summary.innerHTML = '';
    const strong = document.createElement('strong');
    strong.textContent = name;
    const levelTag = document.createElement('em');
    levelTag.textContent = ` (${level})`;
    levelTag.style.fontStyle = 'normal';
    levelTag.style.color = colorFor(intensity);
    levelTag.style.fontWeight = '700';
    summary.append(strong, levelTag, `: ${direct} direct sets, ${indirect} indirect sets in the last 7 days.`);
  }

  // Map asset region id → canonical group key. The library has ~70 ids
  // and we only need to route the canonical ones; the rest just don't
  // match and fall through to "no data". Mirrors core/muscles.py:REGIONS.
  const REGION_TO_GROUP = {
    'chest-upper-left':'chest','chest-upper-right':'chest',
    'chest-lower-left':'chest','chest-lower-right':'chest',
    'lats-upper-left':'back','lats-upper-right':'back',
    'lats-mid-left':'back','lats-mid-right':'back',
    'lats-lower-left':'back','lats-lower-right':'back',
    'traps-mid-left':'back','traps-mid-right':'back',
    'traps-lower-left':'back','traps-lower-right':'back',
    'lower-back-erectors-left':'back','lower-back-erectors-right':'back',
    'spine':'back',
    'shoulder-front-left':'shoulders','shoulder-front-right':'shoulders',
    'shoulder-side-left':'shoulders','shoulder-side-right':'shoulders',
    'deltoid-rear-left':'shoulders','deltoid-rear-right':'shoulders',
    'biceps-left':'biceps','biceps-right':'biceps',
    'triceps-long-left':'triceps','triceps-long-right':'triceps',
    'triceps-lateral-left':'triceps','triceps-lateral-right':'triceps',
    'abs-upper-left':'abs','abs-upper-right':'abs',
    'abs-lower-left':'abs','abs-lower-right':'abs',
    'obliques-left':'abs','obliques-right':'abs',
    'gluteus-maximus-left':'glutes','gluteus-maximus-right':'glutes',
    'gluteus-medius-left':'glutes','gluteus-medius-right':'glutes',
    'quads-left':'quads','quads-right':'quads',
    'hamstrings-lateral-left':'hamstrings','hamstrings-lateral-right':'hamstrings',
    'hamstrings-medial-left':'hamstrings','hamstrings-medial-right':'hamstrings',
    'calves-gastroc-lateral-left':'calves','calves-gastroc-lateral-right':'calves',
    'calves-gastroc-medial-left':'calves','calves-gastroc-medial-right':'calves',
    'calves-soleus-left':'calves','calves-soleus-right':'calves',
  };
  const groupByKey = {};
  for (const g of groups || []) groupByKey[g.key] = g;
  const KEY_LABEL = {
    chest:'Chest', back:'Back', shoulders:'Shoulders',
    biceps:'Biceps', triceps:'Triceps', abs:'Abs',
    glutes:'Glutes', quads:'Quads', hamstrings:'Hamstrings',
    calves:'Calves',
  };

  // Find a canonical group for a library region id by walking up to the
  // first dash-segment (e.g. "chest-upper-left" → "chest"). This covers
  // any new region the library adds without needing code changes here.
  function groupKeyFor(regionId) {
    if (REGION_TO_GROUP[regionId]) return REGION_TO_GROUP[regionId];
    const root = String(regionId).split('-')[0];
    return groupByKey[root] ? root : null;
  }

  // Instantiate the chart. The library draws inside the supplied element
  // and appends a wrapper; we then post-process to apply our green scale
  // (because the library's refreshPath() sets inline fill=library color).
  function mountChart(view) {
    if (chartInstance) { chartInstance.destroy(); chartInstance = null; }
    // Clear the host so the library can re-attach a wrapper.
    host.querySelectorAll('.body-chart-container').forEach(n => n.remove());
    host.dataset.mmState = 'loading';
    chartInstance = new BodyMuscles.BodyChart(host, {
      view,
      bodyState: buildBodyState(),
      ariaLabel: view === BodyMuscles.ViewSide.FRONT
        ? 'Anterior body map showing muscle training load, last 7 days'
        : 'Posterior body map showing muscle training load, last 7 days',
      enableTransitions: !window.matchMedia('(prefers-reduced-motion: reduce)').matches,
      onMuscleClick: (regionId, libraryName) => {
        const key = groupKeyFor(regionId);
        const group = key ? groupByKey[key] : null;
        const label = key ? KEY_LABEL[key] : libraryName;
        setSummary(label, group, key);
        // Update selection state (selected muscle outline)
        const next = buildBodyState();
        for (const id in next) next[id].selected = (id === regionId);
        chartInstance.update({ bodyState: next });
        // The library re-applies its color on update, so reapply ours.
        applyColors();
      },
    });
    applyColors();
    host.dataset.mmState = 'loaded';
  }

  // Override the library's yellow→orange→red gradient with our green-first
  // scale. Walk all rendered muscle paths and set fill to colorFor(intensity).
  function applyColors() {
    const paths = host.querySelectorAll('.body-chart-muscle');
    for (const p of paths) {
      const id = p.getAttribute('data-muscle-id') || (p.querySelector('title')?.textContent || '');
      // The library stores the muscleId in a closure map; we don't have
      // direct access. Use the path's <title> text to look up the region
      // id by matching against the regions dict + library export.
      const state = lookupIntensityForPath(p);
      p.style.fill = colorFor(state);
      p.setAttribute('fill', colorFor(state));
    }
  }

  // Resolve intensity for a given path. The library exposes MUSCLE_MAP
  // (all region defs with id+name+path+view). Match by `d` attribute, or
  // fall back to MUSCLE_MAP id matches via the title text.
  const MUSCLE_MAP = (BodyMuscles.MUSCLE_MAP || []).concat();
  function lookupIntensityForPath(pathEl) {
    const d = pathEl.getAttribute('d');
    if (!d) return 0;
    const def = MUSCLE_MAP.find(m => m.path === d);
    if (!def) return 0;
    return Number(regions[def.id] || 0);
  }

  let chartInstance = null;
  let currentView = BodyMuscles.ViewSide.FRONT;
  mountChart(currentView);

  // Front / Back toggle
  const frontBtn = document.getElementById('muscle-view-front');
  const backBtn  = document.getElementById('muscle-view-back');
  function setView(view) {
    currentView = view;
    if (frontBtn) frontBtn.setAttribute('aria-pressed', view === BodyMuscles.ViewSide.FRONT);
    if (backBtn)  backBtn.setAttribute('aria-pressed', view === BodyMuscles.ViewSide.BACK);
    mountChart(view);
  }
  if (frontBtn) frontBtn.addEventListener('click', () => setView(BodyMuscles.ViewSide.FRONT));
  if (backBtn)  backBtn.addEventListener('click',  () => setView(BodyMuscles.ViewSide.BACK));

  // Move the summary paragraph above the chart visually but keep it
  // outside the chart container (the library replaces the host's children
  // on re-render). Already done in template; nothing more needed here.
})();

// =========================================================================
// Exercise library search
// -------------------------------------------------------------------------
// Plain text match on name + activity_type + equipment. Hides rows whose
// data-search attribute doesn't include the query.
// =========================================================================

(function initLibrarySearch(){
  const input = document.getElementById('exercise-search');
  if (!input) return;
  const rows = document.querySelectorAll('.library-row');
  const empty = document.querySelector('.library-empty');
  const groups = document.querySelectorAll('.library-group');

  function apply() {
    const q = input.value.trim().toLowerCase();
    let anyVisible = false;
    for (const r of rows) {
      const hit = !q || (r.dataset.search || '').includes(q);
      r.dataset.hidden = hit ? 'false' : 'true';
      if (hit) anyVisible = true;
    }
    // Hide a group heading if all its rows are hidden
    for (const g of groups) {
      const any = g.querySelector('.library-row[data-hidden="false"]');
      g.style.display = any ? '' : 'none';
    }
    if (empty) empty.hidden = anyVisible;
  }
  input.addEventListener('input', apply);
  apply();
})();

// =========================================================================
// Body page: focus the weight field when navigating to #weight-field
// -------------------------------------------------------------------------
// The Weight quick-add card links to the measurement form's weight input
// wrapper. Browsers handle the scroll, but only the wrapper div gets
// focus by default — the <input> inside needs explicit focus to surface
// the mobile keyboard and on-screen picker.
// =========================================================================

(function initWeightFocus(){
  function focusOnHash(){
    const id = (location.hash || '').slice(1);
    if (!id) return;
    const wrap = document.getElementById(id);
    if (!wrap) return;
    const input = wrap.querySelector('input, select, textarea');
    if (input) input.focus({ preventScroll: false });
  }
  window.addEventListener('hashchange', focusOnHash);
  if (location.hash) focusOnHash();
})();

// =========================================================================
// Food Breakdown (entry.ai_breakdown JSON)
// -------------------------------------------------------------------------
// Schema 2 (current contract) renders a meal-oriented primary view: dish
// header with cuisine / strategy / confidence / completeness chips,
// incomplete-meal warning, "you ate" portion selector, big calorie +
// range, macro strip, unmatched list, and an advanced ingredient-details
// table with editable weights and nutrient overrides. The Apply button
// copies the fraction-adjusted totals into the main form's seven
// nutrient inputs (sugar / sodium left empty when unknown).
//
// Schema 1 (legacy) is still accepted: items fall back to bd.ingredients,
// and every new field (dish_name, strategy, completeness, unmatched,
// fraction_consumed) has a graceful default so old entries keep
// rendering with the primary view.
// =========================================================================

(function initFoodBreakdown(){
  const dataEl = document.getElementById('food-breakdown-data');
  if (!dataEl) return;

  let bd;
  try { bd = JSON.parse(dataEl.textContent); }
  catch (e) { return; }
  if (!bd) return;

  // Normalize: schema 2 uses "items"; schema 1 used "ingredients". Fall
  // back so stored schema-1 breakdowns still render.
  const items = Array.isArray(bd.items) ? bd.items
              : Array.isArray(bd.ingredients) ? bd.ingredients
              : [];
  if (!items.length && !Array.isArray(bd.unmatched)) return;

  // Per-item fraction (schema 2). Default 1.0 so schema 1 is unchanged.
  for (const ing of items) {
    if (typeof ing.fraction_consumed !== 'number') ing.fraction_consumed = 1.0;
  }

  const meta = document.getElementById('food-breakdown-meta');
  const primary = document.getElementById('food-breakdown-primary');
  const table = document.getElementById('food-breakdown-table');
  const recalcBtn = document.getElementById('breakdown-recalc');
  const applyBtn = document.getElementById('breakdown-apply');
  if (!table || !primary) return;

  const COLS = ['kcal', 'protein', 'carbs', 'fat', 'fiber', 'sodium', 'sugar'];
  const UNITS = { kcal: 'kcal', protein: 'g', carbs: 'g', fat: 'g', fiber: 'g', sodium: 'mg', sugar: 'g' };
  const MACRO_COLS = ['protein', 'carbs', 'fat', 'fiber', 'sodium', 'sugar'];
  const MACRO_LABELS = { protein: 'Protein', carbs: 'Carbs', fat: 'Fat', fiber: 'Fiber', sodium: 'Sodium', sugar: 'Sugar' };

  function round1(n) { return Math.round(n * 10) / 10; }
  function roundInt(n) { return Math.round(n); }
  function fmt(n, k) {
    if (n == null || !Number.isFinite(Number(n))) return 'Unknown';
    const v = (k === 'kcal' || k === 'sodium') ? roundInt(n) : round1(n);
    return `${v} ${UNITS[k]}`;
  }
  function fmtRange(v, k) {
    if (v == null || !Number.isFinite(Number(v))) return 'Unknown';
    if (k === 'kcal') return `${Math.round(v / 10) * 10}`;
    return `${round1(v)}`;
  }

  // Per-item compute (no fraction consumed yet — fractions apply at the
  // totals level so the editable table can recompute on weight change
  // without compounding fraction_consumed). A hand-entered cell value
  // (custom_values) wins per nutrient; the rest come from per_100g so a
  // single edited cell never discards the row's other reference values.
  function computeItem(ing) {
    const weight = Number(ing.weight_g);
    const out = {};
    for (const k of COLS) {
      const cv = ing.custom_values ? ing.custom_values[k] : null;
      if (cv != null && Number.isFinite(Number(cv))) {
        out[k] = Number(cv);
        continue;
      }
      const per100 = ing.per_100g ? ing.per_100g[k] : null;
      out[k] = (per100 == null || isNaN(per100) || !Number.isFinite(weight) || weight <= 0)
        ? null : round1(weight / 100 * per100);
    }
    return out;
  }

  // Global portion fraction — user-controlled (default 1.0 = ate it all).
  let portionFraction = 1.0;

  // ── Hidden-field serialization ─────────────────────────────────────
  // Every edit (add/remove/weight/nutrient) syncs the working items into
  // #breakdown-json so the server recomputes totals + completeness on
  // Save. The serialized shape matches what the backend expects:
  // per-item ref_key/weight/min/max/user_confirmed/fraction_consumed,
  // custom_values for hand-entered nutrients, and unmatched unchanged.
  const breakdownJsonEl = document.getElementById('breakdown-json');
  function syncBreakdownJson() {
    if (!breakdownJsonEl) return;
    const payload = {
      dish_name: bd.dish_name || '',
      cuisine: bd.cuisine || '',
      strategy: bd.strategy || 'components',
      items: items.map((ing) => ({
        ref_key: ing.ref_key || 'custom',
        name_th: ing.name_th || '',
        weight_g: Number(ing.weight_g) || 0,
        min_g: Number(ing.min_g) || 0,
        max_g: Number(ing.max_g) || 0,
        user_confirmed: !!ing.user_confirmed,
        fraction_consumed: Number(ing.fraction_consumed) || 1.0,
        custom: ing.custom === true,
        custom_values: ing.custom_values || null,
      })),
      unmatched: Array.isArray(bd.unmatched) ? bd.unmatched : [],
      confidence: bd.confidence || 'medium',
    };
    breakdownJsonEl.value = JSON.stringify(payload);
  }

  // Totals = Σ per-item computed × fraction_consumed × portionFraction.
  function computeTotals() {
    const totals = {};
    for (const k of COLS) totals[k] = 0;
    for (const ing of items) {
      const row = computeItem(ing);
      if (!row) continue;
      const frac = Number(ing.fraction_consumed || 1.0) * portionFraction;
      for (const k of COLS) {
        if (row[k] != null) totals[k] += row[k] * frac;
      }
    }
    for (const k of COLS) totals[k] = round1(totals[k]);
    return totals;
  }

  // All unknowns for one column (every per-item computation null) AND the
  // portion factor must still produce a number; if any per-item has a
  // value, the totals are usable even if partial.
  function columnAllUnknown(col) {
    return items.every((ing) => {
      const row = computeItem(ing);
      return row == null || row[col] == null;
    });
  }

  // ── Primary view (header, portion, calorie, macros, unmatched) ──────

  function renderPrimary() {
    primary.replaceChildren();

    // --- Header row: dish name + chips ---
    const header = document.createElement('div');
    header.className = 'meal-hero';

    const name = document.createElement('h3');
    name.className = 'meal-name';
    name.textContent = bd.dish_name || 'This meal';
    header.append(name);

    const chipRow = document.createElement('div');
    chipRow.className = 'meal-chips';

    if (bd.cuisine) {
      const cuisineChip = document.createElement('span');
      cuisineChip.className = 'chip planned';
      cuisineChip.textContent = `Cuisine: ${bd.cuisine}`;
      chipRow.append(cuisineChip);
    }

    if (bd.strategy) {
      const label = { whole_dish: 'Whole dish', components: 'Components', hybrid: 'Hybrid' }[bd.strategy]
                  || bd.strategy;
      const strat = document.createElement('span');
      strat.className = 'chip awaiting';
      strat.textContent = `Strategy: ${label}`;
      chipRow.append(strat);
    }

    if (bd.confidence) {
      const confChip = document.createElement('span');
      confChip.className = `chip ${
        bd.confidence === 'high'   ? 'completed' :
        bd.confidence === 'medium' ? 'in-progress' :
        bd.confidence === 'low'    ? 'awaiting'   : 'planned'
      }`;
      confChip.textContent = `Confidence: ${bd.confidence}`;
      chipRow.append(confChip);
    }

    if (bd.completeness === 'incomplete') {
      const ic = document.createElement('span');
      ic.className = 'chip failed';
      ic.textContent = 'Incomplete';
      chipRow.append(ic);
    }

    header.append(chipRow);
    primary.append(header);

    // --- Incomplete-meal warning card ---
    if (bd.completeness === 'incomplete' && Array.isArray(bd.unmatched) && bd.unmatched.length) {
      const major = bd.unmatched.filter(u => u.estimated_share === 'major');
      const names = major.length ? major.map(u => u.name_th).join(', ')
                                  : bd.unmatched.map(u => u.name_th).join(', ');
      const warning = document.createElement('div');
      warning.className = 'incomplete-warning';
      warning.setAttribute('role', 'status');
      const head = document.createElement('p');
      head.style.margin = '0 0 4px';
      head.innerHTML = '<strong>Incomplete estimate</strong> — major components missing: ' + escapeHtml(names) + '. Totals below are partial.';
      warning.append(head);
      // Per-unmatched notes
      for (const u of bd.unmatched) {
        if (!u.note) continue;
        const np = document.createElement('p');
        np.className = 'muted';
        np.style.margin = '4px 0 0';
        np.style.fontSize = '12.5px';
        np.textContent = `— ${u.name_th}: ${u.note}`;
        warning.append(np);
      }
      primary.append(warning);
    }

    // --- "You ate" portion selector ---
    const portion = document.createElement('div');
    portion.className = 'seg portion-selector';
    portion.setAttribute('role', 'radiogroup');
    portion.setAttribute('aria-label', 'You ate');

    function portionBtn(label, fraction) {
      const b = document.createElement('button');
      b.type = 'button';
      b.textContent = label;
      b.className = 'seg-btn';
      b.setAttribute('role', 'radio');
      b.dataset.fraction = String(fraction);
      b.setAttribute('aria-checked', 'false');
      if (Math.abs(portionFraction - fraction) < 1e-6) {
        b.classList.add('is-active');
        b.setAttribute('aria-checked', 'true');
      }
      return b;
    }
    portion.append(portionBtn('All', 1.0));
    portion.append(portionBtn('75%', 0.75));
    portion.append(portionBtn('Half', 0.5));

    const customWrap = document.createElement('label');
    customWrap.className = 'seg-custom';
    customWrap.textContent = 'Custom ';
    const customInput = document.createElement('input');
    customInput.type = 'number';
    customInput.min = '0';
    customInput.max = '100';
    customInput.step = '1';
    customInput.value = String(Math.round(portionFraction * 100));
    customInput.setAttribute('aria-label', 'Custom percent you ate');
    customInput.style.width = '64px';
    customInput.style.minHeight = '32px';
    customInput.style.margin = '0 4px';
    customInput.style.padding = '2px 6px';
    const customPct = document.createElement('span');
    customPct.textContent = '%';
    customWrap.append(customInput, customPct);
    portion.append(customWrap);
    primary.append(portion);

    function selectPortion(fraction) {
      portionFraction = Math.max(0, Math.min(1, Number(fraction) || 0));
      customInput.value = String(Math.round(portionFraction * 100));
      portion.querySelectorAll('button[data-fraction]').forEach(b => {
        const isActive = Math.abs(Number(b.dataset.fraction) - portionFraction) < 1e-6;
        b.classList.toggle('is-active', isActive);
        b.setAttribute('aria-checked', String(isActive));
      });
      renderCalorie();
      renderMacros();
    }
    portion.querySelectorAll('button[data-fraction]').forEach(b => {
      b.addEventListener('click', () => selectPortion(Number(b.dataset.fraction)));
    });
    customInput.addEventListener('input', () => {
      const pct = Number(customInput.value) || 0;
      selectPortion(pct / 100);
    });

    // --- Big calorie display ---
    const kcal = document.createElement('p');
    kcal.className = 'meal-kcal';
    kcal.dataset.mealKcal = '1';
    kcal.textContent = '— kcal';
    primary.append(kcal);

    const range = document.createElement('p');
    range.className = 'meal-kcal-range muted';
    range.dataset.mealRange = '1';
    range.textContent = '';
    primary.append(range);

    // --- Macro strip ---
    const macros = document.createElement('dl');
    macros.className = 'macro-strip';
    macros.setAttribute('aria-label', 'Macros');
    for (const k of MACRO_COLS) {
      const wrap = document.createElement('div');
      const dt = document.createElement('dt');
      dt.textContent = MACRO_LABELS[k];
      const dd = document.createElement('dd');
      dd.dataset.macroCol = k;
      dd.textContent = 'Unknown';
      wrap.append(dt, dd);
      macros.append(wrap);
    }
    primary.append(macros);

    // --- Uncertainty factors (Thai passthrough) ---
    if (Array.isArray(bd.uncertainty_factors_thai) && bd.uncertainty_factors_thai.length) {
      for (const note of bd.uncertainty_factors_thai) {
        const p = document.createElement('p');
        p.className = 'muted meal-uncertainty';
        p.textContent = note;
        primary.append(p);
      }
    }

    // --- Unmatched list (already shown in warning card if incomplete; here
    // show the full list separately if completeness !== 'incomplete') ---
    if (Array.isArray(bd.unmatched) && bd.unmatched.length && bd.completeness !== 'incomplete') {
      const list = document.createElement('div');
      list.className = 'unmatched-list';
      const head = document.createElement('p');
      head.className = 'muted';
      head.style.margin = '12px 0 6px';
      head.textContent = 'Components not in the meal map:';
      list.append(head);
      for (const u of bd.unmatched) {
        const item = document.createElement('div');
        item.className = 'unmatched-item';
        const nameSpan = document.createElement('span');
        nameSpan.className = 'unmatched-name';
        nameSpan.textContent = u.name_th || '';
        item.append(nameSpan);
        const shareChip = document.createElement('span');
        shareChip.className = `chip ${u.estimated_share === 'major' ? 'failed' : 'planned'}`;
        shareChip.textContent = u.estimated_share || 'minor';
        item.append(shareChip);
        if (u.note) {
          const note = document.createElement('p');
          note.className = 'muted unmatched-note';
          note.textContent = u.note;
          item.append(note);
        }
        list.append(item);
      }
      primary.append(list);
    }
  }

  // HTML-escape for safely injecting potentially-Thai names into innerHTML.
  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
  }

  // ── Live calorie + range ──

  function renderCalorie() {
    const el = primary.querySelector('[data-meal-kcal]');
    const rangeEl = primary.querySelector('[data-meal-range]');
    if (!el || !rangeEl) return;
    const totals = computeTotals();
    const kcalAllUnknown = columnAllUnknown('kcal');
    if (kcalAllUnknown) {
      el.textContent = 'Unknown kcal';
      el.classList.add('is-unknown');
    } else {
      el.classList.remove('is-unknown');
      el.textContent = `${Math.round(totals.kcal)} kcal`;
    }
    if (Array.isArray(bd.range_kcal) && bd.range_kcal.length === 2) {
      const lo = bd.range_kcal[0] * portionFraction;
      const hi = bd.range_kcal[1] * portionFraction;
      rangeEl.textContent = `≈ ${fmtRange(lo, 'kcal')}–${fmtRange(hi, 'kcal')} kcal`;
    } else {
      rangeEl.textContent = '';
    }
  }

  // ── Live macro strip ──

  function renderMacros() {
    const totals = computeTotals();
    for (const k of MACRO_COLS) {
      const cell = primary.querySelector(`[data-macro-col="${k}"]`);
      if (!cell) continue;
      if (columnAllUnknown(k)) {
        cell.textContent = 'Unknown';
        cell.classList.add('is-unknown');
      } else {
        cell.textContent = `${(k === 'sodium') ? Math.round(totals[k]) : round1(totals[k])} ${UNITS[k]}`;
        cell.classList.remove('is-unknown');
      }
    }
  }

  // ── Advanced ingredient table (existing, reading items) ──

  function chipSpan(kind, text) {
    const span = document.createElement('span');
    span.className = `chip ${kind}`;
    span.textContent = text;
    return span;
  }

  function renderHeader() {
    const thead = document.createElement('thead');
    const tr = document.createElement('tr');
    const headCells = ['Ingredient', 'Edible portion (g)', 'kcal', 'Protein', 'Carbs', 'Fat', 'Fiber', 'Sodium', 'Sugar', 'Source', ''];
    for (const label of headCells) {
      const th = document.createElement('th');
      th.textContent = label;
      if (label !== 'Ingredient' && label !== 'Source' && label !== '') th.className = 'num-cell';
      if (label === 'Edible portion (g)') th.style.textAlign = 'right';
      if (label === '') th.setAttribute('aria-label', 'Remove ingredient');
      tr.append(th);
    }
    thead.append(tr);
    table.append(thead);
  }

  function renderRow(ing, idx) {
    const tr = document.createElement('tr');
    tr.dataset.idx = String(idx);
    const isCustom = ing.custom === true;

    const nameTd = document.createElement('td');
    nameTd.className = 'ingredient-name';
    if (isCustom) {
      const nameInput = document.createElement('input');
      nameInput.type = 'text';
      nameInput.className = 'ingredient-name-input';
      nameInput.placeholder = 'Ingredient name';
      nameInput.maxLength = 80;
      nameInput.value = ing.name_th || '';
      nameInput.setAttribute('aria-label', 'Ingredient name');
      nameInput.addEventListener('input', () => { ing.name_th = nameInput.value; });
      nameTd.append(nameInput);
    } else {
      const title = document.createElement('span');
      title.textContent = ing.name_th || ing.ref_key || '';
      nameTd.append(title);
      nameTd.append(chipSpan(ing.user_confirmed ? 'completed' : 'awaiting',
                             ing.user_confirmed ? 'confirmed' : 'estimated'));
    }
    tr.append(nameTd);

    const weightTd = document.createElement('td');
    weightTd.style.textAlign = 'right';
    const input = document.createElement('input');
    input.type = 'number';
    input.className = 'weight-input num-cell';
    input.min = String(ing.min_g || 0);
    input.max = String(ing.max_g || 9999);
    input.step = '1';
    input.value = String(ing.weight_g || ing.min_g || 0);
    input.setAttribute('aria-label', `Edible portion in grams for ${ing.name_th || ing.ref_key}`);
    input.addEventListener('input', () => {
      ing.weight_g = Number(input.value) || 0;
      if (!isCustom) {
        refreshTableTotals();
        renderCalorie();
        renderMacros();
      }
    });
    weightTd.append(input);
    tr.append(weightTd);

    for (const k of COLS) {
      const td = document.createElement('td');
      td.className = 'num-cell';
      td.dataset.col = k;
      const cell = document.createElement('input');
      cell.type = 'number';
      cell.className = 'nutrient-input';
      cell.step = '0.1';
      cell.min = '0';
      cell.setAttribute('aria-label', `${k} for ${ing.name_th || ing.ref_key}`);
      cell.dataset.nutrient = k;
      const per100 = ing.per_100g && ing.per_100g[k];
      if (isCustom || per100 == null) {
        cell.value = '';
        cell.placeholder = '—';
        ing.custom_values = ing.custom_values || {};
        if (ing.custom_values[k] != null) cell.value = String(ing.custom_values[k]);
        cell.addEventListener('input', () => {
          ing.custom_values = ing.custom_values || {};
          ing.custom_values[k] = cell.value === '' ? null : Number(cell.value);
          refreshTableTotals();
          renderCalorie();
          renderMacros();
        });
      } else {
        // Show the stored hand edit when present, else the scaled
        // reference value (blanking the cell reverts to reference).
        const showValue = () => (ing.custom_values && ing.custom_values[k] != null)
          ? String(ing.custom_values[k])
          : String(round1((ing.weight_g || 0) / 100 * per100));
        cell.value = showValue();
        cell.addEventListener('input', () => {
          ing.custom_values = ing.custom_values || {};
          ing.custom_values[k] = cell.value === '' ? null : Number(cell.value);
          refreshTableTotals();
          renderCalorie();
          renderMacros();
        });
        input.addEventListener('input', () => {
          if (ing.custom_values && ing.custom_values[k] != null) return;
          cell.value = showValue();
        });
      }
      td.append(cell);
      tr.append(td);
    }

    const sourceTd = document.createElement('td');
    sourceTd.className = 'source-cell';
    sourceTd.title = isCustom ? 'User-entered' : (ing.source || '');
    sourceTd.textContent = isCustom ? 'User-entered' : (ing.source || '');
    tr.append(sourceTd);

    const removeTd = document.createElement('td');
    const removeBtn = document.createElement('button');
    removeBtn.type = 'button';
    removeBtn.className = 'secondary breakdown-remove-row';
    removeBtn.textContent = '×';
    removeBtn.setAttribute('aria-label', 'Remove ingredient');
    removeBtn.addEventListener('click', () => {
      const i = items.indexOf(ing);
      if (i > -1) { items.splice(i, 1); tr.remove(); refreshTableTotals(); renderCalorie(); renderMacros(); }
    });
    removeTd.append(removeBtn);
    tr.append(removeTd);

    return tr;
  }

  function renderBody() {
    const tbody = document.createElement('tbody');
    items.forEach((ing, idx) => { tbody.append(renderRow(ing, idx)); });
    table.append(tbody);
  }

  function renderFoot() {
    const tfoot = document.createElement('tfoot');
    const tr = document.createElement('tr');
    const label = document.createElement('td');
    label.className = 'totals-name';
    label.colSpan = 2;
    label.textContent = 'Totals';
    tr.append(label);
    for (const k of COLS) {
      const td = document.createElement('td');
      td.className = 'num-cell';
      td.dataset.totalCol = k;
      tr.append(td);
    }
    const sourcePlaceholder = document.createElement('td');
    sourcePlaceholder.colSpan = 1;
    tr.append(sourcePlaceholder);
    tfoot.append(tr);

    const rangeTr = document.createElement('tr');
    const rangeLabel = document.createElement('td');
    rangeLabel.className = 'range-line';
    rangeLabel.colSpan = 2;
    rangeLabel.textContent = '';
    rangeTr.append(rangeLabel);
    const rangeSpan = document.createElement('td');
    rangeSpan.className = 'range-line';
    rangeSpan.colSpan = 8;
    rangeSpan.dataset.rangeCell = '1';
    rangeTr.append(rangeSpan);
    tfoot.append(rangeTr);

    table.append(tfoot);
  }

  // Table's totals row reflects per-item × fraction_consumed only
  // (NOT portionFraction — the table shows what's on the plate; the
  // primary hero reflects what was eaten after portion adjustment).
  function computeTableTotals() {
    const totals = {};
    for (const k of COLS) totals[k] = 0;
    for (const ing of items) {
      const row = computeItem(ing);
      if (!row) continue;
      const frac = Number(ing.fraction_consumed || 1.0);
      for (const k of COLS) {
        if (row[k] != null) totals[k] += row[k] * frac;
      }
    }
    for (const k of COLS) totals[k] = round1(totals[k]);
    return totals;
  }

  function refreshTableTotals() {
    const totals = computeTableTotals();
    for (const k of COLS) {
      const cell = table.querySelector(`td[data-total-col="${k}"]`);
      if (!cell) continue;
      const allUnknown = items.every((ing) => {
        const row = computeItem(ing);
        return row == null || row[k] == null;
      });
      if (allUnknown) {
        cell.textContent = 'Unknown';
        cell.classList.add('is-unknown');
      } else {
        cell.textContent = `${(k === 'kcal' || k === 'sodium') ? Math.round(totals[k]) : round1(totals[k])} ${UNITS[k]}`;
        cell.classList.remove('is-unknown');
      }
    }
    const rangeCell = table.querySelector('[data-range-cell]');
    if (rangeCell && Array.isArray(bd.range_kcal) && bd.range_kcal.length === 2) {
      // Table range shows the "on the plate" range (no portionFraction).
      rangeCell.textContent = `≈ ${bd.range_kcal[0]}–${bd.range_kcal[1]} kcal`;
    }
    // Every table refresh means the items changed — keep the hidden
    // field in sync so Save persists the edited breakdown.
    syncBreakdownJson();
  }

  // ── Build the page ──

  renderPrimary();
  renderCalorie();
  renderMacros();

  if (items.length) {
    renderHeader();
    renderBody();
    renderFoot();
    refreshTableTotals();
  } else {
    syncBreakdownJson();  // even the initial state must be serializable
  }

  // Also serialize right before the form submits (covers portion-button
  // changes that don't run refreshTableTotals).
  const editForm = document.querySelector('form.card[method="post"]');
  if (editForm && breakdownJsonEl) {
    editForm.addEventListener('submit', syncBreakdownJson, true);  // capture phase
  }

  if (recalcBtn) {
    recalcBtn.addEventListener('click', () => {
      refreshTableTotals();
      renderCalorie();
      renderMacros();
    });
  }

  const addBtn = document.getElementById('breakdown-add-row');
  if (addBtn) {
    addBtn.addEventListener('click', () => {
      const ing = {
        custom: true,
        ref_key: 'custom',
        name_th: '',
        weight_g: 0,
        min_g: 0,
        max_g: 9999,
        user_confirmed: true,
        per_100g: null,
        custom_values: {},
        fraction_consumed: 1.0,
      };
      items.push(ing);
      const tbody = table.querySelector('tbody');
      tbody.append(renderRow(ing, items.length - 1));
      refreshTableTotals();
      renderCalorie();
      renderMacros();
      const nameInput = tbody.lastElementChild.querySelector('.ingredient-name-input');
      if (nameInput) nameInput.focus();
    });
  }

  if (applyBtn) {
    applyBtn.addEventListener('click', () => {
      // Apply uses the portion-adjusted totals (the user's "you ate" value).
      const totals = computeTotals();
      const form = document.querySelector('form.card[method="post"]');
      if (!form) return;
      for (const k of COLS) {
        const input = form.querySelector(`input[name="${k}"]`);
        if (!input) continue;
        const allUnknown = items.every((ing) => {
          const row = computeItem(ing);
          return row == null || row[k] == null;
        });
        // Unknown nutrients stay empty so the saved entry keeps NULL.
        if (allUnknown) { input.value = ''; continue; }
        input.value = (k === 'kcal' || k === 'sodium') ? String(Math.round(totals[k])) : String(round1(totals[k]));
      }
      const saveBtn = form.querySelector('button[type="submit"], button:not([type="button"])');
      if (saveBtn) saveBtn.scrollIntoView({ block: 'center', behavior: 'smooth' });
    });
  }
})();