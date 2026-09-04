"""Render the exported JSON records for human reading without summarizing them."""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def block(value, kind="text"):
    text = value if isinstance(value,str) else json.dumps(value,indent=2,ensure_ascii=False)
    # Use a delimiter longer than any run of backticks in the model output.
    fence = "`" * max(4, max((len(s) for s in __import__('re').findall(r'`+',text)),default=0)+1)
    return f"{fence}{kind}\n{text}\n{fence}\n"


def main():
    for path in sorted(HERE.glob("*.json")):
        data = json.loads(path.read_text())
        e = data["episode"]
        parts = [f"# {path.stem}\n", data["selection_note"]+"\n",
                 f"Source: `{data['source_record']}/{data['source_episode']}`.\n",
                 f"[Machine-readable record]({path.name}). Selected illustration, not a random sample.\n",
                 "## Conversation\n"]
        for i,m in enumerate(e.get("messages", [])):
            parts.append(f"### Message {i}: {m['role']}" + (f" / {m['name']}" if m.get('name') else "") + "\n")
            if m.get("content") is not None:
                parts.append(block(m["content"]))
            if m.get("_reasoning"):
                parts.extend(["Returned reasoning:\n",block(m["_reasoning"])])
            if m.get("tool_calls"):
                parts.append(block(m["tool_calls"],"json"))
        parts.extend(["## Separately recorded reasoning\n",
                      "Original turn indices are retained below. These are model-provided traces, not guaranteed internal motives.\n",
                      block(e.get("reasoning",e.get("reasoning_trace",[])),"json"),
                      "## Tool events\n",block(e.get("events",e.get("runtime_events",[])),"json")])
        for key in ("scores","final_state","note_text_raw","note_text","shadow_render","shadow_log_at_episode_end"):
            if key in e:
                parts.extend([f"## {key}\n",block(e[key])])
        path.with_suffix(".md").write_text("\n".join(parts))


if __name__ == "__main__":
    main()
