"""
SillyTavern Character Card Service

Handles import/export of characters in SillyTavern V2 format.
Spec: https://github.com/malfoyslastname/character-card-spec-v2

Card format: JSON embedded in PNG metadata (tEXt chunk with key "chara")
The JSON is base64-encoded.
"""

import json
import base64
import struct
import zlib
import re
from typing import Optional
from pathlib import Path


# SillyTavern V2 Card Schema constants
CARD_SPEC = "chara_card_v2"
CARD_SPEC_VERSION = "2.0"


def create_card_json(
    name: str,
    description: str,
    personality: str,
    scenario: str,
    first_mes: str,
    mes_example: str = "",
    system_prompt: str = "",
    post_history_instructions: str = "",
    creator_notes: str = "",
    tags: Optional[list] = None,
    creator: str = "SoulPulse",
    character_version: str = "1.0",
    extensions: Optional[dict] = None,
) -> dict:
    """Create a SillyTavern V2 character card JSON structure."""
    return {
        "spec": CARD_SPEC,
        "spec_version": CARD_SPEC_VERSION,
        "data": {
            "name": name,
            "description": description,
            "personality": personality,
            "scenario": scenario,
            "first_mes": first_mes,
            "mes_example": mes_example,
            "creator_notes": creator_notes,
            "system_prompt": system_prompt,
            "post_history_instructions": post_history_instructions,
            "tags": tags or [],
            "creator": creator,
            "character_version": character_version,
            "extensions": extensions or {},
        }
    }


def card_to_json_string(card: dict) -> str:
    """Serialize card to JSON string."""
    return json.dumps(card, ensure_ascii=False, indent=2)


def json_string_to_card(json_str: str) -> Optional[dict]:
    """Parse JSON string into card dict. Returns None if invalid."""
    try:
        card = json.loads(json_str)
        if card.get("spec") == CARD_SPEC:
            return card
        # Try V1 format (no spec field, flat structure)
        if "name" in card and "description" in card:
            return _upgrade_v1_to_v2(card)
        return None
    except (json.JSONDecodeError, KeyError):
        return None


def _upgrade_v1_to_v2(v1_card: dict) -> dict:
    """Upgrade a V1 card to V2 format."""
    return {
        "spec": CARD_SPEC,
        "spec_version": CARD_SPEC_VERSION,
        "data": {
            "name": v1_card.get("name", ""),
            "description": v1_card.get("description", ""),
            "personality": v1_card.get("personality", ""),
            "scenario": v1_card.get("scenario", ""),
            "first_mes": v1_card.get("first_mes", ""),
            "mes_example": v1_card.get("mes_example", ""),
            "creator_notes": v1_card.get("creator_notes", ""),
            "system_prompt": v1_card.get("system_prompt", ""),
            "post_history_instructions": v1_card.get("post_history_instructions", ""),
            "tags": v1_card.get("tags", []),
            "creator": v1_card.get("creator", ""),
            "character_version": v1_card.get("character_version", "1.0"),
            "extensions": v1_card.get("extensions", {}),
        }
    }


def embed_card_in_png(png_bytes: bytes, card_json: dict) -> bytes:
    """
    Embed character card JSON into PNG metadata as a tEXt chunk.
    The card is base64-encoded and stored with key "chara".
    """
    card_str = json.dumps(card_json, ensure_ascii=False)
    card_b64 = base64.b64encode(card_str.encode('utf-8')).decode('ascii')

    # Build tEXt chunk: keyword + null separator + text
    keyword = b"chara"
    text_data = keyword + b"\x00" + card_b64.encode('ascii')

    # Create PNG chunk: length + type + data + CRC
    chunk_type = b"tEXt"
    chunk_length = struct.pack(">I", len(text_data))
    chunk_crc = struct.pack(">I", zlib.crc32(chunk_type + text_data) & 0xFFFFFFFF)
    text_chunk = chunk_length + chunk_type + text_data + chunk_crc

    # Insert before IEND chunk (last 12 bytes of PNG)
    return png_bytes[:-12] + text_chunk + png_bytes[-12:]


