const state = { source: "built_in", result: null, mapView: "optimized", csvText: null, adviceTimer: null, leafletMap: null };

const $ = (id) => document.getElementById(id);
const sourceButtons = [...document.querySelectorAll("[data-source]")];
const mapButtons = [...document.querySelectorAll("[data-view]")];

sourceButtons.forEach((button) => button.addEventListener("click", () => setSource(button.dataset.source)));
mapButtons.forEach((button) => button.addEventListener("click", () => {
  state.mapView = button.dataset.view;
  mapButtons.forEach((item) => item.classList.toggle("active", item === button));
  mapButtons.forEach((item) => item.setAttribute("aria-pressed", String(item === button)));
  if (state.result) renderMap();
}));

document.querySelectorAll("[data-preset]").forEach((button) => button.addEventListener("click", () => runPreset(button.dataset.preset)));
["customer-count", "vehicle-capacity", "seed"].forEach((id) => $(id).addEventListener("change", () => scheduleFleetAdvice(true)));
$("vehicle-count").addEventListener("change", () => scheduleFleetAdvice(false));
$("route-method").addEventListener("change", renderRouteDetails);
$("csv-file").addEventListener("change", async (event) => {
  const file = event.target.files[0];
  state.csvText = file ? await file.text() : null;
  $("source-summary").innerHTML = file
    ? `<strong>${escapeHtml(file.name)}</strong><span>Read locally · ${(file.size / 1024).toFixed(1)} KB</span>`
    : "<strong>No CSV selected</strong><span>Use the seven-column coordinate schema</span>";
});

$("scenario-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const runButton = $("run-button");
  runButton.disabled = true;
  runButton.textContent = "Running both methods…";
  setMessage("neutral", "Building one shared scenario and running both methods…");
  try {
    const response = await fetch("/api/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(requestPayload()),
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || "The comparison could not be completed.");
    state.result = payload;
    renderResults();
    if (window.matchMedia("(max-width: 900px)").matches) {
      $("results").scrollIntoView({ behavior: "smooth", block: "start" });
    }
  } catch (error) {
    state.result = null;
    $("result-heading").textContent = "Input needs attention";
    setMessage("error", error.message);
    clearResults();
  } finally {
    runButton.disabled = false;
    runButton.textContent = "Run both methods →";
  }
});

function setSource(source) {
  state.source = source;
  sourceButtons.forEach((button) => button.classList.toggle("active", button.dataset.source === source));
  sourceButtons.forEach((button) => button.setAttribute("aria-pressed", String(button.dataset.source === source)));
  $("upload-panel").classList.toggle("hidden", source !== "csv");
  $("customer-count").disabled = source !== "generate";
  $("seed").disabled = source === "built_in";
  if (source === "built_in") {
    $("customer-count").value = 12;
    $("source-summary").innerHTML = "<strong>Built-in synthetic city</strong><span>12 customers · deterministic example</span>";
  } else if (source === "generate") {
    if ($("customer-count").value === "12") $("customer-count").value = 20;
    $("source-summary").innerHTML = "<strong>Generated coordinate scenario</strong><span>Reproducible with the same random seed</span>";
    scheduleFleetAdvice(true);
  } else {
    $("source-summary").innerHTML = state.csvText
      ? "<strong>CSV ready</strong><span>Coordinate rows will be validated before solving</span>"
      : "<strong>No CSV selected</strong><span>Use the seven-column coordinate schema</span>";
  }
  if (source !== "generate") $("fleet-advice").classList.add("hidden");
}

function runPreset(preset) {
  const presets = {
    capacity: { customers: 40, vehicles: 4, capacity: 12, shift: 360, seed: 101, label: "Capacity-constrained scenario" },
    windows: { customers: 30, vehicles: 7, capacity: 18, shift: 180, seed: 202, label: "Tight time-window scenario" },
    fleet: { customers: 24, vehicles: 8, capacity: 18, shift: 360, seed: 303, label: "Fleet-sufficient scenario" },
  };
  const selected = presets[preset];
  setSource("generate");
  clearTimeout(state.adviceTimer);
  $("customer-count").value = selected.customers;
  $("vehicle-count").value = selected.vehicles;
  $("vehicle-capacity").value = selected.capacity;
  $("shift-minutes").value = selected.shift;
  $("seed").value = selected.seed;
  $("source-summary").innerHTML = `<strong>${selected.label}</strong><span>One-click reproducible preset</span>`;
  $("scenario-form").requestSubmit();
}

