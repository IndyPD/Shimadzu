import json

def slim_blackboard(input_path, output_path):
    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    slimmed = {}
    for k, v in data.items():
        if isinstance(v, (int, float)) and v != 0:
            slimmed[k] = v
        elif isinstance(v, bool) and v:
            slimmed[k] = v
        elif isinstance(v, str) and v.strip():
            slimmed[k] = v
        elif isinstance(v, dict):  # nested block (rare, e.g., "indy")
            if any(val not in [0, False, "", None] for val in v.values()):
                slimmed[k] = v

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(slimmed, f, indent=2)

    print(f"[Slimmer] Slimmed {len(data)} → {len(slimmed)} keys. Saved to {output_path}")


if __name__ == "__main__":
    slim_blackboard("blackboard.json", "blackboard.slimmed.json")