def extract_card_from_png(png_bytes: bytes) -> Optional[dict]:
    """
    Extract character card JSON from PNG tEXt metadata.
    Looks for tEXt chunk with key "chara".
    """
    # Skip PNG signature (8 bytes)
    pos = 8
    while pos < len(png_bytes):
        if pos + 8 > len(png_bytes):
            break
        # Read chunk length and type
        chunk_length = struct.unpack(">I", png_bytes[pos:pos + 4])[0]
        chunk_type = png_bytes[pos + 4:pos + 8]
        chunk_data = png_bytes[pos + 8:pos + 8 + chunk_length]

        if chunk_type == b"tEXt":
            # Split by null byte to get keyword and text
            null_idx = chunk_data.find(b"\x00")
            if null_idx != -1:
                keyword = chunk_data[:null_idx]
                if keyword == b"chara":
                    text = chunk_data[null_idx + 1:]
                    try:
                        json_str = base64.b64decode(text).decode('utf-8')
                        return json.loads(json_str)
                    except Exception:
                        pass

        # Move to next chunk (length + type + data + CRC)
        pos += 12 + chunk_length

        if chunk_type == b"IEND":
            break

    return None


def parse_markdown_character(md_path: str) -> dict:
    """
    Parse a SoulPulse character markdown file into a structured dict.
    Extracts sections like personality, speech patterns, visual DNA, etc.
    """
    with open(md_path, 'r', encoding='utf-8') as f:
        content = f.read()

    sections = {}
    current_section = None
    current_content = []

    for line in content.split('\n'):
        # Match ## or ### headers
        header_match = re.match(r'^#{1,3}\s+(.+)', line)
        if header_match:
            if current_section:
                sections[current_section] = '\n'.join(current_content).strip()
            current_section = header_match.group(1).strip()
            current_content = []
        else:
            current_content.append(line)

    if current_section:
        sections[current_section] = '\n'.join(current_content).strip()

    return sections


def _extract_dialogue_examples(sections: dict) -> str:
    """
    Extract dialogue examples from the 示例对话 section specifically,
    formatting them with <START> separators for SillyTavern.
    """
    # First look for the dedicated 示例对话 section
    example_text = ""
    for key in sections:
        if '示例对话' in key:
            example_text = sections[key]
            break

    if not example_text:
        # Fallback: look in the broader speech pattern section
        for key in sections:
            if '语言风格' in key or 'speech' in key.lower():
                example_text = sections[key]
                break

    if not example_text:
        return ""

    # Parse dialogue blocks separated by intimacy level headers or double newlines
    # Each block typically starts with **亲密度 X-Y（...）：**
    blocks = re.split(r'\n\*\*亲密度', example_text)
    formatted = []

    for block in blocks:
        block = block.strip()
        if not block:
            continue
        # Re-add the prefix if it was split off
        if not block.startswith('**亲密度'):
            # Check if this is the first part before any headers
            if formatted or '>' in block:
                block = '**亲密度' + block
            else:
                continue

        # Extract the dialogue lines (quoted with >)
        lines = []
        for line in block.split('\n'):
            line = line.strip()
            if line.startswith('>'):
                # Remove the > prefix and clean up
                dialogue = line.lstrip('>').strip()
                lines.append(dialogue)
            elif line.startswith('**亲密度'):
                # This is a header line, use as context
                header = line.strip('*').strip()
                lines.append(f"[{header}]")

        if lines:
            formatted.append("<START>\n" + '\n'.join(lines))

    return '\n\n'.join(formatted)


def _generate_greeting(name: str, sections: dict) -> str:
    """
    Generate a first_mes (greeting) from the character's personality
    if no explicit greeting section exists in the markdown.
    Uses the lowest intimacy dialogue example or crafts one from personality.
    """
    # Try to find the lowest-intimacy dialogue example
    for key in sections:
        if '示例对话' in key:
            content = sections[key]
            # Look for the first dialogue example (intimacy 0-10)
            lines = content.split('\n')
            greeting_lines = []
            capturing = False
            for line in lines:
                if '亲密度 0' in line or '陌生人' in line:
                    capturing = True
                    continue
                elif capturing and line.startswith('**亲密度'):
                    break
                elif capturing and line.strip().startswith('>'):
                    greeting_lines.append(line.lstrip('>').strip())
                elif capturing and line.strip():
                    greeting_lines.append(line.strip())
            if greeting_lines:
                return '\n'.join(greeting_lines)

    # Fallback: generate from basic info + outer personality
    outer_persona = ""
    for key in sections:
        if '外在人格' in key or 'public persona' in key.lower():
            outer_persona = sections[key][:200]
            break

    if outer_persona:
        # Create a simple in-character greeting based on personality
        return f"*{name}看向你* ...你好。"

    return f"*{name}抬起头* ......"


