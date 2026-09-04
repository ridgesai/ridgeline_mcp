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
    async def create_issue(
        github_issue_url: str,
        branch: str | None = None,
        retry: bool = False,
    ) -> dict:
        """Create a Ridgeline issue from a GitHub issue URL, paying via x402.

        Ridgeline's AI agents will attempt to solve the issue and open a pull
        request. This tool spends USDC from the configured wallet. Calling it
        again for an issue that already exists costs nothing unless you pass
        retry=true, so repeating a call is always safe.

        Parameters
        ----------
        github_issue_url : str
            Full URL of the GitHub issue, e.g.
            'https://github.com/owner/repo/issues/123'.
        branch : str or None, optional
            Existing branch the work should be based on, e.g. 'develop'. Omit
            to use the repository's default branch.
        retry : bool, optional
            Pay for a fresh re-run of an issue Ridgeline has already worked
            on. Only set this when the user has explicitly asked to re-run the
            issue, as it charges the wallet again. Has no effect on an issue
            that does not exist yet.

        Returns
        -------
        dict
            Keys: issue_id, origin, outcome, retry_available, paid, tx_hash.
            When outcome is 'existing' and retry_available is true, the issue
            can be re-run by calling again with retry=true, which costs money.
        """
        try:
            return await tools.create_issue(client, github_issue_url, branch, retry)
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
