from dataclasses import dataclass
from typing import Any

import httpx
from eth_account import Account
from x402.client import x402Client
from x402.http import x402HTTPClient
from x402.http.constants import (
    PAYMENT_RESPONSE_HEADER,
    PAYMENT_SIGNATURE_HEADER,  # noqa: F401
)
from x402.http.utils import decode_payment_response_header
from x402.mechanisms.evm.exact import register_exact_evm_client
from x402.mechanisms.evm.types import TypedDataDomain, TypedDataField

from ridgeline.config import Settings

_BALANCE_OF_SELECTOR = "0x70a08231"
_USDC_DECIMALS = 6


class EthAccountSigner:
    """Adapts an eth_account key to the x402 ClientEvmSigner protocol.

    The x402 protocol calls ``sign_typed_data`` positionally and expects raw
    signature bytes, while ``eth_account`` uses keyword arguments and returns a
    ``SignedMessage``. This class bridges the two.
    """

    def __init__(self, private_key: str) -> None:
        """Create a signer from a hex-encoded private key.

        Parameters
        ----------
        private_key : str
            Hex-encoded private key, with or without a '0x' prefix.
        """
        self._account = Account.from_key(private_key)

    @property
    def address(self) -> str:
        """The signer's checksummed Ethereum address.

        Returns
        -------
        str
            Checksummed address (0x...).
        """
        return self._account.address

    def sign_typed_data(
        self,
        domain: dict[str, Any],
        types: dict[str, list[dict[str, str]]],
        primary_type: str,
        message: dict[str, Any],
    ) -> bytes:
        """Sign EIP-712 typed data.

        Parameters
        ----------
        domain : dict[str, Any] or TypedDataDomain
            EIP-712 domain separator. The x402 library may pass either a
            plain dict or its own ``TypedDataDomain`` dataclass, which is
            not a mapping and cannot be coerced with ``dict()``.
        types : dict[str, list[dict[str, str] or TypedDataField]]
            Type definitions. Each field may be a plain dict or the
            library's ``TypedDataField`` dataclass.
        primary_type : str
            Primary type name. Unused: eth_account infers it from `types`.
        message : dict[str, Any]
            Message data to sign.

        Returns
        -------
        bytes
            65-byte ECDSA signature.
        """
        if isinstance(domain, TypedDataDomain):
            domain_dict: dict[str, Any] = {
                "name": domain.name,
                "version": domain.version,
                "chainId": domain.chain_id,
                "verifyingContract": domain.verifying_contract,
            }
        else:
            domain_dict = dict(domain)

        types_dict: dict[str, list[dict[str, str]]] = {}
        for type_name, fields in types.items():
            types_dict[type_name] = [
                {"name": f.name, "type": f.type}
                if isinstance(f, TypedDataField)
                else dict(f)
                for f in fields
            ]

        signed = self._account.sign_typed_data(
            domain_data=domain_dict,
            message_types=types_dict,
            message_data=dict(message),
        )
        return bytes(signed.signature)


@dataclass
class PaidResponse:
    """Result of an HTTP call that may have involved an x402 payment.

    Attributes
    ----------
    status_code : int
        Final HTTP status code, after any payment retry.
    body : dict
        Decoded JSON body, or an empty dict if the body was not JSON.
    paid : bool
        True if this call settled a payment.
    tx_hash : str | None
        On-chain transaction hash, when a payment settled.
    """

    status_code: int
    body: dict
    paid: bool
    tx_hash: str | None


def _json_or_empty(response: httpx.Response) -> dict:
    """Decode a JSON body, tolerating non-JSON responses.

    Parameters
    ----------
    response : httpx.Response
        The response to decode.

    Returns
    -------
    dict
        Parsed JSON object, or an empty dict.
    """
    try:
        body = response.json()
    except Exception:
        return {}
    return body if isinstance(body, dict) else {}


class PayingClient:
    """HTTP client that transparently satisfies x402 payment challenges.

    Wraps an ``httpx.AsyncClient``. On a 402 response it signs a payment with the
    configured wallet and retries the request once.
    """

    def __init__(
        self, settings: Settings, http: httpx.AsyncClient | None = None
    ) -> None:
        """Create a paying client.

        Parameters
        ----------
        settings : Settings
            Resolved configuration, including the wallet key and network.
        http : httpx.AsyncClient | None, optional
            HTTP client to use. A new one is created if omitted.
        """
        self._settings = settings
        self._http = http or httpx.AsyncClient(timeout=60.0)
        self.signer = EthAccountSigner(settings.wallet_private_key)

        client = x402Client()
        register_exact_evm_client(client, self.signer, networks=settings.chain_id)
        self._x402 = x402HTTPClient(client)

    async def post_with_payment(self, path: str, json: dict) -> PaidResponse:
        """POST to the Ridgeline API, paying an x402 challenge if one is returned.

        Parameters
        ----------
        path : str
            Path on the Ridgeline API, e.g. '/v1/issues'.
        json : dict
            JSON request body.

        Returns
        -------
        PaidResponse
            The final response, and whether a payment settled.
        """
        url = f"{self._settings.api_url}{path}"
        response = await self._http.post(url, json=json)

        if response.status_code != 402:
            return PaidResponse(
                status_code=response.status_code,
                body=_json_or_empty(response),
                paid=False,
                tx_hash=None,
            )

        payment_headers, _ = await self._x402.handle_402_response(
            dict(response.headers), response.content
        )
        retried = await self._http.post(url, json=json, headers=payment_headers)

        if retried.status_code == 402:
            return PaidResponse(
                status_code=402,
                body=_json_or_empty(retried),
                paid=False,
                tx_hash=None,
            )

        tx_hash = None
        settle_header = retried.headers.get(PAYMENT_RESPONSE_HEADER)
        if settle_header:
            try:
                tx_hash = decode_payment_response_header(settle_header).transaction
            except Exception:
                tx_hash = None

        return PaidResponse(
            status_code=retried.status_code,
            body=_json_or_empty(retried),
            paid=True,
            tx_hash=tx_hash,
        )

    async def usdc_balance(self) -> float:
        """Read the wallet's USDC balance on the configured network.

        Returns
        -------
        float
            Balance in USDC, converted from the contract's 6-decimal units.

        Raises
        ------
        RuntimeError
            If the RPC request fails at the transport level (connection error,
            timeout, or a non-JSON response body), or if the RPC node returns
            a JSON-RPC error object instead of a result. In both cases the
            balance could not be determined and must not be reported as 0.0.
        """
        padded_address = self.signer.address[2:].lower().rjust(64, "0")
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "eth_call",
            "params": [
                {
                    "to": self._settings.usdc_address,
                    "data": f"{_BALANCE_OF_SELECTOR}{padded_address}",
                },
                "latest",
            ],
        }
        try:
            response = await self._http.post(self._settings.rpc_url, json=payload)
            body = response.json()
        except Exception as e:
            raise RuntimeError(
                "Failed to read USDC balance: the RPC request to "
                f"{self._settings.rpc_url} did not complete "
                f"(wallet={self.signer.address}). Underlying error: {e}"
            ) from e

        if "error" in body:
            rpc_error = body["error"]
            message = (
                rpc_error.get("message", rpc_error)
                if isinstance(rpc_error, dict)
                else rpc_error
            )
            raise RuntimeError(
                "Failed to read USDC balance: the RPC node returned an error "
                f"for wallet {self.signer.address} instead of a balance. "
                f"RPC error: {message}"
            )

        result = body.get("result", "0x")
        if result in ("0x", "", None):
            return 0.0
        return int(result, 16) / (10**_USDC_DECIMALS)
