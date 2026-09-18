from ridgeline.config import Settings
from ridgeline.x402_client import PaidResponse, PayingClient


class ToolError(Exception):
    """An error whose message is intended to be read by the calling agent."""


def _detail(response: PaidResponse, fallback: str) -> str:
    """Extract the API's error detail, falling back to a default message.

    Parameters
    ----------
    response : PaidResponse
        The response to read.
    fallback : str
        Message to use when no detail is present.

    Returns
    -------
    str
        The error detail.
    """
    detail = response.body.get("detail")
    return detail if isinstance(detail, str) and detail else fallback


async def create_issue(
    client: PayingClient,
    github_issue_url: str,
    branch: str | None = None,
    retry: bool = False,
) -> dict:
    """Create a Ridgeline issue for a GitHub issue, paying via x402 if required.

    Parameters
    ----------
    client : PayingClient
        Client used to call the Ridgeline API.
    github_issue_url : str
        Full URL of the GitHub issue, e.g.
        'https://github.com/owner/repo/issues/123'.
    branch : str or None, optional
        Branch to base the work on. Defaults to the repository's default
        branch when omitted.
    retry : bool, optional
        Request a paid re-run of an issue that already exists. Ignored when
        the issue does not exist yet. Left false, an existing issue is never
        charged for again.

    Returns
    -------
    dict
        Keys: issue_id, origin, outcome, retry_available, paid, tx_hash.

    Raises
    ------
    ToolError
        If the issue could not be created, with an agent-readable reason.
    """
    payload: dict = {"github_issue_url": github_issue_url, "retry": retry}
    if branch:
        payload["branch"] = branch

    response = await client.post_with_payment("/v1/issues", payload)

    if response.status_code == 200:
        return {
            "issue_id": response.body.get("issue_id"),
            "origin": response.body.get("origin"),
            "outcome": response.body.get("outcome"),
            "retry_available": bool(response.body.get("retry_available", False)),
            "paid": response.paid,
            "tx_hash": response.tx_hash,
        }

    if response.status_code == 402:
        reason = _detail(
            response, response.body.get("error", "payment was not accepted")
        )
        raise ToolError(
            f"Wallet could not pay for this issue: {reason}. "
            "Check the wallet's funds with the wallet_balance tool."
        )

    if response.status_code == 404:
        raise ToolError(_detail(response, "Repository or issue not found."))

    if response.status_code == 422:
        raise ToolError(_detail(response, "Invalid GitHub issue URL or branch."))

    if response.status_code == 429:
        raise ToolError("Rate limited by the Ridgeline API. Wait a minute and retry.")

    if response.status_code >= 500 and response.paid:
        tx_note = (
            f"transaction hash {response.tx_hash}"
            if response.tx_hash
            else "the repository and issue number below (the API does not "
            "return a transaction hash for this failure; it is recorded "
            "server-side)"
        )
        raise ToolError(
            f"Payment settled but issue creation failed for {github_issue_url}: "
            f"{_detail(response, 'server error')}. Contact support with {tx_note}. "
            "Retrying is safe and will not double-charge."
        )

    raise ToolError(
        f"Ridgeline API returned {response.status_code}: "
        f"{_detail(response, 'unexpected error')}"
    )


async def wallet_balance(client: PayingClient, settings: Settings) -> dict:
    """Report the configured wallet's USDC balance and spending capacity.

    Parameters
    ----------
    client : PayingClient
        Client whose wallet is inspected.
    settings : Settings
        Resolved configuration, used for the network name.

    Returns
    -------
    dict
        Keys: address, usdc_balance, network.

    Raises
    ------
    ToolError
        If the wallet balance could not be checked because the RPC call
        failed, with an agent-readable reason.
    """
    try:
        balance = await client.usdc_balance()
    except RuntimeError as e:
        raise ToolError(
            "Wallet balance could not be checked: "
            f"{e}. The RPC endpoint may be unreachable or misconfigured. "
            "Retrying may help; if it keeps failing, check the BASE_RPC_URL setting."
        ) from e
    return {
        "address": client.signer.address,
        "usdc_balance": balance,
        "network": settings.network,
    }
