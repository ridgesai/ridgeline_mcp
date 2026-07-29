# Ridgeline MCP Server

Lets an MCP-host agent (Claude Code, Cursor, …) interact with the Ridgeline platform.

## Tools

- **`create_issue(github_issue_url)`** — creates a Ridgeline issue for an existing
  GitHub issue, paying via x402. Returns `issue_id`, `origin`, `paid`, `tx_hash`.
  Safe to retry: the API will not double-charge for the same issue. If the issue was already
  processed and you want to retry, you can call the tool again and after paying via X402,
  the issue will be processed again
- **`wallet_balance()`** — reports the wallet's USDC balance, its address, and the
  network.

## Requirements

- Python 3.10 or newer.
- [uv](https://docs.astral.sh/uv/) to install dependencies and run the server.
- The [Ridgeline GitHub App](https://github.com/apps/ridges-ai/installations/new)
  must be installed on the target repository.
- A wallet (its private key) holding USDC on the configured network (Base or
  Base Sepolia). For testnet, fund the wallet with Base Sepolia USDC from a
  faucet such as [faucet.circle.com](https://faucet.circle.com/).

## Setup

1. Clone the repo:

   ```bash
   git clone git@github.com:ridgesai/ridgeline_mcp.git
   ```

2. Install the [Ridgeline GitHub App](https://github.com/apps/ridges-ai/installations/new)
   on the repository you want Ridgeline to open issues/PRs against.

3. Add the server to your MCP host's config with the required environment
   variables (see [Configuration](#configuration) and
   [Claude Code setup](#claude-code-setup) below). `uv` installs dependencies
   automatically the first time the host launches the server, so there's no
   separate install step.

## Configuration

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
        "RIDGELINE_API_URL": "https://api.ridgeline.example",
        "WALLET_PRIVATE_KEY": "0x...",
        "X402_NETWORK": "testnet"
      }
    }
  }
}
```

Use `uv run --directory <path>` rather than relying on a `cwd` field: the host may
spawn the server from a different working directory, and `--directory` makes `uv`
resolve this project regardless. `WALLET_PRIVATE_KEY` must be a 32-byte key
(64 hex characters, `0x`-prefixed) — a 20-byte account address will fail to start.

## Security

The private key is read from the environment only. It is never accepted as a
tool argument, never logged, and never returned in a tool result — so it does not
enter the agent's context.

This is an stdio MCP server: it must never write to stdout, which carries the
JSON-RPC protocol. Any diagnostic logging goes to stderr.
