import json
import boto3
import base64
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
import uuid
import time
from datetime import datetime
import random
import os
import subprocess
import tempfile
from google import genai
from pydantic import BaseModel
from typing import List, Optional
from dotenv import load_dotenv
from jinja2 import Template
import game_state_manager
import traceback

load_dotenv()

# DynamoDB setup
dynamodb = boto3.resource('dynamodb')
game_state_table = dynamodb.Table('adventure-game-state')
stats_table = dynamodb.Table('adventure-stats')
story_scenes_table = dynamodb.Table('adventure-story-scenes')

# Google Gemini setup
GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY')
genai_client = genai.Client(api_key=GOOGLE_API_KEY)

game_state = game_state_manager.GameStateManager()

# Pydantic models for structured scene generation
class SceneChoice(BaseModel):
    text: str
    leads_to: str

class GeneratedScene(BaseModel):
    title: str
    description: str
    summary: str  # What happened in the transition to this scene
    background_color: str
    choice_a: SceneChoice
    choice_b: SceneChoice

# Story generation templates and themes
STORY_THEMES = {
    'fantasy': {
        'locations': ['enchanted forest', 'crystal cave', 'ancient ruins', 'mystical lake', 'dragon lair', 'wizard tower', 'fairy glade'],
        'creatures': ['dragon', 'unicorn', 'phoenix', 'shadow beast', 'forest spirit', 'ancient wizard', 'magical fairy'],
        'objects': ['magical sword', 'crystal orb', 'ancient tome', 'healing potion', 'enchanted ring', 'mysterious key'],
        'colors': ['#2d5016', '#1a1a2e', '#4a148c', '#006064', '#7b1fa2', '#b71c1c', '#4a7c59']
    },
    'sci_fi': {
        'locations': ['space station', 'alien planet', 'cybercity', 'quantum lab', 'neural network', 'time portal', 'robot factory'],
        'creatures': ['alien being', 'AI construct', 'cyborg', 'space pirate', 'quantum entity', 'android'],
        'objects': ['plasma weapon', 'neural implant', 'quantum computer', 'alien artifact', 'time device', 'energy core'],
        'colors': ['#0d47a1', '#1a237e', '#4a148c', '#e65100', '#bf360c', '#263238', '#37474f']
    },
    'mystery': {
        'locations': ['old mansion', 'foggy cemetery', 'abandoned library', 'secret passage', 'dark alley', 'hidden chamber'],
        'creatures': ['mysterious figure', 'ghostly apparition', 'suspicious butler', 'eccentric detective', 'shadowy stalker'],
        'objects': ['cryptic note', 'antique key', 'hidden diary', 'bloody knife', 'strange photograph', 'coded message'],
        'colors': ['#212121', '#424242', '#616161', '#795548', '#5d4037', '#3e2723', '#1b0000']
    }
}

# Item definitions
ITEMS = {
    'basic_sword': {'name': 'Basic Sword', 'type': 'weapon', 'power': 10},
    'leather_armor': {'name': 'Leather Armor', 'type': 'armor', 'defense': 5},
    'health_potion': {'name': 'Health Potion', 'type': 'consumable', 'effect': 'heal_25'},
    'magic_ring': {'name': 'Magic Ring', 'type': 'accessory', 'power': 15},
    'steel_sword': {'name': 'Steel Sword', 'type': 'weapon', 'power': 20},
    'chain_armor': {'name': 'Chain Armor', 'type': 'armor', 'defense': 15},
    'ancient_tome': {'name': 'Ancient Tome', 'type': 'special', 'power': 30},
    'energy_core': {'name': 'Energy Core', 'type': 'special', 'power': 25},
    'plasma_rifle': {'name': 'Plasma Rifle', 'type': 'weapon', 'power': 35},
    'cyber_implant': {'name': 'Cyber Implant', 'type': 'accessory', 'power': 20},
    'detective_badge': {'name': 'Detective Badge', 'type': 'special', 'power': 10}
}

