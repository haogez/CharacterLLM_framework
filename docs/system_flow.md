# 系统流程概览

本文档梳理 `main_full`, `graph_store`, `story_based_memory_generator`, `generator`, `openai_client`, `flow` 六个核心文件的协作流程，方便快速理解系统逻辑。

## 1. 角色生成入口（`app/main_full.py`）
- FastAPI 提供 `/api/v1/characters/generate` 接口。
- 调用 `CharacterGenerator` 基于用户描述生成主角色，并写入内存态字典 `characters`。
- 生成关联角色后，后台任务触发 `generate_and_store_fine_grained_memories` 进入故事与记忆构建流程。

## 2. 角色与关联角色生成（`app/core/character/generator.py`）
- `CharacterGenerator.generate_character` 通过 `CharacterLLM` 生成主角 21 个画像字段并做校验。
- `generate_related_characters` 解析主角的 past_experience/background，推断关键关系类型，再用 LLM 生成具有关系属性的关联角色，确保与主角人设、年龄阶段一致。

## 3. LLM 客户端封装（`app/core/llm/openai_client.py`）
- `OpenAIClient` 封装异步 ChatCompletions/Embeddings，支持自定义 `OPENAI_API_KEY` 与 `OPENAI_BASE_URL`。
- `CharacterLLM` 作为上层封装，提供角色画像生成、结构化 JSON 解析等能力，并在解析失败时尝试从 ```json``` 代码块或文本中提取 JSON。

## 4. 故事驱动的记忆构建（`app/core/memory/story_based_memory_generator.py`）
- `generate_idea` 根据主角背景生成故事类型与核心主题。
- `refine_characters_with_backgrounds` 补全主角及关联角色的背景故事，强调按年龄格式化事件。
- `generate_chaptered_lifespan_story` 产出分章节人生故事；当前 `generate_and_store_fine_grained_memories` 直接将章节故事作为记忆片段输入后续处理。
- `extract_entities_and_relationships_from_story` 解析故事，提取实体与事件关系，配合 GraphStore 写入 CSV。

## 5. 图谱与向量存储（`app/core/graph/graph_store.py`）
- 启动时自动检查/创建 `impression_embeddings` 向量索引（基于 `impression_embedding` 属性，维度取自当前嵌入模型），缺失时即刻创建，保证 Neo4jVector 可用；若向量初始化仍失败，则降级继续启动并给出提示。
- 提供 CSV 导入/导出能力：节点、实体-事件关系、时间链、事件细节、对话节点（逐句、带说话人）、角色间关系等均可生成 CSV 并批量导入 Neo4j。
- 支持按角色查询记忆、关系、地点（Place 节点），并暴露关系查询、向量检索等辅助方法供对话流程使用。

## 6. 对话响应流程（`app/core/response/flow.py`）
- `ResponseFlow.process` 分三阶段：
  1) `_needs_memory` 判断是否需要调用记忆。
  2) `_generate_immediate_response` 生成即时回答。
  3) `_generate_supplementary_response` 通过 GraphRAG 从 Neo4j 检索印象记忆，并补充带记忆的响应。
- `app/main_full.py` 的 `/api/v1/chat` 将该生成过程封装为 SSE 流式输出，兼容用户扮演角色上下文并记录日志。

## 7. 后台故事到图谱的流水线（`generate_and_store_fine_grained_memories` 于 `app/main_full.py`）
1) 为主角孵化故事灵感并完善角色背景（主角时间线字段强校验，关联角色时间线宽松但会统一转字符串）。
2) 生成分章节故事并作为记忆片段使用，按场景/时间/主题/参与者落地事件节点。
3) 从故事中抽取实体、关系与时间链；生成 CSV，其中对话被切分为逐句的 Dialogue 节点并回连说话人 Character 节点。
4) 将节点、实体-事件关系、时间链、事件细节、角色关系等 CSV 导入 Neo4j，并在导入前确保向量索引可用。
5) 更新角色的生成状态与耗时统计。

整体上，API 层驱动角色生成与对话，故事生成模块负责记忆与图谱的数据产出，GraphStore 负责存储与检索，ResponseFlow 则结合 LLM 与图谱实现带记忆的聊天体验。