function scheduleFleetAdvice(autoApply) {
  if (state.source !== "generate") return;
  clearTimeout(state.adviceTimer);
  state.adviceTimer = setTimeout(() => refreshFleetAdvice(autoApply), 250);
}

async function refreshFleetAdvice(autoApply) {
  try {
    const payload = requestPayload();
    const requestSignature = fleetAdviceSignature(payload);
    const response = await fetch("/api/suggest", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!response.ok) return;
    const summary = await response.json();
    if (requestSignature !== fleetAdviceSignature(requestPayload())) {
      scheduleFleetAdvice(autoApply);
      return;
    }
    if (autoApply) $("vehicle-count").value = summary.minimum_vehicles_by_capacity;
    const vehicles = Number($("vehicle-count").value);
    const totalCapacity = vehicles * Number($("vehicle-capacity").value);
    const advice = $("fleet-advice");
    advice.classList.remove("hidden");
    advice.textContent = vehicles < summary.minimum_vehicles_by_capacity
      ? `Capacity warning: ${summary.total_demand} demand units require at least ${summary.minimum_vehicles_by_capacity} vehicles. The current fleet can theoretically cover at most ${summary.max_orders_by_capacity} of ${summary.customer_count} orders before time windows are considered.`
      : `Capacity check: ${summary.total_demand} demand units / ${totalCapacity} fleet capacity. Suggested minimum: ${summary.minimum_vehicles_by_capacity} vehicles; time windows may require more.`;
  } catch (_) {
    $("fleet-advice").classList.add("hidden");
  }
}

function fleetAdviceSignature(payload) {
  return [payload.customer_count, payload.vehicle_count, payload.vehicle_capacity, payload.seed].join(":");
}

function requestPayload() {
  return {
    source: state.source,
    customer_count: Number($("customer-count").value),
    vehicle_count: Number($("vehicle-count").value),
    vehicle_capacity: Number($("vehicle-capacity").value),
    average_speed_kmph: Number($("average-speed").value),
    shift_minutes: Number($("shift-minutes").value),
    seed: Number($("seed").value),
    solver_time_limit_seconds: Number($("time-limit").value),
    csv_text: state.source === "csv" ? state.csvText : null,
    routing_mode: "euclidean",
  };
}

function renderResults() {
  const { baseline, optimized, scenario } = state.result;
  $("result-heading").textContent = scenario.name;
  const total = scenario.customers.length;
  if (optimized.unserved_orders === 0) {
    setMessage("success", `Optimized plan serves all ${total} orders. Both methods used identical inputs and constraints.`);
  } else {
    setMessage("warning", `Optimized plan serves ${optimized.served_orders} of ${total} orders. Unserved orders remain visible below.`);
  }
  renderValidationCheck();
  renderRunMetadata();
  renderMap();
  renderComparison();
  renderRouteDetails();
  renderUnserved();
}

function setMessage(kind, text) {
  const message = $("message");
  message.className = `message ${kind}`;
  message.textContent = text;
}

function clearResults() {
  if (state.leafletMap) {
    state.leafletMap.remove();
    state.leafletMap = null;
  }
  $("route-map").innerHTML = '<p class="empty-copy">Routes will appear here.</p>';
  $("route-legend").innerHTML = "";
  $("comparison-table").innerHTML = "";
  $("route-details").innerHTML = '<p class="empty-copy">No route details yet.</p>';
  $("unserved-section").classList.add("hidden");
  $("validation-check").classList.add("hidden");
  $("map-inspector").classList.add("hidden");
  $("run-metadata").textContent = "";
}

