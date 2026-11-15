import asyncio

from fastapi.testclient import TestClient

from ol_musky.app import create_app
from ol_musky.db.engine import make_engine, make_session_factory
from ol_musky.db.scenario_repo import save_scenario


def _store(settings, scenario):
    async def run():
        engine = make_engine(settings)
        async with make_session_factory(engine)() as session:
            await save_scenario(session, scenario)
        await engine.dispose()

    asyncio.run(run())


def test_parameters(settings, scenario):
    _store(settings, scenario)
    with TestClient(create_app(settings)) as client:
        response = client.get("/mcp/parameters", params={"token": "abc123"})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == 0
    assert body["description"] == ""
    assert body["parameters"] == scenario.parameters_dict()
    assert body["parameters"]["rows"] == 40
    assert "starting_capital" not in body["parameters"]


def test_parameters_without_scenario(settings):
    with TestClient(create_app(settings)) as client:
        body = client.get("/mcp/parameters", params={"token": "abc123"}).json()
    assert body["status"] == 2200
    assert body["parameters"] == {}


def test_token_is_required(settings):
    with TestClient(create_app(settings)) as client:
        response = client.get("/mcp/parameters")
    assert response.status_code == 200
    assert response.json() == {
        "validation": {},
        "status": 1001,
        "description": "token required - see competition coordinator",
    }


def test_token_format(settings):
    with TestClient(create_app(settings)) as client:
        for token in ("x" * 33, "bad token", "semi;colon"):
            body = client.get("/mcp/parameters", params={"token": token}).json()
            assert body["status"] == 1000, token
        for token in ("x" * 32, "with-dash_ok"):
            body = client.get("/mcp/parameters", params={"token": token}).json()
            assert body["status"] != 1000, token
