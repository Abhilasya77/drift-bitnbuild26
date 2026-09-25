// Compiles contracts/CredentialAttestation.sol -> build/CredentialAttestation.json (abi + bytecode)
// Usage: npm install && node compile.js     (Remix does the same thing in the browser)
const fs = require("fs");
const solc = require("solc");
const source = fs.readFileSync(__dirname + "/contracts/CredentialAttestation.sol", "utf8");
const input = {
  language: "Solidity",
  sources: { "CredentialAttestation.sol": { content: source } },
  settings: { optimizer: { enabled: true, runs: 200 }, evmVersion: "paris",
              outputSelection: { "*": { "*": ["abi", "evm.bytecode.object"] } } },
};
const out = JSON.parse(solc.compile(JSON.stringify(input)));
const errors = (out.errors || []).filter(e => e.severity === "error");
if (errors.length) { console.error(errors.map(e => e.formattedMessage).join("\n")); process.exit(1); }
(out.errors || []).forEach(e => console.warn(e.formattedMessage));
const c = out.contracts["CredentialAttestation.sol"].CredentialAttestation;
fs.mkdirSync(__dirname + "/build", { recursive: true });
fs.writeFileSync(__dirname + "/build/CredentialAttestation.json",
  JSON.stringify({ abi: c.abi, bytecode: "0x" + c.evm.bytecode.object }, null, 2));
console.log("compiled OK, bytecode bytes:", c.evm.bytecode.object.length / 2);
