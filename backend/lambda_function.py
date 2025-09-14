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

load_dotenv()

# DynamoDB setup
dynamodb = boto3.resource('dynamodb')
game_state_table = dynamodb.Table('adventure-game-state')
stats_table = dynamodb.Table('adventure-stats')
story_scenes_table = dynamodb.Table('adventure-story-scenes')

# Google Gemini setup
GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY')
genai_client = genai.Client(api_key=GOOGLE_API_KEY)

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

# Player state configuration
INITIAL_PLAYER_STATE = {
    'health': 100,
    'max_health': 100,
    'gold': 50,
    'items': ['basic_sword', 'leather_armor'],
    'level': 1,
    'experience': 0
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
    'player_state': INITIAL_PLAYER_STATE.copy(),
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
            background: #0d1117;
        }

        body {
            width: 800px;
            height: 600px;
            background: linear-gradient(135deg, #0d1117, {{ background_color }}99);
            font-family: 'Cormorant Garamond', serif;
            color: #ffffff;
            position: relative;
            overflow: hidden;
        }

        .scene-container {
            padding: 40px;
            height: 100%;
            display: flex;
            flex-direction: column;
            justify-content: space-between;
            position: relative;
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

        <div class="stats-overlay">
            <div class="stat-line">
                <span class="stat-icon">❤️</span>
                Health: {{ health }}/{{ max_health }}
                <div class="health-bar">
                    <div class="health-fill"></div>
                </div>
            </div>
            <div class="stat-line">
                <span class="stat-icon">💰</span>
                Gold: {{ gold }}
            </div>
            <div class="stat-line">
                <span class="stat-icon">⭐</span>
                Level: {{ level }} (XP: {{ experience }})
            </div>
            {% if items %}
            <div class="stat-line">
                <span class="stat-icon">🎒</span>
                Items: {{ items_display }}
            </div>
            {% endif %}
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
            height: 80px;
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
    
    # Extract path and query parameters
    path = event.get('path', '/')
    query_params = event.get('queryStringParameters') or {}
    
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
            image_data = generate_scene_image()
        elif path.endswith('/choice/a') or path.endswith('/choice/b'):
            choice = 'a' if path.endswith('/a') else 'b'
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
            image_data = generate_choice_image('a')
        elif path.endswith('/option/b.png'):
            image_data = generate_choice_image('b')
        elif path.endswith('/stats.png'):
            image_data = generate_stats_image()
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
    try:
        response = game_state_table.get_item(Key={'game_id': 'global'})
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

    # Handle initial scene specially
    if scene_id == 'start':
        return INITIAL_SCENE

    try:
        # Try to get existing scene from DynamoDB
        response = story_scenes_table.get_item(Key={'scene_id': scene_id})
        if 'Item' in response:
            return response['Item']
    except Exception as e:
        print(f"Error fetching scene {scene_id}: {e}")

    # Generate new scene if not found
    print(f"Generating new scene: {scene_id}")
    return generate_new_scene(scene_id, theme, previous_scene, choice_made)

def generate_new_scene(scene_id, theme='fantasy', previous_scene=None, choice_made=None):
    """Generate a new story scene using Gemini AI with fallback to procedural generation"""

    # Try Gemini generation first
    gemini_scene = generate_scene_with_gemini(scene_id, theme, previous_scene, choice_made)

    if gemini_scene:
        # Add player state to Gemini-generated scene
        player_state = generate_player_state_for_scene(scene_id, theme, previous_scene, choice_made)
        gemini_scene['player_state'] = player_state

        # Save to DynamoDB
        try:
            story_scenes_table.put_item(Item=gemini_scene)
            print(f"Saved Gemini-generated scene: {scene_id}")
        except Exception as e:
            print(f"Error saving Gemini scene {scene_id}: {e}")

        return gemini_scene

    # Fallback to original procedural generation
    print(f"Falling back to procedural generation for scene: {scene_id}")

    # Get theme data
    theme_data = STORY_THEMES.get(theme, STORY_THEMES['fantasy'])

    # Generate scene content
    location = random.choice(theme_data['locations'])
    creature = random.choice(theme_data['creatures'])
    object_item = random.choice(theme_data['objects'])
    background_color = random.choice(theme_data['colors'])

    # Create story variations based on scene patterns
    scene_patterns = [
        {
            'title': f'The {location.title()}',
            'description': f'You arrive at {location}. A {creature} watches\\nyou from the shadows. What do you do?',
            'summary': f'You venture deeper into the adventure and encounter {location}.'
        },
        {
            'title': f'Encounter at {location.title()}',
            'description': f'Before you lies {location}. You notice\\n{object_item} glinting in the distance.',
            'summary': f'Your journey leads you to {location} where you spot something interesting.'
        },
        {
            'title': f'The {creature.title()} Challenge',
            'description': f'A {creature} emerges from {location}.\\nIt seems to be guarding {object_item}.',
            'summary': f'A {creature} appears before you, presenting a new challenge.'
        }
    ]

    pattern = random.choice(scene_patterns)

    # Generate choice options based on theme
    choice_patterns = {
        'fantasy': [
            ('Cast a spell', 'Use magic'),
            ('Draw your sword', 'Attack directly'),
            ('Speak peacefully', 'Try diplomacy'),
            ('Search for clues', 'Investigate further'),
            ('Take the treasure', 'Claim the reward'),
            ('Proceed cautiously', 'Move forward')
        ],
        'sci_fi': [
            ('Scan with tricorder', 'Use technology'),
            ('Fire plasma weapon', 'Attack with energy'),
            ('Establish contact', 'Attempt communication'),
            ('Access database', 'Check records'),
            ('Activate shield', 'Defensive action'),
            ('Navigate around', 'Find alternate route')
        ],
        'mystery': [
            ('Examine evidence', 'Investigate closely'),
            ('Question suspect', 'Interrogate person'),
            ('Follow the trail', 'Pursue lead'),
            ('Search the area', 'Look for clues'),
            ('Call for backup', 'Get assistance'),
            ('Confront directly', 'Direct approach')
        ]
    }

    theme_choices = choice_patterns.get(theme, choice_patterns['fantasy'])
    selected_choices = random.sample(theme_choices, 2)

    # Generate next scene IDs
    scene_num = len(scene_id)  # Simple way to create unique IDs
    next_scene_a = f'{theme}_{scene_num}a_{random.randint(1000, 9999)}'
    next_scene_b = f'{theme}_{scene_num}b_{random.randint(1000, 9999)}'

    # Generate player state based on previous scene and choice
    player_state = generate_player_state_for_scene(scene_id, theme, previous_scene, choice_made)

    new_scene = {
        'scene_id': scene_id,
        'title': pattern['title'],
        'description': pattern['description'],
        'summary': pattern['summary'],
        'background_color': background_color,
        'choices': {
            'a': {'text': selected_choices[0][0], 'leads_to': next_scene_a},
            'b': {'text': selected_choices[1][0], 'leads_to': next_scene_b}
        },
        'theme': theme,
        'created_at': datetime.now().isoformat(),
        'player_state': player_state
    }

    # Save to DynamoDB
    try:
        story_scenes_table.put_item(Item=new_scene)
        print(f"Saved new scene: {scene_id}")
    except Exception as e:
        print(f"Error saving scene {scene_id}: {e}")

    return new_scene

def generate_player_state_for_scene(scene_id, theme, previous_scene=None, choice_made=None):
    """Generate deterministic player state based on previous state and action taken"""

    # Start with initial state if no previous scene
    if previous_scene is None:
        return INITIAL_PLAYER_STATE.copy()

    # Get previous player state
    prev_state = previous_scene.get('player_state', INITIAL_PLAYER_STATE).copy()

    # Determine action type based on choice text and theme
    choice_text = previous_scene.get('choices', {}).get(choice_made, {}).get('text', '').lower()

    # Action patterns that affect player state
    action_effects = {
        # Combat actions
        'fight': {'health': -15, 'gold': 30, 'experience': 20},
        'attack': {'health': -15, 'gold': 30, 'experience': 20},
        'sword': {'health': -10, 'gold': 25, 'experience': 15},
        'weapon': {'health': -12, 'gold': 28, 'experience': 18},

        # Peaceful actions
        'speak': {'health': 5, 'gold': 10, 'experience': 15},
        'peaceful': {'health': 5, 'gold': 10, 'experience': 15},
        'diplomacy': {'health': 5, 'gold': 15, 'experience': 20},

        # Exploration actions
        'search': {'health': 0, 'gold': 20, 'experience': 10},
        'investigate': {'health': -5, 'gold': 15, 'experience': 25},
        'examine': {'health': 0, 'gold': 5, 'experience': 15},

        # Treasure/reward actions
        'treasure': {'health': 0, 'gold': 50, 'experience': 15},
        'take': {'health': 0, 'gold': 35, 'experience': 10},
        'claim': {'health': 0, 'gold': 45, 'experience': 12},

        # Magic actions
        'spell': {'health': 10, 'gold': 5, 'experience': 30},
        'magic': {'health': 10, 'gold': 5, 'experience': 30},

        # Rest/healing actions
        'rest': {'health': 25, 'gold': 0, 'experience': 5},
        'drink': {'health': 30, 'gold': -5, 'experience': 5},

        # Risky actions
        'continue': {'health': -8, 'gold': 12, 'experience': 8},
        'proceed': {'health': -5, 'gold': 8, 'experience': 12}
    }

    # Find matching action effect
    effect = {'health': 0, 'gold': 0, 'experience': 0}
    for keyword, modifier in action_effects.items():
        if keyword in choice_text:
            effect = modifier
            break

    # Apply base scene progression (small random but deterministic changes)
    scene_hash = hash(scene_id) % 100
    base_effect = {
        'health': -2 + (scene_hash % 5),  # -2 to +2
        'gold': 5 + (scene_hash % 10),   # 5 to 14
        'experience': 3 + (scene_hash % 8)  # 3 to 10
    }

    # Combine effects
    new_state = prev_state.copy()
    new_state['health'] = max(0, min(new_state['max_health'],
                                   new_state['health'] + effect['health'] + base_effect['health']))
    new_state['gold'] = max(0, new_state['gold'] + effect['gold'] + base_effect['gold'])
    new_state['experience'] += effect['experience'] + base_effect['experience']

    # Level up logic
    exp_needed = new_state['level'] * 100
    if new_state['experience'] >= exp_needed:
        new_state['level'] += 1
        new_state['max_health'] += 20
        new_state['health'] = new_state['max_health']  # Full heal on level up

        # Add items based on level and theme
        new_items = get_level_items(new_state['level'], theme)
        for item in new_items:
            if item not in new_state['items']:
                new_state['items'].append(item)

    return new_state

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

def generate_scene_with_gemini(scene_id, theme, previous_scene=None, choice_made=None):
    """Use Google Gemini to generate a new scene with structured output"""

    try:
        # Build context from previous scene
        if previous_scene and choice_made:
            prev_title = previous_scene.get('title', 'Unknown Scene')
            prev_description = previous_scene.get('description', '')
            choice_text = previous_scene.get('choices', {}).get(choice_made, {}).get('text', 'made a choice')
            player_state = previous_scene.get('player_state', INITIAL_PLAYER_STATE)

            context = f"""
Previous scene: "{prev_title}"
Previous description: {prev_description}
Player chose: "{choice_text}"
Current player state: Health {player_state.get('health', 100)}/{player_state.get('max_health', 100)},
Gold {player_state.get('gold', 50)}, Level {player_state.get('level', 1)},
Items: {', '.join(player_state.get('items', []))}
"""
        else:
            context = "This is the beginning of a new adventure."

        # Get theme information
        theme_data = STORY_THEMES.get(theme, STORY_THEMES['fantasy'])
        locations = ', '.join(theme_data['locations'])
        creatures = ', '.join(theme_data['creatures'])
        objects = ', '.join(theme_data['objects'])

        prompt = f"""
You are creating an interactive adventure scene for a {theme} themed story.

{context}

Create a new scene that continues the story logically. The scene should:
1. Have an engaging title
2. Provide a vivid description (2-3 sentences, use \\n for line breaks)
3. Include a summary of what happened between the previous scene and this one (e.g., "You swing your sword at the phoenix, it shoots flames at you")
4. Choose an appropriate background color from the theme palette: {', '.join(theme_data['colors'])}
5. Offer two meaningful choices that fit the {theme} theme
6. Use these theme elements when appropriate:
   - Locations: {locations}
   - Creatures: {creatures}
   - Objects: {objects}

Make the story engaging and maintain narrative consistency with the previous events.
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
        return None

def process_choice(choice):
    """Process a player's choice and update game state"""
    current_state = get_current_game_state()
    current_scene_id = current_state.get('current_scene', 'start')

    scene = get_or_generate_scene(current_scene_id)

    if choice in scene.get('choices', {}):
        next_scene_id = scene['choices'][choice]['leads_to']

        # Ensure the next scene exists or generate it with player state context
        next_scene = get_or_generate_scene(next_scene_id, scene.get('theme', 'fantasy'), scene, choice)

        # Check if player died (health <= 0)
        if next_scene.get('player_state', {}).get('health', 100) <= 0:
            # Reset to start if player died
            update_game_state('start')
        else:
            update_game_state(next_scene_id)

def generate_scene_image():
    """Generate the main scene image using HTML template rendering"""
    current_state = get_current_game_state()
    scene_id = current_state.get('current_scene', 'start')
    scene = get_or_generate_scene(scene_id)

    # Get player state
    player_state = scene.get('player_state', INITIAL_PLAYER_STATE)
    health = player_state.get('health', 100)
    max_health = player_state.get('max_health', 100)
    gold = player_state.get('gold', 50)
    level = player_state.get('level', 1)
    experience = player_state.get('experience', 0)
    items = player_state.get('items', [])

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
        items=items,
        items_display=items_display
    )

    # Convert HTML to PNG
    png_data = render_html_to_png(html_content, 800, 600)

    # Fallback to PIL if HTML conversion fails
    if png_data is None:
        return generate_scene_image_fallback(scene, current_state)

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
    png_data = render_html_to_png(html_content, 400, 80)

    # Fallback to PIL if HTML conversion fails
    if png_data is None:
        return generate_choice_image_fallback(choice_type, choice_data, color)

    return png_data

def generate_scene_image_fallback(scene, current_state):
    """Fallback scene image generation using PIL"""
    width, height = 800, 600
    img = Image.new('RGB', (width, height), scene.get('background_color', '#2d5016'))
    draw = ImageDraw.Draw(img)

    try:
        title_font = ImageFont.truetype("/opt/fonts/Arial-Bold.ttf", 36)
        text_font = ImageFont.truetype("/opt/fonts/Arial.ttf", 20)
        small_font = ImageFont.truetype("/opt/fonts/Arial.ttf", 16)
    except:
        title_font = ImageFont.load_default()
        text_font = ImageFont.load_default()
        small_font = ImageFont.load_default()

    # Draw title
    title = scene.get('title', 'Adventure Scene')
    title_bbox = draw.textbbox((0, 0), title, font=title_font)
    title_width = title_bbox[2] - title_bbox[0]
    draw.text(((width - title_width) // 2, 50), title, fill='white', font=title_font)

    # Draw description
    description = scene.get('description', 'Your adventure continues...')
    words = description.replace('\n', ' ').split()
    lines = []
    current_line = []

    for word in words:
        test_line = ' '.join(current_line + [word])
        test_bbox = draw.textbbox((0, 0), test_line, font=text_font)
        if test_bbox[2] - test_bbox[0] > width - 100:
            if current_line:
                lines.append(' '.join(current_line))
                current_line = [word]
            else:
                lines.append(word)
        else:
            current_line.append(word)

    if current_line:
        lines.append(' '.join(current_line))

    y_pos = 200
    for line in lines:
        line_bbox = draw.textbbox((0, 0), line, font=text_font)
        line_width = line_bbox[2] - line_bbox[0]
        draw.text(((width - line_width) // 2, y_pos), line, fill='white', font=text_font)
        y_pos += 30

    # Draw simple stats
    player_state = scene.get('player_state', INITIAL_PLAYER_STATE)
    stats_text = f"Health: {player_state.get('health', 100)}/{player_state.get('max_health', 100)} | Gold: {player_state.get('gold', 50)} | Level: {player_state.get('level', 1)}"
    draw.text((50, height - 50), stats_text, fill='white', font=small_font)

    buffer = BytesIO()
    img.save(buffer, format='PNG', quality=95)
    return buffer.getvalue()

def generate_choice_image_fallback(choice_type, choice_data, color):
    """Fallback choice image generation using PIL"""
    width, height = 400, 80
    img = Image.new('RGB', (width, height), color)
    draw = ImageDraw.Draw(img)

    draw.rectangle([2, 2, width-3, height-3], outline='white', width=2)

    try:
        font = ImageFont.truetype("/opt/fonts/Arial-Bold.ttf", 18)
    except:
        font = ImageFont.load_default()

    text = choice_data['text']
    text_bbox = draw.textbbox((0, 0), text, font=font)
    text_width = text_bbox[2] - text_bbox[0]
    text_height = text_bbox[3] - text_bbox[1]

    x = (width - text_width) // 2
    y = (height - text_height) // 2

    draw.text((x, y), text, fill='white', font=font)

    buffer = BytesIO()
    img.save(buffer, format='PNG', quality=95)
    return buffer.getvalue()

def generate_stats_image():
    """Generate statistics display image"""
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
