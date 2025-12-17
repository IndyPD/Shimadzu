from graphviz import Digraph


class GraphNode:
    def __init__(self, id, childs, **kwargs):
        self.id = id
        self.childs = childs
        self.kwargs = kwargs

    def get_available_childs(self):
        return self.childs


class VisualGraph:
    def __init__(self, filename="graph.gv"):
        self.graph = Digraph('G', filename=filename)
        self.node_dict = {}

    ##
    # @param childs list of node names or edge-node name tuples
    def add_node(self, node_id, childs, **kwargs):
        if node_id in self.node_dict:
            self.node_dict[node_id].childs += childs
        else:
            self.node_dict[node_id] = GraphNode(node_id, childs, **kwargs)

    def remove_node(self, node_id):
        del self.node_dict[node_id]

    def draw(self, unique=False):
        self.graph.clear()
        for node in self.node_dict.values():
            self.graph.node(node.id, **node.kwargs)
            childs = node.get_available_childs()
            if unique:
                childs = list(set(childs))
            for child in childs:
                if isinstance(child, tuple) or isinstance(child, list):
                    self.graph.edge(str(node.id), str(child[1]), str(child[0]))
                else:
                    self.graph.edge(str(node.id), str(child))
        return self.graph


def draw_program(program):
    try:
        dot = Digraph(comment='The Round Table')

        dot.attr(rankdir='TB')  # Top to bottom layout

        def add_children(item_dict, node_id):
            node = item_dict[node_id]
            for child_id in node.children:
                child = item_dict[child_id]
                dot.node(child.id, child.name,
                         color='black' if child.active else 'gray',
                        style='filled',
                        fillcolor='white' if child.active else 'gray')
                dot.edge(node.id, child.id)
                if not child.folded:
                    add_children(item_dict, child_id)

        root_id = program.root
        root = program.item_dict[root_id]
        dot.node(root_id, root.name)
        add_children(program.item_dict, root_id)

        return dot
    except Exception as e:
        print("Some error in GraphViz - skip drawing")
        print(e)
