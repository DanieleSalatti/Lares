"""Tests for Graph Memory capabilities."""

import os
import tempfile

import pytest

from lares.providers.sqlite_with_graph import SqliteGraphMemoryProvider


@pytest.fixture
async def provider():
    """Create a test provider with temp database."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        p = SqliteGraphMemoryProvider(
            db_path=db_path, base_instructions="Test system prompt"
        )
        await p.initialize()
        yield p
        await p.shutdown()


@pytest.mark.asyncio
async def test_initialize_creates_graph_tables(provider):
    """Test that initialization creates graph tables."""
    cursor = await provider._db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    tables = [row[0] for row in await cursor.fetchall()]

    # Base tables
    assert "messages" in tables
    assert "memory_blocks" in tables

    # Graph tables
    assert "memory_nodes" in tables
    assert "memory_edges" in tables


@pytest.mark.asyncio
async def test_create_memory_node(provider):
    """Test creating a memory node."""
    node_id = await provider.create_memory_node(
        content="Daniele is training for Aconcagua",
        source="conversation",
        summary="Aconcagua training",
        tags=["mountaineering", "training"],
    )

    assert node_id is not None
    # Node IDs are UUIDs
    assert len(node_id) == 36  # UUID format: 8-4-4-4-12


@pytest.mark.asyncio
async def test_get_memory_node(provider):
    """Test retrieving a memory node."""
    node_id = await provider.create_memory_node(
        content="Test content here",
        source="test",
        summary="Test summary",
        tags=["test"],
    )

    node = await provider.get_memory_node(node_id)

    assert node is not None
    assert node["id"] == node_id
    assert node["content"] == "Test content here"
    assert node["source"] == "test"
    assert node["summary"] == "Test summary"
    assert "test" in node["tags"]


@pytest.mark.asyncio
async def test_get_nonexistent_node_returns_none(provider):
    """Test that getting nonexistent node returns None."""
    node = await provider.get_memory_node("00000000-0000-0000-0000-000000000000")
    assert node is None


@pytest.mark.asyncio
async def test_search_memory_nodes(provider):
    """Test searching memory nodes by content."""
    await provider.create_memory_node(
        content="Python is a great programming language",
        source="test",
    )
    await provider.create_memory_node(
        content="JavaScript runs in browsers",
        source="test",
    )
    await provider.create_memory_node(
        content="Python also has great ML libraries",
        source="test",
    )

    results = await provider.search_memory_nodes("Python")

    assert len(results) == 2
    for node in results:
        assert "Python" in node["content"]


@pytest.mark.asyncio
async def test_search_nodes_by_summary(provider):
    """Test searching memory nodes by summary."""
    await provider.create_memory_node(
        content="First node content",
        source="test",
        summary="Important work item",
    )
    await provider.create_memory_node(
        content="Second node content",
        source="test",
        summary="Personal note",
    )
    await provider.create_memory_node(
        content="Third node content",
        source="test",
        summary="Important personal matter",
    )

    # Search matches summary field
    results = await provider.search_memory_nodes("Important")

    assert len(results) == 2


@pytest.mark.asyncio
async def test_list_recent_nodes(provider):
    """Test listing recent nodes."""
    await provider.create_memory_node(content="First", source="test")
    await provider.create_memory_node(content="Second", source="test")
    await provider.create_memory_node(content="Third", source="test")

    results = await provider.list_recent_nodes(limit=2)

    assert len(results) == 2
    # Most recent first
    assert results[0]["content"] == "Third"
    assert results[1]["content"] == "Second"


@pytest.mark.asyncio
async def test_create_memory_edge(provider):
    """Test creating an edge between nodes."""
    node1 = await provider.create_memory_node(content="Node 1", source="test")
    node2 = await provider.create_memory_node(content="Node 2", source="test")

    edge_id = await provider.create_memory_edge(
        source_id=node1,
        target_id=node2,
        edge_type="relates_to",
        initial_weight=0.8,
    )

    assert edge_id is not None
    # Edge IDs are UUIDs
    assert len(edge_id) == 36


@pytest.mark.asyncio
async def test_get_connected_nodes(provider):
    """Test retrieving connected nodes."""
    center = await provider.create_memory_node(content="Center node", source="test")
    node1 = await provider.create_memory_node(content="Connected 1", source="test")
    node2 = await provider.create_memory_node(content="Connected 2", source="test")
    isolated = await provider.create_memory_node(content="Isolated", source="test")

    await provider.create_memory_edge(center, node1, "relates_to")
    await provider.create_memory_edge(center, node2, "relates_to")

    connected = await provider.get_connected_nodes(center)

    assert len(connected) == 2
    connected_ids = [n["id"] for n in connected]
    assert node1 in connected_ids
    assert node2 in connected_ids
    assert isolated not in connected_ids


@pytest.mark.asyncio
async def test_strengthen_edge(provider):
    """Test strengthening an edge increases weight."""
    node1 = await provider.create_memory_node(content="Node 1", source="test")
    node2 = await provider.create_memory_node(content="Node 2", source="test")

    await provider.create_memory_edge(node1, node2, "relates_to", initial_weight=0.5)

    # Strengthen the edge
    new_weight = await provider.strengthen_edge(node1, node2, amount=0.2)

    # Check the weight increased
    assert new_weight == pytest.approx(0.7, rel=0.01)

    # Verify in database
    cursor = await provider._db.execute(
        "SELECT weight FROM memory_edges WHERE source_node_id = ? AND target_node_id = ?",
        (node1, node2),
    )
    row = await cursor.fetchone()
    assert row is not None
    assert row[0] == pytest.approx(0.7, rel=0.01)


@pytest.mark.asyncio
async def test_traverse_graph(provider):
    """Test BFS traversal of graph."""
    # Create a small graph: A -> B -> C, A -> D
    node_a = await provider.create_memory_node(content="Node A", source="test")
    node_b = await provider.create_memory_node(content="Node B", source="test")
    node_c = await provider.create_memory_node(content="Node C", source="test")
    node_d = await provider.create_memory_node(content="Node D", source="test")
    node_e = await provider.create_memory_node(content="Node E", source="test")

    await provider.create_memory_edge(node_a, node_b, "relates_to")
    await provider.create_memory_edge(node_b, node_c, "relates_to")
    await provider.create_memory_edge(node_a, node_d, "relates_to")
    # E is isolated

    # Traverse from A with depth 1
    result = await provider.traverse_graph(node_a, max_depth=1)
    visited_ids = [n["id"] for n in result]

    assert node_a in visited_ids  # Start node
    assert node_b in visited_ids  # Depth 1
    assert node_d in visited_ids  # Depth 1
    assert node_c not in visited_ids  # Depth 2, shouldn't be included
    assert node_e not in visited_ids  # Isolated

    # Traverse with depth 2
    result = await provider.traverse_graph(node_a, max_depth=2)
    visited_ids = [n["id"] for n in result]

    assert node_c in visited_ids  # Now depth 2 is included


@pytest.mark.asyncio
async def test_graph_stats(provider):
    """Test getting graph statistics."""
    # Empty graph
    stats = await provider.get_graph_stats()
    assert stats["node_count"] == 0
    assert stats["edge_count"] == 0

    # Add some content
    node1 = await provider.create_memory_node(content="Node 1", source="test")
    node2 = await provider.create_memory_node(content="Node 2", source="test")
    await provider.create_memory_edge(node1, node2, "relates_to")

    stats = await provider.get_graph_stats()
    assert stats["node_count"] == 2
    assert stats["edge_count"] == 1


@pytest.mark.asyncio
async def test_update_node_access(provider):
    """Test that manually accessing a node updates its access count."""
    node_id = await provider.create_memory_node(content="Test node", source="test")

    # Check initial access count directly (before get_memory_node calls it)
    cursor = await provider._db.execute(
        "SELECT access_count FROM memory_nodes WHERE id = ?", (node_id,)
    )
    row = await cursor.fetchone()
    assert row[0] == 0  # Initial access count

    # Update access manually
    await provider.update_node_access(node_id)

    # Access count should increase
    cursor = await provider._db.execute(
        "SELECT access_count FROM memory_nodes WHERE id = ?", (node_id,)
    )
    row = await cursor.fetchone()
    assert row[0] == 1


@pytest.mark.asyncio
async def test_get_memory_node_updates_access(provider):
    """Test that get_memory_node increments access count in database."""
    node_id = await provider.create_memory_node(content="Test node", source="test")

    # First get - updates access after reading, so returned value is still 0
    node = await provider.get_memory_node(node_id)
    assert node["access_count"] == 0  # Returns value BEFORE increment

    # But database should now have 1
    cursor = await provider._db.execute(
        "SELECT access_count FROM memory_nodes WHERE id = ?", (node_id,)
    )
    row = await cursor.fetchone()
    assert row[0] == 1

    # Second get - returns 1 (the current value), then increments to 2
    node = await provider.get_memory_node(node_id)
    assert node["access_count"] == 1

    # Database now has 2
    cursor = await provider._db.execute(
        "SELECT access_count FROM memory_nodes WHERE id = ?", (node_id,)
    )
    row = await cursor.fetchone()
    assert row[0] == 2


@pytest.mark.asyncio
async def test_base_sqlite_functionality_still_works(provider):
    """Test that base SQLite provider functions work with graph provider."""
    # Add a message (base functionality)
    msg_id = await provider.add_message("user", "Hello!")
    assert msg_id is not None

    # Add a block (base functionality)
    await provider.update_block("test", "Block content")

    # Get context (base functionality)
    context = await provider.get_context()
    assert len(context.messages) == 1
    assert len(context.blocks) == 1

    # Graph functionality also works
    node_id = await provider.create_memory_node(content="Graph node", source="test")
    assert node_id is not None


@pytest.mark.asyncio
async def test_edge_weight_capped_at_one(provider):
    """Test that edge weights are capped at 1.0."""
    node1 = await provider.create_memory_node(content="Node 1", source="test")
    node2 = await provider.create_memory_node(content="Node 2", source="test")

    await provider.create_memory_edge(node1, node2, initial_weight=0.9)

    # Strengthen by 0.3 - should cap at 1.0
    new_weight = await provider.strengthen_edge(node1, node2, amount=0.3)

    assert new_weight == 1.0


@pytest.mark.asyncio
async def test_source_filter_on_search(provider):
    """Test filtering nodes by source."""
    await provider.create_memory_node(
        content="Conversation about Python", source="conversation"
    )
    await provider.create_memory_node(
        content="Research on Python ML", source="research"
    )
    await provider.create_memory_node(
        content="Python reflection", source="reflection"
    )

    # Search with source filter
    results = await provider.search_memory_nodes(
        "Python", source_filter="conversation"
    )

    assert len(results) == 1
    assert results[0]["source"] == "conversation"


@pytest.mark.asyncio
async def test_source_filter_on_list_recent(provider):
    """Test filtering recent nodes by source."""
    await provider.create_memory_node(content="Conv 1", source="conversation")
    await provider.create_memory_node(content="Research 1", source="research")
    await provider.create_memory_node(content="Conv 2", source="conversation")

    results = await provider.list_recent_nodes(source_filter="conversation")

    assert len(results) == 2
    for node in results:
        assert node["source"] == "conversation"


@pytest.mark.asyncio
async def test_nodes_by_source_in_stats(provider):
    """Test that stats include node counts by source."""
    await provider.create_memory_node(content="C1", source="conversation")
    await provider.create_memory_node(content="C2", source="conversation")
    await provider.create_memory_node(content="R1", source="research")

    stats = await provider.get_graph_stats()

    assert "nodes_by_source" in stats
    assert stats["nodes_by_source"]["conversation"] == 2
    assert stats["nodes_by_source"]["research"] == 1


@pytest.mark.asyncio
async def test_decay_edges(provider):
    """Test Hebbian decay reduces edge weights."""
    # Create two nodes and an edge
    node1 = await provider.create_memory_node("Node A", source="test")
    node2 = await provider.create_memory_node("Node B", source="test")
    await provider.create_memory_edge(node1, node2, initial_weight=1.0)

    # Decay with 10% rate
    result = await provider.decay_edges(decay_rate=0.1, floor=0.1)

    assert result["edge_count"] == 1
    assert result["decay_rate"] == 0.1
    assert result["floor"] == 0.1
    assert result["before_avg_weight"] == 1.0
    assert result["after_avg_weight"] == 0.9  # 1.0 * 0.9 = 0.9


@pytest.mark.asyncio
async def test_decay_respects_floor(provider):
    """Test that decay doesn't go below floor."""
    # Create edge with low weight
    node1 = await provider.create_memory_node("Node A", source="test")
    node2 = await provider.create_memory_node("Node B", source="test")
    await provider.create_memory_edge(node1, node2, initial_weight=0.15)

    # Decay with large rate but floor of 0.1
    result = await provider.decay_edges(decay_rate=0.5, floor=0.1)

    # 0.15 * 0.5 = 0.075, but floor is 0.1
    assert result["after_avg_weight"] == 0.1


