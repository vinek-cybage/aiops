#!/bin/bash

# Start Neo4j in the background
/startup/docker-entrypoint.sh neo4j &
NEO4J_PID=$!

DB_USER="${NEO4J_AUTH%%/*}"
DB_PASS="${NEO4J_AUTH##*/}"
SEED=/import/ssh_graph_seed.cypher

echo "[seed] Waiting for Neo4j to be ready..."
until cypher-shell -a "bolt://localhost:7687" -u "$DB_USER" -p "$DB_PASS" "RETURN 1;" > /dev/null 2>&1; do
  sleep 2
done

COUNT=$(cypher-shell -a "bolt://localhost:7687" -u "$DB_USER" -p "$DB_PASS" \
  "MATCH (n:SSHIPAddress) RETURN count(n) AS c;" 2>/dev/null \
  | grep -E '^[0-9]+$' | head -1)

if [ -z "$COUNT" ] || [ "$COUNT" -eq 0 ] 2>/dev/null; then
  echo "[seed] Loading SSH graph..."
  cypher-shell -a "bolt://localhost:7687" -u "$DB_USER" -p "$DB_PASS" --file "$SEED"
  echo "[seed] Done."
else
  echo "[seed] SSH graph already loaded ($COUNT nodes) -- skipping."
fi

wait $NEO4J_PID
