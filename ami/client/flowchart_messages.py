class Msg(object):

    def __init__(self, name):
        self.name = name


class CreateNode(Msg):

    def __init__(self, name, node_type):
        super(CreateNode, self).__init__(name)
        self.node_type = node_type


class Display(Msg):

    def __init__(self, name, inputs):
        super(Display, self).__init__(name)
        self.inputs = inputs


class RenameNode(Msg):

    def __init__(self, old_name, new_name):
        super(RenameNode, self).__init__(old_name)
        self.new_name = new_name


class UpdateNodeAttributes(Msg):

    def __init__(self, node_name, inputs=None, conditions=None):
        super(UpdateNodeAttributes, self).__init__(node_name)
        self.inputs = inputs
        self.conditions = conditions
