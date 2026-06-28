import sys
import os
import threading
import time
import socket

graph_lock = threading.Lock()
graph = {}
routing_event = threading.Event()

def listening_stdin(node_id, master_stop, port_number, broadcast_event, node_down_event, failed_nodes, original_neighbouring_nodes, force_print_event, blacklisted_edges):
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
                    # Ignore STDIN updates from ghost nodes
                    if source_node in failed_nodes:
                        continue
                        
                    if source_node not in graph:
                        graph[source_node] = {}
                    
                    current_time = time.time()
                    for n in neighbours:
                        if not n: continue
                        n_parts = n.split(":")
                        node = n_parts[0]
                        cost = float(n_parts[1])
                        port = int(n_parts[2])
                        
                        # Ignore links to ghosts
                        if node in failed_nodes:
                            continue
                            
                        # Ignore severed SPLIT edges
                        edge_tuple = tuple(sorted((source_node, node)))
                        if edge_tuple in blacklisted_edges:
                            continue
                            
                        if node not in graph:
                            graph[node] = {}
                        
                        graph[source_node][node] = (cost, port, current_time)
                        graph[node][source_node] = (cost, port, current_time)
                        
                routing_event.set()  

            elif line[0] == "CHANGE":
                if len(line) != 3:
                    print("Error: Invalid command format. Expected exactly two tokens after CHANGE.", flush=True)
                    os._exit(1)
                    
                neighbour_id = line[1]
                try:
                    new_cost = float(line[2])
                except ValueError:
                    print("Error: Invalid command format. Expected numeric cost value.", flush=True)
                    os._exit(1)
            
                with graph_lock:
                    port = 0
                    if neighbour_id in graph.get(node_id, {}):
                        _, port, _ = graph[node_id][neighbour_id]
                        
                    current_time = time.time()
                    
                    if node_id not in graph: 
                        graph[node_id] = {}
                    if neighbour_id not in graph: 
                        graph[neighbour_id] = {}
                    
                    graph[node_id][neighbour_id] = (new_cost, port, current_time)
                    graph[neighbour_id][node_id] = (new_cost, port, current_time) 
                
                force_print_event.set()
                routing_event.set()
                broadcast_event.set()

            elif line[0] == "FAIL":
                if len(line) != 2:
                    print("Error: Invalid command format. Expected: FAIL <Node-ID>.", flush=True)
                    os._exit(1)
                    
                target_node = line[1]
                if len(target_node) != 1 or not target_node.isalnum():
                    print("Error: Invalid command format. Expected a valid Node-ID.", flush=True)
                    os._exit(1)
                    
                if target_node == node_id:
                    node_down_event.set()
                    print(f"Node {node_id} is now DOWN.", flush=True)
                else:
                    with graph_lock:
                        failed_nodes.add(target_node)
                    force_print_event.set()
                    routing_event.set()

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
                    broadcast_event.set() 
                else:
                    with graph_lock:
                        if target_node in failed_nodes:
                            failed_nodes.remove(target_node)
                    force_print_event.set()
                    routing_event.set()

            elif line[0] == "RESET":
                if len(line) != 1:
                    print("Error: Invalid command format. Expected exactly: RESET.", flush=True)
                    os._exit(1)
                    
                with graph_lock:
                    graph.clear()
                    failed_nodes.clear()
                    blacklisted_edges.clear()
                    node_down_event.clear()
                    
                    graph[node_id] = {}
                    current_time = time.time() 
                    
                    for nid, cost, port_no in original_neighbouring_nodes:
                        cost = float(cost)
                        port_no = int(port_no)
                        if nid not in graph:
                            graph[nid] = {}
                        graph[node_id][nid] = (cost, port_no, current_time)
                        graph[nid][node_id] = (cost, port_no, current_time)
                        
                print(f"Node {node_id} has been reset.", flush=True)
                force_print_event.set()
                routing_event.set()
                broadcast_event.set()

            elif line[0] == "MERGE":
                if len(line) != 3:
                    print("Error: Invalid command format. Expected two valid identifiers for MERGE.", flush=True)
                    os._exit(1)
                node1 = line[1]
                node2 = line[2]
                
                # If I am the node being absorbed, I shut down.
                if node_id == node2:
                    node_down_event.set()
                    print("Graph merged successfully.", flush=True)
                    continue
                
                with graph_lock:
                    failed_nodes.add(node2)
                    
                    # Collect node2's neighbors (excluding node1)
                    node2_neighbors = {}
                    if node2 in graph:
                        for neighbor, data in list(graph[node2].items()):
                            if neighbor != node1 and neighbor != node2:
                                node2_neighbors[neighbor] = data
                    
                    # Ensure node1 exists in graph
                    if node1 not in graph:
                        graph[node1] = {}
                    
                    # Transfer node2's edges to node1 (keep lower cost)
                    for neighbor, data in node2_neighbors.items():
                        cost, port, ts = data
                        if neighbor in graph[node1]:
                            existing_cost = graph[node1][neighbor][0]
                            if cost < existing_cost:
                                graph[node1][neighbor] = (cost, port, time.time())
                                if neighbor in graph:
                                    graph[neighbor][node1] = (cost, graph[neighbor].get(node1, (0, 0, 0))[1], time.time())
                        else:
                            graph[node1][neighbor] = (cost, port, time.time())
                            if neighbor in graph:
                                # The neighbor's link to node1 uses node1's port
                                # We need to figure out the port for reaching node1
                                # Use the port that was used for node1 if neighbor already knows node1
                                # Otherwise use the port from the node2 link
                                n1_port = port  # default
                                if node1 in graph[neighbor]:
                                    n1_port = graph[neighbor][node1][1]
                                graph[neighbor][node1] = (cost, n1_port, time.time())
                    
                    # Remove all references to node2 from every node's adjacency
                    for n in list(graph.keys()):
                        if node2 in graph[n]:
                            del graph[n][node2]
                    
                    # Remove node2's own entry
                    if node2 in graph:
                        del graph[node2]
                    
                    # Also remove node1's self-loop if any
                    if node1 in graph.get(node1, {}):
                        del graph[node1][node1]
                        
                print("Graph merged successfully.", flush=True)
                force_print_event.set()
                routing_event.set()
                broadcast_event.set()

            elif line[0] == "SPLIT":
                if len(line) != 1:
                    print("Error: Invalid command format. Expected exactly: SPLIT.", flush=True)
                    os._exit(1)
                    
                with graph_lock:
                    V = [v for v in sorted(list(graph.keys())) if v not in failed_nodes]
                    k = len(V) // 2
                    V1 = set(V[:k])
                    V2 = set(V[k:])
                    
                    for u in list(graph.keys()):
                        for v in list(graph[u].keys()):
                            if (u in V1 and v in V2) or (u in V2 and v in V1):
                                blacklisted_edges.add(tuple(sorted((u, v)))) 
                                del graph[u][v]
                                
                print("Graph partitioned successfully.", flush=True)
                force_print_event.set()
                routing_event.set()
                broadcast_event.set()
                
        except EOFError:
            break
        except Exception:
            pass
    return

