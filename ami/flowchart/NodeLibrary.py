from collections import OrderedDict
from ami.flowchart.Node import Node


def isNodeClass(cls):
    try:
        if not issubclass(cls, Node):
            return False
    except Exception:
        return False
    return hasattr(cls, 'nodeName')


class NodeLibrary:
    """
    A library of flowchart Node types. Custom libraries may be built to provide
    each flowchart with a specific set of allowed Node types.
    """

    def __init__(self):
        self.nodeList = OrderedDict()
        self.nodeTree = OrderedDict()
        self.labelTree = OrderedDict()

    def addNodeType(self, nodeClass, paths, override=False):
        """
        Register a new node type. If the type's name is already in use,
        an exception will be raised (unless override=True).

        ============== =========================================================
        **Arguments:**

        nodeClass      a subclass of Node (must have typ.nodeName)
        paths          list of tuples specifying the location(s) this
                       type will appear in the library tree.
        override       if True, overwrite any class having the same name
        ============== =========================================================
        """
        if not isNodeClass(nodeClass):
            raise Exception("Object %s is not a Node subclass" % str(nodeClass))

        name = nodeClass.nodeName
        if not override and name in self.nodeList:
            raise Exception("Node type name '%s' is already registered." % name)

        self.nodeList[name] = nodeClass
        for path in paths:
            root = self.nodeTree
            for n in path:
                if n not in root:
                    root[n] = OrderedDict()
                root = root[n]
            root[name] = nodeClass

    def getNodeType(self, name):
        try:
            return self.nodeList[name]
        except KeyError:
            raise Exception("No node type called '%s'" % name)

    def getNodeTree(self):
        return self.nodeTree

    def getLabelTree(self):
        if self.labelTree:
            return self.labelTree

        for root, children in self.nodeTree.items():
            items = {name: child.desc for name, child in children.items()}
            items = list(items.items())
            self.labelTree[root] = items

        return self.labelTree

    def reload(self):
        """
        Reload Node classes in this library.
        """
        raise NotImplementedError()


class SourceLibrary:
    """
    A library of flowchart Node types. Custom libraries may be built to provide
    each flowchart with a specific set of allowed Node types.
    """

    def __init__(self):
        self.sourceList = OrderedDict()
        self.sourceTree = OrderedDict()
        self.labelTree = OrderedDict()

    def addNodeType(self, name, nodeType, paths, override=False):
        """
        Register a new node type. If the type's name is already in use,
        an exception will be raised (unless override=True).

        ============== =========================================================
        **Arguments:**

        nodeClass      a subclass of Node (must have typ.nodeName)
        paths          list of tuples specifying the location(s) this
                       type will appear in the library tree.
        override       if True, overwrite any class having the same name
        ============== =========================================================
        """
        if not override and name in self.sourceList:
            raise Exception("Node type name '%s' is already registered." % name)

        self.sourceList[name] = nodeType
        for path in paths:
            root = self.sourceTree
            for n in path:
                if n not in root:
                    root[n] = OrderedDict()
                root = root[n]
            root[name] = name

    def getSourceType(self, name):
        try:
            return self.sourceList[name]
        except KeyError:
            raise Exception("No node type called '%s'" % name)

    def getSourceTree(self):
        return self.sourceTree

    def getLabelTree(self):
        if self.labelTree:
            return self.labelTree

        for root, children in self.sourceTree.items():
            items = {name: str(self.getSourceType(child)) for name, child in children.items()}
            items = list(items.items())
            self.labelTree[root] = items

        return self.labelTree

    def reload(self):
        """
        Reload Node classes in this library.
        """
        raise NotImplementedError()
