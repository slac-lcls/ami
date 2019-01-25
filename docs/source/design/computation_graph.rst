Computation Graph
=================

The computation graph is a collection of nodes and edges which describe what computations to apply to data and
the dependencies between those computations. It is implemented as a wrapper around NetworkFoX.

Graph
-----

.. autoclass:: ami.graphkit_wrapper.Graph
   :members:
   :special-members: __call__, __init__
   :member-order: bysource

Graph Node Base Classes
-----------------------

All graph nodes should inherit from one of three base classes, either :ref:`Transformation`, :ref:`Filter`, or :ref:`StatefulTransformation`.

Transformation
^^^^^^^^^^^^^^

Transformation is a base class. It may occasionally be useful to override the `to_operation()` method in subclasses of :ref:`Transformation`.

.. autoclass:: ami.graph_nodes.Transformation
   :members:
   :special-members: __init__, __eq__
   :member-order: bysource

StatefulTransformation
^^^^^^^^^^^^^^^^^^^^^^

:ref:`StatefulTransformation` is a subclass of :ref:`Transformation`. It specifies an interface for nodes which maintain state.

Subclasses of this class must implement `__call__` and `reset` methods.

.. autoclass:: ami.graph_nodes.StatefulTransformation
   :members:
   :special-members: __init__, __call__
   :member-order: bysource

Filter
^^^^^^

Filter is the base class from which :ref:`FilterOn` and :ref:`FilterOff` inherit.

.. autoclass:: ami.graph_nodes.Filter
   :members:
   :special-members: __init__

Graph Nodes
-----------

Graph nodes are wrappers around functions. They describe the name, inputs, and outputs of a function, and can optionally
maintain some state.

Nodes in the graph are automatically assigned a color during the graph compilation phase, either `worker`, `localCollector`,
or `globalCollector`. A node's color determines which type of process executes it.

Map
^^^

Map nodes apply `func` to their `inputs`.

.. autoclass:: ami.graph_nodes.Map
   :special-members: __init__
   :inherited-members:

FilterOn
^^^^^^^^

FilterOn is a wrapper around NetworkFoX If nodes.

.. autoclass:: ami.graph_nodes.FilterOn
   :members:
   :special-members: __init__

FilterOff
^^^^^^^^^

FilterOff is a wrapper around NetworkFoX Else nodes.

.. autoclass:: ami.graph_nodes.FilterOff
   :members:
   :special-members: __init__

Graph Example
-------------

Below we show an example of a complex graph.

.. literalinclude:: graph_example.py
