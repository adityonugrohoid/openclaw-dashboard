# OpenClaw Dashboard v2.0

A premium glassmorphism dashboard for monitoring OpenClaw agent status, configuration, and system information.

## Features

- **Premium Design**: Glassmorphism UI with advanced CSS effects and animations
- **Single Page Application**: Complete dashboard in a single HTML file
- **8 Dashboard Pages**:
  - Session Status - Current agent session information
  - Configuration - OpenClaw config with redacted sensitive values
  - Memory Files - Workspace memory and daily logs
  - Skills - Installed OpenClaw skills and capabilities  
  - Workspace - File tree structure and organization
  - Channels - Communication channels configuration
  - Security - Security audit results and recommendations
  - System Info - Host system status and resource usage

## Tech Stack

- **Backend**: FastAPI (Python) with comprehensive API endpoints
- **Frontend**: Single HTML file with Tailwind CSS + Alpine.js (no build step)
- **Package Manager**: uv
- **Port**: 8501

## Architecture

```
openclaw-dashboard/
├── app.py              # FastAPI app + API endpoints + serves static
├── static/
│   └── index.html      # Single-page dashboard (Tailwind + Alpine.js)  
├── pyproject.toml      # fastapi, uvicorn dependencies
└── README.md
```

## API Endpoints

All endpoints read from filesystem/subprocess and return JSON:

- `GET /` → Serves static/index.html
- `GET /api/config` → Parse openclaw.json with redacted sensitive values
- `GET /api/session` → Run openclaw status via subprocess
- `GET /api/memory` → List workspace .md files with content
- `GET /api/skills` → List skills with descriptions from SKILL.md
- `GET /api/workspace` → Tree structure of workspace (max depth 4)
- `GET /api/channels` → Channel configuration from openclaw.json
- `GET /api/security` → Run openclaw security audit
- `GET /api/system` → System information (CPU, memory, disk usage)

## Installation & Usage

1. **Install dependencies**:
   ```bash
   cd /home/adityonugrohoid/projects/openclaw-dashboard
   uv sync
   ```

2. **Start the dashboard**:
   ```bash
   uv run python app.py
   ```

3. **Access the dashboard**:
   Open http://localhost:8501 in your browser

## Design Features

### Color Palette
- Background: Deep space navy (#0B0F19)
- Cards: Glassmorphism with backdrop blur
- Accent colors: Electric cyan (#00D4FF) and purple (#7B61FF)
- Text: Primary (#E8EAED), Secondary (#9AA0B0), Muted (#5A6178)

### Visual Effects
- Glassmorphism cards with backdrop blur
- Animated gradient bars with shimmer effect  
- Pulsing status dots for active states
- Smooth page transitions and hover animations
- Custom scrollbars and progress bars
- JSON syntax highlighting
- Responsive design for mobile devices

### Navigation
- Fixed glassmorphism sidebar with brand logo
- 8 navigation items with icons and active states
- Mobile-responsive with collapsible sidebar
- Version information at bottom

## Development

The dashboard is built as a complete single-page application with:

- **FastAPI backend** handling all data fetching from filesystem and subprocesses
- **Alpine.js frontend** for reactive state management and navigation
- **Tailwind CSS** for styling with custom CSS for advanced effects
- **No build step required** - everything loads from CDN

## Security

- Sensitive configuration values are automatically redacted (first 4 + ... + last 4 chars)
- All subprocess calls have 15-second timeouts
- Proper error handling throughout the application
- No CORS needed as frontend and backend are same origin