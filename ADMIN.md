# Ol' Musky - Admin Guide

How to run the game server, and how to use the admin web page.

## Run the server

Requirements: [uv](https://docs.astral.sh/uv/) and Python 3.12.

```sh
uv sync            # one time, to install
uv run ol-musky    # start the server; Ctrl+C stops it
```

| Page | Address |
|---|---|
| Spectator page | <http://127.0.0.1:8000/> |
| Admin page | <http://127.0.0.1:8000/admin> |
| API reference | <http://127.0.0.1:8000/docs> |
| Bot API | `http://127.0.0.1:8000/mcp/...` (see `README.md`) |

The state of the games is in memory. When the server stops, all games end. The result of each game goes to a database (see "Results").

## Configuration

The server reads these files when it starts. Start it again after a change.

| File | Content |
|---|---|
| `config/mcp.yaml` | The scenario: length of a game, real time of one week, starting capital, mining rate, hub capacity, costs, the size of the belt, and the name of the belt file |
| `config/<belt>.csv` | The belt that `mcp.yaml` names: one line `ore,deposit` for each sector |
| `config/teams.yaml` | The teams: one line `token: name` for each team. Give each team its token. |

Environment variables (all optional):

| Variable | Default | Purpose |
|---|---|---|
| `OL_MUSKY_HOST` | `127.0.0.1` | Address of the server. Use `0.0.0.0` to let other computers connect. |
| `OL_MUSKY_PORT` | `8000` | Port of the server |
| `OL_MUSKY_SCENARIO` | `config/mcp.yaml` | Scenario file |
| `OL_MUSKY_TEAMS` | `config/teams.yaml` | Teams file |
| `OL_MUSKY_ADMIN_KEY` | (none) | Key for the admin page (see "Access") |
| `OL_MUSKY_RESULTS` | `results/ol-musky.sqlite3` | Results database. An empty value stops the export. |

## Run a game

1. Add the teams to `config/teams.yaml` and start the server.
2. Each team starts its own game with `/mcp/startup?token=<token>`. Its clock starts at that time. A team can start again as frequently as it wants.
3. Watch the games on the spectator page. A game ends after the number of weeks in the scenario (600 weeks of 200 ms is 2 minutes).

To try the server with the sample bot (it needs the `requests` library):

```sh
cd admin
uv run --with requests python naive.py dev    # "dev" is a token from config/teams.yaml
```

## Results

Nothing is recorded while a game runs. The server writes the final state of a game to the SQLite database `results/ol-musky.sqlite3`:

- when the game of a team ends (the first time that the spectator page or a request reads the team after its last week), and
- when the server stops, for the games that did not end.

| Table | Content |
|---|---|
| `mcp_result` | One row for each export: team, scenario, start time, week, balance, and `finished` (1 = the game ended). This is the history of all scores. |
| `mcp_team` | One row for each team: its last exported game |
| `mcp_ledger`, `mcp_hub`, `mcp_order`, `mcp_site` | The ledger, the hubs, the pending work orders, and the mined sectors of that game |
| `mcp_belt` | The belt of the scenario |

A new game of a team replaces its rows in all tables except `mcp_result`.

**Scoring.** For each judged run, the team calls `/mcp/startup` and the judges watch the spectator page. When the game ends, its score is in the database:

```sh
sqlite3 -header -column results/ol-musky.sqlite3 \
  "SELECT name, start_time, week, round(balance, 2) AS balance, finished FROM mcp_result ORDER BY id"
```

The SQL reports of `admin/` run on the database, for example `sqlite3 results/ol-musky.sqlite3 < admin/eff.sql`.

## The admin page

The admin page makes belts and selects the belt of the game.

**New belt.** Set the seed and the six settings: coverage (sparse to dense), total ore, number of clusters, cluster size, ore Y share, and roughness. The preview changes immediately. The same settings and seed always give the same belt; "New seed" gives a different belt with the same settings.

**Preview.** The ore of the belt (blue is ore X, red is ore Y; a larger deposit is larger and brighter), and its measurements: coverage, total ore, largest and typical deposit, the number of good hub sites, how many hub loads the best site and a typical site hold, the part of the ore in reach of hubs, and the largest empty area.

**Save.** Give the belt a name and click "Save". The belt goes to `config/<name>.csv`. The file has the seed and the settings in comment lines, so that the same belt can be made again. A file that exists is not replaced: use a new name.

**Saved belts.** A table of the belt files in `config/`, with their measurements.

- "View" shows a saved belt in the preview.
- "Load at start" selects the belt that the server loads when it starts. It changes only the belt file name in `config/mcp.yaml`.
- The mark "in use now" shows the belt of the server that runs. The mark "loads at start" shows the belt for the next start. Start the server again to use a new belt; games in progress keep their belt until then.
- A belt must have the size of the scenario. A file of a different size shows "wrong size" and cannot be selected.

### Access

- With no admin key, only the computer of the server can open the admin page.
- To use the admin page from a different computer, set a key before you start the server, and give the key in the address:

  ```sh
  OL_MUSKY_ADMIN_KEY=<key> OL_MUSKY_HOST=0.0.0.0 uv run ol-musky
  ```

  `http://<server address>:8000/admin?key=<key>`

The spectator page has no access control. It shows the ore of the belt, so do not give the players access to it during a competition.
