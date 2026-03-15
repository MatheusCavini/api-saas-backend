-- Sample entity table for Falcon API boilerplate
CREATE TABLE IF NOT EXISTS sample_entity (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(255) NOT NULL,
    email       VARCHAR(255) NOT NULL,
    description TEXT,
    created_at  TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at  TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_sample_entity_email ON sample_entity (email);
CREATE INDEX IF NOT EXISTS idx_sample_entity_created_at ON sample_entity (created_at);
