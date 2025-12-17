from ..utils.graphviz import *

def draw_fsm(fsm):
    graph = VisualGraph()
    for k, v in fsm.get_rule_table().items():
        graph.add_node(k.name, [(vk.name, vv.name) for vk, vv in v.items()], color='red' if k == fsm.get_state() else 'black')
    return graph.draw()

def draw_full_fsm(fsm):
    graph = VisualGraph()
    for k, v in fsm.get_full_rule_table().items():
        graph.add_node(k.name, [(vk.name, vv.name) for vk, vv in v.items()], color='red' if k == fsm.get_state() else 'black')
    return graph.draw()