"""Ask my AI as a LangGraph flow (ARCHITECTURE.md §6)."""

import operator
from dataclasses import dataclass
from typing import Annotated, Any, Literal, TypedDict

import httpx
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.runtime import Runtime
from langgraph.types import Checkpointer, Send, interrupt

from orchestrator import gateway, prompts, routing, telemetry
from orchestrator.contract import RunIn

TEXT_LIMIT = 500
MAX_SHORTEN = 2
MAX_TOKENS = 1500
PLAN_TOKENS = 1000
PART_TOKENS = 800


@dataclass(frozen=True)
class Context:
    run: RunIn
    client: httpx.AsyncClient


class Answer(TypedDict):
    index: int
    kind: str
    task: str
    model: str
    text: str


class WorkTask(TypedDict):
    """What `plan` sends each parallel `work` node."""

    index: int
    kind: str
    task: str
    model: int


class State(TypedDict, total=False):
    parts: list[dict[str, Any]]
    answers: Annotated[list[Answer], operator.add]
    models_used: Annotated[list[str], operator.add]
    fallback_used: Annotated[bool, operator.or_]
    trace_ids: Annotated[list[str], operator.add]
    draft: str
    writer: Literal["single", "merge"]
    writer_model: int | None
    tries: int
    status: Literal["ready", "failed"]
    reason: str
    decision: str


class AllModelsFailed(Exception):
    pass


def _name(run: RunIn, index: int | None) -> str:
    """The name of a model in the run."""
    return "Platform AI" if index is None else run.models[index].name


async def _ask(
    ctx: Context,
    order: list[int | None],
    *,
    system: str,
    messages: list[dict[str, str]],
    memory: bool,
    max_tokens: int = MAX_TOKENS,
    trace: bool = False,
) -> tuple[gateway.Reply, int | None]:
    """Try each model in order."""
    run = ctx.run
    for index in order:
        own = index is not None
        with_memory = memory and own and bool(run.memory)
        sent_system = system + prompts.MEMORY if with_memory else system
        sent = (
            prompts.add_to_last(messages, prompts.memory_block(run.memory))
            if with_memory
            else messages
        )
        try:
            reply = await gateway.complete(
                ctx.client,
                run,
                None if index is None else run.models[index],
                system=sent_system,
                messages=sent,
                max_tokens=max_tokens,
                trace="draft" if trace else "off",
                trace_messages=messages if trace and with_memory else None,
            )
        except gateway.GatewayError as exc:
            telemetry.model_try(own=own, ok=False, reason=exc.reason)
            continue
        telemetry.model_try(own=own, ok=True)
        return reply, index
    raise AllModelsFailed


def _base(run: RunIn) -> list[dict[str, str]]:
    """The question and instruction as model messages."""
    return [m.model_dump() for m in run.messages]


@telemetry.timed("plan")
async def plan(state: State, runtime: Runtime[Context]) -> State:
    """Platform AI splits the question into parts."""
    run = runtime.context.run
    try:
        reply, _ = await _ask(
            runtime.context,
            [None],
            system=prompts.PLANNER,
            messages=_base(run),
            memory=False,
            max_tokens=PLAN_TOKENS,
        )
    except AllModelsFailed:
        return {"parts": []}
    planned = prompts.parse_plan(reply.text) or []
    if len(planned) < 2:
        return {"parts": []}
    used: list[int] = []
    parts = []
    for p in planned:
        index = routing.pick(p.kind, run.models, used)
        used.append(index)
        parts.append({"kind": p.kind, "task": p.task, "model": index})
    return {"parts": parts}


@telemetry.timed("single")
async def single(state: State, runtime: Runtime[Context]) -> State:
    """Answer with one model."""
    run = runtime.context.run
    first = routing.best(run.models)
    try:
        reply, index = await _ask(
            runtime.context,
            routing.chain(first, run.models),
            system=run.system,
            messages=_base(run),
            memory=True,
            trace=True,
        )
    except AllModelsFailed:
        return {"status": "failed", "reason": "all_models_failed"}
    return {
        "draft": reply.text,
        "writer": "single",
        "writer_model": index,
        "models_used": [_name(run, index)],
        "fallback_used": index != first,
        "trace_ids": [reply.trace_id] if reply.trace_id else [],
    }


@telemetry.timed("work")
async def work(task: WorkTask, runtime: Runtime[Context]) -> State:
    """One part, on the model the plan chose (then the others, then Platform AI)."""
    run = runtime.context.run
    first: int = task["model"]
    messages = prompts.add_to_last(
        _base(run), prompts.quote("part", f"{task['kind']}: {task['task']}")
    )
    try:
        reply, index = await _ask(
            runtime.context,
            routing.chain(first, run.models),
            system=run.system + prompts.PART,
            messages=messages,
            memory=True,
            max_tokens=PART_TOKENS,
        )
    except AllModelsFailed:
        return {"fallback_used": True}
    answer = Answer(
        index=task["index"], kind=task["kind"], task=task["task"],
        model=_name(run, index), text=prompts.trim_part(prompts.clean_output(reply.text)),
    )  # fmt: skip
    return {"answers": [answer], "models_used": [answer["model"]], "fallback_used": index != first}


