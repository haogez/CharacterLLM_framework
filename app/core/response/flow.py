# app/core/response/flow.py (修改版)
"""
三阶段响应流程模块 (已集成图谱记忆检索 - Neo4j版)

实现角色对话的三阶段响应流程：下意识响应、记忆检索、补充响应。
现在从 Neo4j 图谱检索记忆。
"""

import asyncio
import json
import time
from typing import Dict, List, Any, Optional, AsyncGenerator

from app.core.llm.openai_client import CharacterLLM
# --- 修改导入 ---
from app.core.graph.graph_store import GraphStore # 导入新版 GraphStore
# ---

class ResponseFlow:
    """
    三阶段响应流程类
    核心：通过结构化Prompt让LLM自主解析完整记忆格式，无硬编码提取逻辑
    """
    
    def __init__(self, 
                character_llm: Optional[CharacterLLM] = None,
                # --- 修改参数 ---
                graph_store: Optional[GraphStore] = None): # 确保类型注解是新版 GraphStore
        self.character_llm = character_llm or CharacterLLM()
        self.graph_store = graph_store or GraphStore() # 使用新版 GraphStore
        # ---
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
    
    # 1. 修改：process 方法改为 async
    async def process(self, 
                     character_id: str,
                     character_data: Dict[str, Any],
                     user_input: str,
                     conversation_history: List[Dict[str, str]] = None) -> AsyncGenerator[Dict[str, Any], None]:
        """主流程：仅保留核心逻辑，无硬编码提取步骤"""
        start_time = time.time()
        # 1. 判断是否需要记忆（基于LLM自主分析，不做硬编码规则）
        # 2. 修改：await 调用异步 _needs_memory
        needs_memory = await self._needs_memory(character_data, user_input)
        
        if not needs_memory:
            # 3. 修改：await 调用异步 _generate_direct_response
            direct_resp = await self._generate_direct_response(character_data, user_input, conversation_history)
            yield {
                "type": "direct", 
                "content": direct_resp, 
                "timestamp": round(time.time() - start_time, 2)
            }
            return
        
        # 2. 三阶段流程（记忆检索返回完整格式，不做提前提取）
        # 4. 修改：创建任务以并行执行 immediate response 和 memory retrieval
        immediate_task = asyncio.create_task(self._generate_immediate_response(character_data, user_input, conversation_history))
        # --- 修改：调用图谱检索 ---
        # memory_task = asyncio.create_task(self._retrieve_relevant_memories(character_id, user_input))
        memory_task = asyncio.create_task(self._retrieve_relevant_memories_from_graph(character_id, user_input))
        # ---
        
        # 5. 修改：await immediate response task
        immediate_resp = await immediate_task
        # 返回下意识响应
        yield {
            "type": "immediate", 
            "content": immediate_resp, 
            "timestamp": round(time.time() - start_time, 2)
        }
        
        # 处理记忆结果
        # 6. 修改：await memory retrieval task
        memories = await memory_task
        if memories:
            # 7. 修改：await 调用异步 _generate_supplementary_response
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
            # 8. 修改：await 调用异步 _generate_no_memory_response
            no_memory_resp = await self._generate_no_memory_response(character_data, user_input, immediate_resp)
            yield {
                "type": "no_memory", 
                "content": no_memory_resp, 
                "timestamp": round(time.time() - start_time, 2)
            }

    # ------------------------------
    # 核心优化：补充响应生成（无硬编码提取，全靠LLM自主解析）
    # ------------------------------
    # 9. 修改：_generate_supplementary_response 方法改为 async
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
        # --- 使用新的日志格式 ---
        print("\n" + "="*60)
        print(f"📝 生成补充响应...")
        print(f"   角色: {character_data.get('name')}")
        print(f"   用户输入: {user_input}")
        print(f"   记忆数量: {len(memories)} | 涉及类型: {[mem.get('type', '未定义') for mem in memories]}")
        print("="*60)
        # ---
        
        formatted_memories = []
        for idx, mem in enumerate(memories, 1):
            # --- 修改：移除来源关系信息以便格式化 ---
            mem_to_format = {k: v for k, v in mem.items() if not k.startswith('_')} # 过滤掉 '_source_relationship', '_related_character_id'
            # 仅打印标题和类型，避免打印完整 content
            mem_type = mem.get('type', '未定义')
            mem_title = mem.get('title', f'记忆 {idx}')
            formatted_memories.append(f"""
【第{idx}条记忆】
- 记忆类型：{mem_type}
- 记忆标题：{mem_title}
""")
        # ---
        
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
   - 提及其光感：参考「time.age」（当时年龄）和「time.period」（人生阶段），如“我25岁刚工作时”。
   - 体现情绪：从「emotion.immediate」（即时情绪）过渡到「emotion.reflected」（事后反思），如“当时很紧张，后来才明白问题所在”。
   - 关联现在：结合「behavior_impact」（行为影响）说明对现在的影响，如“从那以后我就养成了检查的习惯”。
   - 感官细节：从「content」中提取视觉/听觉/嗅觉/触觉描述，让场景更真实（如“雨水打湿衣服的冰凉感”“咖啡的焦味”）。
