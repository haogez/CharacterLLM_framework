# app/core/graph/graph_store.py

"""
图谱存储模块 (Neo4j 自部署版) - 使用统一 CSV 格式
修改以支持：
1. 统一的 Character 节点 (基于 app_id)
2. 印象节点 (Impression) 和事件节点 (Event)
3. 时间顺序链
4. 印象随时间变化和事件间影响
5. 修复 Cypher 语法错误和类型错误
6. 修复注释语法错误
7. 修复 CSV 中 JSON 字符串引号转义问题 - 使用 Base64 编码
8. 修复重复角色节点问题
9. 修复 Cypher 弃用警告
10. 为所有角色（包括关联角色）添加完整的印象结构
11. 基于多因素的印象强度计算
12. 事件细节节点（物品、动作、对话）
13. 优化节点结构，确保清晰无重复
"""
import traceback

import os
import json
import uuid
import re
import csv
import base64
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from neo4j import GraphDatabase
from langchain_community.vectorstores import Neo4jVector
from langchain_openai import OpenAIEmbeddings # 或者其他嵌入模型
from app.core.utils.log_utils import log_error, log_success, log_warning, log_info, log_debug

class GraphStore:
    def __init__(self,
                 uri: str = "bolt://neo4j-latest-new:7687",
                 user: str = "neo4j",
                 password: str = "zyh123456",
                 database: str = "neo4j",
                 embedding: Optional[Any] = None,
                 index_name: str = "impressions", # 为印象节点指定索引
                 text_node_property: str = "impression_content" # 指定用于向量化的节点属性
                 ):
        self.uri = uri
        self.user = user
        self.password = password
        self.database = database
        self.driver = GraphDatabase.driver(self.uri, auth=(self.user, self.password))
        self.temp_csv_dir = "./temp_csv"
        os.makedirs(self.temp_csv_dir, exist_ok=True)

        print("- 初始化 OpenAI Embeddings -")
        try:
            # 新版 langchain-openai 的正确写法（base_url 需要显式写出）
            self.embeddings = OpenAIEmbeddings(
                model="text-embedding-3-small",
                api_key=os.environ.get("OPENAI_API_KEY"),
                base_url=os.environ.get("OPENAI_BASE_URL")  # 关键：新版要求显式写出 base_url
            )
            print("✅ OpenAI Embeddings 初始化成功。")
        except Exception as e:
            print(f"❌ OpenAI Embeddings 初始化失败: {e}")
            import traceback as tb
            tb.print_exc()
            self.embeddings = None
            self.neo4j_vector_impressions = None


        # --- 初始化 Neo4jVector 实例 ---
        # 确保 embeddings 成功初始化后才尝试初始化 Neo4jVector
        if self.embeddings is not None:
            try:
                self.neo4j_vector_impressions = Neo4jVector.from_existing_index(
                    embedding=self.embeddings, # 现在 self.embeddings 已存在且配置正确
                    url=self.uri,
                    username=self.user,
                    password=self.password,
                    database=self.database,
                    embedding_node_property="impression_embedding", # 这个属性名需要在导入时创建
                    index_name="impression_embeddings", # 确保索引名称正确且维度匹配
                    # search_type="vector", # 如果要使用 hybrid，必须确保 keyword_index_name 指向的全文索引存在
                )
                print("✅ Neo4jVector (impressions) 初始化成功。")
            except Exception as e:
                print(f"❌ Neo4jVector (impressions) 初始化失败: {e}")
                print("   这可能导致语义搜索功能不可用，但应用将继续启动。")
                # **修正：确保 traceback 可用**
                import traceback as tb
                tb.print_exc() # 打印完整堆栈跟踪
                self.neo4j_vector_impressions = None # 设置为 None，后续需要检查
        else:
            print("⚠️  由于 Embeddings 初始化失败，跳过 Neo4jVector 初始化。")
            self.neo4j_vector_impressions = None
        # --- 修改：初始化 Neo4jVector 实例用于 Event 节点 ---
        # 注意：这里假设索引 "event_embeddings" (向量索引) 和 "event_keyword_index" (全文索引) 已在 Neo4j 中创建
        # self.neo4j_vector_events = Neo4jVector.from_existing_index(
        #     embedding=self.embeddings,
        #     url=self.uri,
        #     username=self.user,
        #     password=self.password,
        #     database=self.database,
        #     embedding_node_property="event_embedding", # 这个属性名需要在导入时创建
        #     index_name="event_embeddings", # 向量索引名，需要预先存在
        #     # --- 修改：添加 keyword_index_name ---
        #     keyword_index_name="event_keyword_index", # 全文索引名，需要预先存在
        #     # --- 修改：search_type 改为 vector 或保持 hybrid (但必须提供 keyword_index_name) ---
        #     search_type="vector", # 暂时改为 vector 以避免需要全文索引，或者确保 keyword_index_name 存在
        #     # search_type="hybrid", # 如果要使用 hybrid，必须确保 keyword_index_name 指向的全文索引存在
        #     # retrieval_query="""
        #     # // 在检索时，返回 Event 节点及其关联的 Character 和 Impression 信息
        #     # MATCH (e:Event {app_id: node.app_id})<-[:OF_EVENT]-(i:Impression)<-[:HAS_IMPRESSION]-(c:Character)
        #     # RETURN e{.*, app_id: e.app_id}, i{.*, app_id: i.app_id}, c{.*, app_id: c.app_id}, score
        #     # """
        # )
        # --- 修改：初始化 Neo4jVector 实例用于 Impression 节点 ---
        self.neo4j_vector_impressions = Neo4jVector.from_existing_index(
            embedding=self.embeddings,
            url=self.uri,
            username=self.user,
            password=self.password,
            database=self.database,
            embedding_node_property="impression_embedding", # 这个属性名需要在导入时创建
            index_name="impression_embeddings", # 向量索引名，需要预先存在
            # --- 修改：添加 keyword_index_name (如果需要 hybrid) 或者使用 vector ---
            # keyword_index_name="impression_keyword_index", # 全文索引名，需要预先存在
            search_type="vector", # 暂时改为 vector
            # search_type="hybrid", # 如果要使用 hybrid，必须确保 keyword_index_name 指向的全文索引存在
            # retrieval_query="""
            # // 在检索时，返回 Impression 节点及其关联的 Character 和 Event 信息
            # MATCH (i:Impression {app_id: node.app_id})-[:OF_EVENT]->(e:Event)
            # RETURN i{.*, app_id: i.app_id}, e{.*, app_id: e.app_id}, score
            # """
        )
        print("--- Neo4jVector 实例初始化完成 ---")
        # 使用通过挂载卷共享的目录
        self.temp_csv_dir = "/zhouyuhao/zhouyuhao_data_new/import"
        os.makedirs(self.temp_csv_dir, exist_ok=True)

        AUTH = (self.user, self.password)

        print(f"=== Neo4j 连接调试 ===")
        print(f"URI: {self.uri}")
        print(f"User: {self.user}")
        print(f"Database: {self.database}")
        print(f"======================")

        try:
            self.driver = GraphDatabase.driver(self.uri, auth=AUTH)
            self.driver.verify_connectivity()
            print(f"--- 成功连接到 Neo4j '{self.database}' ---")
            print(f"--- URI: {self.uri} ---")
            print("--- Neo4j 连接初始化完成 ---")
        except Exception as e:
            print(f"连接 Neo4j 失败: {e}")
            import traceback
            traceback.print_exc()
            raise e

    def close(self):
        if self.driver:
            self.driver.close()
            print("--- Neo4j 连接已关闭 ---")


    def create_character_node(self, character_data: Dict[str, Any]) -> bool:
        """
        创建或更新角色节点。
        使用 app_id 作为唯一标识，避免重复创建。
        """
        char_name = character_data.get("name")
        if not char_name:
            print("错误：角色数据必须包含 'name' 字段。")
            return False

        app_id = character_data.get("id", str(uuid.uuid4()))

        with self.driver.session(database=self.database) as session:
            try:
                node_properties = character_data.copy()
                node_properties.pop("id", None)
                node_properties["app_id"] = app_id
                # 确保标签为 Character
                node_properties["is_main_character"] = node_properties.get("is_main_character", False)

                # 将所有嵌套结构转为JSON字符串
                for key, value in node_properties.items():
                    if isinstance(value, (dict, list)) and not isinstance(value, (str, int, float, bool)):
                        node_properties[key] = json.dumps(value, ensure_ascii=False)

                session.run(
                    """
                    MERGE (c:Character {app_id: $app_id}) // 使用 app_id 作为唯一标识
                    SET c = $properties
                    """,
                    app_id=app_id,
                    properties=node_properties
                )
                print(f"--- 角色节点 '{char_name}' (app_id: {app_id}) 创建/更新成功 ---")
                return True
            except Exception as e:
                print(f"创建角色节点 '{char_name}' 失败: {e}")
                return False

    def create_general_entity_node(self, entity_data: Dict[str, Any]) -> bool:
        """
        创建通用实体节点 (非人物)。
        根据实体类型创建不同标签的节点，并使用 app_id 作为唯一标识。
        """
        ent_name = entity_data.get("name")
        ent_type = entity_data.get("type", "Entity").upper()
        if not all([ent_name, ent_type]):
            print("错误：实体数据必须包含 'name' 和 'type' 字段。")
            return False

        app_id = entity_data.get("id", str(uuid.uuid4()))

        with self.driver.session(database=self.database) as session:
            try:
                node_properties = entity_data.copy()
                node_properties.pop("id", None)
                node_properties["app_id"] = app_id

                # 将所有嵌套结构转为JSON字符串
                for key, value in node_properties.items():
                    if isinstance(value, (dict, list)) and not isinstance(value, (str, int, float, bool)):
                        node_properties[key] = json.dumps(value, ensure_ascii=False)

                # 为非人物实体创建标签
                label = f"{ent_type}"

                session.run(
                    f"""
                    MERGE (e:{label} {{app_id: $app_id}}) // 使用 app_id 作为唯一标识
                    SET e = $properties
                    """,
                    app_id=app_id,
                    properties=node_properties
                )
                print(f"--- 实体节点 '{ent_name}' ({ent_type}) 创建/更新成功 ---")
                return True
            except Exception as e:
                print(f"创建实体节点 '{ent_name}' 失败: {e}")
                return False

    def create_event_node(self, event_data: Dict[str, Any]) -> bool:
        """
        创建事件节点，包含事件的真实内容。
        """
        event_app_id = event_data.get("id", str(uuid.uuid4()))
        event_data["id"] = event_app_id
        event_title = event_data.get("title", "未命名事件")

        with self.driver.session(database=self.database) as session:
            try:
                event_properties = event_data.copy()
                event_properties.pop("id", None)
                event_properties["app_id"] = event_app_id
                # 存储事件的原始内容作为context
                event_properties["context"] = event_data.get("content", "")

                # 将所有嵌套结构转为JSON字符串
                for key, value in event_properties.items():
                    if isinstance(value, (dict, list)) and not isinstance(value, (str, int, float, bool)):
                        event_properties[key] = json.dumps(value, ensure_ascii=False)

                session.run(
                    """
                    MERGE (e:Event {app_id: $event_app_id})
                    SET e = $properties
                    """,
                    event_app_id=event_app_id,
                    properties=event_properties
                )
                print(f"--- 事件节点 '{event_title}' ({event_app_id}) 创建/更新成功 ---")
                return True
            except Exception as e:
                print(f"创建事件节点 '{event_app_id}' 失败: {e}")
                return False

    def create_event_detail_node(self, event_app_id: str, detail_data: Dict[str, Any]) -> bool:
        """
        创建事件细节节点（物品、动作、对话等）。
        detail_type: "object", "action", "dialogue"
        """
        detail_app_id = detail_data.get("id", str(uuid.uuid4()))
        detail_type = detail_data.get("type", "DETAIL")
        detail_content = detail_data.get("content", "")
        
        if not all([event_app_id, detail_type, detail_content]):
            print("错误：细节数据必须包含 'type' 和 'content' 字段，且需要事件ID")
            return False

        with self.driver.session(database=self.database) as session:
            try:
                detail_properties = detail_data.copy()
                detail_properties.pop("id", None)
                detail_properties["app_id"] = detail_app_id
                detail_properties["event_app_id"] = event_app_id

                # 将所有嵌套结构转为JSON字符串
                for key, value in detail_properties.items():
                    if isinstance(value, (dict, list)) and not isinstance(value, (str, int, float, bool)):
                        detail_properties[key] = json.dumps(value, ensure_ascii=False)

                # 创建特定类型的细节节点
                session.run(
                    f"""
                    MERGE (d:{detail_type} {{app_id: $detail_app_id}})
                    SET d = $properties
                    """,
                    detail_app_id=detail_app_id,
                    properties=detail_properties
                )
                
                # 连接到事件节点
                session.run(
                    """
                    MATCH (d) WHERE d.app_id = $detail_app_id
                    MATCH (e:Event) WHERE e.app_id = $event_app_id
                    MERGE (e)-[:HAS_DETAIL]->(d)
                    """,
                    detail_app_id=detail_app_id,
                    event_app_id=event_app_id
                )
                
                print(f"--- 事件细节节点 ({detail_type}: {detail_app_id}) 创建并关联到事件 {event_app_id} 成功 ---")
                return True
            except Exception as e:
                print(f"创建事件细节节点 '{detail_app_id}' 失败: {e}")
                return False

    def calculate_impression_strength(self, character_data: Dict[str, Any], event_data: Dict[str, Any]) -> int:
        """
        根据多因素计算印象强度:
        1. 事件发生时间（越近强度越高）
        2. 事件影响程度（正面/负面/重大程度）
        3. 角色性格特质（敏感性等）
        """
        # 基础强度
        base_strength = 70
        
        # 1. 时间因素（假设事件有timestamp字段）
        event_time_str = event_data.get("time", {}).get("specific", "")
        try:
            event_time = datetime.fromisoformat(event_time_str)
            days_since = (datetime.now() - event_time).days
            # 时间衰减：每过30天衰减10%，最低保留30%
            time_factor = max(0.3, 1 - (days_since / 300))  # 300天约衰减70%
        except:
            time_factor = 1.0  # 无法解析时间则不衰减
        
        # 2. 事件影响因素
        impact_score = event_data.get("importance", {}).get("score", 5) / 5.0  # 归一化到0-1
        event_type = event_data.get("type", "")
        if event_type in ["trauma", "achievement"]:  # 重大事件额外加成
            impact_factor = impact_score * 1.5
        else:
            impact_factor = impact_score
        
        # 3. 角色性格因素（神经质/开放性越高，记忆越深刻）
        personality = character_data.get("personality", {})
        neuroticism = personality.get("neuroticism", 50) / 100.0  # 归一化到0-1
        openness = personality.get("openness", 50) / 100.0
        personality_factor = 0.5 + (neuroticism + openness) / 4  # 范围0.5-1.0
        
        # 计算最终强度（0-100）
        final_strength = int(base_strength * time_factor * impact_factor * personality_factor)
        return max(10, min(100, final_strength))  # 确保在10-100之间

    def create_impression_node(self, impression_data: Dict[str, Any], character_data: Dict[str, Any], event_data: Dict[str, Any]) -> bool:
        """
        创建印象节点，基于角色性格、事件重要性和时间计算强度。
        """
        impression_app_id = impression_data.get("id", str(uuid.uuid4()))
        impression_data["id"] = impression_app_id
        
        # 确保印象数据包含必要字段
        source_char_id = impression_data.get("source_character_app_id")
        event_id = impression_data.get("event_app_id")
        if not source_char_id or not event_id:
            print(f"错误：印象数据必须包含 'source_character_app_id' 和 'event_app_id'。")
            return False

        with self.driver.session(database=self.database) as session:
            try:
                impression_properties = impression_data.copy()
                impression_properties.pop("id", None)
                impression_properties["app_id"] = impression_app_id
                
                # 计算印象强度
                impression_properties["strength"] = self.calculate_impression_strength(character_data, event_data)
                
                # 根据强度决定细节保留程度
                full_content = impression_data.get("content", "")
                if impression_properties["strength"] < 30:
                    # 强度低，保留更少细节
                    content_length = max(5, int(len(full_content) * 0.3))
                    impression_properties["content"] = full_content[:content_length] + "..."
                    impression_properties["is_faded"] = True
                elif impression_properties["strength"] < 70:
                    # 强度中等，保留部分细节
                    content_length = max(10, int(len(full_content) * 0.7))
                    impression_properties["content"] = full_content[:content_length]
                    impression_properties["is_faded"] = False
                else:
                    # 强度高，保留完整细节
                    impression_properties["content"] = full_content
                    impression_properties["is_faded"] = False

                # 将所有嵌套结构转为JSON字符串
                for key, value in impression_properties.items():
                    if isinstance(value, (dict, list)) and not isinstance(value, (str, int, float, bool)):
                        impression_properties[key] = json.dumps(value, ensure_ascii=False)

                session.run(
                    """
                    MERGE (i:Impression {app_id: $impression_app_id})
                    SET i = $properties
                    """,
                    impression_app_id=impression_app_id,
                    properties=impression_properties
                )
                print(f"--- 印象节点 ({impression_app_id}) 创建/更新成功 (强度: {impression_properties['strength']}) ---")
                return True
            except Exception as e:
                print(f"创建印象节点 '{impression_app_id}' 失败: {e}")
                return False

    def create_character_event_impression_triple(self, character_data: Dict[str, Any], event_data: Dict[str, Any], impression_content: str, remembered_details: Dict[str, List[str]]) -> bool: # **修改：添加 remembered_details 参数
        """为单个角色创建完整的"角色->印象->事件"结构
        impression_content: 已经根据角色视角、性格、时间等处理过的印象内容
        remembered_details: 一个字典，包含印象中记得的细节，如 {"locations": ["学校"], "items": ["日记本"]}
        """
        character_app_id = character_data.get("id")
        event_app_id = event_data.get("id")
        if not all([character_app_id, event_app_id, impression_content]):
            print("错误：创建角色-印象-事件三元组缺少必要数据")
            return False

        if not self.create_character_node(character_data):
            return False
        if not self.create_event_node(event_data): # 事件节点将包含原始内容
            return False

        # 2. 创建印象数据 (impression_content 应该已经是处理过的)
        impression_data = {
            "id": str(uuid.uuid4()),
            "source_character_app_id": character_app_id,
            "event_app_id": event_app_id,
            "content": impression_content, # 使用已处理的内容
            "timestamp": datetime.now().isoformat()
        }

        # 3. 创建印象节点（使用新的带强度计算的方法）
        if not self.create_impression_node(impression_data, character_data, event_data):
            return False

        # 4. 建立基本关系 (角色 -> 印象 -> 事件)
        with self.driver.session(database=self.database) as session:
            try:
                # 角色 -> 印象
                session.run("""
                    MATCH (c:Character {app_id: $char_app_id}), (i:Impression {app_id: $impression_app_id})
                    MERGE (c)-[:HAS_IMPRESSION]->(i)
                """, char_app_id=character_app_id, impression_app_id=impression_data["id"])

                # 印象 -> 事件
                session.run("""
                    MATCH (i:Impression {app_id: $impression_app_id}), (e:Event {app_id: $event_app_id})
                    MERGE (i)-[:OF_EVENT]->(e)
                """, impression_app_id=impression_data["id"], event_app_id=event_app_id)

                # --- 新增：连接印象到事件的衍生节点 (基于 remembered_details) ---
                impression_app_id = impression_data["id"]
                for detail_type, detail_names in remembered_details.items():
                    for detail_name in detail_names:
                        if not detail_name:
                            continue
                        # 根据 detail_type 构造 detail_app_id (与 save_entities_and_relationships_to_csv 中的逻辑一致)
                        if detail_type == "locations":
                            detail_app_id = f"place_{hash(detail_name)}"
                            rel_type = "REMEMBERS_LOCATION"
                        elif detail_type == "times":
                            detail_app_id = f"time_{hash(detail_name)}"
                            rel_type = "REMEMBERS_TIME"
                        elif detail_type == "actions":
                            detail_app_id = f"action_{hash(detail_name)}"
                            rel_type = "REMEMBERS_ACTION"
                        elif detail_type == "actors":
                            detail_app_id = f"actor_{hash(detail_name)}"
                            rel_type = "REMEMBERS_ACTOR"
                        elif detail_type == "emotions":
                            detail_app_id = f"emotion_{hash(detail_name)}"
                            rel_type = "REMEMBERS_EMOTION"
                        elif detail_type == "items":
                            detail_app_id = f"item_{hash(detail_name)}"
                            rel_type = "REMEMBERS_ITEM"
                        else:
                            continue # 跳过未知类型

                        # 创建 Impression -> Detail 的关系
                        # 注意：这里假设 detail_app_id 对应的节点已经存在（由 Event 连接创建）
                        # MERGE 确保关系唯一
                        session.run(f"""
                            MATCH (i:Impression {{app_id: $impression_app_id}})
                            MATCH (d) WHERE d.app_id = $detail_app_id
                            MERGE (i)-[:{rel_type}]->(d)
                        """, impression_app_id=impression_app_id, detail_app_id=detail_app_id)

                print(f"--- 角色 {character_app_id} -> 印象 -> 事件 {event_app_id} 三元组及其相关衍生节点连接创建成功 ---")
                return True
            except Exception as e:
                print(f"创建角色-印象-事件三元组及其相关衍生节点连接失败: {e}")
                import traceback
                traceback.print_exc()
                return False

    def create_all_character_event_impressions(self, main_character: Dict[str, Any], related_characters: List[Dict[str, Any]], event_data: Dict[str, Any], impression_contents: Dict[str, str]) -> bool:
        """
        为所有角色（主角色+关联角色）创建"角色->印象->事件"结构
        impression_contents: 字典，键为角色ID，值为该角色对事件的印象内容
        """
        # 为主角色创建印象
        main_char_id = main_character.get("id")
        if main_char_id in impression_contents:
            if not self.create_character_event_impression_triple(
                main_character, 
                event_data, 
                impression_contents[main_char_id]
            ):
                print(f"警告：主角色 {main_char_id} 的印象创建失败")
        
        # 为所有关联角色创建印象
        for char in related_characters:
            char_id = char.get("id")
            if char_id and char_id in impression_contents:
                if not self.create_character_event_impression_triple(
                    char, 
                    event_data, 
                    impression_contents[char_id]
                ):
                    print(f"警告：关联角色 {char_id} 的印象创建失败")
        
        return True


    def connect_entity_to_event(self, entity_app_id: str, event_app_id: str, relationship_type: str = "RELATED_TO") -> bool:
        """
        连接非人物实体到事件。
        """
        with self.driver.session(database=self.database) as session:
            try:
                # 确保实体和事件节点存在
                ent_result = session.run(
                    """
                    MATCH (ent) WHERE ent.app_id = $entity_app_id
                    RETURN ent
                    """,
                    entity_app_id=entity_app_id
                ).single()
                if not ent_result:
                    print(f"错误：未找到实体 app_id 为 {entity_app_id} 的节点。")
                    return False

                event_result = session.run(
                    """
                    MATCH (e:Event) WHERE e.app_id = $event_app_id
                    RETURN e
                    """,
                    event_app_id=event_app_id
                ).single()
                if not event_result:
                    print(f"错误：未找到事件 app_id 为 {event_app_id} 的节点。")
                    return False

                # 连接实体 -> 事件
                session.run(
                    f"""
                    MATCH (ent) WHERE ent.app_id = $entity_app_id
                    MATCH (e:Event {{app_id: $event_app_id}})
                    MERGE (ent)-[:{relationship_type}]->(e)
                    """,
                    entity_app_id=entity_app_id,
                    event_app_id=event_app_id
                )
                print(f"--- 实体 {entity_app_id} -> 事件 {event_app_id} (关系: {relationship_type}) 连接成功 ---")
                return True
            except Exception as e:
                print(f"连接实体 {entity_app_id} -> 事件 {event_app_id} 失败: {e}")
                return False

    def create_temporal_chain(self, sorted_events: List[Dict[str, Any]]) -> bool:
        """
        创建事件的时间顺序链。
        sorted_events: 按时间戳排序的事件列表。
        """
        if len(sorted_events) < 2:
            print("事件数量少于2，无需创建时间链。")
            return True

        with self.driver.session(database=self.database) as session:
            try:
                for i in range(len(sorted_events) - 1):
                    current_event_id = sorted_events[i].get("id")
                    next_event_id = sorted_events[i+1].get("id")
                    if not current_event_id or not next_event_id:
                        print(f"警告：事件列表中存在缺失ID，跳过连接。")
                        continue

                    session.run(
                        """
                        MATCH (e1:Event {app_id: $current_event_id}), (e2:Event {app_id: $next_event_id})
                        MERGE (e1)-[:FOLLOWS]->(e2)
                        """,
                        current_event_id=current_event_id,
                        next_event_id=next_event_id
                    )
                    print(f"--- 时间链连接：事件 {current_event_id} -> 事件 {next_event_id} ---")
                print("--- 时间顺序链创建完成 ---")
                return True
            except Exception as e:
                print(f"创建时间顺序链失败: {e}")
                return False

    def get_related_characters(self, character_id: str) -> List[Dict[str, Any]]:
        """
        获取与指定角色相关的角色列表。
        通过事件关联。
        """
        with self.driver.session(database=self.database) as session:
            try:
                result = session.run(
                    """
                    MATCH (c1:Character {app_id: $char_id})-[:HAS_IMPRESSION]->(:Impression)-[:OF_EVENT]->(e:Event)<-[:OF_EVENT]-(:Impression)<-[:HAS_IMPRESSION]-(c2:Character)
                    WHERE c1 <> c2
                    RETURN DISTINCT c2
                    """,
                    char_id=character_id
                )

                related_chars = []
                for record in result:
                    char_node = record["c2"]
                    char_props = dict(char_node)
                    for key, value in char_props.items():
                        if isinstance(value, str):
                            try:
                                char_props[key] = json.loads(value)
                            except (json.JSONDecodeError, TypeError):
                                pass
                    related_chars.append(char_props)

                print(f"--- 获取到 {len(related_chars)} 个与角色 {character_id} 相关的角色 ---")
                return related_chars
            except Exception as e:
                print(f"获取角色 {character_id} 的相关角色失败: {e}")
                return []

    def get_character_impressions(self, character_id: str) -> List[Dict[str, Any]]:
        """
        获取指定角色的所有印象及其关联的事件。
        """
        with self.driver.session(database=self.database) as session:
            try:
                result = session.run(
                    """
                    MATCH (c:Character {app_id: $char_id})-[:HAS_IMPRESSION]->(i:Impression)-[:OF_EVENT]->(e:Event)
                    RETURN i, e
                    """,
                    char_id=character_id
                )

                impressions = []
                for record in result:
                    impression_node = record["i"]
                    event_node = record["e"]
                    impression_props = dict(impression_node)
                    event_props = dict(event_node)

                    # 合并印象和事件信息
                    combined = {
                        "impression": impression_props,
                        "event": event_props,
                        "event_app_id": event_props.get("app_id"),
                        "impression_app_id": impression_props.get("app_id")
                    }

                    # 解析JSON字段
                    for key, value in combined["impression"].items():
                        if isinstance(value, str):
                            try:
                                combined["impression"][key] = json.loads(value)
                            except (json.JSONDecodeError, TypeError):
                                pass
                    
                    for key, value in combined["event"].items():
                        if isinstance(value, str):
                            try:
                                combined["event"][key] = json.loads(value)
                            except (json.JSONDecodeError, TypeError):
                                pass

                    impressions.append(combined)

                print(f"--- 获取到 {len(impressions)} 条角色 {character_id} 的印象 ---")
                return impressions
            except Exception as e:
                print(f"获取角色 {character_id} 的印象失败: {e}")
                return []

    def get_event_details(self, event_id: str) -> List[Dict[str, Any]]:
        """
        获取事件的所有细节节点（物品、动作、对话等）
        """
        with self.driver.session(database=self.database) as session:
            try:
                result = session.run(
                    """
                    MATCH (e:Event {app_id: $event_id})-[:HAS_DETAIL]->(d)
                    RETURN d
                    """,
                    event_id=event_id
                )

                details = []
                for record in result:
                    detail_node = record["d"]
                    detail_props = dict(detail_node)
                    
                    # 解析JSON字段
                    for key, value in detail_props.items():
                        if isinstance(value, str):
                            try:
                                detail_props[key] = json.loads(value)
                            except (json.JSONDecodeError, TypeError):
                                pass
                    
                    details.append(detail_props)

                print(f"--- 获取到 {len(details)} 个事件 {event_id} 的细节 ---")
                return details
            except Exception as e:
                print(f"获取事件 {event_id} 的细节失败: {e}")
                return []

    def delete_character_graph(self, character_id: str) -> bool:
        """
        删除指定角色及其关联的图谱数据（印象、关系）。
        保留事件和细节节点，因为它们可能与其他角色相关。
        """
        with self.driver.session(database=self.database) as session:
            try:
                # 1. 删除角色 -> 印象的关系和印象节点
                session.run(
                    """
                    MATCH (c:Character {app_id: $char_id})-[r:HAS_IMPRESSION]->(i:Impression)
                    DELETE r, i
                    """,
                    char_id=character_id
                )
                # 2. 删除角色本身
                session.run(
                    """
                    MATCH (c:Character {app_id: $char_id})
                    DELETE c
                    """,
                    char_id=character_id
                )
                print(f"--- 角色 {character_id} 及其关联的印象节点已删除 ---")
                return True
            except Exception as e:
                print(f"删除角色 {character_id} 的图谱数据失败: {e}")
                return False

    def update_impression_over_time(self, impression_app_id: str) -> bool:
        """
        模拟印象随时间自然变化（淡忘）。
        根据当前强度应用不同的衰减因子
        """
        with self.driver.session(database=self.database) as session:
            try:
                # 获取当前印象内容和强度
                result = session.run(
                    """
                    MATCH (i:Impression {app_id: $impression_app_id})
                    RETURN i.impression_content AS current_content, i.content AS content, i.strength AS current_strength
                    """,
                    impression_app_id=impression_app_id
                ).single()

                if not result:
                    print(f"错误：未找到印象 ID 为 {impression_app_id} 的节点。")
                    return False

                current_content = result["content"] or result["current_content"] or ""
                current_strength = result["current_strength"] or 100

                # 根据当前强度应用不同的衰减因子
                if current_strength < 30:
                    decay_factor = 0.8  # 弱记忆衰减更快
                elif current_strength < 70:
                    decay_factor = 0.9  # 中等记忆正常衰减
                else:
                    decay_factor = 0.95  # 强记忆衰减较慢

                # 计算新的强度和内容
                new_strength = max(5, int(current_strength * decay_factor))
                content_length = max(5, int(len(current_content) * decay_factor))
                new_content = current_content[:content_length] + ("..." if len(current_content) > content_length else "")

                session.run(
                    """
                    MATCH (i:Impression {app_id: $impression_app_id})
                    SET i.content = $new_content, i.strength = $new_strength, i.last_updated = $timestamp
                    """,
                    impression_app_id=impression_app_id,
                    new_content=new_content,
                    new_strength=new_strength,
                    timestamp=datetime.now().isoformat()
                )
                print(f"--- 印象 {impression_app_id} 已更新 (强度: {new_strength}, 内容长度: {len(new_content)}) ---")
                return True
            except Exception as e:
                print(f"更新印象 {impression_app_id} 失败: {e}")
                return False

    def save_entities_and_relationships_to_csv(self,
                                            main_character: Dict[str, Any], # 主角色
                                            related_characters: List[Dict[str, Any]], # 关联角色，包含 relationship_to_protagonist
                                            entities: List[Dict[str, Any]], # 额外实体（可选，可能从其他地方提取）
                                            relationships: List[Dict[str, Any]], # 额外关系（可选，可能从其他地方提取）
                                            memories: List[Dict[str, Any]], # **关键修改：现在是结构化的对话场景列表**
                                            character_id: str, # 主角色 ID
                                            character_to_character_relationships: List[Dict[str, Any]] = None # 可选的推断角色间关系
                                            ) -> Dict[str, str]:
        """
        将角色、结构化对话场景（作为事件）、细粒度细节（从场景中直接获取）、
        额外实体/关系、角色间关系等数据保存为多个符合 Neo4j LOAD CSV 格式的 CSV 文件。
        **关键修改：直接使用 memories 中的字段，不再进行文本提取。**
        """
        print(f"- 开始将数据保存为统一格式的 CSV (新模型, 直接使用对话场景) -", flush=True)

        # --- 定义 CSV 文件路径 ---
        nodes_filename = os.path.join(self.temp_csv_dir, f"story_nodes_{character_id}.csv")
        # impressions_filename = os.path.join(self.temp_csv_dir, f"story_impressions_{character_id}.csv") # 如果需要单独的印象节点
        relationships_filename = os.path.join(self.temp_csv_dir, f"story_entity_event_relationships_{character_id}.csv") # 非人物实体-事件关系 (可选)
        temporal_chain_filename = os.path.join(self.temp_csv_dir, f"temporal_chain_{character_id}.csv")
        details_filename = os.path.join(self.temp_csv_dir, f"event_details_{character_id}.csv") # 事件细节 (可选)
        # 新增：角色间关系 CSV 文件名 (用于主角 -> 关联角色)
        char_to_char_relationships_filename = os.path.join(self.temp_csv_dir, f"character_to_character_relationships_{character_id}.csv")
        # 新增：细粒度节点 CSV 文件名 (直接从 memories 获取)
        places_filename = os.path.join(self.temp_csv_dir, f"places_{character_id}.csv")
        times_filename = os.path.join(self.temp_csv_dir, f"times_{character_id}.csv")
        actions_filename = os.path.join(self.temp_csv_dir, f"actions_{character_id}.csv")
        actors_filename = os.path.join(self.temp_csv_dir, f"actors_{character_id}.csv")
        emotions_filename = os.path.join(self.temp_csv_dir, f"emotions_{character_id}.csv")
        items_filename = os.path.join(self.temp_csv_dir, f"items_{character_id}.csv")
        # 新增：事件-细粒度节点关系 CSV
        event_to_detail_relationships_csv_filename = os.path.join(self.temp_csv_dir, f"event_to_details_{character_id}.csv")

        # --- 收集所有需要创建节点的数据 ---
        all_nodes_to_create = []

        # 1. 添加主角色和关联角色 (Character 节点)
        all_character_ids = set()
        all_character_ids.add(main_character.get('id'))
        for rc in related_characters:
            all_character_ids.add(rc.get('id'))

        character_map = {}
        character_map[main_character.get('id')] = main_character
        for rc in related_characters:
            character_map[rc.get('id')] = rc

        # --- 保存节点 CSV (Character, Event, 其他实体) ---
        with open(nodes_filename, 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = [
                'node_id', 'label', 'name', 'app_id', 'age', 'gender', 'occupation', 'hobby', 'skill',
                'values', 'living_habit', 'dislike', 'language_style', 'appearance', 'family_status',
                'education', 'social_pattern', 'favorite_thing', 'usual_place', 'past_experience',
                'speech_style', 'openness', 'conscientiousness', 'extraversion', 'agreeableness', 'neuroticism',
                'is_protagonist', 'entity_type', 'description', 'event_title', 'event_content', 'event_age', 'event_importance', 'properties',
                'type', # 添加 'type' 字段
                # **修改：添加 'relationship_to_protagonist' 字段到节点 CSV (可选，用于调试或更复杂的节点属性)**
                'relationship_to_protagonist'
            ]
            # **关键修改：添加 quoting=csv.QUOTE_ALL**
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames, quoting=csv.QUOTE_ALL, quotechar='"')
            writer.writeheader()

            # 1. 写入所有角色节点 (去重后)
            for char_id in all_character_ids:
                char_data = character_map.get(char_id)
                if not char_data:
                    continue

                # **重要：对包含复杂结构的字段进行预处理，使用 Base64 编码**
                # 例如 personality 字段
                personality_dict = char_data.get("personality", {})
                # 确保 personality 是一个字典
                if not isinstance(personality_dict, dict):
                    personality_dict = {}
                json_str_personality = json.dumps(personality_dict, ensure_ascii=False)
                personality_base64 = base64.b64encode(json_str_personality.encode('utf-8')).decode('utf-8')

                node_props = {
                    "node_id": char_data.get("id"),
                    "label": "Character",
                    "name": char_data.get("name", ""),
                    "app_id": char_data.get("id"),
                    "age": char_data.get("age"),
                    "gender": char_data.get("gender", ""),
                    "occupation": char_data.get("occupation", ""),
                    "hobby": char_data.get("hobby", ""),
                    "skill": char_data.get("skill", ""),
                    "values": char_data.get("values", ""),
                    "living_habit": char_data.get("living_habit", ""),
                    "dislike": char_data.get("dislike", ""),
                    "language_style": char_data.get("language_style", ""),
                    "appearance": char_data.get("appearance", ""),
                    "family_status": char_data.get("family_status", ""),
                    "education": char_data.get("education", ""),
                    "social_pattern": char_data.get("social_pattern", ""),
                    "favorite_thing": char_data.get("favorite_thing", ""),
                    "usual_place": char_data.get("usual_place", ""),
                    "past_experience": char_data.get("past_experience", ""),
                    "speech_style": char_data.get("speech_style", ""),
                    "openness": personality_dict.get("openness", 50),
                    "conscientiousness": personality_dict.get("conscientiousness", 50),
                    "extraversion": personality_dict.get("extraversion", 50),
                    "agreeableness": personality_dict.get("agreeableness", 50),
                    "neuroticism": personality_dict.get("neuroticism", 50),
                    "is_protagonist": True if char_id == character_id else False,
                    "entity_type": "Character",
                    "description": char_data.get("background", ""), # 或者其他描述字段
                    # **修改：为 Character 节点设置 event 相关字段为空**
                    "event_title": "",
                    "event_content": "",
                    "event_age": "",
                    "event_importance": "",
                    # **修改：使用 Base64 编码的 properties**
                    "properties": personality_base64, # 将 personality 作为 properties 存储
                    "type": "Character", # 添加 type 字段
                    # **修改：添加 'relationship_to_protagonist' 字段**
                    "relationship_to_protagonist": char_data.get("relationship_to_protagonist", "未知")
                }
                writer.writerow(node_props)

            # 2. 写入所有记忆作为 Event 节点 (来自结构化对话场景)
            for memory in memories: # **关键修改：直接遍历结构化对话场景**
                event_node_id = memory.get('id') or str(uuid.uuid4()) # 使用 memory 的 id 作为 Event 节点的 id
                # **修改：使用 memory 中的特定字段作为事件节点的原始内容**
                # 假设 memory 包含 'dialogue_content', 'context', 'title' 等
                original_content_for_event = memory.get('dialogue_content', memory.get('content', memory.get('original_context', '')))
                event_age = memory.get('time_at_occurrence', memory.get('time', {}).get('age', '')) # **关键修改：使用新字段**

                event_props = {
                    'node_id': event_node_id,
                    'label': 'Event',
                    'name': memory.get('title', ''),
                    'app_id': memory.get('id', ''),
                    'entity_type': 'Event',
                    'event_title': memory.get('title', ''),
                    'event_content': original_content_for_event,
                    'event_age': event_age,
                    'event_importance': memory.get('importance', {}).get('score', ''), # 假设 importance 存在于 memory 中
                    'description': original_content_for_event[:100], # **使用 original_content**
                    # **重要：处理可能包含复杂结构的字段，如 emotion, importance 等**
                    # 将它们作为 JSON 字符串，然后进行 Base64 编码
                    'properties': base64.b64encode(json.dumps({
                        'time': memory.get('time', {}),
                        'emotion': memory.get('emotion', {}), # 假设 emotion 存在于 memory 中
                        'importance': memory.get('importance', {}),
                        'behavior_impact': memory.get('behavior_impact', {}), # 假设 behavior_impact 存在于 memory 中
                        'trigger_system': memory.get('trigger_system', {}), # 假设 trigger_system 存在于 memory 中
                        'memory_distortion': memory.get('memory_distortion', {}), # 假设 memory_distortion 存在于 memory 中
                        # ... 可以添加其他需要的字段 ...
                    }, ensure_ascii=False).encode('utf-8')).decode('utf-8'),
                    'type': 'Event' # 添加 type 字段
                }
                writer.writerow(event_props)

            # 3. 写入非人物实体节点 (从参数 entities 提取 - 可选)
            entity_node_map = {}
            for entity in entities: # **关键修改：只处理传入的 entities**
                ent_node_id = entity.get('app_id') or str(uuid.uuid4())
                entity_node_map[entity.get('app_id')] = ent_node_id
                ent_props = {
                    'node_id': ent_node_id,
                    'label': entity.get('type', 'Entity').capitalize(), # 例如 'Place', 'Concept'
                    'name': entity.get('name', ''),
                    'app_id': entity.get('app_id', ''),
                    'entity_type': entity.get('type', 'Entity').upper(),
                    'description': entity.get('description', ''),
                    'properties': base64.b64encode(json.dumps(entity.get('properties', {}), ensure_ascii=False).encode('utf-8')).decode('utf-8'),
                    'type': entity.get('type', 'Entity').upper() # 添加 type 字段
                }
                writer.writerow(ent_props)

        print(f"- 节点 CSV 文件已保存至: {nodes_filename} -")

        # --- 新增：保存细粒度节点 CSV (Places, Times, Actions, Actors, Emotions, Items) ---
        # **关键修改：直接从 memories 列表中提取这些信息**
        # 集合用于去重
        all_places = set()
        all_times = set()
        all_actions = set()
        all_actors = set()
        all_emotions = set()
        all_items = set()

        for memory in memories:
            all_places.update(memory.get('locations', [])) # **关键修改：直接获取**
            all_times.update(memory.get('times', [])) # **关键修改：直接获取**
            all_actions.update(memory.get('actions', [])) # **关键修改：直接获取**
            all_actors.update(memory.get('actors', [])) # **关键修改：直接获取**
            all_emotions.update(memory.get('emotions', [])) # **关键修改：直接获取**
            all_items.update(memory.get('items', [])) # **关键修改：直接获取**

        # 写入 Places
        with open(places_filename, 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = ['app_id', 'name', 'type', 'description', 'properties']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames, quoting=csv.QUOTE_ALL, quotechar='"')
            writer.writeheader()
            for place_name in all_places:
                if not place_name: continue
                place_app_id = f"place_{abs(hash(place_name))}"
                writer.writerow({
                    'app_id': place_app_id,
                    'name': place_name,
                    'type': 'Place',
                    'description': f'A place mentioned in a memory: {place_name}',
                    'properties': base64.b64encode(json.dumps({}, ensure_ascii=False).encode('utf-8')).decode('utf-8')
                })
        print(f"- 地点节点 CSV 文件已保存至: {places_filename} -")

        # 写入 Times
        with open(times_filename, 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = ['app_id', 'name', 'type', 'description', 'properties']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames, quoting=csv.QUOTE_ALL, quotechar='"')
            writer.writeheader()
            for time_desc in all_times:
                if not time_desc: continue
                time_app_id = f"time_{abs(hash(time_desc))}"
                writer.writerow({
                    'app_id': time_app_id,
                    'name': time_desc,
                    'type': 'Time',
                    'description': f'A time mentioned in a memory: {time_desc}',
                    'properties': base64.b64encode(json.dumps({}, ensure_ascii=False).encode('utf-8')).decode('utf-8')
                })
        print(f"- 时间节点 CSV 文件已保存至: {times_filename} -")

        # 写入 Actions
        with open(actions_filename, 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = ['app_id', 'name', 'type', 'description', 'properties']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames, quoting=csv.QUOTE_ALL, quotechar='"')
            writer.writeheader()
            for action_desc in all_actions:
                if not action_desc: continue
                action_app_id = f"action_{abs(hash(action_desc))}"
                writer.writerow({
                    'app_id': action_app_id,
                    'name': action_desc,
                    'type': 'Action',
                    'description': f'An action mentioned in a memory: {action_desc}',
                    'properties': base64.b64encode(json.dumps({}, ensure_ascii=False).encode('utf-8')).decode('utf-8')
                })
        print(f"- 动作节点 CSV 文件已保存至: {actions_filename} -")

        # 写入 Actors
        with open(actors_filename, 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = ['app_id', 'name', 'type', 'description', 'properties']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames, quoting=csv.QUOTE_ALL, quotechar='"')
            writer.writeheader()
            for actor_name in all_actors:
                if not actor_name: continue
                # 注意：actors 可能包含角色的 app_id 或姓名
                # 如果 actor_name 是一个已知的角色 ID，则应连接到 Character 节点
                # 否则，可以将其视为一个 Actor 节点
                # 这里假设 actor_name 是一个名称，我们创建一个 Actor 节点
                actor_app_id = f"actor_{abs(hash(actor_name))}"
                writer.writerow({
                    'app_id': actor_app_id,
                    'name': actor_name,
                    'type': 'Actor',
                    'description': f'An actor mentioned in a memory: {actor_name}',
                    'properties': base64.b64encode(json.dumps({}, ensure_ascii=False).encode('utf-8')).decode('utf-8')
                })
        print(f"- 参与者节点 CSV 文件已保存至: {actors_filename} -")

        # 写入 Emotions
        with open(emotions_filename, 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = ['app_id', 'name', 'type', 'description', 'properties']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames, quoting=csv.QUOTE_ALL, quotechar='"')
            writer.writeheader()
            for emotion_desc in all_emotions:
                if not emotion_desc: continue
                emotion_app_id = f"emotion_{abs(hash(emotion_desc))}"
                writer.writerow({
                    'app_id': emotion_app_id,
                    'name': emotion_desc,
                    'type': 'Emotion',
                    'description': f'An emotion mentioned in a memory: {emotion_desc}',
                    'properties': base64.b64encode(json.dumps({}, ensure_ascii=False).encode('utf-8')).decode('utf-8')
                })
        print(f"- 情感节点 CSV 文件已保存至: {emotions_filename} -")

        # 写入 Items
        with open(items_filename, 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = ['app_id', 'name', 'type', 'description', 'properties']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames, quoting=csv.QUOTE_ALL, quotechar='"')
            writer.writeheader()
            for item_name in all_items:
                if not item_name: continue
                item_app_id = f"item_{abs(hash(item_name))}"
                writer.writerow({
                    'app_id': item_app_id,
                    'name': item_name,
                    'type': 'Item',
                    'description': f'An item mentioned in a memory: {item_name}',
                    'properties': base64.b64encode(json.dumps({}, ensure_ascii=False).encode('utf-8')).decode('utf-8')
                })
        print(f"- 物品节点 CSV 文件已保存至: {items_filename} -")


        # --- 保存非人物实体到事件的关系 CSV (可选 - 处理传入的 relationships) ---
        # **关键修改：只处理传入的 relationships 列表**
        with open(relationships_filename, 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = ['relation_id', 'entity_app_id', 'event_app_id', 'relationship_type', 'properties']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames, quoting=csv.QUOTE_ALL, quotechar='"')
            writer.writeheader()
            for rel in relationships: # **关键修改：直接遍历传入的关系**
                writer.writerow(rel)
        print(f"- 非人物实体-事件关系 CSV 文件已保存至: {relationships_filename} -")


        # --- 保存 Event 衍生节点到事件的关系 CSV (NEW) ---
        # **关键修改：直接使用 memories 中的字段建立关系**
        # 准备存储关系的列表
        all_event_to_detail_relationships = []

        # 遍历所有记忆（事件）
        for memory in memories:
            event_app_id = memory.get('id')
            if not event_app_id:
                continue

            # 从 memory 中直接提取细粒度信息并建立关系
            # - 提取并处理地点 -
            for loc_name in memory.get('locations', []): # **关键修改：直接获取**
                if not loc_name: continue
                place_app_id = f"place_{abs(hash(loc_name))}"
                all_event_to_detail_relationships.append({
                    'event_app_id': event_app_id,
                    'detail_app_id': place_app_id,
                    'relationship_type': 'OCCURRED_AT' # 或 'LOCATION'
                })

            # - 提取并处理时间 -
            for time_desc in memory.get('times', []): # **关键修改：直接获取**
                if not time_desc: continue
                time_app_id = f"time_{abs(hash(time_desc))}"
                all_event_to_detail_relationships.append({
                    'event_app_id': event_app_id,
                    'detail_app_id': time_app_id,
                    'relationship_type': 'AT_TIME' # 或 'TIME'
                })

            # - 提取并处理动作 -
            for action_desc in memory.get('actions', []): # **关键修改：直接获取**
                if not action_desc: continue
                action_app_id = f"action_{abs(hash(action_desc))}"
                all_event_to_detail_relationships.append({
                    'event_app_id': event_app_id,
                    'detail_app_id': action_app_id,
                    'relationship_type': 'INVOLVES_ACTION' # 或 'ACTION'
                })

            # - 提取并处理参与者 (Actors) -
            for actor_name in memory.get('actors', []): # **关键修改：直接获取**
                if not actor_name: continue
                actor_app_id = f"actor_{abs(hash(actor_name))}"
                all_event_to_detail_relationships.append({
                    'event_app_id': event_app_id,
                    'detail_app_id': actor_app_id,
                    'relationship_type': 'INVOLVES_ACTOR' # 或 'ACTOR'
                })

            # - 提取并处理情感 -
            for emotion_desc in memory.get('emotions', []): # **关键修改：直接获取**
                if not emotion_desc: continue
                emotion_app_id = f"emotion_{abs(hash(emotion_desc))}"
                all_event_to_detail_relationships.append({
                    'event_app_id': event_app_id,
                    'detail_app_id': emotion_app_id,
                    'relationship_type': 'HAS_EMOTION' # 或 'EMOTION'
                })

            # - 提取并处理物品 -
            for item_name in memory.get('items', []): # **关键修改：直接获取**
                if not item_name: continue
                item_app_id = f"item_{abs(hash(item_name))}"
                all_event_to_detail_relationships.append({
                    'event_app_id': event_app_id,
                    'detail_app_id': item_app_id,
                    'relationship_type': 'USES_ITEM' # 或 'ITEM'
                })

        # - 写入 Event -> Detail 关系 CSV -
        with open(event_to_detail_relationships_csv_filename, 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = ['event_app_id', 'detail_app_id', 'relationship_type']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames, quoting=csv.QUOTE_ALL, quotechar='"')
            writer.writeheader()
            for rel in all_event_to_detail_relationships:
                writer.writerow(rel)
        print(f"- 事件-衍生节点关系 CSV 文件已保存至: {event_to_detail_relationships_csv_filename} -")


        # --- 保存事件细节 CSV (可选 - 处理传入的 details) ---
        # **关键修改：只处理传入的 details 列表**
        details_filename = os.path.join(self.temp_csv_dir, f"event_details_{character_id}.csv")
        with open(details_filename, 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = ['detail_id', 'event_app_id', 'type', 'content', 'properties']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames, quoting=csv.QUOTE_ALL, quotechar='"')
            writer.writeheader()
            # 假设 memory 的 'details' 字段包含细粒度信息 (如果有的话)
            for memory in memories:
                event_app_id = memory.get('id')
                if not event_app_id:
                    continue
                # 提取事件细节（假设在memory的details字段中）
                details = memory.get('details', []) # 假设 memory 有 details 字段
                for detail in details:
                    detail_id = str(uuid.uuid4())
                    detail_props = {
                        'detail_id': detail_id,
                        'event_app_id': event_app_id,
                        'type': detail.get('type', 'DETAIL'),
                        'content': detail.get('content', '')
                    }
                    # 将 detail 中的其他动态属性放入 properties
                    dynamic_props = {k: v for k, v in detail.items() if k not in ['type', 'content', 'detail_id', 'event_app_id', 'properties']}
                    for k, v in dynamic_props.items():
                        if isinstance(v, (dict, list)):
                            dynamic_props[k] = json.dumps(v, ensure_ascii=False)
                    json_str = json.dumps(dynamic_props, ensure_ascii=False)
                    detail_props['properties'] = base64.b64encode(json_str.encode('utf-8')).decode('utf-8')
                    writer.writerow(detail_props)
        print(f"- 事件细节 CSV 文件已保存至: {details_filename} -")


        # --- 保存时间链 CSV (可选 - 基于 memory 的 age 排序) ---
        # **关键修改：处理包含中文单位的年龄字符串**
        temporal_chain_filename = os.path.join(self.temp_csv_dir, f"temporal_chain_{character_id}.csv")
        with open(temporal_chain_filename, 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = ['from_event_app_id', 'to_event_app_id', 'relationship_type', 'properties']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames, quoting=csv.QUOTE_ALL, quotechar='"')
            writer.writeheader()
            # 这里需要根据 memory 的时间顺序来建立事件间的时间链关系
            # 示例：简单的相邻事件链接 (按 memory 的 age 顺序)
            # **关键修改：排序依据改为 memory 的 age 字段，并处理字符串格式**
            # 定义一个辅助函数来提取年龄数字
            def extract_age_float(memory_item):
                time_str = memory_item.get('time_at_occurrence', memory_item.get('time', {}).get('age', '0'))
                # 使用正则表达式查找数字（包括小数）
                match = re.search(r'(\d+(?:\.\d+)?)', str(time_str))
                if match:
                    try:
                        return float(match.group(1))
                    except ValueError:
                        # 如果转换失败，返回 0 或其他默认值
                        return 0.0
                else:
                    # 如果没有找到数字，返回 0 或其他默认值
                    return 0.0

            # 使用辅助函数进行排序
            sorted_memories = sorted(memories, key=extract_age_float)
            for i in range(len(sorted_memories) - 1):
                from_event_id = sorted_memories[i].get('id')
                to_event_id = sorted_memories[i+1].get('id')
                if from_event_id and to_event_id:
                    writer.writerow({
                        'from_event_app_id': from_event_id,
                        'to_event_app_id': to_event_id,
                        'relationship_type': 'FOLLOWS',
                        'properties': base64.b64encode(json.dumps({}, ensure_ascii=False).encode('utf-8')).decode('utf-8')
                    })
        print(f"- 时间链 CSV 文件已保存至: {temporal_chain_filename} -")


        # --- 新增：保存主角到关联角色的关系 CSV ---
        # **关键修改：利用 related_characters 中的 'relationship_to_protagonist' 字段生成主角到关联角色的关系 CSV。**
        # 收集主角到关联角色的关系
        protagonist_to_related_rels = []
        protagonist_id = main_character.get('id')
        for rel_char in related_characters:
            rel_char_id = rel_char.get('id')
            # **关键修改：直接使用 'relationship_to_protagonist' 字段**
            rel_type_from_main = rel_char.get('relationship_to_protagonist', '关联角色')
            # 可以添加更多属性，如描述、强度等
            rel_description = f"{main_character.get('name')} 与 {rel_char.get('name')} 的关系是 {rel_type_from_main}"
            rel_strength = 70 # 可以根据具体逻辑计算或设置默认值

            protagonist_to_related_rels.append({
                'relationship_id': str(uuid.uuid4()), # 为关系生成唯一ID
                'from_character_app_id': protagonist_id,
                'to_character_app_id': rel_char_id,
                'relationship_type': rel_type_from_main, # 使用新字段值作为关系类型
                'description': rel_description,
                'strength': rel_strength,
                # 如果需要，可以添加更多属性到 properties
                'properties': base64.b64encode(json.dumps({
                    'source_relationship_field': 'relationship_to_protagonist',
                    'calculated_strength': rel_strength
                }, ensure_ascii=False).encode('utf-8')).decode('utf-8')
            })

        # 将主角到关联角色的关系与其他推断的关系合并
        all_char_to_char_relationships = protagonist_to_related_rels # 开始时只包含基于新字段的关系
        if character_to_character_relationships:
            all_char_to_char_relationships.extend(character_to_character_relationships) # 合并其他推断关系

        # 写入合并后的角色间关系 CSV
        with open(char_to_char_relationships_filename, 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = ['relationship_id', 'from_character_app_id', 'to_character_app_id', 'relationship_type', 'description', 'strength', 'properties']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames, quoting=csv.QUOTE_ALL, quotechar='"')
            writer.writeheader()
            for rel in all_char_to_char_relationships:
                writer.writerow(rel)
        print(f"- 角色间关系 CSV 文件已保存至: {char_to_char_relationships_filename} -", flush=True)
        # --- 结束新增 ---


        # 修改返回值，包含新增的文件名
        result = {
            "nodes_file": os.path.basename(nodes_filename),
            # "impressions_file": os.path.basename(impressions_filename), # 如果有印象节点
            "entity_event_relationships_file": os.path.basename(relationships_filename), # 旧的实体-事件关系
            "temporal_chain_file": os.path.basename(temporal_chain_filename),
            "details_file": os.path.basename(details_filename),
            "event_to_detail_relationships_file": os.path.basename(event_to_detail_relationships_csv_filename), # 新增：事件-衍生节点关系
            "places_file": os.path.basename(places_filename), # 新增
            "times_file": os.path.basename(times_filename), # 新增
            "actions_file": os.path.basename(actions_filename), # 新增
            "actors_file": os.path.basename(actors_filename), # 新增
            "emotions_file": os.path.basename(emotions_filename), # 新增
            "items_file": os.path.basename(items_filename), # 新增
            # **修改：返回新的角色间关系文件名**
            "char_to_char_relationships_file": os.path.basename(char_to_char_relationships_filename),
        }

        return result

    # --- 在数据导入后，计算并存储向量的方法 ---
    def compute_and_store_vectors(self):
        """
        在所有节点和关系导入 Neo4j 后，计算 Event 和 Impression 节点的向量并存储。
        """
        print("--- 开始计算并存储向量 ---",flush=True)
        with self.driver.session(database=self.database) as session:
            try:
                # 1. 为 Event 节点计算并存储向量
                # print("  - 为 Event 节点计算向量...")
                # result = session.run("MATCH (e:Event) WHERE e.event_content IS NOT NULL RETURN e.app_id AS app_id, e.event_content AS content")
                # events_to_embed = [(record["app_id"], record["content"]) for record in result]
                # print(f"    找到 {len(events_to_embed)} 个 Event 节点需要计算向量")

                # batch_size = 100
                # for i in range(0, len(events_to_embed), batch_size):
                #     batch = events_to_embed[i:i+batch_size]
                #     contents = [item[1] for item in batch]
                #     try:
                #         embeddings_list = self.embeddings.embed_documents(contents)
                #         for j, (app_id, content) in enumerate(batch):
                #             embedding_vector = embeddings_list[j]
                #             session.run(
                #                 "MATCH (e:Event {app_id: $app_id}) SET e.event_embedding = $embedding",
                #                 app_id=app_id,
                #                 embedding=embedding_vector
                #             )
                #         print(f"    批次 {i//batch_size + 1} 的 {len(batch)} 个 Event 向量已存储")
                #     except Exception as e:
                #         print(f"    批次 {i//batch_size + 1} 计算向量失败: {e}")
                #         # 可能需要重试逻辑或跳过失败项

                # 2. 为 Impression 节点计算并存储向量
                print("  - 为 Impression 节点计算向量...")
                result = session.run("MATCH (i:Impression) WHERE i.impression_content IS NOT NULL RETURN i.app_id AS app_id, i.impression_content AS content")
                impressions_to_embed = [(record["app_id"], record["content"]) for record in result]
                print(f"    找到 {len(impressions_to_embed)} 个 Impression 节点需要计算向量")

                batch_size = 100
                for i in range(0, len(impressions_to_embed), batch_size):
                    batch = impressions_to_embed[i:i+batch_size]
                    contents = [item[1] for item in batch]
                    try:
                        embeddings_list = self.embeddings.embed_documents(contents)
                        for j, (app_id, content) in enumerate(batch):
                            embedding_vector = embeddings_list[j]
                            session.run(
                                "MATCH (i:Impression {app_id: $app_id}) SET i.impression_embedding = $embedding",
                                app_id=app_id,
                                embedding=embedding_vector
                            )
                        print(f"    批次 {i//batch_size + 1} 的 {len(batch)} 个 Impression 向量已存储")
                    except Exception as e:
                        print(f"    批次 {i//batch_size + 1} 计算向量失败: {e}")
                        # 可能需要重试逻辑或跳过失败项

            except Exception as e:
                print(f"--- 计算和存储向量失败: {e} ---")
                import traceback
                traceback.print_exc()
        print("--- 向量计算和存储完成 ---",flush=True)

    # --- 向量检索方法 ---
    # def semantic_search_events(self, query: str, k: int = 5) -> List[Dict[str, Any]]:
    #     """
    #     使用 Neo4jVector 检索与查询语义相关的 Event 节点。
    #     """
    #     try:
    #         # 使用 Neo4jVector 进行相似度搜索
    #         # similarity_search 返回的是 Document 对象列表
    #         # similarity_search_with_score 返回 (Document, score) 元组列表
    #         docs_with_scores = self.neo4j_vector_events.similarity_search_with_score(query, k=k)
    #         results = []
    #         for doc, score in docs_with_scores:
    #             # doc.page_content 是节点的 text 属性（通常是 event_content）
    #             # doc.metadata 包含节点的其他属性
    #             node_data = doc.metadata
    #             # LangChain 的 retrieval_query 可能会将关联节点信息也放入 metadata
    #             # 需要根据 retrieval_query 的结构解析 metadata
    #             # 这里假设 metadata 直接包含了 e, i, c 字典
    #             event_data = node_data.get("e", {})
    #             impression_data = node_data.get("i", {})
    #             character_data = node_data.get("c", {})
    #             results.append({
    #                 "event": event_data,
    #                 "impression": impression_data,
    #                 "character": character_data,
    #                 "relevance_score": 1 - score, # 转换为相关性分数 (1 - 距离)
    #                 "source": "vector_event"
    #             })
    #         print(f"--- 向量搜索 Event 返回 {len(results)} 条记录 ---")
    #         return results
    #     except Exception as e:
    #         print(f"--- Event 向量搜索失败: {e} ---")
    #         import traceback
    #         traceback.print_exc()
    #         return []

    def semantic_search_impressions(self, query: str, k: int = 5) -> List[Dict[str, Any]]:
        """
        使用 Neo4jVector 检索与查询语义相关的 Impression 节点。
        """
        try:
            docs_with_scores = self.neo4j_vector_impressions.similarity_search_with_score(query, k=k)
            results = []
            for doc, score in docs_with_scores:
                node_data = doc.metadata
                impression_data = node_data.get("i", {})
                event_data = node_data.get("e", {})
                # character_data = node_data.get("c", {}) # 如果 retrieval_query 包含
                results.append({
                    "impression": impression_data,
                    "event": event_data,
                    # "character": character_data, # 如果 retrieval_query 包含
                    "relevance_score": 1 - score,
                    "source": "vector_impression"
                })
            print(f"--- 向量搜索 Impression 返回 {len(results)} 条记录 ---")
            return results
        except Exception as e:
            print(f"--- Impression 向量搜索失败: {e} ---")
            import traceback
            traceback.print_exc()
            return []

    def import_nodes_from_csv(self, csv_filename: str) -> bool:
        if not csv_filename or not os.path.exists(os.path.join(self.temp_csv_dir, csv_filename)):
            print(f"错误：CSV 文件不存在: {os.path.join(self.temp_csv_dir, csv_filename)}")
            return False
        print(f"--- 开始从统一 CSV 文件导入节点: {csv_filename} ---",flush=True)
        neo4j_import_path = f"/var/lib/neo4j/import/{csv_filename}"

        with self.driver.session(database=self.database) as session:
            try:
                # 1. 创建节点 (Character, Event, Place, Time, Action, Actor, Emotion, Item)
                query_create = f"""
                LOAD CSV WITH HEADERS FROM 'file://{neo4j_import_path}' AS row
                CALL (row) {{
                    WITH row
                    // 根据 label 字段创建不同类型的节点
                    FOREACH (_ IN CASE WHEN row.label = 'Character' THEN [1] ELSE [] END |
                        MERGE (c:Character {{app_id: row.app_id}})
                        SET c += row
                    )
                    FOREACH (_ IN CASE WHEN row.label = 'Event' THEN [1] ELSE [] END |
                        MERGE (e:Event {{app_id: row.app_id}})
                        SET e += row
                    )
                    FOREACH (_ IN CASE WHEN row.label = 'Place' THEN [1] ELSE [] END |
                        MERGE (p:Place {{app_id: row.app_id}})
                        SET p.name = row.name
                    )
                    FOREACH (_ IN CASE WHEN row.label = 'Time' THEN [1] ELSE [] END |
                        MERGE (t:Time {{app_id: row.app_id}})
                        SET t.description = row.description
                    )
                    FOREACH (_ IN CASE WHEN row.label = 'Action' THEN [1] ELSE [] END |
                        MERGE (a:Action {{app_id: row.app_id}})
                        SET a.description = row.description
                    )
                    FOREACH (_ IN CASE WHEN row.label = 'Actor' THEN [1] ELSE [] END |
                        MERGE (act:Actor {{app_id: row.app_id}})
                        SET act.name = row.name
                    )
                    FOREACH (_ IN CASE WHEN row.label = 'Emotion' THEN [1] ELSE [] END |
                        MERGE (em:Emotion {{app_id: row.app_id}})
                        SET em.description = row.description
                    )
                    FOREACH (_ IN CASE WHEN row.label = 'Item' THEN [1] ELSE [] END |
                        MERGE (i:Item {{app_id: row.app_id}})
                        SET i.name = row.name
                    )
                }}
                """
                session.run(query_create)
                # ... (获取导入数量的逻辑可以保留，但需要区分不同标签) ...
                print(f"--- 成功从 CSV {csv_filename} 导入节点 ---",flush=True)
                return True
            except Exception as e:
                print(f"从 CSV {csv_filename} 导入节点失败: {e}")
                import traceback
                traceback.print_exc()
                return False

    def import_event_details_from_csv(self, csv_filename: str) -> bool:
        if not csv_filename or not os.path.exists(os.path.join(self.temp_csv_dir, csv_filename)):
            print(f"错误：CSV 文件不存在: {os.path.join(self.temp_csv_dir, csv_filename)}")
            return False

        print(f"--- 开始从 CSV 文件导入事件细节: {csv_filename} ---",flush=True)
        neo4j_import_path = f"/var/lib/neo4j/import/{csv_filename}"

        with self.driver.session(database=self.database) as session:
            try:
                # 1. 创建细节节点
                query_create = f"""
                LOAD CSV WITH HEADERS FROM 'file://{neo4j_import_path}' AS row
                CALL (row) {{
                    WITH row
                    CALL apoc.create.node([row.type], {{
                        app_id: row.detail_id,
                        content: row.content,
                        event_app_id: row.event_app_id,
                        properties: row.properties
                    }}) YIELD node
                    RETURN node
                }}
                RETURN count(node) AS createdDetails;
                """
                result_create = session.run(query_create)
                count_create = result_create.single()["createdDetails"]
                print(f"--- 成功创建 {count_create} 个事件细节节点 ---",flush=True)

                # 2. 连接事件到细节
                query_connect = f"""
                LOAD CSV WITH HEADERS FROM 'file://{neo4j_import_path}' AS row
                MATCH (e:Event {{app_id: row.event_app_id}}), (d) WHERE d.app_id = row.detail_id
                CALL apoc.create.relationship(e, 'HAS_DETAIL', {{}}, d) YIELD rel
                RETURN count(rel) AS connectedDetails;
                """
                result_connect = session.run(query_connect)
                count_connect = result_connect.single()["connectedDetails"]
                print(f"--- 成功连接 {count_connect} 条事件-细节关系 ---",flush=True)
                return True
            except Exception as e:
                print(f"从 CSV {csv_filename} 导入事件细节失败: {e}")
                return False

    def import_impressions_from_csv(self, csv_filename: str) -> bool:
        if not csv_filename or not os.path.exists(os.path.join(self.temp_csv_dir, csv_filename)):
            print(f"错误：CSV 文件不存在: {os.path.join(self.temp_csv_dir, csv_filename)}")
            return False
        print(f"--- 开始从 CSV 文件导入印象关系: {csv_filename} ---",flush=True)
        neo4j_import_path = f"/var/lib/neo4j/import/{csv_filename}"

        with self.driver.session(database=self.database) as session:
            try:
                # 1. 创建印象节点 (包含 properties)
                query_create = f"""
                LOAD CSV WITH HEADERS FROM 'file://{neo4j_import_path}' AS row
                CALL (row) {{
                    WITH row
                    CALL apoc.create.node(['Impression'], {{
                        app_id: row.impression_id,
                        impression_content: row.impression_content,
                        strength: toInteger(row.strength),
                        timestamp: row.timestamp,
                        properties: row.properties,
                        remembered_details_json: row.remembered_details_json // 添加这个字段
                    }}) YIELD node
                    RETURN node
                }}
                RETURN count(node) AS createdImpressions;
                """
                result_create = session.run(query_create)
                count_create = result_create.single()["createdImpressions"]
                print(f"--- 成功创建 {count_create} 个印象节点 ---",flush=True)

                # 2. 连接 Character -> Impression -> Event
                query_connect = f"""
                LOAD CSV WITH HEADERS FROM 'file://{neo4j_import_path}' AS row
                MATCH (c:Character {{app_id: row.character_app_id}}), (i:Impression {{app_id: row.impression_id}}), (e:Event {{app_id: row.event_app_id}})
                CALL apoc.create.relationship(c, 'HAS_IMPRESSION', {{}}, i) YIELD rel AS rel1
                CALL apoc.create.relationship(i, 'OF_EVENT', {{}}, e) YIELD rel AS rel2
                RETURN count(rel1) AS connectedCharacterToImpression, count(rel2) AS connectedImpressionToEvent;
                """
                result_connect = session.run(query_connect)
                counts = result_connect.single()
                print(f"--- 成功连接 {counts['connectedCharacterToImpression']} 条 Character->Impression 关系 ---",flush=True)
                print(f"--- 成功连接 {counts['connectedImpressionToEvent']} 条 Impression->Event 关系 ---",flush=True)

            except Exception as e:
                print(f"从 CSV {csv_filename} 导入印象关系失败: {e}")
                import traceback
                traceback.print_exc()
                return False

        # --- 新增：导入印象与细节节点的关系 ---
        print("--- 开始建立 Impression -> Detail 关系 ---",flush=True)
        success_details = self._connect_impressions_to_details()
        if success_details:
            print("--- Impression -> Detail 关系建立成功 ---",flush=True)
        else:
            print("--- Impression -> Detail 关系建立失败 ---",flush=True)
            return False # 或者可以选择不返回 False，因为基本的 Impression 节点和 C->I->E 关系已建立
        # ---

        return True

    def import_entity_event_relationships_from_csv(self, csv_filename: str) -> bool:
        if not csv_filename or not os.path.exists(os.path.join(self.temp_csv_dir, csv_filename)):
            print(f"错误：CSV 文件不存在: {os.path.join(self.temp_csv_dir, csv_filename)}")
            return False

        print(f"--- 开始从 CSV 文件导入实体-事件关系: {csv_filename} ---",flush=True)
        neo4j_import_path = f"/var/lib/neo4j/import/{csv_filename}"

        with self.driver.session(database=self.database) as session:
            try:
                # 1. 创建关系 (Event -> Detail)
                query_create = f"""
                LOAD CSV WITH HEADERS FROM 'file://{neo4j_import_path}' AS row
                CALL (row) {{
                    WITH row
                    MATCH (e:Event {{app_id: row.event_app_id}})
                    // 根据 detail_app_id 的前缀判断节点类型并连接
                    FOREACH (_ IN CASE row.detail_app_id STARTS WITH 'place_' WHEN true THEN 1 ELSE 0 END |
                        MERGE (d:Place {{app_id: row.detail_app_id}})
                        MERGE (e)-[:OCCURRED_AT]->(d)
                    )
                    FOREACH (_ IN CASE row.detail_app_id STARTS WITH 'time_' WHEN true THEN 1 ELSE 0 END |
                        MERGE (d:Time {{app_id: row.detail_app_id}})
                        MERGE (e)-[:AT_TIME]->(d)
                    )
                    FOREACH (_ IN CASE row.detail_app_id STARTS WITH 'action_' WHEN true THEN 1 ELSE 0 END |
                        MERGE (d:Action {{app_id: row.detail_app_id}})
                        MERGE (e)-[:INVOLVES_ACTION]->(d)
                    )
                    FOREACH (_ IN CASE row.detail_app_id STARTS WITH 'actor_' WHEN true THEN 1 ELSE 0 END |
                        MERGE (d:Actor {{app_id: row.detail_app_id}})
                        MERGE (e)-[:INVOLVES_ACTOR]->(d)
                    )
                    FOREACH (_ IN CASE row.detail_app_id STARTS WITH 'emotion_' WHEN true THEN 1 ELSE 0 END |
                        MERGE (d:Emotion {{app_id: row.detail_app_id}})
                        MERGE (e)-[:HAS_EMOTION]->(d)
                    )
                    FOREACH (_ IN CASE row.detail_app_id STARTS WITH 'item_' WHEN true THEN 1 ELSE 0 END |
                        MERGE (d:Item {{app_id: row.detail_app_id}})
                        MERGE (e)-[:USES_ITEM]->(d)
                    )
                }}
                """
                session.run(query_create)
                print(f"--- 成功从 CSV {csv_filename} 导入事件-衍生节点关系 ---",flush=True)
                return True
            except Exception as e:
                print(f"从 CSV {csv_filename} 导入事件-衍生节点关系失败: {e}",flush=True)
                import traceback
                traceback.print_exc()
                return False

    def import_temporal_chain_from_csv(self, csv_filename: str) -> bool:
        if not csv_filename or not os.path.exists(os.path.join(self.temp_csv_dir, csv_filename)):
            print(f"错误：CSV 文件不存在: {os.path.join(self.temp_csv_dir, csv_filename)}")
            return False

        print(f"--- 开始从 CSV 文件导入时间链: {csv_filename} ---",flush=True)
        neo4j_import_path = f"/var/lib/neo4j/import/{csv_filename}"

        with self.driver.session(database=self.database) as session:
            try:
                query = f"""
                LOAD CSV WITH HEADERS FROM 'file://{neo4j_import_path}' AS row
                MATCH (e1:Event {{app_id: row.current_event_app_id}}), (e2:Event {{app_id: row.next_event_app_id}})
                CALL apoc.create.relationship(e1, 'FOLLOWS', {{}}, e2) YIELD rel
                RETURN count(rel) AS importedChains;
                """
                result = session.run(query)
                count = result.single()["importedChains"]
                print(f"--- 成功从 CSV {csv_filename} 导入 {count} 条时间链关系 ---",flush=True)
                return True
            except Exception as e:
                print(f"从 CSV {csv_filename} 导入时间链失败: {e}",flush=True)
                return False

    def import_character_to_character_relationships_from_csv(self, csv_filename: str) -> bool:
        if not csv_filename or not os.path.exists(os.path.join(self.temp_csv_dir, csv_filename)):
            print(f"错误：CSV 文件不存在: {os.path.join(self.temp_csv_dir, csv_filename)}")
            return False
        print(f"--- 开始从 CSV 文件导入角色间关系: {csv_filename} ---",flush=True)
        neo4j_import_path = f"/var/lib/neo4j/import/{csv_filename}"
        with self.driver.session(database=self.database) as session:
            try:
                query = f"""
                LOAD CSV WITH HEADERS FROM 'file://{neo4j_import_path}' AS row
                CALL (row) {{
                    WITH row
                    // 确保两端的角色节点存在
                    MERGE (from_char:Character {{app_id: row.from_character_app_id}})
                    MERGE (to_char:Character {{app_id: row.to_character_app_id}})
                    // 创建或更新关系
                    MERGE (from_char)-[r:HAS_RELATIONSHIP {{to_character_app_id: row.to_character_app_id}}]->(to_char)
                    SET r.type = row.relationship_type,
                        r.description = row.description,
                        r.strength = toInteger(row.strength),
                        r.last_updated = $timestamp,
                        r.properties = row.properties
                }}
                RETURN count(*) AS importedRelationships; /* 使用 count(*) 替代 count(r) */
                """
                result = session.run(query, timestamp=datetime.now().isoformat())
                count = result.single()["importedRelationships"]
                print(f"--- 成功从 CSV {csv_filename} 导入 {count} 条角色间关系 ---",flush=True)
                return True
            except Exception as e:
                print(f"使用复杂查询从 CSV {csv_filename} 导入角色间关系失败: {e}",flush=True)
                import traceback
                traceback.print_exc()
                # 尝试一个更简单的查询，如果上面的因为其他原因失败
                try:
                    query_simple = f"""
                    LOAD CSV WITH HEADERS FROM 'file://{neo4j_import_path}' AS row
                    MATCH (from_char:Character {{app_id: row.from_character_app_id}}), (to_char:Character {{app_id: row.to_character_app_id}})
                    CALL apoc.create.relationship(from_char, 'HAS_RELATIONSHIP', {{
                        type: row.relationship_type,
                        description: row.description,
                        strength: toInteger(row.strength),
                        last_updated: $timestamp,
                        properties: row.properties,
                        to_character_app_id: row.to_character_app_id
                    }}, to_char) YIELD rel
                    RETURN count(rel) AS importedRelationships;
                    """
                    result_simple = session.run(query_simple, timestamp=datetime.now().isoformat())
                    count_simple = result_simple.single()["importedRelationships"]
                    print(f"--- 使用简化查询成功从 CSV {csv_filename} 导入 {count_simple} 条角色间关系 ---",flush=True)
                    return True
                except Exception as e2:
                    print(f"简化查询从 CSV {csv_filename} 导入角色间关系也失败: {e2}",flush=True)
                    return False

    def get_relationship_between_characters(self, from_char_id: str, to_char_id: str) -> Optional[Dict[str, Any]]:
        """
        获取 from_char_id 角色对 to_char_id 角色的关系信息。
        """
        with self.driver.session(database=self.database) as session:
            try:
                result = session.run(
                    """
                    MATCH (c1:Character {app_id: $from_char_id})-[r:HAS_RELATIONSHIP {to_character_app_id: $to_char_id}]->(c2:Character {app_id: $to_char_id})
                    RETURN r
                    """,
                    from_char_id=from_char_id,
                    to_char_id=to_char_id
                )
                record = result.single()
                if record:
                    rel_props = dict(record["r"])
                    # 解析JSON字段（如果有的话）
                    for key, value in rel_props.items():
                        if isinstance(value, str):
                            try:
                                rel_props[key] = json.loads(value)
                            except (json.JSONDecodeError, TypeError):
                                pass
                    return rel_props
                else:
                    print(f"--- 未找到角色 {from_char_id} 对 {to_char_id} 的关系 ---",flush=True)
                    return None
            except Exception as e:
                print(f"获取角色 {from_char_id} -> {to_char_id} 的关系失败: {e}",flush=True)
                return None

    # --- 新增：处理印象内容的辅助方法 ---
    # --- 修改：根据角色性格、事件性质、时间因素处理印象内容的方法 ---
    def _process_impression_content_with_details(self, original_content: str, character_data: Dict[str, Any], memory_data: Dict[str, Any]) -> tuple[str, Dict[str, List[str]]]:
        """
        根据角色性格、事件性质、时间因素处理原始事件内容，生成角色对事件的印象内容和保留的细节列表。
        返回: (processed_content: str, remembered_details: Dict[str, List[str]])
        """
        # --- 提取原始细节信息 ---
        original_details = {
            'dialogues': memory_data.get('dialogues', []),
            'locations': memory_data.get('locations', []),
            'times': memory_data.get('times', []),
            'actions': memory_data.get('actions', []),
            'actors': memory_data.get('actors', []),
            'emotions': memory_data.get('emotions', []),
            'items': memory_data.get('items', [])
        }
        # ---


        # -------------------------- 1. 基础参数提取 --------------------------
        # 1.1 角色性格特质（基于大五人格模型，0-100分，从character_data获取）
        personality = character_data.get('personality', {})
        neuroticism = personality.get('neuroticism', 50)  # 神经质（情绪敏感度）
        conscientiousness = personality.get('conscientiousness', 50)  # 尽责性（严谨程度）
        openness = personality.get('openness', 50)  # 开放性（细节关注度）
        extraversion = personality.get('extraversion', 50)  # 外向性（大大咧咧程度）

        # 1.2 事件性质参数（从memory_data获取，0-10分）
        event_nature = memory_data.get('event_nature', {})
        emotional_intensity = event_nature.get('emotional_intensity', memory_data.get('emotion', {}).get('intensity', 5))
        importance = memory_data.get('importance', {}).get('score', 5)
        event_type = event_nature.get('type', 'neutral')

        # 1.3 时间参数（从memory_data获取）
        # **修改：优先使用 age 差计算天数，并优化日志逻辑**
        memory_time_info = memory_data.get('time', {})
        event_age_at_occurrence = memory_time_info.get('age', character_data.get('age', 0)) # 事件发生时角色年龄
        current_character_age = character_data.get('age', 0) # 角色当前设定年龄

        # 计算年龄差（年）
        age_difference_years = current_character_age - event_age_at_occurrence
        # 将年龄差转换为天数（假设一年约365天）
        # 这是一个估算，但比解析字符串更可靠
        calculated_days_from_age = max(0, int(age_difference_years * 365))
        print(f"  [DEBUG] 通过 age 字段计算时间衰减: 事件时年龄 {event_age_at_occurrence}, 当前年龄 {current_character_age}, 年龄差 {age_difference_years}, 估算天数 {calculated_days_from_age}",flush=True)

        # 如果通过 age 字段计算出的天数有效，则直接使用它
        if calculated_days_from_age > 0:
            days_passed = calculated_days_from_age
        else:
            # 如果 age 字段无效或导致天数 <= 0，尝试使用 specific_time_str
            specific_time_str = memory_time_info.get('specific', '').strip()
            if specific_time_str:
                try:
                    # 尝试解析 specific_time_str 为 datetime 对象
                    # 这里需要一个更灵活的解析器，但为了通用性，我们先尝试 ISO 格式
                    # 如果不是 ISO 格式，解析会失败，然后使用 importance 作为 fallback
                    # 尝试多种可能的格式，例如 "YYYY年MM月DD日 HH:MM:SS", "YYYY-MM-DD", "YYYY/MM/DD" 等
                    import dateutil.parser # 需要安装 python-dateutil: pip install python-dateutil
                    event_time = dateutil.parser.parse(specific_time_str)
                    current_time = datetime.now()
                    calculated_days_from_specific = (current_time - event_time).days
                    calculated_days_from_specific = max(0, calculated_days_from_specific) # 确保不为负数
                    print(f"  [DEBUG] 通过 specific_time '{specific_time_str}' 解析并计算天数: {calculated_days_from_specific}",flush=True)
                    days_passed = calculated_days_from_specific
                except (ValueError, TypeError) as e:
                    # 如果解析失败，使用 importance 估算作为备选
                    importance_score = memory_data.get('importance', {}).get('score', 5)
                    days_passed = max(0, int((10 - importance_score) * 365 / 9))
                    print(f"  [DEBUG] 无法解析 specific_time: '{specific_time_str}' (错误: {e}), 使用基于 importance ({importance_score}) 的估算: {days_passed} 天",flush=True)
            else:
                # 如果 specific_time_str 也为空，使用 importance 估算
                importance_score = memory_data.get('importance', {}).get('score', 5)
                days_passed = max(0, int((10 - importance_score) * 365 / 9))
                print(f"  [DEBUG] 未找到 specific_time, 且 age 字段无效，使用基于 importance ({importance_score}) 的估算: {days_passed} 天",flush=True)


        # -------------------------- 2. 核心影响指标计算 --------------------------
        # 2.1 性格特质量化：细致度（反应该人是否容易记住细节，0-1）
        detail_orientation = (
            0.3 * neuroticism +
            0.4 * conscientiousness +
            0.2 * openness -
            0.1 * extraversion
        ) / 100
        detail_orientation = max(0.1, min(detail_orientation, 0.9))

        # 2.2 事件性质量化：事件显著性（反应该事件本身是否容易被记住，0-1）
        event_saliency = (0.6 * emotional_intensity + 0.4 * importance) / 10
        event_saliency = max(0.1, min(event_saliency, 0.9))

        # 2.3 时间衰减量化：记忆留存衰减系数（0-1）
        time_decay = min(1.0, max(0.05, float(2.71828 **(-0.005 * days_passed))))

        # 2.4 综合记忆保留强度（决定整体细节保留比例，0-1）
        retention_strength = (0.5 * detail_orientation + 0.5 * event_saliency) * time_decay


        # -------------------------- 3. 内容基础压缩（基于保留强度） --------------------------
        compression_ratio = 0.05 + 0.95 * retention_strength
        original_length = len(original_content)
        base_retain_length = int(original_length * compression_ratio)
        base_retain_length = max(10, min(base_retain_length, original_length))

        core_pattern = re.compile(r'(.*?[，。；？！])')
        sentences = core_pattern.findall(original_content)
        if not sentences:
            sentences = [original_content]
        sorted_sentences = sorted(sentences, key=lambda x: len(x), reverse=True)  # 长句更可能含核心信息
        core_content = ''.join(sorted_sentences[:int(len(sentences)*compression_ratio)])
        compressed_content = core_content[:base_retain_length]


        # -------------------------- 4. 细节类型筛选（基于性格特质） --------------------------
        detail_types = {
            'dialogue': re.compile(r'“.*?”|‘.*?’'),
            'objects': re.compile(r'[那这某]+[一-龥a-zA-Z0-9]*[个只件台辆]{1}[一-龥a-zA-Z0-9]*'),
            'scene': re.compile(r'[早中晚昨今明]{1}.*?[处地场合]{1}|[0-9]{1,2}[点分]{1}'),
            'emotion': re.compile(r'[开心|难过|生气|害怕|惊讶]{1}')
        }

        detail_retain_probs = {
            'dialogue': 0.3 + detail_orientation * 0.6,
            'objects': 0.2 + detail_orientation * 0.7,
            'scene': 0.6 + detail_orientation * 0.3,
            'emotion': 0.4 + event_saliency * 0.5
        }

        filtered_content = compressed_content
        # **修改：记录哪些细节被过滤了**
        remembered_details = {
            'dialogues': [],
            'locations': [],
            'times': [],
            'actions': [],
            'actors': [],
            'emotions': [],
            'items': []
        }

        for detail_name, pattern in detail_types.items():
            # 从原始内容中提取当前类型的细节
            original_details_list = original_details.get(detail_name.replace('objects', 'items').replace('scene', 'locations'), [])
            if detail_retain_probs[detail_name] < 0.5:
                # 如果保留概率低，则进行过滤
                replacement = {
                    'dialogue': '说了些话',
                    'objects': '某个东西', # 对应 items
                    'scene': '某个时候', # 对应 locations
                    'emotion': '有些情绪'
                }[detail_name]
                filtered_content = pattern.sub(replacement, filtered_content)
                # **记录：哪些原始细节被过滤掉了，哪些留下了**
                # 这里我们简化处理，认为如果保留概率低，就可能过滤掉很多
                # 更精确的判断需要对比 filtered_content 和 original_content
                # 我们暂时先记录所有原始细节为 "可能被过滤"，稍后根据 distortion 进行调整
            else:
                # 如果保留概率高，则保留更多细节
                # **记录：哪些原始细节被保留了**
                if detail_name == 'dialogue':
                    remembered_details['dialogues'] = original_details.get('dialogues', [])
                elif detail_name == 'objects':
                    remembered_details['items'] = original_details.get('items', [])
                elif detail_name == 'scene':
                    remembered_details['locations'] = original_details.get('locations', [])
                elif detail_name == 'emotion':
                    remembered_details['emotions'] = original_details.get('emotions', [])


        # -------------------------- 5. 印象扭曲（基于性格与事件类型） --------------------------
        distortion_factor = (0.4 * neuroticism + 0.3 * (100 - conscientiousness) + 0.3 * openness) / 100

        distorted_content = filtered_content
        # **修改：根据扭曲情况调整 remembered_details**
        if distortion_factor > 0.6:
            if event_type == 'negative':
                distorted_content = re.sub(r'有点', '非常', distorted_content)
                distorted_content = re.sub(r'可能', '肯定', distorted_content)
            elif event_type == 'positive':
                distorted_content = re.sub(r'还不错', '特别好', distorted_content)
            distorted_content = f"好像{distorted_content}，我记得大概是这样..."
            # **扭曲严重，可能忘记更多细节，清空部分列表**
            # 这是一个简化的逻辑，可以根据具体扭曲内容进行更精确的判断
            if '日记本' in distorted_content:
                remembered_details['items'] = ['日记本'] # 假设扭曲后只记得日记本
            else:
                remembered_details['items'] = [] # 否则可能什么都记不清
            # 对其他类型也可以进行类似判断
        elif 0.3 < distortion_factor <= 0.6:
            if extraversion > 70:
                distorted_content = re.sub(r'，.*?[。；]', '。', distorted_content)
            # **中等扭曲，可能简化某些细节**
            # 例如，可能简化对话，保留地点
            if not re.search(r'“.*?”|‘.*?’', distorted_content):
                 remembered_details['dialogues'] = [] # 如果处理后没有对话标记，认为对话被遗忘

        # **再次检查原始细节是否在最终的 distorted_content 中**
        # 这是最精确的方法，但需要对每种类型进行关键词匹配
        # 例如，检查原始地点名是否在 distorted_content 中
        # 这里我们用一个简化的函数来模拟这个过程
        remembered_details = self._refine_remembered_details(distorted_content, original_details, remembered_details)

        return distorted_content, remembered_details

    def _refine_remembered_details(self, distorted_content: str, original_details: Dict[str, List[str]], current_remembered: Dict[str, List[str]]) -> Dict[str, List[str]]:
        """
        根据最终的 distorted_content 和原始的 original_details，
        精确判断哪些细节被记住了。
        根据 story_based_memory_generator.py 中的 Prompt，original_details 和 current_remembered
        中的值应为字符串列表。
        """
        refined = {}
        for detail_type, original_list in original_details.items():
            # current_list = current_remembered.get(detail_type, [])
            # 现在我们直接基于 original_list 和 distorted_content 来判断
            refined_list = []
            for item in original_list: # item 应该是字符串
                # 检查 item 是否在 distorted_content 中
                # 使用 lower() 以实现不区分大小写的匹配
                if isinstance(item, str) and item.lower() in distorted_content.lower():
                    refined_list.append(item)
                # 如果 item 不是字符串（理论上不应该发生），则跳过
            refined[detail_type] = refined_list
        return refined

    def _connect_impressions_to_details(self) -> bool:
        """
        从已导入的印象节点的 properties 中读取 remembered_details，
        并建立 Impression -> Detail 的关系。
        """
        with self.driver.session(database=self.database) as session:
            try:
                # Cypher 查询，获取所有印象节点及其 properties (Base64 编码)
                query = """
                MATCH (i:Impression)
                WHERE i.remembered_details_json IS NOT NULL // 确保有 details 信息
                RETURN i.app_id AS impression_app_id, i.remembered_details_json AS details_json_b64
                """
                results = session.run(query)
                for record in results:
                    impression_app_id = record["impression_app_id"]
                    details_json_b64 = record["details_json_b64"]

                    if not details_json_b64:
                        continue

                    try:
                        # 解码 Base64
                        details_json_str = base64.b64decode(details_json_b64).decode('utf-8')
                        # 解析 JSON
                        remembered_details = json.loads(details_json_str)

                        # 遍历 remembered_details，建立关系
                        for detail_type, detail_names in remembered_details.items():
                            for detail_name in detail_names:
                                if not detail_name:
                                    continue
                                # 根据 detail_type 构造 detail_app_id
                                if detail_type == "locations":
                                    detail_app_id = f"place_{hash(detail_name)}"
                                    rel_type = "REMEMBERS_LOCATION"
                                elif detail_type == "times":
                                    detail_app_id = f"time_{hash(detail_name)}"
                                    rel_type = "REMEMBERS_TIME"
                                elif detail_type == "actions":
                                    detail_app_id = f"action_{hash(detail_name)}"
                                    rel_type = "REMEMBERS_ACTION"
                                elif detail_type == "actors":
                                    detail_app_id = f"actor_{hash(detail_name)}"
                                    rel_type = "REMEMBERS_ACTOR"
                                elif detail_type == "emotions":
                                    detail_app_id = f"emotion_{hash(detail_name)}"
                                    rel_type = "REMEMBERS_EMOTION"
                                elif detail_type == "items":
                                    detail_app_id = f"item_{hash(detail_name)}"
                                    rel_type = "REMEMBERS_ITEM"
                                else:
                                    continue # 跳过未知类型

                                # 创建 Impression -> Detail 的关系
                                session.run(f"""
                                    MATCH (i:Impression {{app_id: $impression_app_id}})
                                    MATCH (d) WHERE d.app_id = $detail_app_id
                                    MERGE (i)-[:{rel_type}]->(d)
                                """, impression_app_id=impression_app_id, detail_app_id=detail_app_id)

                    except (base64.binascii.Error, json.JSONDecodeError, TypeError) as e:
                        print(f"解码或解析印象 {impression_app_id} 的 remembered_details 时出错: {e}",flush=True)
                        continue # 跳过这个印象

                return True
            except Exception as e:
                print(f"建立 Impression -> Detail 关系失败: {e}",flush=True)
                import traceback
                traceback.print_exc()
                return False

if __name__ == "__main__":
    try:
        graph_store = GraphStore(
            uri="bolt://neo4j-latest-new:7687",
            user="neo4j",
            password="zyh123456",
            database="neo4j"
        )
        graph_store.close()
    except Exception as e:
        print(f"初始化 GraphStore 失败: {e}",flush=True)