def convert_markdown_to_card(md_path: str) -> dict:
    """
    Convert a SoulPulse character markdown file to SillyTavern V2 card format.

    Mapping:
    - 人格系统 (Three-Layer Personality) → description (all personality layers combined)
    - 基础信息 → personality (basic traits summary)
    - 示例对话 → mes_example (formatted with <START> separators per intimacy tier)
    - System Prompt → system_prompt
    - 背景故事/Backstory → scenario (full backstory context)
    - 关系进阶 → extensions.relationship_system
    - 视觉DNA → extensions.visual_dna
    - 情绪触发点 → extensions.emotion_triggers
    - 秘密层级 → extensions.secret_layers
    - 日常作息 → extensions.daily_routine
    - 声音特质 → extensions.voice_profile
    - 语言风格 → extensions.speech_pattern (full speech rules)
    """
    sections = parse_markdown_character(md_path)

    # Extract name from first heading or filename
    name = ""
    with open(md_path, 'r', encoding='utf-8') as f:
        first_line = f.readline().strip()
        if first_line.startswith('#'):
            # Extract just the Chinese name part
            raw_name = first_line.lstrip('#').strip()
            # Try to get just the name before " - " or " (" 
            if ' - ' in raw_name:
                raw_name = raw_name.split(' - ')[0].strip()
            if ' (' in raw_name:
                raw_name = raw_name.split(' (')[0].strip()
            name = raw_name

    if not name:
        name = Path(md_path).stem

    # Build rich description from ALL personality layers
    description_parts = []
    # Include the three personality layers (outer/inner/hidden)
    personality_section_keys = []
    for key in sections:
        if ('人格' in key or '外在' in key or '内在' in key or '隐藏' in key
                or 'personality' in key.lower() or 'public persona' in key.lower()
                or 'private self' in key.lower() or 'hidden depth' in key.lower()):
            personality_section_keys.append(key)

    for key in personality_section_keys:
        content = sections[key]
        if content.strip():
            description_parts.append(f"[{key}]\n{content}")

    description = '\n\n'.join(description_parts) if description_parts else ""

    # Build personality summary from basic info
    personality = ""
    for key in sections:
        if '基础信息' in key or 'basic' in key.lower():
            personality = sections[key]
            break

    # Extract dialogue examples with proper <START> formatting
    mes_example = _extract_dialogue_examples(sections)

    # Extract system prompt (from the code block in System Prompt section)
    system_prompt = ""
    for key in sections:
        if 'system prompt' in key.lower() or '系统提示' in key or 'personality_prompt' in key.lower():
            raw = sections[key]
            # Strip markdown code block markers if present
            raw = re.sub(r'^```[a-z]*\n?', '', raw)
            raw = re.sub(r'\n?```$', '', raw)
            system_prompt = raw.strip()
            break

    # Extract scenario/backstory - combine all subsections for richness
    scenario_parts = []
    for key in sections:
        if '背景故事' in key or 'backstory' in key.lower():
            scenario_parts.append(sections[key])
        elif ('家庭' in key or '成长' in key or '当前冲突' in key) and '背景' not in key:
            # Include family/growth/conflict sub-sections
            scenario_parts.append(f"[{key}]\n{sections[key]}")
    scenario = '\n\n'.join(scenario_parts) if scenario_parts else ""

    # If scenario is empty, try broader matching
    if not scenario:
        for key in sections:
            if '背景' in key or 'background' in key.lower():
                scenario = sections[key]
                break

    # Build first message (greeting)
    first_mes = ""
    for key in sections:
        if '初始' in key or 'greeting' in key.lower() or '开场' in key or '第一条消息' in key:
            first_mes = sections[key]
            break

    # If no explicit greeting, generate one from character data
    if not first_mes:
        first_mes = _generate_greeting(name, sections)

    # Extensions for SoulPulse-specific data
    extensions: dict = {}

    for key in sections:
        if '关系进阶' in key or ('关系' in key and 'progression' in key.lower()):
            extensions['relationship_system'] = sections[key]
        elif '视觉' in key or 'visual identity' in key.lower():
            extensions['visual_dna'] = sections[key]
        elif '情绪触发' in key or 'trigger point' in key.lower():
            extensions['emotion_triggers'] = sections[key]
        elif '秘密' in key or 'secret layer' in key.lower():
            extensions['secret_layers'] = sections[key]
        elif '日常作息' in key or 'daily routine' in key.lower():
            extensions['daily_routine'] = sections[key]
        elif '声音' in key or 'voice profile' in key.lower():
            extensions['voice_profile'] = sections[key]
        elif '语言风格' in key or 'speech pattern' in key.lower():
            extensions['speech_pattern'] = sections[key]

    # Add SoulPulse metadata
    extensions['soulpulse'] = {
        'source_file': str(Path(md_path).name),
        'format_version': '1.0',
    }

    # Build tags from archetype/category info
    tags = []
    for key in sections:
        if '基础信息' in key:
            content = sections[key]
            if '乙女' in content:
                tags.append('otome')
            if 'BL' in content or 'bl' in content.lower():
                tags.append('bl')
            # Extract category for dual-audience characters
            if '双线' in content:
                if 'otome' not in tags:
                    tags.append('otome')
                if 'bl' not in tags:
                    tags.append('bl')

    return create_card_json(
        name=name,
        description=description,
        personality=personality,
        scenario=scenario,
        first_mes=first_mes,
        mes_example=mes_example,
        system_prompt=system_prompt,
        tags=tags,
        extensions=extensions,
    )


