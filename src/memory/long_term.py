"""Neo4j long-term relationship memory, scoped per player.

Neo4j is optional: if NEO4J_* variables are not set, every call degrades to a
harmless no-op (reads return []), so the game runs with short-term memory only.
"""
from __future__ import annotations

import logging
import os
import re
from typing import Optional

log = logging.getLogger(__name__)

_REL_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]*$")
KNOWN_RELATIONS = frozenset({
    "INTERACTED_WITH", "FEARS", "TRUSTS", "DISTRUSTS", "HATES", "RESPECTS",
    "IS_CURIOUS_ABOUT", "KNOWS_SECRET_OF", "HAS_WITNESSED", "WARNED",
    "THREATENED", "AIDED", "BETRAYED",
})
MAX_CONTEXTS_PER_EDGE = 20  # keep edges from growing without bound

_driver = None
_disabled = False
_constraints_done = False


def enabled() -> bool:
    return bool(os.getenv("NEO4J_URI") and os.getenv("NEO4J_USER") and os.getenv("NEO4J_PASSWORD"))


def _get_driver():
    """Return a shared driver, or None if Neo4j is not configured/available."""
    global _driver, _disabled, _constraints_done
    if _disabled:
        return None
    if _driver is None:
        if not enabled():
            log.info("Neo4j not configured; long-term memory disabled.")
            _disabled = True
            return None
        try:
            from neo4j import GraphDatabase
            _driver = GraphDatabase.driver(
                os.environ["NEO4J_URI"],
                auth=(os.environ["NEO4J_USER"], os.environ["NEO4J_PASSWORD"]),
            )
        except Exception as exc:  # missing package, bad URI, ...
            log.warning("Neo4j unavailable, long-term memory disabled: %s", exc)
            _disabled = True
            return None
    if not _constraints_done:
        try:
            with _driver.session() as s:
                s.run("CREATE CONSTRAINT player_id_unique IF NOT EXISTS "
                      "FOR (p:Player) REQUIRE p.id IS UNIQUE")
                s.run("CREATE CONSTRAINT character_scope_unique IF NOT EXISTS "
                      "FOR (c:Character) REQUIRE (c.name, c.player_id) IS UNIQUE")
            _constraints_done = True
        except Exception as exc:
            log.warning("Could not ensure Neo4j constraints: %s", exc)
    return _driver


def normalize_relation(relation: str) -> str:
    """Validate a relationship type. Cypher can't parameterise these, so be strict."""
    rel = relation.strip().upper().replace(" ", "_")
    if not _REL_PATTERN.match(rel):
        raise ValueError(f"Invalid relationship type {relation!r}; use UPPERCASE_WITH_UNDERSCORES.")
    if rel not in KNOWN_RELATIONS:
        log.warning("Relationship %s is not in KNOWN_RELATIONS; add it if intentional.", rel)
    return rel


def write_relationship(player_id: str, char: str, relation: str, target: str,
                       value: int, context: str) -> None:
    rel = normalize_relation(relation)
    driver = _get_driver()
    if driver is None:
        return
    cypher = f"""
        MERGE (p:Player {{id: $player_id}})
        MERGE (a:Character {{name: $char,   player_id: $player_id}})
        MERGE (b:Character {{name: $target, player_id: $player_id}})
        MERGE (p)-[:HAS_CHARACTER]->(a)
        MERGE (p)-[:HAS_CHARACTER]->(b)
        MERGE (a)-[r:{rel}]->(b)
        SET r.level      = coalesce(r.level, 0) + $value,
            r.contexts   = (coalesce(r.contexts, []) + $context)[-{MAX_CONTEXTS_PER_EDGE}..],
            r.updated_at = datetime()
    """
    try:
        with driver.session() as s:
            s.run(cypher, player_id=player_id, char=char, target=target,
                  value=int(value), context=context[:300])
    except Exception as exc:
        log.error("Neo4j write failed (player=%s char=%s): %s", player_id, char, exc)


def read_relationships(player_id: str, char: str) -> list[str]:
    driver = _get_driver()
    if driver is None:
        return []
    cypher = """
        MATCH (c:Character {name: $char, player_id: $player_id})-[r]->(o:Character)
        RETURN type(r) AS rel, o.name AS target, r.level AS level, r.contexts AS contexts
        ORDER BY r.level DESC
    """
    try:
        with driver.session() as s:
            return [
                f"{char} {rec['rel']} {rec['target']} "
                f"(level:{rec['level']}) ctx:{(rec['contexts'] or [])[-3:]}"
                for rec in s.run(cypher, player_id=player_id, char=char)
            ]
    except Exception as exc:
        log.error("Neo4j read failed (player=%s char=%s): %s", player_id, char, exc)
        return []


def close() -> None:
    global _driver, _constraints_done
    if _driver is not None:
        _driver.close()
    _driver, _constraints_done = None, False
