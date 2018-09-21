from ami.graph import Graph
from ami.comm import Store


class TestGraph:
    def setup(self):
        self.store = Store()
        self.graph = Graph(self.store)

    def teardown(self):
        pass

    def test_fake(self):
        self.store.put("fake", 5)
        new_graph = {
            "fake2": {
                "inputs": ["fake"],
                "outputs": [("fake2", "Pick1")],
                "code": "fake2 = fake*2"
            }
        }
        self.graph.update(new_graph)
        self.graph.configure(["fake"])
        self.graph.execute()

        assert self.store.get("fake2") == 10