# Initial scene for new games
INITIAL_SCENE = {
    'scene_id': 'start',
    'title': 'The Adventure Begins',
    'description': 'Welcome, brave adventurer! Your journey starts here.\nEvery choice shapes a unique story just for you.',
    'background_color': '#2d5016',
    'choices': {
        'a': {'text': 'Begin a Fantasy Quest', 'leads_to': 'fantasy_start'},
        'b': {'text': 'Start Sci-Fi Adventure', 'leads_to': 'scifi_start'}
    },
    'theme': 'fantasy',
    'created_at': datetime.now().isoformat(),
    'player_state': game_state_manager.PlayerState(),
    'summary': 'Your adventure begins in this mysterious realm.'
}

# HTML Template for scene rendering
SCENE_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Adventure Scene</title>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Cinzel:wght@400;600;700&family=Cormorant+Garamond:ital,wght@0,400;0,600;1,400&display=swap');

        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            width: 800px;
            height: 600px;
            font-family: 'Cormorant Garamond', serif;
            color: #ffffff;
            position: relative;
            overflow: hidden;
            background: #0d1117;
        }

        .scene-container {
            padding: 40px;
            height: 100%;
            display: flex;
            flex-direction: column;
            justify-content: space-between;
            position: relative;
            background: #0d1117;
        }

        .decorative-border {
            position: absolute;
            top: 15px;
            left: 15px;
            right: 15px;
            bottom: 15px;
            border: 3px solid rgba(255, 255, 255, 0.5);
            border-radius: 15px;
            pointer-events: none;
        }

        .title {
            font-family: 'Cinzel', serif;
            font-size: 36px;
            font-weight: 700;
            text-align: center;
            margin-bottom: 25px;
            text-shadow: 2px 2px 4px rgba(0, 0, 0, 0.7);
            color: #fff;
            letter-spacing: 2px;
        }

        .content-area {
            flex-grow: 1;
            display: flex;
            flex-direction: column;
            justify-content: center;
            max-width: 720px;
            margin: 0 auto;
        }

        .summary {
            background: rgba(255, 255, 136, 0.25);
            border-left: 4px solid #ffeb3b;
            padding: 15px 20px;
            margin-bottom: 20px;
            border-radius: 0 8px 8px 0;
            font-style: italic;
            font-size: 18px;
            line-height: 1.4;
        }

        .summary::before {
            content: "▶ ";
            color: #ffff88;
            font-weight: bold;
        }

        .description {
            font-size: 24px;
            line-height: 1.6;
            text-align: center;
            margin-bottom: 30px;
            text-shadow: 1px 1px 2px rgba(0, 0, 0, 0.5);
            font-weight: 400;
        }

        .stats-overlay {
            position: absolute;
            bottom: 20px;
            left: 20px;
            background: rgba(13, 17, 23, 0.9);
            padding: 15px;
            border-radius: 10px;
            font-size: 16px;
            line-height: 1.4;
            backdrop-filter: blur(5px);
            border: 1px solid rgba(255, 255, 255, 0.4);
        }

        .stat-line {
            margin: 3px 0;
            display: flex;
            align-items: center;
        }

        .stat-icon {
            margin-right: 8px;
            font-size: 18px;
        }

        .health-bar {
            width: 120px;
            height: 8px;
            background: rgba(255, 255, 255, 0.3);
            border-radius: 4px;
            overflow: hidden;
            margin-left: 10px;
        }

        .health-fill {
            height: 100%;
            background: linear-gradient(90deg, #ff4444, #ff8888);
            transition: width 0.3s ease;
            width: {{ health_percentage }}%;
        }

        .decorative-elements {
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            pointer-events: none;
        }

        .corner-ornament {
            position: absolute;
            width: 60px;
            height: 60px;
            opacity: 0.3;
        }

        .corner-ornament.top-left {
            top: 25px;
            left: 25px;
            background: radial-gradient(circle, rgba(255,255,255,0.4) 0%, transparent 70%);
            border-radius: 50%;
        }

        .corner-ornament.bottom-right {
            bottom: 25px;
            right: 25px;
            background: radial-gradient(circle, rgba(255,255,255,0.4) 0%, transparent 70%);
            border-radius: 50%;
        }

        .theme-fantasy {
            background: linear-gradient(135deg, #2d5016, #4a7c59);
        }

        .theme-sci_fi {
            background: linear-gradient(135deg, #0d47a1, #1976d2);
        }

        .theme-mystery {
            background: linear-gradient(135deg, #212121, #424242);
        }
    </style>
</head>
<body class="theme-{{ theme }}">
    <div class="decorative-border"></div>
    <div class="scene-container">
        <div class="title">{{ title }}</div>

        <div class="content-area">
            {% if summary and scene_id != 'start' %}
            <div class="summary">{{ summary }}</div>
            {% endif %}

            <div class="description">{{ description | replace('\n', '<br>') }}</div>
        </div>


    </div>

    <div class="decorative-elements">
        <div class="corner-ornament top-left"></div>
        <div class="corner-ornament bottom-right"></div>
    </div>
</body>
</html>
"""

CHOICE_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Choice Button</title>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Cinzel:wght@600&display=swap');

        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
            background: #0d1117;
        }

        body {
            width: 400px;
            height: 150px;
            font-family: 'Cinzel', serif;
            color: #ffffff;
            display: flex;
            align-items: center;
            justify-content: center;
            position: relative;
            border-radius: 12px;
            box-shadow: 0 6px 20px rgba(0, 0, 0, 0.5);
            border: 2px solid rgba(255, 255, 255, 0.6);
        }

        .button-content {
            text-align: center;
            padding: 0 15px;
            width: 100%;
            max-width: 370px;
        }

        .choice-label {
            font-size: 14px;
            opacity: 0.8;
            margin-bottom: 2px;
            letter-spacing: 1px;
        }

        .choice-text {
            font-size: 16px;
            font-weight: 600;
            text-shadow: 1px 1px 2px rgba(0, 0, 0, 0.7);
            letter-spacing: 0.5px;
            line-height: 1.2;
            word-wrap: break-word;
            hyphens: auto;
        }

        /* Scale text down for longer choices */
        @media (max-width: 400px) {
            .choice-text {
                font-size: 14px;
            }
        }

        /* Further scaling for very long text */
        .choice-text.long-text {
            font-size: 14px;
            line-height: 1.1;
        }

        .choice-text.very-long-text {
            font-size: 12px;
            line-height: 1.0;
        }

        .shine {
            position: absolute;
            top: 0;
            left: -100%;
            width: 100%;
            height: 100%;
            background: linear-gradient(90deg, transparent, rgba(255,255,255,0.3), transparent);
            animation: shine 3s infinite;
        }

        @keyframes shine {
            0% { left: -100%; }
            100% { left: 100%; }
        }
    </style>
</head>
<body>
    <div class="button-content">
        <div class="choice-label">Choice {{ choice_type.upper() }}</div>
        <div class="choice-text" id="choiceText">{{ text }}</div>
    </div>
    <div class="shine"></div>

    <script>
        // Auto-scale text to fit within button
        function scaleTextToFit() {
            const textElement = document.getElementById('choiceText');
            const text = textElement.textContent;

            // Add classes based on text length
            if (text.length > 40) {
                textElement.classList.add('very-long-text');
            } else if (text.length > 25) {
                textElement.classList.add('long-text');
            }

            // Additional dynamic scaling if needed
            const container = textElement.parentElement;
            const containerWidth = container.offsetWidth - 30; // Account for padding

            let fontSize = window.getComputedStyle(textElement).fontSize;
            fontSize = parseInt(fontSize);

            // Reduce font size until text fits
            while (textElement.scrollWidth > containerWidth && fontSize > 10) {
                fontSize -= 1;
                textElement.style.fontSize = fontSize + 'px';
            }
        }

        // Run after fonts load
        window.addEventListener('load', scaleTextToFit);
        document.fonts.ready.then(scaleTextToFit);
    </script>
</body>
</html>
"""

def lambda_handler(event, context):
    """Main Lambda handler for adventure game endpoints"""
    print(f"DEBUG: Lambda handler called with path: {event.get('path', '/')}")

    # Extract path and query parameters
    path = event.get('path', '/')
    query_params = event.get('queryStringParameters') or {}
    print(f"DEBUG: Query params: {query_params}")
    
    # Set CORS headers
    headers = {
        'Content-Type': 'image/png',
        'Cache-Control': 'no-cache, no-store, must-revalidate',
        'Pragma': 'no-cache',
        'Expires': '0',
        'Access-Control-Allow-Origin': '*'
    }
    
    try:
        # Route to appropriate handler
        if path.endswith('/scene.png'):
            print("DEBUG: Generating scene image")
            image_data = generate_scene_image()
        elif path.endswith('/choice/a') or path.endswith('/choice/b'):
            choice = 'a' if path.endswith('/a') else 'b'
            print(f"DEBUG: Processing choice: {choice}")
            process_choice(choice)
            # Redirect back to GitHub README
            return {
                'statusCode': 302,
                'headers': {
                    'Location': 'https://github.com/lhnealreilly/InteractiveStoryREADME#current-scene',
                    'Cache-Control': 'no-cache, no-store, must-revalidate'
                }
            }
        elif path.endswith('/option/a.png'):
            print("DEBUG: Generating choice A image")
            image_data = generate_choice_image('a')
        elif path.endswith('/option/b.png'):
            print("DEBUG: Generating choice B image")
            image_data = generate_choice_image('b')
        elif path.endswith('/stats.png'):
            image_data = generate_stats_image()
        elif path.endswith('/player.png'):
            print("DEBUG: Generating player stats image")
            #TODO Generate player stats image
        elif path.endswith('/history.png'):
            image_data = generate_history_image()
        else:
            # Default to scene image
            image_data = generate_scene_image()
        
        # Return base64 encoded image
        return {
            'statusCode': 200,
            'headers': headers,
            'body': base64.b64encode(image_data).decode('utf-8'),
            'isBase64Encoded': True
        }
        
    except Exception as e:
        print(f"Error: {str(e)}")
        # Return error image
        error_image = generate_error_image(str(e))
        return {
            'statusCode': 200,
            'headers': headers,
            'body': base64.b64encode(error_image).decode('utf-8'),
            'isBase64Encoded': True
        }

def get_current_game_state():
    """Retrieve current game state from DynamoDB"""
    print("DEBUG: Getting current game state from DynamoDB")
    try:
        response = game_state_table.get_item(Key={'game_id': 'global'})
        print(f"DEBUG: DynamoDB response: {response}")
        if 'Item' in response:
            return response['Item']
        else:
            # Initialize new game state
            initial_state = {
                'game_id': 'global',
                'current_scene': 'start',
                'total_players': 0,
                'choices_made': 0,
                'last_updated': datetime.now().isoformat()
            }
            game_state_table.put_item(Item=initial_state)
            return initial_state
    except Exception as e:
        print(f"Error getting game state: {e}")
        return {
            'game_id': 'global',
            'current_scene': 'start',
            'total_players': 0,
            'choices_made': 0,
            'last_updated': datetime.now().isoformat()
        }

def update_game_state(new_scene):
    """Update game state in DynamoDB"""
    try:
        current_state = get_current_game_state()
        current_state['current_scene'] = new_scene
        current_state['choices_made'] = current_state.get('choices_made', 0) + 1
        current_state['last_updated'] = datetime.now().isoformat()
        
        game_state_table.put_item(Item=current_state)
        
        # Update statistics
        update_stats(new_scene)
        
    except Exception as e:
        print(f"Error updating game state: {e}")

def update_stats(scene_id):
    """Update statistics in DynamoDB"""
    try:
        stats_table.update_item(
            Key={'stat_type': 'scene_visits'},
            UpdateExpression='ADD scene_counts.#scene :inc',
            ExpressionAttributeNames={'#scene': scene_id},
            ExpressionAttributeValues={':inc': 1}
        )

        stats_table.update_item(
            Key={'stat_type': 'total_choices'},
            UpdateExpression='ADD choice_count :inc',
            ExpressionAttributeValues={':inc': 1}
        )

    except Exception as e:
        print(f"Error updating stats: {e}")

def get_or_generate_scene(scene_id, theme='fantasy', previous_scene=None, choice_made=None):
    """Get scene from DynamoDB or generate new one if it doesn't exist"""
    print(f"DEBUG: Getting/generating scene: {scene_id}, theme: {theme}")

    # Handle initial scene specially
    if scene_id == 'start':
        print("DEBUG: Returning initial scene")
        return INITIAL_SCENE

    try:
        # Try to get existing scene from DynamoDB
        print(f"DEBUG: Checking DynamoDB for existing scene: {scene_id}")
        response = story_scenes_table.get_item(Key={'scene_id': scene_id})
        if 'Item' in response:
            print(f"DEBUG: Found existing scene in DynamoDB")
            processed_scene = {**response['Item']}
            processed_scene['player_state'] = game_state.import_state(processed_scene['player_state'])
            return processed_scene
        else:
            print(f"DEBUG: Scene not found in DynamoDB, will generate new one")
    except Exception as e:
        print(f"Error fetching scene {scene_id}: {e}")

    # Generate new scene if not found
    print(f"Generating new scene: {scene_id}")
    return generate_new_scene(scene_id, theme, previous_scene, choice_made)

def generate_new_scene(scene_id, theme='fantasy', previous_scene=None, choice_made=None):
    """Generate a new story scene using Gemini AI with fallback to procedural generation"""
    print(f"DEBUG: Generating new scene: {scene_id}")
    print(f"DEBUG: Previous scene: {previous_scene.get('scene_id', 'None') if previous_scene else 'None'}")
    print(f"DEBUG: Choice made: {choice_made}")
    print(f"DEBUG: Previous scene player state: {previous_scene}")

    # Try Gemini generation first
    print("DEBUG: Attempting Gemini scene generation")
    gemini_scene = generate_scene_with_gemini(scene_id, theme, previous_scene, choice_made)

    print("DEBUG: Gemini scene generation successful")
    # Add player state to Gemini-generated scene
    #TODO Calculate the new player state based on consequences of the choice made
    #player_state = game_state.apply_choice_consequences(previous_scene.get('player_state'), choice_made, scene_id)
    player_state = game_state_manager.PlayerState()
    gemini_scene['player_state'] = player_state
    print(f"DEBUG: Added player state to scene: {player_state}")

    # Save to DynamoDB
    try:
        saveable_scene = {**gemini_scene}
        saveable_scene['player_state'] = game_state.export_state(gemini_scene['player_state'])
        story_scenes_table.put_item(Item=saveable_scene)
        print(f"Saved Gemini-generated scene: {scene_id}")
    except Exception as e:
        print(f"Error saving Gemini scene {scene_id}: {e}")

    return gemini_scene
    


def get_level_items(level, theme):
    """Get items awarded at specific levels based on theme"""
    theme_items = {
        'fantasy': {
            2: ['health_potion'],
            3: ['magic_ring'],
            4: ['steel_sword'],
            5: ['chain_armor', 'ancient_tome']
        },
        'sci_fi': {
            2: ['energy_core'],
            3: ['cyber_implant'],
            4: ['plasma_rifle'],
            5: ['quantum_computer']
        },
        'mystery': {
            2: ['detective_badge'],
            3: ['cryptic_note'],
            4: ['antique_key'],
            5: ['hidden_diary']
        }
    }

    return theme_items.get(theme, {}).get(level, [])

def render_html_to_png(html_content, width=800, height=600):
    """Convert HTML to PNG using wkhtmltoimage"""
    try:
        # Create temporary files
        with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as html_file:
            html_file.write(html_content)
            html_file.flush()

            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as png_file:
                png_path = png_file.name

            # Use wkhtmltoimage to convert HTML to PNG
            cmd = [
                '/opt/bin/wkhtmltoimage',  # Lambda layer path
                '--width', str(width),
                '--height', str(height),
                '--quality', '95',
                '--format', 'png',
                '--disable-smart-width',
                '--no-stop-slow-scripts',
                '--javascript-delay', '1000',  # Allow time for fonts to load
                html_file.name,
                png_path
            ]

            # Run the conversion
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)

            if result.returncode != 0:
                print(f"wkhtmltoimage error: {result.stderr}")
                return None

            # Read the generated PNG
            with open(png_path, 'rb') as f:
                png_data = f.read()

            # Cleanup
            os.unlink(html_file.name)
            os.unlink(png_path)

            return png_data

    except Exception as e:
        print(f"HTML to PNG conversion failed: {e}")
        return None

def generate_scene_with_gemini(scene_id, theme, previous_scene=None, choice_made=None, player_state=None):
    """Use Google Gemini to generate a new scene with structured output"""

    try:
        # Use GameStateManager to generate consequence-aware prompt
        if player_state is None:
            player_state = previous_scene.get('player_state', {})

        # Generate the sophisticated prompt using GameStateManager
        prompt = game_state.generate_scene_prompt(player_state, theme, previous_scene, choice_made)

        # Add theme-specific elements to the prompt
        theme_data = STORY_THEMES.get(theme, STORY_THEMES['fantasy'])
        locations = ', '.join(theme_data['locations'])
        creatures = ', '.join(theme_data['creatures'])
        objects = ', '.join(theme_data['objects'])

        prompt += f"""

THEME ELEMENTS FOR {theme.upper()}:
- Locations: {locations}
- Creatures: {creatures}
- Objects: {objects}
- Color palette: {', '.join(theme_data['colors'])}

Use these elements appropriately in your scene generation.
"""

        # Generate scene using Gemini
        response = genai_client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config={
                "response_mime_type": "application/json",
                "response_schema": GeneratedScene,
            },
        )

        # Parse the generated scene
        generated_scene: GeneratedScene = response.parsed

        # Convert to our scene format
        new_scene = {
            'scene_id': scene_id,
            'title': generated_scene.title,
            'description': generated_scene.description,
            'summary': generated_scene.summary,
            'background_color': generated_scene.background_color,
            'choices': {
                'a': {'text': generated_scene.choice_a.text, 'leads_to': f'{theme}_{len(scene_id)}a_{random.randint(1000, 9999)}'},
                'b': {'text': generated_scene.choice_b.text, 'leads_to': f'{theme}_{len(scene_id)}a_{random.randint(1000, 9999)}'}
            },
            'theme': theme,
            'created_at': datetime.now().isoformat()
        }

        return new_scene

    except Exception as e:
        print(f"Error generating scene with Gemini: {e}")
        # Fallback to original generation method
        print(traceback.format_exc())

def process_choice(choice):
    """Process a player's choice and update game state"""
    print(f"DEBUG: Processing choice: {choice}")
    current_state = get_current_game_state()
    current_scene_id = current_state.get('current_scene', 'start')
    print(f"DEBUG: Current scene ID: {current_scene_id}")

    scene = get_or_generate_scene(current_scene_id)
    print(f"DEBUG: Current scene choices: {scene.get('choices', {})}")

    if choice in scene.get('choices', {}):
        next_scene_id = scene['choices'][choice]['leads_to']
        print(f"DEBUG: Choice leads to scene: {next_scene_id}")

        # Generate the next scene with choice consequences
        next_scene = get_or_generate_scene(next_scene_id, scene.get('theme', 'fantasy'), scene, choice)

        # Update game state to the new scene
        # (Death handling is already done in generate_new_scene)
        update_game_state(next_scene.get('scene_id', next_scene_id))

        # Update death statistics if player died
        if next_scene.get('scene_id') == 'start' and scene.get('scene_id') != 'start':
            try:
                stats_table.update_item(
                    Key={'stat_type': 'player_deaths'},
                    UpdateExpression='SET death_count = if_not_exists(death_count, :zero) + :inc',
                    ExpressionAttributeValues={':inc': 1, ':zero': 0}
                )
            except Exception as e:
                print(f"Error updating death stats: {e}")

def generate_scene_image():
    """Generate the main scene image using HTML template rendering"""
    print("DEBUG: Starting scene image generation")
    current_state = get_current_game_state()
    scene_id = current_state.get('current_scene', 'start')
    print(f"DEBUG: Current scene ID for image: {scene_id}")
    scene = get_or_generate_scene(scene_id)
    print(f"DEBUG: Scene data: {scene.get('title', 'No title')} - {scene.get('description', 'No description')[:50]}...")

    # Get player state - handle both old and new formats
    player_state_data = scene.get('player_state', {})
    print(f"DEBUG: Player state data: {player_state_data}")
    if isinstance(player_state_data, game_state_manager.PlayerState):
        # New format - import from GameStateManager
        player_state = player_state_data
        print(f"DEBUG: Successfully imported player state")
    else:
        print(f"DEBUG: Player state data dict, converting to PlayerState")
        player_state = game_state.import_state(player_state_data)

    health = player_state.health
    max_health = player_state.max_health
    gold = player_state.gold
    level = player_state.level
    experience = player_state.experience
    items = player_state.items
    food = getattr(player_state, 'food', 3)
    corruption = getattr(player_state, 'corruption', 0)
    reputation = getattr(player_state, 'reputation', 'unknown')
    print(f"DEBUG: Player stats - Health: {health}/{max_health}, Food: {food}, Gold: {gold}, Corruption: {corruption}")

    # Prepare items display
    items_display = ""
    if items:
        item_names = [ITEMS.get(item, {}).get('name', item) for item in items[:3]]
        items_display = ", ".join(item_names)
        if len(items) > 3:
            items_display += f" (+{len(items)-3} more)"

    # Calculate health percentage for progress bar
    health_percentage = (health / max_health * 100) if max_health > 0 else 0

    # Render HTML template
    template = Template(SCENE_TEMPLATE)
    html_content = template.render(
        title=scene.get('title', 'Adventure Scene'),
        description=scene.get('description', 'Your adventure continues...'),
        summary=scene.get('summary', ''),
        scene_id=scene_id,
        background_color=scene.get('background_color', '#2d5016'),
        theme=scene.get('theme', 'fantasy'),
        health=health,
        max_health=max_health,
        health_percentage=health_percentage,
        gold=gold,
        level=level,
        experience=experience,
        food=food,
        corruption=corruption,
        reputation=reputation,
        items=items,
        items_display=items_display
    )

    # Convert HTML to PNG
    print("DEBUG: Converting HTML to PNG")
    png_data = render_html_to_png(html_content, 800, 600)


    return png_data

def generate_choice_image(choice_type):
    """Generate choice button images using HTML template rendering"""
    current_state = get_current_game_state()
    scene_id = current_state.get('current_scene', 'start')
    scene = get_or_generate_scene(scene_id)

    choice_data = scene.get('choices', {}).get(choice_type, {
        'text': 'Continue Adventure',
        'leads_to': 'start'
    })

    # Color schemes for choices
    color = '#4CAF50' if choice_type == 'a' else '#2196F3'
    hover_color = '#45a049' if choice_type == 'a' else '#1976D2'

    # Render HTML template
    template = Template(CHOICE_TEMPLATE)
    html_content = template.render(
        choice_type=choice_type,
        text=choice_data['text'],
        color=color,
        hover_color=hover_color
    )

    # Convert HTML to PNG
    png_data = render_html_to_png(html_content, 400, 150)

    return png_data

def generate_stats_image():
    """Generate global statistics display image"""
    try:
        # Get stats from DynamoDB
        response = stats_table.scan()
        stats_data = {item['stat_type']: item for item in response.get('Items', [])}
    except:
        stats_data = {}

    width, height = 600, 300
    img = Image.new('RGB', (width, height), '#1a1a2e')
    draw = ImageDraw.Draw(img)

    try:
        title_font = ImageFont.truetype("/opt/fonts/Arial-Bold.ttf", 32)
        text_font = ImageFont.truetype("/opt/fonts/Arial.ttf", 20)
    except:
        title_font = ImageFont.load_default()
        text_font = ImageFont.load_default()

    # Title
    draw.text((50, 30), "*** Adventure Statistics ***", fill='white', font=title_font)

    # Stats
    y_pos = 100
    current_state = get_current_game_state()

    stats_lines = [
        f"* Total Choices Made: {current_state.get('choices_made', 0)}",
        f"* Current Scene: {current_state.get('current_scene', 'start').replace('_', ' ').title()}",
        f"* Last Updated: {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}",
        f"* Adventure Score: {random.randint(1000, 9999)}"
    ]

    for line in stats_lines:
        draw.text((50, y_pos), line, fill='white', font=text_font)
        y_pos += 35

    buffer = BytesIO()
    img.save(buffer, format='PNG', quality=95)
    return buffer.getvalue()

def generate_history_image():
    """Generate recent choices history image"""
    width, height = 600, 200
    img = Image.new('RGB', (width, height), '#2d1b69')
    draw = ImageDraw.Draw(img)
    
    try:
        title_font = ImageFont.truetype("/opt/fonts/Arial-Bold.ttf", 28)
        text_font = ImageFont.truetype("/opt/fonts/Arial.ttf", 18)
    except:
        title_font = ImageFont.load_default()
        text_font = ImageFont.load_default()
    
    draw.text((50, 20), "*** Recent Adventures ***", fill='white', font=title_font)
    
    # Mock recent activity (in production, you'd store actual history)
    recent_choices = [
        "Anonymous adventurer chose the dark path",
        "Someone discovered the crystal cave",
        "A brave soul fought the shadow beast",
        "Explorer found magical treasure"
    ]
    
    y_pos = 70
    for i, choice in enumerate(recent_choices[:4]):
        draw.text((50, y_pos), f"• {choice}", fill='#cccccc', font=text_font)
        y_pos += 25
    
    buffer = BytesIO()
    img.save(buffer, format='PNG', quality=95)
    return buffer.getvalue()


def generate_error_image(error_message):
    """Generate error display image"""
    width, height = 600, 200
    img = Image.new('RGB', (width, height), '#d32f2f')
    draw = ImageDraw.Draw(img)
    
    try:
        font = ImageFont.truetype("/opt/fonts/Arial-Bold.ttf", 24)
    except:
        font = ImageFont.load_default()
    
    draw.text((50, 50), "*** Adventure Temporarily Unavailable ***", fill='white', font=font)
    draw.text((50, 100), "The adventure continues soon...", fill='white', font=font)
    
    buffer = BytesIO()
    img.save(buffer, format='PNG', quality=95)
    return buffer.getvalue()
