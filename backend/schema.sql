CREATE TABLE "Usuarios" (
    id BIGSERIAL PRIMARY KEY,
    nome VARCHAR(150) NOT NULL,
    email VARCHAR(255) NOT NULL UNIQUE,
    senha_hash TEXT NOT NULL,
    criado_em TIMESTAMPTZ DEFAULT NOW()
);

-- Tabela de sintomas registrados
CREATE TABLE "Sintomas" (
    id BIGSERIAL PRIMARY KEY,

    usuario_id BIGINT NOT NULL
        REFERENCES "Usuarios"(id)
        ON DELETE CASCADE,

    tipo VARCHAR(100) NOT NULL,
    subtipo VARCHAR(100),
    descricao TEXT,

    inicio TIMESTAMPTZ NOT NULL,
    fim TIMESTAMPTZ,

    criado_em TIMESTAMPTZ DEFAULT NOW(),
    atualizado_em TIMESTAMPTZ DEFAULT NOW()
);

-- Índice para buscas por usuário + data
CREATE INDEX "IX_Sintomas_UsuarioData"
    ON "Sintomas" (usuario_id, inicio);

-- ── IA ───────────────────────────────────────────────────────────────────────
-- (o app também cria isso sozinho em init_db; fica aqui como referência)
ALTER TABLE "Usuarios" ADD COLUMN IF NOT EXISTS ia_consentimento_em TIMESTAMP;

CREATE TABLE IF NOT EXISTS "IaUso" (
    usuario_id BIGINT NOT NULL REFERENCES "Usuarios"(id) ON DELETE CASCADE,
    dia DATE NOT NULL,
    recurso TEXT NOT NULL,
    total INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (usuario_id, dia, recurso)
);