class CharacterCardService:
    """High-level service for character card operations."""

    async def export_persona_to_card(self, persona) -> dict:
        """
        Export an AIPersona ORM object to SillyTavern V2 card JSON.
        Uses stored tavern_card_json if available, otherwise builds from persona fields.
        """
        if persona.tavern_card_json:
            try:
                return json.loads(persona.tavern_card_json)
            except json.JSONDecodeError:
                pass

        # Build from persona fields
        extensions: dict = {}
        if persona.visual_prompt_tags:
            extensions['visual_dna'] = persona.visual_prompt_tags
        if persona.secret_layers_json:
            extensions['secret_layers'] = persona.secret_layers_json
        if persona.daily_routine_json:
            extensions['daily_routine'] = persona.daily_routine_json
        if persona.voice_config_json:
            extensions['voice_config'] = persona.voice_config_json

        card = create_card_json(
            name=persona.name,
            description=persona.bio or "",
            personality=f"{persona.archetype or ''} | {persona.profession or ''}",
            scenario=persona.family_background or "",
            first_mes="",  # Would need to be set manually
            system_prompt=persona.personality_prompt or "",
            extensions=extensions,
        )
        return card

    async def export_as_png_card(self, persona, avatar_bytes: bytes) -> bytes:
        """Export persona as a PNG character card (image with embedded JSON metadata)."""
        card = await self.export_persona_to_card(persona)
        return embed_card_in_png(avatar_bytes, card)

    async def import_card_to_persona_data(self, card_json: dict) -> dict:
        """
        Convert a SillyTavern card JSON to a dict suitable for creating/updating an AIPersona.
        Returns field mappings ready for ORM.
        """
        data = card_json.get("data", card_json)

        persona_data = {
            "name": data.get("name", ""),
            "bio": data.get("description", ""),
            "personality_prompt": data.get("system_prompt", "") or data.get("description", ""),
            "family_background": data.get("scenario", ""),
            "tavern_card_json": json.dumps(card_json, ensure_ascii=False),
        }

        # Extract from extensions
        extensions = data.get("extensions", {})
        if 'visual_dna' in extensions:
            persona_data["visual_prompt_tags"] = extensions['visual_dna']
        if 'secret_layers' in extensions:
            persona_data["secret_layers_json"] = extensions['secret_layers']
        if 'daily_routine' in extensions:
            persona_data["daily_routine_json"] = extensions['daily_routine']
        if 'voice_config' in extensions:
            persona_data["voice_config_json"] = extensions['voice_config']

        # Tags → category
        tags = data.get("tags", [])
        if "otome" in tags:
            persona_data["category"] = "otome"
        elif "bl" in tags:
            persona_data["category"] = "bl"
        elif "gl" in tags:
            persona_data["category"] = "gl"

        return persona_data


# Singleton instance for convenient import
character_card_service = CharacterCardService()
