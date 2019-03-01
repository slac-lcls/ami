# ami
The LCLS-II online graphical analysis monitoring package.

## Documentation
[User documentation](doc/userdoc.md)
[Design documentation](doc/toplevel.md)
[Test information](doc/testing.md)

# Examples
If you use the setup.py included to set this up you should now have two console
scripts available on your path: `ami-worker` and `ami-manager`. Several example
configuration files are included in the examples directory.

To run ami with three workers run the following in lcls2/ami (for either psanasource or random source):
```ami-worker -n 3 random://examples/worker.json```
```ami-worker -n 3 psana://examples/psana.json```

Then start the manager:
```ami-manager```

Then, start a GUI (client):
```ami-client```

You should see an interactive QT window. There is also a convenience launcher
that when you want to run all parts of ami on a single node:
```ami-local -n 3 random://examples/worker.json```

To load a graph, add this flag to ami-local:
```-l examples/basic.ami```

To use psana a working release need to be added to the python path

# Status/To-do

1 MAR 19:
- Graph types/validation
- Status messages from worker
- Dynamic menus
- documentation
- cleanup repo
- Additional graph operations or flowchart boxes:
    * Peak/hit finder operations
    * Operation that collects the data for a scatter plot of two variables.
    * Histogramming operation. This is like binning but instead of a key there is just a predefined set of bins and we count
      the number of times the input we are reducing falls into each bin. This should have the option to normalize the total to one.
    * Version of the ROI operation that works on 1-D arrays.
    * A box in the flowchart that allows us to overlay two or more plots.
    * Boxes in the flowchart for doing arthimetic operations. Do we want a box where they can enter an expression like (2*input - 5)/ 10
      instead of having to do that in three boxes (multiple by 2, then subtract 5, and then divide by ten).

19 Feb 19:
- Graph types/validation
- Status messages from worker
- Fix gui crashes as they occur
- Dynamic menus
- saving node state (pull from separate processes)
- documentation
- cleanup repo

20 DEC 18:
Bigger Projects:
- switch to shmem
- pydm (waiting for hugo)
- different displays running in different processes
- pvaccess (dan is working on this)
- Clemens' complex example via GUI
- partition call dropdown for xppcspad.raw..., xppcpad.fex...
- display "reference counting" for automated graph-remove
- external-data (including collector) to worker feedback. probably EPICS.  (e.g. for background subtraction)
- complex data types (e.g. peaks/times from hsd fex)
- check gessner issue OK
- included detectors changing from run to run
- call complex psana algorithm with parameters, e.g. peakfinder
- record operator actions with "amicli" commands that could be played back
- parallelize global collector

6 DEC 18
CPO/TJL:

Think about:
1. "." interface versus dictionaries
2. missing data (none? hasattr? in keys()?)
3. det xface attributes not appearing until event

29 NOV 18
CPO/TJL : we have been thinking about how to intialize the graph with data from psana (shmem or xtc).

This is the special procedure for data coming from the data source (elemental data), which is discovered through the partition.

1. "list GUI" calls a partition method that provides the available detector information (e.g `xppcspad.raw.raw`, `xpphsd.fex.peaks`)
2. user clicks on desired detector source (`xppcspad.raw.raw`)
3. "list GUI" adds pick1 node to graph with corresponding source (source is by convention . to _ string, e.g. "xppcspad_raw_raw")
4. Workers know which elemental data they need to get from the psana data source by querying the graph (ask Seshu)
5. Workers get("xppcspad_raw_raw") elemental data from psana data source event and pass to graph {"xppcspad_raw_raw" : xppcspad.raw.raw}
6. "list GUI" opens a detector GUI (e.g. for a 2D CSPAD image) and connects it to the output of pick1 graph node

In summary, Worker will (a) figure out what he needs from the Graph, and (b) get() those things from the DataSource.

Note: the . to _ substitution and use of strings is an attempt to remove psana specific ideas from AMI2

