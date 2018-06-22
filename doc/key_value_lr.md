# Key-Value Store implemented on a Legion Logical Region

Key syntax is like a Linux file path, e.g. /worker1/state/current_frame_number.
All data is JSON strings.
Data is stored in a 1-D index space.
Regions of the key space are mapped to contiguous index points.

