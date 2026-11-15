# Redevelopment (2026)

This document has the technical description of the game server. `README.md` has the overview of the competition, its rules, and the instructions for the players, which include the API specification.

The game server is being built again from an empty start, one layer at a time. Each layer has its own tests and depends only on the layers before it. The competition text and the API specification in `README.md` describe the game as this server supplies it.

**Design**

The engine follows the dataflow idea of the Lucid language: a value is a stream, and an operation applies to streams point by point.

- The belt is a stream of asteroids; the index is the sector ID.
- `miners` is a sparse stream in parallel with the belt: at each sector, the hub of each bot that is there.
- A world is the state of one player in one week. Each player has their own world.
- `sweep(world)` gives the world of the next week. It goes along the asteroid stream and mines with each bot that it finds. `weeks(world)` is the stream of worlds.
- State is where things are. A hub mines because its bots are in `miners`; there are no status flags, and the sweep has no conditional statements. The limits are arithmetic: a bot takes the minimum of its rate, the deposit, and the free space of its hub.
- All values are immutable. A command or a sweep returns a new world.

**Status**

|Layer|Module|Scope|State|
|:---:|---|---|:---:|
|1|`sweep.py`|Mining: the weekly sweep along the asteroid stream|done|
|2|`placement.py`|Belt geometry; `claim`, `land`, `lift`; placement rules|done|
|3|`timeline.py`|Events by week; `advance` = sweep, then the events of the new week|done|
|4|`ledger.py`, `market.py`, `game.py`|Money, ore prices, and the player commands `build`, `deploy`, `move`, `ship`|done|
|5|`reports.py`, `clock.py`|Status, ledger, market, parameters and prospecting views; the clock of a team|done|
|6|`scenario.py`, `league.py`, `server.py`|Scenario and team files; teams and their clocks; the HTTP API|done|
|7|`spectator.py`, `pages/spectator.html`|Spectator page: the ore of the belt, the hubs that mine, and a bar chart of the balances, live|done|
|8|-|Admin functions, guide page, export of results|next|

`world.py` holds the immutable values (`World`, `Asteroid`, `Hub`, `Terms`), and `rejection.py` holds the error for a command that breaks a rule. All modules are in `src/ol_musky/`. Piracy and insurance are not in the game at this time.

**Time.** There is no universal clock and no timer. Each team has its own clock, which starts when the team calls `/mcp/startup`; a team can start again as frequently as it wants. The server calculates the world of the team's current week when a request asks for it.

**Run the server** (requires [uv](https://docs.astral.sh/uv/) and Python 3.12)

```sh
uv sync
uv run ol-musky                 # spectator page at http://127.0.0.1:8000, API docs at /docs
curl 'http://127.0.0.1:8000/mcp/startup?token=dev'
curl 'http://127.0.0.1:8000/mcp/build_hubs?token=dev&hubs=A'
curl 'http://127.0.0.1:8000/mcp/status_report?token=dev'
```

The server reads `config/mcp.yaml` (the scenario and its belt file) and `config/teams.yaml` (API token and name of each team) at start. The environment variables `OL_MUSKY_SCENARIO`, `OL_MUSKY_TEAMS`, `OL_MUSKY_HOST` and `OL_MUSKY_PORT` change the files and the address. The state is in memory only.

**Spectator page.** `http://127.0.0.1:8000/` shows the belt and a bar chart. The belt has a haze of the ore at the start of a game (one colour for each ore type; a larger deposit is larger and brighter), and a dot for each hub that mines, in the colour of its team. Hubs that are idle or in transit are not in the graphic. The bar chart has one bar for each team, for its balance, with the week of the team below its name; a dashed line shows the starting capital. The teams are in the sequence of their names, so that a bar and its colour stay in the same position. After eight teams the colours start again with outlined bars and ring dots, and then with striped bars and rings that have a centre point. Point at a team, or click it, to show only that team in the belt and to see its details. The page reads `/spectator/state` one time each second and `/spectator/belt` one time. The data has no API tokens. The players do not have access to this page during a competition; the server does not restrict access to it.

The tools in `admin/` and the guide page in `templates/` are from the 2018 server. They stay unchanged until the application is complete.

**Development**

```sh
uv run pytest
uv run ruff check . && uv run ruff format --check src tests
```

**Other documents**

|File|Content|
|---|---|
|`doc/mining-bot.puml`|PlantUML activity diagram of a mining bot with three parallel loops: prospecting, building and deploying, and shipping|
|`doc/mining_process.puml`|PlantUML activity diagram of the basic loop of a mining bot|