function renderComparison() {
  const { baseline, optimized } = state.result;
  const sameCoverage = baseline.served_orders === optimized.served_orders;
  const totalOrders = baseline.served_orders + baseline.unserved_orders;
  const distancePerBaselineOrder = baseline.served_orders ? baseline.total_distance_km / baseline.served_orders : null;
  const distancePerOptimizedOrder = optimized.served_orders ? optimized.total_distance_km / optimized.served_orders : null;
  const incomparable = '<span class="not-comparable">Not comparable — different coverage</span>';
  const rows = [
    ["Orders served", `${baseline.served_orders} / ${totalOrders}`, `${optimized.served_orders} / ${totalOrders}`, signed(optimized.served_orders - baseline.served_orders), optimized.served_orders > baseline.served_orders],
    ["Coverage rate", `${fmt(baseline.served_orders / totalOrders * 100, 0)}%`, `${fmt(optimized.served_orders / totalOrders * 100, 0)}%`, `${signed((optimized.served_orders - baseline.served_orders) / totalOrders * 100)} pp`, optimized.served_orders > baseline.served_orders],
    ["Distance / served order", distancePerBaselineOrder === null ? "—" : `${fmt(distancePerBaselineOrder, 1)} km`, distancePerOptimizedOrder === null ? "—" : `${fmt(distancePerOptimizedOrder, 1)} km`, distancePerBaselineOrder && distancePerOptimizedOrder ? `${signed((distancePerOptimizedOrder - distancePerBaselineOrder) / distancePerBaselineOrder * 100, 1)}%` : "—", distancePerOptimizedOrder < distancePerBaselineOrder],
    ["Total distance", `${fmt(baseline.total_distance_km, 1)} km`, `${fmt(optimized.total_distance_km, 1)} km`, sameCoverage ? distanceDelta(baseline, optimized) : incomparable, sameCoverage && optimized.total_distance_km < baseline.total_distance_km],
    ["Estimated travel", `${fmt(baseline.total_travel_minutes, 0)} min`, `${fmt(optimized.total_travel_minutes, 0)} min`, sameCoverage ? numericDelta(baseline.total_travel_minutes, optimized.total_travel_minutes, "min") : incomparable, sameCoverage && optimized.total_travel_minutes < baseline.total_travel_minutes],
    ["Vehicles used", baseline.vehicles_used, optimized.vehicles_used, numericDelta(baseline.vehicles_used, optimized.vehicles_used, ""), false],
    ["Capacity utilization", `${fmt(baseline.average_capacity_utilization * 100, 0)}%`, `${fmt(optimized.average_capacity_utilization * 100, 0)}%`, `${signed((optimized.average_capacity_utilization - baseline.average_capacity_utilization) * 100)} pp`, false],
  ];
  $("comparison-table").outerHTML = `<table class="comparison" id="comparison-table">
    <thead><tr><th scope="col">Metric</th><th scope="col">Greedy</th><th scope="col">Optimized</th><th scope="col">Difference</th></tr></thead>
    <tbody>${rows.map((row) => `<tr><th scope="row">${row[0]}</th><td>${row[1]}</td><td>${row[2]}</td><td class="${row[4] ? "delta-good" : ""}">${row[3]}</td></tr>`).join("")}</tbody>
  </table>`;
}

function renderValidationCheck() {
  const { baseline, optimized } = state.result;
  const errors = [...baseline.validation_messages, ...optimized.validation_messages];
  const check = $("validation-check");
  check.classList.remove("hidden");
  check.textContent = errors.length === 0
    ? "Independent feasibility check: passed · capacity · time windows · shift · unique service"
    : `Independent feasibility check needs attention: ${errors.join(" · ")}`;
}

function renderRunMetadata() {
  const { baseline, optimized } = state.result;
  const budget = optimized.solver_metadata.search_budget_seconds;
  const reached = optimized.solver_metadata.search_limit_reached;
  const basis = state.result.map_data?.distance_basis || "Straight-line distance";
  $("run-metadata").textContent = `Travel model: ${basis}. Run details: greedy construction ${fmt(baseline.runtime_ms, 1)} ms. OR-Tools search budget ${fmt(budget, 1)} s${reached ? " (limit reached)" : ""}. Runtime is not treated as a solution-quality metric.`;
}

function distanceDelta(baseline, optimized) {
  if (!baseline.total_distance_km) return "—";
  const percent = (optimized.total_distance_km - baseline.total_distance_km) / baseline.total_distance_km * 100;
  return `${percent > 0 ? "+" : ""}${fmt(percent, 1)}%`;
}

function numericDelta(baseline, optimized, unit) {
  const value = optimized - baseline;
  return `${value > 0 ? "+" : ""}${fmt(value, 0)}${unit ? ` ${unit}` : ""}`;
}

function signed(value, digits = 0) {
  return `${value > 0 ? "+" : ""}${fmt(value, digits)}`;
}

