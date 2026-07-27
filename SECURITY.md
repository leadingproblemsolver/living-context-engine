# Security

Living Context Engine may contain sensitive project decisions, blockers, paths, and unresolved risks. Symlink inputs are rejected and stored source paths remain relative. Restrict filesystem permissions on `data/`, maintain encrypted backups where appropriate, and delete obsolete projects through the explicit confirmation-gated CLI command.

The HTTP API binds safely to loopback without credentials. Non-loopback binding requires `LCE_API_TOKEN`; bearer comparison is constant-time. Browser CORS is disabled unless one exact `LCE_CORS_ORIGIN` is configured, and preflight requests from other origins are rejected. Use TLS and organizational access control at the reverse proxy.

Report vulnerabilities privately through the repository security-advisory mechanism.
