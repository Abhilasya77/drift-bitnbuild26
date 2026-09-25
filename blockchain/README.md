# Blockchain: CredentialAttestation (Polygon Amoy testnet)

Stores **only a non-sensitive hash** of each temporary credential, so any service can check that the platform really issued it and whether it has been revoked, without trusting our database. No names, DOB, document numbers, images or biometrics ever go on-chain.

| Function | Who | What |
|---|---|---|
| `attest(bytes32 hash, uint64 expiresAt)` | platform issuer wallet | Called by the backend when a credential is issued |
| `revoke(bytes32 hash, string reason)` | platform issuer wallet | Called by the backend when the permanent ID is linked |
| `verify(bytes32 hash)` | anyone (free, read-only) | Returns `exists, valid, issuedAt, expiresAt, revokedAt, issuer` |
| `setIssuer(address, bool)` | owner | Add or remove platform wallets |

Tested on a local test chain (see `backend/tests/test_flow.py::test_web3_attestation_on_local_chain`): only issuers can attest, issuing writes the hash, `verify` shows it valid, and linking the permanent ID revokes it.

## 1. Wallet + test tokens (10 min)
1. Install **MetaMask** and create a **new wallet only for this hackathon**. Never use a wallet holding real money.
2. Add the network: *Networks → Add network manually*
   - Name `Polygon Amoy` · RPC `https://rpc-amoy.polygon.technology` · Chain ID `80002` · Symbol `POL` · Explorer `https://amoy.polygonscan.com`
3. Get free test POL from a faucet: faucet.polygon.technology, Alchemy, QuickNode or Chainlink (some ask you to sign in, so try another if one refuses). About 0.1 POL is plenty.

## 2. Deploy with Remix (5 min, in the browser)
1. Open **remix.ethereum.org** → new file `CredentialAttestation.sol` → paste `contracts/CredentialAttestation.sol`
2. **Solidity compiler** tab → version **0.8.24** → Advanced: EVM **paris** → Compile
3. **Deploy & run** tab → Environment **Injected Provider – MetaMask** (network must show 80002) → Deploy → confirm in MetaMask
4. Copy the deployed contract address (under *Deployed Contracts*)

Alternative without Remix: `npm install && node compile.js && DEPLOYER_PRIVATE_KEY=0x... python deploy.py`

## 3. Connect the backend (`backend/.env`)
```
WEB3_RPC_URL=https://rpc-amoy.polygon.technology
WEB3_CONTRACT_ADDRESS=0x...           # from step 2
WEB3_PRIVATE_KEY=0x...                # the SAME test wallet (MetaMask → Account details → Show private key)
```
Restart the backend. Now every issued credential is attested automatically, and `/credentials/current` and `/verify/{token}` show the transaction and an **amoy.polygonscan.com** link. That's your demo moment.

Keep the private key only in `backend/.env`. It must never go in GitHub, the frontend or chat. If the chain is slow or down, credentials still work; the attestation just shows `failed`/`pending`.
