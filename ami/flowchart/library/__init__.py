# -*- coding: utf-8 -*-
from ami.flowchart.NodeLibrary import NodeLibrary, isNodeClass
from ami.flowchart.library import Roi, Conditional, Operators, Display, Accumulators, Alert, Numpy

modules = [Roi, Conditional, Operators, Display, Accumulators, Alert, Numpy]

try:
    from ami.flowchart.library import Scipy
    modules.append(Scipy)
except ImportError as e:
    print(e)

try:
    from ami.flowchart.library import Psalg
    modules.append(Psalg)
except ImportError as e:
    print(e)

try:
    from ami.flowchart.library import FFTW
    modules.append(FFTW)
except ImportError as e:
    print(e)

# Build default library
LIBRARY = NodeLibrary()

# Add all nodes to the default library
for mod in modules:
    nodes = [getattr(mod, name) for name in dir(mod) if isNodeClass(getattr(mod, name))]

    for node in nodes:
        LIBRARY.addNodeType(node, [(mod.__name__.split('.')[-1],)])
