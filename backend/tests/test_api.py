"""End-to-end HTTP tests: login, auth, lesson flow. Fixtures client/clock/parent: conftest."""

import uuid

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Child, Parent
from app.seed import load_topics
from app.services import login_codes, pairing
from app.services.lessons import part_sizes
from tests.conftest import CONTENT_DIR, Clock


async def pair(
    db: AsyncSession, client: AsyncClient, parent: Parent, child: Child, clock: Clock
) -> dict[str, str]:
    """Log a device in with the child's code; returns the auth header."""
    await login_codes.ensure_code(db, child, clock.moment)
    body = {"word": child.code_word, "pin": child.code_pin, "device_name": "iPad"}
    response = await client.post("/api/login", json=body)
    assert response.status_code == 200, response.text
    token: str = response.json()["device_token"]
    return {"Authorization": f"Bearer {token}"}


async def test_requests_need_a_valid_device_token(
    db: AsyncSession, client: AsyncClient, parent: Parent, child: Child, clock: Clock
) -> None:
    assert (await client.get("/api/me")).status_code == 401
    assert (
        await client.get("/api/me", headers={"Authorization": "Bearer nope"})
    ).status_code == 401

    headers = await pair(db, client, parent, child, clock)
    assert (await client.get("/api/me", headers=headers)).status_code == 200

    (device,) = await pairing.active_devices(db, child.id)
    await pairing.revoke_device(db, device.id, clock.moment)
    assert (await client.get("/api/me", headers=headers)).status_code == 401


async def test_full_lesson_flow_over_http(
    db: AsyncSession, client: AsyncClient, parent: Parent, child: Child, clock: Clock
) -> None:
    headers = await pair(db, client, parent, child, clock)

    me = (await client.get("/api/me", headers=headers)).json()
    assert me["settings"] == {"rate": 10, "cap_lari": 15, "show_hint": True}
    assert me["week"] == {
        "week_start": "2026-09-21",
        "today": "2026-09-22",
        "coins": 0,
        "lari": 0.0,
        "study_days": [],
    }
    content = load_topics(CONTENT_DIR)
    lessons = me["lessons"]
    n_lessons = sum(len(part_sizes(len(t.words))) for t in content)
    assert [lsn["number"] for lsn in lessons] == list(range(1, n_lessons + 1))
    assert [lsn["topic_slug"] for lsn in lessons[:5]] == [
        "letters-1",
        "letters-2",
        "letters-3",
        "letters-4",
        "syllables",
    ]
    assert (lessons[0]["status"], lessons[0]["playable"]) == ("current", True)
    # letters-2 waits for letters-1: topics go in order within a section.
    assert (lessons[1]["status"], lessons[1]["playable"]) == ("current", False)
    colors = next(lsn for lsn in lessons if lsn["topic_slug"] == "colors")
    assert (colors["total"], colors["introduced"], colors["status"]) == (10, 0, "current")
    assert colors["playable"] is False  # basics comes first among the word topics
    basics = next(lsn for lsn in lessons if lsn["topic_slug"] == "basics")
    topics = me["topics"]
    assert [t["slug"] for t in topics[:5]] == [lsn["topic_slug"] for lsn in lessons[:5]]
    assert len(topics) == len(content)
    assert all(t["done"] is False for t in topics)
    firsts = {"letters-1", "syllables", "basics"}  # the first topic of each section
    assert all(t["status"] == ("open" if t["slug"] in firsts else "locked") for t in topics)
    assert me["today_lesson"] is None
    assert me["review_available"] is False
    assert len(me["stickers"]) == sum(len(t.words) for t in content)
    # every lesson has its words, in path order
    assert sorted(set(s["lesson"] for s in me["stickers"])) == [lsn["number"] for lsn in lessons]
    assert [s["lesson"] for s in me["stickers"]] == sorted(s["lesson"] for s in me["stickers"])

    started = await client.post("/api/sessions", json={"lesson": basics["number"]}, headers=headers)
    assert started.status_code == 200, started.text
    session_id, steps = started.json()["session_id"], started.json()["steps"]
    assert [s["type"] for s in steps] == ["intro"] * 3 + ["listen"] * 3

    listen_index = 3
    step = steps[listen_index]
    wrong = next(o["slug"] for o in step["options"] if o["slug"] != step["word"]["slug"])
    bad = await client.post(
        f"/api/sessions/{session_id}/answers",
        json={
            "step_index": listen_index,
            "word_slug": wrong,
            "attempt": 1,
            "client_answer_id": str(uuid.uuid4()),
        },
        headers=headers,
    )
    assert bad.json()["correct"] is False and bad.json()["coins_gained"] == 0

    answer_id = str(uuid.uuid4())
    payload = {
        "step_index": 4,
        "word_slug": steps[4]["word"]["slug"],
        "attempt": 1,
        "client_answer_id": answer_id,
    }
    good = await client.post(f"/api/sessions/{session_id}/answers", json=payload, headers=headers)
    assert good.json() == {
        "correct": True,
        "coins_gained": 1,
        "word_learned": False,
        "week_coins": 1,
        "week_lari": 0.1,
    }
    retry = await client.post(f"/api/sessions/{session_id}/answers", json=payload, headers=headers)
    assert retry.json() == good.json()

    invalid = await client.post(
        f"/api/sessions/{session_id}/answers",
        json={
            "step_index": 0,
            "word_slug": "red",
            "attempt": 1,
            "client_answer_id": str(uuid.uuid4()),
        },
        headers=headers,
    )
    assert invalid.status_code == 400

    finished = await client.post(f"/api/sessions/{session_id}/finish", headers=headers)
    assert finished.status_code == 200
    assert finished.json()["coins_gained"] == 1

    after_finish = await client.post(
        f"/api/sessions/{session_id}/answers",
        json={
            "step_index": 5,
            "word_slug": steps[5]["word"]["slug"],
            "attempt": 1,
            "client_answer_id": str(uuid.uuid4()),
        },
        headers=headers,
    )
    assert after_finish.status_code == 409

    me = (await client.get("/api/me", headers=headers)).json()
    assert me["week"]["coins"] == 1 and me["week"]["study_days"] == ["2026-09-22"]
    basics = next(lsn for lsn in me["lessons"] if lsn["topic_slug"] == "basics")
    assert (basics["introduced"], basics["status"], basics["playable"]) == (3, "current", True)
    assert me["today_lesson"] == basics["number"]
    by_slug = {t["slug"]: t["status"] for t in me["topics"]}
    assert (by_slug["basics"], by_slug["colors"], by_slug["letters-1"]) == (
        "today",
        "locked",
        "open",
    )
    locked = await client.post("/api/sessions", json={"lesson": colors["number"]}, headers=headers)
    assert locked.status_code == 409

    foreign = await client.post(f"/api/sessions/{uuid.uuid4()}/finish", headers=headers)
    assert foreign.status_code == 404

    # Starting a topic over: the words come back as intro cards, a locked topic is 409.
    restarted = await client.post("/api/topics/basics/restart", headers=headers)
    assert restarted.status_code == 200, restarted.text
    assert [s["word"]["slug"] for s in restarted.json()["steps"] if s["type"] == "intro"] == [
        "dog",
        "cat",
        "apple",
    ]
    assert (await client.post("/api/topics/colors/restart", headers=headers)).status_code == 409
    assert (await client.post("/api/topics/nope/restart", headers=headers)).status_code == 404
