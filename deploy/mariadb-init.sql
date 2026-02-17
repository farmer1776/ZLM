-- Ensure database exists with utf8mb4 charset
CREATE DATABASE IF NOT EXISTS zimbra_lifecycle
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

-- Grant privileges to the application user
-- Password is managed via podman secrets / environment
GRANT ALL PRIVILEGES ON zimbra_lifecycle.* TO 'zlm'@'%';
FLUSH PRIVILEGES;
