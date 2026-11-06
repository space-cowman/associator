"""Activity generator for the live site (owner's pre-launch test; every account is the owner's)."""

import hashlib
import json
import os
import random
import re
import sys
import time
import uuid
from datetime import timedelta
from pathlib import Path
from typing import Any

import httpx
import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "phase-1-core/api/src"))
from topics import CLUSTERS, FIRST, INSTRUCTIONS, WORDS  # noqa: E402

DESCRIPTIONS = dict(CLUSTERS)

from api.auth import issue_token  # noqa: E402
from api.routes.signin import TERMS_VERSION, reserved_handle  # noqa: E402

BASE = os.environ.get("LOADGEN_BASE", "https://associator.space")
GATEWAY = os.environ.get("LOADGEN_GATEWAY", "http://127.0.0.1:14000")
MANIFEST = Path(os.environ.get("LOADGEN_MANIFEST", ".secrets/loadgen/manifest.json"))
WAVES = int(os.environ.get("LOADGEN_WAVES", "6"))
INTERVAL = int(os.environ.get("LOADGEN_INTERVAL", "1200"))
PEOPLE = int(os.environ.get("LOADGEN_PEOPLE", "100"))
THREADS_PER_WAVE = int(os.environ.get("LOADGEN_THREADS", "170"))
DRAFTS_PER_WAVE = int(os.environ.get("LOADGEN_DRAFTS", "17"))
PACE = 0.25
OUTPUT_PER_MINUTE = 900

_spent: list[tuple[float, int]] = []


def _wait_for_tokens(need: int) -> None:
    """Sleep until the last 60 seconds' output tokens plus `need` fit the per-minute budget."""
    while True:
        now = time.monotonic()
        _spent[:] = [(t, n) for t, n in _spent if now - t < 60]
        used = sum(n for _, n in _spent)
        if used + need <= OUTPUT_PER_MINUTE or not _spent:
            return
        time.sleep(60 - (now - _spent[0][0]) + 0.5)


rng = random.Random()


def _db() -> psycopg.Connection:
    """Connect to the database."""
    return psycopg.connect(
        host="127.0.0.1",
        port=15432,
        dbname="platform_v2",
        user="platform_v2_owner",
        password=os.environ["PG_OWNER_PASSWORD"],
        autocommit=True,
    )


def load_manifest() -> dict[str, Any]:
    """Read what earlier runs created."""
    if MANIFEST.exists():
        return json.loads(MANIFEST.read_text())
    return {"people": [], "clusters": []}


def save_manifest(m: dict[str, Any]) -> None:
    """Save what this run created."""
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(m, indent=1))


def _handle(taken: set[str]) -> str:
    """A new unused handle."""
    while True:
        style = rng.random()
        if style < 0.4:
            h = f"{rng.choice(FIRST)}-{rng.choice(WORDS)}"
        elif style < 0.7:
            h = f"{rng.choice(WORDS)}-{rng.choice(WORDS)}{rng.randint(1, 99)}"
        else:
            h = f"{rng.choice(FIRST)}{rng.randint(2, 999)}"
        if h not in taken and not reserved_handle(h) and 3 <= len(h) <= 30:
            return h


def make_people(m: dict[str, Any], n: int) -> None:
    """Create the test people."""
    with _db() as conn:
        taken = {r[0] for r in conn.execute("SELECT handle FROM users")}
        while len(m["people"]) < n:
            handle = _handle(taken)
            taken.add(handle)
            days = rng.randint(3, 120)
            (uid,) = conn.execute(
                "INSERT INTO users (handle, auth_provider, provider_user_id_hash, terms_version,"
                " terms_accepted_at, created_at) VALUES (%s, 'dev', %s, %s, now(),"
                " now() - make_interval(days => %s)) RETURNING id",
                (
                    handle,
                    hashlib.sha256(f"loadgen:{handle}".encode()).hexdigest(),
                    TERMS_VERSION,
                    days,
                ),
            ).fetchone()  # type: ignore[misc]
            m["people"].append({"id": str(uid), "handle": handle})
            save_manifest(m)


