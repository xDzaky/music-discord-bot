# Railway Deploy for Private Server MVP

This repo can now run from environment variables, so `settings.json` is optional in cloud deployments.

## Services

Create 4 services:

1. `vocard-bot`
2. `lavalink`
3. `spotify-tokener`
4. MongoDB managed service of your choice

## 1. Deploy the bot service

- Root: `Vocard`
- Build: `[Dockerfile](/home/dzaky/Desktop/coding-project/music-discord-bot/Vocard/Dockerfile)`
- Required environment variables:
  - `TOKEN`
  - `MONGODB_URL`
  - `MONGODB_NAME`
  - `LAVALINK_HOST`
  - `LAVALINK_PORT`
  - `LAVALINK_PASSWORD`
  - `LAVALINK_SECURE`
- Optional:
  - `CLIENT_ID`
  - `IPC_ENABLE=false`

## 2. Deploy the Lavalink service

- Dockerfile path: `[Dockerfile-lavalink](/home/dzaky/Desktop/coding-project/music-discord-bot/Vocard/lavalink/Dockerfile-lavalink)`
- Config file: `[application.yml](/home/dzaky/Desktop/coding-project/music-discord-bot/Vocard/lavalink/application.yml)`
- Required environment variables:
  - `SERVER_PORT=2333`
  - `LAVALINK_SERVER_PASSWORD`
  - `SPOTIFY_CLIENT_ID`
  - `SPOTIFY_CLIENT_SECRET`
  - `SPOTIFY_TOKEN_ENDPOINT`
- Recommended:
  - `LOG_LEVEL_ROOT=INFO`
  - `LOG_LEVEL_LAVALINK=INFO`
  - `LAVALINK_REQUEST_LOGGING=true`

Point `SPOTIFY_TOKEN_ENDPOINT` at the cloud provider's internal URL for the `spotify-tokener` service. Do not keep the default Docker hostname unless your platform resolves it privately.

## 3. Deploy the spotify-tokener service

- Image: `ghcr.io/topi314/spotify-tokener:master`
- Required environment variables:
  - `SPOTIFY_TOKENER_ADDR=0.0.0.0:49152`

## 4. Connect MongoDB

- Use a managed MongoDB URI in `MONGODB_URL`
- Set the database name in `MONGODB_NAME`
- The bot will refuse to start without both values

## Discord Invite Permissions

Use at least:

- `View Channels`
- `Send Messages`
- `Embed Links`
- `Connect`
- `Speak`
- `Use Slash Commands`
- `Read Message History`

## Smoke Test

After deploy, test in one private Discord server:

1. `/play https://www.youtube.com/watch?v=ZSvYVSsxIsc`
2. `/play <spotify track url>`
3. `/play <spotify playlist url>`
4. `/skip`
5. `/stop`
6. `/search query:never gonna give you up platform:spotify`

If YouTube works but Spotify does not, check `SPOTIFY_CLIENT_ID`, `SPOTIFY_CLIENT_SECRET`, and the internal `SPOTIFY_TOKEN_ENDPOINT` first.
