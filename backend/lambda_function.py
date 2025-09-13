import json
import boto3
import base64
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
import uuid
import time
from datetime import datetime
import random

# DynamoDB setup
dynamodb = boto3.resource('dynamodb')
game_state_table = dynamodb.Table('adventure-game-state')
stats_table = dynamodb.Table('adventure-stats')
story_scenes_table = dynamodb.Table('adventure-story-scenes')

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
    'player_state': INITIAL_PLAYER_STATE.copy()
}

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
    """Generate a new story scene using procedural generation"""

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
        },
        {
            'title': f'Encounter at {location.title()}',
            'description': f'Before you lies {location}. You notice\\n{object_item} glinting in the distance.',
        },
        {
            'title': f'The {creature.title()} Challenge',
            'description': f'A {creature} emerges from {location}.\\nIt seems to be guarding {object_item}.',
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
    """Generate the main scene image showing current story state"""
    current_state = get_current_game_state()
    scene_id = current_state.get('current_scene', 'start')
    scene = get_or_generate_scene(scene_id)
    
    # Create image canvas
    width, height = 800, 600
    img = Image.new('RGB', (width, height), scene['background_color'])
    draw = ImageDraw.Draw(img)
    
    try:
        # Try to load a nice font, fall back to default if not available
        title_font = ImageFont.truetype("/opt/fonts/Arial-Bold.ttf", 48)
        text_font = ImageFont.truetype("/opt/fonts/Arial.ttf", 24)
        small_font = ImageFont.truetype("/opt/fonts/Arial.ttf", 18)
    except:
        title_font = ImageFont.load_default()
        text_font = ImageFont.load_default()
        small_font = ImageFont.load_default()
    
    # Draw title
    title_bbox = draw.textbbox((0, 0), scene['title'], font=title_font)
    title_width = title_bbox[2] - title_bbox[0]
    draw.text(((width - title_width) // 2, 50), scene['title'], 
              fill='white', font=title_font)
    
    # Draw description
    description_lines = scene['description'].split('\n')
    y_pos = 150
    for line in description_lines:
        line_bbox = draw.textbbox((0, 0), line, font=text_font)
        line_width = line_bbox[2] - line_bbox[0]
        draw.text(((width - line_width) // 2, y_pos), line, 
                  fill='white', font=text_font)
        y_pos += 35
    
    # Draw decorative elements
    draw.ellipse([50, 50, 100, 100], fill='#ffffff20')
    draw.ellipse([700, 500, 750, 550], fill='#ffffff20')
    
    # Draw player stats
    player_state = scene.get('player_state', INITIAL_PLAYER_STATE)
    health = player_state.get('health', 100)
    max_health = player_state.get('max_health', 100)
    gold = player_state.get('gold', 50)
    level = player_state.get('level', 1)
    experience = player_state.get('experience', 0)

    # Player stats overlay
    stats_y = height - 120
    draw.text((50, stats_y), f"Health: {health}/{max_health}", fill='white', font=small_font)
    draw.text((50, stats_y + 20), f"Gold: {gold}", fill='white', font=small_font)
    draw.text((50, stats_y + 40), f"Level: {level} (XP: {experience})", fill='white', font=small_font)

    # Items display
    items = player_state.get('items', [])
    if items:
        items_text = "Items: " + ", ".join([ITEMS.get(item, {}).get('name', item) for item in items[:3]])
        if len(items) > 3:
            items_text += f" (+{len(items)-3} more)"
        draw.text((50, stats_y + 60), items_text, fill='white', font=small_font)
    
    # Convert to bytes
    buffer = BytesIO()
    img.save(buffer, format='PNG', quality=95)
    return buffer.getvalue()

def generate_choice_image(choice_type):
    """Generate choice button images"""
    current_state = get_current_game_state()
    scene_id = current_state.get('current_scene', 'start')
    scene = get_or_generate_scene(scene_id)
    
    choice_data = scene.get('choices', {}).get(choice_type, {
        'text': 'Continue Adventure', 
        'leads_to': 'start'
    })
    
    # Create button image
    width, height = 400, 80
    color = '#4CAF50' if choice_type == 'a' else '#2196F3'
    hover_color = '#45a049' if choice_type == 'a' else '#1976D2'
    
    img = Image.new('RGB', (width, height), color)
    draw = ImageDraw.Draw(img)
    
    # Add button border
    draw.rectangle([2, 2, width-3, height-3], outline='white', width=2)
    
    try:
        font = ImageFont.truetype("/opt/fonts/Arial-Bold.ttf", 20)
    except:
        font = ImageFont.load_default()
    
    # Center the text
    text = choice_data['text']
    text_bbox = draw.textbbox((0, 0), text, font=font)
    text_width = text_bbox[2] - text_bbox[0]
    text_height = text_bbox[3] - text_bbox[1]
    
    x = (width - text_width) // 2
    y = (height - text_height) // 2
    
    draw.text((x, y), text, fill='white', font=font)
    
    # Add choice indicator
    choice_label = f"Choice {choice_type.upper()}"
    draw.text((10, 10), choice_label, fill='white', font=font)
    
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