4. 禁止元信息：不提及“记忆”“字段”“类型要求”等词汇，像自然回忆一样讲述。
5. 长度要求：≥250字，逻辑连贯（场景铺垫→事件经过→对现在的影响）。
6. 呼应前文：与之前的简短响应（{immediate_response}）呼应，但完全重写，不简单补充。
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
可供参考的记忆详情：
{''.join(formatted_memories)}

请以{character_data.get('name')}的身份，按上述规则生成补充响应：
"""
        
        # 10. 修改：await 调用 LLM 异步方法
        response = await self.character_llm.client.generate_response(system_prompt=system_prompt, user_prompt=user_prompt)
        
        if len(response.strip()) < 180:
            print(f"响应过短（{len(response.strip())}字），重新生成...")
            # 11. 修改：await 调用 LLM 异步方法
            response = await self.character_llm.client.generate_response(
                system_prompt=system_prompt + "\n⚠️  警告：响应过短！请务必融入记忆中的时间、情绪、行为影响等细节，长度≥250字！",
                user_prompt=user_prompt
            )
        
        print(f"✅ 补充响应生成完成 (长度: {len(response.strip())}字)")
        print("="*60 + "\n")
        return response.strip()
    
    # ------------------------------
    # 其他方法：全量简化，移除所有硬编码提取逻辑
    # ------------------------------
    # 12. 修改：_needs_memory 方法改为 async
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
        
        # 13. 修改：await 调用 LLM 异步方法
        result = await self.character_llm.client.generate_response(system_prompt, user_prompt)
        return result.strip().upper() == "YES"
    
    # --- 修改：_retrieve_relevant_memories_from_graph 方法 ---
    async def _retrieve_relevant_memories_from_graph(self, character_id: str, query_text: str, n_results: int = 3) -> List[Dict[str, Any]]:
        print("\n" + "="*60)
        print("🔍  开始从 Neo4j 图谱检索记忆...")
        print(f"   角色ID: {character_id}")
        print(f"   查询文本: {query_text}")
        print("="*60)

        start_time = time.time()
        # 1. 从图谱获取所有记忆
        all_raw_memories = self.graph_store.get_all_memories_for_character(character_id)
        print(f"⏱️  从 Neo4j 获取所有记忆耗时: {time.time()-start_time:.2f}秒")
        print(f"📊 获取到 {len(all_raw_memories)} 条原始记忆")

        # 2. 使用 LLM 生成查询嵌入向量 (需要 LLM 客户端)
        # 假设 self.character_llm.client 有 create_embeddings 方法
        try:
            # 将查询文本和所有记忆内容合并，用于嵌入
            query_embedding = await self.character_llm.client.create_embeddings([query_text])
            memory_contents = [mem.get('content', '') for mem in all_raw_memories]
            memory_embeddings = await self.character_llm.client.create_embeddings(memory_contents)
        except Exception as e:
            print(f"⚠️  使用 LLM 生成嵌入向量失败: {e}，将使用关键词匹配排序作为备选方案。")
            # 备选方案：关键词匹配 (非常粗糙)
            for mem in all_raw_memories:
                content = mem.get('content', '').lower()
                query_lower = query_text.lower()
                relevance_score = content.count(query_lower) / (len(content.split()) + 1)
                mem['relevance'] = relevance_score
        else:
            # 计算余弦相似度 (需要 numpy 或类似库，这里简化)
            # 伪代码: 计算 query_embedding 与 memory_embeddings 中每个向量的相似度
            # 为了演示，我们假设有一个计算函数
            import numpy as np # 需要安装 numpy
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

            # 将相似度分数添加到记忆中
            for i, mem in enumerate(all_raw_memories):
                mem['relevance'] = similarities[i]

        # 3. 按相关性分数排序
        all_raw_memories.sort(key=lambda x: x.get('relevance', 0), reverse=True)
        # 4. 选择前 n_results 个
        relevant_memories = all_raw_memories[:n_results]
        # 5. 过滤掉模拟添加的 _source_relationship 和 _related_character_id (如果需要)
        for mem in relevant_memories:
             mem.pop('_source_relationship', None)
             mem.pop('_related_character_id', None)

        print(f"📊 排序后高相关性记忆数: {len(relevant_memories)}")
        for idx, mem in enumerate(relevant_memories, 1):
            print(f"   📌 记忆{idx}: 类型={mem.get('type')} | 标题={mem.get('title')} | 相关性={mem.get('relevance', 0):.2f}")

        print("="*60 + "\n")
        return relevant_memories
    # ---

    # --- 注释掉旧的 _retrieve_relevant_memories 方法 ---
    # async def _retrieve_relevant_memories(self, character_id: str, query_text: str, n_results: int = 3) -> List[Dict[str, Any]]:
    #     print("\n" + "="*60)
    #     print("🔍  开始检索记忆...")
    #     print(f"   角色ID: {character_id}")
    #     print(f"   查询文本: {query_text}")
    #     print("="*60)
    #     
    #     start_time = time.time()
    #     # 15. 修改：await 调用异步 memory store 方法 (假设已添加)
    #     raw_memories = await self.memory_store.query_memories_async(
    #         character_id=character_id,
    #         query_text=query_text,
    #         n_results=n_results,
    #         return_full_fields=True
    #     )
    #     
    #     relevant_memories = [mem for mem in raw_memories if mem.get('relevance', 0) > 0.3]
    #     
    #     print(f"⏱️  检索耗时: {time.time()-start_time:.2f}秒")
    #     print(f"📊 高相关性记忆数: {len(relevant_memories)}")
    #     for idx, mem in enumerate(relevant_memories, 1):
    #         print(f"   📌 记忆{idx}: 类型={mem.get('type')} | 标题={mem.get('title')} | 相关性={mem.get('relevance', 0):.2f}")
    #     
    #     print("="*60 + "\n")
    #     return relevant_memories
    # ---
    
    # 16. 修改：_generate_direct_response 方法改为 async
    async def _generate_direct_response(self, character_data: Dict[str, Any], user_input: str, conversation_history: List[Dict[str, str]] = None) -> str:
        # 17. 修改：简化 Prompt 以提升速度
        simplified_system_prompt = f"""