class Person:
    def __init__(self, d: dict[str, str]) -> None:
        """Load a test person."""
        self.id, self.handle = uuid.UUID(d["id"]), d["handle"]
        hours = timedelta(hours=4)
        self.h = {"Authorization": f"Bearer {issue_token(self.id, self.handle, 'human', hours)}"}
        self.agent = {
            "Authorization": f"Bearer {issue_token(self.id, self.handle, 'agent', hours)}"
        }
        self.mcp_token: str | None = None
        self.clusters: list[str] = []


api = httpx.Client(base_url=f"{BASE}/api", timeout=180)
gw = httpx.Client(base_url=GATEWAY, timeout=180)
stats: dict[str, int] = {}


def count(key: str) -> None:
    """Count one action."""
    stats[key] = stats.get(key, 0) + 1


def call(method: str, path: str, headers: dict[str, str], body: Any = None) -> httpx.Response:
    """Call the api."""
    time.sleep(PACE)
    for _ in range(3):
        r = api.request(method, path, headers=headers, json=body)
        if r.status_code == 429 and "Retry-After" in r.headers:
            time.sleep(min(int(r.headers["Retry-After"]), 60))
            continue
        return r
    return r


def post(path: str, who: Person, body: dict[str, Any], agent: bool = False) -> httpx.Response:
    """Post to the api as a person."""
    r = call("POST", path, who.agent if agent else who.h, body)
    if r.status_code == 422 and "confirm_personal_data" in r.text:
        r = call(
            "POST", path, who.agent if agent else who.h, {**body, "confirm_personal_data": True}
        )
    return r


def write(prompt: str, who: Person) -> Any:
    """Ask the small model for JSON, paced to its free quota."""
    for _ in range(3):
        _wait_for_tokens(600)
        try:
            r = gw.post(
                "/complete",
                json={
                    "request_id": uuid.uuid4().hex,
                    "user_id": str(who.id),
                    "model": "platform-small",
                    "system": "You write realistic posts for an online question-and-discussion"
                    " community. Reply with JSON only. Never include real names, emails,"
                    " phone numbers, API keys or passwords.",
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 1800,
                },
            )
        except httpx.HTTPError:
            time.sleep(10)
            continue
        if r.status_code == 429:
            time.sleep(float(r.json()["detail"].get("retry_after") or 20) + 1)
            continue
        if r.status_code != 200:
            return None
        usage = r.json()["usage"]
        _spent.append((time.monotonic(), usage["output_tokens"]))
        found = re.search(r"\{.*\}", r.json()["text"], re.DOTALL)
        try:
            return json.loads(found.group(0)) if found else None
        except ValueError:
            return None
    return None


def mcp(token: str, tool: str, args: dict[str, Any]) -> dict[str, Any] | None:
    """Call an MCP tool."""
    headers = {
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
        "MCP-Protocol-Version": "2025-06-18",
        "Authorization": f"Bearer {token}",
    }
    with httpx.Client(base_url=BASE, timeout=120) as c:
        init = c.post(
            "/mcp",
            headers=headers,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "assistant", "version": "1"},
                },
            },
        )
        if init.status_code != 200:
            return None
        if session := init.headers.get("mcp-session-id"):
            headers["Mcp-Session-Id"] = session
        c.post(
            "/mcp", headers=headers, json={"jsonrpc": "2.0", "method": "notifications/initialized"}
        )
        r = c.post(
            "/mcp",
            headers=headers,
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": tool, "arguments": args},
            },
        )
    text = r.text
    if r.headers.get("content-type", "").startswith("text/event-stream"):
        text = next((ln[5:] for ln in r.text.splitlines() if ln.startswith("data:")), "{}")
    result: dict[str, Any] | None = json.loads(text).get("result")
    return result


