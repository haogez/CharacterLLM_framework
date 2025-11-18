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

    async def infer_character_relationships(self, main_character: Dict[str, Any], related_characters: List[Dict[str, Any]], graph_store) -> List[Dict[str, Any]]:
        """
        推断主角色与关联角色之间，以及关联角色彼此之间的关系。
        """
        log_info(f"开始为角色 {main_character.get('name')} 及其关联角色推断关系...")
        start_time = time.time()

        all_characters = [main_character] + related_characters
        relationships = []

        if len(all_characters) < 2:
            log_info("角色数量少于2，无需推断关系。")
            return relationships

        # 构建角色信息字符串，供 LLM 分析，并明确包含 ID
        char_info_list = []
        for char in all_characters:
            char_info_list.append(
                f"ID: {char.get('id')}\n"  # 明确包含 ID
                f"姓名: {char.get('name')}\n"
                f"年龄: {char.get('age')}\n"
                f"职业: {char.get('occupation')}\n"
                f"价值观: {char.get('values')}\n"
                f"社交模式: {char.get('social_pattern')}\n"
                f"过往经历: {char.get('past_experience')}\n"
                f"背景故事: {char.get('background')[:200]}...\n" # 限制长度，避免 prompt 过长
                f"---"
            )
        all_char_info_str = "\n".join(char_info_list)

        # 构建 LLM Prompt
        system_prompt = f"""
        你是关系分析专家。根据以下角色信息，分析并推断每一对角色之间的关系。

        **角色信息 (包含ID)**:
        {all_char_info_str}

        **任务**:
        1.  分析所有角色对 (A, B)，其中 A 和 B 是不同角色的 ID。
        2.  推断 A 对 B 的关系类型 (如 FRIEND, FAMILY, COLLEAGUE, STRANGER, ACQUAINTANCE, ENEMY, MENTOR, etc.)。
        3.  用 1-2 句话描述 A 对 B 的关系 (基于他们的背景故事、价值观、社交模式等)。
        4.  估算 A 对 B 的关系强度 (1-100)。考虑因素：关系类型、过往互动、价值观相似度、社交模式（如孤僻的人可能对所有关系强度评分较低）。
        5.  如果 A 和 B 没有直接联系或互动，标记关系为 STRANGER，强度设为 5。

        **输出格式** (JSON数组):
        [
          {{
            "relationship_id": "uuid",
            "from_character_id": "角色A的ID (必须从上面的角色信息中准确复制ID)",
            "to_character_id": "角色B的ID (必须从上面的角色信息中准确复制ID)",
            "relationship_type": "FRIEND",
            "description": "A认为B是... (A对B的看法或关系描述)",
            "strength": 85
          }},
          ...
        ]

        **重要**:
        - 每个关系都必须包含所有字段。
        - 为每一对角色 (A, B) 都生成一条记录 (A->B)。
        - 关系是**有向**的，A->B 和 B->A 可能不同 (例如，A是B的老师，但B不是A的老师；A喜欢B，但B不喜欢A)。
        - **必须**使用角色信息中明确给出的 "ID:" 后面的值作为 "from_character_id" 和 "to_character_id"。
        - 请直接返回JSON数组，不要添加其他解释文字。
        """

        user_prompt = "请根据角色信息推断所有角色对之间的有向关系。"

        try:
            result = await self.character_llm.client.generate_structured_response(system_prompt, user_prompt)

            if isinstance(result, list):
                raw_relationships = result
            elif isinstance(result, dict):
                raw_relationships = result.get("relationships", [])
            else:
                log_warning(f"LLM 推断关系返回了非预期格式: {type(result)}")
                raw_relationships = []

            for raw_rel in raw_relationships:
                if not isinstance(raw_rel, dict):
                    log_warning(f"跳过非字典格式的关系: {raw_rel}")
                    continue

                rel_id = str(uuid.uuid4())
                # 确保处理 None 或空字符串的情况
                from_char_id = raw_rel.get("from_character_id")
                to_char_id = raw_rel.get("to_character_id")
                if not from_char_id or not to_char_id:
                    log_warning(f"关系中缺少有效的 from_character_id 或 to_character_id: {raw_rel}")
                    continue # 跳过无效关系

                processed_rel = {
                    "relationship_id": rel_id,
                    "from_character_app_id": from_char_id, # 注意字段名映射
                    "to_character_app_id": to_char_id,
                    "relationship_type": raw_rel.get("relationship_type", "UNKNOWN"),
                    "description": raw_rel.get("description", ""),
                    "strength": raw_rel.get("strength", 50)
                }
                # 验证 ID 是否存在于角色列表中
                if from_char_id not in [c['id'] for c in all_characters] or to_char_id not in [c['id'] for c in all_characters]:
                     log_warning(f"关系中包含未知角色ID: {from_char_id} -> {to_char_id}, 跳过此关系。")
                     continue
                if from_char_id == to_char_id:
                    log_warning(f"关系的起始和结束ID相同: {from_char_id}, 跳过此关系。")
                    continue
                relationships.append(processed_rel)

            log_success(f"推断出 {len(relationships)} 条角色间关系。")

            # --- 移除：不再直接导入图谱，由调用方处理 ---
            # if graph_store and relationships:
            #     log_info(f"开始将 {len(relationships)} 条角色间关系导入图谱...")
            #     success_char_rels = graph_store.import_character_to_character_relationships_from_list(relationships)
            #     if success_char_rels:
            #         log_success(f"角色间关系数据已成功从列表导入 Neo4j。")
            #     else:
            #         log_error(f"角色间关系数据导入 Neo4j 失败。")
            # else:
            #     log_info("没有角色间关系需要导入图谱或 GraphStore 未提供。")
            # ---

        except Exception as e:
            log_error(f"推断角色关系失败: {e}")
            import traceback
            traceback.print_exc()

        log_info(f"推断角色关系耗时: {time.time() - start_time:.2f} 秒")
        return relationships
    
    def _calculate_chapter_boundaries(self, total_age: int) -> List[Dict[str, Any]]:
        """
        根据总年龄，计算出 2 个章节的边界。
        使得每个章节内的“记忆事件数”大致相等。
        记忆事件密度函数: density = k / (age + offset)^alpha
        """
        if total_age <= 3:
            # 如果总年龄小于等于3，无法划分有意义的章节
            return [{"start": 0, "end": total_age, "label": f"0-{total_age}岁"}]

        # --- 修改：计算 2 个章节的边界 ---
        # 方案一：简单地将年龄平均分成两部分
        # midpoint = total_age // 2
        # boundaries = [
        #     {"start": 3, "end": midpoint, "label": f"3-{midpoint}岁 (早期)"},
        #     {"start": midpoint + 1, "end": total_age, "label": f"{midpoint + 1}-{total_age}岁 (后期)"}
        # ]

        # 方案二：根据您之前提到的密度函数逻辑，估算使两部分事件数相等的分界点
        # 这需要积分密度函数 density = k / (age + offset)^alpha
        # 积分 k / (x + offset)^alpha = k * (x + offset)^(1-alpha) / (1-alpha) (alpha != 1)
        # 计算从 3 岁到 total_age 的总记忆事件数（积分近似）
        k = 100.0  # 参数 k 和 alpha 需要根据实际数据调整，这里使用一个示例值
        alpha = 0.8
        offset = 1.0

        def integral_density(age):
            # 积分 k / (x + offset)^alpha = k * (x + offset)^(1-alpha) / (1-alpha)
            if alpha == 1:
                return k * math.log(age + offset)
            else:
                return k * ((age + offset) ** (1 - alpha)) / (1 - alpha)

        total_density = integral_density(total_age) - integral_density(3)
        target_density_per_half = total_density / 2

        # 寻找第一个章节的结束点（第二个章节的开始点）
        # 即找到 age_x，使得 integral_density(age_x) - integral_density(3) = target_density_per_half
        # integral_density(age_x) = target_density_per_half + integral_density(3)
        target_integral_for_first_half = target_density_per_half + integral_density(3)

        # 使用二分查找来近似求解 age_x
        low_age = 3.0
        high_age = float(total_age)
        epsilon = 0.5 # 精度，允许误差半岁
        age_x = high_age # 初始化为最大值，以防查找失败

        iterations = 0
        max_iterations = 100 # 防止无限循环
        while high_age - low_age > epsilon and iterations < max_iterations:
            mid_age = (low_age + high_age) / 2
            current_integral = integral_density(mid_age)
            if current_integral < target_integral_for_first_half:
                low_age = mid_age
            else:
                high_age = mid_age
            age_x = (low_age + high_age) / 2
            iterations += 1

        # 确保分界点在合理范围内
        split_point = max(3, min(int(age_x), total_age))
        # 确保第一个章节至少包含3岁
        if split_point < 3:
             split_point = 3

        boundaries = [
            {"start": 3, "end": split_point, "label": f"3-{split_point}岁 (早期)"},
            {"start": split_point + 1, "end": total_age, "label": f"{split_point + 1}-{total_age}岁 (后期)"}
        ]

        # 确保边界覆盖到 total_age
        if boundaries and boundaries[-1]["end"] < total_age:
            boundaries[-1]["end"] = total_age
            boundaries[-1]["label"] = f"{boundaries[-1]['start']}-{total_age}岁 (后期)"

        # 如果因为年龄太小导致边界不完整（例如 split_point 就是 total_age），手动补充
        if len(boundaries) < 2:
            # 这种情况理论上不应该发生，因为 split_point 计算逻辑应保证至少有两段
            # 但如果发生，确保至少有一个边界覆盖全部
            if boundaries:
                 boundaries = [
                     {"start": 3, "end": split_point, "label": f"3-{split_point}岁 (早期)"},
                     {"start": split_point + 1, "end": total_age, "label": f"{split_point + 1}-{total_age}岁 (后期)"}
                 ]
                 # 再次检查，如果 split_point + 1 > total_age，则合并或调整
                 if boundaries[1]["start"] > boundaries[1]["end"]:
                     boundaries[0]["end"] = total_age
                     boundaries[0]["label"] = f"3-{total_age}岁 (全期)" # 或者其他合适的标签
                     boundaries = [boundaries[0]] # 只保留一个章节

        return boundaries

    async def generate_chaptered_lifespan_story(self, main_character: Dict[str, Any], related_characters: List[Dict[str, Any]], story_idea: str) -> List[Dict[str, Any]]: # 修改返回类型
        log_info(f"开始为角色 {main_character.get('name')} 生成分章节人生故事...")
        start_time = time.time()

        main_char_age = main_character.get('age', 17)
        main_char_name = main_character.get('name')
        all_char_map = {main_character['id']: main_character}
        all_char_map.update({rc['id']: rc for rc in related_characters})

        age_ranges_to_use = self._calculate_chapter_boundaries(main_char_age)
        log_info(f"计算出的章节边界: {age_ranges_to_use}")

        chaptered_stories = [] # 存储章节内容的列表
        current_context = ""

        for age_range in age_ranges_to_use:
            range_start = age_range['start']
            range_end = age_range['end']
            range_label = age_range['label']

            if range_start > main_char_age:
                 log_info(f"  - 跳过章节: {range_label} (超出角色当前年龄 {main_char_age})")
                 continue

            log_info(f"  - 生成章节: {range_start}-{range_end}岁 ({range_label})")

            # 构建章节特定的 past_experience
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
                if char_age_at_range_start < 0 or (range_start >= 3 and char_age_at_range_start < 3):
                     continue
                all_char_details.append(f"{p_data['name']} (ID: {pid}, 当时约 {char_age_at_range_start} 岁, 职业: {p_data['occupation']})")

            # **修改 system_prompt：强调连续性、标龄、避免小结**
            system_prompt = f"""
            你是一个叙事体故事作家。请为角色 "{main_char_name}" (ID: {main_character['id']}) 写一段关于 {range_start}-{range_end} 岁 ({range_label}) 的故事章节。
            **章节要求**:
            1.  **时间线**: 严格限定在 {range_start}-{range_end} 岁，不得涉及后续年龄。
            2.  **人设锚定**: 全面体现主角色的所有人设字段，特别是 personality (五维分数)、living_habit、values、dislike、appearance、social_pattern、usual_place、favorite_thing、hobby、skills。
            3.  **事件整合**: 必须包含主角色 past_experience 中提及的此阶段关键事件：{relevant_past_exp_str}。
            4.  **角色互动**: 自然融入以下角色：{', '.join(all_char_details)}。互动需符合主角色和关联角色的人设。
            5.  **细节丰富**: 体现具体的地点、物品、感官细节、对话、心理活动，使其适配知识图谱提取。
            6.  **风格**: 客观清晰，包含必要的场景与心理描写，避免模糊表述。
            7.  **连贯性**: 与之前生成的章节内容保持连贯性，不要有突兀的过渡或小结。在故事中必须有清楚的来龙去脉，不能够突兀的出现一段故事情节，应该具有清晰合理的“起因、经过、结果”（但不要进行标注，需要连贯的故事体）。
            8.  **字数要求**: 此章节内容**必须至少达到 2000 字**，详细描述该阶段的多个事件、场景、人物互动、心理变化等。
            9.  **叙事风格**: 严格按照小说类型，对话部分使用标准引号和换行，非对话部分描述细腻，包含环境、动作、心理活动。
            10. **连续性与标龄**: 请将此章节无缝衔接在之前章节之后，形成一个连续的故事流。在故事的关键节点或场景转换时，**明确标注当前角色的年龄**（例如：“当{main_char_name} **10岁**那年春天...” 或 “...{main_char_name} **12岁**的夏天，发生了一件...”）。**不要**为此章节写一个独立的、总结性的结尾小结，故事应流畅地过渡到下一个阶段（如果有的话）。
            11. **内容完整性**: 确保本章节内容充实，覆盖了 {range_start}-{range_end} 岁这个年龄段的主要生活片段，以便后续能够从中提取出足够多的记忆。

            **主角色完整人设**:
            {json.dumps(main_character, ensure_ascii=False, indent=2)}

            **关联角色人设**:
            {json.dumps(related_characters, ensure_ascii=False, indent=2)}

            **故事灵感**:
            {story_idea}

            **当前故事上下文** (请确保衔接自然):
            {current_context}

            请生成 {range_start}-{range_end} 岁 ({range_label}) 的故事章节 (至少2000字，连续叙事，标龄，无小结):
            """
            user_prompt = f"请生成 {range_start}-{range_end} 岁 ({range_label}) 的故事章节。"

            try:
                chapter_story = await self.character_llm.client.generate_response(system_prompt, user_prompt)
                # 不再添加章节标题，直接追加内容以保持连续性
                # full_story_parts.append(chapter_story) # 移除

                # **存储章节信息**
                chapter_info = {
                    "content": chapter_story,
                    "start_age": range_start,
                    "end_age": range_end,
                    "label": range_label,
                    "original_context": f"### 第{range_start}-{range_end}岁：{range_label}\n\n{chapter_story}" # 保留原始上下文（包含标题）用于保存
                }
                chaptered_stories.append(chapter_info)

                current_context = current_context + "\n\n" + chapter_story

                log_success(f"    - 章节 {range_start}-{range_end}岁 ({range_label}) 生成完成，长度: {len(chapter_story)} 字符")

                part_filename = f"generated_stories/{main_character.get('id', 'unknown')}_story_chapter_{range_start}_{range_end}.txt"
                with open(part_filename, "w", encoding="utf-8") as f:
                    f.write(chapter_info["original_context"]) # 保存时包含标题

            except Exception as e:
                log_error(f"生成章节 {range_start}-{range_end}岁 ({range_label}) 失败: {e}")
                chapter_info = {
                    "content": f"[错误：未能生成此章节内容]\n",
                    "start_age": range_start,
                    "end_age": range_end,
                    "label": range_label,
                    "original_context": f"### 第{range_start}-{range_end}岁：{range_label}\n\n[错误：未能生成此章节内容]\n"
                }
                chaptered_stories.append(chapter_info)

        # **保存完整的、带标题的连续故事**
        full_story_with_titles = "\n\n".join([chapter["original_context"] for chapter in chaptered_stories])
        final_story_filename = f"generated_stories/{main_character.get('id', 'unknown')}_lifespan_story_chaptered.txt"
        with open(final_story_filename, "w", encoding="utf-8") as f:
            f.write(full_story_with_titles)
        log_success(f"最终分章节人生故事已保存到 {final_story_filename}")

        log_success(f"角色 {main_char_name} 的分章节人生故事生成完成")
        log_info(f"生成分章节故事耗时: {time.time() - start_time:.2f} 秒")
        return chaptered_stories # 返回章节列表

    async def generate_character_lifespan_story(self, character_data: Dict[str, Any], related_characters: List[Dict[str, Any]], relationships: List[Dict[str, Any]]) -> str: # 保持返回完整故事字符串的接口，用于其他可能的用途
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

        # **调用修改后的方法，获取章节列表**
        chaptered_stories = await self.generate_chaptered_lifespan_story(refined_main_char, refined_related_chars, story_idea.get('story_idea', ''))

        # **如果仍需要完整字符串（例如用于关系推断），可以在这里拼接**
        full_story_string = "\n\n".join([chapter["original_context"] for chapter in chaptered_stories])

        log_success(f"角色 {character_data.get('name')} 的人生故事生成完成")
        log_info(f"总耗时: {time.time() - start_time:.2f} 秒")
        return full_story_string # 或者返回 chaptered_stories，取决于其他地方的调用方式

    async def extract_memories_from_lifespan_story(self, chaptered_stories: List[Dict[str, Any]], character_data: Dict[str, Any], related_characters: List[Dict[str, Any]]) -> List[Dict[str, Any]]: # 修改参数
        log_info(f"开始从分章节故事中提取记忆片段 (新模型)...")
        start_time = time.time()

        # 构建名称到ID的映射表
        name_to_id_map = {}
        name_to_id_map[character_data.get('name')] = character_data.get('id')
        for rc in related_characters:
            name_to_id_map[rc.get('name')] = rc.get('id')

        # 构建角色信息字符串，用于 LLM 理解上下文
        all_char_map = {character_data['id']: character_data}
        all_char_map.update({rc['id']: rc for rc in related_characters})

        extracted_memories = []
        for chapter_info in chaptered_stories:
            chapter_content = chapter_info["content"]
            chapter_start_age = chapter_info["start_age"]
            chapter_end_age = chapter_info["end_age"]
            chapter_label = chapter_info["label"]

            log_info(f"  - 从章节 {chapter_start_age}-{chapter_end_age}岁 ({chapter_label}) 提取记忆...")

            # **修改 Prompt：针对单个章节提取，明确年龄范围**
            system_prompt = f"""
            你是记忆考古学家，任务是仔细阅读关于"{character_data.get('name')}"在{chapter_start_age}-{chapter_end_age}岁 ({chapter_label})的特定故事片段，并将片段中发生的每一个可记忆的事件、场景、对话、情绪、感觉、思考、行为等都识别出来，转换成详细的、结构化的记忆条目。

            **重要要求**：
            1.  **时间线**: 所有提取的记忆事件都必须发生在 {chapter_start_age}-{chapter_end_age} 岁之间。请根据故事内容推断具体事件发生时的年龄。
            2.  **原始上下文**: 为每个提取的记忆提供其在当前章节原文中的**完整上下文段落**，即 "original_context" 字段。这应是故事中与该记忆直接相关的原始句子或段落。
            3.  **年龄准确性**: 确保 "time.age" 字段准确反映事件发生时的年龄。

            **提取细粒度信息要求**：
            请从故事片段中识别并提取以下类型的信息，并将它们分别存入对应的列表中：
            - **对话 (dialogues)**: 识别故事中的对话，格式为 [{{"content": "对话内容", "speaker": "说话人姓名或身份"}}]。
            - **地点 (locations)**: 识别事件发生的地点，格式为 ["地点1", "地点2"]。
            - **时间 (times)**: 识别事件发生的时间（年份、季节、月份、具体日期、一天中的某个时段），格式为 ["时间描述1", "时间描述2"]。
            - **动作/行为 (actions)**: 识别推动事件发展的关键非语言行为，格式为 ["行为1", "行为2"]。
            - **参与者 (actors)**: 识别事件中出现的所有角色（包括主角、配角、路人等），格式为 ["角色1姓名", "角色2姓名"]。
            - **情感 (emotions)**: 识别事件中的核心情感倾向，格式为 ["情感1", "情感2"]。
            - **物品 (items)**: 识别事件中涉及的关键物品，格式为 ["物品1", "物品2"]。

            记忆条目格式要求（JSON数组）：
            [
              {{
                "id": "唯一ID (作为事件的ID)",
                "title": "记忆标题（10-15字，包含核心意象）",
                "content": "记忆片段的详细描述（从故事中提取的原文或概括）",
                "original_context": "该记忆片段在原始故事中的完整上下文段落（原文内容）", // **新增字段**
                "time": {{
                  "age": {chapter_start_age},  // 发生时角色的年龄 (根据章节标题确定，或从内容推断)
                  "period": "{chapter_label}",  // 人生阶段 (根据章节标题确定)
                  "specific": "2023年秋天的一个下午"  // 具体时间 (如果故事中提及)
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
                "participants": ["[角色名称或拼音]"], // **重要**：必须包含所有在此记忆片段中出现的角色的**名称或拼音**（从以下列表中选择：{list(name_to_id_map.keys())}）。**注意**：请使用角色的名称或拼音，稍后系统会将其转换为ID。
                "tags": ["友谊", "美好回忆"], // 新增：标签列表
                "duration": "几分钟", // 新增：事件持续时间
                "context_before": "...", // 新增：片段前的上下文
                "context_after": "..."  // 新增：片段后的上下文
                // --- 新增细粒度信息字段 ---
                "dialogues": [{{"content": "对话内容", "speaker": "说话人姓名或身份"}}], // 对话列表
                "locations": ["地点1", "地点2"], // 地点列表
                "times": ["时间描述1", "时间描述2"], // 时间列表
                "actions": ["行为1", "行为2"], // 动作列表
                "actors": ["角色1姓名", "角色2姓名"], // 参与者列表
                "emotions": ["情感1", "情感2"], // 情感列表
                "items": ["物品1", "物品2"] // 物品列表
                // ---
              }},
              // ... 更多记忆条目
            ]

            **重要**:
            - 每个记忆条目都必须包含所有字段，即使某些字段没有明确信息也需用空字符串或默认值填充。
            - "participants" 字段**必须**包含所有在此记忆片段中出现的角色的**名称或拼音**（从 character_data 和 related_characters 中获取）。请严格检查，确保名称或拼音存在于提供的列表中。
            - "type", "location", "tags", "duration", "context_before", "context_after", "original_context", "dialogues", "locations", "times", "actions", "actors", "emotions", "items" 是新增的细粒度属性。
            - 请直接返回JSON数组，不要添加其他解释文字。
            - **特别注意**：请确保提取的 "time.age" 字段准确反映事件发生时主角色的年龄（在 {chapter_start_age}-{chapter_end_age} 范围内）。请确保 "participants" 列表包含事件中涉及的所有角色名称或拼音。"original_context" 必须是当前章节故事原文中与此记忆相关的完整段落。
            """

            user_prompt = f"""
            以下是关于{character_data.get('name')}在{chapter_start_age}-{chapter_end_age}岁 ({chapter_label}) 的故事片段，请从中提取记忆片段。请务必阅读整个片段，识别事件，并为每个记忆提供其原始上下文。
            {chapter_content}
            """

            try:
                result = await self.character_llm.client.generate_structured_response(system_prompt, user_prompt)

                if isinstance(result, list):
                    raw_extracted_memories = result
                elif isinstance(result, dict):
                    raw_extracted_memories = result.get("memories", [])
                else:
                    log_warning(f"LLM 为章节 {chapter_start_age}-{chapter_end_age} 返回了非预期格式: {type(result)}")
                    raw_extracted_memories = []

                for raw_mem in raw_extracted_memories:
                    if not isinstance(raw_mem, dict):
                        log_warning(f"跳过非字典格式的记忆: {raw_mem}")
                        continue

                    memory_id = str(uuid.uuid4())
                    processed_mem = raw_mem.copy()
                    processed_mem["id"] = memory_id

                    # 验证并**映射**参与者 (将名称/拼音映射为ID)
                    participants_names = processed_mem.get("participants", [])
                    if not isinstance(participants_names, list):
                        participants_names = [participants_names] if participants_names else []

                    mapped_participant_ids = []
                    for name_or_pinyin in participants_names:
                        if name_or_pinyin in name_to_id_map:
                            mapped_id = name_to_id_map[name_or_pinyin]
                            mapped_participant_ids.append(mapped_id)
                            log_debug(f"[DEBUG] Mapped participant name/pinyin '{name_or_pinyin}' to ID '{mapped_id}'")
                        else:
                            log_warning(f"[DEBUG] Name/Pinyin '{name_or_pinyin}' from memory participants not found in name_to_id_map. Skipping.")

                    processed_mem["participants"] = mapped_participant_ids

                    if not processed_mem["participants"]:
                        processed_mem["participants"] = [character_data.get("id")]

                    tags = processed_mem.get("tags", [])
                    if not isinstance(tags, list):
                        processed_mem["tags"] = [tags] if tags else []

                    # 确保 'original_context' 字段存在
                    if 'original_context' not in processed_mem or processed_mem['original_context'] is None:
                        processed_mem['original_context'] = processed_mem.get('content', '')
                        log_debug(f"[DEBUG] Memory ID {memory_id} missing 'original_context', using 'content' field.")

                    # 确保 'time' 字段存在，并设置默认年龄范围
                    if 'time' not in processed_mem or not isinstance(processed_mem['time'], dict):
                        processed_mem['time'] = {'age': chapter_start_age, 'period': chapter_label, 'specific': '未知'}

                    # **修正：确保 time.age 在当前章节范围内**
                    if not (chapter_start_age <= processed_mem['time'].get('age', chapter_start_age) <= chapter_end_age):
                        log_warning(f"[DEBUG] Memory ID {memory_id} has age {processed_mem['time'].get('age', 'N/A')} outside chapter range {chapter_start_age}-{chapter_end_age}. Adjusting to start age {chapter_start_age}.")
                        processed_mem['time']['age'] = chapter_start_age
                    
                    processed_mem["dialogues"] = raw_mem.get("dialogues", [])
                    processed_mem["locations"] = raw_mem.get("locations", [])
                    processed_mem["times"] = raw_mem.get("times", [])
                    processed_mem["actions"] = raw_mem.get("actions", [])
                    processed_mem["actors"] = raw_mem.get("actors", [])
                    processed_mem["emotions"] = raw_mem.get("emotions", [])
                    processed_mem["items"] = raw_mem.get("items", [])

                    extracted_memories.append(processed_mem)

            except Exception as e:
                log_error(f"从章节 {chapter_start_age}-{chapter_end_age} 提取记忆片段失败: {e}")
                import traceback
                traceback.print_exc()

        log_success(f"从分章节故事中总共提取了 {len(extracted_memories)} 条记忆片段 (新模型)")
        log_info(f"提取记忆片段耗时: {time.time() - start_time:.2f} 秒")
        return extracted_memories

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

        # 3. 推断角色间关系
        character_to_character_relationships = await self.infer_character_relationships(character_data, related_characters, graph_store) # 调用推断方法
        log_success(f"推断出 {len(character_to_character_relationships)} 条角色间关系")

        extraction_filename = f"generated_stories/{character_data.get('id', 'unknown')}_extracted_entities_and_relationships_new_model.txt"
        with open(extraction_filename, "w", encoding="utf-8") as f:
            f.write(json.dumps({"entities": entities, "relationships": relationships, "character_to_character_relationships": character_to_character_relationships}, ensure_ascii=False, indent=2))
        log_success(f"从故事中提取的实体、关系和角色间关系已保存到 {extraction_filename}")


        if graph_store:
            log_info(f"开始将数据保存为新模型的CSV并导入到 Neo4j...")
            csv_files_info = graph_store.save_entities_and_relationships_to_csv(
                character_data, # 主角色
                related_characters, # 关联角色
                entities, # 提取的非人物实体
                relationships, # 提取的非人物实体-事件关系
                extracted_memories, # 提取的记忆 (作为事件)
                character_data.get('id', 'unknown'), # 角色ID
                character_to_character_relationships # 新增：推断的角色间关系
            )

            nodes_filename = csv_files_info.get("nodes_file")
            impressions_filename = csv_files_info.get("impressions_file")
            entity_event_relationships_filename = csv_files_info.get("entity_event_relationships_file")
            temporal_chain_filename = csv_files_info.get("temporal_chain_file")
            details_filename = csv_files_info.get("details_file")
            char_to_char_relationships_filename = csv_files_info.get("char_to_char_relationships_file") # 新增

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

            if details_filename:
                success_details = graph_store.import_event_details_from_csv(details_filename)
                if success_details:
                    log_success(f"事件细节数据已成功从 CSV {details_filename} 导入 Neo4j。")
                else:
                    log_error(f"事件细节数据从 CSV {details_filename} 导入 Neo4j 失败。")

            if char_to_char_relationships_filename:
                success_char_to_char = graph_store.import_character_to_character_relationships_from_csv(char_to_char_relationships_filename)
                if success_char_to_char:
                    log_success(f"角色间关系数据已成功从 CSV {char_to_char_relationships_filename} 导入 Neo4j。")
                else:
                    log_error(f"角色间关系数据从 CSV {char_to_char_relationships_filename} 导入 Neo4j 失败。")
            else:
                log_info("没有角色间关系CSV文件需要导入。")

            # --- 新增：在所有导入完成后，计算并存储向量 ---
            log_info("开始计算并存储节点向量...")
            graph_store.compute_and_store_vectors() # 调用新方法
            log_info("节点向量计算和存储完成。")
        else:
            log_warning("GraphStore 未提供，跳过 CSV 保存和导入步骤。")

        log_success(f"从故事中提取了 {len(entities)} 个非人物实体")
        log_info(f"提取实体和关系耗时: {time.time() - start_time:.2f} 秒")
        # 返回空列表，因为主要逻辑已移至CSV导入
        return [], [], character_to_character_relationships # (entities, non_event_relationships, char_to_char_relationships)