function renderMap() {
  if (state.result.map_data?.mode === "road" && window.L) {
    renderRoadMap();
    return;
  }
  renderSyntheticMap();
}

function renderRoadMap() {
  if (state.leafletMap) state.leafletMap.remove();
  const container = $("route-map");
  container.innerHTML = "";
  const mapData = state.result.map_data;
  const scenario = state.result.scenario;
  const activeSolution = state.mapView === "baseline" ? state.result.baseline : state.result.optimized;
  const unserved = new Set(Object.keys(activeSolution.unserved_customers));
  const map = L.map(container, { zoomControl: true, preferCanvas: true });
  state.leafletMap = map;
  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
  }).addTo(map);

  const bounds = [];
  const depot = [mapData.depot.lat, mapData.depot.lon];
  bounds.push(depot);
  L.circleMarker(depot, { radius: 9, color: "#fff", weight: 3, fillColor: "#1a1a1a", fillOpacity: 1 })
    .bindTooltip("Depot", { direction: "top" }).addTo(map);
  scenario.customers.forEach((customer) => {
    const coordinate = mapData.customers[customer.customer_id];
    const point = [coordinate.lat, coordinate.lon];
    bounds.push(point);
    const marker = L.circleMarker(point, {
      radius: 5,
      color: unserved.has(customer.customer_id) ? "#9a3b2e" : "#1a1a1a",
      weight: 1.5,
      fillColor: unserved.has(customer.customer_id) ? "#f0c7bf" : "#ffffff",
      fillOpacity: 1,
    }).addTo(map);
    marker.bindTooltip(`${escapeHtml(customer.customer_id)} · demand ${customer.demand} · ${clock(customer.window_start)}–${clock(customer.window_end)}`);
    marker.on("click", () => showCustomerDetails(customer.customer_id));
  });

  const routeSets = state.mapView === "compare"
    ? [["baseline", mapData.routes.baseline], ["optimized", mapData.routes.optimized]]
    : [[state.mapView, mapData.routes[state.mapView]]];
  routeSets.forEach(([kind, routes]) => routes.forEach((route) => {
    const compare = state.mapView === "compare";
    const style = kind === "baseline"
      ? { color: "#d45f45", weight: compare ? 9 : 6, opacity: compare ? 0.48 : 0.82, dashArray: "13 11", lineCap: "round" }
      : { color: "#4b9ee8", weight: compare ? 4.5 : 6, opacity: compare ? 0.96 : 0.9, lineCap: "round" };
    L.polyline(route.geometry, style).bindTooltip(`${kind === "baseline" ? "Greedy" : "Optimized"} · ${route.vehicle_id}`).addTo(map);
  }));
  map.fitBounds(bounds, { padding: [28, 28], maxZoom: 14 });
  setTimeout(() => map.invalidateSize(), 0);

  const legend = state.mapView === "compare"
    ? '<span><i class="baseline-key"></i>Greedy · wide translucent dashed</span><span><i class="optimized-key"></i>Optimized · solid blue</span>'
    : state.mapView === "baseline"
      ? '<span><i class="baseline-key"></i>Greedy routes</span>'
      : '<span><i class="optimized-key"></i>Optimized routes</span>';
  $("route-legend").innerHTML = `${legend}<span class="map-disclaimer">Real OpenStreetMap streets · routes follow OSRM road geometry · KPIs use the same fastest-route road matrix shown here.</span>`;
}

