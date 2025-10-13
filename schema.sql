-- Drop tables in reverse order of dependency
DROP TABLE IF EXISTS audit_logs;
DROP TABLE IF EXISTS winners;
DROP TABLE IF EXISTS selections;
DROP TABLE IF EXISTS rounds;

-- Table to manage each lottery round
CREATE TABLE rounds (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL, -- e.g., "100 Birr Round - Oct 2025"
    price INTEGER NOT NULL,
    grid_size INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'open', -- 'open', 'closed', 'completed'
    creation_date TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Table to track every number selection for every round
CREATE TABLE selections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    round_id INTEGER NOT NULL,
    number INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending', -- 'pending', 'confirmed'
    user_id TEXT,
    user_name TEXT,
    selection_date TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (round_id) REFERENCES rounds (id),
    UNIQUE (round_id, number) -- Ensures a number can only be selected once per round
);

-- Table to store multiple winners for each round's draw
CREATE TABLE winners (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    round_id INTEGER NOT NULL,
    draw_date TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    winning_number INTEGER NOT NULL,
    user_id TEXT NOT NULL,
    user_name TEXT NOT NULL,
    prize_tier INTEGER NOT NULL, -- 1 for 1st, 2 for 2nd, 3 for 3rd
    prize_amount REAL NOT NULL,
    FOREIGN KEY (round_id) REFERENCES rounds (id)
);

-- Table for detailed audit logging
CREATE TABLE audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    log_date TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    actor TEXT NOT NULL, -- e.g., 'SYSTEM', 'ADMIN', 'PLAYER_JohnDoe'
    action TEXT NOT NULL, -- e.g., 'CREATE_ROUND', 'APPROVE_SELECTION', 'RUN_DRAW'
    details TEXT -- e.g., 'Approved number 45 for user JohnDoe in round 3'
);