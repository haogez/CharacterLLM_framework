"""
角色生成器模块
"""

import json
import os
import asyncio
import uuid
from typing import Dict, List, Any, Optional, Tuple

from app.core.llm.openai_client import CharacterLLM, OpenAIClient

class CharacterGenerator:
    def __init__(self, character_llm: Optional[CharacterLLM] = None):
        self.character_llm = character_llm or CharacterLLM()
    
    async def generate_character(self, description: str) -> Dict[str, Any]:
        character_data = await self.character_llm.generate_character(description)
        self._validate_and_fix_character_data(character_data)
        return character_data

    async def generate_related_characters(self, main_character: Dict[str, Any], count: int = 5) -> List[Dict[str, Any]]:
        """
        为角色生成关联角色，限定在主角色当前人生阶段。
        例如，如果主角色是17岁高中生，生成的同学、老师、家人、朋友等。
        """
        print(f"开始为 {main_character.get('name')} (当前年龄: {main_character.get('age')}岁, 职业: {main_character.get('occupation')}) 生成 {count} 个关联角色...")
        
        # --- 构建更精确的生成提示 ---
        # 根据主角色的年龄和职业推断可能接触的角色类型
        age = main_character.get('age', 0)
        occupation = main_character.get('occupation', '未知')
        
        if age < 18 and '学生' in occupation:
            possible_roles = ["同班同学", "其他年级同学", "老师", "室友", "朋友", "家人", "邻居", "校医", "保安", "食堂工作人员"]
        elif age >= 18 and age < 25 and '学生' in occupation:
            possible_roles = ["同学", "室友", "教授", "导师", "朋友", "家人", "邻居", "同学的朋友", "社团成员", "兼职同事"]
        elif age >= 25 and age < 65:
            possible_roles = ["同事", "上司", "下属", "客户", "朋友", "家人", "邻居", "配偶", "孩子", "医生", "邻居"]
        else:
            possible_roles = ["家人", "邻居", "朋友", "社区成员", "志愿者", "医生", "护工"]
        
        # 确保不会生成未来角色的提示词
        forbidden_roles = ["未来的配偶", "未来的同事", "未来的同学", "未来的老师", "未来的朋友", "未来的孩子"]
        
        related_characters = []
        for i in range(count):
            # 为每次生成提供不同的角色类型提示，增加多样性
            role_hint = possible_roles[i % len(possible_roles)] if possible_roles else "熟悉的人"
            
            # 构建角色描述提示
            related_desc = f"""
            与{main_character.get('name')}相关的角色，必须是{main_character.get('name')}在当前人生阶段（{age}岁，{occupation}）可能认识、接触或了解的人。
            角色类型：{role_hint}。
            例如：如果{main_character.get('name')}是高中生，这个角色可能是{role_hint}，{main_character.get('name')}在学校、家庭或社区中与之有过互动或至少认识。
            重要：不要生成{main_character.get('name')}未来才会遇到的角色，如{', '.join(forbidden_roles)}。
            请生成这个角色的详细信息。
            """
            
            try:
                related_char = await self.character_llm.generate_character(related_desc)
                related_char["id"] = related_char.get("id") or str(uuid.uuid4())
                related_characters.append(related_char)
                print(f"  - 生成关联角色 {i+1}/{count}: {related_char.get('name')} ({related_char.get('occupation')})")
            except Exception as e:
                print(f"  - 生成关联角色 {i+1} 失败: {e}")
                # 如果生成失败，可以创建一个基础的关联角色
                fallback_char = {
                    "id": str(uuid.uuid4()),
                    "name": f"关联角色_{i+1}",
                    "age": age - 5 if age > 5 else 25, # 简单估算一个可能的年龄
                    "gender": "未知",
                    "occupation": "未知",
                    "hobby": "未知",
                    "skill": "未知",
                    "values": "未知",
                    "living_habit": "未知",
                    "dislike": "未知",
                    "language_style": "未知",
                    "appearance": "未知",
                    "family_status": "未知",
                    "education": "未知",
                    "social_pattern": "未知",
                    "favorite_thing": "未知",
                    "usual_place": "未知",
                    "past_experience": "未知",
                    "speech_style": "未知",
                    "personality": {"openness": 50, "conscientiousness": 50, "extraversion": 50, "agreeableness": 50, "neuroticism": 50},
                    "background": f"一个与 {main_character.get('name')} 在当前阶段相关的角色，具体信息待完善。"
                }
                related_characters.append(fallback_char)
        
        print(f"为 {main_character.get('name')} 生成了 {len(related_characters)} 个关联角色")
        return related_characters

    async def generate_relationships(self, main_character: Dict[str, Any], related_characters: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        print(f"开始为 {main_character.get('name')} 与 {len(related_characters)} 个关联角色生成关系...")
        relationships = []
        for related_char in related_characters:
            relationship_id = str(uuid.uuid4())
            relationships.append({
                "relationship_id": relationship_id,
                "character1_id": main_character.get("id"),
                "character2_id": related_char.get("id"),
                "relationship_type": "朋友",
                "description": f"{main_character.get('name')} 与 {related_char.get('name')} 之间的关系描述",
                "strength": 50,
                "history": f"{main_character.get('name')} 与 {related_char.get('name')} 的关系历史"
            })
        print(f"生成了 {len(relationships)} 条关系")
        return relationships

    async def generate_memories(self, character_data: Dict[str, Any], count: int = 10) -> List[Dict[str, Any]]:
        memory_types = {
            "education": 0.2,
            "work": 0.3,
            "family": 0.2,
            "hobby": 0.1,
            "trauma": 0.1,
            "achievement": 0.1
        }
        
        type_counts = {}
        remaining = count
        for memory_type, ratio in memory_types.items():
            type_count = max(1, int(count * ratio))
            if remaining >= type_count:
                type_counts[memory_type] = type_count
                remaining -= type_count
            else:
                type_counts[memory_type] = remaining
                remaining = 0
        
        if remaining > 0:
            type_counts["work"] += remaining
        
        all_memories = []
        for memory_type, type_count in type_counts.items():
            for _ in range(type_count):
                memory = await self.character_llm.generate_memory(character_data, memory_type)
                memory["type"] = memory_type
                all_memories.append(memory)
        
        return all_memories
    
    def _validate_and_fix_character_data(self, character_data: Dict[str, Any]) -> None:
        if "name" not in character_data:
            character_data["name"] = "Unknown name"
        if "age" not in character_data:
            character_data["age"] = 30
        elif isinstance(character_data["age"], str):
            try:
                character_data["age"] = int(character_data["age"])
            except ValueError:
                character_data["age"] = 30
        if "gender" not in character_data:
            character_data["gender"] = "Unknown gender"
        if "occupation" not in character_data:
            character_data["occupation"] = "Unknown occupation"
        if "background" not in character_data:
            character_data["background"] = "Unknown background"
        
        if "personality" not in character_data:
            character_data["personality"] = {
                "openness": 50,
                "conscientiousness": 50,
                "extraversion": 50,
                "agreeableness": 50,
                "neuroticism": 50
            }
        else:
            ocean_traits = ["openness", "conscientiousness", "extraversion", "agreeableness", "neuroticism"]
            for trait in ocean_traits:
                if trait not in character_data["personality"]:
                    character_data["personality"][trait] = 50
        
        if "speech_style" not in character_data:
            character_data["speech_style"] = "Neutral and standard speech pattern."