function renderSyntheticMap() {
  if (state.leafletMap) {
    state.leafletMap.remove();
    state.leafletMap = null;
  }
  const scenario = state.result.scenario;
  const mobile = window.matchMedia("(max-width: 560px)").matches;
  const mapWidth = mobile ? 420 : 760;
  const mapHeight = mobile ? 460 : 390;
  const solutions = state.mapView === "compare"
    ? [[state.result.baseline, "baseline"], [state.result.optimized, "optimized"]]
    : [[state.result[state.mapView], state.mapView]];
  const points = [scenario.depot, ...scenario.customers];
  const xValues = points.map((point) => point.x_km);
  const yValues = points.map((point) => point.y_km);
  const minX = Math.min(...xValues), maxX = Math.max(...xValues);
  const minY = Math.min(...yValues), maxY = Math.max(...yValues);
  const scaleX = (x) => 42 + (x - minX) / Math.max(1, maxX - minX) * (mapWidth - 84);
  const scaleY = (y) => mapHeight - 48 - (y - minY) / Math.max(1, maxY - minY) * (mapHeight - 96);
  const customerById = Object.fromEntries(scenario.customers.map((customer) => [customer.customer_id, customer]));
  const paths = [];
  solutions.forEach(([solution, kind]) => solution.routes.forEach((route) => {
    const routePoints = [scenario.depot, ...route.stops.map((stop) => customerById[stop.customer_id]), scenario.depot];
    const routePath = streetRoutePath(routePoints, scaleX, scaleY, mapWidth, mapHeight);
    paths.push(`<path class="route-casing ${kind}" d="${routePath}" />`);
    paths.push(`<path class="route-line ${kind}" d="${routePath}" />`);
  }));
  const activeSolution = state.mapView === "baseline" ? state.result.baseline : state.result.optimized;
  const unserved = new Set(Object.keys(activeSolution.unserved_customers));
  const nodes = scenario.customers.map((customer) => `
    <g class="customer-marker" tabindex="0" role="button" aria-label="${escapeHtml(customer.customer_id)}, demand ${customer.demand}, time window ${clock(customer.window_start)} to ${clock(customer.window_end)}" data-customer-id="${escapeHtml(customer.customer_id)}"><title>${escapeHtml(customer.customer_id)} · demand ${customer.demand} · window ${clock(customer.window_start)}–${clock(customer.window_end)}</title>
    <circle class="node ${unserved.has(customer.customer_id) ? "unserved" : ""}" cx="${scaleX(customer.x_km)}" cy="${scaleY(customer.y_km)}" r="8" />
    <circle class="node-core" cx="${scaleX(customer.x_km)}" cy="${scaleY(customer.y_km)}" r="2.4" />
    <text class="map-label customer-label" x="${scaleX(customer.x_km) + 10}" y="${scaleY(customer.y_km) - 9}">${escapeHtml(customer.customer_id)}</text></g>`).join("");
  const depotX = scaleX(scenario.depot.x_km), depotY = scaleY(scenario.depot.y_km);
  $("route-map").innerHTML = `<svg class="synthetic-map ${scenario.customers.length > 20 ? "dense" : ""}" viewBox="0 0 ${mapWidth} ${mapHeight}" role="group" aria-label="Fictional city map with synthetic delivery routes">
    <defs><filter id="marker-shadow" x="-50%" y="-50%" width="200%" height="200%"><feDropShadow dx="0" dy="1" stdDeviation="1.2" flood-opacity=".28" /></filter></defs>
    ${fictionalBasemap(mapWidth, mapHeight)}
    ${paths.join("")}${nodes}
    <g transform="translate(${depotX},${depotY})"><title>Synthetic depot</title><path class="depot-pin" d="M0,-14 C8,-14 13,-9 13,-2 C13,7 0,18 0,18 C0,18 -13,7 -13,-2 C-13,-9 -8,-14 0,-14 Z"/><circle class="depot-core" cx="0" cy="-2" r="4" /></g>
    <text class="map-label" x="${depotX + 15}" y="${depotY + 16}">DEPOT</text>
    <g transform="translate(28,${mapHeight - 28})"><path d="M0 0 H72" stroke="#5f655f" stroke-width="2"/><path d="M0 -4 V4 M72 -4 V4" stroke="#5f655f"/><text class="map-scale" x="0" y="14">SYNTHETIC NETWORK</text></g>
  </svg>`;
  const legend = state.mapView === "compare"
    ? '<span><i class="baseline-key"></i>Greedy routes</span><span><i style="border-color:#4b9ee8"></i>Optimized routes</span>'
    : state.mapView === "baseline"
      ? '<span><i class="baseline-key"></i>Greedy routes</span>'
      : '<span><i style="border-color:#4b9ee8"></i>Optimized routes</span>';
  $("route-legend").innerHTML = `${legend}<span class="map-disclaimer">Offline fallback · schematic street display · KPIs use the shared straight-line distance matrix.</span>`;
  document.querySelectorAll(".customer-marker").forEach((marker) => {
    const show = () => showCustomerDetails(marker.dataset.customerId);
    marker.addEventListener("click", show);
    marker.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") { event.preventDefault(); show(); }
    });
  });
}

