# Infrastructure

Local infrastructure is defined in `docker-compose.yml` and started by
`task infra` or `task dev`.

- Postgres: `localhost:${APP_DATABASE__HOST_PORT:-5433}`
- Keycloak: `http://localhost:${APP_KEYCLOAK__PORT:-8080}`
- Traefik dashboard: `http://localhost:${APP_TRAEFIK__DASHBOARD_PORT:-8089}`
- Dozzle logs: `http://localhost:${APP_DOZZLE__HOST_PORT:-8888}`

Keycloak imports `config/keycloak/realm-export.json` on startup. Redis is not
part of this template.
