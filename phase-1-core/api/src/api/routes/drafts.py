"""AI drafts that wait for their owner's approval."""

import json
import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from api import (
    formatting,
    llm_client,
    memory,
    metrics,
    orchestrator_client,
    prompts,
    ratelimit,
    safety_client,
)
from api.auth import CurrentUser, current_user
from api.routes.replies import CREATE_LIMIT as REPLY_LIMIT
from api.routes.replies import CREATE_WINDOW_SECONDS as REPLY_WINDOW
from api.routes.replies import insert_reply
from api.routes.threads import PostText
from api.validation import safe_multiline
from api.visibility import ensure_visible

router = APIRouter()

DRAFT_LIMIT = 30
DRAFT_WINDOW_SECONDS = 3600
TEXT_LIMIT = 500
MAX_SHORTEN = 2
MAX_TOKENS = 1500

Instruction = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=300),
    AfterValidator(safe_multiline),
]
Mode = Literal["ask_my_ai", "platform_ai"]


class DraftIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Mode
    instruction: Instruction
    parent_id: uuid.UUID | None = None
    idempotency_key: str = Field(pattern=r"^[A-Za-z0-9-]{8,64}$")
    memory_on: bool = False


class ApproveIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: PostText | None = None
    confirm_personal_data: bool = False


class DraftOut(BaseModel):
    id: uuid.UUID
    thread_id: uuid.UUID
    parent_id: uuid.UUID | None
    status: str
    mode: str
    text: str
    instruction: str
    model_label: str | None
    warnings: list[str]
    reply_id: uuid.UUID | None
    created_at: datetime
    decided_at: datetime | None
    models_used: list[str]
    plan: list[dict[str, Any]]
    memory_used: list[str]


_SELECT = (
    "SELECT id, thread_id, parent_id, status, mode, text, instruction, model_label,"
    " safety_report, reply_id, created_at, decided_at, run_id, models_used, plan, memory_used"
    " FROM drafts"
)


def _out(row: Any, memory_texts: dict[uuid.UUID, str] | None = None) -> DraftOut:
    """Shape one draft for the response."""
    m = dict(row._mapping)
    report = m.pop("safety_report") or {}
    m.pop("run_id")
    used = [memory_texts[i] for i in m.pop("memory_used") if memory_texts and i in memory_texts]
    return DraftOut(**m, warnings=[str(w) for w in report.get("warnings", [])], memory_used=used)


async def _memory_texts(
    request: Request, user_id: uuid.UUID, rows: list[Any]
) -> dict[uuid.UUID, str]:
    """The texts of the memory items these drafts used (items deleted since are left out)."""
    if not any(r.memory_used for r in rows):
        return {}
    return {i.id: i.text for i in await memory.load(request, user_id)}


async def _outs(request: Request, user_id: uuid.UUID, rows: list[Any]) -> list[DraftOut]:
    """Shape drafts, with the memory items they used."""
    texts = await _memory_texts(request, user_id, rows)
    return [_out(r, texts) for r in rows]


async def _replace_pending(conn: Any, user_id: uuid.UUID, thread_id: uuid.UUID) -> list[uuid.UUID]:
    """One pending draft per user per question: a new one replaces the earlier one."""
    rows = await conn.execute(
        text(
            "UPDATE drafts SET status = 'discarded', decided_at = now()"
            " WHERE user_id = :u AND thread_id = :t AND status = 'pending' RETURNING run_id"
        ),
        {"u": user_id, "t": thread_id},
    )
    return [r.run_id for r in rows if r.run_id is not None]


def _human(user: CurrentUser) -> None:
    """Only the person, not an AI app, may do this."""
    if user.actor != "human":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Drafts are requested by you, not your AI")


