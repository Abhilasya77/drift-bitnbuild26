// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @title CredentialAttestation — Team Drift, BitNBuild '26
/// @notice Records a non-sensitive fingerprint (hash) of each temporary platform credential on Polygon Amoy,
///         so any participating service can check that a credential was really issued by the platform and
///         whether it has since been revoked — without trusting our database.
/// @dev    NO personal data ever goes here: no names, DOB, document numbers, images or biometrics.
///         The hash is computed by the backend from {credential id, issued_at, expires_at, issuer}.
///         On-chain integrity proves the attestation exists; it does NOT prove the original
///         government document is authentic.
contract CredentialAttestation {
    struct Record {
        uint64 issuedAt;    // block timestamp when attested
        uint64 expiresAt;   // credential expiry (unix seconds)
        uint64 revokedAt;   // 0 = not revoked
        address issuer;     // wallet that attested it
    }

    address public owner;
    mapping(address => bool) public isIssuer;
    mapping(bytes32 => Record) private records;

    event IssuerSet(address indexed issuer, bool allowed);
    event Attested(bytes32 indexed credentialHash, address indexed issuer, uint64 expiresAt);
    event Revoked(bytes32 indexed credentialHash, address indexed issuer, string reason);

    error NotOwner();
    error NotIssuer();
    error AlreadyAttested();
    error UnknownCredential();
    error AlreadyRevoked();

    modifier onlyOwner() {
        if (msg.sender != owner) revert NotOwner();
        _;
    }

    modifier onlyIssuer() {
        if (!isIssuer[msg.sender]) revert NotIssuer();
        _;
    }

    constructor() {
        owner = msg.sender;
        isIssuer[msg.sender] = true;
        emit IssuerSet(msg.sender, true);
    }

    /// @notice Allow or remove a platform wallet that may attest credentials.
    function setIssuer(address issuer, bool allowed) external onlyOwner {
        isIssuer[issuer] = allowed;
        emit IssuerSet(issuer, allowed);
    }

    /// @notice Record a newly issued credential's hash.
    function attest(bytes32 credentialHash, uint64 expiresAt) external onlyIssuer {
        if (records[credentialHash].issuedAt != 0) revert AlreadyAttested();
        records[credentialHash] = Record(uint64(block.timestamp), expiresAt, 0, msg.sender);
        emit Attested(credentialHash, msg.sender, expiresAt);
    }

    /// @notice Mark a credential as no longer valid (e.g. permanent ID linked, or fraud confirmed).
    function revoke(bytes32 credentialHash, string calldata reason) external onlyIssuer {
        Record storage r = records[credentialHash];
        if (r.issuedAt == 0) revert UnknownCredential();
        if (r.revokedAt != 0) revert AlreadyRevoked();
        r.revokedAt = uint64(block.timestamp);
        emit Revoked(credentialHash, msg.sender, reason);
    }

    /// @notice Anyone can check a credential hash. `valid` = attested, not revoked and not expired.
    function verify(bytes32 credentialHash)
        external
        view
        returns (bool exists, bool valid, uint64 issuedAt, uint64 expiresAt, uint64 revokedAt, address issuer)
    {
        Record memory r = records[credentialHash];
        exists = r.issuedAt != 0;
        valid = exists && r.revokedAt == 0 && block.timestamp < r.expiresAt;
        return (exists, valid, r.issuedAt, r.expiresAt, r.revokedAt, r.issuer);
    }
}
