from mcp.server.fastmcp import FastMCP

from ridgeline import tools
from ridgeline.config import load_settings
from ridgeline.x402_client import PayingClient


def build_server() -> FastMCP:
    """Build the Ridgeline MCP server with its tools registered.

    Returns
    -------
    FastMCP
        The configured server, ready to run over a transport.
    """
    settings = load_settings()
    client = PayingClient(settings)
    server = FastMCP("Ridgeline")

    @server.tool()
    async def create_issue(github_issue_url: str, branch: str | None = None) -> dict:
        """Create a Ridgeline issue from a GitHub issue URL, paying via x402.

        Ridgeline's AI agents will attempt to solve the issue and open a pull
        request. This tool spends USDC from the configured wallet. Calling it
        twice for the same issue is safe and will not double-charge.

        Parameters
        ----------
        github_issue_url : str
            Full URL of the GitHub issue, e.g.
            'https://github.com/owner/repo/issues/123'.
        branch : str or None, optional
            Existing branch the work should be based on, e.g. 'develop'. Omit
            to use the repository's default branch.

        Returns
        -------
        dict
            Keys: issue_id, origin, paid, tx_hash.
        """
        try:
            return await tools.create_issue(client, github_issue_url, branch)
        except tools.ToolError as e:
            raise ValueError(str(e)) from e

    @server.tool()
    async def wallet_balance() -> dict:
        """Report the USDC balance of the wallet used to pay for issues.

        Returns
        -------
        dict
            Keys: address, usdc_balance, network.
        """
        try:
            return await tools.wallet_balance(client, settings)
        except tools.ToolError as e:
            raise ValueError(str(e)) from e

    return server


def main() -> None:
    """Run the MCP server over stdio."""
    build_server().run()


if __name__ == "__main__":
    main()
