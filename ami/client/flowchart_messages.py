class Msg(object):

    def __init__(self, name):
        self.name = name


class BrokerMsg(Msg):

    """
    Messages to command the broker to do something.
    """

    def __init__(self, name):
        super(BrokerMsg, self).__init__(name)


class NodeMsg(Msg):

    """
    Messages which should be cached and forwarded to node processes.
    """

    def __init__(self, name):
        super(NodeMsg, self).__init__(name)


class CreateNode(BrokerMsg):

    def __init__(self, name, node_type):
        super(CreateNode, self).__init__(name)
        self.node_type = node_type


class Display(NodeMsg):

    def __init__(self, name, inputs):
        super(Display, self).__init__(name)
        self.inputs = inputs


class RenameNode(Msg):

    def __init__(self, old_name, new_name):
        super(RenameNode, self).__init__(old_name)
        self.new_name = new_name


class UpdateNodeAttributes(NodeMsg):

    def __init__(self, node_name, inputs=None, conditions=None):
        super(UpdateNodeAttributes, self).__init__(node_name)
        self.inputs = inputs
        self.conditions = conditions
