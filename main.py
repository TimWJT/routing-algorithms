import sys
import os
import threading
import time
import socket
import heapq

graph = {}

def listening(arguments):
    while True:
        try:
            line = input().strip().split()
            print("Received: ", line)
            
            if len(line) < 3:
                print("too little inputs")
                break
            if line[0] != "UPDATE":
                break
            
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
    
            
        except EOFError:
            print("Error in input")
            break
    return

def sendThread(node_id):
    
    
    update_message = f"UPDATE {node_id}"
    
    
    for n in graph[node_id]:
        cost, port = graph[node_id][n]
        update_message += graph[node_id][n] + ":" + cost + ":" + port
    
    
    
    print(update_message) 
    
def dijkstras(starting_node):
    prev = {}
    dist = {}
    visited = set()
    
    for node in graph:
        dist[node] = float('inf')
        prev[node] = None
    
    dist[starting_node] = 0
    
    
    for n in graph[current_node]:
        cost, port = graph[current_node][n]
        
        new_dist = dist[current_node] + cost
        
        if new_dist < dist[n]:
            dist[n] = new_dist
            prev[n] = current_node
              
            
    return path
       

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
    
    listening(input_arguments)
    
    
if __name__ == "__main__":
    main()