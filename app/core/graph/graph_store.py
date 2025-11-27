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
                    search_type="vector",
                )
                print("✅ Neo4jVector (impressions) 初始化成功。")
            except Exception as e:
                print(f"❌ Neo4jVector (impressions) 初始化失败: {e}")
                print("   这可能导致语义搜索功能不可用，但应用将继续启动。")
                import traceback as tb
                tb.print_exc() # 打印完整堆栈跟踪
                self.neo4j_vector_impressions = None
        else:
            print("⚠️  由于 Embeddings 初始化失败，跳过 Neo4jVector 初始化。")
            self.neo4j_vector_impressions = None
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
        将主角、关联角色以及结构化对话（事件）保存为 CSV。
        仅保留结构化对话中出现的字段：id/scene/participants/topic/time_at_occurrence/context/dialogue_content。
        输出：
        - nodes_file：角色与事件节点
        - relationships_file：角色-事件关系与事件时间链
        """
        print(f"- 开始将数据保存为统一格式的 CSV (仅角色/事件与时间链) -", flush=True)

        nodes_filename = os.path.join(self.temp_csv_dir, f"timeline_graph_nodes_{character_id}.csv")
        relationships_filename = os.path.join(self.temp_csv_dir, f"timeline_graph_relationships_{character_id}.csv")

        allowed_memory_fields = {
            "id", "scene", "participants", "topic", "time_at_occurrence", "context", "dialogue_content"
        }

        sanitized_memories = []
        for memory in memories:
            sanitized = {k: v for k, v in memory.items() if k in allowed_memory_fields}
            sanitized.setdefault("id", str(uuid.uuid4()))
            sanitized.setdefault("participants", [])
            sanitized_memories.append(sanitized)

        with open(nodes_filename, 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = [
                "node_id", "label", "name", "role", "age", "gender", "occupation", "past_experience", "background",
                "topic", "context", "dialogue_content", "time_at_occurrence", "participants"
            ]
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames, quoting=csv.QUOTE_ALL, quotechar='"')
            writer.writeheader()

            # 主角与关联角色节点
            for is_main, char_data in [(True, main_character)] + [(False, rc) for rc in related_characters]:
                writer.writerow({
                    "node_id": char_data.get("id"),
                    "label": "Character",
                    "name": char_data.get("name", ""),
                    "role": "protagonist" if is_main else "related",
                    "age": char_data.get("age", ""),
                    "gender": char_data.get("gender", ""),
                    "occupation": char_data.get("occupation", ""),
                    "past_experience": char_data.get("past_experience", ""),
                    "background": char_data.get("background", ""),
                    "topic": "",
                    "context": "",
                    "dialogue_content": "",
                    "time_at_occurrence": "",
                    "participants": ""
                })

            # 事件节点
            for memory in sanitized_memories:
                writer.writerow({
                    "node_id": memory.get("id"),
                    "label": "Event",
                    "name": memory.get("topic", ""),
                    "role": "event",
                    "age": "",
                    "gender": "",
                    "occupation": "",
                    "past_experience": "",
                    "background": "",
                    "topic": memory.get("topic", ""),
                    "context": memory.get("context", ""),
                    "dialogue_content": memory.get("dialogue_content", ""),
                    "time_at_occurrence": memory.get("time_at_occurrence", ""),
                    "participants": ";".join(memory.get("participants", [])),
                })

        name_to_id = {main_character.get("name"): main_character.get("id")}
        for rc in related_characters:
            name_to_id[rc.get("name")] = rc.get("id")

        def _parse_age(value: str) -> float:
            if not value:
                return float("inf")
            match = re.search(r"(\d+(?:\.\d+)?)", value)
            return float(match.group(1)) if match else float("inf")

        with open(relationships_filename, 'w', newline='', encoding='utf-8') as rel_csv:
            fieldnames = ["start_id", "end_id", "type", "description"]
            writer = csv.DictWriter(rel_csv, fieldnames=fieldnames, quoting=csv.QUOTE_ALL, quotechar='"')
            writer.writeheader()

            # 主角 -> 事件，关联角色 -> 事件
            for memory in sanitized_memories:
                event_id = memory.get("id")
                writer.writerow({
                    "start_id": main_character.get("id"),
                    "end_id": event_id,
                    "type": "PROTAGONIST_EVENT",
                    "description": "主角参与事件"
                })

                for participant in memory.get("participants", []):
                    participant_id = name_to_id.get(participant)
                    if participant_id and participant_id != main_character.get("id"):
                        writer.writerow({
                            "start_id": participant_id,
                            "end_id": event_id,
                            "type": "ASSOCIATED_EVENT",
                            "description": f"{participant} 参与事件"
                        })

            # 事件时间链
            ordered_memories = sorted(sanitized_memories, key=lambda m: _parse_age(m.get("time_at_occurrence", "")))
            for idx in range(len(ordered_memories) - 1):
                writer.writerow({
                    "start_id": ordered_memories[idx].get("id"),
                    "end_id": ordered_memories[idx + 1].get("id"),
                    "type": "NEXT_EVENT",
                    "description": "时间顺序"
                })

        print("--- CSV 文件已生成 (角色/事件/时间链) ---", flush=True)
        return {
            "nodes_file": os.path.basename(nodes_filename),
            "relationships_file": os.path.basename(relationships_filename),
        }

    def import_nodes_from_csv(self, csv_filename: str) -> bool:
        print("⚠️ 已停用代码层面的 Cypher 导入，请使用 Neo4j-admin 或 Neo4j Desktop 的 CSV 导入功能。")
        return False

    def import_entity_event_relationships_from_csv(self, csv_filename: str) -> bool:
        print("⚠️ 已停用代码层面的 Cypher 导入，请使用 Neo4j 提供的 CSV 批量导入工具。")
        return False

    def import_temporal_chain_from_csv(self, csv_filename: str) -> bool:
        print("⚠️ 已停用代码层面的 Cypher 导入，请使用 Neo4j 提供的 CSV 批量导入工具。")
        return False

    def import_character_to_character_relationships_from_csv(self, csv_filename: str) -> bool:
        print("⚠️ 已停用代码层面的 Cypher 导入，请使用 Neo4j 提供的 CSV 批量导入工具。")
        return False

