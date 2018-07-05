# Data Source

class DataSource:

Every data source inherits from the DataSource base class.
This class provides services to push event data into the local store where they can be accessed by Workers.

Note that the Data Acquisition System can replay data streams from a file to enable test and debugging.
It can optionally log data to files that can be replayed later.

## SharedMemoryDataSource
class SharedMemoryDataSource: pulls XTC data from a region of shared memory and pushes it to the local store.
The XTC data was delivered by the Data Acquisition system.


## extending a new data source
Data sources are extensible by inheriting from class DataSource.
