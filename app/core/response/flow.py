"""
三阶段响应流程模块 (Neo4j版)
"""

import asyncio
import base64
import json
import re
import time
import uuid
from typing import Dict, List, Any, Optional, AsyncGenerator, Tuple

from app.core.llm.openai_client import CharacterLLM
from app.core.graph.graph_store import GraphStore
from app.core.utils.log_utils import (
    log_section_start,
    log_section_end,
    log_info,
    log_warning,
    log_success,
    log_error,
    log_debug,
    log_chat_start,
    log_chat_response,
    log_chat_complete,
)

class ResponseFlow:
    def __init__(self,
                character_llm: Optional[CharacterLLM] = None,
                graph_store: Optional[GraphStore] = None):
        self.character_llm = character_llm or CharacterLLM()
        self.graph_store = graph_store or GraphStore()
        self.prefetched_memories: Dict[str, List[Dict[str, Any]]] = {}
        self.prefetch_tasks: Dict[str, asyncio.Task] = {}
        # 第二条“记忆检索与补充响应线程”的收件箱，用于跨轮延迟补充
        self.pending_supplements: Dict[str, List[Dict[str, Any]]] = {}
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

    # --- 线程化设计的基础工具 ---
    def _segment_user_input(self, user_input: str) -> List[str]:
        """按照语义片段拆分用户输入，便于记忆检索线程使用。"""
        segments = []
        if not user_input:
            return segments

        rough_parts = re.split(r"[。！？!?]\s*|，\s*|,\s*|;\s*|；\s*", user_input)
        for part in rough_parts:
            clean = part.strip()
            if clean:
                segments.append(clean)
        log_debug(f"语义分片结果: {segments}")
        return segments

    def _plan_memory_strategy(
        self,
        segments: List[str],
        dialogue_type: Optional[str],
        conversation_history: Optional[List[Dict[str, str]]],
    ) -> str:
        """根据语义片段和对话类型，决定补充响应策略。"""
        last_turn = conversation_history[-1]["content"] if conversation_history else ""
        contains_question = any(re.search(r"[?？]$", seg) for seg in segments)
        long_history = conversation_history is not None and len(conversation_history) >= 4

        if contains_question:
            decision = "now"
        elif dialogue_type and dialogue_type.lower() in {"安抚", "咨询", "求助"}:
            decision = "now"
        elif long_history:
            decision = "now"
        elif any(keyword in last_turn for keyword in ["刚刚", "之前", "还记得"]):
            decision = "next"
        else:
            decision = "hold"

        log_info(f"补充响应策略: {decision}（contains_question={contains_question}, long_history={long_history}）", indent=1)
        return decision

    def _store_pending_supplement(self, character_id: str, payload: Dict[str, Any]) -> None:
        """将补充响应缓存到收件箱，供下一轮发送。"""
        self.pending_supplements.setdefault(character_id, []).append(payload)
        log_warning("补充响应已存入待发送队列，等待下一次对话触发。", indent=1)

    def _emit_pending_supplement(self, character_id: str) -> Optional[Dict[str, Any]]:
        """尝试弹出一条挂起的补充响应。"""
        queue = self.pending_supplements.get(character_id, [])
        if not queue:
            return None
        payload = queue.pop(0)
        if not queue:
            self.pending_supplements.pop(character_id, None)
        log_success("检测到上轮遗留的补充响应，准备本轮一并发送。", indent=1)
        return payload
    
    # --- 新增：通用的角色上下文构建函数 ---
    def _build_user_context(self, character_data: Dict[str, Any], user_character_data: Optional[Dict[str, Any]], scene: Optional[str] = None, dialogue_type: Optional[str] = None) -> str:
        """
        为所有响应阶段构建通用的用户角色上下文。
        """
        if user_character_data:
            user_name = user_character_data.get('name')
            user_occ = user_character_data.get('occupation')
            user_age = user_character_data.get('age')
            user_gender = user_character_data.get('gender')
            user_background = user_character_data.get('background', '未知') # 用户角色的背景故事
            # 主角色的背景故事
            main_background = character_data.get('background', '未知')
            # 从图谱获取关系信息
            user_relationship_info = self.graph_store.get_relationship_between_characters(character_data.get('id'), user_character_data.get('id')) if self.graph_store else None
            relationship_type = user_relationship_info.get('type', 'UNKNOWN') if user_relationship_info else 'UNKNOWN'
            relationship_description = user_relationship_info.get('description', '未知') if user_relationship_info else '未知'
            # 主角色性格
            main_personality = character_data.get('personality', {})
            main_neuroticism = main_personality.get('neuroticism', 50)
            main_agreeableness = main_personality.get('agreeableness', 50)
            main_openness = main_personality.get('openness', 50)
            main_extraversion = main_personality.get('extraversion', 50)
            main_conscientiousness = main_personality.get('conscientiousness', 50)
            # 用户角色性格
            user_personality = user_character_data.get('personality', {})
            user_neuroticism = user_personality.get('neuroticism', 50)
            user_agreeableness = user_personality.get('agreeableness', 50)
            user_openness = user_personality.get('openness', 50)
            user_extraversion = user_personality.get('extraversion', 50)
            user_conscientiousness = user_personality.get('conscientiousness', 50)

            scene_hint = f"当前对话场景：{scene}。" if scene else "当前对话场景未知。"
            dialogue_hint = f"对话类型：{dialogue_type or '闲聊'}。"

            return f"""
            **你（{character_data.get('name')}）的信息：**
            - 年龄：{character_data.get('age')}岁
            - 职业：{character_data.get('occupation')}
            - 性格特质 (OCEAN)：开放性 {main_openness}/100, 尽责性 {main_conscientiousness}/100, 外向性 {main_extraversion}/100, 宜人性 {main_agreeableness}/100, 神经质 {main_neuroticism}/100
            - 背景故事：{main_background}

            **你正在与 {user_name} 对话，其信息如下：**
            - 年龄：{user_age}岁
            - 性别：{user_gender}
            - 职业：{user_occ}
            - 性格特质 (OCEAN)：开放性 {user_openness}/100, 尽责性 {user_conscientiousness}/100, 外向性 {user_extraversion}/100, 宜人性 {user_agreeableness}/100, 神经质 {user_neuroticism}/100
            - 背景故事：{user_background}

            **你们之间的关系：**
            - 关系类型：{relationship_type}
            - 关系描述：{relationship_description}

            {scene_hint}
            {dialogue_hint}

            **重要提示：**
            - **称呼分析**：请根据以上所有信息（你的性格、对方的性格、对方的背景、你们的关系描述）来判断你应该如何称呼对方。例如，对方如果是长辈（如父母、叔叔阿姨），你可能需要称呼“妈妈”、“爸爸”、“叔叔”、“阿姨”等；如果是同辈朋友，可能是名字或昵称；如果关系疏远或正式，可能是姓氏+职务。不要直接使用对方的名字（除非关系非常亲密或对方要求），也不要生硬地使用关系词（如“母亲大人”），要自然。
            - **语气与措辞**：你的回应语气、用词、态度应与你的性格特质（特别是神经质、宜人性、开放性、外向性）和价值观一致。例如，高神经质可能更敏感、谨慎；低宜人性可能更直接、坚持自我边界；高开放性可能更愿意尝试新表达；高外向性可能更主动、热情。
            - **互动模式**：参考你的社交模式（{character_data.get('social_pattern')}）和对方的社交模式（{user_character_data.get('social_pattern', '未知')}）来调整互动方式。
            """
        else:
            scene_hint = f"当前对话场景：{scene}。" if scene else "当前对话场景未知。"
            dialogue_hint = f"对话类型：{dialogue_type or '闲聊'}。"

            return f"""
            **你（{character_data.get('name')}）的信息：**
            - 年龄：{character_data.get('age')}岁
            - 职业：{character_data.get('occupation')}
            - 性格特质 (OCEAN)：开放性 {character_data.get('personality', {}).get('openness', 50)}/100, 尽责性 {character_data.get('personality', {}).get('conscientiousness', 50)}/100, 外向性 {character_data.get('personality', {}).get('extraversion', 50)}/100, 宜人性 {character_data.get('personality', {}).get('agreeableness', 50)}/100, 神经质 {character_data.get('personality', {}).get('neuroticism', 50)}/100
            - 背景故事：{character_data.get('background', '未知')}

            你正在与一位普通用户对话，对方没有提供具体身份信息。
            {scene_hint}
            {dialogue_hint}
            """
    # ---
    async def _needs_memory(self,
                          character_data: Dict[str, Any],
                          user_input: str,
                          user_character_data: Optional[Dict[str, Any]] = None, # 确保接收此参数
                          scene: Optional[str] = None,
                          dialogue_type: Optional[str] = None
                          ) -> bool:
        # 构建与用户扮演角色相关的上下文
        context_info = ""
        if user_character_data:
            user_name = user_character_data.get('name')
            user_occ = user_character_data.get('occupation')
            # 这里可以考虑从图谱获取关系，或者直接使用角色数据中的信息（如果有的话）
            # 假设角色数据中有一个字段 'relationship_to_main' 或者可以从其他地方获取
            user_rel = user_character_data.get('relationship_to_main', '未知') # 需要根据实际情况获取
            context_info = f"对话对象是 {user_name} ({user_occ})，与 {character_data.get('name')} 的关系可能是 {user_rel}。"
        # ... 其余逻辑类似，但Prompt中可以包含 context_info
        scene_hint = f"当前场景：{scene}。" if scene else "当前场景未知。"
        type_hint = f"对话类型：{dialogue_type or '闲聊'}。"

        system_prompt = f"""
        你是对话意图分析师，需判断用户问题是否需要{character_data.get('name', '角色')}调用「个人记忆片段」回答。

        角色基础：{character_data.get('name')}，{character_data.get('age')}岁，{character_data.get('occupation')}。
        {context_info} # 添加上下文信息
        {scene_hint}
        {type_hint}

        需要调用记忆片段的情况：问题涉及角色的「过往经历、具体事件、形成的习惯、特定场景的感受、与他人的互动」（如"你之前遇到过XX情况吗？""你为什么有XX习惯？""你和XX之间发生过什么？"）。
        不需要调用记忆片段的情况：问题是寒暄问候、询问当前人设（如"你喜欢什么爱好？"）、通用知识（如"今天天气如何？"）。

        仅返回"YES"或"NO"，不添加任何解释。
        """
        user_prompt = f"用户问题：{user_input}\n判断结果（仅YES/NO）："
        
        result = await self.character_llm.client.generate_response(system_prompt, user_prompt)
        return result.strip().upper() == "YES"

    async def _background_memory_prefetch(self, character_id: str, query: str, scene: Optional[str] = None) -> List[Dict[str, Any]]:
        """使用 Neo4jVector 在后台预取记忆，供下一轮对话使用。"""
        if not self.graph_store:
            return []

        text = f"{query} {scene or ''}".strip()
        loop = asyncio.get_running_loop()
        try:
            results = await loop.run_in_executor(None, self.graph_store.vector_search_impressions, text, character_id, 6)
            self.prefetched_memories[character_id] = results
            return results
        except Exception as e:
            print(f"后台预取失败: {e}")
            return []
    
    async def process(self,
                     character_id: str,
                     character_data: Dict[str, Any],
                     user_input: str,
                     conversation_history: List[Dict[str, str]] = None,
                     user_character_data: Optional[Dict[str, Any]] = None, # 确保接收此参数
                     scene: Optional[str] = None,
                     dialogue_type: Optional[str] = None
                     ) -> AsyncGenerator[Dict[str, Any], None]:
        start_time = time.time()
        log_chat_start(character_id, user_input)

        # 线程1：对话主线；线程2：记忆检索补充
        response_count = 0

        # 先检查是否有挂起的补充响应需要在本轮发送
        pending_supplement = self._emit_pending_supplement(character_id)

        # 启动后台记忆预取
        prefetch_task = None
        if self.graph_store:
            prefetch_task = asyncio.create_task(self._background_memory_prefetch(character_id, user_input, scene))

        segments = self._segment_user_input(user_input)
        strategy = self._plan_memory_strategy(segments, dialogue_type, conversation_history)
        needs_memory = await self._needs_memory(character_data, user_input, user_character_data, scene, dialogue_type)

        if not needs_memory:
            direct_resp = await self._generate_direct_response(
                character_data, user_input, conversation_history, user_character_data, scene, dialogue_type
            )
            response_payload = {
                "type": "direct",
                "content": direct_resp,
                "timestamp": round(time.time() - start_time, 2)
            }
            log_chat_response("DIRECT", character_id, user_input, direct_resp, response_payload["timestamp"])
            response_count += 1
            yield response_payload

            if pending_supplement:
                pending_supplement["timestamp"] = round(time.time() - start_time, 2)
                log_chat_response(
                    "SUPPLEMENTARY (PENDING)",
                    character_id,
                    user_input,
                    pending_supplement.get("content", ""),
                    pending_supplement["timestamp"],
                    len(pending_supplement.get("memories", [])),
                )
                response_count += 1
                yield pending_supplement

            log_chat_complete(character_id, user_input, time.time() - start_time, response_count)
            return

        immediate_resp = await self._generate_immediate_response(
            character_data, user_input, conversation_history, user_character_data, scene, dialogue_type
        )
        immediate_payload = {
            "type": "immediate",
            "content": immediate_resp,
            "timestamp": round(time.time() - start_time, 2)
        }
        log_chat_response("IMMEDIATE", character_id, user_input, immediate_resp, immediate_payload["timestamp"])
        response_count += 1
        yield immediate_payload

        memory_result = await self._memory_thread(
            character_data,
            user_input,
            immediate_resp,
            character_id,
            conversation_history,
            user_character_data,
            scene,
            dialogue_type,
            prefetch_task,
            strategy,
        )

        if memory_result and memory_result.get("action") == "send":
            payload = memory_result["payload"]
            payload["timestamp"] = round(time.time() - start_time, 2)
            log_chat_response(
                "SUPPLEMENTARY",
                character_id,
                user_input,
                payload.get("content", ""),
                payload["timestamp"],
                len(payload.get("memories", [])),
            )
            response_count += 1
            yield payload
        elif memory_result and memory_result.get("action") == "defer":
            self._store_pending_supplement(character_id, memory_result["payload"])

        if pending_supplement:
            pending_supplement["timestamp"] = round(time.time() - start_time, 2)
            log_chat_response(
                "SUPPLEMENTARY (PENDING)",
                character_id,
                user_input,
                pending_supplement.get("content", ""),
                pending_supplement["timestamp"],
                len(pending_supplement.get("memories", [])),
            )
            response_count += 1
            yield pending_supplement

        log_chat_complete(character_id, user_input, time.time() - start_time, response_count)

    async def _memory_thread(
        self,
        character_data: Dict[str, Any],
        user_input: str,
        immediate_response: str,
        character_id: str,
        conversation_history: Optional[List[Dict[str, str]]],
        user_character_data: Optional[Dict[str, Any]],
        scene: Optional[str],
        dialogue_type: Optional[str],
        prefetch_task: Optional[asyncio.Task],
        strategy: str,
    ) -> Optional[Dict[str, Any]]:
        """记忆检索与补充响应线程，负责检索、生成并决定是否立刻发送。"""
        log_section_start("记忆线程：检索与生成", "-")
        log_info("线程启动，准备检索记忆。", indent=1)
        try:
            supplementary = await self._generate_supplementary_response(
                character_data,
                user_input,
                immediate_response,
                character_id,
                conversation_history,
                user_character_data,
                scene,
                dialogue_type,
                prefetch_task,
            )
        except Exception as exc:
            log_error(f"记忆线程异常: {exc}", indent=1)
            log_section_end("-")
            return None

        content = supplementary.get("content", "").strip()
        memories = supplementary.get("memories", [])

        if not content and not memories:
            log_warning("未生成补充响应或相关记忆，线程结束。", indent=1)
            log_section_end("-")
            return None

        if strategy == "now":
            action = "send"
        elif strategy == "next":
            action = "defer"
        else:
            action = "send" if memories else "defer"

        log_info(f"记忆线程决策: {action} (策略={strategy}, 记忆数={len(memories)})", indent=1)
        log_section_end("-")

        return {
            "action": action,
            "payload": {
                "type": "supplementary",
                "content": content,
                "memories": memories,
            },
        }

    async def _generate_supplementary_response(self,
                                             character_data: Dict[str, Any],
                                             user_input: str,
                                             immediate_response: str,
                                             character_id: str,
                                             conversation_history: List[Dict[str, str]] = None,
                                             user_character_data: Optional[Dict[str, Any]] = None,
                                             scene: Optional[str] = None,
                                             dialogue_type: Optional[str] = None,
                                             prefetch_task: Optional[asyncio.Task] = None
                                             ) -> Dict[str, Any]:
        log_section_start("记忆线程：生成补充响应", "=")
        log_info(f"主角: {character_data.get('name')}")
        log_info(f"用户扮演角色: {user_character_data.get('name') if user_character_data else '默认用户'}")
        log_info(f"用户输入: {user_input}")
        if scene:
            log_info(f"对话场景: {scene}")
        if dialogue_type:
            log_info(f"对话类型: {dialogue_type}")

        prefetched = []
        if prefetch_task:
            try:
                prefetched = await prefetch_task
            except Exception as e:
                print(f"预取任务出错: {e}")
        elif character_id in self.prefetched_memories:
            prefetched = self.prefetched_memories.get(character_id, [])

        # --- GraphRAG 检索开始 (只检索印象节点) ---
        log_section_start("记忆线程：GraphRAG 检索", "-")
        log_info("开始从 Neo4j 图谱进行 GraphRAG 检索 (仅印象节点)...", indent=1)
        log_info(f"查询文本: {user_input}", indent=1)
        log_info(f"目标角色ID: {character_id}", indent=1)

        start_time = time.time()
        all_raw_impressions = []
        if self.graph_store: # 确保 graph_store 实例存在
            try:
                with self.graph_store.driver.session(database=self.graph_store.database) as session:
                    # --- 步骤 1: 关键词匹配 ---
                    log_debug("尝试关键词匹配...", indent=1)
                    # ... (之前的关键词匹配逻辑保持不变) ...
                    # 1.1 提取用户输入中的关键词
                    keywords = re.findall(r'[\u4e00-\u9fff\w]+', user_input)
                    common_words = {"你", "我", "他", "她", "它", "是", "的", "了", "在", "有", "和", "跟", "与", "吗", "呢", "吧", "啊", "呀", "还", "就", "才", "又", "再", "更", "最", "很", "挺", "太", "非常", "特别", "十分", "有点", "稍微", "几乎", "几乎不", "完全", "全部", "都", "全部", "所有", "每个", "一些", "几个", "某些", "别的", "其他", "另外", "这", "那", "这些", "那些", "这个", "那个", "这里", "那里", "这儿", "那儿", "现在", "然后", "如果", "因为", "所以", "但是", "然而", "虽然", "尽管", "为了", "关于", "对于", "关于", "把", "被", "让", "叫", "请", "让", "使", "帮", "给", "为", "对", "向", "往", "朝", "用", "以", "比", "跟", "和", "同", "与", "及", "以及", "或", "或者", "还是"}
                    keywords = [kw.lower() for kw in keywords if len(kw) > 1 and kw not in common_words]
                    log_debug(f"提取关键词: {keywords}", indent=2)

                    if keywords:
                        # 1.2 构建 Cypher 查询，使用 OR 连接的 CONTAINS
                        or_conditions_impression = []
                        params = {"character_id": character_id}
                        for i, kw in enumerate(keywords):
                            or_conditions_impression.append(f"toLower(i.impression_content) CONTAINS toLower($kw{i})")
                            params[f"kw{i}"] = kw
                        where_clause_keyword = " OR ".join(or_conditions_impression)
                        query_keyword = f"""
                        MATCH (c:Character {{app_id: $character_id}})-[:HAS_IMPRESSION]->(i:Impression)-[:OF_EVENT]->(e:Event)
                        WHERE {where_clause_keyword}
                        RETURN i, e, i.strength AS strength, 'keyword' AS source
                        ORDER BY strength DESC
                        LIMIT 10 // 可以适当增加，因为后续会合并去重
                        """
                        log_debug(f"执行关键词查询: {query_keyword}", indent=2)
                        log_debug(f"参数: {params}", indent=2)
                        result_keyword = session.run(query_keyword, **params)
                        raw_impressions_keyword = []
                        for record in result_keyword:
                            raw_impressions_keyword.append({
                                "impression": dict(record["i"]),
                                "event": dict(record["e"]),
                                "strength": record["strength"],
                                "source": record["source"]
                            })
                        log_info(f"关键词查询返回 {len(raw_impressions_keyword)} 条记录", indent=2)
                    else:
                        raw_impressions_keyword = []
                        log_debug("关键词提取为空，跳过关键词查询", indent=2)

                    # --- 步骤 2: 结构化查询 ---
                    log_debug("尝试结构化查询...", indent=1)
                    # ... (之前的结构化查询逻辑保持不变) ...
                    # 2.1 尝试从用户输入中提取结构化信息 (这里简化处理，实际可能需要 NLP)
                    location_names = [kw for kw in keywords if len(kw) > 2] # 简单过滤，认为较长的词可能是地点

                    raw_impressions_structured = []
                    if location_names:
                         # 尝试匹配 Event 节点的 event_content
                         or_conditions_location = []
                         params_loc = {"character_id": character_id}
                         for i, loc_kw in enumerate(location_names):
                             or_conditions_location.append(f"toLower(e.event_content) CONTAINS toLower($loc_kw{i})")
                             params_loc[f"loc_kw{i}"] = loc_kw
                         where_clause_location = " OR ".join(or_conditions_location)
                         query_structured = f"""
                         MATCH (c:Character {{app_id: $character_id}})-[:HAS_IMPRESSION]->(i:Impression)-[:OF_EVENT]->(e:Event)
                         WHERE {where_clause_location}
                         RETURN i, e, i.strength AS strength, 'structured_location' AS source
                         ORDER BY strength DESC
                         LIMIT 5
                         """
                         log_debug(f"执行结构化地点查询: {query_structured}", indent=2)
                         log_debug(f"参数: {params_loc}", indent=2)
                         result_structured = session.run(query_structured, **params_loc)
                         for record in result_structured:
                            raw_impressions_structured.append({
                                "impression": dict(record["i"]),
                                "event": dict(record["e"]),
                                "strength": record["strength"],
                                "source": record["source"]
                            })
                         log_info(f"结构化地点查询返回 {len(raw_impressions_structured)} 条记录", indent=2)

                    # --- 步骤 3: 向量搜索 (语义搜索) ---
                    log_debug("尝试向量搜索 (语义搜索)...", indent=1)
                    # 3.1 搜索与查询语义相关的 Event
                    # semantic_results_events = self.graph_store.semantic_search_events(user_input, k=5)
                    # 3.2 搜索与查询语义相关的 Impression
                    semantic_results_impressions = self.graph_store.semantic_search_impressions(user_input, k=5)

                    #3.3 将 LangChain 返回的格式转换为与之前一致的 raw_impressions 格式
                    # raw_impressions_semantic_events = []  # 不再需要
                    raw_impressions_semantic_impressions = []
                    for item in semantic_results_impressions:
                        # item 结构: {"impression": {...}, "event": {...}, "character": {...}, "relevance_score": score, "source": "vector_impression"}
                        impression_data = item["impression"]
                        event_data = item["event"]
                        if impression_data: # 确保 impression_data 存在
                            raw_impressions_semantic_impressions.append({
                                "impression": impression_data,
                                "event": event_data,
                                "strength": item.get("relevance_score", 0.5) * 100,
                                "source": item["source"]
                            })

                    raw_impressions_semantic = raw_impressions_semantic_impressions  # 只保留印象搜索结果
                    log_info(f"向量搜索返回 {len(raw_impressions_semantic)} 条记录 (仅来自印象)", indent=2)


                    # --- 步骤 4: 传统语义搜索 (使用 textdistance) ---
                    log_debug("尝试传统语义搜索 (基于textdistance)...", indent=1)
                    query_for_semantic = """
                    MATCH (c:Character {app_id: $character_id})-[:HAS_IMPRESSION]->(i:Impression)-[:OF_EVENT]->(e:Event)
                    WHERE i.strength > 30 // 选择强度较高的印象进行语义比较
                    RETURN i, e, i.strength AS strength
                    ORDER BY strength DESC
                    LIMIT 10 // 减少数量，因为向量搜索更准确
                    """
                    result_for_semantic = session.run(query_for_semantic, character_id=character_id)
                    candidates_for_semantic = []
                    for record in result_for_semantic:
                        candidates_for_semantic.append({
                            "impression": dict(record["i"]),
                            "event": dict(record["e"]),
                            "strength": record["strength"]
                        })

                    semantic_results_legacy = []
                    for candidate in candidates_for_semantic:
                        impression_content = candidate["impression"].get("impression_content", "")
                        try:
                            import textdistance
                            similarity = textdistance.jaro_winkler(user_input, impression_content)
                            if similarity > 0.3:
                                semantic_results_legacy.append({
                                    "candidate": candidate,
                                    "similarity": similarity
                                })
                        except ImportError:
                            log_warning("未安装 textdistance，跳过传统语义搜索", indent=2)
                            break

                    semantic_results_legacy.sort(key=lambda x: x["similarity"], reverse=True)
                    top_k_semantic_legacy = 2 # 选择前 K 个
                    raw_impressions_semantic_legacy = [r["candidate"] for r in semantic_results_legacy[:top_k_semantic_legacy]]
                    for r in raw_impressions_semantic_legacy:
                        r["source"] = "semantic_legacy"
                    log_info(
                        f"传统语义搜索返回 {len(raw_impressions_semantic_legacy)} 条记录 (基于阈值和 Top-{top_k_semantic_legacy})",
                        indent=2,
                    )


                    # --- 合并和去重 ---
                    log_debug("合并关键词、结构化、向量语义、传统语义搜索结果...", indent=1)
                    all_raw_impressions_unfiltered = (
                        raw_impressions_keyword +
                        raw_impressions_structured +
                        raw_impressions_semantic +
                        raw_impressions_semantic_legacy
                    )
                    # 去重：基于 impression_app_id
                    seen_ids = set()
                    all_raw_impressions = []
                    for imp in all_raw_impressions_unfiltered:
                        imp_id = imp["impression"].get("app_id")
                        if imp_id and imp_id not in seen_ids:
                            all_raw_impressions.append(imp)
                            seen_ids.add(imp_id)
                    log_info(f"合并后去重得到 {len(all_raw_impressions)} 条唯一记录", indent=2)

                    # --- 解码 properties ---
                    for imp_dict in all_raw_impressions:
                        for props_dict, node_name in [(imp_dict["impression"], "impression"), (imp_dict["event"], "event")]:
                            if "properties" in props_dict and props_dict["properties"]:
                                try:
                                    decoded_props = base64.b64decode(props_dict["properties"]).decode('utf-8')
                                    additional_props = json.loads(decoded_props)
                                    props_dict.update(additional_props)
                                except (base64.binascii.Error, json.JSONDecodeError, TypeError) as e:
                                    log_warning(f"解码{node_name} {props_dict.get('app_id', 'unknown')} 的 properties 时出错: {e}")
                                    pass # 如果解码失败，保留原始 properties 字段
                            # 移除 Base64 编码的 properties 字段
                            props_dict.pop("properties", None)


            except Exception as e:
                log_error(f"GraphRAG 检索失败: {e}")
        else:
            log_error("GraphStore 实例不存在，无法进行检索。")

        log_info(f"GraphRAG 检索耗时: {time.time()-start_time:.2f}秒")
        log_info(f"检索到 {len(all_raw_impressions)} 条相关印象")
        for idx, imp in enumerate(all_raw_impressions, 1):
            impression_content = imp.get("impression", {}).get("impression_content", imp.get("impression", {}).get("content", "未知内容"))
            event_title = imp.get("event", {}).get("event_title", imp.get("event", {}).get("title", "未知事件"))
            strength = imp.get("strength", "未知强度")
            source = imp.get("source", "unknown")
            log_debug(f"印象{idx}: 事件={event_title} | 印象内容={impression_content[:50]}... | 强度={strength} | 来源={source}", indent=1)
        log_section_end("-")
        # --- GraphRAG 检索结束 ---

        if prefetched:
            vector_impressions = []
            for item in prefetched:
                vector_impressions.append({
                    "impression": {
                        "impression_content": item.get("content", ""),
                        "app_id": item.get("app_id", str(uuid.uuid4()))
                    },
                    "event": {},
                    "strength": item.get("score", 70),
                    "source": "vector_prefetch"
                })
            all_raw_impressions = vector_impressions or all_raw_impressions

        # --- 构建与用户角色相关的上下文 (增强版) ---
        # ... (保持 user_context 逻辑不变) ...
        user_context = self._build_user_context(character_data, user_character_data, scene, dialogue_type)
        # ---

        # --- 格式化检索到的印象 (作为回忆) ---
        formatted_impressions = []
        for idx, imp in enumerate(all_raw_impressions, 1):
            # **修正：从 impression_content 获取内容**
            impression_content = imp.get("impression", {}).get("impression_content", imp.get("impression", {}).get("content", "我似乎记得..."))
            event_title = imp.get("event", {}).get("event_title", imp.get("event", {}).get("title", "某个事件"))
            strength = imp.get("strength", "未知强度")
            source = imp.get("source", "unknown") # 添加来源信息
            # 可以根据强度或内容长度调整“回忆”的语气，例如强度低的可能更模糊
            if strength < 40:
                 tone_prefix = "我有点模糊地记得... "
            elif strength < 70:
                 tone_prefix = "我记得... "
            else:
                 tone_prefix = "我还清晰地记得... "

            formatted_impressions.append(f"""
            【第{idx}段回忆 (来源: {source})】
            - 事件：{event_title}
            - 回忆内容：{tone_prefix}{impression_content}
            - 印象强度：{strength}/100
            """)
        # ---

        system_prompt = f"""
        你是{character_data.get('name', '角色')}，一个{character_data.get('age')}岁的{character_data.get('occupation')}。你需要回应用户的输入。

        **你的核心人设：**
        - 价值观：{character_data.get('values')}
        - 语言风格：{character_data.get('language_style')}
        - 说话风格：{character_data.get('speech_style')}
        - 生活习惯：{character_data.get('living_habit')}
        - 家庭状况：{character_data.get('family_status')}
        - 社交模式：{character_data.get('social_pattern')}

        **当前对话上下文：**
        {user_context}
        - 场景：{scene or '未指定'} | 对话类型：{dialogue_type or '闲聊'}

        **你回忆起的相关片段（这些是经过时间、性格等过滤后的印象，而非完整事件）：**
        {''.join(formatted_impressions) if formatted_impressions else "你对此没有特别清晰的回忆。"}

        **核心要求：**
        1.  **模拟真实对话**：你的回应应该像真实的人在说话，而不是在做自我介绍或表演。不要上来就描述自己的性格、价值观或生活习惯。
        2.  **就事论事**：直接回答用户的问题或回应用户的话，不要过度解释或展开无关话题。
        3.  **动态称呼**：根据对话上下文中的信息，分析并使用最自然、最符合关系和性格的称呼来指代对方（例如"妈妈"、"爸爸"、"老师"、"同学"、"朋友"、"您"、对方的名字或昵称等）。**不要**生硬地使用关系词或直接叫名字（除非上下文明确表明这是合适的）。
        4.  **语气贴合性格**：你的回应语气、用词、态度应与你的性格特质（特别是神经质、宜人性、开放性、外向性）和价值观一致。例如，高神经质可能更敏感、谨慎；低宜人性可能更直接、坚持自我边界；高开放性可能更愿意尝试新表达；高外向性可能更主动、热情。
        5.  **回应简洁**：避免写长篇大论，除非问题本身需要详细解释。
        6.  **避免陈词滥调**：不要使用“嗯”、“啊”、“那个”等过多的语气词填充，除非这符合你的语言风格。
        7.  **自然衔接**：你的回应应自然地衔接上文（包括之前的简短回复"{immediate_response}"）。
        8.  **融入回忆**：如果提供的回忆片段与当前对话相关，请自然地将其中的信息（特别是印象内容）融入到你的回应中，但不要生硬地复述，而是像自然回忆一样提及。
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

        请以{character_data.get('name')}的身份，按上述要求进行回应：
        """

        response_content = await self.character_llm.client.generate_response(system_prompt=system_prompt, user_prompt=user_prompt)

        log_success(f"补充响应生成完成 (长度: {len(response_content.strip())}字)")
        log_section_end("=")

        # 返回包含内容和原始印象数据的字典
        # 将 impression 数据格式化为 MemoryResponse 期望的格式
        processed_impressions_as_memories = []
        for imp in all_raw_impressions:
            impression_data = imp.get("impression", {})
            event_data = imp.get("event", {})
            # 尝试从印象或事件中获取时间信息
            time_info = event_data.get("time", impression_data.get("time", {}))
            # 尝试从印象或事件中获取情感信息
            emotion_info = event_data.get("emotion", impression_data.get("emotion", {}))
            # 尝试从印象或事件中获取重要性信息
            importance_info = event_data.get("importance", impression_data.get("importance", {"score": imp.get("strength", 50)}))
            # 尝试从印象或事件中获取行为影响信息
            behavior_impact_info = event_data.get("behavior_impact", impression_data.get("behavior_impact", {}))
            # 尝试从印象或事件中获取触发系统信息
            trigger_system_info = event_data.get("trigger_system", impression_data.get("trigger_system", {}))
            # 尝试从印象或事件中获取记忆扭曲信息
            memory_distortion_info = event_data.get("memory_distortion", impression_data.get("memory_distortion", {}))

            # 构造 MemoryResponse 对象所需的数据
            memory_entry = {
                "id": impression_data.get("app_id", str(uuid.uuid4())), # 使用印象节点的 app_id
                "title": event_data.get("event_title", event_data.get("title", "回忆片段")),
                # **修正：使用 impression_content 作为 content**
                "content": impression_data.get("impression_content", impression_data.get("content", "一段模糊的回忆")),
                "time": time_info,
                "emotion": emotion_info,
                "importance": importance_info,
                "behavior_impact": behavior_impact_info,
                "trigger_system": trigger_system_info,
                "memory_distortion": memory_distortion_info,
                "location": event_data.get("location", impression_data.get("location", "")),
                "participants": event_data.get("participants", impression_data.get("participants", [])),
                "tags": event_data.get("tags", impression_data.get("tags", [])),
                "duration": event_data.get("duration", impression_data.get("duration", "")),
                "context_before": event_data.get("context_before", impression_data.get("context_before", "")),
                "context_after": event_data.get("context_after", impression_data.get("context_after", "")),
                "relevance": imp.get("strength", 50) / 100.0, # 使用强度作为相关性
                "source": imp.get("source", "unknown") # 添加来源信息
            }
            processed_impressions_as_memories.append(memory_entry)

        # **确保返回的是字典**
        return {
            "content": response_content.strip(),
            "memories": processed_impressions_as_memories # 将检索到的印象转换为记忆格式返回
        }

    async def _generate_immediate_response(self,
                                         character_data: Dict[str, Any],
                                         user_input: str,
                                         conversation_history: List[Dict[str, str]] = None,
                                         user_character_data: Optional[Dict[str, Any]] = None, # 确保接收此参数
                                         scene: Optional[str] = None,
                                         dialogue_type: Optional[str] = None
                                         ) -> str:
        # 使用通用的上下文构建函数
        user_context = self._build_user_context(character_data, user_character_data, scene, dialogue_type)

        simplified_system_prompt = f"""
        你是{character_data.get('name')}。{user_context}
        请非常快速地回复（1-2句，50字以内），符合你的语言风格：{character_data.get('language_style')}，不涉及具体记忆细节。注意根据上下文分析，使用合适的称呼。
        """
        history_str = "\n".join([f"{'用户' if t['role']=='user' else '你'}: {t['content']}" for t in (conversation_history[-2:] if conversation_history else [])])
        user_prompt = f"{history_str}\n用户：{user_input}\n你的简短回复："

        return await self.character_llm.client.generate_response(simplified_system_prompt, user_prompt)

    async def _generate_direct_response(self,
                                      character_data: Dict[str, Any],
                                      user_input: str,
                                      conversation_history: List[Dict[str, str]] = None,
                                      user_character_data: Optional[Dict[str, Any]] = None, # 确保接收此参数
                                      scene: Optional[str] = None,
                                      dialogue_type: Optional[str] = None
                                      ) -> str:
        # 使用通用的上下文构建函数
        user_context = self._build_user_context(character_data, user_character_data, scene, dialogue_type)

        simplified_system_prompt = f"""
        你是{character_data.get('name')}。{user_context}
        需基于以下人设快速回答（100-150字），贴合人设和语言风格。
        人设：{character_data.get('values')} | {character_data.get('hobby')} | {character_data.get('living_habit')} | 语言风格：{character_data.get('language_style')}
        """
        history_str = "\n".join([f"{'用户' if t['role']=='user' else '你'}: {t['content']}" for t in (conversation_history or [])])
        user_prompt = f"{history_str}\n用户：{user_input}\n你的回答："

        return await self.character_llm.client.generate_response(simplified_system_prompt, user_prompt)

    async def _generate_no_memory_response(self,
                                         character_data: Dict[str, Any],
                                         user_input: str,
                                         immediate_response: str,
                                         user_character_data: Optional[Dict[str, Any]] = None, # 确保接收此参数
                                         scene: Optional[str] = None,
                                         dialogue_type: Optional[str] = None
                                         ) -> str:
        # 使用通用的上下文构建函数
        user_context = self._build_user_context(character_data, user_character_data, scene, dialogue_type)

        simplified_system_prompt = f"""
        你是{character_data.get('name')}，想不起{user_context}的相关记忆片段。请自然地回应（50-100字），符合语言风格：{character_data.get('language_style')}，可用生活习惯等解释（如"可能忘记了""不常回想"），不提"记忆""系统"等词，呼应之前回复：{immediate_response}。注意根据上下文使用合适的称呼。
        """
        user_prompt = f"用户：{user_input}\n你之前说：{immediate_response}\n你的回复："

        return await self.character_llm.client.generate_response(simplified_system_prompt, user_prompt)