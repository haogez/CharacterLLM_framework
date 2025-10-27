# app/core/graph/relationship_generator.py
"""
人物关系图谱生成器模块

负责生成主角色的关联角色、关系结构以及与这些关系绑定的记忆。
"""

import asyncio
import json
import uuid
from typing import Dict, List, Any, Optional, Tuple
from app.core.llm.openai_client import CharacterLLM
from app.core.character.generator import CharacterGenerator # 导入现有的角色生成器


class RelationshipGenerator:
    """
    人物关系图谱生成器

    负责生成关联角色、关系结构和关系记忆。
    """

    def __init__(self, character_llm: CharacterLLM):
        """
        初始化生成器

        Args:
            character_llm (CharacterLLM): 用于调用LLM的客户端实例
        """
        self.character_llm = character_llm
        self.character_generator = CharacterGenerator(character_llm) # 复用现有的角色生成逻辑

    async def generate_related_characters(self, main_character: Dict[str, Any], count: int) -> List[Dict[str, Any]]:
        """
        生成与主角色相关的角色列表。

        Args:
            main_character (Dict[str, Any]): 主角色的完整数据
            count (int): 需要生成的关联角色数量

        Returns:
            List[Dict[str, Any]]: 生成的关联角色列表
        """
        print(f"--- 开始生成 {count} 个关联角色 ---")

        # 构建系统提示，引导LLM生成与主角色紧密相关的角色
        system_prompt = f"""
        你是角色关联网络构建专家。你的任务是为角色"{main_character.get('name')}"生成{count}个与他/她生活、工作、情感等方面紧密相关的其他角色。

        核心原则：
        1.  关联性：每个角色都必须与"{main_character.get('name')}"有明确的联系（家庭成员、同事、朋友、对手、服务提供者等）。
        2.  多样性：角色类型应尽可能多样，涵盖"{main_character.get('name')}"生活的不同方面（如家庭、工作、社交、兴趣）。
        3.  人设一致性：生成的角色人设必须与"{main_character.get('name')}"的人设、背景、价值观等不冲突，并能形成互动。
        4.  记忆基础：这些角色将成为"{main_character.get('name')}"重要记忆的载体或参与者。

        输出要求：
        - 严格按照JSON格式输出，包含一个 "related_characters" 列表，列表中每个元素是一个完整的角色对象（结构与主角色一致，包含name, age, gender, occupation, hobby, skill, values, living_habit, dislike, language_style, appearance, family_status, education, social_pattern, favorite_thing, usual_place, past_experience, speech_style, personality, background）。
        - 生成的角色必须有具体的姓名、年龄、职业等，使其具有独特性。
        - 生成的角色背景故事应简要提及与"{main_character.get('name')}"的关联。
        - 禁止输出任何解释性文字，仅输出JSON。
        """
        user_prompt = f"""
        主角色信息：
        {json.dumps(main_character, ensure_ascii=False, indent=2)}

        请生成{count}个关联角色：
        """

        # 调用LLM生成关联角色
        result = await self.character_llm.client.generate_structured_response(system_prompt, user_prompt)
        related_characters = result.get("related_characters", [])

        # 为每个生成的角色分配一个唯一的ID
        for char in related_characters:
            if "id" not in char:
                char["id"] = str(uuid.uuid4())

        print(f"--- 生成了 {len(related_characters)} 个关联角色 ---")
        return related_characters

    async def generate_relationships(self, main_character: Dict[str, Any], related_characters: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        生成主角色与关联角色之间的关系，以及主角色的自关系。

        Args:
            main_character (Dict[str, Any]): 主角色数据
            related_characters (List[Dict[str, Any]]): 关联角色列表

        Returns:
            List[Dict[str, Any]]: 关系列表，每条关系包含character1_id, character2_id, relationship_type, strength, description, history, memories
        """
        print("--- 开始生成关系结构 ---")
        relationships = []
        main_id = main_character["id"]

        # 1. 生成主角色的自关系
        self_relationship = {
            "relationship_id": f"{main_id}_self",
            "character1_id": main_id,
            "character2_id": main_id, # 自关系
            "relationship_type": "self",
            "strength": 10, # 自我认知通常很强
            "description": f"{main_character.get('name')} 的自我认知、个人反思和独处经历",
            "history": f"代表{main_character.get('name')}的个人历史、内心世界和独立活动。",
            "memories": [] # 初始时无记忆
        }
        relationships.append(self_relationship)

        # 2. 生成主角色与每个关联角色的关系
        for related_char in related_characters:
            related_id = related_char["id"]
            # 确定关系类型
            rel_type = self._infer_relationship_type(main_character, related_char)

            # 生成关系描述和历史
            system_prompt = f"""
            你是关系分析师，需要分析角色"{main_character.get('name')}"和"{related_char.get('name')}"之间的关系。

            角色A ("{main_character.get('name')}"): {main_character.get('occupation')}, {main_character.get('values')}
            角色B ("{related_char.get('name')}"): {related_char.get('occupation')}, {related_char.get('values')}

            请判断他们的关系类型，并用1-2句话描述这种关系的核心特征和互动模式。
            """
            user_prompt = f"关系类型选项：family, work, friend, romantic, adversarial, service (如医生-病人), other. 请分析并描述："

            analysis_result = await self.character_llm.client.generate_response(system_prompt, user_prompt)
            # 这里可以进一步解析 analysis_result 来更精确地确定 type, strength, description, history
            # 简化处理，直接使用分析结果作为描述
            description = analysis_result.strip()

            relationship = {
                "relationship_id": f"{main_id}_{related_id}",
                "character1_id": main_id,
                "character2_id": related_id,
                "relationship_type": rel_type,
                "strength": 5, # 默认中等强度，后续可基于记忆调整
                "description": description,
                "history": f"{main_character.get('name')} 和 {related_char.get('name')} 的关系历史摘要。",
                "memories": [] # 初始时无记忆
            }
            relationships.append(relationship)

        print(f"--- 生成了 {len(relationships)} 条关系 (包含1条自关系) ---")
        return relationships

    def _infer_relationship_type(self, main_char: Dict[str, Any], related_char: Dict[str, Any]) -> str:
        """
        根据两个角色的信息推断关系类型。

        Args:
            main_char (Dict[str, Any]): 主角色数据
            related_char (Dict[str, Any]): 关联角色数据

        Returns:
            str: 推断出的关系类型
        """
        # 简单规则推断，可根据需要扩展
        occupation = related_char.get('occupation', '').lower()
        family_status = related_char.get('family_status', '').lower()
        main_occ = main_char.get('occupation', '').lower()
        main_family = main_char.get('family_status', '').lower()
        social_pattern = related_char.get('social_pattern', '').lower()
        main_social_pattern = main_char.get('social_pattern', '').lower()

        # 检查家庭关系关键词
        family_keywords = ['parent', 'mother', 'father', 'sibling', 'brother', 'sister', 'child', 'son', 'daughter', 'spouse', 'husband', 'wife', 'partner', 'family', 'relative']
        if any(keyword in family_status.lower() for keyword in family_keywords) or \
           any(keyword in main_family.lower() for keyword in family_keywords) or \
           related_char.get('name') in main_char.get('family_status', '') or \
           main_char.get('name') in related_char.get('family_status', ''):
             return "family"
        # 检查浪漫关系关键词
        if 'spouse' in family_status or 'partner' in family_status or 'romantic' in family_status or 'married' in family_status:
             return "romantic"
        # 检查工作关系关键词
        if main_occ and occupation and (main_occ in occupation or occupation in main_occ):
             return "work"
        if 'colleague' in main_social_pattern or 'colleague' in social_pattern or 'work' in main_social_pattern or 'work' in social_pattern:
             return "work"
        # 检查朋友关系关键词
        if 'friend' in main_social_pattern or 'friend' in social_pattern:
             return "friend"
        # 检查对抗关系关键词
        if 'adversary' in main_social_pattern or 'adversary' in social_pattern or 'enemy' in main_social_pattern or 'enemy' in social_pattern:
             return "adversarial"
        # 检查服务关系关键词
        if 'customer' in main_social_pattern or 'customer' in social_pattern or 'client' in main_social_pattern or 'client' in social_pattern:
             return "service"
        # ... 其他规则
        return "other"


    async def generate_memories_for_relationship(self, main_character: Dict[str, Any], related_character: Optional[Dict[str, Any]], relationship_type: str) -> List[Dict[str, Any]]:
        """
        为特定关系（包括自关系）生成记忆。

        Args:
            main_character (Dict[str, Any]): 主角色数据
            related_character (Optional[Dict[str, Any]]): 关联角色数据，如果为自关系则为None
            relationship_type (str): 关系类型

        Returns:
            List[Dict[str, Any]]: 生成的记忆列表
        """
        log_info(f"为 {relationship_type} 关系生成记忆") # 使用新的日志工具函数

        # 根据关系类型调整Prompt，引导LLM生成相关记忆
        context_desc = ""
        if related_character:
            context_desc = f"与角色 '{related_character.get('name')}' ({related_character.get('occupation')}) 的互动经历。"
        else:
            context_desc = f"{main_character.get('name')} 的个人经历、自我反思或独处时光。"

        # 针对不同关系类型的Prompt调整
        type_specific_instruction = {
            "education": "生成与学习、成长、老师或同学相关的记忆。",
            "work": "生成与工作、同事、项目或职业发展相关的记忆。",
            "family": "生成与家庭成员互动、家庭事件或家庭情感相关的记忆。",
            "hobby": "生成与兴趣爱好、相关人物或活动相关的记忆。",
            "trauma": "生成与创伤事件、相关人物及影响相关的记忆。",
            "achievement": "生成与成就、认可、相关人物或庆祝活动相关的记忆。",
            "social": "生成与社交活动、朋友、聚会或人际关系相关的记忆。",
            "growth": "生成与个人转变、关键事件、相关人物及影响相关的记忆。",
            "self": "生成与个人独处、自我反思、内心感受或个人活动相关的记忆。"
        }

        instruction = type_specific_instruction.get(relationship_type, f"生成与'{relationship_type}'类型的记忆。")

        system_prompt = f"""
        你是"{main_character.get('name')}"的记忆塑造师。请生成一段符合'{relationship_type}'类型的深刻记忆。

        角色背景：{main_character.get('background')}
        相关背景：{context_desc}
        生成指令：{instruction}

        记忆需要包含时间、情感、重要性、行为影响、触发系统和记忆扭曲等维度，格式与完整记忆格式一致。
        请确保记忆内容符合角色的"{relationship_type}"关系背景和人设。

        重要：请直接返回一个包含多条记忆对象的JSON数组，格式如下：
        [
          {{
            "title": "...",
            "content": "...",
            "time": {{ "age": ..., "period": "...", "specific": "..." }},
            "emotion": {{ "immediate": [...], "reflected": [...], "residual": "...", "intensity": ... }},
            "importance": {{ "score": ..., "reason": "...", "frequency": "..." }},
            "behavior_impact": {{ "habit_formed": "...", "attitude_change": "...", "response_pattern": "..." }},
            "trigger_system": {{ "sensory": [...], "contextual": [...], "emotional": [...] }},
            "memory_distortion": {{ "exaggerated": "...", "downplayed": "...", "reason": "..." }}
          }},
          // ... 更多记忆对象
        ]
        请勿在外层添加其他字段（如 {{ "memories": [...] }}）。
        """

        # 让LLM一次性生成多条记忆
        user_prompt = f"请生成2-3段关于'{relationship_type}'类型的详细记忆："

        # 调用LLM生成结构化记忆
        result = await self.character_llm.client.generate_structured_response(system_prompt, user_prompt)
        print(f"--- LLM 返回的原始结果类型: {type(result)} ---")
        print(f"--- LLM 返回的原始结果内容 (前200字符): {str(result)[:200]}{'...' if len(str(result)) > 200 else ''} ---") # 简化打印

        # --- 修改：处理 result 可能是列表或字典的情况 ---
        if isinstance(result, list):
            # LLM 直接返回了记忆列表
            print("--- LLM 直接返回了记忆列表 ---")
            raw_generated_memories = result
        elif isinstance(result, dict):
            # LLM 返回了包含 memories 字段的对象
            print("--- LLM 返回了包含 memories 字段的对象 ---")
            raw_generated_memories = result.get("memories", [])
        else:
            # LLM 返回了非预期格式，可能包含错误
            print(f"--- 警告：LLM 返回了非预期格式: {type(result)} ---")
            print(f"--- 返回内容 (前200字符): {str(result)[:200]}{'...' if len(str(result)) > 200 else ''} ---")
            # 如果 result 包含 'text' 和 'error'，说明解析失败
            if isinstance(result, dict) and 'error' in result:
                 print(f"--- LLM 解析错误: {result.get('error')} ---")
            raw_generated_memories = []
        # ---

        # --- 修改：处理原始记忆数据，映射到完整格式 ---
        generated_memories = []
        for raw_mem in raw_generated_memories:
            if not isinstance(raw_mem, dict):
                print(f"--- 跳过非字典格式的记忆: {raw_mem} ---")
                continue

            # 创建符合完整记忆格式的字典
            processed_mem = {
                "title": raw_mem.get("title", f"关于 {relationship_type} 的记忆"),
                "content": raw_mem.get("content", raw_mem.get("内容", "")), # 尝试匹配 LLM 返回的中文键
                "time": raw_mem.get("time", {
                    "age": main_character.get("age", 30),
                    "period": raw_mem.get("时间", raw_mem.get("period", "未知")), # 尝试匹配 LLM 返回的中文键
                    "specific": raw_mem.get("specific", "未知")
                }),
                "emotion": raw_mem.get("emotion", {
                    "immediate": [],
                    "reflected": [],
                    "residual": raw_mem.get("情感", raw_mem.get("residual", "")), # 尝试匹配 LLM 返回的中文键
                    "intensity": 5
                }),
                "importance": raw_mem.get("importance", {
                    "score": 5,
                    "reason": raw_mem.get("重要性", raw_mem.get("reason", "")), # 尝试匹配 LLM 返回的中文键
                    "frequency": "偶尔想起"
                }),
                "behavior_impact": raw_mem.get("behavior_impact", {
                    "habit_formed": raw_mem.get("行为影响", raw_mem.get("habit_formed", "")), # 尝试匹配 LLM 返回的中文键
                    "attitude_change": raw_mem.get("attitude_change", ""),
                    "response_pattern": raw_mem.get("response_pattern", "")
                }),
                "trigger_system": raw_mem.get("trigger_system", {
                    "sensory": [],
                    "contextual": [raw_mem.get("触发系统", "")], # 尝试匹配 LLM 返回的中文键
                    "emotional": []
                }),
                "memory_distortion": raw_mem.get("memory_distortion", {
                    "exaggerated": raw_mem.get("记忆扭曲", raw_mem.get("exaggerated", "")), # 尝试匹配 LLM 返回的中文键
                    "downplayed": raw_mem.get("downplayed", ""),
                    "reason": raw_mem.get("reason", "")
                })
            }
            # 确保为记忆添加ID
            processed_mem["id"] = str(uuid.uuid4())
            generated_memories.append(processed_mem)
        
        log_success(f"为 {relationship_type} 关系生成了 {len(generated_memories)} 条记忆") # 使用新的日志工具函数
        return generated_memories
