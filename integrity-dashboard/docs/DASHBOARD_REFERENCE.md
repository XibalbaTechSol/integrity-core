# Command Center Technical Reference

The Integrity Dashboard is the primary visual interface for the protocol. It is built for high-performance fleet management and real-time observability.

## Architecture

### State Management
- **React Context**: Used for global agent state and wallet connection.
- **Polling Hooks**: Background hooks fetch latest telemetry from the Oracle every 5 seconds.

### Data Visualization
- **Recharts**: Renders the dynamic Tri-Metric radar charts.
- **Framer Motion**: Manages the "Glassmorphism" UI transitions and live stream animations.

### Web3 Integration
- **Web3Modal**: Standardized provider for wallet connections.
- **Ethers.js**: Handles on-chain state lookups for AIS state roots and slashing events.

## Features

- **Live Stream**: WebSocket-like behavior using short-polling for real-time fidelity.
- **Fleet Registry**: searchable index of all agents associated with the connected DID.
- **Reputation Lending**: (Planned) Interface for the ITK credit facility.