function streetRoutePath(points, scaleX, scaleY, mapWidth, mapHeight) {
  const gridX = [0.1, 0.27, 0.48, 0.67, 0.84].map((ratio) => mapWidth * ratio);
  const gridY = [0.14, 0.30, 0.52, 0.70, 0.86].map((ratio) => mapHeight * ratio);
  const nearest = (value, candidates) => candidates.reduce((best, candidate) => Math.abs(candidate - value) < Math.abs(best - value) ? candidate : best);
  const projected = points.map((point) => ({ x: scaleX(point.x_km), y: scaleY(point.y_km) }));
  let path = `M ${projected[0].x} ${projected[0].y}`;
  for (let index = 1; index < projected.length; index += 1) {
    const from = projected[index - 1], to = projected[index];
    const fromGrid = { x: nearest(from.x, gridX), y: nearest(from.y, gridY) };
    const toGrid = { x: nearest(to.x, gridX), y: nearest(to.y, gridY) };
    path += ` L ${fromGrid.x} ${fromGrid.y} L ${toGrid.x} ${fromGrid.y} L ${toGrid.x} ${toGrid.y} L ${to.x} ${to.y}`;
  }
  return path;
}

function showCustomerDetails(customerId) {
  const scenario = state.result.scenario;
  const customer = scenario.customers.find((item) => item.customer_id === customerId);
  const solution = state.mapView === "baseline" ? state.result.baseline : state.result.optimized;
  const reason = solution.unserved_customers[customerId];
  const inspector = $("map-inspector");
  inspector.classList.remove("hidden");
  inspector.innerHTML = `<strong>${escapeHtml(customer.customer_id)}</strong><span>Demand ${customer.demand}</span><span>Window ${clock(customer.window_start)}–${clock(customer.window_end)}</span><span>${reason ? escapeHtml(reason) : "Served in selected plan"}</span>`;
}

function fictionalBasemap(mapWidth, mapHeight) {
  const scaleWidth = mapWidth / 760;
  const scaleHeight = mapHeight / 390;
  return `<g transform="scale(${scaleWidth} ${scaleHeight})">
    <rect class="map-land" width="760" height="390" />
    <path class="map-water" d="M646,-10 C625,52 674,91 646,146 C618,201 675,249 649,306 C636,337 650,372 676,400 H780 V-10 Z" />
    <path class="map-shore" d="M646,-10 C625,52 674,91 646,146 C618,201 675,249 649,306 C636,337 650,372 676,400" />
    <path class="map-park" d="M64 48 L178 34 L201 92 L171 142 L72 126 Z" />
    <path class="map-park" d="M482 242 L579 227 L617 275 L593 336 L501 329 L464 287 Z" />
    <g>
      <rect class="map-block" x="224" y="35" width="86" height="45" rx="3"/><rect class="map-block" x="333" y="31" width="91" height="51" rx="3"/><rect class="map-block" x="449" y="42" width="94" height="39" rx="3"/>
      <rect class="map-block" x="57" y="172" width="77" height="42" rx="3"/><rect class="map-block" x="158" y="166" width="94" height="50" rx="3"/><rect class="map-block" x="278" y="158" width="84" height="54" rx="3"/><rect class="map-block" x="393" y="164" width="82" height="44" rx="3"/><rect class="map-block" x="503" y="153" width="91" height="55" rx="3"/>
      <rect class="map-block" x="72" y="261" width="96" height="54" rx="3"/><rect class="map-block" x="202" y="263" width="75" height="48" rx="3"/><rect class="map-block" x="313" y="255" width="102" height="61" rx="3"/>
    </g>
    <g>
      <path class="road-casing road primary-casing" d="M-20 224 C125 198 243 218 382 201 C500 187 584 155 680 143"/><path class="road primary" d="M-20 224 C125 198 243 218 382 201 C500 187 584 155 680 143"/><path class="road-marking" d="M-20 224 C125 198 243 218 382 201 C500 187 584 155 680 143"/>
      <path class="road-casing road primary-casing" d="M359 -20 C347 86 378 157 368 235 C360 297 335 344 322 410"/><path class="road primary" d="M359 -20 C347 86 378 157 368 235 C360 297 335 344 322 410"/><path class="road-marking" d="M359 -20 C347 86 378 157 368 235 C360 297 335 344 322 410"/>
      <path class="road-casing road primary-casing" d="M-20 337 C128 325 247 348 370 334 C488 321 565 337 674 357"/><path class="road primary" d="M-20 337 C128 325 247 348 370 334 C488 321 565 337 674 357"/>
    </g>
    <g>
      ${[76, 205, 365, 509, 638].map((x) => `<path class="road-casing road tertiary-casing" d="M${x} 0 V390"/><path class="road tertiary" d="M${x} 0 V390"/>`).join("")}
      ${[55, 117, 203, 273, 335].map((y) => `<path class="road-casing road tertiary-casing" d="M0 ${y} H760"/><path class="road tertiary" d="M0 ${y} H760"/>`).join("")}
      <path class="road-casing road secondary-casing" d="M33 105 H626"/><path class="road secondary" d="M33 105 H626"/>
      <path class="road-casing road secondary-casing" d="M40 271 C168 238 287 239 425 246 C511 251 578 232 641 205"/><path class="road secondary" d="M40 271 C168 238 287 239 425 246 C511 251 578 232 641 205"/>
      <path class="road-casing road secondary-casing" d="M199 18 C213 100 207 177 224 240 C235 284 224 337 217 381"/><path class="road secondary" d="M199 18 C213 100 207 177 224 240 C235 284 224 337 217 381"/>
      <path class="road-casing road secondary-casing" d="M489 18 C471 93 489 157 486 223 C481 301 451 343 447 390"/><path class="road secondary" d="M489 18 C471 93 489 157 486 223 C481 301 451 343 447 390"/>
      <path class="road-casing road secondary-casing" d="M91 13 L607 382"/><path class="road secondary" d="M91 13 L607 382"/>
      <path class="road-casing road secondary-casing" d="M568 4 L39 375"/><path class="road secondary" d="M568 4 L39 375"/>
    </g>
    <text class="district-label" x="82" y="83">NORTH GREEN</text><text class="district-label" x="514" y="294">RIVERSIDE PARK</text><text class="district-label" x="255" y="184">CENTRAL DISTRICT</text>
    <text class="street-label" x="426" y="188" transform="rotate(-8 426 188)">Foundry Avenue</text><text class="street-label" x="371" y="67" transform="rotate(82 371 67)">Market Road</text><text class="street-label" x="89" y="321">South Connector</text>
  </g>`;
}

