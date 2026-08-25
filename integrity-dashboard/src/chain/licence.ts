// ABI slice for LicenceAccount (contracts/src/licence/LicenceAccount.sol) -- the Phase II
// tracer-bullet ERC-6551 licence account. Deliberately deployed ONE PER LICENCE (see its own
// top-level NatSpec), not a singleton. The deployment mirror contains one experimental
// Base Sepolia reference account; the page can start there while still accepting any account
// address. This ABI includes the live settlement and ATCP/IP read surface, but the dashboard
// does not submit relayed intents or authorize session keys.
export const LICENCE_ACCOUNT_ABI = [
  'function owner() view returns (address)',
  'function token() view returns (uint256 chainId, address tokenContract, uint256 tokenId)',
  'function volumeCapTotal() view returns (uint256)',
  'function consumedUnits() view returns (uint256)',
  'function royaltyPricePerUnitWei() view returns (uint256)',
  'function licenceStartTime() view returns (uint256)',
  'function licenceEndTime() view returns (uint256)',
  'function state() view returns (uint256)',
  'function armed() view returns (bool)',
  'function armedCommittedBalance() view returns (uint256)',
  'function protocolFeeRecipient() view returns (address)',
  'function protocolFeeBps() view returns (uint256)',
  'function sessionKeyExpiry(address key) view returns (uint256)',
  'function consume(uint256 units) payable returns (uint256 royaltyPaid)',
  'function consumeWithIntent((address account,uint256 units,uint256 nonce,uint256 expiry) intent, bytes signature) payable returns (uint256 royaltyPaid)',
  'function armTransfer(uint256 committedBalance)',
  'function disarmTransfer()',
  'event Consumed(uint256 units, uint256 royaltyPaid, uint256 totalConsumed)',
  'event ProtocolFeeSettled(address indexed recipient, uint256 amount)',
  'event SessionKeyAuthorized(address indexed key, uint256 expiry)',
  'event SessionKeyRevoked(address indexed key)',
] as const;