你是{character_data.get('name')}，需基于以下人设快速回答（100-150字），贴合人设和语言风格。
人设：{character_data.get('values')} | {character_data.get('hobby')} | {character_data.get('living_habit')} | 语言风格：{character_data.get('language_style')}
"""
        history_str = "\n".join([f"{'用户' if t['role']=='user' else '你'}: {t['content']}" for t in (conversation_history or [])])
        user_prompt = f"{history_str}\n用户：{user_input}\n你的回答："
        
        # 18. 修改：await 调用 LLM 异步方法
        return await self.character_llm.client.generate_response(simplified_system_prompt, user_prompt)
    
    # 19. 修改：_generate_immediate_response 方法改为 async
    async def _generate_immediate_response(self, character_data: Dict[str, Any], user_input: str, conversation_history: List[Dict[str, str]] = None) -> str:
        # 20. 修改：使用更简化的 Prompt
        simplified_system_prompt = f"""
你是{character_data.get('name')}，请非常快速地回复（1-2句，50字以内），符合语言风格：{character_data.get('language_style')}，不涉及具体记忆细节。
"""
        history_str = "\n".join([f"{'用户' if t['role']=='user' else '你'}: {t['content']}" for t in (conversation_history[-2:] if conversation_history else [])])
        user_prompt = f"{history_str}\n用户：{user_input}\n你的简短回复："
        
        # 21. 修改：await 调用 LLM 异步方法
        return await self.character_llm.client.generate_response(simplified_system_prompt, user_prompt)
    
    # 22. 修改：_generate_no_memory_response 方法改为 async
    async def _generate_no_memory_response(self, character_data: Dict[str, Any], user_input: str, immediate_response: str) -> str:
        simplified_system_prompt = f"""
你是{character_data.get('name')}，想不起来用户问题的相关记忆。请自然地回应（50-100字），符合语言风格：{character_data.get('language_style')}，可用生活习惯等解释（如“可能忘记了”“不常回想”），不提“记忆”“系统”等词，呼应之前回复：{immediate_response}。
"""
        user_prompt = f"用户：{user_input}\n你之前说：{immediate_response}\n你的回复："
        
        # 23. 修改：await 调用 LLM 异步方法
        return await self.character_llm.client.generate_response(simplified_system_prompt, user_prompt)


if __name__ == "__main__":
    # Note: Test code needs to be adapted to use async/await
    print("ResponseFlow 模块已加载，方法已异步化，并集成了 Neo4j 图谱记忆检索。")