Data Sources
============

Data sources are generators which yield new event data as :ref:`Messages` when it is available.

AMI can be extended to process different types of data by implementing a new data source which adheres to the interface
specificed by the abstract base class :ref:`Source`.

Messages
--------

Messages are containers for data. There are a number of different message types described by the `MsgTypes` enum.

Message Types
^^^^^^^^^^^^^

.. autoclass:: ami.data.MsgTypes
   :members:


Message
^^^^^^^

Message data is stored in the payload. For datagram message types it should be a dictionary.

.. autoclass:: ami.data.Message
   :members:
   :member-order: bysource
   :special-members:
   :exclude-members: __weakref__

Sources
-------

Data sources must implement the interface described the abstract base class :ref:`Source`.

There are currently three data sources implemented, :ref:`StaticSource`, :ref:`RandomSource`, and :ref:`PsanaSource`.

`StaticSource` and `RandomSource` are used for regression testing and demonstration purposes.

Each source can specify its own configuration options in a JSON file. The configuration options for each source are
described below.

Source
^^^^^^

Source is an abstract base class which describes the interface all sources must implement.

.. autoclass:: ami.data.Source
   :members:
   :member-order: bysource
   :special-members:
   :exclude-members: __weakref__

StaticSource
^^^^^^^^^^^^

.. autoclass:: ami.data.StaticSource
   :members:
   :member-order: bysource
   :special-members:
   :exclude-members: __weakref__

RandomSource
^^^^^^^^^^^^

.. autoclass:: ami.data.RandomSource
   :members:
   :member-order: bysource
   :special-members:
   :exclude-members: __weakref__

PsanaSource
^^^^^^^^^^^

.. autoclass:: ami.data.PsanaSource
   :members:
   :member-order: bysource
   :special-members:
   :exclude-members: __weakref__
