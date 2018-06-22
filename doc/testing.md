# Testing

Test suites will pass whether they are run on a single computer or on a cluster.

## Subsystem tests

### Data flow throughput and scaling

Implement file and live data sources, basic worker and reducers, storage, and a file test client with a protocol handler.
Test data flow using canned data from a file data source.
Test throughput and scaling using a live data source.


### Multiple client graph modification

Implement GraphManager and a multi-client test client.
This client incorporates scripting and logging capability.

### Fail over

Implement RobustnessMonitor.
Inject failures at each component.
Inject failures in the underlying storage system (Redis or Legion).
Verify the system resumes as expected.

### Clients

Implement diverse PyQt clients with scripting/logging ability.
Test each client ability to execute from a script with canned data.




## System tests

End-to-end testing using canned or live data.

### Generic user

The first test is a generic use case of the most common features, driven from
a canned example.
This should run on a cluster or on a single machine.

Starting from scratch, install the software and start it running.
Use an offline data source to drive a standard interaction.
Open a GUI client that acquires 2D sensor image data.
Select a region from the sensor image.
Plot the mean pixel value of this region across time in a strip chart recorder.
Verify the data visualization is corrent.
Shut the system down cleanly.


