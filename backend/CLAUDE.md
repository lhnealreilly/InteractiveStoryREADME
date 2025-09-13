# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is the backend for an Interactive GitHub Adventure - a choose-your-own-adventure game that runs entirely within a README.md file using dynamic PNG generation and GitHub's image proxy system.

### Architecture

The backend is implemented as a Python AWS Lambda function that:
- Serves dynamic PNG images for game scenes, choices, and statistics  
- Maintains global game state in DynamoDB
- Processes player choices and updates story progression
- Handles redirects back to the GitHub README after choices

**Key Components:**
- `lambda_function.py` - Main Lambda handler with story logic and image generation
- `deploy.sh` - Complete AWS deployment script (Lambda + API Gateway + DynamoDB)

### Story System

Stories are defined in `STORY_CONFIG` within `lambda_function.py` with scenes containing:
- title, description, background_color
- choices that lead to other scenes
- Built-in scenes: start → dark_path/light_path → multiple endings

## Deployment

### Prerequisites
- AWS CLI configured with appropriate permissions
- Python 3.9+ with pip
- AWS account with Lambda, DynamoDB, and API Gateway permissions

### Deploy Backend
```bash
./deploy.sh
```

This script will:
1. Create deployment package with dependencies (boto3, Pillow)
2. Set up IAM roles with DynamoDB permissions
3. Deploy Lambda function with 30s timeout, 512MB memory
4. Create DynamoDB tables: `adventure-game-state`, `adventure-stats`
5. Set up API Gateway with proxy integration
6. Initialize game state
7. Output API endpoints for README integration

### API Endpoints
- `/scene.png` - Current adventure scene image
- `/option/a.png` - Choice A button image  
- `/option/b.png` - Choice B button image
- `/choice/a` - Process choice A (redirects to GitHub)
- `/choice/b` - Process choice B (redirects to GitHub)
- `/stats.png` - Game statistics image
- `/history.png` - Recent choices history

### DynamoDB Schema

**adventure-game-state table:**
- `game_id` (Hash Key): Always 'global'
- `current_scene`: Current story scene ID
- `total_players`: Count of unique players
- `choices_made`: Total choices made
- `last_updated`: ISO timestamp

**adventure-stats table:**
- `stat_type` (Hash Key): 'scene_visits' or 'total_choices'
- `scene_counts`: Map of scene_id → visit_count
- `choice_count`: Total choices counter

## Image Generation

Uses Pillow (PIL) to generate dynamic PNGs with:
- Scene backgrounds with configurable colors
- Centered text rendering with multiple font sizes
- Choice buttons with distinct colors (green/blue)
- Statistics overlays and decorative elements
- Error handling with fallback images

**Font Support:** Attempts to load Arial TTF fonts from `/opt/fonts/`, falls back to default if unavailable.

## Development Notes

- All images return cache-busting headers to prevent GitHub proxy caching
- Choice processing updates both game state and statistics atomically
- Error handling returns user-friendly error images instead of HTTP errors
- Redirects after choices use 302 status to return users to GitHub README
- Game state is global (single story progression for all players)

## Adding New Story Content

1. Edit `STORY_CONFIG` in `lambda_function.py`
2. Add new scenes with title, description, background_color, choices
3. Ensure choice paths reference valid scene IDs
4. Redeploy with `./deploy.sh` (updates existing Lambda function)
5. Test endpoints before updating README URLs