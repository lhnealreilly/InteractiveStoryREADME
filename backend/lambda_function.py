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

# Game configuration
STORY_CONFIG = {
    "scenes": {
        "start": {
            "title": "The Mysterious Forest",
            "description": "You find yourself at the edge of an ancient forest.\nTwo paths diverge before you. Choose wisely...",
            "background_color": "#2d5016",
            "choices": {
                "a": {"text": "Take the shadowy left path", "leads_to": "dark_path"},
                "b": {"text": "Follow the sunlit right path", "leads_to": "light_path"}
            }
        },
        "dark_path": {
            "title": "The Shadow Realm",
            "description": "The path grows darker. Strange sounds echo\naround you. A glowing cave appears ahead.",
            "background_color": "#1a1a2e",
            "choices": {
                "a": {"text": "Enter the glowing cave", "leads_to": "crystal_cave"},
                "b": {"text": "Continue on the dark path", "leads_to": "monster_encounter"}
            }
        },
        "light_path": {
            "title": "The Sunlit Meadow",
            "description": "Sunlight dances through the trees. You hear\nthe sound of running water nearby.",
            "background_color": "#4a7c59",
            "choices": {
                "a": {"text": "Follow the sound of water", "leads_to": "magic_river"},
                "b": {"text": "Rest in the peaceful meadow", "leads_to": "fairy_encounter"}
            }
        },
        "crystal_cave": {
            "title": "The Crystal Cave",
            "description": "Magnificent crystals illuminate the cavern.\nAn ancient treasure chest sits in the center.",
            "background_color": "#4a148c",
            "choices": {
                "a": {"text": "Open the treasure chest", "leads_to": "treasure_found"},
                "b": {"text": "Examine the crystals", "leads_to": "magic_discovery"}
            }
        },
        "monster_encounter": {
            "title": "The Shadow Beast",
            "description": "A fearsome shadow creature blocks your path!\nYour heart pounds as you decide your fate.",
            "background_color": "#b71c1c",
            "choices": {
                "a": {"text": "Fight the creature", "leads_to": "epic_battle"},
                "b": {"text": "Try to sneak past", "leads_to": "stealth_success"}
            }
        },
        "magic_river": {
            "title": "The Enchanted River",
            "description": "The water glows with magical energy.\nA wise old turtle emerges from the depths.",
            "background_color": "#006064",
            "choices": {
                "a": {"text": "Speak with the turtle", "leads_to": "wisdom_gained"},
                "b": {"text": "Drink the magical water", "leads_to": "power_boost"}
            }
        },
        "fairy_encounter": {
            "title": "The Fairy Glade",
            "description": "Tiny lights dance around you as forest\nfairies emerge from the flowers.",
            "background_color": "#7b1fa2",
            "choices": {
                "a": {"text": "Ask for their blessing", "leads_to": "fairy_blessing"},
                "b": {"text": "Offer them a gift", "leads_to": "fairy_friendship"}
            }
        }
    }
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
                    'Location': 'https://github.com/user/interactive-adventure#-the-adventure-begins',
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

def process_choice(choice):
    """Process a player's choice and update game state"""
    current_state = get_current_game_state()
    current_scene_id = current_state.get('current_scene', 'start')
    
    scene = STORY_CONFIG['scenes'].get(current_scene_id, STORY_CONFIG['scenes']['start'])
    
    if choice in scene.get('choices', {}):
        next_scene = scene['choices'][choice]['leads_to']
        update_game_state(next_scene)

def generate_scene_image():
    """Generate the main scene image showing current story state"""
    current_state = get_current_game_state()
    scene_id = current_state.get('current_scene', 'start')
    scene = STORY_CONFIG['scenes'].get(scene_id, STORY_CONFIG['scenes']['start'])
    
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
    
    # Draw game stats
    stats_text = f"Total Choices Made: {current_state.get('choices_made', 0)}"
    draw.text((50, height - 50), stats_text, fill='white', font=small_font)
    
    # Convert to bytes
    buffer = BytesIO()
    img.save(buffer, format='PNG', quality=95)
    return buffer.getvalue()

def generate_choice_image(choice_type):
    """Generate choice button images"""
    current_state = get_current_game_state()
    scene_id = current_state.get('current_scene', 'start')
    scene = STORY_CONFIG['scenes'].get(scene_id, STORY_CONFIG['scenes']['start'])
    
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

# DynamoDB table creation helper (run once during setup)
def create_tables():
    """Create necessary DynamoDB tables (call once during deployment)"""
    dynamodb = boto3.resource('dynamodb')
    
    # Game state table
    try:
        game_table = dynamodb.create_table(
            TableName='adventure-game-state',
            KeySchema=[
                {'AttributeName': 'game_id', 'KeyType': 'HASH'}
            ],
            AttributeDefinitions=[
                {'AttributeName': 'game_id', 'AttributeType': 'S'}
            ],
            BillingMode='PAY_PER_REQUEST'
        )
    except:
        pass  # Table might already exist
    
    # Stats table
    try:
        stats_table = dynamodb.create_table(
            TableName='adventure-stats',
            KeySchema=[
                {'AttributeName': 'stat_type', 'KeyType': 'HASH'}
            ],
            AttributeDefinitions=[
                {'AttributeName': 'stat_type', 'AttributeType': 'S'}
            ],
            BillingMode='PAY_PER_REQUEST'
        )
    except:
        pass  # Table might already exist