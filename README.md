environment:
coded in python 3.

packages:
didn't use any external packages or libraries. just the standard built-in python ones:
sys, os, threading, time, socket

how to run:
first make the script executable:
chmod +x Routing.sh

then run it using the format from the spec:
./Routing.sh <Node-ID> <Port-NO> <Node-Config-File> <RoutingDelay> <UpdateInterval>

example:
./Routing.sh A 6000 Aconfig.txt 10 5

to use the commands like CHANGE, FAIL, MERGE, SPLIT, etc, just type them straight into the terminal while the script is running.