def ensure_clusters(m: dict[str, Any], people: list[Person], how_many: int) -> None:
    """Make sure the test clusters exist."""
    existing = set(m["clusters"])
    todo = [c for c in CLUSTERS if c[0] not in {x.split("|")[0] for x in existing}][:how_many]
    for name, description in todo:
        creator = rng.choice(people)
        r = post("/groups", creator, {"name": name, "description": description})
        if r.status_code == 201:
            m["clusters"].append(f"{name}|{r.json()['slug']}")
            save_manifest(m)
            count("clusters")
    slugs = [x.split("|")[1] for x in m["clusters"]]
    for p in people:
        for slug in rng.sample(slugs, k=min(len(slugs), rng.randint(3, 8))):
            if (
                slug not in p.clusters
                and call("PUT", f"/groups/{slug}/membership", p.h).status_code == 204
            ):
                p.clusters.append(slug)


def topic_of(m: dict[str, Any], slug: str) -> str:
    """The topic of a cluster."""
    for x in m["clusters"]:
        name, s = x.split("|")
        if s == slug:
            return name
    return slug


def ask_questions(m: dict[str, Any], people: list[Person], n: int) -> list[dict[str, Any]]:
    """Post test questions."""
    made: list[dict[str, Any]] = []
    slugs = [x.split("|")[1] for x in m["clusters"]]
    while len(made) < n:
        slug = rng.choice(slugs)
        members = [p for p in people if slug in p.clusters] or people
        batch = write(
            f"Write 10 different posts people might share in a '{topic_of(m, slug)}' community"
            f" ({DESCRIPTIONS.get(topic_of(m, slug), '')}). Mostly questions, plus opinions,"
            " recommendation requests and stories; beginners and experts; short and detailed;"
            " casual tone, small typos are fine. Match the community: code or error messages"
            " only in technical ones, jokes and captions in meme ones, numbers in money ones"
            ' (no guaranteed returns). Each at most 450 characters. JSON: {"questions": ["..."]}',
            rng.choice(members),
        )
        for text in (batch or {}).get("questions", [])[:10]:
            if not isinstance(text, str) or not 10 <= len(text) <= 500:
                continue
            asker = rng.choice(members)
            if rng.random() < 0.2:
                if asker.mcp_token is None:
                    t = call("POST", "/me/tokens", asker.h, {"name": "my assistant"})
                    asker.mcp_token = t.json().get("token") if t.status_code == 201 else None
                res = (
                    mcp(asker.mcp_token, "post_question", {"group": slug, "text": text})
                    if asker.mcp_token
                    else None
                )
                found = re.search(r"thread_id[^0-9a-f]{1,12}([0-9a-f-]{36})", json.dumps(res or {}))
                if found:
                    made.append({"id": found.group(1), "text": text, "asker": asker, "slug": slug})
                    count("threads_mcp")
                continue
            r = post("/threads", asker, {"group": slug, "text": text})
            if r.status_code == 201:
                made.append({"id": r.json()["id"], "text": text, "asker": asker, "slug": slug})
                count("threads")
    return made


def reply_to(threads: list[dict[str, Any]], people: list[Person]) -> None:
    """Post test replies."""
    for i in range(0, len(threads), 3):
        group = threads[i : i + 3]
        listing = "\n".join(f"{n}. {t['text']}" for n, t in enumerate(group))
        batch = write(
            "For each post below, write 2 to 6 replies from different people in an online"
            " community: helpful answers, short follow-up questions, disagreements, jokes where"
            " it fits, 'this worked for me', thanks. Some replies answer an earlier reply"
            " (give its number in reply_to)."
            ' Each at most 300 characters, natural tone. JSON: {"threads": [{"question": 0,'
            ' "replies": [{"text": "...", "reply_to": null}]}]}\n\n' + listing,
            rng.choice(people),
        )
        for entry in (batch or {}).get("threads", []):
            q = entry.get("question")
            if not isinstance(q, int) or not 0 <= q < len(group):
                continue
            thread = group[q]
            members = [
                p for p in people if thread["slug"] in p.clusters and p is not thread["asker"]
            ]
            ids: list[str | None] = []
            for rep in entry.get("replies", [])[:6]:
                text = rep.get("text") if isinstance(rep, dict) else None
                if not isinstance(text, str) or not 2 <= len(text) <= 500 or not members:
                    ids.append(None)
                    continue
                parent = rep.get("reply_to")
                parent_id = (
                    ids[parent] if isinstance(parent, int) and 0 <= parent < len(ids) else None
                )
                r = post(
                    f"/threads/{thread['id']}/replies",
                    rng.choice(members),
                    {"text": text, "parent_id": parent_id},
                )
                ids.append(r.json()["id"] if r.status_code == 201 else None)
                count("replies")
            thread["replies"] = [x for x in ids if x]


