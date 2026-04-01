import sys
import os
import threading
import time
import socket

graph_lock = threading.Lock()
graph = {}
routing_event = threading.Event()

def listening_stdin(node_id, master_stop, port_number, broadcast_event):
    while not master_stop.is_set():
        try:
            raw_input = input()
            if not raw_input.strip():
                continue
            
            line = raw_input.strip().split()

            if line[0] == "UPDATE":
                source_node = line[1]
                neighbours = line[2].split(",") if len(line) > 2 else []
                    
                with graph_lock:
                    if source_node not in graph:
                        graph[source_node] = {}
                    
                    current_time = time.time()  # Stamp new updates
                    for n in neighbours:
                        node, cost, port = n.split(":")
                        cost = float(cost)
                        port = int(port)
                        if node not in graph:
                            graph[node] = {}
                        graph[source_node][node] = (cost, port, current_time)
                        graph[node][source_node] = (cost, port, current_time)
                        
                routing_event.set()  

            elif line[0] == "CHANGE":
                neighbour_id = line[1]
                new_cost = float(line[2])
            
                with graph_lock:
                    port = 0
                    if neighbour_id in graph.get(node_id, {}):
                        _, port, _ = graph[node_id][neighbour_id]
                        
                    current_time = time.time()  # Stamp the change
                    
                    if node_id not in graph: 
                        graph[node_id] = {}
                    if neighbour_id not in graph: 
                        graph[neighbour_id] = {}
                    
                    graph[node_id][neighbour_id] = (new_cost, port, current_time)
                    graph[neighbour_id][node_id] = (new_cost, port, current_time) 
                
                routing_event.set()
                broadcast_event.set()  # Force immediate broadcast on change
                
            elif line[0] == "FAIL":
                if len(line) != 2:
                    print("Error: Invalid command format. Expected: FAIL <Node-ID>.", flush=True)
                    os._exit(1)
                    
                target_node = line[1]
                # Assuming valid Node-IDs are single characters based on the 'AB' error spec
                if len(target_node) != 1 or not target_node.isalnum():
                    print("Error: Invalid command format. Expected a valid Node-ID.", flush=True)
                    os._exit(1)
                    
                if target_node == node_id:
                    node_down_event.set()
                    print(f"Node {node_id} is now DOWN.", flush=True)
                else:
                    with graph_lock:
                        failed_nodes.add(target_node)
                    routing_event.set()

            # --- NEW: RECOVER COMMAND ---
            elif line[0] == "RECOVER":
                if len(line) != 2:
                    print("Error: Invalid command format. Expected: RECOVER <Node-ID>.", flush=True)
                    os._exit(1)
                    
                target_node = line[1]
                if len(target_node) != 1 or not target_node.isalnum():
                    print("Error: Invalid command format. Expected a valid Node-ID.", flush=True)
                    os._exit(1)
                    
                if target_node == node_id:
                    node_down_event.clear()
                    print(f"Node {node_id} is now UP.", flush=True)
                    broadcast_event.set()  # Force broadcast immediately upon waking up
                else:
                    with graph_lock:
                        if target_node in failed_nodes:
                            failed_nodes.remove(target_node)
                    routing_event.set()
        except EOFError:
            break
        except Exception:
            pass
    return

def listening_network(my_socket, stop_event, port_number, node_id):
    while not stop_event.is_set():
        try:
            data, addr = my_socket.recvfrom(4096)
            message = data.decode().strip()
            parts = message.split()
            
            if not parts or parts[0] != "UPDATE":
                continue
                
            source_node = parts[1]
            source_port = int(parts[2])
            neighbours = parts[3].split(",") if len(parts) > 3 else []
            
            changes_made = False
            
            with graph_lock:
                if source_node not in graph:
                    graph[source_node] = {}
                    
                for n in neighbours:
                    n_parts = n.split(":")
                    node = n_parts[0]
                    cost = float(n_parts[1])
                    port = int(n_parts[2])
                    
                    # Safely extract timestamp if present, else fallback to 0.0
                    timestamp = float(n_parts[3]) if len(n_parts) > 3 else 0.0
                    
                    # Get the current known timestamp for this edge (-1.0 if unknown)
                    current_ts = graph[source_node].get(node, (0, 0, -1.0))[2]
                    
                    # ONLY update if the incoming data is newer or equal
                    if timestamp >= current_ts:
                        if node not in graph:
                            graph[node] = {}
                        graph[source_node][node] = (cost, port, timestamp)
                        changes_made = True
                        
                        # If this edge involves me, update my outgoing link too
                        if node == node_id:
                            my_ts = graph[node].get(source_node, (0, 0, -1.0))[2]
                            if timestamp >= my_ts:
                                graph[node][source_node] = (cost, source_port, timestamp)
                                
            if changes_made:
                routing_event.set() 
                
        except Exception:
            if not stop_event.is_set():
                pass
            break

