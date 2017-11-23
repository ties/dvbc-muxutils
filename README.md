capture_downstreams.py:
-----------------------

A script that reads a channel file (see `downstreams.conf`) and records from
each channel in this file using `dvbv5-zap`. Optionally, the resulting mpeg
ts file is filtered using tshark, resulting in a pcap file with only specific
packet types.

Script is written for Python 3.6
