"""
Game State Manager - Consequence-driven adventure game mechanics
Generates meaningful AI prompts based on player state and choice consequences
"""

import random
from typing import Dict, List, Tuple, Optional
from enum import Enum
from dataclasses import dataclass, asdict
import json


class CrisisLevel(Enum):
    THRIVING = "thriving"
    STABLE = "stable"
    STRUGGLING = "struggling"
    DESPERATE = "desperate"
    CRITICAL = "critical"


class ReputationType(Enum):
    UNKNOWN = "unknown"
    HERO = "hero"
    DIPLOMAT = "diplomat"
    MERCHANT = "merchant"
    THIEF = "thief"
    MURDERER = "murderer"
    FEARED = "feared"
    CORRUPTED = "corrupted"


@dataclass
class PlayerState:
    health: int = 100
    max_health: int = 100
    gold: int = 10
    food: int = 3
    items: List[str] = None
    level: int = 1
    experience: int = 0
    corruption: int = 0
    reputation: str = ReputationType.UNKNOWN.value
    deaths: int = 0
    scene_history: List[str] = None
    curses: List[str] = None
    permanent_injuries: List[str] = None
    last_choice_consequences: Dict = None

    def __post_init__(self):
        if self.items is None:
            self.items = ['rusty_dagger']
        if self.scene_history is None:
            self.scene_history = []
        if self.curses is None:
            self.curses = []
        if self.permanent_injuries is None:
            self.permanent_injuries = []
        if self.last_choice_consequences is None:
            self.last_choice_consequences = {}


