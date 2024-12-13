import networkx as nx
import collections
import ami.graph_nodes as gn
from ami.data import RequestedData
from networkfox import compose, modifiers


def skip(n):
    return type(n) is str or type(n) is modifiers.optional


class Graph():

    def __init__(self, name):
        """
        Args:
            name (str): Name of graph
        """

        self.name = name
        self.graph = nx.DiGraph()
        self.graphkit = None
        self.global_operations = set()
        self.expanded_global_operations = set()
        self.children_of_global_operations = {}
        self.inputs = collections.defaultdict(set)
        self.outputs = collections.defaultdict(set)

    def __bool__(self):
        return self.graph.size() != 0

    def name_is_valid(self, name):
        """
        Returns true if the name passed is a valid user-defined name for inputs
        and outputs in the graph.

        In other words this checks if the name collides with one the graph may
        generate internally.

        Args:
            name (str): the name whose validity will be checked

        Returns:
            True if the name is valid, False otherwise.
        """
        if isinstance(name, str):
            return not name.endswith(('_worker', '_localCollector', '_globalCollector'))
        else:
            return False

    @property
    def names(self):
        """
        Returns a set of all user-defined names in the graph that can be used
        as inputs for nodes. Internally generated names are exclued from this
        list!

        Returns:
            The set of user-defined names
        """
        return {node for node in self.graph.nodes if self.name_is_valid(node)}

    @property
    def sources(self):
        """
        Returns a set of all input data sources needed by the worker to process
        the full graph.

        Returns:
            The set of all the input data sources
        """
        sources = RequestedData()

        for var in self.inputs['worker']:
            if self.name_is_valid(var):
                sources.add(var)

        return sources

    def add(self, ops):
        """
        Add operations to the graph. If a node already exists in the graph try to replace it if the new node's
        inputs and outputs match the old one's.

        Args:
            ops (list or Transformation): Operation node to add to graph.
        """

        if type(ops) is not list:
            ops = [ops]

        for op in ops:
            try:
                self.insert(op)
            except AssertionError:
                self.replace(op)

    def insert(self, op):
        """
        Insert an operation into the graph. If an operation already exists in the graph this function raises an
        AssertionError.

        Args:
            op (Transformation): Operation to insert into graph

        Raises:
            AssertionError: if an operation already exists in the graph
        """
        assert op not in self.graph.nodes(), "Operation may only be added once %s" % op.name

        if op.is_global_operation:
            for n in self.graph.nodes:
                if skip(n):
                    continue
                if n.is_global_operation and n.parent == op.parent and n.outputs == op.outputs:
                    assert False, "Operation may only be added once %s" % op.name

        for i in op.inputs:
            self.graph.add_edge(i, op)

        for o in op.outputs:
            self.graph.add_edge(op, o)

        self.graphkit = None

    def remove(self, name):
        """
        Recursively removes a node and its descendants from the graph.

        Args:
            name (str): Name of node to remove from graph.
        """

        for n in self.graph.nodes:
            if skip(n):
                continue
            if n.name == name or n.parent == name:
                desc = nx.dag.descendants(self.graph, n)
                self.graph.remove_nodes_from(desc)
                self.graph.remove_node(n)
                break

        if name in self.children_of_global_operations:
            for child in self.children_of_global_operations[name]:
                self.remove(child.name)
                if child in self.expanded_global_operations:
                    self.expanded_global_operations.remove(child)
            del self.children_of_global_operations[name]

        self.graphkit = None

    def replace(self, new_node):
        """
        Replace a node in the graph. Inputs and outputs of new_node must match the existing node in the graph otherwise
        an AssertionError will be raised.

        Args:
            new_node (Transformation): New node to replace existing node with.

        Raises:
            AssertionError: if inputs and outputs of new_node do not match existing node.
        """
        if new_node.is_global_operation and new_node.parent in self.children_of_global_operations:
            descendants = set()
            ancestors = set()
            for child in self.children_of_global_operations[new_node.parent]:
                if child.name == '%s_worker' % new_node.name:
                    descendants.add(child)
                    descendants.update(nx.dag.descendants(self.graph, child))
                    assert set(child.inputs) == set(new_node.inputs), "Inputs must match."
                if child.name == '%s_globalCollector' % new_node.name:
                    ancestors.add(child)
                    ancestors.update(nx.dag.ancestors(self.graph, child))
                    assert set(child.outputs) == set(new_node.outputs), "Outputs must match."
            nodes_to_remove = descendants.intersection(ancestors)

            self.graph.remove_nodes_from(nodes_to_remove)
            for node in nodes_to_remove:
                if node in self.expanded_global_operations:
                    self.expanded_global_operations.remove(node)

            self.children_of_global_operations[new_node.parent].difference_update(nodes_to_remove)
        else:
            old_node = None
            for n in self.graph.nodes:
                if skip(n):
                    continue
                if n.name == new_node.name:
                    old_node = n
                    break

            if old_node is not None:
                # assert old_node is not None, "Old node not found: %s" % new_node.name
                # assert set(old_node.inputs) == set(new_node.inputs), "Inputs must match."
                self.graph.remove_node(old_node)

                diff = set(old_node.outputs).difference(new_node.outputs)
                for node in diff:
                    desc = nx.dag.descendants(self.graph, node)
                    self.graph.remove_nodes_from(desc)

        self.insert(new_node)
        self.graphkit = None

    def reset(self):
        """
        Resets the state of all StatefulTransmation nodes in the graph.
        """
        nodes = list(filter(lambda node: isinstance(node, gn.StatefulTransformation), self.graph.nodes))
        list(map(lambda node: node.reset(), nodes))

    def heartbeat_finished(self):
        """
        Execute post heartbeat hook on StatefulTransformation nodes in the graph.
        """
        nodes = list(filter(lambda node: isinstance(node, gn.StatefulTransformation),
                            self.graph.nodes))
        list(map(lambda node: node.heartbeat_finished(), nodes))

    def begin_run(self, color):
        """
        Execute pre run hook on nodes in the graph.
        """
        nodes = list(filter(lambda node: hasattr(node, "begin_run"), self.graph.nodes))
        list(map(lambda node: node.begin_run(color), nodes))

    def end_run(self, color):
        """
        Execute post run hook on nodes in the graph.
        """
        nodes = list(filter(lambda node: hasattr(node, "end_run"), self.graph.nodes))
        list(map(lambda node: node.end_run(color), nodes))

    def begin_step(self, step, color):
        """
        Execute pre step hook on nodes in the graph.
        """
        nodes = list(filter(lambda node: hasattr(node, "begin_step"), self.graph.nodes))
        list(map(lambda node: node.begin_step(step, color), nodes))

    def end_step(self, step, color):
        """
        Execute post step hook on nodes in the graph.
        """
        nodes = list(filter(lambda node: hasattr(node, "end_step"), self.graph.nodes))
        list(map(lambda node: node.end_step(step, color), nodes))

    def _color_nodes(self):
        """
        Generate all paths from inputs to outputs, for each path look for nodes which have the ``is_global_operation``
        attribute set to True. If in a given path for which we've found a global operation node there is no
        other node with ``is_global_operation`` true which preceeds it then we mark that node for expansion.
        """
        self.global_operations = set()

        global_operations = list(filter(lambda node: getattr(node, 'is_global_operation', False), self.graph.nodes))
        for node in global_operations:
            if node in self.expanded_global_operations:
                continue

            node.color = 'globalCollector'
            before = list(filter(lambda node: getattr(node, 'is_global_operation', False),
                                 nx.algorithms.dag.ancestors(self.graph, node)))
            if before == []:
                self.global_operations.add(node)

                for ancestor in nx.algorithms.dag.ancestors(self.graph, node):
                    if skip(ancestor):
                        continue

                    if ancestor.color == '':
                        ancestor.color = 'worker'

            for descendant in nx.algorithms.dag.descendants(self.graph, node):
                if skip(descendant):
                    continue

                if descendant.color == '':
                    descendant.color = 'globalCollector'

        for node in nx.algorithms.topological_sort(self.graph):
            if skip(node) or node.color:
                continue

            colors = set()

            for predecessor in map(self.graph.predecessors, node.inputs):
                colors.update(map(lambda node: getattr(node, 'color', ''), predecessor))

            if 'globalCollector' in colors:
                node.color = 'globalCollector'
            else:
                node.color = 'worker'

    def _expand_global_operations(self, num_workers, num_local_collectors):
        """
        Expand the nodes found in color_nodes into three nodes which execute on the worker, local collector, and
        global collector respectively. The number of workers and number of local collectors must be known in order to
        properly expand PickN operations.

        Args:
            num_workers (int): Total number of workers.
            num_local_collectors (int): Total number of local collectors.
        """

        inputs = [n for n, d in self.graph.in_degree() if d == 0]
        self.inputs['worker'].update(inputs)

        for node in self.global_operations:
            inputs = node.inputs
            outputs = node.outputs
            if node.parent not in self.children_of_global_operations:
                self.children_of_global_operations[node.parent] = set()

            self.graph.remove_node(node)
            NewNode = getattr(gn, node.__class__.__name__)

            color_order = ['worker', 'localCollector', 'globalCollector']
            worker_outputs = None
            local_collector_outputs = None
            extras = node.on_expand()

            for color in color_order:

                if color == 'worker':
                    worker_outputs = list(map(lambda o: o+'_worker', node.outputs))

                    worker_N = 1
                    if hasattr(node, 'N'):
                        worker_N = max(node.N // num_workers, 1)

                    worker_node = NewNode(name=node.name+'_worker',
                                          inputs=inputs, outputs=worker_outputs,
                                          reduction=node.reduction, N=worker_N,
                                          **extras)
                    worker_node.color = color
                    worker_node.is_global_operation = False
                    self.children_of_global_operations[node.parent].add(worker_node)
                    self.outputs[color].update(worker_outputs)
                    for i in inputs:
                        self.graph.add_edge(i, worker_node)
                    for o in worker_outputs:
                        self.graph.add_edge(worker_node, o)

                elif color == 'localCollector':
                    self.inputs[color].update(worker_outputs)
                    local_collector_outputs = list(map(lambda o: o+'_localCollector', node.outputs))

                    local_collector_N = 1
                    workers_per_local_collector = None
                    if hasattr(node, 'N'):
                        local_collector_N = max(node.N // num_local_collectors, 1)
                        workers_per_local_collector = max(num_workers // num_local_collectors, 1)

                    local_collector_node = NewNode(name=node.name+'_localCollector', inputs=worker_outputs,
                                                   outputs=local_collector_outputs, reduction=node.reduction,
                                                   N=local_collector_N, is_expanded=True,
                                                   num_contributors=workers_per_local_collector, **extras)
                    local_collector_node.color = color
                    local_collector_node.is_global_operation = False
                    self.children_of_global_operations[node.parent].add(local_collector_node)
                    self.outputs[color].update(local_collector_outputs)
                    for i in worker_outputs:
                        self.graph.add_edge(i, local_collector_node)
                    for o in local_collector_outputs:
                        self.graph.add_edge(local_collector_node, o)

                elif color == 'globalCollector':
                    self.inputs[color].update(local_collector_outputs)

                    N = getattr(node, 'N', 1)
                    N = max((N // num_workers)*num_workers, 1)

                    global_collector_node = NewNode(name=node.name+'_globalCollector',
                                                    inputs=local_collector_outputs,
                                                    outputs=outputs, reduction=node.reduction, N=N,
                                                    is_expanded=True,
                                                    num_contributors=num_local_collectors, **extras)
                    global_collector_node.color = color
                    self.children_of_global_operations[node.parent].add(global_collector_node)
                    self.expanded_global_operations.add(global_collector_node)
                    for i in local_collector_outputs:
                        self.graph.add_edge(i, global_collector_node)
                    for o in outputs:
                        self.graph.add_edge(global_collector_node, o)

    def _collect_global_inputs(self):
        """
        Insert Pick1 for nodes which run global collector but depend on inputs which are only available on worker.
        """
        inputs = [n for n, d in self.graph.in_degree() if d == 0]

        global_collector_nodes = list(filter(lambda node: getattr(node, 'color', '') == 'globalCollector',
                                             self.graph.nodes))

        for node in global_collector_nodes:
            new_inputs = []
            update_inputs = False
            if node in self.global_operations:
                continue
            for i in node.inputs:
                if i in inputs:
                    pickone = gn.PickN(name=i+"_pick1", inputs=[i], outputs=["one_"+i], parent=node.parent)
                    self.global_operations.add(pickone)
                    self.add(pickone)
                    update_inputs = True
                    new_inputs.extend(pickone.outputs)
                else:
                    new_inputs.append(i)
            self.graph.remove_node(node)
            if update_inputs:
                node.inputs = new_inputs
            self.add(node)

    def compile(self, num_workers=1, num_local_collectors=1):
        """
        Convert an AMI graph to a networkfox graph. This function must be called after any function which modifies the
        graph, ie add, insert, remove, or replace.

        This is done by coloring nodes, expanding global operations, and replacing filter nodes with the appropriate
        networkfox equivalents.

        Args:
            num_workers (int): Total number of workers.
            num_local_collectors (int): Total number of local collectors.
        """
        self.inputs = collections.defaultdict(set)
        self._color_nodes()
        self._collect_global_inputs()
        self._expand_global_operations(num_workers, num_local_collectors)

        seen = set()
        outputs = [n for n, d in self.graph.out_degree() if d == 0]
        body = []

        for node in self.graph.nodes:
            if node in seen or skip(node):
                continue
            body.append(node.to_operation())

        self.outputs['globalCollector'].update(outputs)
        self.graphkit = compose(name=self.name)(*body)

    def nxplot(self, filename=None):
        A = nx.nx_agraph.to_agraph(self.graph)
        A.layout(prog='dot')
        A.draw(filename)

    def plot(self, filename=None):
        """
        Generate plot of the graph.

        See networkfox documentation for options.

        Args:
            filename (str): Name of file to save plot to.

        Raises:
            AssertionError: if compile() has not been called first
        """
        assert self.graphkit is not None, "call compile first"

        self.graphkit.plot(filename)

    def __call__(self, *args, **kwargs):
        """
        Executes the graph. The dictionary returned by this function will only contain entries for
        the keys in self.outputs for the given color.

        :param args: args[0] should be dictionary of arguments required to execute graph nodes.
        :param kwargs: Should contain a key called color with a valid color, either worker, localCollector,
                       or globalCollector.
        :raises AssertionError: if compile() has not been falled first or if color is None.
        """
        missing_inputs = [k for k, v in args[0].items() if v is None]

        for missed_inputs in missing_inputs:
            args[0].pop(missed_inputs)

        assert self.graphkit is not None, "call compile first"
        color = kwargs.get('color', None)
        assert color is not None
        result = self.graphkit(*args, **kwargs)
        outputs = self.outputs[color]
        return {k: result[k] for k in outputs if k in result}

    def times(self):
        """
        Return time per execution of graphkit node.
        """
        assert self.graphkit is not None, "call compile first"
        return self.graphkit.times()

    def warnings(self):
        assert self.graphkit is not None, "call compile first"
        return self.graphkit.warnings()

    def metadata(self):
        """
        Return dictionary of node metadata.
        """
        assert self.graphkit is not None, "call compile first"
        return self.graphkit.node_metadata()
