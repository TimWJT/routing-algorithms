import sys
import os
import threading
import time
import socket

graph = {}

def listening_stdin(node_id, master_stop):
    while not master_stop.is_set():
        try:
            line = input().strip().split()
            print("Received: ", line)
            
            if len(line) < 3:
                print("too little inputs")
                break
            if line[0] == "UPDATE":
            
                source_node = line[1]
                neighbours_raw = line[2]
                neighbours = neighbours_raw.split(",")
            
                graph[source_node] = {}
                    
                for n in neighbours:
                    node, cost, port = n.split(":")
                    cost = float(cost)
                    port = int(port)
                    
                    if node not in graph:
                        graph[node] = {}
                    
                    graph[source_node][node] = (cost, port)
                    graph[node][source_node] = (cost, port)

            if line[0] == "CHANGE":
                pass
                
                
        except EOFError:
            print("Error in input")
            break
    return


def listening_network(my_socket, stop_event):
    while not stop_event.is_set():
        try:
            # 1. Wait for a packet (up to 4096 bytes)
            data, addr = my_socket.recvfrom(4096)
            
            # 2. Convert bytes back to a string
            message = data.decode().strip()
            
            # 3. Parse the message (just like you did in stdin)
            # Example: "UPDATE B C:5.0:6002"
            parts = message.split()
            if parts[0] == "UPDATE":
                # Extract source_node and neighbors exactly like your other thread
                # Then update the 'graph' dictionary
                
                
                source_node = parts[1]
                neighbours_raw = parts[2]
                neighbours = neighbours_raw.split(",")
            
                graph[source_node] = {}
                    
                for n in neighbours:
                    node, cost, port = n.parts(":")
                    cost = float(cost)
                    port = int(port)
                    
                    if node not in graph:
                        graph[node] = {}
                    
                    graph[source_node][node] = (cost, port)
                    graph[node][source_node] = (cost, port)
                    
        except Exception as e:
            if not stop_event.is_set():
                print(f"Network error: {e}")
            break

def broadcast_updates(update_interval, stop_event, node_id):
    while not stop_event.is_set():
        
        update_message = f"UPDATE {node_id}"
        
        
        for n in graph[node_id]:
            cost, port = graph[node_id][n]
            update_message += f"{n}:{cost}:{port}"        
        
        
        print(update_message) 
        
        stop_event.wait(update_interval)
        stopped = broadcast_updates.wait(update_interval)
        
        
        if stopped:
            break
    
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
        # Find closest unvisited node
        current_node = None
        smallest_distance = float('inf')

        for node in graph:
            if node not in visited and dist[node] < smallest_distance:
                smallest_distance = dist[node]
                current_node = node

        visited.add(current_node)

        # Relax neighbours
        for neighbour in graph[current_node]:
            cost, port = graph[current_node][neighbour]
            
            new_dist = dist[current_node] + cost
            
            if new_dist < dist[neighbour]:
                dist[neighbour] = new_dist
                prev[neighbour] = current_node
              
    return dist, prev
    
    
def get_path(prev, destination_node):
    
    
    least_cost_path = []
    
    current_node = destination_node
        
    while prev[current_node] != None:
        least_cost_path.append(prev[current_node])
        current_node = prev[current_node]
        
    least_cost_path.reverse()
    return ''.join(least_cost_path)
    
def read_config(node_config_file):
    
    neighbouring_nodes = []
    
    with open(node_config_file, "r") as file:
        
        
        neighbour_entries = int(next(file).strip())
        
        for line in file:
            line = line.strip()
            
            if line == "":
                continue
            
            node_id, cost, port_no = line.split(" ")
            neighbouring_nodes.append(line.split(" "))
            
    return neighbouring_nodes

def handle_routing(routing_delay, stop_event, starting_node, destination_node):
    while not stop_event.is_set():
    
        dist, prev = dijkstras(starting_node)
        path = get_path(prev, destination_node)
        
        stop_event.wait(routing_delay)
        
        stopped = handle_routing.wait(routing_delay)
        
        if stopped:
            break

def update_graph(neighbouring_nodes, source_node):
    
    if source_node not in graph:
        graph[source_node] = {}
    
    for node_id, cost, port_no in neighbouring_nodes:
        cost = float(cost)
        port_no = int(port_no)
        if node_id not in graph:
            graph[node_id] = {}
        
        graph[source_node][node_id] = (cost, port_no)
        graph[node_id][source_node] = (cost, port_no)
        
    return


def main():
    """
    Node-ID is a unique identifier (e.g. A, B, C, ...).
2. Port-NO is the port on which the node listens (ports start at 6000 and increment
by one).
3. Node-Config-File is a file specifying the node’s immediate neighbours. The first
line contains an integer n (the number of neighbours), followed by n lines. Each
line contains three tokens: a neighbour’s Node-ID, the cost (a non-negative floating-
point number), and the neighbour’s listening port.
4. RoutingDelay is the delay (in seconds) before the Routing Calculations Thread
computes and outputs the routing table at startup.
5. UpdateInterval is the interval (in seconds) at which the Sending Thread broad-
casts the current update packet via STDOUT.
    """
    input_arguments = sys.argv
    if len(sys.argv) != 6:
        print(f"Error: Insufficient arguments provided. Usage: ./Routing.sh <Node-ID> <Port-NO> <Node-Config-File> <RoutingDelay> <UpdateInterval>")
        sys.exit(1)
        
    node_id = sys.argv[1]
    port_number = sys.argv[2]
    node_config_file = sys.argv[3]
    routing_delay = sys.argv[4]
    update_interval = sys.argv[5]
    
    neighbouring_nodes = read_config(node_config_file)
    
    update_graph(neighbouring_nodes, node_id)
    
    
    # socket stuff
    my_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    my_socket.bind(('localhost', port_number))
    
    
    
    # threadding stuff
    master_stop = threading.Event()
    
    # The Listening Thread: Monitors the "outside world" (STDIN for user commands and Sockets for other nodes).

    listening_thread_stdin = threading.Thread(target = listening_stdin, args = (master_stop,), daemon = True)
    listening_thread_network = threading.Thread(target = listening_network, args = (my_socket, master_stop,), daemon = True)
    # The Sending Thread: Wakes up every UpdateInterval seconds to shout your status to your neighbors.


    sending_thread = threading.Thread(target = broadcast_updates, args = (update_interval, master_stop, node_id), daemon = True)
    # The Routing Thread: Periodically (or on-demand) runs your Dijkstra logic and prints the table.
    destination_node = ""
    #r
    
    routing_thread = threading.Thread(target = handle_routing, args = (routing_delay, master_stop, node_id, destination_node), daemon = True)
    
    listening_thread_stdin.start()
    listening_thread_network.start()
    sending_thread.start()
    routing_thread.start()
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        master_stop.set()
    
    listening_thread_network.join(daemon= True)
    listening_thread_stdin.join(daemon= True)
    sending_thread.join(daemon= True)
    routing_thread.join(daemon= True)
    
if __name__ == "__main__":
    main()