@pytest.mark.asyncio
async def test_strengthen_co_accessed_edges():
    """Test that co-accessed nodes have their edges strengthened."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        provider = SqliteGraphMemoryProvider(db_path=db_path)
        await provider.initialize()

        # Create three related nodes
        node1 = await provider.create_memory_node("restart capability", source="perch_tick")
        node2 = await provider.create_memory_node("restart awareness", source="perch_tick")
        node3 = await provider.create_memory_node("restart command", source="perch_tick")

        # Create edges with initial weight 0.5
        await provider.create_memory_edge(node1, node2, initial_weight=0.5)
        await provider.create_memory_edge(node2, node3, initial_weight=0.5)

        # Strengthen co-accessed edges (simulate search result)
        strengthened = await provider.strengthen_co_accessed_edges([node1, node2, node3])
        
        # Should have strengthened existing edges
        assert strengthened >= 2  # At least 2 edges existed
        
        # Check weight increased
        connected = await provider.get_connected_nodes(node1)
        for conn in connected:
            if conn["id"] == node2:
                assert conn["weight"] > 0.5  # Should be strengthened
        
        await provider.shutdown()


@pytest.mark.asyncio
async def test_search_auto_strengthens_edges():
    """Test that searching auto-strengthens edges between found nodes."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        provider = SqliteGraphMemoryProvider(db_path=db_path)
        await provider.initialize()

        # Create nodes that will match "memory"
        node1 = await provider.create_memory_node("memory graph design", source="research")
        node2 = await provider.create_memory_node("memory decay patterns", source="research")
        
        # Create an edge between them
        await provider.create_memory_edge(node1, node2, initial_weight=0.3)
        
        # Search (should strengthen the edge)
        results = await provider.search_memory_nodes("memory")
        assert len(results) == 2
        
        # Check edge was strengthened
        connected = await provider.get_connected_nodes(node1)
        for conn in connected:
            if conn["id"] == node2:
                assert conn["weight"] > 0.3  # Was 0.3, should be ~0.32
        
        await provider.shutdown()


