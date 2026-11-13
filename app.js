const $ = (id) => document.getElementById(id),
  esc = (value) =>
    String(value).replace(
      /[&<>"']/g,
      (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c],
    );
let examples = null,
  lookupReport = null,
  planReport = null,
  lookupVersion = 0,
  planVersion = 0;
const format = (value) => BigInt(value).toLocaleString();
function notice(id, text, error = false) {
  $(id).textContent = text;
  $(id).className = error ? 'error' : '';
}
async function api(path, body) {
  const response = await fetch(path, {
    method: body === undefined ? 'GET' : 'POST',
    headers: body === undefined ? {} : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await response.json();
  if (!response.ok) throw Error(data.error ?? 'Analysis failed.');
  return data;
}
function clearLookup() {
  lookupVersion++;
  lookupReport = null;
  $('save-lookup').disabled = true;
  $('winner').textContent = 'Inputs changed.';
  $('winner-prefix').textContent = '';
  $('reason').textContent = 'Run a lookup to update the forwarding decision.';
  $('destination-label').textContent = $('destination').value;
  $('family').textContent = '—';
  for (const id of ['bits', 'matches', 'checkpoints']) $(id).replaceChildren();
  $('match-count').textContent = '—';
  notice('lookup-notice', 'Lookup results are pending.');
}
function clearPlan() {
  planVersion++;
  planReport = null;
  $('save-plan').disabled = true;
  $('plan').replaceChildren();
  $('subnets').replaceChildren();
  $('subnet-limit').textContent =
    'The preview shows at most 64 subnets, even for enormous IPv6 ranges.';
  notice('subnet-notice', 'Network changed. Divide it to update the plan.');
}
async function lookup() {
  clearLookup();
  const version = lookupVersion;
  notice('lookup-notice', 'Following the prefix trie…');
  const input = { routes: $('routes').value, destination: $('destination').value };
  try {
    const result = await api('/api/lookup', input);
    if (version !== lookupVersion) return;
    lookupReport = { format: 'prefix-atlas-lookup-v1', input, ...result };
    $('save-lookup').disabled = false;
    $('destination-label').textContent = result.destination;
    $('family').textContent = `IPv${result.version} / ${result.width} BITS`;
    $('winner').textContent = result.winner ? result.winner.hop : 'No route.';
    $('winner-prefix').textContent = result.winner
      ? `${result.winner.cidr} · metric ${result.winner.metric} · route #${result.winner.id}`
      : 'Destination is not covered by this table.';
    $('reason').textContent = result.reason;
    $('bits').innerHTML = Array.from(
      result.bits,
      (bit, i) =>
        `<span class="bit ${result.winner && i < result.winner.prefix ? 'network' : ''}" aria-label="Bit ${i + 1}: ${bit}">${bit}</span>`,
    ).join('');
    $('checkpoints').innerHTML =
      result.checkpoints
        .map(
          (point) =>
            `<span>/${point.depth}<br>route${point.routes.length === 1 ? '' : 's'} ${point.routes.map((id) => '#' + id).join(', ')}</span>`,
        )
        .join('') || '<p>No matching route was encountered.</p>';
    $('match-count').textContent =
      `${result.matches.length} MATCHES / ${result.routes.length} ROUTES`;
    $('matches').innerHTML =
      result.matches
        .map(
          (r, i) =>
            `<tr class="${i === 0 ? 'winner' : ''}"><td>${i + 1}</td><td>${esc(r.cidr)}</td><td>${esc(r.hop)}</td><td>${r.metric}</td><td>${i === 0 ? 'SELECTED' : r.prefix < result.winner.prefix ? 'Less specific' : r.metric > result.winner.metric ? 'Higher metric' : 'Later input order'}</td></tr>`,
        )
        .join('') || '<tr><td colspan="5">No matching route in this address family.</td></tr>';
    notice(
      'lookup-notice',
      `Analyzed ${result.routes.length} routes. Trie traversal followed ${result.traversed_bits} destination bits.`,
    );
  } catch (error) {
    if (version === lookupVersion) {
      $('winner').textContent = 'Check the inputs.';
      notice('lookup-notice', error.message, true);
    }
  }
}
async function plan() {
  clearPlan();
  const version = planVersion;
  notice('subnet-notice', 'Calculating exact boundaries…');
  try {
    const result = await api('/api/subnets', {
      cidr: $('parent').value,
      new_prefix: Number($('new-prefix').value),
    });
    if (version !== planVersion) return;
    planReport = { format: 'prefix-atlas-subnets-v1', ...result };
    $('save-plan').disabled = false;
    $('plan').innerHTML =
      `<article><span>SUBNETS</span><strong>${format(result.subnet_count)}</strong><span>at /${result.new_prefix}</span></article><article><span>ADDRESSES PER SUBNET</span><strong>${format(result.addresses_per_subnet)}</strong><span>Address count, not usable-host count</span></article><article><span>TOTAL ADDRESSES</span><strong>${format(result.address_count)}</strong><span>inside ${esc(result.cidr)}</span></article><p class="range">First address: ${esc(result.first_address)}<br>Last address: ${esc(result.last_address)}</p>`;
    $('subnets').innerHTML = result.subnets
      .map((cidr, i) => `<div class="subnet"><small>SUBNET ${i + 1}</small>${esc(cidr)}</div>`)
      .join('');
    $('subnet-limit').textContent = result.truncated
      ? `Showing the first 64 of ${format(result.subnet_count)} subnets. The export contains this same bounded preview.`
      : `Showing all ${result.subnet_count} subnets.`;
    notice('subnet-notice', 'Boundaries calculated without enumerating individual addresses.');
  } catch (error) {
    if (version === planVersion) notice('subnet-notice', error.message, true);
  }
}
function tab(name) {
  for (const id of ['lookup', 'subnet']) {
    const selected = id === name;
    $(id + '-tab').setAttribute('aria-selected', String(selected));
    $(id + '-tab').tabIndex = selected ? 0 : -1;
    $(id + '-panel').hidden = !selected;
  }
}
for (const name of ['lookup', 'subnet']) {
  $(name + '-tab').addEventListener('click', () => tab(name));
  $(name + '-tab').addEventListener('keydown', (event) => {
    if (['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) {
      event.preventDefault();
      const target =
        event.key === 'Home'
          ? 'lookup'
          : event.key === 'End'
            ? 'subnet'
            : name === 'lookup'
              ? 'subnet'
              : 'lookup';
      tab(target);
      $(target + '-tab').focus();
    }
  });
}
$('lookup-form').addEventListener('submit', (event) => {
  event.preventDefault();
  lookup();
});
$('subnet-form').addEventListener('submit', (event) => {
  event.preventDefault();
  plan();
});
for (const id of ['routes', 'destination']) $(id).addEventListener('input', clearLookup);
for (const id of ['parent', 'new-prefix']) $(id).addEventListener('input', clearPlan);
function loadExample() {
  const example = examples[$('example').value];
  $('routes').value = example.routes;
  $('destination').value = example.destination;
  lookup();
}
$('example').addEventListener('change', loadExample);
function download(name, value, type = 'application/json') {
  const text = typeof value === 'string' ? value : JSON.stringify(value, null, 2),
    url = URL.createObjectURL(new Blob([text], { type })),
    a = document.createElement('a');
  a.href = url;
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
$('save-routes').addEventListener('click', () =>
  download('forwarding-table.txt', $('routes').value, 'text/plain'),
);
$('save-lookup').addEventListener('click', () => {
  if (lookupReport) download('route-analysis.json', lookupReport);
});
$('save-plan').addEventListener('click', () => {
  if (planReport) download('subnet-plan.json', planReport);
});
$('import').addEventListener('change', async () => {
  const file = $('import').files[0];
  $('import').value = '';
  if (!file) return;
  const version = ++lookupVersion;
  try {
    if (file.size > 128000) throw Error('Route file exceeds 128 KB.');
    const text = new TextDecoder('utf-8', { fatal: true }).decode(await file.arrayBuffer());
    if (text.length > 32000) throw Error('Route text exceeds 32,000 characters.');
    if (version !== lookupVersion) return;
    $('routes').value = text;
    lookup();
  } catch (error) {
    if (version === lookupVersion) notice('lookup-notice', 'Import failed: ' + error.message, true);
  }
});
api('/api/examples')
  .then((data) => {
    examples = data;
    $('example').disabled = false;
    if (lookupVersion === 0) loadExample();
  })
  .catch((error) => notice('lookup-notice', error.message, true));
plan();
