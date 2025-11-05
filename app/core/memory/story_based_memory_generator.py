# app/core/memory/story_based_memory_generator.py

"""
基于角色和动态灵感孵化生成人生故事、记忆片段、实体和关系的模块
(修改版：使用 CSV 作为中间存储)
"""

import asyncio
import json
import uuid
import os
import time
import random
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple
from app.core.llm.openai_client import CharacterLLM
from app.core.utils.log_utils import log_info, log_success, log_warning, log_error, log_debug

class StoryBasedMemoryGenerator:
    def __init__(self, character_llm: CharacterLLM):
        self.character_llm = character_llm
        self.age_ranges = [
            {"label": "婴幼儿期", "start": 0, "end": 2},
            {"label": "童年期", "start": 3, "end": 11},
            {"label": "青少年期", "start": 12, "end": 17},
            {"label": "成年早期", "start": 18, "end": 25},
            {"label": "成年中期", "start": 26, "end": 35},
            {"label": "成年晚期", "start": 36, "end": 100},
        ]

    async def generate_idea(self, character_data: Dict[str, Any]) -> Dict[str, Any]:
        log_info(f"开始为角色 {character_data.get('name')} 进行灵感孵化...")
        start_time = time.time()

        system_prompt = f"""
        你是故事灵感孵化师。根据主角色的信息，构思一个适合的故事类型和核心主题。
        例如：如果角色是“阴暗的宝妈”，可以是“家庭伦理剧，主题为母爱与自我救赎”。
        如果角色是“叛逆的高中生”，可以是“青春成长剧，主题为寻找自我与突破束缚”。

        **主角色信息**:
        {json.dumps(character_data, ensure_ascii=False, indent=2)}

        **输出格式** (JSON):
        {{
            "story_type": "故事类型，如 '青春成长剧', '家庭伦理剧', '职场励志剧'",
            "core_theme": "核心主题，如 '寻找自我', '母爱与自我救赎', '成长与突破'",
            "story_idea": "一个简短的故事想法概括，明确故事的主线和核心冲突"
        }}

        请严格按照上述格式输出JSON。
        """
        user_prompt = f"请为角色 {character_data.get('name')} (职业: {character_data.get('occupation')}, 性格: {character_data.get('values')}) 孵化故事灵感。"

        try:
            result = await self.character_llm.client.generate_structured_response(system_prompt, user_prompt)
            log_success(f"角色 {character_data.get('name')} 的灵感孵化完成")
            log_info(f"灵感孵化耗时: {time.time() - start_time:.2f} 秒")
            return result
        except Exception as e:
            log_error(f"角色 {character_data.get('name')} 的灵感孵化失败: {e}")
            log_info(f"灵感孵化耗时: {time.time() - start_time:.2f} 秒")
            return {"story_type": "未知", "core_theme": "未知", "story_idea": "无"}

    async def generate_related_characters(self, main_character: Dict[str, Any], story_idea: str, count: int = 5) -> List[Dict[str, Any]]:
        log_info(f"开始为角色 {main_character.get('name')} 生成 {count} 个关联角色...")
        start_time = time.time()

        age = main_character.get('age', 0)
        occupation = main_character.get('occupation', '未知')

        if age < 18 and '学生' in occupation:
            possible_roles = ["同学", "老师", "室友", "朋友", "家人", "邻居", "校医", "保安", "食堂工作人员"]
        elif age >= 18 and age < 25 and '学生' in occupation:
            possible_roles = ["同学", "室友", "教授", "导师", "朋友", "家人", "邻居", "同学的朋友", "社团成员", "兼职同事"]
        elif age >= 25 and age < 65:
            possible_roles = ["同事", "上司", "下属", "客户", "朋友", "家人", "邻居", "配偶", "孩子", "医生", "邻居"]
        else:
            possible_roles = ["家人", "邻居", "朋友", "社区成员", "志愿者", "医生", "护工"]

        forbidden_roles = ["未来的配偶", "未来的同事", "未来的同学", "未来的老师", "未来的朋友", "未来的孩子"]

        related_characters = []
        for i in range(count):
            role_hint = possible_roles[i % len(possible_roles)] if possible_roles else "熟悉的人"

            related_desc = f"""
            与{main_character.get('name')}相关的角色，必须是{main_character.get('name')}在当前人生阶段（{age}岁，{occupation}）可能认识、接触或了解的人，且符合故事 '{story_idea}' 的背景。
            角色类型：{role_hint}。
            例如：如果{main_character.get('name')}是高中生，这个角色可能是{role_hint}，{main_character.get('name')}在学校、家庭或社区中与之有过互动或至少认识。
            重要：不要生成{main_character.get('name')}未来才会遇到的角色，如{', '.join(forbidden_roles)}。
            请生成这个角色的详细信息。
            """

            try:
                related_char = await self.character_llm.generate_character(related_desc)
                related_char["id"] = related_char.get("id") or str(uuid.uuid4())
                related_characters.append(related_char)
                log_info(f"  - 生成关联角色 {i+1}/{count}: {related_char.get('name')} ({related_char.get('occupation')})")
            except Exception as e:
                log_error(f"  - 生成关联角色 {i+1} 失败: {e}")
                fallback_char = {
                    "id": str(uuid.uuid4()),
                    "name": f"关联角色_{i+1}",
                    "age": age - 5 if age > 5 else 25,
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

        log_success(f"为 {main_character.get('name')} 生成了 {len(related_characters)} 个关联角色")
        log_info(f"生成关联角色耗时: {time.time() - start_time:.2f} 秒")
        return related_characters

    async def refine_characters_with_backgrounds(self, main_character: Dict[str, Any], related_characters: List[Dict[str, Any]]) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
        log_info(f"开始完善角色 {main_character.get('name')} 及其关联角色的背景故事...")
        start_time = time.time()

        main_char_background_prompt = f"""
        你是故事背景完善师。请为角色 {main_character.get('name')} (ID: {main_character.get('id')}) 生成一个更详细、更贴合其所有设定的背景故事。
        **主角色当前人设**:
        {json.dumps(main_character, ensure_ascii=False, indent=2)}

        **关联角色列表**:
        {json.dumps(related_characters, ensure_ascii=False, indent=2)}

        **要求**:
        1.  **时间线一致性**: 故事必须从0岁写到当前设定的{main_character.get('age')}岁，所有past_experience中提到的关键事件都必须在对应年龄段被详细描述。
        2.  **人设锚定**: 严格体现personality五维分数、living_habit、values、dislike、appearance、social_pattern等所有字段。
        3.  **关联角色互动**: 自然地融入关联角色，描述他们与主角色的互动，确保互动符合双方人设。例如，如果主角色social_pattern为“孤僻”，与他人的互动应体现这一点。
        4.  **因果关系**: 明确past_experience中的事件如何导致当前的性格、habit、values等。
        5.  **场景具象化**: 体现usual_place、favorite_thing、hobby等。
        6.  **风格**: 客观清晰，包含必要的场景与心理描写。

        请生成一个连贯的背景故事。
        """
        try:
            refined_main_background = await self.character_llm.client.generate_response(
                system_prompt=main_char_background_prompt,
                user_prompt="请生成详细背景故事。"
            )
            main_character['background'] = refined_main_background
            log_success(f"主角色 {main_character.get('name')} 的背景故事已完善。")
        except Exception as e:
            log_error(f"完善主角色 {main_character.get('name')} 背景故事失败: {e}")

        for i, rel_char in enumerate(related_characters):
            rel_char_background_prompt = f"""
            你是关联角色背景完善师。请为角色 {rel_char.get('name')} (ID: {rel_char.get('id')}) 生成一个背景故事。
            **关联角色当前人设**:
            {json.dumps(rel_char, ensure_ascii=False, indent=2)}

            **主角色信息**:
            {json.dumps(main_character, ensure_ascii=False, indent=2)}

            **要求**:
            1.  **时间线**: 考虑 {main_character.get('name')} 的年龄 ({main_character.get('age')})，{rel_char.get('name')} 在 {main_character.get('name')} 的故事中出现时的年龄应合理。
            2.  **互动一致性**: {rel_char.get('name')} 的行为、语言风格应与 {main_character.get('name')} 的人设 (特别是social_pattern, language_style等) 互动时产生合理的情节。
            3.  **人设锚定**: 体现 {rel_char.get('name')} 自身的所有设定。
            4.  **关联性**: 重点描述 {rel_char.get('name')} 与 {main_character.get('name')} 的关系和互动细节。

            请生成一个贴合主角色故事的背景故事。
            """
            try:
                refined_rel_background = await self.character_llm.client.generate_response(
                    system_prompt=rel_char_background_prompt,
                    user_prompt="请生成详细背景故事。"
                )
                rel_char['background'] = refined_rel_background
                log_success(f"关联角色 {rel_char.get('name')} 的背景故事已完善。")
            except Exception as e:
                log_error(f"完善关联角色 {rel_char.get('name')} 背景故事失败: {e}")

        log_success(f"角色背景故事完善完成")
        log_info(f"完善角色背景耗时: {time.time() - start_time:.2f} 秒")
        return main_character, related_characters

    async def generate_chaptered_lifespan_story(self, main_character: Dict[str, Any], related_characters: List[Dict[str, Any]], story_idea: str) -> str:
        log_info(f"开始为角色 {main_character.get('name')} 生成分章节人生故事...")
        start_time = time.time()

        main_char_age = main_character.get('age', 17)
        main_char_name = main_character.get('name')
        all_char_map = {main_character['id']: main_character}
        all_char_map.update({rc['id']: rc for rc in related_characters})

        full_story_parts = []
        current_context = ""

        max_age_to_cover = main_char_age
        age_ranges_to_use = [r for r in self.age_ranges if r['start'] <= max_age_to_cover]
        if age_ranges_to_use and age_ranges_to_use[-1]['end'] > max_age_to_cover:
            age_ranges_to_use[-1]['end'] = max_age_to_cover

        for age_range in age_ranges_to_use:
            range_start = age_range['start']
            range_end = age_range['end']
            range_label = age_range['label']

            log_info(f"  - 生成章节: {range_start}-{range_end}岁 ({range_label})")

            relevant_past_exp = []
            for exp in main_character.get('past_experience', '').split('\n'):
                 import re
                 age_match = re.search(r'(\d{1,2})岁', exp)
                 if age_match:
                     exp_age = int(age_match.group(1))
                     if range_start <= exp_age <= range_end:
                         relevant_past_exp.append(exp)
            relevant_past_exp_str = "\n".join(relevant_past_exp) if relevant_past_exp else "无明确提及此阶段的关键经历。"

            all_char_details = []
            for pid, p_data in all_char_map.items():
                age_diff = main_char_age - p_data['age']
                char_age_at_range_start = (range_start + range_end) // 2 - age_diff
                all_char_details.append(f"{p_data['name']} (ID: {pid}, 当时约 {char_age_at_range_start} 岁, 职业: {p_data['occupation']})")

            system_prompt = f"""
            你是一个叙事体故事作家。请为角色 "{main_char_name}" (ID: {main_character['id']}) 写一段关于 {range_start}-{range_end} 岁 ({range_label}) 的故事章节。
            **章节要求**:
            1.  **时间线**: 严格限定在 {range_start}-{range_end} 岁，不得涉及后续年龄。
            2.  **人设锚定**: 全面体现主角色的所有人设字段，特别是 personality (五维分数)、living_habit、values、dislike、appearance、social_pattern、usual_place、favorite_thing、hobby、skills。
            3.  **事件整合**: 必须包含主角色 past_experience 中提及的此阶段关键事件：{relevant_past_exp_str}。
            4.  **角色互动**: 自然融入以下角色：{', '.join(all_char_details)}。互动需符合主角色和关联角色的人设。
            5.  **细节丰富**: 体现具体的地点、物品、感官细节、对话、心理活动，使其适配知识图谱提取。
            6.  **风格**: 客观清晰，包含必要的场景与心理描写，避免模糊表述。
            7.  **连贯性**: 与之前生成的章节内容保持连贯性。

            **主角色完整人设**:
            {json.dumps(main_character, ensure_ascii=False, indent=2)}

            **关联角色人设**:
            {json.dumps(related_characters, ensure_ascii=False, indent=2)}

            **故事灵感**:
            {story_idea}

            **当前故事上下文** (请确保衔接自然):
            {current_context}

            请生成 {range_start}-{range_end} 岁 ({range_label}) 的故事章节:
            """
            user_prompt = f"请生成 {range_start}-{range_end} 岁 ({range_label}) 的故事章节。"

            try:
                chapter_story = await self.character_llm.client.generate_response(system_prompt, user_prompt)
                full_story_parts.append(f"### 第{range_start}-{range_end}岁：{range_label}\n\n{chapter_story}")

                current_context = current_context + "\n\n" + chapter_story

                log_success(f"    - 章节 {range_start}-{range_end}岁 ({range_label}) 生成完成，长度: {len(chapter_story)} 字符")

                part_filename = f"generated_stories/{main_character.get('id', 'unknown')}_story_chapter_{range_start}_{range_end}.txt"
                with open(part_filename, "w", encoding="utf-8") as f:
                    f.write(chapter_story)

            except Exception as e:
                log_error(f"生成章节 {range_start}-{range_end}岁 失败: {e}")
                full_story_parts.append(f"### 第{range_start}-{range_end}岁：{range_label}\n\n[错误：未能生成此章节内容]\n")

        full_story = "\n\n".join(full_story_parts)

        final_story_filename = f"generated_stories/{main_character.get('id', 'unknown')}_lifespan_story_chaptered.txt"
        with open(final_story_filename, "w", encoding="utf-8") as f:
            f.write(full_story)
        log_success(f"最终分章节人生故事已保存到 {final_story_filename}")

        log_success(f"角色 {main_char_name} 的分章节人生故事生成完成")
        log_info(f"生成分章节故事耗时: {time.time() - start_time:.2f} 秒")
        return full_story

    async def generate_character_lifespan_story(self, character_data: Dict[str, Any], related_characters: List[Dict[str, Any]], relationships: List[Dict[str, Any]]) -> str:
        log_info(f"开始为角色 {character_data.get('name')} 生成人生故事...")
        start_time = time.time()

        story_idea = await self.generate_idea(character_data)
        if not story_idea:
            log_error("灵感孵化失败，无法继续生成故事。")
            return ""

        if not related_characters:
            log_info("关联角色列表为空，开始生成...")
            related_characters = await self.generate_related_characters(character_data, story_idea.get('story_idea', ''))
            if not related_characters:
                log_error("关联角色生成失败，无法继续生成故事。")
                return ""

        refined_main_char, refined_related_chars = await self.refine_characters_with_backgrounds(character_data, related_characters)

        full_story = await self.generate_chaptered_lifespan_story(refined_main_char, refined_related_chars, story_idea.get('story_idea', ''))

        log_success(f"角色 {character_data.get('name')} 的人生故事生成完成")
        log_info(f"总耗时: {time.time() - start_time:.2f} 秒")
        return full_story

    async def extract_memories_from_lifespan_story(self, story_text: str, character_data: Dict[str, Any], related_characters: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        log_info(f"开始从故事中提取记忆片段 (新模型)...")
        start_time = time.time()

        # 获取所有角色ID列表，用于验证参与者
        all_char_ids = {character_data['id']: character_data['name']}
        all_char_ids.update({rc['id']: rc['name'] for rc in related_characters})

        system_prompt = f"""
        你是记忆考古学家，任务是仔细阅读以下关于"{character_data.get('name')}"的故事，并将故事中发生的每一个可记忆的事件、场景、对话、情绪、感觉、思考、行为等都识别出来，转换成详细的、结构化的记忆条目。

        记忆条目格式要求（JSON数组）：
        [
          {{
            "id": "唯一ID (作为事件的ID)",
            "title": "记忆标题（10-15字，包含核心意象）",
            "content": "记忆片段的详细描述（从故事中提取的原文或概括）",
            "time": {{
              "age": 15,  // 发生时角色的年龄
              "period": "高中一年级",  // 人生阶段
              "specific": "2023年秋天的一个下午"  // 具体时间
            }},
            "emotion": {{
              "immediate": ["开心", "兴奋"],  // 即时情绪
              "reflected": ["满足", "怀念"],  // 事后反思情绪
              "residual": "对友谊的珍视感",  // 残留至今的情感
              "intensity": 8  // 情感强度 (1-10)
            }},
            "importance": {{
              "score": 9,  // 重要性评分 (1-10)
              "reason": "奠定了对友谊的理解",  // 重要性原因
              "frequency": "偶尔想起"  // 回忆频率
            }},
            "behavior_impact": {{
              "habit_formed": "更愿意主动关心朋友",  // 形成的习惯
              "attitude_change": "更加相信友情",  // 态度转变
              "response_pattern": "遇到朋友困难时会主动提供帮助"  // 应对模式
            }},
            "trigger_system": {{
              "sensory": ["听到那首歌"],  // 感官触发点
              "contextual": ["和朋友一起吃饭时"],  // 情境触发点
              "emotional": ["感到孤独时"]  // 情绪触发点
            }},
            "memory_distortion": {{
              "exaggerated": "朋友当时说的话比实际更温暖",  // 记忆中被夸大的部分
              "downplayed": "忽略了自己当时也说了不少话",  // 被淡化的部分
              "reason": "强化积极情感的心理需求"  // 扭曲原因
            }},
            "type": "scene", // 新增：记忆类型 (scene, dialogue, emotion, thought, behavior, sensation)
            "location": "学校操场", // 新增：地点
            "participants": ["[主角色ID]", "[关联角色ID1]"], // 新增：涉及的角色ID列表 (必须是故事中实际提到的角色)
            "tags": ["友谊", "美好回忆"], // 新增：标签列表
            "duration": "几分钟", // 新增：事件持续时间
            "context_before": "...", // 新增：片段前的上下文
            "context_after": "..."  // 新增：片段后的上下文
          }},
          // ... 更多记忆条目
        ]

        **重要**:
        - 每个记忆条目都必须包含所有字段，即使某些字段没有明确信息也需用空字符串或默认值填充。
        - "participants" 字段应包含所有在此记忆片段中出现的角色的ID（从 character_data 和 related_characters 中获取）。请严格检查，确保ID存在于角色列表中。
        - "type", "location", "tags", "duration", "context_before", "context_after" 是新增的细粒度属性。
        - 请直接返回JSON数组，不要添加其他解释文字。
        - **特别注意**：请确保提取的 "time.age" 字段准确反映事件发生时主角色的年龄。请确保 "participants" 列表包含事件中涉及的所有角色ID，且这些ID必须在提供的角色列表中。
        """

        user_prompt = f"""
        以下是故事文本，请从中提取记忆片段：
        {story_text}
        """

        try:
            result = await self.character_llm.client.generate_structured_response(system_prompt, user_prompt)

            if isinstance(result, list):
                raw_extracted_memories = result
            elif isinstance(result, dict):
                raw_extracted_memories = result.get("memories", [])
            else:
                log_warning(f"LLM 返回了非预期格式: {type(result)}")
                raw_extracted_memories = []

            extracted_memories = []
            for raw_mem in raw_extracted_memories:
                if not isinstance(raw_mem, dict):
                    log_warning(f"跳过非字典格式的记忆: {raw_mem}")
                    continue

                memory_id = str(uuid.uuid4())
                processed_mem = raw_mem.copy()
                processed_mem["id"] = memory_id

                # 验证并过滤参与者
                participants = processed_mem.get("participants", [])
                if not isinstance(participants, list):
                    participants = [participants] if participants else []
                # 只保留存在于 all_char_ids 中的ID
                filtered_participants = [pid for pid in participants if pid in all_char_ids]
                processed_mem["participants"] = filtered_participants

                # 如果没有参与者，至少包含主角色
                if not processed_mem["participants"]:
                    processed_mem["participants"] = [character_data.get("id")]

                tags = processed_mem.get("tags", [])
                if not isinstance(tags, list):
                    processed_mem["tags"] = [tags] if tags else []

                extracted_memories.append(processed_mem)

            log_success(f"从故事中提取了 {len(extracted_memories)} 条记忆片段 (新模型)")
            log_info(f"提取记忆片段耗时: {time.time() - start_time:.2f} 秒")
            return extracted_memories

        except Exception as e:
            log_error(f"从故事中提取记忆片段失败 (新模型): {e}")
            log_info(f"提取记忆片段耗时: {time.time() - start_time:.2f} 秒")
            return []

    # --- 修改：提取实体和关系的方法，适应新的节点模型 ---
    async def extract_entities_and_relationships_from_story(self, story_text: str, character_data: Dict[str, Any], related_characters: List[Dict[str, Any]], extracted_memories: List[Dict[str, Any]], graph_store) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        log_info(f"开始从故事中提取实体和关系 (新模型)...")
        start_time = time.time()

        # 1. 提取实体（人物、地点、物品、事件等）
        # 人物实体已包含在 character_data 和 related_characters 中
        # 非人物实体从故事和记忆中提取
        entities = []
        # 从记忆中提取地点、标签作为实体
        for memory in extracted_memories:
            location = memory.get('location')
            if location:
                location_entity = {
                    "app_id": str(uuid.uuid4()),
                    "name": location,
                    "type": "Place",
                    "description": f"事件 '{memory.get('title', '')}' 发生的地点",
                    "properties": {}
                }
                entities.append(location_entity)

            for tag in memory.get('tags', []):
                tag_entity = {
                    "app_id": str(uuid.uuid4()),
                    "name": tag,
                    "type": "Concept", # 或者根据tag内容判断更具体的类型
                    "description": f"与事件 '{memory.get('title', '')}' 相关的标签",
                    "properties": {}
                }
                entities.append(tag_entity)

        # 2. 提取关系
        # 关系主要指非人物实体与事件的关系
        relationships = []
        # (这部分在graph_store中通过CSV处理)

        extraction_filename = f"generated_stories/{character_data.get('id', 'unknown')}_extracted_entities_and_relationships_new_model.txt"
        with open(extraction_filename, "w", encoding="utf-8") as f:
            f.write(json.dumps({"entities": entities, "relationships": relationships}, ensure_ascii=False, indent=2))
        log_success(f"从故事中提取的实体和关系已保存到 {extraction_filename}")

        # --- 修改：将数据保存为新模型的CSV并导入 ---
        if graph_store:
            log_info(f"开始将数据保存为新模型的CSV并导入到 Neo4j...")
            csv_files_info = graph_store.save_entities_and_relationships_to_csv(
                character_data, # 主角色
                related_characters, # 关联角色
                entities, # 提取的非人物实体
                relationships, # 提取的关系 (现在主要用于非人物实体)
                extracted_memories, # 提取的记忆 (作为事件)
                character_data.get('id', 'unknown') # 角色ID
            )

            nodes_filename = csv_files_info.get("nodes_file")
            impressions_filename = csv_files_info.get("impressions_file")
            entity_event_relationships_filename = csv_files_info.get("entity_event_relationships_file")
            temporal_chain_filename = csv_files_info.get("temporal_chain_file")

            if nodes_filename:
                success_nodes = graph_store.import_nodes_from_csv(nodes_filename)
                if success_nodes:
                    log_success(f"节点数据已成功从 CSV {nodes_filename} 导入 Neo4j。")
                else:
                    log_error(f"节点数据从 CSV {nodes_filename} 导入 Neo4j 失败。")

            if impressions_filename:
                success_impressions = graph_store.import_impressions_from_csv(impressions_filename)
                if success_impressions:
                    log_success(f"印象关系数据已成功从 CSV {impressions_filename} 导入 Neo4j。")
                else:
                    log_error(f"印象关系数据从 CSV {impressions_filename} 导入 Neo4j 失败。")

            if entity_event_relationships_filename:
                success_entity_event = graph_store.import_entity_event_relationships_from_csv(entity_event_relationships_filename)
                if success_entity_event:
                    log_success(f"实体-事件关系数据已成功从 CSV {entity_event_relationships_filename} 导入 Neo4j。")
                else:
                    log_error(f"实体-事件关系数据从 CSV {entity_event_relationships_filename} 导入 Neo4j 失败。")

            if temporal_chain_filename:
                success_temporal = graph_store.import_temporal_chain_from_csv(temporal_chain_filename)
                if success_temporal:
                    log_success(f"时间链数据已成功从 CSV {temporal_chain_filename} 导入 Neo4j。")
                else:
                    log_error(f"时间链数据从 CSV {temporal_chain_filename} 导入 Neo4j 失败。")

        else:
            log_warning("GraphStore 未提供，跳过 CSV 保存和导入步骤。")

        log_success(f"从故事中提取了 {len(entities)} 个非人物实体")
        log_info(f"提取实体和关系耗时: {time.time() - start_time:.2f} 秒")
        # 返回空列表，因为主要逻辑已移至CSV导入
        return [], []
    # ---