@pytest.mark.asyncio
async def test_search_weighted_basic(provider):
    """Test weighted search returns results with scores."""
    # Create nodes
    node1 = await provider.create_memory_node(
        content="Python programming language",
        source="test",
        summary="Python basics",
    )
    node2 = await provider.create_memory_node(
        content="Python data science",
        source="test",
        summary="Data science with Python",
    )

    # Search without any edges - should still work
    results = await provider.search_memory_nodes_weighted("Python", limit=5)

    assert len(results) == 2
    assert all("final_score" in r for r in results)
    assert all("graph_score" in r for r in results)
    assert all("recency_rank" in r for r in results)


@pytest.mark.asyncio
async def test_search_weighted_boosts_connected(provider):
    """Test that connected nodes get boosted in weighted search."""
    # Create nodes
    important = await provider.create_memory_node(
        content="Important Python memory",
        source="test",
    )
    isolated = await provider.create_memory_node(
        content="Isolated Python memory",
        source="test",
    )
    connector = await provider.create_memory_node(
        content="Connector node",
        source="test",
    )

    # Make 'important' well-connected
    await provider.create_memory_edge(connector, important, initial_weight=0.9)
    await provider.create_memory_edge(important, connector, initial_weight=0.8)

    # Search with high weight boost
    results = await provider.search_memory_nodes_weighted(
        "Python", limit=5, weight_boost=0.8
    )

    # Important node should rank higher due to connections
    python_results = [r for r in results if "Python" in r["content"]]
    assert len(python_results) == 2

    # Find which one has higher score
    important_result = next(r for r in python_results if r["id"] == important)
    isolated_result = next(r for r in python_results if r["id"] == isolated)

    assert important_result["graph_score"] > isolated_result["graph_score"]


