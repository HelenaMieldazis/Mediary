-- Esquema do Mediary para MySQL 8 (InnoDB, utf8mb4).
-- O app cria tudo isso sozinho no init_db() ao subir; este arquivo fica como
-- referência e para criar o banco manualmente, se preferir:
--   mysql -h HOST -u USUARIO -p NOME_DO_BANCO < schema.sql
--
-- Os nomes das tabelas são sensíveis a maiúsculas no MySQL em Linux (padrão da
-- AWS RDS): use exatamente Usuarios, Sintomas e IaUso.

CREATE TABLE IF NOT EXISTS Usuarios (
    id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    nome VARCHAR(255) NOT NULL,
    email VARCHAR(255) NOT NULL,
    senha_hash VARCHAR(255) NOT NULL,
    criado_em DATETIME DEFAULT CURRENT_TIMESTAMP,
    -- NULL = não consentiu o uso da IA (LGPD). Preenchido com a data do aceite.
    ia_consentimento_em DATETIME NULL,
    UNIQUE KEY uq_usuarios_email (email)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Sintomas registrados (sempre consultados filtrando por usuario_id)
CREATE TABLE IF NOT EXISTS Sintomas (
    id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    usuario_id INT NOT NULL,
    tipo VARCHAR(100) NOT NULL,
    subtipo VARCHAR(100) NULL,
    descricao TEXT NULL,
    inicio DATETIME NOT NULL,
    fim DATETIME NULL,
    criado_em DATETIME DEFAULT CURRENT_TIMESTAMP,
    atualizado_em DATETIME DEFAULT CURRENT_TIMESTAMP,
    KEY ix_sintomas_usuario_inicio (usuario_id, inicio),
    CONSTRAINT fk_sintomas_usuario FOREIGN KEY (usuario_id)
        REFERENCES Usuarios(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ── IA ───────────────────────────────────────────────────────────────────────
-- Contador diário de uso da IA por usuário (não guarda conteúdo da conversa).
-- "dia" é a data em America/Sao_Paulo, calculada pelo backend.
CREATE TABLE IF NOT EXISTS IaUso (
    usuario_id INT NOT NULL,
    dia DATE NOT NULL,
    recurso VARCHAR(40) NOT NULL,
    total INT NOT NULL DEFAULT 0,
    PRIMARY KEY (usuario_id, dia, recurso),
    CONSTRAINT fk_iauso_usuario FOREIGN KEY (usuario_id)
        REFERENCES Usuarios(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
