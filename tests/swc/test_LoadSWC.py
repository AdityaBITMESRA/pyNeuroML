import unittest

import networkx as nx

from pyneuroml.swc.LoadSWC import SWCGraph, SWCNode


class TestSWCNode(unittest.TestCase):
    def test_init(self):
        node = SWCNode(1, 1, 0.0, 0.0, 0.0, 1.0, -1)
        self.assertEqual(node.id, 1)
        self.assertEqual(node.type, 1)
        self.assertEqual(node.x, 0.0)
        self.assertEqual(node.y, 0.0)
        self.assertEqual(node.z, 0.0)
        self.assertEqual(node.radius, 1.0)
        self.assertEqual(node.parent_id, -1)

    def test_invalid_init(self):
        with self.assertRaises(ValueError):
            SWCNode("a", 1, 0.0, 0.0, 0.0, 1.0, -1)


class TestSWCGraph(unittest.TestCase):
    def setUp(self):
        self.tree = SWCGraph()
        self.node1 = SWCNode(1, 1, 0.0, 0.0, 0.0, 1.0, -1)
        self.node2 = SWCNode(2, 3, 1.0, 0.0, 0.0, 0.5, 1)
        self.node2.fraction_along = 1.0
        self.node3 = SWCNode(3, 3, 2.0, 0.0, 0.0, 0.5, 2)
        self.node3.fraction_along = 0.5
        self.tree.add_node(self.node1)
        self.tree.add_node(self.node2)
        self.tree.add_node(self.node3)

    def test_duplicate_node(self):
        with self.assertRaises(ValueError):
            self.tree.add_node(SWCNode(1, 1, 0.0, 0.0, 0.0, 1.0, -1))

    def test_add_metadata(self):
        self.tree.add_metadata("ORIGINAL_SOURCE", "file.swc")
        self.assertEqual(self.tree.metadata["ORIGINAL_SOURCE"], "file.swc")

    def test_invalid_metadata(self):
        self.tree.add_metadata("INVALID_FIELD", "value")
        self.assertEqual(self.tree.metadata, {})

    def test_get_segment_adjacency_list(self):
        adjacency_list = self.tree.get_segment_adjacency_list()
        self.assertEqual(adjacency_list, {1: [self.node2], 2: [self.node3]})

    def test_get_graph(self):
        graph = self.tree.get_graph()
        self.assertIsInstance(graph, nx.DiGraph)
        self.assertEqual(len(graph.nodes), 3)
        self.assertEqual(len(graph.edges), 2)
        self.assertEqual(graph.nodes[self.node1.id]["type"], self.node1.type)
        self.assertEqual(graph.nodes[self.node2.id]["x"], self.node2.x)
        self.assertEqual(graph.nodes[self.node3.id]["radius"], self.node3.radius)
        self.assertEqual(graph.edges[(self.node1.id, self.node2.id)]["weight"], 0.0)
        self.assertEqual(graph.edges[(self.node2.id, self.node3.id)]["weight"], 0.5)

    def test_get_parent(self):
        self.assertIsNone(self.tree.get_parent(self.node1.id))
        self.assertEqual(self.tree.get_parent(self.node2.id), self.node1)
        self.assertEqual(self.tree.get_parent(self.node3.id), self.node2)
        with self.assertRaises(ValueError):
            self.tree.get_parent(4)