@pytest.mark.asyncio
async def test_get_node_connectivity(provider):
    """Test getting connectivity stats for a node."""
    # Create a hub node
    hub = await provider.create_memory_node(content="Hub node", source="test")
    spoke1 = await provider.create_memory_node(content="Spoke 1", source="test")
    spoke2 = await provider.create_memory_node(content="Spoke 2", source="test")

    # Connect spokes to hub
    await provider.create_memory_edge(spoke1, hub, initial_weight=0.7)
    await provider.create_memory_edge(spoke2, hub, initial_weight=0.5)
    await provider.create_memory_edge(hub, spoke1, initial_weight=0.3)

    stats = await provider.get_node_connectivity(hub)

    assert stats["incoming"]["count"] == 2
    assert stats["incoming"]["total_weight"] == pytest.approx(1.2, rel=0.01)
    assert stats["outgoing"]["count"] == 1
    assert stats["outgoing"]["total_weight"] == pytest.approx(0.3, rel=0.01)
    assert stats["graph_score"] > 0


@pytest.mark.asyncio
async def test_weight_boost_zero_is_recency(provider):
    """Test that weight_boost=0 falls back to pure recency ordering."""
    # Create nodes in order
    old = await provider.create_memory_node(content="Old Python", source="test")
    new = await provider.create_memory_node(content="New Python", source="test")

    # Make old one highly connected
    connector = await provider.create_memory_node(content="Connector", source="test")
    await provider.create_memory_edge(connector, old, initial_weight=0.9)
    await provider.create_memory_edge(old, connector, initial_weight=0.9)

    # With weight_boost=0, newer should still be first
    results = await provider.search_memory_nodes_weighted(
        "Python", limit=5, weight_boost=0.0
    )

    python_results = [r for r in results if "Python" in r["content"]]
    assert python_results[0]["id"] == new  # Newer is first with 0 boost
