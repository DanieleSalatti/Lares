"""Graph memory MCP tools.

These tools allow the agent to create and traverse a graph memory
for associative recall.
"""

from __future__ import annotations


async def _get_graph_memory_provider():
    """Get a graph memory provider instance."""
    from lares.config import load_memory_config
    from lares.providers.sqlite_with_graph import SqliteGraphMemoryProvider

    memory_config = load_memory_config()
    provider = SqliteGraphMemoryProvider(
        db_path=memory_config.sqlite_path,
    )
    await provider.initialize()
    return provider


async def graph_create_node(
    content: str,
    source: str = "conversation",
    summary: str | None = None,
    tags: str | None = None,
) -> str:
    """Create a new memory node in the graph.

    Args:
        content: The memory content to store
        source: Origin type (conversation, perch_tick, research, reflection)
        summary: Optional short summary
        tags: Optional comma-separated tags

    Returns:
        The node ID or error message
    """
    try:
        provider = await _get_graph_memory_provider()
        tag_list = [t.strip() for t in tags.split(",")] if tags else None
        node_id = await provider.create_memory_node(
            content=content,
            source=source,
            summary=summary,
            tags=tag_list,
        )
        await provider.shutdown()
        return f"✅ Created memory node: {node_id}"
    except Exception as e:
        return f"Error creating node: {e}"


async def graph_search_nodes(
    query: str,
    limit: int = 10,
    source: str | None = None,
    weight_boost: float = 0.3,
) -> str:
    """Search memory nodes by content with weight-aware ranking.

    Combines text matching with graph connectivity - well-connected
    nodes rank higher. Also strengthens edges between co-accessed
    nodes (Hebbian learning).

    Args:
        query: Text to search for
        limit: Maximum results to return
        source: Optional filter by source type
        weight_boost: How much to favor connected nodes (0.0-1.0)
                     0.0 = pure recency, 1.0 = heavily favor connections
                     Default 0.3 = balanced

    Returns:
        Matching nodes with scores, or error message
    """
    try:
        provider = await _get_graph_memory_provider()
        nodes = await provider.search_memory_nodes_weighted(
            query, limit, source, weight_boost
        )
        await provider.shutdown()

        if not nodes:
            return f"No nodes found matching: {query}"

        lines = [f"🧠 Graph search for '{query}' (weight_boost={weight_boost}):", ""]
        for node in nodes:
            tags_str = (
                ", ".join(node.get("tags", [])) if node.get("tags") else "none"
            )
            lines.append(f"**{node['id'][:8]}...** ({node['source']})")
            # Show scores
            score_info = (
                f"score: {node['final_score']:.2f} "
                f"(graph: {node['graph_score']:.2f}, "
                f"recency: {node['recency_rank']:.2f})"
            )
            lines.append(f"  {score_info}")
            if node.get("summary"):
                lines.append(f"  Summary: {node['summary']}")
            lines.append(f"  Content: {node['content'][:120]}...")
            lines.append(f"  Tags: {tags_str}")
            lines.append("")

        return "\n".join(lines)
    except Exception as e:
        return f"Error searching nodes: {e}"


async def graph_create_edge(
    source_id: str,
    target_id: str,
    edge_type: str = "related",
    weight: float = 0.5,
) -> str:
    """Create an edge between two memory nodes.

    Args:
        source_id: Source node ID
        target_id: Target node ID
        edge_type: Relationship (related, caused_by, supports, contradicts)
        weight: Initial edge weight (0.0-1.0)

    Returns:
        Success message or error
    """
    try:
        provider = await _get_graph_memory_provider()
        await provider.create_memory_edge(
            source_id=source_id,
            target_id=target_id,
            edge_type=edge_type,
            initial_weight=weight,
        )
        await provider.shutdown()
        src_short = source_id[:8]
        tgt_short = target_id[:8]
        return f"✅ Edge {src_short}→{tgt_short} (type: {edge_type}, wt: {weight})"
    except Exception as e:
        return f"Error creating edge: {e}"


async def graph_get_connected(
    node_id: str,
    direction: str = "both",
    min_weight: float = 0.1,
    limit: int = 10,
) -> str:
    """Get nodes connected to a given node.

    Args:
        node_id: The node to find connections for
        direction: outgoing, incoming, or both
        min_weight: Minimum edge weight to include
        limit: Maximum results

    Returns:
        Connected nodes or error message
    """
    try:
        provider = await _get_graph_memory_provider()
        connected = await provider.get_connected_nodes(
            node_id=node_id,
            direction=direction,
            min_weight=min_weight,
            limit=limit,
        )
        await provider.shutdown()

        if not connected:
            return f"No connections found for node {node_id[:8]}..."

        lines = [f"🔗 Connections for {node_id[:8]}... ({direction}):", ""]
        for conn in connected:
            arrow = "→" if conn["direction"] == "outgoing" else "←"
            wt = conn["weight"]
            etype = conn["edge_type"]
            lines.append(f"  {arrow} {conn['id'][:8]}... (wt: {wt:.2f}, {etype})")
            if conn.get("summary"):
                lines.append(f"     {conn['summary']}")
            else:
                lines.append(f"     {conn['content'][:80]}...")
            lines.append("")

        return "\n".join(lines)
    except Exception as e:
        return f"Error getting connections: {e}"


