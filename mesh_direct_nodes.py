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

def is_ip_address(value):
    # Simple regex for IPv4 validation
    return re.match(r'^\d{1,3}(\.\d{1,3}){3}$', value) is not None

if len(sys.argv) < 2:
    print(f"Usage: {sys.argv[0]} [ /dev/ttyUSBX | IP address ]")
    sys.exit(1)

TARGET = sys.argv[1]

# Choose flag based on input format
if TARGET.startswith("/dev/"):
    flag = "--port"
elif is_ip_address(TARGET):
    flag = "--host"
else:
    print("Invalid input: must be a serial port (/dev/ttyX) or IP address.")
    sys.exit(1)

try:
    result = subprocess.run(
        ["meshtastic", flag, TARGET, "--info"],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    output = result.stdout

    mesh_start = output.find("Nodes in mesh:")
    if mesh_start == -1:
        print("No 'Nodes in mesh' section found.")
        exit(1)

    mesh_data = output[mesh_start + len("Nodes in mesh:"):].strip()
    mesh_json_block = extract_balanced_braces(mesh_data)

    if not mesh_json_block:
        print("Failed to extract a balanced JSON block from 'Nodes in mesh'.")
        exit(1)

    mesh_nodes = json.loads(mesh_json_block)

    print("Directly connected nodes:")
    for node_id, node in mesh_nodes.items():
        if node.get("hopsAway") == 0:
            user = node.get("user", {})
            name = user.get("longName", "unknown")
            snr = node.get("snr", "N/A")
            last_heard = node.get("lastHeard", "N/A")
            if isinstance(last_heard, (int, float)):
                last_heard_str = format_timestamp(last_heard)
            else:
                last_heard_str = "N/A"
            print(f"- {name} ({node_id}) | SNR: {snr} | Last Heard: {last_heard_str}")

except subprocess.CalledProcessError as e:
    print(f"Error running meshtastic CLI: {e.stderr}")
except json.JSONDecodeError as je:
    print(f"JSON parse error: {je}")
