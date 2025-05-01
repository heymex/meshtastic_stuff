import subprocess
import json
import datetime
import sys
import re

def extract_balanced_braces(text):
    start = text.find('{')
    if start == -1:
        return None
    count = 0
    end = start
    while end < len(text):
        if text[end] == '{':
            count += 1
        elif text[end] == '}':
            count -= 1
            if count == 0:
                return text[start:end + 1]
        end += 1
    return None

def format_timestamp(ts):
    try:
        return datetime.datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')
    except Exception:
        return "Invalid timestamp"

def parse_age_string(age_str):
    match = re.match(r"(\d+)([smhd])", age_str)
    if not match:
        return None
    value, unit = int(match.group(1)), match.group(2)
    if unit == 's':
        return datetime.timedelta(seconds=value)
    if unit == 'm':
        return datetime.timedelta(minutes=value)
    if unit == 'h':
        return datetime.timedelta(hours=value)
    if unit == 'd':
        return datetime.timedelta(days=value)
    return None

def get_nodes(port):
    result = subprocess.run(
        ["meshtastic", "--port", port, "--info"],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    output = result.stdout

    mesh_start = output.find("Nodes in mesh:")
    if mesh_start == -1:
        print("No 'Nodes in mesh' section found.")
        sys.exit(1)

    mesh_data = output[mesh_start + len("Nodes in mesh:"):].strip()
    mesh_json_block = extract_balanced_braces(mesh_data)

    if not mesh_json_block:
        print("Failed to extract a balanced JSON block from 'Nodes in mesh'.")
        sys.exit(1)

    return json.loads(mesh_json_block)

if len(sys.argv) < 2:
    print(f"Usage: {sys.argv[0]} /dev/ttyUSBX [--direct | --routers] [--age 1h] [--json-out filename.json]")
    sys.exit(1)

PORT = sys.argv[1]
MODE = "all"  # default if no mode flag is specified
AGE_FILTER = None
JSON_OUT = None

# Parse additional arguments
for i in range(2, len(sys.argv)):
    if sys.argv[i] == "--direct":
        MODE = "direct"
    elif sys.argv[i] == "--routers":
        MODE = "routers"
    elif sys.argv[i] == "--age" and i + 1 < len(sys.argv):
        AGE_FILTER = parse_age_string(sys.argv[i + 1])
    elif sys.argv[i] == "--json-out" and i + 1 < len(sys.argv):
        JSON_OUT = sys.argv[i + 1]

try:
    mesh_nodes = get_nodes(PORT)
    node_list = []
    now = datetime.datetime.now()

    for node_id, node in mesh_nodes.items():
        user = node.get("user", {})
        role = (node.get("role") or user.get("role") or "unknown").upper()
        name = user.get("longName", "unknown")
        snr = node.get("snr", "N/A")
        last_heard = node.get("lastHeard", None)

        # Apply mode filtering
        if MODE == "direct" and node.get("hopsAway") != 0:
            continue
        if MODE == "routers" and not any(r in role for r in ["ROUTER", "REPEATER"]):
            continue

        # Apply age filtering
        if AGE_FILTER and isinstance(last_heard, (int, float)):
            last_heard_time = datetime.datetime.fromtimestamp(last_heard)
            if now - last_heard_time > AGE_FILTER:
                continue

        node_list.append({
            "name": name,
            "id": node_id,
            "role": role,
            "snr": snr,
            "last_heard": last_heard,
            "last_heard_str": format_timestamp(last_heard) if last_heard else "N/A"
        })

    # Sort by most recent last_heard
    node_list.sort(key=lambda x: x["last_heard"] or 0, reverse=True)

    # Report header
    mode_label = {
        "direct": "Directly Connected Nodes",
        "routers": "Router and Repeater Nodes",
        "all": "All Nodes"
    }.get(MODE, "All Nodes")

    print(f"\n{mode_label} (Filtered & Sorted):")
    for node in node_list:
        print(f"- {node['name']} ({node['id']}) | Role: {node['role']} | SNR: {node['snr']} | Last Heard: {node['last_heard_str']}")

    # Optional JSON export
    if JSON_OUT:
        with open(JSON_OUT, 'w') as f:
            json.dump(node_list, f, indent=2)
        print(f"\nJSON report saved to {JSON_OUT}")

except subprocess.CalledProcessError as e:
    print(f"Error running meshtastic CLI: {e.stderr}")
except json.JSONDecodeError as je:
    print(f"JSON parse error: {je}")
