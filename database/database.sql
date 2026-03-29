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


-- Habilita a geração de UUIDs nativa do PostgreSQL
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ==========================================
-- 1. TABELAS DE DOMÍNIO / ENUMERADORES
-- ==========================================

CREATE TABLE roles (
    id SERIAL PRIMARY KEY,
    role_key UUID UNIQUE NOT NULL DEFAULT uuid_generate_v4(),
    name VARCHAR(50) UNIQUE NOT NULL, -- 'owner', 'admin', 'member', 'viewer'
    description VARCHAR(255),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Inserindo os cargos padrão automaticamente
INSERT INTO roles (name, description) VALUES 
('owner', 'Workspace owner. Inherits all administrator permissions, plus access to billing, invoicing, and subscription management.'),
('admin', 'Workspace administrator. Inherits all member permissions, plus the ability to manage API keys and invite or remove teammates.'),
('member', 'Standard member. Read-only access to view API keys, usage metrics, and system logs.');

-- ==========================================
-- 2. TABELAS INDEPENDENTES (Sem Foreign Keys)
-- ==========================================

CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    user_key UUID UNIQUE NOT NULL DEFAULT uuid_generate_v4(),
    username VARCHAR(255) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_users_email ON users(email);
-- Índice para buscas rápidas da API usando o UUID público
CREATE INDEX idx_users_user_key ON users(user_key);

CREATE TABLE workspaces (
    id SERIAL PRIMARY KEY,
    workspace_key UUID UNIQUE NOT NULL DEFAULT uuid_generate_v4(),
    name VARCHAR(255) NOT NULL,
    stripe_customer_id VARCHAR(255) UNIQUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    deactivated_on TIMESTAMP WITH TIME ZONE
);
CREATE INDEX idx_workspaces_workspace_key ON workspaces(workspace_key);

CREATE TABLE plans (
    id SERIAL PRIMARY KEY,
    plan_key UUID UNIQUE NOT NULL DEFAULT uuid_generate_v4(),
    stripe_price_id VARCHAR(255) UNIQUE NOT NULL,
    name VARCHAR(100) NOT NULL,
    description TEXT NOT NULL,
    price_cents INT NOT NULL,
    currency VARCHAR(3) NOT NULL DEFAULT 'USD',
    rate_limit_rpm INT NOT NULL,
    features JSONB NOT NULL DEFAULT '[]'::jsonb,
    monthly_quota INT NOT NULL DEFAULT 0,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE services (
    id SERIAL PRIMARY KEY,
    service_key UUID UNIQUE NOT NULL DEFAULT uuid_generate_v4(),
    slug VARCHAR(100) UNIQUE NOT NULL,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    credit_cost INT NOT NULL DEFAULT 1,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE invitation_status (
    id SERIAL PRIMARY KEY,
    status_key UUID UNIQUE NOT NULL DEFAULT uuid_generate_v4(),
    enum VARCHAR(50) UNIQUE NOT NULL, 
    description VARCHAR(255),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO invitation_status (enum, description) VALUES 
('pending', 'The invitation was created and is waiting for user acceptation.'),
('accepted', 'Invited user accepted invitation and joined workspace.'),
('expired', 'Invitation period has expired. Invited user can no longer join workspace using this invitation.'),
('refused', 'Invited user refused invitation and did not join workspace.'),
('revoked', 'Host user revoked this invitation.');

-- ==========================================
-- 3. TABELAS DEPENDENTES (Com Foreign Keys)
-- ==========================================
-- IMPORTANTE: Todas as Foreign Keys agora apontam para BIGINT

CREATE TABLE invitations (
    id SERIAL PRIMARY KEY,
    invitation_key UUID UNIQUE NOT NULL DEFAULT uuid_generate_v4(),
    workspace_id INT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    invited_email VARCHAR(255) NOT NULL,
    host_user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role_id INT NOT NULL REFERENCES roles(id) ON DELETE RESTRICT, 
    status_id INT NOT NULL REFERENCES invitation_status(id) ON DELETE RESTRICT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL
);

CREATE TABLE workspace_members (
    workspace_id INT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role_id INT NOT NULL REFERENCES roles(id) ON DELETE RESTRICT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (workspace_id, user_id)
);

CREATE TABLE subscriptions (
    id SERIAL PRIMARY KEY,
    subscription_key UUID UNIQUE NOT NULL DEFAULT uuid_generate_v4(),
    workspace_id INT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    plan_id INT NOT NULL REFERENCES plans(id) ON DELETE RESTRICT,
    stripe_sub_id VARCHAR(255) UNIQUE NOT NULL,
    status VARCHAR(50) NOT NULL, -- active, past_due, canceled
    current_period_end TIMESTAMP WITH TIME ZONE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_subs_workspace ON subscriptions(workspace_id);

CREATE TABLE api_keys (
    id BIGSERIAL PRIMARY KEY,
    api_key_key UUID UNIQUE NOT NULL DEFAULT uuid_generate_v4(),
    workspace_id BIGINT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL, -- Para o cliente identificar no dashboard
    key_prefix VARCHAR(50) NOT NULL, -- Usado para exibir na tela (ex: sk_live_a1b2...)
    key_hash VARCHAR(255) UNIQUE NOT NULL, -- Onde faremos a busca real com o passlib
    status VARCHAR(50) NOT NULL DEFAULT 'active', -- active, revoked, suspended
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_api_keys_hash ON api_keys(key_hash);
CREATE INDEX idx_api_keys_workspace ON api_keys(workspace_id);
CREATE INDEX idx_api_keys_api_key_key ON api_keys(api_key_key);

CREATE TABLE usage (
    id BIGSERIAL PRIMARY KEY,
    usage_key UUID UNIQUE NOT NULL DEFAULT uuid_generate_v4(),
    workspace_id BIGINT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    api_key_id BIGINT REFERENCES api_keys(id) ON DELETE SET NULL, 
    service_id BIGINT NOT NULL REFERENCES services(id) ON DELETE RESTRICT,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    status_code INT NOT NULL,
    latency_ms INT NOT NULL,
    credit_cost INT NOT NULL
);
CREATE INDEX idx_usage_workspace_time ON usage(workspace_id, timestamp);
