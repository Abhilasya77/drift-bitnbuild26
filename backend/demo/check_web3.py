"""Diagnose the blockchain connection. Never prints the private key.

    cd backend && python demo/check_web3.py            # read-only checks
    cd backend && python demo/check_web3.py --send     # also sends one real test attestation (tiny fee)
"""
import secrets
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import config  # noqa: E402
from app.services import web3_attest as w  # noqa: E402


def line(ok, text):
    print(("  OK  " if ok else "  !!  ") + text)
    return ok


print("RPC:     ", config.WEB3_RPC_URL or "(missing)")
print("Contract:", config.WEB3_CONTRACT_ADDRESS or "(missing)")
if not line(w.enabled(), "WEB3_* settings found in .env"):
    sys.exit()

w3 = w._web3()
line(w3.is_connected(), "RPC reachable")
chain = w3.eth.chain_id
line(chain == config.WEB3_CHAIN_ID, f"chain id {chain} (expected {config.WEB3_CHAIN_ID})")

key = config.WEB3_PRIVATE_KEY.strip()
if not key.startswith("0x"):
    key = "0x" + key
try:
    acct = w3.eth.account.from_key(key)
except Exception as e:
    line(False, f"private key is not valid ({type(e).__name__}). It must be 64 hex characters (plus 0x).")
    sys.exit()
line(True, f"wallet {acct.address}")
bal = w3.from_wei(w3.eth.get_balance(acct.address), "ether")
line(bal > 0.001, f"balance {bal} POL")

code = w3.eth.get_code(w3.to_checksum_address(config.WEB3_CONTRACT_ADDRESS))
if not line(len(code) > 0, "contract exists at that address on this chain"):
    sys.exit("  -> Wrong address, or it was deployed on a different network (e.g. Remix VM).")
c = w._contract()
line(c.functions.isIssuer(acct.address).call(),
     "this wallet is an allowed issuer (it must be the wallet that deployed the contract)")

if "--send" in sys.argv:
    h = "0x" + secrets.token_hex(32)
    try:
        tx = w.attest(h, int(time.time()) + 86400)
        print("  ..  sent", tx, "- waiting for confirmation")
        receipt = w3.eth.wait_for_transaction_receipt(tx, timeout=120)
        line(receipt["status"] == 1, f"test attestation confirmed: {config.WEB3_EXPLORER_URL}/tx/{tx}")
        print("       verify():", w.verify(h))
    except Exception as e:
        line(False, f"sending failed: {type(e).__name__}: {str(e)[:300]}")