async def _write(
    request: Request, user: CurrentUser, mode: Mode, messages: list[dict[str, str]]
) -> llm_client.Answer:
    """Ask the model; if the reply is too long, ask it to shorten (never truncate)."""
    own = mode == "ask_my_ai"
    answer = await llm_client.complete(
        request,
        user,
        own_model=own,
        system=prompts.SYSTEM,
        messages=messages,
        max_tokens=MAX_TOKENS,
        trace="draft",
    )
    for _ in range(MAX_SHORTEN):
        if len(prompts.clean_output(answer.text)) <= TEXT_LIMIT:
            break
        messages = [
            *messages,
            {"role": "assistant", "content": answer.text},
            {"role": "user", "content": prompts.SHORTEN},
        ]
        answer = await llm_client.complete(
            request,
            user,
            own_model=own,
            system=prompts.SYSTEM,
            messages=messages,
            max_tokens=MAX_TOKENS,
            trace="draft",
        )
    return answer


async def _trace_of(request: Request, draft_id: uuid.UUID) -> uuid.UUID | None:
    """The LangSmith trace id of a draft."""
    async with request.app.state.db.connect() as conn:
        trace: uuid.UUID | None = await conn.scalar(
            text("SELECT trace_id FROM drafts WHERE id = :id"), {"id": draft_id}
        )
    return trace


async def _check_instruction(request: Request, instruction: str) -> None:
    """The instruction is sent to an AI provider: keys and passwords never leave our servers."""
    try:
        await safety_client.check(
            request, instruction, formatting.for_safety(instruction), personal_data="allow"
        )
    except HTTPException as exc:
        if exc.status_code != status.HTTP_422_UNPROCESSABLE_CONTENT:
            raise
        blocks: list[Any] = exc.detail.get("blocks", []) if isinstance(exc.detail, dict) else []
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            {
                "reason": "instruction_blocked",
                "message": ("Your instruction contains a key or password; remove it and try again"),
                "blocks": blocks,
            },
        ) from None