def _merge_messages(run: RunIn, answers: list[Answer]) -> list[dict[str, str]]:
    """Build the messages that merge the parts."""
    quoted = [
        prompts.quote("answer", f"{a['kind']} ({a['task']}):\n{a['text']}")
        for a in sorted(answers, key=lambda a: a["index"])
    ]
    return prompts.add_to_last(_base(run), *quoted)


@telemetry.timed("merge")
async def merge(state: State, runtime: Runtime[Context]) -> State:
    """Merge the parts into one answer."""
    run = runtime.context.run
    answers = state.get("answers", [])
    if not answers:
        return {"status": "failed", "reason": "all_models_failed"}
    if run.memory:
        order: list[int | None] = routing.chain(
            routing.best(run.models), run.models, platform=False
        )
    else:
        order = [None, *range(len(run.models))]
    try:
        reply, index = await _ask(
            runtime.context,
            order,
            system=run.system + prompts.MERGE,
            messages=_merge_messages(run, answers),
            memory=False,
            trace=True,
        )
    except AllModelsFailed:
        return {"status": "failed", "reason": "all_models_failed"}
    return {
        "draft": reply.text,
        "writer": "merge",
        "writer_model": index,
        "fallback_used": index != order[0],
        "trace_ids": [reply.trace_id] if reply.trace_id else [],
    }


@telemetry.timed("shorten")
async def shorten(state: State, runtime: Runtime[Context]) -> State:
    """Ask the model that wrote the draft to shorten it (never cut mid-sentence)."""
    run = runtime.context.run
    if state["writer"] == "merge":
        system, base = run.system + prompts.MERGE, _merge_messages(run, state.get("answers", []))
        memory, ask = False, prompts.MERGE_SHORTEN
    else:
        system, base, memory, ask = run.system, _base(run), True, prompts.SHORTEN
    messages = [
        *base,
        {"role": "assistant", "content": state["draft"]},
        {"role": "user", "content": ask},
    ]
    writer = state.get("writer_model")
    order: list[int | None] = [writer]
    try:
        reply, _ = await _ask(
            runtime.context, order, system=system, messages=messages, memory=memory
        )
    except AllModelsFailed:
        return {"tries": state.get("tries", 0) + 1}
    return {"draft": reply.text, "tries": state.get("tries", 0) + 1}


async def check(state: State) -> State:
    """Check the answer's length."""
    if state.get("status") == "failed":
        return {}
    text = prompts.clean_output(state.get("draft", ""))
    if not text:
        return {"status": "failed", "reason": "empty_answer"}
    if len(text) <= TEXT_LIMIT:
        return {"draft": text, "status": "ready"}
    if state.get("tries", 0) >= MAX_SHORTEN:
        return {"status": "failed", "reason": "too_long"}
    return {}


async def approve(state: State) -> State:
    """Pause until the person approves, edits or discards (in the api)."""
    decision = interrupt({"draft": state["draft"]})
    return {"decision": str(decision)}


def _start(state: State, runtime: Runtime[Context]) -> Literal["single", "plan"]:
    """Start a run."""
    return "single" if len(runtime.context.run.models) == 1 else "plan"


def _after_plan(state: State) -> list[Send] | Literal["single"]:
    """Choose split or single after planning."""
    parts = state.get("parts", [])
    if not parts:
        return "single"
    return [
        Send("work", WorkTask(index=n, kind=p["kind"], task=p["task"], model=p["model"]))
        for n, p in enumerate(parts)
    ]


def _after_check(state: State) -> Literal["shorten", "approve", "__end__"]:
    """Shorten or finish after the check."""
    status = state.get("status")
    return "approve" if status == "ready" else "__end__" if status == "failed" else "shorten"


def build(checkpointer: Checkpointer = None) -> CompiledStateGraph[State, Context, State, State]:
    """Build the graph."""
    g = StateGraph(State, context_schema=Context)
    g.add_node("plan", plan)
    g.add_node("single", single)
    g.add_node("work", work, input_schema=WorkTask)  # type: ignore[call-overload]
    g.add_node("merge", merge)
    g.add_node("shorten", shorten)
    g.add_node("check", check)
    g.add_node("approve", approve)
    g.add_conditional_edges(START, _start, ["single", "plan"])
    g.add_conditional_edges("plan", _after_plan, ["single", "work"])
    g.add_edge("work", "merge")
    g.add_edge("single", "check")
    g.add_edge("merge", "check")
    g.add_edge("shorten", "check")
    g.add_conditional_edges("check", _after_check, ["shorten", "approve", END])
    g.add_edge("approve", END)
    return g.compile(checkpointer=checkpointer)
