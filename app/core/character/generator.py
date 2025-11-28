"""
角色生成器模块
"""

import json
import asyncio
import uuid
import re
from typing import Dict, List, Any, Optional, Tuple

from app.core.llm.openai_client import CharacterLLM, OpenAIClient

class CharacterGenerator:
    def __init__(self, character_llm: Optional[CharacterLLM] = None):
        self.character_llm = character_llm or CharacterLLM()
    
    async def generate_character(self, description: str) -> Dict[str, Any]:
        character_data = await self.character_llm.generate_character(
            description,
            enforce_protagonist_relationship=True,
            timeline_mode="strict",
        )
        self._validate_and_fix_character_data(character_data, strict_timeline=True)
        return character_data

    async def generate_related_characters(self, main_character: Dict[str, Any], count: int = 5) -> List[Dict[str, Any]]:
        """
        为角色生成关联角色，限定在主角色当前人生阶段。
        """
        print(f"开始为 {main_character.get('name')} (当前年龄: {main_character.get('age')}岁, 职业: {main_character.get('occupation')}) 生成 {count} 个关联角色...")

        # **修改：使用 LLM 分析 past_experience 和 background 来推断关键角色**
        past_experience = main_character.get('past_experience', '')
        background = main_character.get('background', '')

        analysis_prompt = f"""
        你是角色关系分析师。请仔细分析以下主角色的关键经历和背景故事，推断出**对主角色人生产生关键影响**（例如塑造性格、价值观、习惯、人生轨迹等）的**角色类型或具体人物**。

        **主角色信息**:
        - 姓名: {main_character.get('name')}
        - 年龄: {main_character.get('age')}
        - 职业: {main_character.get('occupation')}
        - 核心人设: {main_character.get('values')} | {main_character.get('living_habit')} | {main_character.get('social_pattern')} | {main_character.get('personality')}

        **关键经历 (past_experience)**:
        {past_experience}

        **背景故事 (background)**:
        {background}

        **任务**:
        1. 请列出 **最多** {count} 个最有可能对主角色 {main_character.get('name')} 的成长或人生轨迹产生**关键影响**的角色类型或具体人物。
        2. **重要**：生成的角色类型**不能是**主角色本人（例如，不要生成“自己”、“本人”、“主角”）。
        例如，如果 past_experience 提到 "父母争吵"，应包含 "父亲" 或 "母亲"；如果提到 "朋友背叛"，应包含 "朋友"；如果背景提到 "学校"，应包含 "同学" 或 "老师"。
        请注意区分：**关键影响**的角色（如塑造性格的父母、改变观念的导师、产生重大事件的朋友）与**日常接触**的角色（如普通同学、偶尔见面的邻居）。
        输出格式为 JSON 数组，例如 ["父亲", "导师", "挚友", "心理咨询师", "社区志愿者"]。
        请直接输出 JSON 数组，不要添加其他解释文字。
        """

        try:
            analysis_result = await self.character_llm.client.generate_response(
                system_prompt="你是一个擅长分析人物关系和背景的角色分析师。",
                user_prompt=analysis_prompt
            )
            # 尝试解析 LLM 返回的 JSON
            key_entities = json.loads(analysis_result)
            if not isinstance(key_entities, list):
                raise ValueError("LLM 返回的不是 JSON 数组")
            # **修改：过滤掉可能的“本人”、“自己”等**
            key_entities = [entity for entity in key_entities if entity.lower() not in ["本人", "自己", "主角"]]
            print(f"  - LLM 推断出的关键角色类型: {key_entities}")
        except Exception as e:
            print(f"  - LLM 分析关键角色失败: {e}，将使用默认逻辑。")
            # 如果 LLM 分析失败，回退到基于年龄和职业的 LLM 推断逻辑
            key_entities = []
            age = main_character.get('age')
            occupation = main_character.get('occupation')
            fallback_analysis_prompt = f"""
            你是角色关系分析师。请分析一个 {age} 岁的 {occupation} 在其生活、学习或工作环境中，通常会接触到哪些**对个人成长或人生观有潜在关键影响**的角色类型？

            **主角色信息**:
            - 年龄: {age}
            - 职业: {occupation}
            - 核心人设 (价值观, 生活习惯, 社交模式, 性格): {main_character.get('values')}, {main_character.get('living_habit')}, {main_character.get('social_pattern')}, {main_character.get('personality')}

            **任务**:
            1. 请列出 {count} 个**可能**对其产生关键影响的角色类型，例如：老师（影响知识或品格）、导师（职业引导）、挚友（情感支持或观念改变）、心理咨询师（心理成长）、家长（早期性格塑造）等。
            2. **重要**：生成的角色类型**不能是**主角色本人（例如，不要生成“自己”、“本人”、“主角”）。
            避免列出影响较小或仅为日常接触的角色（如普通同学、收银员）。
            输出格式为 JSON 数组，例如 ["老师", "导师", "挚友", "心理咨询师", "家长"]。
            请直接输出 JSON 数组，不要添加其他解释文字。
            """
            try:
                fallback_result = await self.character_llm.client.generate_response(
                    system_prompt="你是一个擅长分析人物关系和背景的角色分析师。",
                    user_prompt=fallback_analysis_prompt
                )
                key_entities = json.loads(fallback_result)
                if not isinstance(key_entities, list):
                    raise ValueError("LLM 回退分析返回的不是 JSON 数组")
                # **修改：过滤掉可能的“本人”、“自己”等**
                key_entities = [entity for entity in key_entities if entity.lower() not in ["本人", "自己", "主角"]]
                print(f"  - LLM 回退推断出的角色类型: {key_entities}")
            except Exception as fallback_e:
                print(f"  - LLM 回退分析也失败: {fallback_e}，使用基础逻辑。")
                key_entities = [] # 如果都失败，使用空列表


        # **修改：构建更精确的生成提示，强调参考 past_experience 和 background，并指定关系**
        related_characters = []
        generated_count = 0
        # 先尝试根据 LLM 推断出的 key_entities 生成特定角色
        for entity_type in key_entities:
            if generated_count >= count:
                break
            # **修改：在 prompt 中明确指定关系，并强调不是主角本人**
            related_desc = f"""
            与{main_character.get('name')}相关的角色，其与主角的关系为：{entity_type}。
            **重要**：生成的角色**不能是**{main_character.get('name')}本人。
            请基于以下信息生成该角色的详细人设：
            - 主角色信息: {json.dumps({k: v for k, v in main_character.items() if k not in ['background', 'past_experience']}, ensure_ascii=False, indent=2)}
            - 主角色关键经历 (past_experience): {main_character.get('past_experience')}
            - 主角色背景故事 (background): {main_character.get('background')}
            请生成一个与{main_character.get('name')}在上述经历中**明确相关或可能相关**的{entity_type}的详细人设。
            例如，如果主角色 past_experience 提到 '5岁时：父母争吵频繁'，则生成的父亲或母亲角色必须与此经历一致。
            如果 past_experience 提到 '13岁时：经历亲密朋友的背叛'，则应生成一个可能的朋友角色（即使未明确命名，也要符合背景）。
            角色必须在主角色当前人生阶段（{main_character.get('age')}岁，{main_character.get('occupation')}）中可能认识、接触或了解。
            重要：生成的角色与主角的关系必须是 {entity_type}。
            """
            try:
                related_char = await self.character_llm.generate_character(
                    related_desc,
                    enforce_protagonist_relationship=False,
                    relationship_override=entity_type,
                    timeline_mode="relaxed",
                )
                related_char["id"] = related_char.get("id") or str(uuid.uuid4())
                related_char["relationship_to_protagonist"] = entity_type
                self._validate_and_fix_character_data(related_char, strict_timeline=False)
                related_characters.append(related_char)
                print(f"  - 根据LLM分析生成关联角色 {generated_count+1}/{count}: {related_char.get('name')} ({related_char.get('occupation')}) - 关系: {entity_type}")
                generated_count += 1
            except Exception as e:
                print(f"  - 根据LLM分析生成关联角色 {entity_type} 失败: {e}")
                # 如果失败，可以创建一个基础的关联角色
                fallback_char = {
                    "id": str(uuid.uuid4()),
                    "name": f"{entity_type}_{generated_count+1}",
                    "age": main_character.get('age') - 5 if main_character.get('age') > 5 else 25, # 简单估算一个可能的年龄
                    "gender": "未知",
                    "occupation": f"{entity_type}",
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
                    "background": f"一个与 {main_character.get('name')} 在当前阶段相关的 {entity_type}，具体信息待完善。",
                    # **修改：在 fallback 时也设置正确的 'relationship_to_protagonist' 字段**
                    "relationship_to_protagonist": entity_type
                }
                related_characters.append(fallback_char)
                generated_count += 1

        # 如果根据LLM分析生成的角色数量不足，再补充生成
        # 为了保证多样性，使用 LLM 推断潜在角色类型
        if generated_count < count:
            print(f"  - LLM分析生成了 {len(key_entities)} 个角色，当前已生成 {generated_count} 个，还需 {count - generated_count} 个。")
            # 获取已生成角色的类型（或名称）用于去重
            generated_types = set()
            for rc in related_characters:
                # 可以用 occupation 或 name 来代表类型
                # 这里优先使用 occupation，如果 occupation 为空或与 name 相似，则用 name
                occ = rc.get('occupation', '').strip()
                name = rc.get('name', '').strip()
                if occ and occ != name:
                    generated_types.add(occ)
                else:
                    generated_types.add(name)

            # LLM 推断潜在角色类型
            age = main_character.get('age')
            occupation = main_character.get('occupation')
            # 构建一个 Prompt，让 LLM 推断在当前主角色环境下，除了已生成的类型外，还可能遇到哪些**对成长有关键影响**且**身份类型不同**的角色
            potential_analysis_prompt = f"""
            你是角色关系分析师。主角色 {main_character.get('name')} 是一个 {age} 岁的 {occupation}。
            其核心人设为：{main_character.get('values')}, {main_character.get('living_habit')}, {main_character.get('social_pattern')}, {main_character.get('personality')}。
            目前已经生成了以下角色：{list(generated_types)}。
            请推断，基于主角色的年龄、职业、核心人设、生活/学习/工作环境以及 past_experience 和 background，还可能遇到哪些**不同身份类型**且**对其成长或人生观有潜在关键影响**的角色？
            **重要**：生成的角色类型**不能是**主角色本人（例如，不要生成“自己”、“本人”、“主角”）。
            例如，如果已生成“老师”，可以考虑“心理咨询师”、“导师”、“挚友”、“邻居”、“社区志愿者”等不同类型。
            请列出 **最多** {count - generated_count} 个可能的新角色类型。
            输出格式为 JSON 数组，例如 ["心理咨询师", "导师", "邻居", "社区志愿者"]。
            请直接输出 JSON 数组，不要添加其他解释文字。
            """
            try:
                potential_result = await self.character_llm.client.generate_response(
                    system_prompt="你是一个擅长分析人物关系和背景的角色分析师。",
                    user_prompt=potential_analysis_prompt
                )
                potential_entities = json.loads(potential_result)
                if not isinstance(potential_entities, list):
                    raise ValueError("LLM 推断潜在角色返回的不是 JSON 数组")
                # **修改：过滤掉可能的“本人”、“自己”等**
                potential_entities = [entity for entity in potential_entities if entity.lower() not in ["本人", "自己", "主角"]]
                print(f"  - LLM 推断出的潜在角色类型: {potential_entities}")
            except Exception as pe:
                print(f"  - LLM 推断潜在角色失败: {pe}，将使用基础逻辑或退出。")
                potential_entities = [] # 如果失败，使用空列表

            # 从潜在角色中生成
            for entity_type in potential_entities:
                if generated_count >= count:
                    break
                # 确保新类型不在已生成列表中
                if entity_type not in generated_types:
                    # **修改：在 prompt 中明确指定关系，并强调不是主角本人**
                    related_desc = f"""
                    与{main_character.get('name')}相关的角色，其与主角的关系为：{entity_type}。
                    **重要**：生成的角色**不能是**{main_character.get('name')}本人。
                    请基于以下信息生成该角色的详细人设：
                    - 主角色信息: {json.dumps({k: v for k, v in main_character.items() if k not in ['background', 'past_experience']}, ensure_ascii=False, indent=2)}
                    - 主角色关键经历 (past_experience): {main_character.get('past_experience')}
                    - 主角色背景故事 (background): {main_character.get('background')}
                    请生成一个与{main_character.get('name')}在当前人生阶段（{main_character.get('age')}岁，{main_character.get('occupation')}）可能认识、接触或了解的{entity_type}的详细人设。
                    重要：请参考主角色的 past_experience 和 background 生成，确保角色与主角色的经历有潜在的关联性或合理性。
                    重要：生成的角色应对其成长或人生观有**潜在的关键影响**。
                    重要：不要生成{main_character.get('name')}未来才会遇到的角色。
                    重要：生成的角色与主角的关系必须是 {entity_type}。
                    重要：生成的角色**不能是**{main_character.get('name')}本人。
                    请生成这个角色的详细信息。
                    """
                    try:
                        related_char = await self.character_llm.generate_character(
                            related_desc,
                            enforce_protagonist_relationship=False,
                            relationship_override=entity_type,
                            timeline_mode="relaxed",
                        )
                        related_char["id"] = related_char.get("id") or str(uuid.uuid4())
                        related_char["relationship_to_protagonist"] = entity_type
                        self._validate_and_fix_character_data(related_char, strict_timeline=False)
                        related_characters.append(related_char)
                        print(f"  - 根据LLM推断的潜在角色生成 {generated_count+1}/{count}: {related_char.get('name')} ({related_char.get('occupation')}) - 关系: {entity_type}")
                        generated_count += 1
                    except Exception as e:
                        print(f"  - 根据LLM推断的潜在角色生成 {entity_type} 失败: {e}")
                        # 如果失败，可以创建一个基础的关联角色
                        fallback_char = {
                            "id": str(uuid.uuid4()),
                            "name": f"{entity_type}_{generated_count+1}",
                            "age": age - 5 if age > 5 else 25, # 简单估算一个可能的年龄
                            "gender": "未知",
                            "occupation": f"{entity_type}",
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
                            "background": f"一个与 {main_character.get('name')} 在当前阶段相关的 {entity_type}，具体信息待完善。",
                            # **修改：在 fallback 时也设置正确的 'relationship_to_protagonist' 字段**
                            "relationship_to_protagonist": entity_type
                        }
                        related_characters.append(fallback_char)
                        generated_count += 1
                else:
                    print(f"  - 潜在角色类型 '{entity_type}' 已存在，跳过。")

        # 如果仍然不足，并且 LLM 推断潜在角色也失败或没有新角色，则可以考虑一个非常通用的回退逻辑
        while generated_count < count:
            print(f"  - 仍然需要生成 {count - generated_count} 个角色，使用通用回退逻辑。")
            # 这里可以再次尝试一个非常通用的 LLM 提示，或者简单地创建一个通用的“熟人”角色
            # 为了简单起见，这里创建一个通用的回退角色
            # **重要：在回退逻辑中也要确保 'relationship_to_protagonist' 设置正确**
            fallback_char = {
                "id": str(uuid.uuid4()),
                "name": f"关联角色_{generated_count+1}",
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
                "background": f"一个与 {main_character.get('name')} 在当前阶段相关的角色，具体信息待完善。",
                # **修改：在通用回退角色中也设置一个默认的、但不为 '本人' 的 'relationship_to_protagonist'**
                "relationship_to_protagonist": f"关联角色_{generated_count+1}" # 或者可以是 "熟人", "邻居" 等
            }
            related_characters.append(fallback_char)
            generated_count += 1


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
    
    def _validate_and_fix_character_data(self, character_data: Dict[str, Any], strict_timeline: bool = True) -> None:
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
        if "past_experience" not in character_data:
            character_data["past_experience"] = ""
        else:
            if isinstance(character_data["past_experience"], list):
                character_data["past_experience"] = "；".join(
                    [str(item) for item in character_data["past_experience"] if str(item).strip()]
                )
            elif isinstance(character_data["past_experience"], (dict, tuple)):
                character_data["past_experience"] = json.dumps(character_data["past_experience"], ensure_ascii=False)

            if strict_timeline:
                character_data["past_experience"] = self._ensure_timeline_format(
                    character_data["past_experience"], "past_experience", character_data["age"]
                )

        if "background" not in character_data:
            character_data["background"] = "Unknown background"
        else:
            if isinstance(character_data["background"], list):
                character_data["background"] = "；".join(
                    [str(item) for item in character_data["background"] if str(item).strip()]
                )
            elif isinstance(character_data["background"], (dict, tuple)):
                character_data["background"] = json.dumps(character_data["background"], ensure_ascii=False)

            if strict_timeline:
                character_data["background"] = self._ensure_timeline_format(
                    character_data["background"], "background", character_data["age"]
                )
        
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

    def _ensure_timeline_format(self, text: str, label: str, max_age: int) -> str:
        """
        Ensure timeline fields strictly follow the "X岁时：..." pattern.
        Raises ValueError when the pattern is missing so upstream prompts must comply.
        """
        if not isinstance(text, str):
            raise ValueError(f"{label} 必须是字符串且需包含按年龄分段的经历。")

        segments = re.findall(r"(\d+(?:\.\d+)?岁时：[^。]*。?)", text)
        if not segments:
            raise ValueError(
                f"{label} 缺少按 'X岁时：' 切分的经历，请补充从 0 岁到 {max_age} 岁的时间线描述。"
            )

        normalized_segments = []
        for seg in segments:
            normalized = seg.strip()
            if not normalized.endswith("。"):
                normalized += "。"
            normalized_segments.append(normalized)

        return "".join(normalized_segments)