@router.post("/threads/{thread_id}/drafts", status_code=status.HTTP_201_CREATED)
async def create_draft(
    thread_id: uuid.UUID,
    body: DraftIn,
    request: Request,
    user: Annotated[CurrentUser, Depends(current_user)],
) -> DraftOut:
    """Ask an AI to draft a reply for approval."""
    _human(user)
    async with request.app.state.db.connect() as conn:
        await ensure_visible(conn, user.id, thread_id=thread_id)
    db = request.app.state.db
    async with db.connect() as conn:
        existing = (
            await conn.execute(
                text(_SELECT + " WHERE user_id = :u AND idempotency_key = :k"),
                {"u": user.id, "k": body.idempotency_key},
            )
        ).one_or_none()
        if existing is not None:
            return (await _outs(request, user.id, [existing]))[0]
        source = (
            await conn.execute(
                text(
                    "SELECT t.text AS thread_text, p.text AS parent_text FROM threads t"
                    " LEFT JOIN replies p ON p.id = CAST(:parent AS uuid) AND p.thread_id = t.id"
                    " WHERE t.id = :thread AND t.deleted_at IS NULL"
                    " AND (CAST(:parent AS uuid) IS NULL OR p.id IS NOT NULL)"
                ),
                {"thread": thread_id, "parent": body.parent_id},
            )
        ).one_or_none()
    if source is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Thread or parent reply not found")
    await ratelimit.enforce(
        request, f"ratelimit:drafts:{user.id}", DRAFT_LIMIT, DRAFT_WINDOW_SECONDS
    )
    await _check_instruction(request, body.instruction)
    messages = prompts.draft_messages(source.thread_text, source.parent_text, body.instruction)
    if body.memory_on and body.mode != "ask_my_ai":
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            {"reason": "memory_platform", "message": "Platform AI never uses your memory"},
        )
    used: list[memory.Item] = []
    run_id: str | None = None
    models_used: list[str] = []
    plan: list[dict[str, Any]] = []
    if body.mode == "ask_my_ai" and request.app.state.orchestrator is not None:
        if body.memory_on:
            question = [source.thread_text, source.parent_text or "", body.instruction]
            used = await memory.retrieve(request, user, "\n".join(question))
        run = await orchestrator_client.start(
            request, user, system=prompts.SYSTEM, messages=messages, memory=[i.text for i in used]
        )
        draft_text = prompts.clean_output(run.get("text") or "")
        run_id, models_used, plan = run["run_id"], run["models_used"], run["plan"]
        label: str | None = " + ".join(models_used)[:100] or None
        trace_id = run["trace_ids"][0] if run["trace_ids"] else None
    else:
        if body.memory_on:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                {
                    "reason": "memory_unavailable",
                    "message": "Using your memory is not available yet",
                },
            )
        answer = await _write(request, user, body.mode, messages)
        draft_text = prompts.clean_output(answer.text)
        label, trace_id = f"{answer.provider}:{answer.model}", answer.trace_id
    if not draft_text:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            {"reason": "empty_answer", "message": "The model gave no answer. Try again."},
        )
    if len(draft_text) > TEXT_LIMIT:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            {"reason": "too_long", "message": "The model could not answer briefly. Try again."},
        )
    warnings = await safety_client.check(
        request, draft_text, formatting.for_safety(draft_text), personal_data="allow"
    )

    replaced: list[uuid.UUID] = []
    try:
        async with db.begin() as conn:
            replaced = await _replace_pending(conn, user.id, thread_id)
            row = (
                await conn.execute(
                    text(
                        "INSERT INTO drafts (thread_id, parent_id, user_id, mode, text,"
                        " instruction, model_label, safety_report, idempotency_key, trace_id,"
                        " run_id, models_used, plan, memory_used)"
                        " VALUES (:thread, :parent, :u, :mode, :text, :instruction, :label,"
                        " jsonb_build_object('warnings', CAST(:warnings AS text[])), :key, :trace,"
                        " :run, :models, CAST(:plan AS jsonb), CAST(:memory AS uuid[]))"
                        " RETURNING id, thread_id, parent_id, status, mode, text, instruction,"
                        " model_label, safety_report, reply_id, created_at, decided_at,"
                        " run_id, models_used, plan, memory_used"
                    ),
                    {
                        "thread": thread_id,
                        "parent": body.parent_id,
                        "u": user.id,
                        "mode": body.mode,
                        "text": draft_text,
                        "instruction": body.instruction,
                        "label": label,
                        "trace": trace_id,
                        "warnings": formatting.warning_labels(warnings),
                        "key": body.idempotency_key,
                        "run": run_id,
                        "models": models_used,
                        "plan": json.dumps(plan),
                        "memory": [i.id for i in used],
                    },
                )
            ).one()
    except IntegrityError:
        await orchestrator_client.resume(request, _uuid(run_id), "discarded")
        async with db.connect() as conn:
            row = (
                await conn.execute(
                    text(_SELECT + " WHERE user_id = :u AND idempotency_key = :k"),
                    {"u": user.id, "k": body.idempotency_key},
                )
            ).one()
    for old in replaced:
        await orchestrator_client.resume(request, old, "discarded")
    return _out(row, {i.id: i.text for i in used})


def _uuid(value: str | None) -> uuid.UUID | None:
    """Read a UUID, or None if it is not one."""
    return uuid.UUID(value) if value else None


class AgentDraftIn(BaseModel):
    """An answer written by the user's own AI app (MCP)."""

    model_config = ConfigDict(extra="forbid")

    text: PostText
    parent_id: uuid.UUID | None = None
    idempotency_key: str = Field(pattern=r"^[A-Za-z0-9-]{8,64}$")
    model_label: str = Field(default="your AI app", pattern=r"^[A-Za-z0-9 ._:/()-]{1,60}$")


AGENT_INSTRUCTION = "(given in your AI app)"


