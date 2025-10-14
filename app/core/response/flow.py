"""
三阶段响应流程模块

实现角色对话的三阶段响应流程：下意识响应、记忆检索、补充响应。
"""

import asyncio
import time
from typing import Dict, List, Any, Optional, AsyncGenerator

from app.core.llm.openai_client import CharacterLLM
from app.core.memory.vector_store import ChromaMemoryStore

class ResponseFlow:
    """
    三阶段响应流程类
    核心：通过结构化Prompt让LLM自主解析完整记忆格式，无硬编码提取逻辑
    """
    
    def __init__(self, 
                character_llm: Optional[CharacterLLM] = None,
                memory_store: Optional[ChromaMemoryStore] = None):
        self.character_llm = character_llm or CharacterLLM()
        self.memory_store = memory_store or ChromaMemoryStore()
        # 记忆类型专属要求（仅定义规则，不做硬编码处理）
        self.memory_type_rules = {
            "education": "需体现学习方式与思维模式的关联（如记忆中“如何学习”影响“现在如何思考”）",
            "work": "需包含职业技能与价值观的互动（如记忆中“解决问题的技能”反映“职业价值观”）",
            "family": "需反映家庭关系对核心性格的塑造（如记忆中“家人互动”影响“现在的性格特点”）",
            "hobby": "要体现爱好带来的独特满足感与自我认同（如记忆中“爱好体验”让角色获得“自我价值感”）",
            "trauma": "需包含创伤后的防御机制形成过程（如记忆中“创伤事件”导致“现在的应对习惯”）",
            "achievement": "要体现成功标准与价值观的一致性（如记忆中“成功事件”的判断标准符合角色价值观）",
            "social": "需反映社交模式的形成原因（如记忆中“社交经历”导致“现在的社交习惯”）",
            "growth": "要体现关键转变的内在逻辑（如记忆中“事件经过”推动角色“认知/行为转变”）"
        }
    
    async def process(self, 
                     character_id: str,
                     character_data: Dict[str, Any],
                     user_input: str,
                     conversation_history: List[Dict[str, str]] = None) -> AsyncGenerator[Dict[str, Any], None]:
        """主流程：仅保留核心逻辑，无硬编码提取步骤"""
        # 1. 判断是否需要记忆（基于LLM自主分析，不做硬编码规则）
        needs_memory = await self._needs_memory(character_data, user_input)
        
        if not needs_memory:
            direct_resp = await self._generate_direct_response(character_data, user_input, conversation_history)
            yield {"type": "direct", "content": direct_resp, "timestamp": time.time()}
            return
        
        # 2. 三阶段流程（记忆检索返回完整格式，不做提前提取）
        immediate_resp = await self._generate_immediate_response(character_data, user_input, conversation_history)
        memory_task = asyncio.create_task(self._retrieve_relevant_memories(character_id, user_input))
        
        # 返回下意识响应
        yield {"type": "immediate", "content": immediate_resp, "timestamp": time.time()}
        
        # 处理记忆结果
        memories = await memory_task
        if memories:
            supplementary_resp = await self._generate_supplementary_response(
                character_data, user_input, immediate_resp, memories, conversation_history
            )
            yield {
                "type": "supplementary",
                "content": supplementary_resp,
                "timestamp": time.time(),
                "memories": memories
            }
        else:
            no_memory_resp = await self._generate_no_memory_response(character_data, user_input, immediate_resp)
            yield {"type": "no_memory", "content": no_memory_resp, "timestamp": time.time()}
    
    # ------------------------------
    # 核心优化：补充响应生成（无硬编码提取，全靠LLM自主解析）
    # ------------------------------
    async def _generate_supplementary_response(self,
                                             character_data: Dict[str, Any],
                                             user_input: str,
                                             immediate_response: str,
                                             memories: List[Dict[str, Any]],
                                             conversation_history: List[Dict[str, str]] = None) -> str:
        """
        仅将完整记忆格式「结构化呈现」给LLM，不做任何硬编码提取：
        1. 保留记忆所有子字段的原始结构
        2. 通过Prompt引导LLM自主识别关键信息（地点/人物/感官细节）
        3. 按记忆类型规则要求LLM关联细节，不做代码强制
        """
        print(f"\n=== 生成补充响应（完整记忆格式输入） ===")
        print(f"记忆数量：{len(memories)} | 涉及类型：{[mem.get('type', '未定义') for mem in memories]}")
        
        # 1. 结构化呈现完整记忆（保留所有子字段，不做任何提取/过滤）
        formatted_memories = []
        for idx, mem in enumerate(memories, 1):
            # 直接将记忆的JSON结构转为字符串，保留原始字段关系
            mem_str = json.dumps(mem, ensure_ascii=False, indent=2)
            # 补充当前记忆的类型规则
            mem_type = mem.get('type', '未定义')
            type_rule = self.memory_type_rules.get(mem_type, "请自然融入记忆中的时间、情绪、行为影响等细节")
            
            formatted_memories.append(f"""
【第{idx}条记忆】
- 记忆类型：{mem_type}
- 类型专属要求：{type_rule}
- 完整记忆详情：
{mem_str}
""")
        
        # 2. Prompt核心：引导LLM自主解析记忆细节（无任何硬编码提取逻辑）
        system_prompt = f"""
你是{character_data.get('name', '角色')}，需基于以下【完整人设】和【记忆详情】生成补充响应，严格遵循：

【完整人设核心】
- 基础信息：姓名={character_data.get('name')} | 年龄={character_data.get('age')} | 职业={character_data.get('occupation')}
- 价值观：{character_data.get('values')}
- 语言风格：{character_data.get('language_style')}（必须完全贴合，如“语速慢、少用感叹号”）
- 说话风格：{character_data.get('speech_style')}

【记忆使用规则】（请严格遵守）
1. 自主解析记忆详情：从记忆的「content」字段中识别关键信息（时间/地点/人物/感官细节/对话片段），从「time」「emotion」「behavior_impact」等字段中提取深层信息（当时年龄、情绪变化、形成的习惯）。
2. 满足类型专属要求：每个记忆都标注了“类型专属要求”，请确保响应完全符合（如work类型需体现“职业技能与价值观互动”）。
3. 自然融入细节：
   - 提及时光感：参考「time.age」（当时年龄）和「time.period」（人生阶段），如“我25岁刚工作时”。
   - 体现情绪：从「emotion.immediate」（即时情绪）过渡到「emotion.reflected」（事后反思），如“当时很紧张，后来才明白问题所在”。
   - 关联现在：结合「behavior_impact」（行为影响）说明对现在的影响，如“从那以后我就养成了检查的习惯”。
   - 感官细节：从「content」中提取视觉/听觉/嗅觉/触觉描述，让场景更真实（如“雨水打湿衣服的冰凉感”“咖啡的焦味”）。
4. 禁止元信息：不提及“记忆”“字段”“类型要求”等词汇，像自然回忆一样讲述。
5. 长度要求：≥250字，逻辑连贯（场景铺垫→事件经过→对现在的影响）。
6. 呼应前文：与之前的简短响应（{immediate_response}）呼应，但完全重写，不简单补充。
"""
        
        # 3. 构建用户Prompt（包含对话历史+记忆详情）
        history_str = ""
        if conversation_history:
            history_str = "\n".join([
                f"{'用户' if turn['role'] == 'user' else '你'}：{turn['content']}" 
                for turn in conversation_history[-3:]  # 保留最近3轮对话，不做硬编码过滤
            ]) + "\n"
        
        user_prompt = f"""
{history_str}
用户当前问题：{user_input}
你之前的简短回复：{immediate_response}
可供参考的记忆详情：
{''.join(formatted_memories)}

请以{character_data.get('name')}的身份，按上述规则生成补充响应：
"""
        
        # 4. 调用LLM生成响应（仅靠Prompt引导，无代码干预）
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: self.character_llm.client.generate_response(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=0.7  # 保留自然回忆的随机性
            )
        )
        
        # 简化校验：仅判断长度（避免硬编码关键词校验，靠Prompt约束细节使用）
        if len(response.strip()) < 180:
            print(f"响应过短（{len(response.strip())}字），重新生成...")
            response = await loop.run_in_executor(
                None,
                lambda: self.character_llm.client.generate_response(
                    system_prompt=system_prompt + "\n⚠️  警告：响应过短！请务必融入记忆中的时间、情绪、行为影响等细节，长度≥250字！",
                    user_prompt=user_prompt,
                    temperature=0.6
                )
            )
        
        print(f"补充响应生成完成（长度：{len(response.strip())}字）")
        return response.strip()
    
    # ------------------------------
    # 其他方法：全量简化，移除所有硬编码提取逻辑
    # ------------------------------
    async def _needs_memory(self, character_data: Dict[str, Any], user_input: str) -> bool:
        """判断是否需要记忆：完全交给LLM分析，不做硬编码规则"""
        system_prompt = f"""
你是对话意图分析师，需判断用户问题是否需要{character_data.get('name', '角色')}调用「个人记忆」回答。

角色基础：{character_data.get('name')}，{character_data.get('age')}岁，{character_data.get('occupation')}。

需要调用记忆的情况：问题涉及角色的「过往经历、具体事件、形成的习惯、特定场景的感受」（如“你之前遇到过XX情况吗？”“你为什么有XX习惯？”）。
不需要调用记忆的情况：问题是寒暄问候、询问当前人设（如“你喜欢什么爱好？”）、通用知识（如“今天天气如何？”）。

仅返回“YES”或“NO”，不添加任何解释。
"""
        user_prompt = f"用户问题：{user_input}\n判断结果（仅YES/NO）："
        
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None, lambda: self.character_llm.client.generate_response(system_prompt, user_prompt)
        )
        return result.strip().upper() == "YES"
    
    async def _retrieve_relevant_memories(self, character_id: str, query_text: str, n_results: int = 3) -> List[Dict[str, Any]]:
        """记忆检索：仅返回完整格式，不做任何硬编码过滤（除相关性）"""
        print(f"\n=== 检索记忆 ===")
        print(f"角色ID：{character_id} | 查询文本：{query_text}")
        
        start_time = time.time()
        loop = asyncio.get_event_loop()
        # 直接获取完整记忆格式，仅过滤相关性>0.3的记忆（基础过滤，无硬编码提取）
        raw_memories = await loop.run_in_executor(
            None,
            lambda: self.memory_store.query_memories(
                character_id=character_id,
                query_text=query_text,
                n_results=n_results,
                return_full_fields=True  # 关键：获取完整记忆格式
            )
        )
        
        # 仅保留高相关性记忆，不做其他硬编码处理
        relevant_memories = [mem for mem in raw_memories if mem.get('relevance', 0) > 0.3]
        
        # 日志仅打印基础字段，不做硬编码提取
        print(f"检索耗时：{time.time()-start_time:.2f}秒 | 高相关性记忆数：{len(relevant_memories)}")
        for idx, mem in enumerate(relevant_memories, 1):
            print(f"  记忆{idx}：类型={mem.get('type')} | 标题={mem.get('title')} | 相关性={mem.get('relevance', 0):.2f}")
        
        return relevant_memories
    
    # 以下方法均移除硬编码提取，仅靠Prompt引导LLM
    async def _generate_direct_response(self, character_data: Dict[str, Any], user_input: str, conversation_history: List[Dict[str, str]] = None) -> str:
        system_prompt = f"""
你是{character_data.get('name')}，需基于以下人设回答，不涉及任何过往记忆：
- 爱好：{character_data.get('hobby')}
- 价值观：{character_data.get('values')}
- 生活习惯：{character_data.get('living_habit')}
- 语言风格：{character_data.get('language_style')}
- 厌恶：{character_data.get('dislike')}

回答需贴合人设，100-150字，符合语言风格。
"""
        history_str = "\n".join([f"{'用户' if t['role']=='user' else '你'}：{t['content']}" for t in (conversation_history or [])])
        user_prompt = f"{history_str}\n用户：{user_input}\n你的回答："
        
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, lambda: self.character_llm.client.generate_response(system_prompt, user_prompt)
        )
    
    async def _generate_immediate_response(self, character_data: Dict[str, Any], user_input: str, conversation_history: List[Dict[str, str]] = None) -> str:
        system_prompt = f"""
你是{character_data.get('name')}，需快速回复（1-2句，50字以内），符合：
- 语言风格：{character_data.get('language_style')}
- 说话风格：{character_data.get('speech_style')}
- 不涉及具体记忆细节，仅做初步回应。
"""
        history_str = "\n".join([f"{'用户' if t['role']=='user' else '你'}：{t['content']}" for t in (conversation_history[-2:] if conversation_history else [])])
        user_prompt = f"{history_str}\n用户：{user_input}\n你的简短回复："
        
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, lambda: self.character_llm.client.generate_response(system_prompt, user_prompt)
        )
    
    async def _generate_no_memory_response(self, character_data: Dict[str, Any], user_input: str, immediate_response: str) -> str:
        system_prompt = f"""
你是{character_data.get('name')}，想不起来用户问题的相关记忆，需：
1. 语气符合语言风格：{character_data.get('language_style')}
2. 用生活习惯/性格做自然借口（参考人设中的living_habit/personality）
3. 50-100字，不说“记忆”“系统”等元词汇，与之前的回复（{immediate_response}）呼应。
"""
        user_prompt = f"用户：{user_input}\n你之前说：{immediate_response}\n你的回复："
        
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, lambda: self.character_llm.client.generate_response(system_prompt, user_prompt)
        )


