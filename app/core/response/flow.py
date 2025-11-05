"""
三阶段响应流程模块 (Neo4j版)
"""

import asyncio
import json
import os
import time
from typing import Dict, List, Any, Optional, AsyncGenerator

from app.core.llm.openai_client import CharacterLLM
from app.core.graph.graph_store import GraphStore

class ResponseFlow:
    def __init__(self,
                character_llm: Optional[CharacterLLM] = None,
                graph_store: Optional[GraphStore] = None):
        self.character_llm = character_llm or CharacterLLM()
        self.graph_store = graph_store or GraphStore(
            # GraphStore 构造函数内部会使用 os.environ.get 和其自身的默认值
            # 这样更简洁，且确保 GraphStore 的逻辑是唯一的权威来源
        )
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
        start_time = time.time()
        needs_memory = await self._needs_memory(character_data, user_input)
        
        if not needs_memory:
            direct_resp = await self._generate_direct_response(character_data, user_input, conversation_history)
            yield {
                "type": "direct", 
                "content": direct_resp, 
                "timestamp": round(time.time() - start_time, 2)
            }
            return
        
        immediate_task = asyncio.create_task(self._generate_immediate_response(character_data, user_input, conversation_history))
        memory_task = asyncio.create_task(self._retrieve_relevant_memories_from_graph(character_id, user_input))
        
        immediate_resp = await immediate_task
        yield {
            "type": "immediate", 
            "content": immediate_resp, 
            "timestamp": round(time.time() - start_time, 2)
        }
        
        memories = await memory_task
        if memories:
            supplementary_resp = await self._generate_supplementary_response(
                character_data, user_input, immediate_resp, memories, conversation_history
            )
            yield {
                "type": "supplementary",
                "content": supplementary_resp,
                "timestamp": round(time.time() - start_time, 2),
                "memories": memories
            }
        else:
            no_memory_resp = await self._generate_no_memory_response(character_data, user_input, immediate_resp)
            yield {
                "type": "no_memory", 
                "content": no_memory_resp, 
                "timestamp": round(time.time() - start_time, 2)
            }

    async def _generate_supplementary_response(self,
                                             character_data: Dict[str, Any],
                                             user_input: str,
                                             immediate_response: str,
                                             memories: List[Dict[str, Any]],
                                             conversation_history: List[Dict[str, str]] = None) -> str:
        print("\n" + "="*60)
        print(f"📝 生成补充响应...")
        print(f"   角色: {character_data.get('name')}")
        print(f"   用户输入: {user_input}")
        print(f"   记忆数量: {len(memories)}")
        print("="*60)
        
        formatted_memories = []
        for idx, mem in enumerate(memories, 1):
            mem_to_format = {k: v for k, v in mem.items() if not k.startswith('_')}
            mem_type = mem.get('type', '未定义')
            mem_title = mem.get('title', f'记忆片段 {idx}')
            mem_location = mem.get('location', '未知地点')
            formatted_memories.append(f"""
【第{idx}条记忆片段】
- 记忆类型：{mem_type}
- 记忆标题：{mem_title}
- 发生地点：{mem_location}
- 涉及角色：{mem.get('participants', [])}
- 记忆标签：{mem.get('tags', [])}
""")
        
        system_prompt = f"""
你是{character_data.get('name', '角色')}，需基于以下【完整人设】和【记忆片段详情】生成补充响应，严格遵循：

【完整人设核心】
- 基础信息：姓名={character_data.get('name')} | 年龄={character_data.get('age')} | 职业={character_data.get('occupation')}
- 价值观：{character_data.get('values')}
- 语言风格：{character_data.get('language_style')}（必须完全贴合，如“语速慢、少用感叹号”）
- 说话风格：{character_data.get('speech_style')}

【记忆使用规则】（请严格遵守）
1. 自主解析记忆详情：从记忆的「content」字段中识别关键信息（时间/地点/人物/感官细节/对话片段），从「time」「emotion」「behavior_impact」等字段中提取深层信息（当时年龄、情绪变化、形成的习惯）。
2. 满足类型专属要求：每个记忆片段都标注了“类型专属要求”，请确保响应完全符合（如scene类型需体现“场景氛围”，dialogue类型需体现“对话内容”）。
3. 自然融入细节：
   - 提及其光感：参考「time.age」（当时年龄）和「time.period」（人生阶段），如“我25岁刚工作时”。
   - 体现情绪：从「emotion.immediate」（即时情绪）过渡到「emotion.reflected」（事后反思），如“当时很紧张，后来才明白问题所在”。
   - 关联现在：结合「behavior_impact」（行为影响）说明对现在的影响，如“从那以后我就养成了检查的习惯”。
   - 感官细节：从「content」中提取视觉/听觉/嗅觉/触觉描述，让场景更真实（如“雨水打湿衣服的冰凉感”“咖啡的焦味”）。
4. 利用细粒度信息：参考「location」（地点）、「tags」（标签）、「participants」（参与者）、「duration」（持续时间）等，让回答更具体、更贴合记忆。
5. 禁止元信息：不提及“记忆”“字段”“类型要求”等词汇，像自然回忆一样讲述。
6. 长度要求：≥250字，逻辑连贯（场景铺垫→事件经过→对现在的影响）。
7. 呼应前文：与之前的简短响应（{immediate_response}）呼应，但完全重写，不简单补充。
"""
        
        history_str = ""
        if conversation_history:
            history_str = "\n".join([
                f"{'用户' if turn['role'] == 'user' else '你'}：{turn['content']}" 
                for turn in conversation_history[-3:]
            ]) + "\n"
        
        user_prompt = f"""
{history_str}
用户当前问题：{user_input}
你之前的简短回复：{immediate_response}
可供参考的记忆片段详情：
{''.join(formatted_memories)}

请以{character_data.get('name')}的身份，按上述规则生成补充响应：
"""
        
        response = await self.character_llm.client.generate_response(system_prompt=system_prompt, user_prompt=user_prompt)
        
        if len(response.strip()) < 180:
            response = await self.character_llm.client.generate_response(
                system_prompt=system_prompt + "\n⚠️  警告：响应过短！请务必融入记忆中的时间、情绪、行为影响、地点、参与者等细节，长度≥250字！",
                user_prompt=user_prompt
            )
        
        print(f"✅ 补充响应生成完成 (长度: {len(response.strip())}字)")
        print("="*60 + "\n")
        return response.strip()
    
    async def _needs_memory(self, character_data: Dict[str, Any], user_input: str) -> bool:
        system_prompt = f"""
你是对话意图分析师，需判断用户问题是否需要{character_data.get('name', '角色')}调用「个人记忆片段」回答。

角色基础：{character_data.get('name')}，{character_data.get('age')}岁，{character_data.get('occupation')}。

需要调用记忆片段的情况：问题涉及角色的「过往经历、具体事件、形成的习惯、特定场景的感受、与他人的互动」（如“你之前遇到过XX情况吗？”“你为什么有XX习惯？”“你和XX之间发生过什么？”）。
不需要调用记忆片段的情况：问题是寒暄问候、询问当前人设（如“你喜欢什么爱好？”）、通用知识（如“今天天气如何？”）。

仅返回“YES”或“NO”，不添加任何解释。
"""
        user_prompt = f"用户问题：{user_input}\n判断结果（仅YES/NO）："
        
        result = await self.character_llm.client.generate_response(system_prompt, user_prompt)
        return result.strip().upper() == "YES"
    
    async def _retrieve_relevant_memories_from_graph(self, character_id: str, query_text: str, n_results: int = 5) -> List[Dict[str, Any]]:
        print("\n" + "="*60)
        print("🔍  开始从 Neo4j 图谱检索细粒度记忆片段...")
        print(f"   角色ID: {character_id}")
        print(f"   查询文本: {query_text}")
        print("="*60)

        start_time = time.time()
        all_raw_memories = self.graph_store.get_memories_for_character(character_id)
        print(f"⏱️  从 Neo4j 获取所有相关记忆片段耗时: {time.time()-start_time:.2f}秒")
        print(f"📊 获取到 {len(all_raw_memories)} 条原始记忆片段")

        if not all_raw_memories:
            print("   📌 未找到任何相关记忆片段")
            print("="*60 + "\n")
            return []

        try:
            query_embedding = await self.character_llm.client.create_embeddings([query_text])
            memory_contents = [mem.get('content', '') for mem in all_raw_memories]
            memory_embeddings = await self.character_llm.client.create_embeddings(memory_contents)
        except Exception as e:
            print(f"⚠️  使用 LLM 生成嵌入向量失败: {e}，将使用关键词匹配排序作为备选方案。")
            for mem in all_raw_memories:
                content = mem.get('content', '').lower()
                query_lower = query_text.lower()
                title_relevance = content.count(query_lower) / (len(content.split()) + 1)
                tags_relevance = sum(query_lower in tag.lower() for tag in mem.get('tags', []))
                participants_relevance = sum(query_lower in pid.lower() for pid in mem.get('participants', []))
                relevance_score = title_relevance + tags_relevance + participants_relevance
                mem['relevance'] = relevance_score
        else:
            import numpy as np
            def cosine_similarity(vec1, vec2):
                dot_product = np.dot(vec1, vec2)
                norm_vec1 = np.linalg.norm(vec1)
                norm_vec2 = np.linalg.norm(vec2)
                if norm_vec1 == 0 or norm_vec2 == 0:
                    return 0.0
                return dot_product / (norm_vec1 * norm_vec2)

            similarities = []
            for mem_emb in memory_embeddings:
                sim = cosine_similarity(np.array(query_embedding[0]), np.array(mem_emb))
                similarities.append(sim)

            for i, mem in enumerate(all_raw_memories):
                mem['relevance'] = similarities[i]

        all_raw_memories.sort(key=lambda x: x.get('relevance', 0), reverse=True)
        relevant_memories = all_raw_memories[:n_results]

        print(f"📊 排序后高相关性记忆片段数: {len(relevant_memories)}")
        for idx, mem in enumerate(relevant_memories, 1):
            print(f"   📌 记忆片段{idx}: 类型={mem.get('type')} | 标题={mem.get('title')} | 相关性={mem.get('relevance', 0):.2f} | 地点={mem.get('location')} | 参与者={mem.get('participants')}")

        print("="*60 + "\n")
        return relevant_memories

    async def _generate_direct_response(self, character_data: Dict[str, Any], user_input: str, conversation_history: List[Dict[str, str]] = None) -> str:
        simplified_system_prompt = f"""
你是{character_data.get('name')}，需基于以下人设快速回答（100-150字），贴合人设和语言风格。
人设：{character_data.get('values')} | {character_data.get('hobby')} | {character_data.get('living_habit')} | 语言风格：{character_data.get('language_style')}
"""
        history_str = "\n".join([f"{'用户' if t['role']=='user' else '你'}: {t['content']}" for t in (conversation_history or [])])
        user_prompt = f"{history_str}\n用户：{user_input}\n你的回答："
        
        return await self.character_llm.client.generate_response(simplified_system_prompt, user_prompt)
    
    async def _generate_immediate_response(self, character_data: Dict[str, Any], user_input: str, conversation_history: List[Dict[str, str]] = None) -> str:
        simplified_system_prompt = f"""
你是{character_data.get('name')}，请非常快速地回复（1-2句，50字以内），符合语言风格：{character_data.get('language_style')}，不涉及具体记忆细节。
"""
        history_str = "\n".join([f"{'用户' if t['role']=='user' else '你'}: {t['content']}" for t in (conversation_history[-2:] if conversation_history else [])])
        user_prompt = f"{history_str}\n用户：{user_input}\n你的简短回复："
        
        return await self.character_llm.client.generate_response(simplified_system_prompt, user_prompt)
    
    async def _generate_no_memory_response(self, character_data: Dict[str, Any], user_input: str, immediate_response: str) -> str:
        simplified_system_prompt = f"""
你是{character_data.get('name')}，想不起来用户问题的相关记忆片段。请自然地回应（50-100字），符合语言风格：{character_data.get('language_style')}，可用生活习惯等解释（如“可能忘记了”“不常回想”），不提“记忆”“系统”等词，呼应之前回复：{immediate_response}。
"""
        user_prompt = f"用户：{user_input}\n你之前说：{immediate_response}\n你的回复："
        
        return await self.character_llm.client.generate_response(simplified_system_prompt, user_prompt)