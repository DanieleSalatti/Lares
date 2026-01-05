"""Graph memory extension for SQLite provider.

Adds memory nodes and edges for associative memory.
"""

import json
import uuid
from collections import deque
from datetime import UTC, datetime

import aiosqlite
import structlog

log = structlog.get_logger()


class GraphMemoryMixin:
    """Mixin that adds graph memory capabilities to SqliteMemoryProvider."""

    _db: aiosqlite.Connection | None

    async def _create_graph_tables(self) -> None:
        """Create graph memory tables if they don't exist."""
        if not self._db:
            raise RuntimeError("Provider not initialized")

        await self._db.executescript("""
            -- Memory graph nodes
            CREATE TABLE IF NOT EXISTS memory_nodes (
                id TEXT PRIMARY KEY,
                content TEXT NOT NULL,
                summary TEXT,
                source TEXT NOT NULL,
                tags TEXT,
                embedding BLOB,
                access_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_accessed TIMESTAMP
            );

            -- Memory graph edges
            CREATE TABLE IF NOT EXISTS memory_edges (
                id TEXT PRIMARY KEY,
                source_node_id TEXT NOT NULL,
                target_node_id TEXT NOT NULL,
                weight REAL DEFAULT 0.5,
                edge_type TEXT DEFAULT 'related',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_strengthened TIMESTAMP,
                FOREIGN KEY (source_node_id) REFERENCES memory_nodes(id) ON DELETE CASCADE,
                FOREIGN KEY (target_node_id) REFERENCES memory_nodes(id) ON DELETE CASCADE,
                UNIQUE(source_node_id, target_node_id)
            );

            -- Indexes for efficient traversal
            CREATE INDEX IF NOT EXISTS idx_edges_source ON memory_edges(source_node_id);
            CREATE INDEX IF NOT EXISTS idx_edges_target ON memory_edges(target_node_id);
            CREATE INDEX IF NOT EXISTS idx_edges_weight ON memory_edges(weight DESC);
            CREATE INDEX IF NOT EXISTS idx_nodes_source ON memory_nodes(source);
            CREATE INDEX IF NOT EXISTS idx_nodes_accessed ON memory_nodes(last_accessed DESC);
        """)
        await self._db.commit()
        log.info("graph_memory_tables_created")

    # === Node Operations ===

    async def create_memory_node(
        self,
        content: str,
        source: str = "conversation",
        summary: str | None = None,
        tags: list[str] | None = None,
    ) -> str:
        """Create a new memory node.

        Args:
            content: The memory content
            source: Origin type (conversation, perch_tick, research, reflection)
            summary: Optional short summary
            tags: Optional list of tags

        Returns:
            The node ID
        """
        if not self._db:
            raise RuntimeError("Provider not initialized")

        node_id = str(uuid.uuid4())
        now = datetime.now(tz=UTC).isoformat()

        await self._db.execute(
            """
            INSERT INTO memory_nodes
            (id, content, summary, source, tags, access_count, created_at, last_accessed)
            VALUES (?, ?, ?, ?, ?, 0, ?, ?)
            """,
            (
                node_id,
                content,
                summary,
                source,
                json.dumps(tags) if tags else None,
                now,
                now,
            ),
        )
        await self._db.commit()

        log.info("memory_node_created", node_id=node_id, source=source)
        return node_id

    async def get_memory_node(self, node_id: str) -> dict | None:
        """Get a single memory node by ID."""
        if not self._db:
            return None

        cursor = await self._db.execute(
            """
            SELECT id, content, summary, source, tags, access_count,
                   created_at, last_accessed
            FROM memory_nodes WHERE id = ?
            """,
            (node_id,),
        )
        row = await cursor.fetchone()

        if not row:
            return None

        # Update access tracking
        await self.update_node_access(node_id)

        return {
            "id": row["id"],
            "content": row["content"],
            "summary": row["summary"],
            "source": row["source"],
            "tags": json.loads(row["tags"]) if row["tags"] else [],
            "access_count": row["access_count"],
            "created_at": row["created_at"],
            "last_accessed": row["last_accessed"],
        }

    async def search_memory_nodes(
        self,
        query: str,
        limit: int = 10,
        source_filter: str | None = None,
        strengthen_connections: bool = True,
    ) -> list[dict]:
        """Search nodes by content (text search for Phase 1).

        Args:
            query: Text to search for
            limit: Max results to return
            source_filter: Optional filter by source type
            strengthen_connections: If True, strengthen edges between co-accessed nodes
        """
        if not self._db:
            return []

        pattern = f"%{query}%"

        if source_filter:
            cursor = await self._db.execute(
                """
                SELECT id, content, summary, source, tags, access_count,
                       created_at, last_accessed
                FROM memory_nodes
                WHERE (content LIKE ? OR summary LIKE ?) AND source = ?
                ORDER BY last_accessed DESC
                LIMIT ?
                """,
                (pattern, pattern, source_filter, limit),
            )
        else:
            cursor = await self._db.execute(
                """
                SELECT id, content, summary, source, tags, access_count,
                       created_at, last_accessed
                FROM memory_nodes
                WHERE content LIKE ? OR summary LIKE ?
                ORDER BY last_accessed DESC
                LIMIT ?
                """,
                (pattern, pattern, limit),
            )

        rows = await cursor.fetchall()
        results = [
            {
                "id": row["id"],
                "content": row["content"],
                "summary": row["summary"],
                "source": row["source"],
                "tags": json.loads(row["tags"]) if row["tags"] else [],
                "access_count": row["access_count"],
                "created_at": row["created_at"],
                "last_accessed": row["last_accessed"],
            }
            for row in rows
        ]

        # Hebbian co-activation: strengthen edges between nodes found together
        if strengthen_connections and len(results) >= 2:
            node_ids = [r["id"] for r in results]
            await self.strengthen_co_accessed_edges(node_ids)

        return results


    async def list_recent_nodes(
        self,
        limit: int = 20,
        source_filter: str | None = None,
    ) -> list[dict]:
        """List recently created/accessed nodes."""
        if not self._db:
            return []

        if source_filter:
            cursor = await self._db.execute(
                """
                SELECT id, content, summary, source, tags, access_count,
                       created_at, last_accessed
                FROM memory_nodes
                WHERE source = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (source_filter, limit),
            )
        else:
            cursor = await self._db.execute(
                """
                SELECT id, content, summary, source, tags, access_count,
                       created_at, last_accessed
                FROM memory_nodes
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            )

        rows = await cursor.fetchall()
        return [
            {
                "id": row["id"],
                "content": row["content"],
                "summary": row["summary"],
                "source": row["source"],
                "tags": json.loads(row["tags"]) if row["tags"] else [],
                "access_count": row["access_count"],
                "created_at": row["created_at"],
                "last_accessed": row["last_accessed"],
            }
            for row in rows
        ]

    async def update_node_access(self, node_id: str) -> None:
        """Update access count and last_accessed timestamp."""
        if not self._db:
            return

        await self._db.execute(
            """
            UPDATE memory_nodes
            SET access_count = access_count + 1,
                last_accessed = ?
            WHERE id = ?
            """,
            (datetime.now(tz=UTC).isoformat(), node_id),
        )
        await self._db.commit()

    # === Edge Operations ===

    async def create_memory_edge(
        self,
        source_id: str,
        target_id: str,
        edge_type: str = "related",
        initial_weight: float = 0.5,
    ) -> str:
        """Create an edge between two nodes.

        Returns edge ID. Updates weight if edge exists (upsert).
        """
        if not self._db:
            raise RuntimeError("Provider not initialized")

        edge_id = str(uuid.uuid4())
        now = datetime.now(tz=UTC).isoformat()

        # Upsert - if edge exists, strengthen it instead
        await self._db.execute(
            """
            INSERT INTO memory_edges
            (id, source_node_id, target_node_id, edge_type, weight, created_at, last_strengthened)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source_node_id, target_node_id) DO UPDATE SET
                weight = MIN(1.0, weight + 0.1),
                last_strengthened = excluded.last_strengthened
            """,
            (edge_id, source_id, target_id, edge_type, initial_weight, now, now),
        )
        await self._db.commit()

        log.info(
            "memory_edge_created",
            source=source_id,
            target=target_id,
            edge_type=edge_type,
        )
        return edge_id

    async def strengthen_edge(
        self,
        source_id: str,
        target_id: str,
        amount: float = 0.1,
    ) -> float:
        """Strengthen an edge (Hebbian learning).

        Returns new weight (capped at 1.0).
        """
        if not self._db:
            raise RuntimeError("Provider not initialized")

        now = datetime.now(tz=UTC).isoformat()

        await self._db.execute(
            """
            UPDATE memory_edges
            SET weight = MIN(1.0, weight + ?),
                last_strengthened = ?
            WHERE source_node_id = ? AND target_node_id = ?
            """,
            (amount, now, source_id, target_id),
        )
        await self._db.commit()

        # Get the new weight
        cursor = await self._db.execute(
            "SELECT weight FROM memory_edges WHERE source_node_id = ? AND target_node_id = ?",
            (source_id, target_id),
        )
        row = await cursor.fetchone()
        return row["weight"] if row else 0.0

    async def strengthen_co_accessed_edges(
        self,
        node_ids: list[str],
        amount: float = 0.02,
    ) -> int:
        """Strengthen edges between nodes accessed together (Hebbian co-activation).

        "Neurons that fire together wire together" - when nodes appear in
        the same search result, their connections should strengthen.

        Args:
            node_ids: List of node IDs that were accessed together
            amount: Small bump per co-access (default 0.02, subtle effect)

        Returns:
            Number of edges strengthened
        """
        if not self._db or len(node_ids) < 2:
            return 0

        now = datetime.now(tz=UTC).isoformat()
        strengthened = 0

        # Strengthen edges between all pairs of co-accessed nodes
        for i, source_id in enumerate(node_ids):
            for target_id in node_ids[i + 1:]:
                # Try both directions since edges are directional
                for src, tgt in [(source_id, target_id), (target_id, source_id)]:
                    cursor = await self._db.execute(
                        """
                        UPDATE memory_edges
                        SET weight = MIN(1.0, weight + ?),
                            last_strengthened = ?
                        WHERE source_node_id = ? AND target_node_id = ?
                        """,
                        (amount, now, src, tgt),
                    )
                    if cursor.rowcount > 0:
                        strengthened += 1

        await self._db.commit()

        if strengthened > 0:
            log.info(
                "edges_co_strengthened",
                node_count=len(node_ids),
                edges_strengthened=strengthened,
                amount=amount,
            )

        return strengthened

    async def get_connected_nodes(
        self,
        node_id: str,
        direction: str = "both",
        min_weight: float = 0.1,
        limit: int = 10,
    ) -> list[dict]:
        """Get nodes connected to this one, sorted by edge weight."""
        if not self._db:
            return []

        results = []

        if direction in ("outgoing", "both"):
            cursor = await self._db.execute(
                """
                SELECT n.id, n.content, n.summary, n.source, e.weight, e.edge_type
                FROM memory_nodes n
                JOIN memory_edges e ON n.id = e.target_node_id
                WHERE e.source_node_id = ? AND e.weight >= ?
                ORDER BY e.weight DESC
                LIMIT ?
                """,
                (node_id, min_weight, limit),
            )
            rows = await cursor.fetchall()
            for row in rows:
                results.append({
                    "id": row["id"],
                    "content": row["content"],
                    "summary": row["summary"],
                    "source": row["source"],
                    "weight": row["weight"],
                    "edge_type": row["edge_type"],
                    "direction": "outgoing",
                })

        if direction in ("incoming", "both"):
            cursor = await self._db.execute(
                """
                SELECT n.id, n.content, n.summary, n.source, e.weight, e.edge_type
                FROM memory_nodes n
                JOIN memory_edges e ON n.id = e.source_node_id
                WHERE e.target_node_id = ? AND e.weight >= ?
                ORDER BY e.weight DESC
                LIMIT ?
                """,
                (node_id, min_weight, limit),
            )
            rows = await cursor.fetchall()
            for row in rows:
                results.append({
                    "id": row["id"],
                    "content": row["content"],
                    "summary": row["summary"],
                    "source": row["source"],
                    "weight": row["weight"],
                    "edge_type": row["edge_type"],
                    "direction": "incoming",
                })

        # Sort by weight and limit
        results.sort(key=lambda x: x["weight"], reverse=True)
        return results[:limit]

    async def traverse_graph(
        self,
        start_node_id: str,
        max_depth: int = 2,
        max_nodes: int = 20,
        min_weight: float = 0.2,
    ) -> list[dict]:
        """BFS traversal from a starting node.

        Returns nodes with their distance from start.
        """
        if not self._db:
            return []

        visited = set()
        results = []
        queue = deque([(start_node_id, 0)])

        while queue and len(results) < max_nodes:
            current_id, depth = queue.popleft()

            if current_id in visited:
                continue
            visited.add(current_id)

            # Get node info
            node = await self.get_memory_node(current_id)
            if node:
                node["depth"] = depth
                results.append(node)

            # Don't explore beyond max depth
            if depth >= max_depth:
                continue

            # Get connected nodes
            connected = await self.get_connected_nodes(
                current_id,
                direction="outgoing",
                min_weight=min_weight,
                limit=10,
            )

            for conn in connected:
                if conn["id"] not in visited:
                    queue.append((conn["id"], depth + 1))

        return results

    async def get_graph_stats(self) -> dict:
        """Get statistics about the memory graph."""
        if not self._db:
            return {}

        # Node count
        cursor = await self._db.execute("SELECT COUNT(*) as count FROM memory_nodes")
        node_row = await cursor.fetchone()
        node_count = node_row["count"] if node_row else 0

        # Edge count
        cursor = await self._db.execute("SELECT COUNT(*) as count FROM memory_edges")
        edge_row = await cursor.fetchone()
        edge_count = edge_row["count"] if edge_row else 0

        # Average connections per node
        avg_connections = edge_count / node_count if node_count > 0 else 0

        # Nodes by source
        cursor = await self._db.execute(
            "SELECT source, COUNT(*) as count FROM memory_nodes GROUP BY source"
        )
        source_rows = await cursor.fetchall()
        by_source = {row["source"]: row["count"] for row in source_rows}

        return {
            "node_count": node_count,
            "edge_count": edge_count,
            "avg_connections": round(avg_connections, 2),
            "nodes_by_source": by_source,
        }

    # === Hebbian Dynamics ===

    async def decay_edges(
        self,
        decay_rate: float = 0.05,
        floor: float = 0.1,
    ) -> dict:
        """Apply exponential decay to all edge weights (Hebbian forgetting).

        Edges that haven't been strengthened recently will weaken.
        Formula: new_weight = max(floor, weight * (1 - decay_rate))

        Args:
            decay_rate: Fraction to decay per call (0.05 = 5% decay)
            floor: Minimum weight (edges never fully disappear)

        Returns:
            Stats about the decay operation
        """
        if not self._db:
            raise RuntimeError("Provider not initialized")

        # Get current stats before decay
        cursor = await self._db.execute(
            "SELECT COUNT(*) as count, AVG(weight) as avg_weight FROM memory_edges"
        )
        before = await cursor.fetchone()
        before_avg = before["avg_weight"] if before["avg_weight"] else 0

        # Apply decay: weight = MAX(floor, weight * (1 - decay_rate))
        await self._db.execute(
            """
            UPDATE memory_edges
            SET weight = MAX(?, weight * ?)
            """,
            (floor, 1 - decay_rate),
        )
        await self._db.commit()

        # Get stats after decay
        cursor = await self._db.execute(
            "SELECT COUNT(*) as count, AVG(weight) as avg_weight FROM memory_edges"
        )
        after = await cursor.fetchone()
        after_avg = after["avg_weight"] if after["avg_weight"] else 0

        log.info(
            "edges_decayed",
            decay_rate=decay_rate,
            floor=floor,
            before_avg=round(before_avg, 3),
            after_avg=round(after_avg, 3),
            edge_count=after["count"] if after else 0,
        )

        return {
            "edge_count": after["count"] if after else 0,
            "decay_rate": decay_rate,
            "floor": floor,
            "before_avg_weight": round(before_avg, 3),
            "after_avg_weight": round(after_avg, 3),
        }

    # === Weight-Aware Retrieval ===

    async def search_memory_nodes_weighted(
        self,
        query: str,
        limit: int = 10,
        source_filter: str | None = None,
        weight_boost: float = 0.3,
        strengthen_connections: bool = True,
    ) -> list[dict]:
        """Search nodes with weight-aware ranking.

        Unlike basic search (ordered by recency), this method boosts nodes
        that have stronger connections in the graph. Well-connected nodes
        are likely to be more important.

        Args:
            query: Text to search for
            limit: Max results to return
            source_filter: Optional filter by source type
            weight_boost: How much to weight graph connectivity (0.0-1.0)
                         0.0 = pure text search, 1.0 = heavily favor connected nodes
            strengthen_connections: If True, strengthen edges between co-accessed nodes

        Returns:
            List of nodes with added 'graph_score' and 'final_score' fields

        Scoring formula:
            graph_score = (sum of incoming weights + sum of outgoing weights) / 2
            final_score = (1 - weight_boost) * recency_rank + weight_boost * graph_score
        """
        if not self._db:
            return []

        pattern = f"%{query}%"

        # First, get text-matching candidates (more than we need for re-ranking)
        fetch_limit = limit * 3  # Fetch more to have candidates for re-ranking

        if source_filter:
            cursor = await self._db.execute(
                """
                SELECT id, content, summary, source, tags, access_count,
                       created_at, last_accessed
                FROM memory_nodes
                WHERE (content LIKE ? OR summary LIKE ?) AND source = ?
                ORDER BY last_accessed DESC
                LIMIT ?
                """,
                (pattern, pattern, source_filter, fetch_limit),
            )
        else:
            cursor = await self._db.execute(
                """
                SELECT id, content, summary, source, tags, access_count,
                       created_at, last_accessed
                FROM memory_nodes
                WHERE content LIKE ? OR summary LIKE ?
                ORDER BY last_accessed DESC
                LIMIT ?
                """,
                (pattern, pattern, fetch_limit),
            )

        rows = await cursor.fetchall()

        if not rows:
            return []

        # Build candidate list with graph scores
        candidates = []
        for i, row in enumerate(rows):
            node_id = row["id"]

            # Calculate graph score: sum of edge weights touching this node
            incoming_cursor = await self._db.execute(
                "SELECT COALESCE(SUM(weight), 0) as total "
                "FROM memory_edges WHERE target_node_id = ?",
                (node_id,),
            )
            incoming = await incoming_cursor.fetchone()
            incoming_weight = incoming["total"] if incoming else 0

            outgoing_cursor = await self._db.execute(
                "SELECT COALESCE(SUM(weight), 0) as total "
                "FROM memory_edges WHERE source_node_id = ?",
                (node_id,),
            )
            outgoing = await outgoing_cursor.fetchone()
            outgoing_weight = outgoing["total"] if outgoing else 0

            graph_score = (incoming_weight + outgoing_weight) / 2

            # Recency rank: 1.0 for most recent, decays for older
            recency_rank = 1.0 - (i / fetch_limit)

            # Final score combines recency and graph connectivity
            final_score = (
                (1 - weight_boost) * recency_rank + weight_boost * graph_score
            )

            candidates.append({
                "id": row["id"],
                "content": row["content"],
                "summary": row["summary"],
                "source": row["source"],
                "tags": json.loads(row["tags"]) if row["tags"] else [],
                "access_count": row["access_count"],
                "created_at": row["created_at"],
                "last_accessed": row["last_accessed"],
                "graph_score": round(graph_score, 3),
                "recency_rank": round(recency_rank, 3),
                "final_score": round(final_score, 3),
            })

        # Sort by final score (descending) and take top 'limit'
        candidates.sort(key=lambda x: x["final_score"], reverse=True)
        results = candidates[:limit]

        # Hebbian co-activation: strengthen edges between nodes found together
        if strengthen_connections and len(results) >= 2:
            node_ids = [r["id"] for r in results]
            await self.strengthen_co_accessed_edges(node_ids)

        return results

    async def get_node_connectivity(self, node_id: str) -> dict:
        """Get connectivity stats for a specific node.

        Returns incoming/outgoing weights and counts.
        """
        if not self._db:
            return {}

        # Incoming edges
        cursor = await self._db.execute(
            """
            SELECT COUNT(*) as count, COALESCE(SUM(weight), 0) as total,
                   COALESCE(AVG(weight), 0) as avg
            FROM memory_edges WHERE target_node_id = ?
            """,
            (node_id,),
        )
        incoming = await cursor.fetchone()

        # Outgoing edges
        cursor = await self._db.execute(
            """
            SELECT COUNT(*) as count, COALESCE(SUM(weight), 0) as total,
                   COALESCE(AVG(weight), 0) as avg
            FROM memory_edges WHERE source_node_id = ?
            """,
            (node_id,),
        )
        outgoing = await cursor.fetchone()

        inc_total = incoming["total"] if incoming else 0
        out_total = outgoing["total"] if outgoing else 0

        return {
            "incoming": {
                "count": incoming["count"] if incoming else 0,
                "total_weight": round(inc_total, 3),
                "avg_weight": round(incoming["avg"], 3) if incoming else 0,
            },
            "outgoing": {
                "count": outgoing["count"] if outgoing else 0,
                "total_weight": round(out_total, 3),
                "avg_weight": round(outgoing["avg"], 3) if outgoing else 0,
            },
            "graph_score": round((inc_total + out_total) / 2, 3),
        }
