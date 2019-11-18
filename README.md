# ami
The LCLS-II online graphical analysis monitoring package.

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
