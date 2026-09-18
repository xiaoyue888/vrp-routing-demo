# Vehicle Routing Optimization Demo

This privacy-safe portfolio Demo plans last-mile delivery routes for a homogeneous
fleet operating from one depot. It solves a focused capacitated vehicle-routing
problem with customer time windows (CVRPTW) and compares two methods on identical
inputs:

- a transparent greedy feasible nearest-neighbour baseline;
- an OR-Tools routing model described as optimized, not provably optimal.

All included scenarios and examples are synthetic. The public interface uses
offline Euclidean distance at a configured average speed. The code does not store
uploads or contain client data. An opt-in road-network adapter remains available
for future local evaluation.

## Verified example

In the bundled 12-customer offline scenario, both methods serve all 12 orders.
The greedy baseline travels 74.5 km and the OR-Tools plan travels 64.4 km, a
13.5% reduction for that specific synthetic run. The interface recalculates these
figures for every scenario and keeps partial service or failure visible.

## Assumptions

- Every route starts and ends at one depot.
- The fleet is homogeneous.
- Each customer is visited at most once and has demand, service duration, and a
  service-start time window.
- Both algorithms and the independent validator share exactly one travel matrix.
- The public mode uses Euclidean kilometres and one fixed average speed.
- An optional local road mode can use fastest-route distance and duration from an
  OSRM-compatible service when it is explicitly enabled.
- Travel time is rounded up to whole minutes in the OR-Tools model.
- Orders that cannot be served may be dropped with a high penalty and are always
  reported explicitly.

## Local setup

From this directory:

```powershell
python -m pip install -e ".[dev]"
python -m vrp_demo --time-limit 2
pytest
```

Start the interactive local Demo:

```powershell
python -m vrp_demo.web
```

Then open `http://127.0.0.1:4190`. The local server holds no database and writes
no scenario or CSV content to disk.

The public interface does not call OSRM. To evaluate the retained road adapter
locally, explicitly enable it and set `VRP_OSRM_URL` to an OSRM-compatible base
URL:

```powershell
$env:VRP_OSRM_URL = "http://127.0.0.1:5000"
$env:VRP_ENABLE_ROAD_ROUTING = "true"
python -m vrp_demo.web
```

Generate a reproducible random scenario:

```powershell
python -m vrp_demo --random --seed 42 --customers 20 --time-limit 2
```

The CLI prints structured JSON from the same computational core used by the interface.

## CSV customer schema

The header must be exactly:

```csv
customer_id,x_km,y_km,demand,service_minutes,window_start,window_end
```

Fleet settings, depot coordinates, average speed, and random seed remain scenario
parameters rather than repeated CSV columns. Times are minutes from the start of
the planning horizon. CSV content is parsed in memory and is not persisted by the
core.

## Interface

The interactive implementation is `ui/app.html`; it renders a route map, KPI comparison, route
details, validation errors, and unserved-order explanations. It is a portfolio
Demo, not production dispatch software.

The interface prioritizes service coverage before total distance. When the two
methods serve different order counts, total-distance differences are explicitly
marked as not comparable and distance per served order is shown instead. It also
surfaces the independent feasibility check and treats the OR-Tools duration as a
search budget rather than a speed comparison.

Generated scenarios include three one-click presets and an exact capacity-based
fleet suggestion. The public route display and KPIs use the same offline
straight-line matrix. In Compare, the greedy route is a wide translucent warm
dashed line beneath a narrower blue optimized line, keeping both visible.

Uploaded CSV coordinates stay in offline mode and are not sent to a third-party
routing service. A road-network edition would require a self-hosted or contracted
routing provider before public deployment.

The HTTP adapter caps solver requests at 10 seconds, allows two concurrent solves,
applies a per-IP request limit, disables directory listing, returns safe input
messages, and sends baseline security headers. It is suitable for this low-traffic
portfolio staging service; a higher-traffic production use case would still need
infrastructure-level rate limiting and a more scalable serving layer.

## Publication boundary

The Python runtime remains separate from the static website. A public Render
staging service is available at `https://vrp-routing-demo.onrender.com/`, while
the GitHub repository remains private. The hosted service preserves offline
routing as its public mode. The code is licensed separately under the MIT License
below.

## Render staging configuration

`render.yaml` defines the proposed free staging Web Service. Render supplies its
port through `PORT`; the service reads that value and uses `VRP_HOST=0.0.0.0` in
the hosted environment while keeping `127.0.0.1:4190` as the local default.

The health-check endpoint is:

```text
/healthz
```

It returns only service status and the public routing mode. It does not run the
solver or expose scenario data.

The approved website return link is declared in `render.yaml`:

```text
VRP_CASE_STUDY_URL=https://xiaoyue-portfolio.pages.dev/vehicle-routing.html
```

If the value is missing or invalid, the Demo falls back to the local case-study URL.
Road routing remains disabled unless `VRP_ENABLE_ROAD_ROUTING=true` is explicitly set.

## License

This project is available under the [MIT License](LICENSE).
