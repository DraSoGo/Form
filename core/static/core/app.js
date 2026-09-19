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

  // Green-first scale (overrides the library's yellow→orange→red).
  // intensity 0 → muted gray; 1–2 → pale green; 3–5 → green; 6–7 → amber;
  // 8–10 → muted red.
  const SCALE = [
    '#c5cdbe', // 0  no data
    '#dbe9c8', // 1
    '#cfe1b6', // 2  low
    '#9bb377', // 3
    '#7e9a5d', // 4  moderate
    '#6d8d54', // 5
    '#c89a3a', // 6
    '#d49a3a', // 7  high
    '#b3504a', // 8
    '#b84b45', // 9
    '#a03b35', // 10 very high
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
  function setSummary(name, group) {
    if (!summary) return;
    if (!group) {
      summary.textContent = `${name}: no data in the last 7 days.`;
      return;
    }
    const direct   = Number(group.direct   || 0);
    const indirect = Number(group.indirect || 0);
    summary.innerHTML = '';
    const strong = document.createElement('strong');
    strong.textContent = name;
    summary.append(strong, `: ${direct} direct sets, ${indirect} indirect sets in the last 7 days.`);
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
        setSummary(label, group);
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