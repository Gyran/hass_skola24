# Skola24

Vårdnadshavare mot Skola24. Kräver Home Assistant 2026.11.1.

`custom_components/skola24/` är det Marketplace installerar. En device per barn. Tre sensorer: meddelande, ordinarie tider, undantagstider. Servicen `skola24.set_temporary_change_message` tar den devicen, ett meddelande, ett datum och `overwrite`. Tomt datum är idag, Europe/Stockholm. Klockslag rörs inte. `overwrite` är av som standard: en lapp som redan finns den dagen lämnas kvar. Ingen knapp och inget standardmeddelande i integrationen. Automationen skickar texten.

## HASS

Inloggning ligger i config entry, inte i git. Meddelandetexten bor i automationen.

<!-- ha-marketplace:exclude-start -->

[![Open your Home Assistant instance and start setting up a new integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=skola24)

`server.py` är stdio-MCP för Cursor. Samma klient. Barn, schema, läs och skriv dagens ändring.

## Lokal MCP

```bash
uv sync
cp .env.example .env
```

`.env` har `USERNAME` och `PASSWORD`. Committa den inte. Cookie-jar hamnar i `data/session.json`.

```json
"skola24": {
  "command": "/Users/gyran/projects/hass_skola24/bin/mcp"
}
```

## Test

```bash
uv run pytest
```

<!-- ha-marketplace:exclude-end -->
