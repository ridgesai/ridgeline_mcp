# Ridgeline MCP Server

Lets an MCP-host agent (Claude Code, Cursor, …) interact with the Ridgeline platform.
In practice: you ask your agent to open a Ridgeline issue for a GitHub issue, and this
server automatically pays for it via x402 and hands back the result — no manual
payment step, no separate dashboard.

## Before you start

If you've never set up an MCP server or heard of x402, read this section first —
it explains *why* the steps below exist, not just what to type.

**What is MCP?** The Model Context Protocol lets an AI host (Claude Code, Cursor, …)
call tools it doesn't have built in. You register a server by telling the host how
to launch it — a command, arguments, and environment variables — in the host's
config. The host then starts the server as a subprocess and your agent gains its
tools (here, `create_issue` and `wallet_balance`).

**What is x402?** x402 is an HTTP-based micropayment protocol. When this server
calls the Ridgeline API, the API can reply with HTTP 402 ("Payment Required")
instead of the normal response. This server automatically signs a USDC payment
from your configured wallet and retries the request — that's why it needs a
funded wallet's private key up front, and why there's no manual "pay now" step.

## Tools

- **`create_issue(github_issue_url, branch=None)`** — creates a Ridgeline issue for
  an existing GitHub issue, paying via x402. Returns `issue_id`, `origin`, `paid`,
  `tx_hash`.
  Safe to retry: the API will not double-charge for the same issue. If the issue was already
  processed and you want to retry, you can call the tool again and after paying via X402,
  the issue will be processed again.
  `branch` is optional: pass an existing branch name (e.g. `develop`) to base the
  work on it, or omit it to use the repository's default branch. The branch must
  already exist on the repo — the API rejects unknown branches. Ask your agent
  something like *"open a Ridgeline issue for <url>, based on the develop branch"*.
- **`wallet_balance()`** — reports the wallet's USDC balance, its address, and the
  network.

## Requirements