def ai_drafts(threads: list[dict[str, Any]], people: list[Person], n: int) -> bool:
    """Platform AI drafts, decided like people do."""
    for thread in rng.sample(threads, k=min(n, len(threads))):
        who = rng.choice([p for p in people if thread["slug"] in p.clusters] or people)
        r = post(
            f"/threads/{thread['id']}/drafts",
            who,
            {
                "mode": "platform_ai",
                "instruction": rng.choice(INSTRUCTIONS),
                "idempotency_key": uuid.uuid4().hex,
            },
        )
        if r.status_code == 429:
            return False
        if r.status_code != 201:
            continue
        d = r.json()
        roll = rng.random()
        if roll < 0.70:
            call("POST", f"/drafts/{d['id']}/approve", who.h, {"confirm_personal_data": True})
            count("drafts_approved")
        elif roll < 0.85:
            first = re.split(r"(?<=[.!?])\s", d["text"], maxsplit=1)[0]
            call(
                "POST",
                f"/drafts/{d['id']}/approve",
                who.h,
                {"text": first, "confirm_personal_data": True},
            )
            count("drafts_edited")
        else:
            call("POST", f"/drafts/{d['id']}/discard", who.h)
            count("drafts_discarded")
    return True


def vote_and_mark(threads: list[dict[str, Any]], people: list[Person]) -> None:
    """Vote and mark answers Satisfied."""
    for thread in threads:
        voters = rng.sample(people, k=rng.randint(0, 12))
        for v in voters:
            if v is not thread["asker"]:
                call(
                    "POST",
                    f"/threads/{thread['id']}/vote",
                    v.agent if rng.random() < 0.15 else v.h,
                    {"value": 1 if rng.random() < 0.85 else -1},
                )
                count("votes")
        for reply in thread.get("replies", []):
            for v in rng.sample(people, k=rng.randint(0, 6)):
                call(
                    "POST",
                    f"/replies/{reply}/vote",
                    v.agent if rng.random() < 0.15 else v.h,
                    {"value": 1 if rng.random() < 0.8 else -1},
                )
                count("votes")
        if thread.get("replies") and rng.random() < 0.3:
            call(
                "PUT",
                f"/threads/{thread['id']}/satisfied",
                thread["asker"].h,
                {"reply_id": rng.choice(thread["replies"])},
            )
            count("satisfied")


def main() -> None:
    """Run the load test waves."""
    m = load_manifest()
    make_people(m, PEOPLE)
    people = [Person(p) for p in m["people"]]
    drafts_on = True
    for wave in range(WAVES):
        started = time.monotonic()
        ensure_clusters(m, people, 30 if wave == 0 else 6)
        threads = ask_questions(m, people, THREADS_PER_WAVE)
        reply_to(threads, people)
        if drafts_on:
            drafts_on = ai_drafts(threads, people, DRAFTS_PER_WAVE)
        vote_and_mark(threads, people)
        print(
            f"wave {wave + 1}/{WAVES} done in {int(time.monotonic() - started)} s: {stats}",
            flush=True,
        )
        if wave < WAVES - 1:
            time.sleep(max(0, INTERVAL - (time.monotonic() - started)))


if __name__ == "__main__":
    main()