@router.post("/threads/{thread_id}/agent-drafts", status_code=status.HTTP_201_CREATED)
async def create_agent_draft(
    thread_id: uuid.UUID,
    body: AgentDraftIn,
    request: Request,
    user: Annotated[CurrentUser, Depends(current_user)],
) -> DraftOut:
    """Store an answer from an AI app as a draft for approval."""
    if user.actor != "agent":
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "For your AI app; on the site, use Ask my AI instead"
        )
    async with request.app.state.db.connect() as conn:
        await ensure_visible(conn, user.id, thread_id=thread_id)
    db = request.app.state.db
    async with db.connect() as conn:
        existing = (
            await conn.execute(
                text(_SELECT + " WHERE user_id = :u AND idempotency_key = :k"),
                {"u": user.id, "k": body.idempotency_key},
            )
        ).one_or_none()
        if existing is not None:
            return (await _outs(request, user.id, [existing]))[0]
        found = await conn.scalar(
            text(
                "SELECT 1 FROM threads t LEFT JOIN replies p"
                " ON p.id = CAST(:parent AS uuid) AND p.thread_id = t.id"
                " WHERE t.id = :thread AND t.deleted_at IS NULL"
                " AND (CAST(:parent AS uuid) IS NULL OR p.id IS NOT NULL)"
            ),
            {"thread": thread_id, "parent": body.parent_id},
        )
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Thread or parent reply not found")
    await ratelimit.enforce(
        request, f"ratelimit:drafts:{user.id}", DRAFT_LIMIT, DRAFT_WINDOW_SECONDS
    )
    warnings = await safety_client.check(
        request, body.text, formatting.for_safety(body.text), personal_data="allow"
    )
    replaced: list[uuid.UUID] = []
    try:
        async with db.begin() as conn:
            replaced = await _replace_pending(conn, user.id, thread_id)
            row = (
                await conn.execute(
                    text(
                        "INSERT INTO drafts (thread_id, parent_id, user_id, mode, text,"
                        " instruction, model_label, safety_report, idempotency_key)"
                        " VALUES (:thread, :parent, :u, 'mcp', :text, :instruction, :label,"
                        " jsonb_build_object('warnings', CAST(:warnings AS text[])), :key)"
                        " RETURNING id, thread_id, parent_id, status, mode, text, instruction,"
                        " model_label, safety_report, reply_id, created_at, decided_at,"
                        " run_id, models_used, plan, memory_used"
                    ),
                    {
                        "thread": thread_id,
                        "parent": body.parent_id,
                        "u": user.id,
                        "text": body.text,
                        "instruction": AGENT_INSTRUCTION,
                        "label": body.model_label,
                        "warnings": formatting.warning_labels(warnings),
                        "key": body.idempotency_key,
                    },
                )
            ).one()
    except IntegrityError:
        async with db.connect() as conn:
            row = (
                await conn.execute(
                    text(_SELECT + " WHERE user_id = :u AND idempotency_key = :k"),
                    {"u": user.id, "k": body.idempotency_key},
                )
            ).one()
    for old in replaced:
        await orchestrator_client.resume(request, old, "discarded")
    return _out(row)


@router.get("/drafts")
async def list_drafts(
    request: Request,
    user: Annotated[CurrentUser, Depends(current_user)],
    status_filter: Annotated[
        Literal["pending", "approved", "discarded"], Query(alias="status")
    ] = "pending",
) -> list[DraftOut]:
    """List my drafts."""
    async with request.app.state.db.connect() as conn:
        rows = await conn.execute(
            text(_SELECT + " WHERE user_id = :u AND status = :s ORDER BY created_at DESC LIMIT 50"),
            {"u": user.id, "s": status_filter},
        )
    return await _outs(request, user.id, list(rows))


