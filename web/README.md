# Glyph Evaluation Harness - Web UI

This is the web interface for the Glyph Evaluation Harness, providing a modern dashboard for zero-token replay evaluation of AI agent systems.

## Overview

The web UI provides a comprehensive interface for:
- **Run Management**: Create, monitor, and manage evaluation runs
- **Live vs Replay Modes**: View execution mode and token usage statistics
- **Artifact Inspection**: Examine immutable evidence artifacts
- **Baseline Comparison**: Compare candidate runs against approved baselines
- **Cost Tracking**: Monitor token usage and cost savings from replay
- **Release Decisions**: View detailed release decisions with reason codes
- **Progress Monitoring**: Real-time progress updates for long-running evaluations

## Architecture Integration

The web UI is built on the zero-token replay evaluation architecture:

### Live vs Replay Execution

The UI clearly distinguishes between execution modes:

**Live Run Example:**
```
Run 020 — Candidate v43
Mode: Live
Estimated target tokens: 1.4M
Budget cap: 1.8M
Cases requiring live execution: 18
Cases replayed: 102
Decision: PASSED
```

**Replay Run Example:**
```
Run 019 — Candidate v42
Mode: Replay
Model tokens: 0
Evaluator tokens: 0
Cases checked: 120
Cached traces reused: 120
Deterministic graders: 8
AI judges: 0
Decision: BLOCKED
```

### Key Features

#### Run Dashboard
- List all evaluation runs with status indicators
- Filter by mode (live/replay), status, project
- View token usage and cost savings
- Compare multiple runs side-by-side

#### Artifact Browser
- Inspect immutable evidence artifacts
- View sanitized execution events
- Check artifact integrity and hashes
- Download replay bundles

#### Baseline Comparison
- View baseline vs candidate comparisons
- See behavior change detection
- Examine blocking trials and reason codes
- Track regression metrics

#### Progress Monitoring
- Real-time progress bars for long runs
- Cancellation support for running evaluations
- Progress event timeline
- Worker status and queue depth

#### Release Decision UI
- Clear pass/block/inconclusive indicators
- Detailed reason codes and explanations
- Deterministic vs AI grade breakdown
- Policy compliance status

## Getting Started

### Prerequisites

- Node.js 18+ 
- pnpm, npm, or yarn
- Running evaluation harness backend API

### Installation

```bash
# Install dependencies
pnpm install
# or
npm install
# or
yarn install
```

### Configuration

Create a `.env.local` file:

```env
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_WS_URL=ws://localhost:8000
```

### Development

```bash
# Run development server
pnpm dev
# or
npm run dev
# or
yarn dev
```

Open [http://localhost:3000](http://localhost:3000) with your browser.

### Build

```bash
# Build for production
pnpm build
# or
npm run build
# or
yarn build
```

### Production

```bash
# Start production server
pnpm start
# or
npm run start
# or
yarn start
```

## Technology Stack

- **Next.js 14**: React framework with App Router
- **TypeScript**: Type-safe development
- **Tailwind CSS**: Utility-first styling
- **shadcn/ui**: High-quality React components
- **Recharts**: Data visualization for metrics
- **WebSocket**: Real-time progress updates

## Project Structure

```
web/
├── app/                    # Next.js App Router
│   ├── page.tsx           # Dashboard home
│   ├── runs/              # Run management pages
│   ├── artifacts/          # Artifact browser
│   ├── baselines/         # Baseline comparison
│   └── api/               # API routes
├── components/             # React components
│   ├── ui/                # shadcn/ui components
│   ├── runs/              # Run-related components
│   └── charts/            # Data visualization
├── lib/                   # Utilities and helpers
└── public/                # Static assets
```

## API Integration

The web UI integrates with the evaluation harness backend:

### REST API Endpoints

- `GET /api/runs` - List evaluation runs
- `POST /api/runs` - Create new evaluation run
- `GET /api/runs/{id}` - Get run details
- `GET /api/artifacts/{id}` - Get artifact details
- `GET /api/baselines/compare` - Compare runs

### WebSocket Events

- `run:progress` - Real-time progress updates
- `run:completed` - Run completion notification
- `run:failed` - Run failure notification
- `artifact:created` - New artifact available

## Contributing

When adding new features:

1. Follow the existing component structure
2. Use TypeScript for type safety
3. Maintain responsive design for mobile/tablet
4. Add appropriate loading and error states
5. Test with both live and replay execution modes
6. Update this README with new features

## Deploy on Vercel

The easiest way to deploy is using the [Vercel Platform](https://vercel.com/new):

```bash
vercel
```

Check out the [Next.js deployment documentation](https://nextjs.org/docs/app/building-your-application/deploying) for more details.