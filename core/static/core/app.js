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
// Reads the JSON emitted by food_form.html and renders a per-ingredient
// table with editable weights, live recompute, totals row, kcal-range
// line, and "Apply to nutrition fields" that copies the totals into the
// main form's seven nutrient inputs. No backend calls — fully client
// deterministic. Unknown values stay "Unknown" in the
// table and clear the corresponding main-form input on Apply.
// =========================================================================

(function initFoodBreakdown(){
  const dataEl = document.getElementById('food-breakdown-data');
  if (!dataEl) return;

  let bd;
  try { bd = JSON.parse(dataEl.textContent); }
  catch (e) { return; }
  if (!bd || !Array.isArray(bd.ingredients)) return;

  const meta = document.getElementById('food-breakdown-meta');
  const table = document.getElementById('food-breakdown-table');
  const recalcBtn = document.getElementById('breakdown-recalc');
  const applyBtn = document.getElementById('breakdown-apply');
  if (!table) return;

  const COLS = ['kcal', 'protein', 'carbs', 'fat', 'fiber', 'sodium', 'sugar'];
  const UNITS = { kcal: 'kcal', protein: 'g', carbs: 'g', fat: 'g', fiber: 'g', sodium: 'mg', sugar: 'g' };

  function round1(n) { return Math.round(n * 10) / 10; }

  function computeRow(ing) {
    const out = {};
    // Direct user edits (custom_values) override the per-100g computation.
    if (ing.custom_values) {
      let anySet = false;
      for (const k of COLS) {
        if (ing.custom_values[k] != null && Number.isFinite(Number(ing.custom_values[k]))) {
          out[k] = Number(ing.custom_values[k]); anySet = true;
        } else { out[k] = null; }
      }
      if (anySet) return out;
    }
    const weight = Number(ing.weight_g);
    if (!Number.isFinite(weight) || weight <= 0) return null;
    if (!ing.per_100g) return null;
    for (const k of COLS) {
      const per100 = ing.per_100g[k];
      out[k] = (per100 == null || isNaN(per100)) ? null : round1(weight / 100 * per100);
    }
    return out;
  }

  function renderMeta() {
    if (!meta) return;
    meta.replaceChildren();
    const conf = bd.confidence || 'unknown';
    const confChip = document.createElement('span');
    confChip.className = `chip ${
      conf === 'high' ? 'completed' :
      conf === 'medium' ? 'in-progress' :
      conf === 'low' ? 'awaiting' : 'planned'
    }`;
    confChip.textContent = `Confidence: ${conf}`;
    meta.append(confChip);

    if (Array.isArray(bd.range_kcal) && bd.range_kcal.length === 2) {
      const lo = Math.round(bd.range_kcal[0]);
      const hi = Math.round(bd.range_kcal[1]);
      const span = document.createElement('span');
      span.className = 'muted';
      span.textContent = `≈ ${lo}–${hi} kcal`;
      meta.append(span);
    }

    if (Array.isArray(bd.unknown_fields) && bd.unknown_fields.length) {
      const u = document.createElement('span');
      u.className = 'muted';
      u.textContent = `Unknown: ${bd.unknown_fields.join(', ')}`;
      meta.append(u);
    }

    // Uncertainty factors (Thai text, rendered as-is per the contract).
    if (Array.isArray(bd.uncertainty_factors_thai) && bd.uncertainty_factors_thai.length) {
      for (const note of bd.uncertainty_factors_thai) {
        const p = document.createElement('p');
        p.className = 'muted';
        p.style.margin = '4px 0 0';
        p.style.fontSize = '12.5px';
        p.textContent = note;
        meta.append(p);
      }
    }
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

  function chipSpan(kind, text) {
    const span = document.createElement('span');
    span.className = `chip ${kind}`;
    span.textContent = text;
    return span;
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
      if (!isCustom) refreshTotals();
    });
    weightTd.append(input);
    tr.append(weightTd);

    // Nutrient cells: editable inputs. Reference rows recalculate from
    // per-100g when the weight changes, but direct edits override the
    // computed value until the weight changes again. Custom rows are
    // always free-form.
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
          refreshTotals();
        });
      } else {
        cell.value = String(round1((ing.weight_g || 0) / 100 * per100));
        cell.addEventListener('input', () => {
          ing.custom_values = ing.custom_values || {};
          ing.custom_values[k] = cell.value === '' ? null : Number(cell.value);
          refreshTotals();
        });
        const weightListener = () => {
          if (ing.custom_values && ing.custom_values[k] != null) return;
          cell.value = String(round1((ing.weight_g || 0) / 100 * per100));
        };
        input.addEventListener('input', weightListener);
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
      const i = bd.ingredients.indexOf(ing);
      if (i > -1) { bd.ingredients.splice(i, 1); tr.remove(); refreshTotals(); }
    });
    removeTd.append(removeBtn);
    tr.append(removeTd);

    return tr;
  }

  function renderBody() {
    const tbody = document.createElement('tbody');
    bd.ingredients.forEach((ing, idx) => {
      tbody.append(renderRow(ing, idx));
    });
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

  function computeTotals() {
    const totals = {};
    for (const k of COLS) totals[k] = 0;
    for (const ing of bd.ingredients) {
      const row = computeRow(ing);
      if (!row) continue;
      for (const k of COLS) {
        if (row[k] != null) totals[k] += row[k];
      }
    }
    for (const k of COLS) totals[k] = round1(totals[k]);
    return totals;
  }

  function refreshTotals() {
    const totals = computeTotals();
    // Row cells are now live inputs — only refresh totals + range.
    for (const k of COLS) {
      const cell = table.querySelector(`td[data-total-col="${k}"]`);
      if (!cell) continue;
      const allUnknown = bd.ingredients.every((ing) => {
        const row = computeRow(ing);
        return row == null || row[k] == null;
      });
      if (allUnknown) {
        cell.textContent = 'Unknown';
        cell.classList.add('is-unknown');
      } else {
        cell.textContent = `${totals[k]} ${UNITS[k]}`;
        cell.classList.remove('is-unknown');
      }
    }
    const rangeCell = table.querySelector('[data-range-cell]');
    if (rangeCell && Array.isArray(bd.range_kcal) && bd.range_kcal.length === 2) {
      rangeCell.textContent = `≈ ${Math.round(bd.range_kcal[0])}–${Math.round(bd.range_kcal[1])} kcal`;
    }
  }

  // Build the table.
  renderMeta();
  renderHeader();
  renderBody();
  renderFoot();
  refreshTotals();

  if (recalcBtn) recalcBtn.addEventListener('click', refreshTotals);

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
      };
      bd.ingredients.push(ing);
      const tbody = table.querySelector('tbody');
      tbody.append(renderRow(ing, bd.ingredients.length - 1));
      refreshTotals();
      const nameInput = tbody.lastElementChild.querySelector('.ingredient-name-input');
      if (nameInput) nameInput.focus();
    });
  }

  if (applyBtn) {
    applyBtn.addEventListener('click', () => {
      const totals = computeTotals();
      const form = document.querySelector('form.card[method="post"]');
      if (!form) return;
      for (const k of COLS) {
        const input = form.querySelector(`input[name="${k}"]`);
        if (!input) continue;
        const allUnknown = bd.ingredients.every((ing) => {
          const row = computeRow(ing);
          return row == null || row[k] == null;
        });
        // Unknown nutrients stay empty so the saved entry keeps NULL.
        input.value = allUnknown ? '' : String(totals[k]);
      }
      const saveBtn = form.querySelector('button[type="submit"], button:not([type="button"])');
      if (saveBtn) saveBtn.scrollIntoView({ block: 'center', behavior: 'smooth' });
    });
  }
})();