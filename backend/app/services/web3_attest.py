"""Optional Web3 integrity layer: writes a credential's non-sensitive hash to the
CredentialAttestation contract on Polygon Amoy (testnet), revokes it when the credential ends,
and reads its on-chain status for the verification page.

Turned OFF unless WEB3_RPC_URL, WEB3_PRIVATE_KEY and WEB3_CONTRACT_ADDRESS are set.
Use a TESTNET-ONLY wallet. The private key lives only in backend/.env (never GitHub, never frontend).
Any blockchain error is caught: the credential flow never breaks because the chain is slow or down.
"""
import json
from pathlib import Path

from .. import config

_ABI = json.loads((Path(__file__).parent / "attestation_abi.json").read_text())
_w3 = None          # tests can inject a Web3 instance via set_web3()


def enabled() -> bool:
    return bool(config.WEB3_CONTRACT_ADDRESS and (_w3 is not None or
                                                  (config.WEB3_RPC_URL and config.WEB3_PRIVATE_KEY)))


def set_web3(w3, account=None):
    """For tests/local chains: use an existing Web3 instance (and optionally an unlocked account)."""
    global _w3, _test_account
    _w3, _test_account = w3, account


_test_account = None


def _web3():
    global _w3
    if _w3 is None:
        from web3 import Web3
        _w3 = Web3(Web3.HTTPProvider(config.WEB3_RPC_URL, request_kwargs={"timeout": 15}))
        # Polygon is a proof-of-authority style chain: its block headers carry extra data that web3.py
        # rejects unless this middleware is added (error: "ExtraDataLengthError ... POA chain").
        from web3.middleware import ExtraDataToPOAMiddleware
        _w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
    return _w3


def _contract():
    w3 = _web3()
    return w3.eth.contract(address=w3.to_checksum_address(config.WEB3_CONTRACT_ADDRESS), abi=_ABI)


def _send(fn) -> str:
    """Sign and send a contract call. Returns the tx hash (0x...) without waiting for confirmation."""
    w3 = _web3()
    if _test_account:                                  # local test chain with unlocked account
        return w3.to_hex(fn.transact({"from": _test_account}))
    key = config.WEB3_PRIVATE_KEY.strip()
    acct = w3.eth.account.from_key(key if key.startswith("0x") else "0x" + key)
    # Polygon rejects transactions whose tip is below ~25 gwei ("transaction underpriced"), and some public
    # RPCs suggest less. Set fees explicitly: tip >= 30 gwei, max fee = 2 x base fee + tip.
    min_tip = w3.to_wei(30, "gwei")
    try:
        tip = max(min_tip, w3.eth.max_priority_fee)
    except Exception:
        tip = min_tip
    base_fee = w3.eth.get_block("latest").get("baseFeePerGas") or w3.eth.gas_price
    tx = fn.build_transaction({
        "from": acct.address,
        "nonce": w3.eth.get_transaction_count(acct.address, "pending"),
        "chainId": config.WEB3_CHAIN_ID,
        "maxPriorityFeePerGas": tip,
        "maxFeePerGas": 2 * base_fee + tip,
    })
    signed = acct.sign_transaction(tx)
    return w3.to_hex(w3.eth.send_raw_transaction(signed.raw_transaction))


def _b32(hash_hex: str) -> bytes:
    return bytes.fromhex(hash_hex.removeprefix("0x"))


def attest(hash_hex: str, expires_at_unix: int) -> str:
    return _send(_contract().functions.attest(_b32(hash_hex), int(expires_at_unix)))


def revoke(hash_hex: str, reason: str) -> str:
    return _send(_contract().functions.revoke(_b32(hash_hex), reason[:100]))


def tx_status(tx_hash: str) -> str:
    """pending / confirmed / failed"""
    try:
        receipt = _web3().eth.get_transaction_receipt(tx_hash)
    except Exception:
        return "pending"
    return "confirmed" if receipt["status"] == 1 else "failed"


def verify(hash_hex: str) -> dict:
    exists, valid, issued_at, expires_at, revoked_at, issuer = _contract().functions.verify(_b32(hash_hex)).call()
    return {"exists": exists, "valid": valid, "issued_at": issued_at, "expires_at": expires_at,
            "revoked_at": revoked_at or None, "issuer": issuer}


def explorer_tx_url(tx_hash: str | None) -> str | None:
    return f"{config.WEB3_EXPLORER_URL}/tx/{tx_hash}" if tx_hash and config.WEB3_EXPLORER_URL else None