function renderRouteDetails() {
  if (!state.result) return;
  const solution = state.result[$("route-method").value];
  if (!solution.routes.length) {
    $("route-details").innerHTML = '<p class="empty-copy">No routes were produced.</p>';
    return;
  }
  $("route-details").innerHTML = solution.routes.map((route, index) => `
    <details ${index === 0 ? "open" : ""}>
      <summary><strong>${escapeHtml(route.vehicle_id)}</strong><span class="route-summary">${route.stops.length} stops · ${fmt(route.distance_km, 1)} km · ${fmt(route.capacity_utilization * 100, 0)}% capacity</span></summary>
      <div class="stops">
        <div class="stop"><strong>Depot</strong><span>depart 00:00</span></div>
        ${route.stops.map((stop) => `<div class="stop"><strong>${escapeHtml(stop.customer_id)}</strong><span>arrive ${clock(stop.arrival_minute)}</span><span>service ${clock(stop.service_start_minute)}</span><span>load ${stop.load_after}</span></div>`).join("")}
        <div class="stop"><strong>Depot</strong><span>route ${fmt(route.duration_minutes, 0)} min</span></div>
      </div>
    </details>`).join("");
}

function renderUnserved() {
  const solution = state.result.optimized;
  const entries = Object.entries(solution.unserved_customers);
  $("unserved-section").classList.toggle("hidden", entries.length === 0);
  $("unserved-list").innerHTML = entries.map(([id, reason]) => `<div class="unserved-item"><strong>${escapeHtml(id)}</strong><span>${escapeHtml(reason)}</span></div>`).join("");
}

function fmt(value, digits) { return Number(value).toFixed(digits); }
function clock(minutes) {
  const rounded = Math.round(minutes);
  return `${String(Math.floor(rounded / 60)).padStart(2, "0")}:${String(rounded % 60).padStart(2, "0")}`;
}
function escapeHtml(value) {
  return String(value).replace(/[&<>'"]/g, (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" })[character]);
}