async def graph_traverse(
    start_node_id: str,
    max_depth: int = 2,
    max_nodes: int = 20,
    min_weight: float = 0.2,
) -> str:
    """Traverse the memory graph from a starting node (BFS).

    Args:
        start_node_id: Node to start traversal from
        max_depth: Maximum traversal depth
        max_nodes: Maximum nodes to return
        min_weight: Minimum edge weight to follow

    Returns:
        Nodes found during traversal or error message
    """
    try:
        provider = await _get_graph_memory_provider()
        nodes = await provider.traverse_graph(
            start_node_id=start_node_id,
            max_depth=max_depth,
            max_nodes=max_nodes,
            min_weight=min_weight,
        )
        await provider.shutdown()

        if not nodes:
            return f"No nodes found starting from {start_node_id[:8]}..."

        lines = [f"🗺️ Graph traversal from {start_node_id[:8]}...:", ""]
        for node in nodes:
            depth = node.get("depth", 0)
            indent = "  " * depth
            node_short = node["id"][:8]
            lines.append(f"{indent}[d{depth}] {node_short}... ({node['source']})")
            if node.get("summary"):
                lines.append(f"{indent}  {node['summary']}")
            else:
                lines.append(f"{indent}  {node['content'][:100]}...")
            lines.append("")

        return "\n".join(lines)
    except Exception as e:
        return f"Error traversing graph: {e}"


async def graph_stats() -> str:
    """Get statistics about the memory graph.

    Returns:
        Graph statistics (node count, edge count, etc.)
    """
    try:
        provider = await _get_graph_memory_provider()
        stats = await provider.get_graph_stats()
        await provider.shutdown()

        lines = [
            "📊 Memory Graph Statistics:",
            "",
            f"  Nodes: {stats.get('node_count', 0)}",
            f"  Edges: {stats.get('edge_count', 0)}",
            f"  Avg connections/node: {stats.get('avg_connections', 0)}",
            "",
            "  Nodes by source:",
        ]

        for source, count in stats.get("nodes_by_source", {}).items():
            lines.append(f"    • {source}: {count}")

        return "\n".join(lines)
    except Exception as e:
        return f"Error getting stats: {e}"


async def graph_decay_edges(decay_rate: float = 0.05, floor: float = 0.1) -> str:
    """Apply Hebbian decay to edge weights.

    Edges that haven't been strengthened recently will weaken.
    Run this periodically (e.g., nightly) to simulate memory forgetting.

    Args:
        decay_rate: Fraction to decay (0.05 = 5% per call)
        floor: Minimum weight (default 0.1, edges never fully disappear)

    Returns:
        Stats about the decay operation
    """
    memory = await _get_graph_memory_provider()
    result = await memory.decay_edges(decay_rate=decay_rate, floor=floor)

    return f"""🧠 Edge Decay Applied:

  Edges: {result['edge_count']}
  Decay rate: {result['decay_rate']*100:.1f}%
  Floor: {result['floor']}

  Before avg weight: {result['before_avg_weight']:.3f}
  After avg weight: {result['after_avg_weight']:.3f}
  Change: {result['after_avg_weight'] - result['before_avg_weight']:+.3f}
"""


async def graph_node_connectivity(node_id: str) -> str:
    """Get connectivity statistics for a memory node.

    Shows incoming/outgoing edge counts and weights.

    Args:
        node_id: The node ID to check

    Returns:
        Connectivity stats or error message
    """
    try:
        provider = await _get_graph_memory_provider()
        stats = await provider.get_node_connectivity(node_id)
        await provider.shutdown()

        incoming = stats["incoming"]
        outgoing = stats["outgoing"]

        return f"""📊 Connectivity for {node_id[:8]}...

Incoming edges: {incoming['count']}
  Total weight: {incoming['total_weight']:.3f}
  Avg weight: {incoming['avg_weight']:.3f}

Outgoing edges: {outgoing['count']}
  Total weight: {outgoing['total_weight']:.3f}
  Avg weight: {outgoing['avg_weight']:.3f}

Graph score: {stats['graph_score']:.3f}
"""
    except Exception as e:
        return f"Error getting connectivity: {e}"
