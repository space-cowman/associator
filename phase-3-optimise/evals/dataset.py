"""Upload the draft test sets to LangSmith (run: make evals-dataset)."""

import json
import os
from pathlib import Path

from langsmith import Client

from api import prompts

DATASETS = {
    "associator-draft-questions": (
        "questions.jsonl",
        "Realistic 'my AI's answer did not work' developer questions, plus "
        "prompt-injection probes, formatted exactly as Associator sends a draft request.",
    ),
    "associator-multipart-questions": (
        "multipart.jsonl",
        "Questions with two or three parts (why, how, and an opinion) across the site's topics: "
        "where splitting the work over several models can help.",
    ),
}


def main() -> None:
    """Upload the test sets to LangSmith."""
    client = Client(
        api_url=os.environ["LANGSMITH_ENDPOINT"], api_key=os.environ["LANGSMITH_API_KEY"]
    )
    for name, (file, description) in DATASETS.items():
        upload(client, name, file, description)


def upload(client: Client, name: str, file: str, description: str) -> None:
    """Upload one test set if it changed."""
    rows = [
        json.loads(line) for line in (Path(__file__).parent / file).read_text().splitlines() if line
    ]
    if client.has_dataset(dataset_name=name):
        dataset = client.read_dataset(dataset_name=name)
        old = [e.id for e in client.list_examples(dataset_id=dataset.id)]
        if len(old) == len(rows):
            print(f"{name}: {len(rows)} examples (unchanged)")
            return
        if old:
            client.delete_examples(example_ids=old)
    else:
        dataset = client.create_dataset(name, description=description)
    client.create_examples(
        dataset_id=dataset.id,
        inputs=[
            {
                "system": prompts.SYSTEM,
                "messages": prompts.draft_messages(r["thread"], None, r["instruction"]),
            }
            for r in rows
        ],
        metadata=[{"topic": r["topic"]} for r in rows],
    )
    topics = sorted({r["topic"] for r in rows})
    print(f"{name}: {len(rows)} examples ({', '.join(topics)})")


if __name__ == "__main__":
    main()
