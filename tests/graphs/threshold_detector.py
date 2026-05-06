import typing

import ami.graph_nodes as gn
from ami.flowchart.Node import Node


class EventProcessor:

    def __init__(self):
        pass

    def begin_run(self):
        pass

    def end_run(self):
        pass

    def begin_step(self, step):
        pass

    def end_step(self, step):
        pass

    def on_event(self, In, *args, **kwargs):
        In[In < 50] = 0
        # return 1 output(s)
        return In


class threshold_detector(Node):
    """ """

    nodeName = "threshold_detector"

    def __init__(self, name):
        super().__init__(
            name,
            terminals={
                "threshold": {"io": "out", "removable": True, "ttype": typing.Any, "optional": False, "group": None},
                "In": {"io": "in", "removable": True, "ttype": typing.Any, "optional": False, "group": None},
            },
        )

    def to_operation(self, **kwargs):
        proc = EventProcessor()

        return gn.Map(
            name=self.name() + "_operation",
            **kwargs,
            func=proc.on_event,
            begin_run=proc.begin_run,
            end_run=proc.end_run,
            begin_step=proc.begin_step,
            end_step=proc.end_step,
        )