- Python 3.10 or newer.
- [uv](https://docs.astral.sh/uv/) to install dependencies and run the server.
- The [Ridgeline GitHub App](https://github.com/apps/ridges-ai/installations/new)
  must be installed on the target repository.
- A wallet (its private key) holding USDC. This must be a
  wallet you hold the private key for yourself (e.g. exported from MetaMask or any
  other Ethereum-compatible wallet) — not a hosted or custodial account. The
  server signs payments locally with this key; it is never sent anywhere.

## Setup

1. Clone the repo:

   ```bash
   git clone git@github.com:ridgesai/ridgeline_mcp.git
   ```

2. Install the [Ridgeline GitHub App](https://github.com/apps/ridges-ai/installations/new)
   on the repository you want Ridgeline to open issues/PRs against. This grants
   Ridgeline permission to open issues and pull requests on that repo — without
   it, `create_issue` will fail.

3. Register the server with Claude Code. Pick one:

   > The steps below are for Claude Code specifically, since that's the host with
   > a CLI (`claude mcp add-json`) to walk through. This server itself isn't
   > Claude-specific — it's a standard MCP server, so it works the same way with
   > any MCP-compatible host (Cursor, etc.). For another host, use its equivalent
   > "add an MCP server" config and reuse the same `command`/`args`/`env` block
   > from Option B below.

   **Option A (recommended): the `claude mcp add-json` CLI.** Run this from a
   terminal, replacing the four placeholder values with your own:

   ```bash
   claude mcp add-json ridgeline '{
     "command": "uv",
     "args": ["run", "--directory", "/absolute/path/to/ridgeline_mcp", "ridgeline-mcp"],
     "env": {
       "RIDGELINE_API_URL": "https://product.ridges.ai",
       "WALLET_PRIVATE_KEY": "0xYOUR_64_CHAR_HEX_KEY",
       "X402_NETWORK": "mainnet"
     }
   }'
   ```

   - `/absolute/path/to/ridgeline_mcp` — the full path to the cloned repo on
     your machine (e.g. `/Users/you/code/ridgeline_mcp`), not a relative path.
   - `RIDGELINE_API_URL` — the Ridgeline API's base URL.
   - `WALLET_PRIVATE_KEY` — your funded wallet's private key (see
     [Configuration](#configuration) for the required format).
   - `X402_NETWORK` — `mainnet`.

   This registers the server without you having to hand-edit any JSON files.
   `uv` installs the project's dependencies automatically the first time Claude
   Code launches the server, so there's no separate install step.

   **Option B: edit the config file directly.** If you'd rather edit the file
   by hand (or need project-scoped `.mcp.json`), add this block under
   `mcpServers` — see [Claude Code setup](#claude-code-setup) below for the
   full snippet and notes on the `--directory` flag and key format.

4. Restart or reload Claude Code so it picks up the new server registration.

5. Verify it worked: run `/mcp` inside Claude Code, or `claude mcp list` from a
   shell, and confirm `ridgeline` shows as connected. You can also just ask your
   agent something like "what tools do you have from the ridgeline server?".

## Configuration

These variables go inside the MCP config's `env` block (the one you set in Setup
step 3) — not your shell profile. Claude Code passes them to the server process
when it launches it.

| Variable | Required | Default | Description |
| --- | --- | --- | --- |
| `RIDGELINE_API_URL` | yes | — | Base URL of the Ridgeline API |
| `WALLET_PRIVATE_KEY` | yes | — | Hex private key used to sign payments |
| `X402_NETWORK` | no | `testnet` | `mainnet` or `testnet` |
| `BASE_RPC_URL` | no | public Base RPC | RPC used for balance reads |

## Claude Code setup

Add to your MCP config:

```json
{
  "mcpServers": {
    "ridgeline": {
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "/absolute/path/to/ridgeline_mcp",
        "ridgeline-mcp"
      ],
      "env": {
        "RIDGELINE_API_URL": "https://product.ridges.ai",
        "WALLET_PRIVATE_KEY": "0x...",
        "X402_NETWORK": "mainnet"
      }
    }
  }
}
```

Use `uv run --directory <path>` rather than relying on a `cwd` field: the host may
spawn the server from a different working directory, and `--directory` makes `uv`
resolve this project regardless. `WALLET_PRIVATE_KEY` must be a 32-byte key
(64 hex characters, `0x`-prefixed) — a 20-byte account address will fail to start.

## Troubleshooting

**Server doesn't appear, or the agent has no `ridgeline` tools**
- Restart/reload Claude Code — config changes don't apply to an already-running
  session.
- Check the config JSON is valid (a missing or trailing comma is enough to break
  it).
- Confirm the `--directory` path is absolute and points at the cloned repo.

**`RIDGELINE_API_URL is not set` or `WALLET_PRIVATE_KEY is not set`**
- The variable is missing from the MCP config's `env` block, or was set in your
  shell instead — the server only reads what Claude Code passes it via `env`.

**Server fails to start with a key-format error**
- `WALLET_PRIVATE_KEY` must be `0x` followed by 64 hex characters (32 bytes). A
  wallet *address* (20 bytes, also `0x`-prefixed but shorter) will not work.

**`create_issue` fails with a branch error**
- The branch you passed doesn't exist on the repository — check the exact name
  (branch names are case-sensitive), or omit `branch` to use the default branch.
- If you omitted `branch` and still got this, the repo has no commits yet, so
  there's no default branch to base an issue on. Push a commit first.

**Payments keep failing, or you keep getting HTTP 402 back**
- The wallet is probably unfunded on the network you configured — check with the
  `wallet_balance` tool.
- Confirm `X402_NETWORK` matches where the wallet actually holds USDC (`testnet`
  vs `mainnet`); fund a testnet wallet via the Circle faucet linked in
  [Requirements](#requirements).

## Security

The private key is read from the environment only. It is never accepted as a
tool argument, never logged, and never returned in a tool result — so it does not
enter the agent's context.

This is an stdio MCP server: it must never write to stdout, which carries the
JSON-RPC protocol. Any diagnostic logging goes to stderr.