class GameStateManager:
    """Manages player state and generates consequence-aware AI prompts"""

    def __init__(self):
        self.action_consequences = {
            # Combat actions - high risk/reward
            'fight': {
                'health': lambda s: -random.randint(20, 40),
                'gold': lambda s: random.randint(15, 50) if s.health > 30 else 0,
                'experience': 25,
                'food': -1,
                'reputation_change': ReputationType.FEARED.value,
                'description': 'violent confrontation'
            },
            'attack': {
                'health': lambda s: -random.randint(15, 35),
                'gold': lambda s: random.randint(10, 40),
                'experience': 20,
                'corruption': 2,
                'description': 'aggressive action'
            },
            'kill': {
                'health': lambda s: -random.randint(25, 50),
                'corruption': 5,
                'gold': lambda s: random.randint(20, 60),
                'reputation_change': ReputationType.MURDERER.value,
                'description': 'lethal violence'
            },

            # Peaceful actions - safer but lower rewards
            'speak': {
                'health': 5,
                'gold': lambda s: random.randint(5, 15),
                'experience': 10,
                'reputation_change': ReputationType.DIPLOMAT.value,
                'description': 'diplomatic approach'
            },
            'negotiate': {
                'gold': lambda s: random.randint(10, 25),
                'experience': 20,
                'reputation_change': ReputationType.DIPLOMAT.value,
                'description': 'peaceful negotiation'
            },
            'help': {
                'health': -5,
                'experience': 15,
                'corruption': -2,
                'reputation_change': ReputationType.HERO.value,
                'description': 'selfless assistance'
            },

            # Survival actions
            'rest': {
                'health': lambda s: min(25, s.max_health - s.health),
                'food': -2,
                'experience': 5,
                'description': 'recuperation'
            },
            'eat': {
                'health': lambda s: 10 if s.food > 0 else -15,
                'food': lambda s: -1 if s.food > 0 else 0,
                'description': 'sustenance'
            },

            # Exploration actions
            'search': {
                'health': lambda s: -random.randint(0, 15),
                'gold': lambda s: random.randint(0, 30),
                'experience': 10,
                'food': lambda s: -1 if random.random() < 0.3 else 0,
                'description': 'risky exploration'
            },

            # Greed actions
            'steal': {
                'gold': lambda s: random.randint(20, 60),
                'corruption': 5,
                'reputation_change': ReputationType.THIEF.value,
                'description': 'criminal activity'
            },

            # Magic actions
            'magic': {
                'health': lambda s: random.randint(-15, 25),
                'corruption': lambda s: random.randint(2, 8),
                'experience': 35,
                'description': 'arcane manipulation'
            },
        }

    def get_crisis_level(self, state: PlayerState) -> CrisisLevel:
        """Determine the player's current crisis level"""
        health_ratio = state.health / state.max_health

        # Critical - immediate death risk
        if health_ratio <= 0.25 or state.food == 0 or len(state.curses) >= 3:
            return CrisisLevel.CRITICAL

        # Desperate - multiple serious problems
        if (health_ratio <= 0.4 and state.food <= 1) or state.corruption >= 70:
            return CrisisLevel.DESPERATE

        # Struggling - single serious problem
        if health_ratio <= 0.5 or state.food <= 1 or state.gold <= 5 or state.corruption >= 50:
            return CrisisLevel.STRUGGLING

        # Stable - doing okay
        if health_ratio >= 0.7 and state.food >= 2 and state.gold >= 20:
            return CrisisLevel.STABLE

        # Thriving - excellent condition
        return CrisisLevel.THRIVING

    def get_resource_status(self, state: PlayerState) -> Dict[str, str]:
        """Analyze resource scarcity for AI context"""
        status = {}

        if state.health <= 30:
            status['health'] = 'CRITICAL - near death'
        elif state.health <= 60:
            status['health'] = 'LOW - badly injured'
        else:
            status['health'] = 'GOOD - healthy'

        if state.food == 0:
            status['food'] = 'STARVING - immediate danger'
        elif state.food == 1:
            status['food'] = 'HUNGRY - need food soon'
        else:
            status['food'] = 'FED - adequate supplies'

        if state.gold <= 5:
            status['gold'] = 'POOR - cannot afford basic items'
        elif state.gold <= 20:
            status['gold'] = 'STRUGGLING - limited purchasing power'
        else:
            status['gold'] = 'WEALTHY - can afford most things'

        if state.corruption >= 70:
            status['corruption'] = 'DAMNED - soul nearly lost'
        elif state.corruption >= 40:
            status['corruption'] = 'CORRUPTED - moral decay spreading'
        elif state.corruption >= 20:
            status['corruption'] = 'TAINTED - darkness creeping in'
        else:
            status['corruption'] = 'PURE - soul intact'

        return status

    def generate_consequence_context(self, state: PlayerState, previous_choice: str = None) -> str:
        """Generate detailed context about current player state for AI"""
        crisis = self.get_crisis_level(state)
        resources = self.get_resource_status(state)

        context = f"""
PLAYER STATE ANALYSIS:
Crisis Level: {crisis.value.upper()}
Health: {state.health}/{state.max_health} ({resources['health']})
Food: {state.food} ({resources['food']})
Gold: {state.gold} ({resources['gold']})
Corruption: {state.corruption}/100 ({resources['corruption']})
Reputation: {state.reputation.upper()}
Level: {state.level} (XP: {state.experience})

ACTIVE PROBLEMS:
"""

        problems = []
        if state.food == 0:
            problems.append("- STARVING: Player will die soon without food")
        if state.health <= 25:
            problems.append("- NEAR DEATH: Any combat could be fatal")
        if state.gold <= 5:
            problems.append("- BROKE: Cannot afford basic necessities")
        if state.corruption >= 50:
            problems.append("- CORRUPTED: Dark choices affecting all interactions")
        if state.curses:
            problems.append(f"- CURSED: {', '.join(state.curses)}")
        if state.permanent_injuries:
            problems.append(f"- INJURED: {', '.join(state.permanent_injuries)}")

        if problems:
            context += '\n'.join(problems)
        else:
            context += "- No immediate threats"

        if previous_choice:
            context += f"\n\nPREVIOUS ACTION: {previous_choice}"
            if state.last_choice_consequences:
                context += f"\nCONSEQUENCES: {state.last_choice_consequences}"

        return context

    def generate_scene_prompt(self, state: PlayerState, theme: str, previous_scene: Dict = None, choice_made: str = None) -> str:
        """Generate a consequence-aware prompt for AI scene generation"""

        crisis = self.get_crisis_level(state)
        context = self.generate_consequence_context(state, choice_made)

        # Base prompt structure
        prompt = f"""You are creating an interactive adventure scene for a {theme} themed story.

{context}

SCENE REQUIREMENTS:
"""

        # Crisis-specific scene requirements
        if crisis == CrisisLevel.CRITICAL:
            prompt += """
SURVIVAL MODE - Player is in immediate mortal danger:
- Create life-or-death scenarios where wrong choice = death
- Make resources extremely scarce and expensive
- Show NPCs exploiting player's desperate state
- Offer high-risk/high-reward options vs safe but costly alternatives
- Emphasize time pressure and urgency
"""
        elif crisis == CrisisLevel.DESPERATE:
            prompt += """
DESPERATION MODE - Player has serious problems:
- Multiple threats affecting player simultaneously
- Resources are scarce and overpriced
- NPCs should notice player's weakness
- Choices should involve difficult moral compromises
- Show consequences of previous poor decisions
"""
        elif crisis == CrisisLevel.STRUGGLING:
            prompt += """
CHALLENGE MODE - Player faces significant obstacles:
- Present meaningful but manageable risks
- Make resources available but at fair cost
- NPCs react neutrally but opportunities exist
- Balance risk vs reward carefully
- Show paths to improvement requiring sacrifice
"""
        elif crisis == CrisisLevel.STABLE:
            prompt += """
GROWTH MODE - Player is doing well:
- Present opportunities for advancement
- Allow player to help others or pursue goals
- Resources available at normal prices
- Focus on character development choices
- Introduce new challenges appropriate to player's level
"""
        else:  # THRIVING
            prompt += """
POWER MODE - Player is thriving:
- Present choices about using power responsibly
- Allow player to affect larger events/NPCs
- Introduce moral complexity and corruption temptations
- Show how power can corrupt or inspire
- Create scenarios where player's reputation matters
"""

        # Reputation-specific NPC behavior
        reputation_effects = {
            ReputationType.HERO.value: "NPCs trust you, offer help, but expect heroic behavior",
            ReputationType.MURDERER.value: "NPCs fear you, demand payment upfront, some flee",
            ReputationType.THIEF.value: "NPCs guard possessions, watch you suspiciously",
            ReputationType.DIPLOMAT.value: "NPCs respect you, offer information and fair deals",
            ReputationType.CORRUPTED.value: "NPCs sense darkness, react with fear or disgust",
            ReputationType.FEARED.value: "NPCs submit to intimidation but hate you"
        }

        if state.reputation in reputation_effects:
            prompt += f"\nNPC BEHAVIOR: {reputation_effects[state.reputation]}\n"

        # Resource economy guidance
        prompt += f"""
RESOURCE ECONOMY:
- Food costs 5-15 gold (player has {state.gold})
- Healing costs 20-50 gold
- Magic services cost 30-100 gold
- Make prices reflect player's desperate state if applicable

CHOICE CONSEQUENCES:
Generate exactly two choices where consequences match current state:
"""

        # Choice consequence templates based on crisis level
        if crisis in [CrisisLevel.CRITICAL, CrisisLevel.DESPERATE]:
            prompt += """
Choice A: HIGH RISK (20-40 health loss possible) / HIGH REWARD (significant gold/items)
Choice B: SAFE OPTION (costs gold/food) / SURVIVAL FOCUSED (minimal gain but safer)
"""
        else:
            prompt += """
Choice A: MODERATE RISK (10-20 health loss) / GOOD REWARD (fair gold/experience gain)
Choice B: LOW RISK (minor costs) / MODEST REWARD (small but reliable gain)
"""

        prompt += """
SCENE GENERATION:
1. Create engaging title reflecting current crisis level
2. Write vivid description (2-3 sentences, use \\n for line breaks)
3. Include summary of what happened since last scene
4. Choose appropriate background color for mood
5. Make choices feel meaningfully different
6. Show how player's condition affects the situation
7. Reflect reputation in NPC interactions
8. Make resource scarcity feel real and impactful

Remember: This player's choices have led to their current state. Show consequences!
"""

        return prompt

    #TODO fix the choice system + consequences system to be consistent and make sense
    def apply_choice_consequences(self, state: PlayerState, choice_text: str, scene_id: str) -> PlayerState:
        return state
        """Apply consequences of a choice to player state"""
        new_state = PlayerState(**asdict(state))

        # Automatic survival costs
        new_state.food = max(0, new_state.food - 1)

        # Starvation damage
        if new_state.food <= 0:
            starvation_damage = random.randint(15, 25)
            new_state.health = max(0, new_state.health - starvation_damage)
            new_state.last_choice_consequences = {
                'starvation_damage': starvation_damage,
                'message': 'Starvation weakens you severely'
            }
            if 'starving' not in new_state.curses:
                new_state.curses.append('starving')

        # Apply choice-specific consequences
        choice_lower = choice_text.lower()
        consequences = {}

        for keyword, effects in self.action_consequences.items():
            if keyword in choice_lower:
                for effect_type, effect_value in effects.items():
                    if effect_type == 'description':
                        continue

                    if callable(effect_value):
                        value = effect_value(new_state)
                    else:
                        value = effect_value

                    if effect_type == 'health':
                        old_health = new_state.health
                        new_state.health = max(0, min(new_state.max_health, new_state.health + value))
                        consequences['health'] = new_state.health - old_health
                    elif effect_type == 'gold':
                        old_gold = new_state.gold
                        new_state.gold = max(0, new_state.gold + value)
                        consequences['gold'] = new_state.gold - old_gold
                    elif effect_type == 'food':
                        old_food = new_state.food
                        new_state.food = max(0, new_state.food + value)
                        consequences['food'] = new_state.food - old_food
                    elif effect_type == 'experience':
                        new_state.experience += value
                        consequences['experience'] = value
                    elif effect_type == 'corruption':
                        old_corruption = new_state.corruption
                        new_state.corruption = max(0, min(100, new_state.corruption + value))
                        consequences['corruption'] = new_state.corruption - old_corruption
                    elif effect_type == 'reputation_change':
                        old_rep = new_state.reputation
                        new_state.reputation = value
                        consequences['reputation'] = f'{old_rep} -> {value}'

                new_state.last_choice_consequences = consequences
                break

        # Critical failure from high corruption
        if new_state.corruption > 60 and random.random() < 0.15:
            corruption_damage = new_state.health // 3
            new_state.health = max(1, new_state.health - corruption_damage)
            consequences['corruption_damage'] = corruption_damage

        # Add to scene history
        new_state.scene_history.append(scene_id)
        if len(new_state.scene_history) > 10:
            new_state.scene_history = new_state.scene_history[-10:]

        # Level up logic
        exp_needed = new_state.level * 150
        if new_state.experience >= exp_needed:
            new_state.level += 1

            # Corruption affects level benefits
            if new_state.corruption < 25:
                health_gain = 25
                new_state.max_health += health_gain
                new_state.health = new_state.max_health
            elif new_state.corruption < 50:
                health_gain = 15
                new_state.max_health += health_gain
                new_state.health = min(new_state.max_health, new_state.health + 20)
            else:
                health_gain = 5
                new_state.max_health += health_gain
                new_state.health = min(new_state.max_health, new_state.health + 10)

            consequences['level_up'] = {'new_level': new_state.level, 'health_gain': health_gain}

        return new_state

    def is_dead(self, state: PlayerState) -> bool:
        """Check if player has died"""
        return state.health <= 0

    def handle_death(self, state: PlayerState) -> PlayerState:
        """Handle player death - reset to fresh start for isolated runs"""
        # Each run is completely isolated, so death just resets to initial state
        # Deaths are tracked in external stats table, not player state
        fresh_state = PlayerState()

        # Only carry over the death count for this specific run
        fresh_state.deaths = state.deaths + 1

        return fresh_state

    def export_state(self, state: PlayerState) -> Dict:
        """Export state to dictionary for storage"""
        return asdict(state)

    def import_state(self, state_dict: Dict) -> PlayerState:
        """Import state from dictionary"""
        return PlayerState(**state_dict)


# Example usage and testing
if __name__ == "__main__":
    # Test the game state manager
    gsm = GameStateManager()

    # Test different crisis scenarios
    scenarios = [
        # Healthy start
        PlayerState(),

        # Critical health
        PlayerState(health=15, food=0, gold=3),

        # High corruption
        PlayerState(health=80, corruption=75, reputation=ReputationType.MURDERER.value),

        # Thriving
        PlayerState(health=150, max_health=150, gold=200, food=10, level=5)
    ]

    for i, state in enumerate(scenarios):
        print(f"\n{'='*50}")
        print(f"SCENARIO {i+1}:")
        print(f"Crisis Level: {gsm.get_crisis_level(state).value}")
        print(f"Resources: {gsm.get_resource_status(state)}")
        print(f"\nAI PROMPT:")
        print(gsm.generate_scene_prompt(state, "fantasy"))
        print(f"{'='*50}")