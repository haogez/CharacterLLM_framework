# app/core/memory/story_based_memory_generator.py

"""
基于角色和动态灵感孵化生成人生故事、记忆片段、实体和关系的模块
(修改版：使用 CSV 作为中间存储)
"""

import asyncio
import re
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
        # **修改：从 background 中提取格式化的经历**
        background = character_data.get('background', '')
        # 使用正则表达式提取 "X岁时：..." 的部分
        age_pattern = r"(\d+岁(?:\.\d+)?时：.*?)(?=\.|$|\d+岁(?:\.\d+)?时：)"
        formatted_experiences = re.findall(age_pattern, background, re.DOTALL)
        past_experiences_summary = "\n".join(formatted_experiences) if formatted_experiences else character_data.get('past_experience', '')

        system_prompt = f"""你是故事灵感孵化师。根据主角色的信息，特别是其背景故事中按年龄格式化的关键经历，构思一个适合的故事类型和核心主题。例如：如果角色是“阴暗的宝妈”，可以是“家庭伦理剧，主题为母爱与自我救赎”。如果角色是“叛逆的高中生”，可以是“青春成长剧，主题为寻找自我与突破束缚”。

        **主角色信息**:
        {json.dumps({k: v for k, v in character_data.items() if k != 'background'}, ensure_ascii=False, indent=2)}

        **主角色按年龄格式化的成长经历 (来自 background 字段)**:
        {past_experiences_summary}

        **输出格式** (JSON):
        {{
            "story_type": "故事类型，如 '青春成长剧', '家庭伦理剧', '职场励志剧'",
            "core_theme": "核心主题，如 '寻找自我', '母爱与自我救赎', '成长与突破'",
            "story_idea": "一个简短的故事想法概括，明确故事的主线和核心冲突，必须清晰点明由人设字段生成出来的人生成长经历具体事件，不能前后矛盾，要有因果影响。"
        }}

        请严格按照上述格式输出JSON。"""
        user_prompt = f"请为角色 {character_data.get('name')} (职业: {character_data.get('occupation')}, 性格: {character_data.get('values')}) 孵化故事灵感。"

        result = await self.character_llm.client.generate_structured_response(system_prompt, user_prompt)
        log_success(f"角色 {character_data.get('name')} 的灵感孵化完成")
        log_info(f"灵感孵化耗时: {time.time() - start_time:.2f} 秒")
        return result

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
                related_char = await self.character_llm.generate_character(
                    related_desc,
                    enforce_protagonist_relationship=False,
                    relationship_override=role_hint,
                    timeline_mode="relaxed",
                )
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

        # **修改：Prompt 用于生成格式化的 background**
        main_char_background_prompt = f"""
        你是故事背景完善师。请为角色 {main_character.get('name')} (ID: {main_character.get('id')}) 生成一个更详细、更贴合其所有设定的背景故事。
        **主角色当前人设**:
        {json.dumps({k: v for k, v in main_character.items() if k != 'background'}, ensure_ascii=False, indent=2)}

        **关联角色列表**:
        {json.dumps(related_characters, ensure_ascii=False, indent=2)}

        **要求**:
        1.  **时间线一致性**: 故事必须从0岁写到当前设定的{main_character.get('age')}岁，所有past_experience中提到的关键事件都必须在对应年龄段被详细描述。
        2.  **格式化经历**: **核心修改**：严格按照以下格式生成背景故事，每个年龄（或年龄段）用冒号分隔：
            "0岁时：[具体事件或描述]。1岁时：[具体事件或描述]。2岁时：[具体事件或描述]。3岁时：[具体事件或描述]。... 直至当前角色年龄 {main_character.get('age')}岁。[最后可选：一段连贯的文字总结角色的整体背景和性格形成过程，但这部分不强制，重点是前面的格式化经历]。"
        3.  **人设锚定**: 严格体现personality五维分数、living_habit、values、dislike、appearance、social_pattern等所有字段。
        4.  **关联角色互动**: 自然地融入关联角色，描述他们与主角色的互动，确保互动符合双方人设。例如，如果主角色social_pattern为“孤僻”，与他人的互动应体现这一点。
        5.  **因果关系**: 明确past_experience中的事件如何导致当前的性格、habit、values等。
        6.  **场景具象化**: 体现usual_place、favorite_thing、hobby等。
        7.  **风格**: 客观清晰，包含必要的场景与心理描写。

        请生成一个连贯且格式化的背景故事。
        """

        try:
            refined_main_background = await self.character_llm.client.generate_response(system_prompt=main_char_background_prompt, user_prompt="请生成详细背景故事（格式化经历）。")
            main_character['background'] = refined_main_background
            log_success(f"主角色 {main_character.get('name')} 的背景故事已完善。")
        except Exception as e:
            log_error(f"完善主角色 {main_character.get('name')} 背景故事失败: {e}")
            # 如果失败，保留原始 background 或设置默认值
            main_character['background'] = main_character.get('background', '背景故事生成失败。')

        for i, rel_char in enumerate(related_characters):
            # 关联角色的 background 也最好格式化，或者保持原样，取决于后续如何使用
            # 为了保持一致性，也可以要求格式化
            rel_char_background_prompt = f"""
            你是关联角色背景完善师。请为角色 {rel_char.get('name')} (ID: {rel_char.get('id')}) 生成一个背景故事。
            **关联角色当前人设**:
            {json.dumps({k: v for k, v in rel_char.items() if k != 'background'}, ensure_ascii=False, indent=2)}

            **主角色信息**:
            {json.dumps({k: v for k, v in main_character.items() if k != 'background'}, ensure_ascii=False, indent=2)}

            **要求**:
            1.  **时间线**: 考虑 {main_character.get('name')} 的年龄 ({main_character.get('age')})，{rel_char.get('name')} 在 {main_character.get('name')} 的故事中出现时的年龄应合理。
            2.  **格式化经历**: **核心修改**：严格按照以下格式生成背景故事，每个年龄（或年龄段）用冒号分隔（如果年龄信息明确的话）：
                "0岁时：[具体事件或描述]。1岁时：[具体事件或描述]。... 直至当前角色年龄或与主角色互动时的年龄。[最后可选：一段连贯的文字总结]。"
                如果难以确定具体年龄，可以描述其人生阶段（如“童年时期”、“青年时期”）。
            3.  **互动一致性**: {rel_char.get('name')} 的行为、语言风格应与 {main_character.get('name')} 的人设 (特别是social_pattern, language_style等) 互动时产生合理的情节。
            4.  **人设锚定**: 体现 {rel_char.get('name')} 自身的所有设定。
            5.  **关联性**: 重点描述 {rel_char.get('name')} 与 {main_character.get('name')} 的关系和互动细节。

            请生成一个贴合主角色故事的格式化背景故事。
            """

            try:
                refined_rel_background = await self.character_llm.client.generate_response(system_prompt=rel_char_background_prompt, user_prompt="请生成详细背景故事（格式化经历）。")
                rel_char['background'] = refined_rel_background
                log_success(f"关联角色 {rel_char.get('name')} 的背景故事已完善。")
            except Exception as e:
                log_error(f"完善关联角色 {rel_char.get('name')} 背景故事失败: {e}")
                rel_char['background'] = rel_char.get('background', '背景故事生成失败。')

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

    async def generate_chaptered_lifespan_story(self, main_character: Dict[str, Any], related_characters: List[Dict[str, Any]], story_idea: str) -> List[Dict[str, Any]]:
        """
        直接生成结构化的对话场景列表，而不是小说体故事。
        返回格式: [{"场景": "...", "参与者": [...], "主题": "...", "时间": "...", "背景": "...", "对话": "..."}, ...]
        """
        log_info(f"开始为角色 {main_character.get('name')} 生成结构化对话场景...")
        start_time = time.time()

        # 1. 从主角的时间线经历中提取格式化片段，优先使用 past_experience
        timeline_text = main_character.get('past_experience') or main_character.get('background', '')
        age_pattern = r"(\d+(?:\.\d+)?岁(?:\.\d+)?时：.*?)(?=\.|$|\d+(?:\.\d+)?岁(?:\.\d+)?时：)"
        formatted_experiences = re.findall(age_pattern, timeline_text, re.DOTALL)
        experiences_by_age = {}
        for exp in formatted_experiences:
            match = re.match(r"(\d+(?:\.\d+)?)岁(?:\.\d+)?时：(.*)", exp)
            if match:
                age = float(match.group(1))
                content = match.group(2).strip()
                experiences_by_age[age] = experiences_by_age.get(age, []) + [content]

        # 2. 构建关联角色信息
        all_char_map = {main_character['id']: main_character}
        all_char_map.update({rc['id']: rc for rc in related_characters})
        all_char_details = [f"{p_data['name']} (ID: {p_data['id']}, 职业: {p_data['occupation']})" for pid, p_data in all_char_map.items() if pid != main_character['id']]

        # 3. 为每个有经历的年龄生成对话场景
        generated_scenes = []
        for age, experiences in sorted(experiences_by_age.items()):
            if age > main_character.get('age', 100): # 跳过超出当前年龄的经历
                continue
            for i, exp_desc in enumerate(experiences):
                log_info(f" - 为 {age} 岁生成场景 {i+1}...")

                # **修改：Prompt 用于生成对话场景**
                system_prompt = f"""
                你是对话场景构建师。根据角色 "{main_character.get('name')}" 在 {age} 岁时的特定经历描述，构建一个包含关键对话、动作、场景和背景的详细场景。

                **主角色信息**:
                {json.dumps({k: v for k, v in main_character.items() if k not in ['background', 'past_experience']}, ensure_ascii=False, indent=2)}

                **关联角色信息**:
                {json.dumps(related_characters, ensure_ascii=False, indent=2)}

                **要求**:
                1.  **时间**: 场景必须发生在 {age} 岁。
                2.  **人设锚定**: 场景中的行为、对话、情感必须严格符合主角色和关联角色的人设（特别是 personality, values, language_style, speech_style, living_habit, social_pattern, appearance, family_status 等）。
                3.  **基于经历**: 场景的核心内容必须来源于或体现以下经历描述："{exp_desc}"。
                4.  **参与者**: 场景中的参与者必须是主角色或关联角色列表中的角色。
                5.  **格式化输出**: 为该场景生成一个符合以下 JSON 格式的条目：
                {{
                    "场景": "场景发生的具体地点（如 家中, 学校教室, 公园等）",
                    "参与者": ["角色A姓名", "角色B姓名", ...], // 列出场景中参与对话的所有角色姓名
                    "主题": "场景对话的核心主题或讨论的问题",
                    "时间": "{age}岁", // 场景发生时角色的年龄
                    "背景": "场景发生的背景或原因，简述 '{exp_desc}'",
                    "对话": "角色间的具体对话内容，格式为：\"角色名：（动作/表情描述）对话内容。角色名：（动作/表情描述）对话内容。...\"，至少五轮。必须详细描述动作、表情、语气。"
                }}

                **输出格式** (单个JSON对象):
                {{
                    "场景": "...",
                    "参与者": ["..."],
                    "主题": "...",
                    "时间": "...",
                    "背景": "...",
                    "对话": "..."
                }}

                请严格按照上述格式输出单个JSON对象，不要添加其他解释文字。
                """

                user_prompt = f"请为 {age} 岁时的经历 '{exp_desc}' 构建一个详细的对话场景。"

                try:
                    raw_result = await self.character_llm.client.generate_response(system_prompt, user_prompt)
                    print(f"=== LLM 生成场景原始响应 (完整) ===")
                    print(raw_result)
                    print(f"=== 响应长度: {len(raw_result)} ===")

                    # 尝试解析为单个 JSON 对象
                    try:
                        parsed_scene = json.loads(raw_result)
                        if isinstance(parsed_scene, dict):
                            # 为每个场景生成唯一 ID
                            scene_id = str(uuid.uuid4())
                            # 添加 ID 并可能调整结构以符合系统期望（如果需要作为记忆存储）
                            processed_scene = {
                                "id": scene_id, # 添加唯一 ID
                                "scene": parsed_scene.get("场景"),
                                "participants": parsed_scene.get("参与者", []),
                                "topic": parsed_scene.get("主题"),
                                "time_at_occurrence": parsed_scene.get("时间"),
                                "context": parsed_scene.get("背景"),
                                "dialogue_content": parsed_scene.get("对话"),
                                "original_context": raw_result # 可选：存储原始响应片段
                            }
                            generated_scenes.append(processed_scene)
                        else:
                            log_warning(f"LLM 为 {age} 岁场景 {i+1} 返回的不是 JSON 对象: {type(parsed_scene)}")
                    except json.JSONDecodeError as e:
                        log_error(f"解析 LLM 为 {age} 岁场景 {i+1} 生成的 JSON 失败: {e}")
                        log_error(f"原始响应: {raw_result[:500]}...") # 记录前500字符以便调试
                        continue # 跳过此场景

                except Exception as e:
                    log_error(f"为 {age} 岁场景 {i+1} 生成对话失败: {e}")
                    import traceback
                    traceback.print_exc()
                    continue # 跳过此场景

        log_success(f"为角色 {main_character.get('name')} 生成了 {len(generated_scenes)} 个结构化对话场景")
        log_info(f"生成结构化对话场景耗时: {time.time() - start_time:.2f} 秒")
        # **修改：返回场景列表，而不是章节列表**
        return generated_scenes

    async def generate_character_lifespan_story(self, character_data: Dict[str, Any], related_characters: List[Dict[str, Any]], relationships: List[Dict[str, Any]]) -> str: # 保持返回完整故事字符串的接口，用于其他可能的用途
        log_info(f"开始为角色 {character_data.get('name')} 生成人生故事 (新流程)...")
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

        # 直接使用已有的时间线内容生成结构化对话场景，不再补全背景故事
        structured_scenes = await self.generate_chaptered_lifespan_story(character_data, related_characters, story_idea.get('story_idea', ''))

        # **如果仍需要完整字符串（例如用于关系推断），可以在这里拼接场景对话内容**
        # full_story_string = "\n\n".join([scene["dialogue_content"] for scene in structured_scenes])
        full_story_string = json.dumps(structured_scenes, ensure_ascii=False, indent=2) # 或者其他合适的格式

        log_success(f"角色 {character_data.get('name')} 的人生故事 (结构化对话) 生成完成")
        log_info(f"总耗时: {time.time() - start_time:.2f} 秒")
        return full_story_string # 返回 JSON 字符串或拼接的字符串，取决于其他地方的调用方式

    async def extract_memories_from_lifespan_story(self, chaptered_stories: List[Dict[str, Any]], character_data: Dict[str, Any], related_characters: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        log_info(f"开始从分章节故事中提取对话场景 (新格式)...")
        start_time = time.time()
        # 构建名称到ID的映射表（用于验证参与者）
        name_to_id_map = {}
        name_to_id_map[character_data.get('name')] = character_data.get('id')
        for rc in related_characters:
            name_to_id_map[rc.get('name')] = rc.get('id')

        all_char_map = {character_data['id']: character_data}
        all_char_map.update({rc['id']: rc for rc in related_characters})

        extracted_memories = []
        for chapter_info in chaptered_stories:
            chapter_content = chapter_info["content"]
            chapter_start_age = chapter_info["start_age"]
            chapter_end_age = chapter_info["end_age"]
            chapter_label = chapter_info["label"]
            log_info(f" - 从章节 {chapter_start_age}-{chapter_end_age}岁 ({chapter_label}) 提取对话场景...")

            # **修改：Prompt 用于提取对话场景**
            system_prompt = f"""
            你是记忆考古学家，任务是仔细阅读关于"{character_data.get('name')}"在{chapter_start_age}-{chapter_end_age}岁 ({chapter_label})的特定故事片段，并从中识别出所有包含**关键对话**的重要场景。

            **重要要求**：
            1.  **时间线**: 所有提取的场景都必须发生在 {chapter_start_age}-{chapter_end_age} 岁之间。请根据故事内容推断具体场景发生时的年龄。
            2.  **对话场景**: 识别出包含至少五轮对话的场景。
            3.  **格式化输出**: 为每个识别出的场景生成一个符合以下 JSON 格式的条目：
            {{
                "场景": "场景发生的具体地点（如 家中, 学校教室, 公园等）",
                "参与者": ["角色A姓名", "角色B姓名", ...], // 列出场景中参与对话的所有角色姓名
                "主题": "场景对话的核心主题或讨论的问题",
                "时间": "场景发生时角色的年龄（如 14.25岁）",
                "背景": "场景发生的背景或原因",
                "对话": "角色间的具体对话内容，格式为：\"角色名：（动作/表情描述）对话内容。角色名：（动作/表情描述）对话内容。...\"，至少五轮。"
            }}

            **输出格式** (JSON数组):
            [
                {{
                    "场景": "...",
                    "参与者": ["..."],
                    "主题": "...",
                    "时间": "...",
                    "背景": "...",
                    "对话": "..."
                }},
                ...
            ]

            请直接返回JSON数组，不要添加其他解释文字。
            """

            user_prompt = f"""以下是关于{character_data.get('name')}在{chapter_start_age}-{chapter_end_age}岁 ({chapter_label}) 的故事片段，请从中提取符合上述格式的对话场景。请务必阅读整个片段，识别包含至少五轮对话的场景，并按照指定的JSON格式输出。

            {chapter_content}"""

            try:
                # **重要：修改返回格式预期**
                # LLM 应该返回一个 JSON 数组，每个元素是一个对话场景
                raw_result = await self.character_llm.client.generate_response(system_prompt, user_prompt)
                print(f"=== LLM 提取对话场景原始响应 (完整) ===")
                print(raw_result)
                print(f"=== 响应长度: {len(raw_result)} ===")

                # 尝试解析整个响应为 JSON 数组
                try:
                    parsed_scenes = json.loads(raw_result)
                    if isinstance(parsed_scenes, list):
                        for scene in parsed_scenes:
                            # 为每个场景生成一个唯一的 ID
                            scene_id = str(uuid.uuid4())
                            # 添加 ID 并可能调整结构以符合系统期望（如果需要作为记忆存储）
                            processed_scene = {
                                "id": scene_id, # 添加唯一 ID
                                "scene": scene.get("场景"),
                                "participants": scene.get("参与者", []),
                                "topic": scene.get("主题"),
                                "time_at_occurrence": scene.get("时间"),
                                "context": scene.get("背景"),
                                "dialogue_content": scene.get("对话"),
                                # ... 可能需要其他字段以符合 MemoryResponse 或其他存储格式 ...
                                "original_context": raw_result # 可选：存储原始响应片段
                            }
                            extracted_memories.append(processed_scene)
                    else:
                        log_warning(f"LLM 返回的不是 JSON 数组: {type(parsed_scenes)}")
                        # 可以选择跳过或尝试其他处理方式
                except json.JSONDecodeError as e:
                    log_error(f"解析 LLM 提取的对话场景 JSON 失败: {e}")
                    log_error(f"原始响应: {raw_result[:500]}...") # 记录前500字符以便调试
                    # 可以选择跳过此章节或尝试从原始响应中提取
                    # 这里我们跳过，因为格式不匹配
                    continue

            except Exception as e:
                log_error(f"从章节 {chapter_start_age}-{chapter_end_age}岁 提取对话场景失败: {e}")
                traceback.print_exc() # 打印完整堆栈跟踪
                continue # 继续处理下一个章节

        log_success(f"从分章节故事中总共提取了 {len(extracted_memories)} 个对话场景 (新格式)")
        log_info(f"提取对话场景耗时: {time.time() - start_time:.2f} 秒")
        return extracted_memories

    async def extract_entities_and_relationships_from_story(self, story_text: str, character_data: Dict[str, Any], related_characters: List[Dict[str, Any]], extracted_memories: List[Dict[str, Any]], graph_store) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        修改：接收结构化的对话场景列表 (extracted_memories) 来提取实体和关系。
        story_text 在新流程中可能只是 JSON 字符串，不再用于提取。
        """
        log_info(f"开始从结构化对话场景中提取实体和关系 (新模型)...")
        start_time = time.time()

        # **修改：现在直接处理 extracted_memories (即 structured_scenes)**
        scenes_to_process = extracted_memories # 这些已经是结构化的场景

        # 1. 提取实体（人物、地点、物品、事件等）
        # 人物实体已包含在 character_data 和 related_characters 中
        entities = []
        # 从场景中提取地点、物品作为实体
        for scene in scenes_to_process:
            location = scene.get('scene') # "场景" 字段对应地点
            if location:
                location_entity = {
                    "app_id": str(uuid.uuid4()),
                    "name": location,
                    "type": "Place",
                    "description": f"场景 '{scene.get('topic', '')}' 发生的地点",
                    "properties": {}
                }
                entities.append(location_entity)

            # 从对话内容中提取可能的物品（这比较复杂，可以简化或省略）
            # dialogue_content = scene.get('dialogue_content', '')
            # ... (可能需要 NLP 来提取物品) ...
            # items = extract_items_from_dialogue(dialogue_content) # 假设有个函数
            # for item_name in items:
            #     item_entity = {"app_id": str(uuid.uuid4()), "name": item_name, "type": "Item", ...}
            #     entities.append(item_entity)

            # 主题也可以作为一个概念实体
            topic = scene.get('topic')
            if topic:
                topic_entity = {
                    "app_id": str(uuid.uuid4()),
                    "name": topic,
                    "type": "Concept",
                    "description": f"场景 '{scene.get('scene', '')}' 的主题",
                    "properties": {}
                }
                entities.append(topic_entity)

        # 2. 提取关系（主要是角色-事件、事件-地点、事件-主题等）
        relationships = []
        # 这部分逻辑需要根据 GraphStore 的 CSV 导入结构进行调整
        # 例如，为每个场景创建一个 Event 节点，并建立相关关系
        # (这部分逻辑在 graph_store.save_entities_and_relationships_to_csv 中处理)

        log_success(f"从结构化对话场景中提取了 {len(entities)} 个非人物实体")
        log_info(f"提取实体和关系耗时: {time.time() - start_time:.2f} 秒")

        # 关系链由 GraphStore 基于参与者和时间线生成，这里只返回实体
        return [], [], [] # (entities, non_event_relationships, char_to_char_relationships)