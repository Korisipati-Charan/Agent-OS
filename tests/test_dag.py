"""
Tests for Task DAG: topological sorting, cycle detection, and dependency progression.
"""

import pytest
from agentos.cognitive.dag import TaskDAG, TaskNode, TaskStatus, CycleError


def test_topological_sort_success():
    dag = TaskDAG(task_id="t1", goal="Test DAG")
    n1 = TaskNode(node_id="n1", description="step 1", tool_name="tool_a", dependencies=set())
    n2 = TaskNode(node_id="n2", description="step 2", tool_name="tool_b", dependencies={"n1"})
    n3 = TaskNode(node_id="n3", description="step 3", tool_name="tool_c", dependencies={"n2"})

    dag.add_node(n1)
    dag.add_node(n2)
    dag.add_node(n3)

    order = dag.validate_acyclic()
    assert order == ["n1", "n2", "n3"]


def test_dag_cycle_detection():
    dag = TaskDAG(task_id="t2", goal="Cyclic DAG")
    n1 = TaskNode(node_id="n1", description="step 1", tool_name="tool_a", dependencies={"n2"})
    n2 = TaskNode(node_id="n2", description="step 2", tool_name="tool_b", dependencies={"n1"})

    dag.add_node(n1)
    dag.add_node(n2)

    with pytest.raises(CycleError):
        dag.validate_acyclic()


def test_ready_node_progression():
    dag = TaskDAG(task_id="t3", goal="Progression")
    n1 = TaskNode(node_id="n1", description="step 1", tool_name="tool_a", dependencies=set())
    n2 = TaskNode(node_id="n2", description="step 2", tool_name="tool_b", dependencies={"n1"})

    dag.add_node(n1)
    dag.add_node(n2)

    ready = dag.get_ready_nodes()
    assert len(ready) == 1
    assert ready[0].node_id == "n1"

    dag.mark_completed("n1", result="output_1")

    ready_2 = dag.get_ready_nodes()
    assert len(ready_2) == 1
    assert ready_2[0].node_id == "n2"
