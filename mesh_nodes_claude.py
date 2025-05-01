import subprocess
import json
import datetime
import sys
import re
import argparse
from typing import Dict, List, Optional, Any, Union


def extract_balanced_braces(text: str) -> Optional[str]:
    """
    Extract a JSON object enclosed in balanced braces from text.
    
    Args:
        text: The text to extract from
        
    Returns:
        Extracted JSON string or None if no valid JSON found
    """
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


def format_timestamp(ts: Optional[Union[int, float]]) -> str:
    """
    Format a timestamp to a human-readable date string.
    
    Args:
        ts: Unix timestamp
        
    Returns:
        Formatted date string or error message
    """
    if ts is None:
        return "N/A"
        
    try:
        return datetime.datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')
    except Exception:
        return "Invalid timestamp"


def parse_age_string(age_str: str) -> Optional[datetime.timedelta]:
    """
    Parse an age string (like '1h', '30m', '2d') into a timedelta.
    
    Args:
        age_str: String representing a time period with unit
        
    Returns:
        timedelta object or None if invalid format
    """
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


def get_nodes(port: str) -> Dict[str, Any]:
    """
    Get node information from the Meshtastic device.
    
    Args:
        port: Device port to connect to
        
    Returns:
        Dictionary of node information
        
    Raises:
        SystemExit: If node information cannot be retrieved or parsed
    """
    try:
        result = subprocess.run(
            ["meshtastic", "--port", port, "--info"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=30  # Add timeout to prevent hanging
        )
    except subprocess.CalledProcessError as e:
        print(f"Error running Meshtastic CLI: {e.stderr}")
        sys.exit(1)
    except subprocess.TimeoutExpired:
        print("Meshtastic command timed out. Check your device connection.")
        sys.exit(1)
    except FileNotFoundError:
        print("Meshtastic CLI not found. Make sure it's installed and in your PATH.")
        sys.exit(1)
        
    output = result.stdout

    mesh_start = output.find("Nodes in mesh:")
    if mesh_start == -1:
        print("No 'Nodes in mesh' section found in the output.")
        sys.exit(1)

    mesh_data = output[mesh_start + len("Nodes in mesh:"):].strip()
    mesh_json_block = extract_balanced_braces(mesh_data)

    if not mesh_json_block:
        print("Failed to extract a balanced JSON block from 'Nodes in mesh'.")
        sys.exit(1)

    try:
        return json.loads(mesh_json_block)
    except json.JSONDecodeError as je:
        print(f"Failed to parse JSON: {je}")
        print(f"Raw JSON block: {mesh_json_block[:100]}...")  # Print start of the JSON block
        sys.exit(1)


def filter_and_sort_nodes(
    mesh_nodes: Dict[str, Any], 
    mode: str = "all", 
    age_filter: Optional[datetime.timedelta] = None
) -> List[Dict[str, Any]]:
    """
    Filter and sort mesh nodes based on given criteria.
    
    Args:
        mesh_nodes: Dictionary of node information
        mode: Filter mode ('all', 'direct', or 'routers')
        age_filter: Only include nodes heard within this timedelta
        
    Returns:
        List of filtered and sorted node dictionaries
    """
    node_list = []
    now = datetime.datetime.now()

    for node_id, node in mesh_nodes.items():
        user = node.get("user", {})
        role = (node.get("role") or user.get("role") or "unknown").upper()
        name = user.get("longName") or user.get("shortName") or node_id
        snr = node.get("snr", "N/A")
        last_heard = node.get("lastHeard")
        hops_away = node.get("hopsAway")

        # Apply mode filtering
        if mode == "direct" and hops_away != 0:
            continue
        if mode == "routers" and not any(r in role for r in ["ROUTER", "REPEATER"]):
            continue

        # Apply age filtering
        if age_filter and isinstance(last_heard, (int, float)):
            last_heard_time = datetime.datetime.fromtimestamp(last_heard)
            if now - last_heard_time > age_filter:
                continue

        node_list.append({
            "name": name,
            "id": node_id,
            "role": role,
            "snr": snr,
            "hops_away": hops_away,
            "last_heard": last_heard,
            "last_heard_str": format_timestamp(last_heard)
        })

    # Sort by most recent last_heard
    node_list.sort(key=lambda x: x["last_heard"] or 0, reverse=True)
    return node_list


def display_nodes(nodes: List[Dict[str, Any]], mode: str) -> None:
    """
    Display a formatted list of nodes.
    
    Args:
        nodes: List of node dictionaries
        mode: Filter mode used ('all', 'direct', or 'routers')
    """
    mode_label = {
        "direct": "Directly Connected Nodes",
        "routers": "Router and Repeater Nodes",
        "all": "All Nodes"
    }.get(mode, "All Nodes")

    print(f"\n{mode_label} (Filtered & Sorted):")
    
    if not nodes:
        print("No nodes found matching the criteria.")
        return
        
    # Calculate column widths for better formatting
    name_width = max(len(node['name']) for node in nodes) + 2
    id_width = max(len(node['id']) for node in nodes) + 2
    role_width = max(len(node['role']) for node in nodes) + 2
    
    # Print header
    print(f"{'Name':<{name_width}} {'ID':<{id_width}} {'Role':<{role_width}} {'SNR':<8} {'Hops':<5} {'Last Heard'}")
    print(f"{'-'*name_width} {'-'*id_width} {'-'*role_width} {'-'*8} {'-'*5} {'-'*19}")
    
    # Print nodes
    for node in nodes:
        hops = node.get('hops_away', 'N/A')
        # Handle the case where hops_away might be None
        if hops is None:
            hops = 'N/A'
        snr = node.get('snr', 'N/A')
        # Format SNR with more space
        snr_formatted = f"{snr:<8}" if snr != 'N/A' else f"{'N/A':<8}"
        
        print(f"{node['name']:<{name_width}} {node['id']:<{id_width}} {node['role']:<{role_width}} "
              f"{snr_formatted} {hops:<5} {node['last_heard_str']}")


def parse_arguments() -> argparse.Namespace:
    """
    Parse command line arguments.
    
    Returns:
        Namespace containing the parsed arguments
    """
    parser = argparse.ArgumentParser(
        description="Query and display Meshtastic mesh network nodes"
    )
    
    parser.add_argument(
        "port", 
        help="Serial port for Meshtastic device (e.g., /dev/ttyUSB0)"
    )
    
    parser.add_argument(
        "--mode", 
        choices=["all", "direct", "routers"], 
        default="all",
        help="Filter mode: all nodes, direct connections only, or routers/repeaters only"
    )
    
    parser.add_argument(
        "--age", 
        help="Only show nodes heard within this time (format: 1s, 5m, 2h, 1d)"
    )
    
    parser.add_argument(
        "--json-out", 
        metavar="FILENAME",
        help="Save node data to a JSON file"
    )
    
    return parser.parse_args()


def main():
    """Main function to run the script."""
    # Handle legacy command line format for backward compatibility
    if len(sys.argv) > 1 and not sys.argv[1].startswith("-"):
        # Transform old format arguments to new format
        new_args = [sys.argv[0], sys.argv[1]]
        
        if "--direct" in sys.argv:
            new_args.extend(["--mode", "direct"])
            sys.argv.remove("--direct")
        elif "--routers" in sys.argv:
            new_args.extend(["--mode", "routers"])
            sys.argv.remove("--routers")
            
        # Handle --age parameter
        if "--age" in sys.argv:
            age_index = sys.argv.index("--age")
            if age_index + 1 < len(sys.argv):
                new_args.extend(["--age", sys.argv[age_index + 1]])
                
        # Handle --json-out parameter
        if "--json-out" in sys.argv:
            json_index = sys.argv.index("--json-out")
            if json_index + 1 < len(sys.argv):
                new_args.extend(["--json-out", sys.argv[json_index + 1]])
                
        sys.argv = new_args

    args = parse_arguments()
    age_filter = None
    
    if args.age:
        age_filter = parse_age_string(args.age)
        if not age_filter:
            print(f"Invalid age format: {args.age}. Expected format like '1s', '5m', '2h', '1d'")
            sys.exit(1)

    try:
        mesh_nodes = get_nodes(args.port)
        node_list = filter_and_sort_nodes(mesh_nodes, args.mode, age_filter)
        display_nodes(node_list, args.mode)

        # Optional JSON export
        if args.json_out:
            try:
                with open(args.json_out, 'w') as f:
                    json.dump(node_list, f, indent=2)
                print(f"\nJSON report saved to {args.json_out}")
            except IOError as e:
                print(f"Error writing to JSON file: {e}")

    except Exception as e:
        print(f"Unexpected error occurred: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()