def broadcast_updates(update_interval, stop_event, node_id, my_socket, port_number, broadcast_event):
    last_stdout_message = ""
    
    while not stop_event.is_set():
        neighbour_parts_stdout = []
        neighbour_parts_socket = []
        ports_to_send = [] 
        
        with graph_lock:
            if node_id in graph:
                # Sorted to ensure consistent STDOUT for the autograder
                for n in sorted(graph[node_id].keys()):
                    cost, port, timestamp = graph[node_id][n]
                    neighbour_parts_stdout.append(f"{n}:{cost}:{port}")
                    
                    # Socket message gets the timestamp, STDOUT strictly does not
                    neighbour_parts_socket.append(f"{n}:{cost}:{port}:{timestamp}")
                    ports_to_send.append(port) 
        
        if neighbour_parts_stdout:
            stdout_message = f"UPDATE {node_id} " + ",".join(neighbour_parts_stdout)
            socket_message = f"UPDATE {node_id} {port_number} " + ",".join(neighbour_parts_socket)
            
            for port in ports_to_send: 
                if port != 0:
                    try:
                        my_socket.sendto(socket_message.encode(), ("localhost", port))
                    except Exception:
                        pass
            
            # Only print if the topology actually changed, and flush it
            if stdout_message != last_stdout_message:
                print(stdout_message, flush=True)
                last_stdout_message = stdout_message
        
        # Wait for the interval OR the manual broadcast_event trigger
        broadcast_event.wait(timeout=update_interval)
        broadcast_event.clear()

def dijkstras(starting_node):
    prev = {}
    dist = {}
    visited = set()
    
    # Initialise
    for node in graph:
        dist[node] = float('inf')
        prev[node] = None
    
    dist[starting_node] = 0

    # Main loop
    while len(visited) < len(graph):
        current_node = None
        smallest_distance = float('inf')

        for node in graph:
            if node not in visited and dist[node] < smallest_distance:
                smallest_distance = dist[node]
                current_node = node

        if current_node is None:
            break

        visited.add(current_node)

        # Relax neighbours
        for neighbour in graph[current_node]:
            cost, port, timestamp = graph[current_node][neighbour]  # Unpack 3 values
            
            new_dist = dist[current_node] + cost
            
            if new_dist < dist[neighbour]:
                dist[neighbour] = new_dist
                prev[neighbour] = current_node
              
    return dist, prev
    
def get_path(prev, destination_node):
    if prev[destination_node] is None:
        return "UNREACHABLE"
    
    least_cost_path = []
    current_node = destination_node
        
    while prev[current_node] is not None:
        least_cost_path.append(prev[current_node])
        current_node = prev[current_node]
    
    least_cost_path.reverse()
    least_cost_path.append(destination_node)
    
    return ''.join(least_cost_path)
        
def read_config(node_config_file):
    neighbouring_nodes = []
    
    with open(node_config_file, "r") as file:
        neighbour_entries = int(next(file).strip())
        
        for line in file:
            line = line.strip()
            if line == "":
                continue
            
            # Use split() instead of split(" ") to safely handle extra spaces
            neighbouring_nodes.append(line.split())
            
    return neighbouring_nodes

def handle_routing(routing_delay, stop_event, starting_node, node_id):
    # Wait once at startup
    stop_event.wait(routing_delay)
    
    while not stop_event.is_set():
        try:
            with graph_lock:
                dist, prev = dijkstras(starting_node)
                nodes_snapshot = sorted(graph)
            
            # Format cleanly as a list to avoid trailing empty lines
            output_lines = [f"I am Node {node_id}"]
            
            for node in nodes_snapshot:
                if node != node_id:
                    path = get_path(prev, node)
                    cost = dist[node]
                    output_lines.append(f"Least cost path from {node_id} to {node}: {path}, link cost: {cost}")
            
            # flush=True forces the buffer to output immediately
            print("\n".join(output_lines), flush=True)
            
        except Exception:
            pass 
        
        # Wait until triggered by an update
        routing_event.wait()
        routing_event.clear()

def update_graph(neighbouring_nodes, source_node):
    if source_node not in graph:
        graph[source_node] = {}
    
    for node_id, cost, port_no in neighbouring_nodes:
        cost = float(cost)
        port_no = int(port_no)
        if node_id not in graph:
            graph[node_id] = {}
        
        # Add 0.0 as the initial timestamp
        graph[source_node][node_id] = (cost, port_no, 0.0)
        graph[node_id][source_node] = (cost, port_no, 0.0)

def main():
    if len(sys.argv) != 6:
        print("Error: Insufficient arguments provided. Usage: ./Routing.sh <Node-ID> <Port-NO> <Node-Config-File> <RoutingDelay> <UpdateInterval>")
        sys.exit(1)
        
    node_id = sys.argv[1]
    port_number = int(sys.argv[2])
    node_config_file = sys.argv[3]
    routing_delay = float(sys.argv[4])
    update_interval = float(sys.argv[5])
    
    neighbouring_nodes = read_config(node_config_file)
    update_graph(neighbouring_nodes, node_id)
    
    # Socket setup
    my_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    my_socket.bind(('localhost', port_number))    
    
    # Threading setup
    master_stop = threading.Event()
    broadcast_event = threading.Event() 
    node_down_event = threading.Event()  # ← NEW: Tracks if THIS node is down
    failed_nodes = set()                 # ← NEW: Tracks if OTHER nodes are down
    
    listening_thread_stdin = threading.Thread(target=listening_stdin, args=(node_id, master_stop, port_number, broadcast_event, node_down_event, failed_nodes), daemon=True)
    listening_thread_network = threading.Thread(target=listening_network, args=(my_socket, master_stop, port_number, node_id, node_down_event), daemon=True)
    sending_thread = threading.Thread(target=broadcast_updates, args=(update_interval, master_stop, node_id, my_socket, port_number, broadcast_event, node_down_event), daemon=True)
    routing_thread = threading.Thread(target=handle_routing, args=(routing_delay, master_stop, node_id, node_id, failed_nodes, node_down_event), daemon=True)
    listening_thread_stdin.start()
    listening_thread_network.start()
    sending_thread.start()
    routing_thread.start()
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        master_stop.set()

if __name__ == "__main__":
    main()