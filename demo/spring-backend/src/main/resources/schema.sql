CREATE TABLE IF NOT EXISTS users (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(100) NOT NULL UNIQUE,
    email VARCHAR(255) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

INSERT IGNORE INTO users (id, username, email, password_hash)
VALUES (1, 'alice', 'alice@example.com', '$2a$10$dummy_hash');
INSERT IGNORE INTO users (id, username, email, password_hash)
VALUES (2, 'bob', 'bob@example.com', '$2a$10$dummy_hash');