def listening_network(my_socket, stop_event, port_number, node_id, node_down_event, failed_nodes, blacklisted_edges):
    while not stop_event.is_set():
        try:
            if node_down_event.is_set():
                my_socket.recvfrom(4096)
                continue
                
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
                if source_node in failed_nodes:
                    continue
                    
                if source_node not in graph:
                    graph[source_node] = {}
                    
                for n in neighbours:
                    n_parts = n.split(":")
                    node = n_parts[0]
                    cost = float(n_parts[1])
                    port = int(n_parts[2])
                    
                    if node in failed_nodes:
                        continue
                        
                    edge_tuple = tuple(sorted((source_node, node)))
                    if edge_tuple in blacklisted_edges:
                        continue
                        
                    timestamp = float(n_parts[3]) if len(n_parts) > 3 else 0.0
                    current_data = graph[source_node].get(node)
                    
                    if current_data is None or timestamp > current_data[2] or (timestamp == current_data[2] and cost != current_data[0]):
                        if node not in graph:
                            graph[node] = {}
                        graph[source_node][node] = (cost, port, timestamp)
                        changes_made = True
                        
                        if node == node_id:
                            my_data = graph[node].get(source_node)
                            if my_data is None or timestamp > my_data[2] or (timestamp == my_data[2] and cost != my_data[0]):
                                graph[node][source_node] = (cost, source_port, timestamp)
                                
            if changes_made:
                routing_event.set() 
                
        except Exception:
            if not stop_event.is_set():
                pass
            break

def broadcast_updates(update_interval, stop_event, node_id, my_socket, port_number, broadcast_event, node_down_event):
    last_stdout_message = ""
    
    while not stop_event.is_set():
        broadcast_event.wait(timeout=update_interval)
        broadcast_event.clear()
        
        if node_down_event.is_set():
            continue

        neighbour_parts_stdout = []
        neighbour_parts_socket = []
        ports_to_send = [] 
        
        with graph_lock:
            if node_id in graph:
                for n in sorted(graph[node_id].keys()):
                    cost, port, timestamp = graph[node_id][n]
                    neighbour_parts_stdout.append(f"{n}:{cost}:{port}")
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
            
            if stdout_message != last_stdout_message:
                print(stdout_message, flush=True)
                last_stdout_message = stdout_message

