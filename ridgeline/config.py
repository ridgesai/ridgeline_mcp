import os
from dataclasses import dataclass

_NETWORK_CONFIG = {
    "testnet": {
        "chain_id": "eip155:84532",
        "usdc_address": "0x036CbD53842c5426634e7929541eC2318f3dCF7e",
        "rpc_url": "https://sepolia.base.org",
    },
    "mainnet": {
        "chain_id": "eip155:8453",
        "usdc_address": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
        "rpc_url": "https://mainnet.base.org",
    },
}


@dataclass(frozen=True)
class Settings:
    """Resolved configuration for the Ridgeline MCP server.

    Attributes
    ----------
    api_url : str
        Base URL of the Ridgeline API, without a trailing slash.
    wallet_private_key : str
        Hex-encoded private key used to sign x402 payments.
    network : str
        Either 'mainnet' or 'testnet'.
    chain_id : str
        CAIP-2 chain identifier for the selected network.
    usdc_address : str
        USDC contract address on the selected network.
    rpc_url : str
        JSON-RPC endpoint used for on-chain balance reads.
    """

    api_url: str
    wallet_private_key: str
    network: str
    chain_id: str
    usdc_address: str
    rpc_url: str


def load_settings() -> Settings:
    """Read and validate configuration from the environment.

    Returns
    -------
    Settings
        The resolved settings.

    Raises
    ------
    ValueError
        If a required variable is missing or a value is invalid.
    """
    api_url = os.getenv("RIDGELINE_API_URL")
    if not api_url:
        raise ValueError("RIDGELINE_API_URL is not set")

    wallet_private_key = os.getenv("WALLET_PRIVATE_KEY")
    if not wallet_private_key:
        raise ValueError("WALLET_PRIVATE_KEY is not set")

    network = os.getenv("X402_NETWORK", "testnet").lower()
    if network not in _NETWORK_CONFIG:
        raise ValueError("X402_NETWORK must be either 'mainnet' or 'testnet'")

    net = _NETWORK_CONFIG[network]
    return Settings(
        api_url=api_url.rstrip("/"),
        wallet_private_key=wallet_private_key,
        network=network,
        chain_id=net["chain_id"],
        usdc_address=net["usdc_address"],
        rpc_url=os.getenv("BASE_RPC_URL", net["rpc_url"]),
    )