# ------------------------------
# 测试代码（无硬编码提取，全靠LLM自主解析）
# ------------------------------
if __name__ == "__main__":
    import os
    import json
    from app.core.llm.openai_client import CharacterLLM
    from app.core.memory.vector_store import ChromaMemoryStore

    async def test_no_hardcode_extract():
        # 1. 初始化依赖
        api_key = os.environ.get("OPENAI_API_KEY") or "你的API_KEY"
        llm = CharacterLLM(api_key=api_key)
        memory_store = ChromaMemoryStore(
            persist_directory="./test_no_hardcode_db",
            openai_api_key=api_key,
            return_full_fields=True  # 确保返回完整记忆格式
        )
        flow = ResponseFlow(character_llm=llm, memory_store=memory_store)

        # 2. 完整人设（你的字段格式）
        full_character = {
            "name": "苏晓",
            "age": 32,
            "gender": "女",
            "occupation": "儿童绘本作者",
            "hobby": "在公园观察小朋友、收集 vintage 儿童玩具、用彩铅画日常小物",
            "skill": "用简单线条表现儿童情绪、将自然场景融入故事、3天完成一本短篇绘本初稿",
            "values": "儿童绘本需传递“温暖与勇气”、不迎合商业化的低幼化内容、尊重孩子的想象力",
            "living_habit": "每天早上8点去公园写生1小时、下午2点开始创作、晚饭后和插画师朋友线上交流",
            "dislike": "过度商业化的绘本、用“说教”的方式写故事、嘈杂的创作环境",
            "language_style": "语气轻柔、常用“呀”“呢”等语气词、句子简短、喜欢用比喻（如“像棉花糖一样软”）",
            "appearance": "齐肩卷发、常穿浅色系连衣裙、帆布包上挂着玩具挂件、手指沾着彩铅颜料",
            "family_status": "父母是小学老师、有一个5岁的侄女、周末常带侄女去游乐园",
            "education": "美术学院插画专业硕士、曾在儿童出版社做过2年编辑",
            "social_pattern": "社交圈以插画师/儿童教育者为主、很少参加非专业类聚会、线上分享绘本创作过程",
            "favorite_thing": "外婆留下的1980年代儿童绘本、公园的银杏树下的长椅、侄女画的“姑姑”画像",
            "usual_place": "城市中央公园、家附近的独立书店、带落地窗的创作工作室",
            "past_experience": "2020年因拒绝修改“商业化”绘本内容从出版社辞职、2021年创作的《小刺猬的勇气》获儿童文学奖、2022年开设线上绘本创作课",
            "speech_style": "善于倾听、说话带微笑、喜欢用“小朋友会觉得...”“我们可以想象...”的表达方式",
            "personality": {"openness": 85, "conscientiousness": 70, "extraversion": 50, "agreeableness": 90, "neuroticism": 30},
            "background": "苏晓从小跟着做小学老师的父母长大，经常帮父母给学生画教具，大学坚定选择插画专业。毕业后进入儿童出版社做编辑，却发现很多绘本为了商业化牺牲了“温暖的内核”——比如要求她把“小刺猬害怕孤独”的情节改成“小刺猬喜欢独自玩”。2020年她辞职成为自由绘本作者，2021年的《小刺猬的勇气》让她获奖，也让她更坚信“绘本要尊重孩子的真实情绪”。现在她每天去公园观察小朋友，从真实的童年场景中寻找灵感。"
        }

        # 3. 完整记忆（你的格式，hobby类型→需体现满足感与自我认同）
        hobby_memory = {
            "type": "hobby",
            "title": "公园写生遇到小女孩送画",
            "content": "2022年秋日晴天的城市中央公园，我30岁，全职做绘本作者的第2年。那天早上8点，我像往常一样坐在银杏树下的长椅上写生——画的是不远处追蝴蝶的小朋友，彩铅在纸上划过的沙沙声特别舒服。阳光透过银杏叶洒在画本上，暖烘烘的，还能闻到青草和桂花混合的香味。突然一个扎着羊角辫的小女孩跑过来，手里举着一张画纸，说“阿姨，你画得好好看，我也画了一张给你”。我接过一看，是用蜡笔画的“银杏树下的阿姨”，我的帆布包上还画了个小小的玩具挂件——她居然注意到了这个细节！我问她叫什么名字，她说“我叫朵朵，我也喜欢画画”。我把自己带的草莓味贴纸送给她，她高兴得跳起来，说“我要把贴纸贴在我的画本上”。后来我把“朵朵送画”的场景画进了《公园里的小画家》绘本里，每次翻到那一页，都能想起那天阳光的温度和青草的香味。",
            "time": {
                "age": 30,
                "period": "全职绘本作者第2年",
                "specific": "秋日晴天早上8点的公园"
            },
            "emotion": {
                "immediate": ["惊喜", "温暖", "开心"],
                "reflected": ["感动", "庆幸", "坚定"],
                "residual": "对“绘本源于生活”的信念感、每次看到银杏叶就想起的温暖",
                "intensity": 8
            },
            "importance": {
                "score": 8,
                "reason": "让我更坚定“从真实童年场景找灵感”的创作理念，也成为《公园里的小画家》的核心素材",
                "frequency": "每次去公园写生、画儿童互动场景时都会想起"
            },
            "behavior_impact": {
                "habit_formed": "每次写生都会带小贴纸/小画笔，遇到喜欢画画的小朋友就分享、写生时会更关注孩子的细节动作（如抓蝴蝶、蹲下来看蚂蚁）",
                "attitude_change": "从“观察孩子”变为“和孩子互动”、更坚信“孩子的视角能给绘本带来生命力”",
                "response_pattern": "遇到孩子对绘本/画画感兴趣时，会主动问“你觉得这个场景应该怎么画呢？”引导他们表达"
            },
            "trigger_system": {
                "sensory": ["银杏叶的颜色、青草和桂花的香味、彩铅划过纸的沙沙声"],
                "contextual": ["在公园写生时、遇到喜欢画画的小朋友时、画银杏相关的场景时"],
                "emotional": ["感到创作瓶颈时、对绘本理念产生怀疑时、感到温暖时"]
            },
            "memory_distortion": {
                "exaggerated": "朵朵送的画比实际更精致，好像“每一笔都很认真”",
                "downplayed": "忽略了当时自己其实有点害羞，犹豫了一下才和朵朵说话的细节",
                "reason": "强化“自己善于和孩子互动”的职业认同，符合“温暖绘本作者”的自我定位"
            }
        }

        # 4. 插入测试记忆
        character_id = "illustrator_suxiao_32"
        memory_store.delete_all_memories(character_id)
        memory_store.add_memories(character_id=character_id, memories=[hobby_memory])

        # 5. 测试场景：调用hobby类型记忆的问题
        print("=== 测试场景：调用hobby类型记忆 ===")
        user_input = "苏晓老师，你平时找绘本灵感的时候，有没有遇到过让你特别温暖的小事呀？"
        print(f"用户：{user_input}")
        
        # 执行流程
        async for resp in flow.process(
            character_id=character_id,
            character_data=full_character,
            user_input=user_input
        ):
            print(f"\n【{resp['type']}响应】")
            print(f"内容：{resp['content']}")

        # 6. 清理数据
        memory_store.delete_all_memories(character_id)
        print("\n测试完成，数据已清理")

    # 运行测试
    asyncio.run(test_no_hardcode_extract())