def dijkstras(starting_node, failed_nodes):
    prev = {}
    dist = {}
    visited = set()
    
    for node in graph:
        dist[node] = float('inf')
        prev[node] = None
    
    dist[starting_node] = 0

    while len(visited) < len(graph):
        current_node = None
        smallest_distance = float('inf')

        for node in graph:
            if node not in visited and node not in failed_nodes and dist[node] < smallest_distance:
                smallest_distance = dist[node]
                current_node = node

        if current_node is None:
            break

        visited.add(current_node)

        for neighbour in graph[current_node]:
            if neighbour in failed_nodes:
                continue
                
            cost, port, timestamp = graph[current_node][neighbour]
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
    
    if not os.path.exists(node_config_file):
        print(f"Error: Configuration file {node_config_file} not found.", flush=True)
        sys.exit(1)

    with open(node_config_file, "r") as file:
        try:
            first_line = next(file).strip()
            neighbour_entries = int(first_line)
        except ValueError:
            print("Error: Invalid configuration file format. (First line must be an integer.)", flush=True)
            sys.exit(1)
            
        for line in file:
            line = line.strip()
            if line == "":
                continue
            
            parts = line.split()
            if len(parts) != 3:
                print("Error: Invalid configuration file format. (Each neighbour entry must have exactly three tokens; cost must be numeric.)", flush=True)
                sys.exit(1)
                
            try:
                float(parts[1]) 
            except ValueError:
                print("Error: Invalid configuration file format. (Each neighbour entry must have exactly three tokens; cost must be numeric.)", flush=True)
                sys.exit(1)

            neighbouring_nodes.append(parts)
            
    return neighbouring_nodes

def handle_routing(routing_delay, stop_event, starting_node, node_id, failed_nodes, node_down_event, force_print_event):
    stop_event.wait(routing_delay)
    last_routing_output = ""
    
    while not stop_event.is_set():
        try:
            if not node_down_event.is_set():
                with graph_lock:
                    dist, prev = dijkstras(starting_node, failed_nodes)
                    nodes_snapshot = sorted(graph)
                
                output_lines = [f"I am Node {node_id}"]
                
                for node in nodes_snapshot:
                    if node != node_id and node not in failed_nodes:
                        path = get_path(prev, node)
                        cost = dist[node]
                        output_lines.append(f"Least cost path from {node_id} to {node}: {path}, link cost: {cost}")
                
                output_str = "\n".join(output_lines)
                
                if output_str != last_routing_output or force_print_event.is_set():
                    print(output_str, flush=True)
                    last_routing_output = output_str
                    force_print_event.clear()
            
        except Exception:
            pass 
        
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
        
        graph[source_node][node_id] = (cost, port_no, 0.0)
        graph[node_id][source_node] = (cost, port_no, 0.0)

def main():
    if len(sys.argv) != 6:
        print("Error: Insufficient arguments provided. Usage: ./Routing.sh <Node-ID> <Port-NO> <Node-Config-File> <RoutingDelay> <UpdateInterval>", flush=True)
        sys.exit(1)
        
    node_id = sys.argv[1]
    if len(node_id) != 1 or not node_id.isalnum():
        print("Error: Invalid Node-ID.", flush=True)
        sys.exit(1)

    try:
        port_number = int(sys.argv[2])
    except ValueError:
        print("Error: Invalid Port number. Must be an integer.", flush=True)
        sys.exit(1)

    node_config_file = sys.argv[3]
    routing_delay = float(sys.argv[4])
    update_interval = float(sys.argv[5])
    
    neighbouring_nodes = read_config(node_config_file)
    update_graph(neighbouring_nodes, node_id)
    
    my_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    my_socket.bind(('localhost', port_number))    
    
    master_stop = threading.Event()
    broadcast_event = threading.Event()
    node_down_event = threading.Event()
    failed_nodes = set()
    force_print_event = threading.Event()
    blacklisted_edges = set()
    
    listening_thread_stdin = threading.Thread(target=listening_stdin, args=(node_id, master_stop, port_number, broadcast_event, node_down_event, failed_nodes, neighbouring_nodes, force_print_event, blacklisted_edges), daemon=True)
    listening_thread_network = threading.Thread(target=listening_network, args=(my_socket, master_stop, port_number, node_id, node_down_event, failed_nodes, blacklisted_edges), daemon=True)
    sending_thread = threading.Thread(target=broadcast_updates, args=(update_interval, master_stop, node_id, my_socket, port_number, broadcast_event, node_down_event), daemon=True)
    routing_thread = threading.Thread(target=handle_routing, args=(routing_delay, master_stop, node_id, node_id, failed_nodes, node_down_event, force_print_event), daemon=True)    
    
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
    

#references
# i have used Claude Opus 4.6 for this assignemtn made by Anthropic 2026. Examples of promps used is "I have this bug where the <insert expected output> isnt showing up properly. help me determine the bug and suggest the changes" and for writing comments in my code