@router.post("/drafts/{draft_id}/approve")
async def approve_draft(
    draft_id: uuid.UUID,
    body: ApproveIn,
    request: Request,
    user: Annotated[CurrentUser, Depends(current_user)],
) -> DraftOut:
    """Publish a draft, edited or as is."""
    _human(user)
    async with request.app.state.db.connect() as conn:
        draft = (
            await conn.execute(
                text(_SELECT + " WHERE id = :id AND user_id = :u"), {"id": draft_id, "u": user.id}
            )
        ).one_or_none()
    if draft is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Draft not found")
    if draft.status != "pending":
        raise HTTPException(status.HTTP_409_CONFLICT, f"Draft already {draft.status}")
    final_text = body.text if body.text is not None else draft.text
    checked = await safety_client.check(
        request,
        final_text,
        formatting.for_safety(final_text),
        personal_data="allow" if body.confirm_personal_data else "ask",
    )
    await ratelimit.enforce(
        request, f"ratelimit:replies:create:{user.id}", REPLY_LIMIT, REPLY_WINDOW
    )

    async with request.app.state.db.begin() as conn:
        claimed = (
            await conn.execute(
                text(
                    "UPDATE drafts SET status = 'approved', decided_at = now()"
                    " WHERE id = :id AND user_id = :u AND status = 'pending' RETURNING id"
                ),
                {"id": draft_id, "u": user.id},
            )
        ).one_or_none()
        if claimed is None:
            raise HTTPException(status.HTTP_409_CONFLICT, "Draft already decided")
        reply_id = await insert_reply(
            conn,
            thread_id=draft.thread_id,
            parent_id=draft.parent_id,
            author_id=user.id,
            text=final_text,
            mode=draft.mode,
            model_label=draft.model_label,
            instruction_given=True,
            human_approved=True,
            warnings=formatting.warning_labels(checked),
        )
        if reply_id is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Thread or parent reply not found")
        await conn.execute(
            text("UPDATE drafts SET reply_id = :r WHERE id = :id"), {"r": reply_id, "id": draft_id}
        )
        row = (await conn.execute(text(_SELECT + " WHERE id = :id"), {"id": draft_id})).one()
    edited = body.text is not None and body.text != draft.text
    metrics.draft_decided(
        draft.mode, "edited" if edited else "approved", metrics.draft_path(draft.run_id, draft.plan)
    )
    decision: Literal["edited", "approved"] = "edited" if edited else "approved"
    await llm_client.feedback(
        request, await _trace_of(request, draft_id), decision, final_text if edited else None
    )
    await orchestrator_client.resume(request, draft.run_id, decision)
    return (await _outs(request, user.id, [row]))[0]


@router.post("/drafts/{draft_id}/discard")
async def discard_draft(
    draft_id: uuid.UUID, request: Request, user: Annotated[CurrentUser, Depends(current_user)]
) -> DraftOut:
    """Throw a draft away."""
    _human(user)
    async with request.app.state.db.begin() as conn:
        row = (
            await conn.execute(
                text(
                    "UPDATE drafts SET status = 'discarded', decided_at = now()"
                    " WHERE id = :id AND user_id = :u AND status = 'pending'"
                    " RETURNING id, thread_id, parent_id, status, mode, text, instruction,"
                    " model_label, safety_report, reply_id, created_at, decided_at,"
                    " run_id, models_used, plan, memory_used"
                ),
                {"id": draft_id, "u": user.id},
            )
        ).one_or_none()
        if row is None:
            exists = await conn.scalar(
                text("SELECT status FROM drafts WHERE id = :id AND user_id = :u"),
                {"id": draft_id, "u": user.id},
            )
            if exists is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Draft not found")
            raise HTTPException(status.HTTP_409_CONFLICT, f"Draft already {exists}")
    metrics.draft_decided(row.mode, "discarded", metrics.draft_path(row.run_id, row.plan))
    await llm_client.feedback(request, await _trace_of(request, draft_id), "discarded")
    await orchestrator_client.resume(request, row.run_id, "discarded")
    return (await _outs(request, user.id, [row]))[0]
