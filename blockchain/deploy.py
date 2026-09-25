"""Deploy CredentialAttestation to Polygon Amoy without Remix (optional; Remix steps are in README.md).

    cd blockchain
    npm install && node compile.js
    pip install web3
    DEPLOYER_PRIVATE_KEY=0x... python deploy.py      # TESTNET-ONLY wallet with a little Amoy POL
"""
import json
import os
from pathlib import Path

from web3 import Web3

RPC = os.getenv("WEB3_RPC_URL", "https://rpc-amoy.polygon.technology")
KEY = os.environ["DEPLOYER_PRIVATE_KEY"]

art = json.loads((Path(__file__).parent / "build" / "CredentialAttestation.json").read_text())
w3 = Web3(Web3.HTTPProvider(RPC))
acct = w3.eth.account.from_key(KEY)
print("Deployer:", acct.address, "balance:", w3.from_wei(w3.eth.get_balance(acct.address), "ether"), "POL")

tx = w3.eth.contract(abi=art["abi"], bytecode=art["bytecode"]).constructor().build_transaction({
    "from": acct.address, "nonce": w3.eth.get_transaction_count(acct.address), "chainId": w3.eth.chain_id})
signed = acct.sign_transaction(tx)
tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
print("Deploying... tx:", w3.to_hex(tx_hash))
receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=180)
print("\nContract address:", receipt["contractAddress"])
print("Put it in backend/.env as WEB3_CONTRACT_ADDRESS=" + receipt["contractAddress"])
print("Explorer: https://amoy.polygonscan.com/address/" + receipt["contractAddress"])
