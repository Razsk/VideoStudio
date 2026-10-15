// VideoStudio GraphRAG Property Graph Dump
MERGE (n:Character {id: 'CHAR_ELENA_VANCE'}) SET n.name = 'Commander Elena Vance', n.condition = 'nominal', n.description = 'Commander of the Helios Observatory guarding the deep-space telemetry array.';
MERGE (n:Character {id: 'CHAR_MARCUS_KOREN'}) SET n.name = 'Dr. Marcus Koren', n.condition = 'nominal', n.description = 'Chief astrophysicist secretly archiving unauthorized orbital transmissions.';
MERGE (n:Location {id: 'LOC_OBSERVATORY_DOME'}) SET n.name = 'Helios Deep-Space Observatory Dome', n.condition = 'nominal', n.description = 'Primary astrometric tracking dome battered by sub-polar storms.';
MERGE (n:Location {id: 'LOC_SUBLEVEL_RELAY_VAULT'}) SET n.name = 'Sub-Level 4 Cryogenic Relay Vault', n.condition = 'nominal', n.description = 'Deep subterranean vault housing the quantum phase-lock cores.';
MERGE (n:Artifact {id: 'ART_CHRONO_COMPASS'}) SET n.name = 'Brass Chrono-Compass', n.condition = 'nominal', n.description = 'Mechanical decryption key required to unseal the Sub-Level 4 vault.';
MERGE (n:LoreFact {id: 'SECRET_GHOST_TELEMETRY'}) SET n.name = 'The Ghost Telemetry Carrier Wave', n.condition = 'nominal', n.description = 'Decommissioned Beacon 9 is still broadcasting coordinates from beyond the Jovian shadow.';
MATCH (a {id: 'CHAR_ELENA_VANCE'}), (b {id: 'ART_CHRONO_COMPASS'}) MERGE (a)-[r:POSSESSES {valid_from: 0, valid_to: null}]->(b);
MATCH (a {id: 'CHAR_ELENA_VANCE'}), (b {id: 'LOC_OBSERVATORY_DOME'}) MERGE (a)-[r:LOCATED_AT {valid_from: 0, valid_to: 2}]->(b);
MATCH (a {id: 'CHAR_MARCUS_KOREN'}), (b {id: 'SECRET_GHOST_TELEMETRY'}) MERGE (a)-[r:KNOWS_SECRET {valid_from: 0, valid_to: null}]->(b);
MATCH (a {id: 'CHAR_ELENA_VANCE'}), (b {id: 'SECRET_GHOST_TELEMETRY'}) MERGE (a)-[r:KNOWS_SECRET {valid_from: 2, valid_to: null}]->(b);
