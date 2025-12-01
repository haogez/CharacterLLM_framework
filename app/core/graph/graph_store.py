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
import subprocess
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
                 index_name: str = "events",
                 text_node_property: str = "event_content"
                 ):
        self.uri = uri
        self.user = user
        self.password = password
        self.database = database
        self.text_node_property = text_node_property
        self.driver = GraphDatabase.driver(self.uri, auth=(self.user, self.password))
        self.temp_csv_dir = "./temp_csv"
        os.makedirs(self.temp_csv_dir, exist_ok=True)

        self.embeddings = embedding or OpenAIEmbeddings()
        self.neo4j_vector_impressions = None
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
            # 初始化后做一次轻量级的模式修复，避免因缺失属性或关系类型导致的查询警告
            try:
                self._backfill_core_schema()
            except Exception as exc:
                log_warning(f"Schema backfill skipped: {exc}")
        except Exception as e:
            print(f"连接 Neo4j 失败: {e}")
            import traceback
            traceback.print_exc()
            raise e

        # 事件、对话、地点、时间、角色、主题的向量索引
        self.vector_index_map = {
            "Event": {"index": "vec_event", "text_prop": "event_content", "vector_prop": "embedding"},
            "Dialogue": {"index": "vec_dialogue", "text_prop": "content", "vector_prop": "embedding"},
            "Place": {"index": "vec_place", "text_prop": "name", "vector_prop": "embedding"},
            "Time": {"index": "vec_time", "text_prop": "label", "vector_prop": "embedding"},
            "Character": {"index": "vec_character", "text_prop": "name", "vector_prop": "embedding"},
            "Topic": {"index": "vec_topic", "text_prop": "name", "vector_prop": "embedding"},
        }

    def _ensure_vector_index(self, index_name: str, label: str, vector_prop: str, dimension: int) -> None:
        """确保指定的向量索引存在，不存在则创建。"""
        with self.driver.session(database=self.database) as session:
            try:
                result = session.run(
                    "SHOW INDEXES YIELD name, type WHERE type = 'VECTOR' AND name = $name RETURN name",
                    name=index_name,
                )
                exists = result.single() is not None
                if exists:
                    print(f"✅ 向量索引 '{index_name}' 已存在，无需创建。")
                    return

                print(f"ℹ️  未找到向量索引 '{index_name}'，正在创建（维度: {dimension}）...")
                session.run(
                    f"""
                    CREATE VECTOR INDEX {index_name} IF NOT EXISTS
                    FOR (n:{label}) ON (n.{vector_prop})
                    OPTIONS {{
                        indexConfig: {{
                            `vector.dimensions`: $dim,
                            `vector.similarity_function`: 'cosine'
                        }}
                    }}
                    """,
                    dim=dimension,
                )
                print(f"✅ 向量索引 '{index_name}' 创建完成。")
            except Exception as e:
                print(f"⚠️  检查/创建向量索引 '{index_name}' 失败: {e}")
                print("   语义检索可能不可用，请手动检查 Neo4j 配置。")

    def _backfill_core_schema(self) -> None:
        """回填核心属性并生成样板关系，避免 Neo4j 查询时的缺失警告。"""
        with self.driver.session(database=self.database) as session:
            # 角色的关系字段
            session.run(
                """
                MATCH (c:Character)
                WHERE c.relationship_to_protagonist IS NULL
                SET c.relationship_to_protagonist = 'UNKNOWN'
                """
            )

            # 事件内容
            session.run(
                """
                MATCH (e:Event)
                WHERE e.event_content IS NULL
                SET e.event_content = coalesce(e.content, e.title, '')
                """
            )

            # 建立模式锚点以注册关系类型（避免 relationship type does not exist 警告）
            session.run(
                """
                MERGE (_schema_c:SchemaAnchor {name:'__schema_char'})
                MERGE (_schema_e:SchemaAnchor {name:'__schema_evt'})
                MERGE (_schema_t:SchemaAnchor {name:'__schema_time'})
                MERGE (_schema_c)-[:PROTAGONIST_EVENT]->(_schema_e)
                MERGE (_schema_e)-[:EVENT_TIME]->(_schema_t)
                """
            )

            log_info("Schema backfill completed for core properties and anchor relations.")

    def close(self):
        if self.driver:
            self.driver.close()
            print("--- Neo4j 连接已关闭 ---")


    @staticmethod
    def _normalize_dialogues(raw_dialogue: Any) -> List[Dict[str, Any]]:
        """
        将对话内容转换为 [{speaker, content}] 列表。
        支持列表、JSON 字符串或连续文本（按“角色：内容”分段）。
        """
        dialogue_list: List[Dict[str, Any]] = []

        if isinstance(raw_dialogue, list):
            for entry in raw_dialogue:
                if isinstance(entry, dict):
                    speaker = entry.get("speaker") or entry.get("角色") or entry.get("人物")
                    content = entry.get("content") or entry.get("台词") or entry.get("对白") or entry.get("对话")
                    if content:
                        dialogue_list.append({"speaker": speaker, "content": str(content).strip()})
                elif isinstance(entry, str) and entry.strip():
                    dialogue_list.append({"speaker": None, "content": entry.strip()})
            return dialogue_list

        if isinstance(raw_dialogue, str):
            raw_text = raw_dialogue.strip()
            if not raw_text:
                return dialogue_list

            try:
                parsed = json.loads(raw_text)
                return GraphStore._normalize_dialogues(parsed)
            except Exception:
                pass

            pattern = re.compile(r"(?P<speaker>[\u4e00-\u9fa5A-Za-z0-9_（）()·\s]+)：")
            matches = list(pattern.finditer(raw_text))
            if matches:
                for idx, match in enumerate(matches):
                    start = match.end()
                    end = matches[idx + 1].start() if idx + 1 < len(matches) else len(raw_text)
                    content = raw_text[start:end].strip()
                    speaker = match.group("speaker").strip()
                    if content:
                        dialogue_list.append({"speaker": speaker, "content": content})
            else:
                dialogue_list.append({"speaker": None, "content": raw_text})

        return dialogue_list


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
                node_properties.setdefault("relationship_to_protagonist", "UNKNOWN")

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

                # 为向量检索提供统一的文本字段
                impression_properties.setdefault("impression_content", impression_properties.get("content", ""))

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
            "impression_content": impression_content,
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

    def get_relationship_between_characters(self, main_character_id: str, other_character_id: str) -> Dict[str, Any]:
        """
        返回两个角色之间的关系类型和描述。
        优先读取关联角色节点上的 relationship_to_protagonist 字段；
        若缺失，则依据共同参与的事件生成描述。
        """
        with self.driver.session(database=self.database) as session:
            try:
                result = session.run(
                    """
                    MATCH (main:Character {app_id: $main_id}), (other:Character {app_id: $other_id})
                    OPTIONAL MATCH (main)-[:PROTAGONIST_EVENT]->(e:Event)<-[:ASSOCIATED_EVENT]-(other)
                    WITH main, other, collect(e.app_id) AS shared_events
                    RETURN COALESCE(other.relationship_to_protagonist, 'UNKNOWN') AS rel, shared_events
                    """,
                    main_id=main_character_id,
                    other_id=other_character_id
                )

                record = result.single()
                rel_type = record["rel"] if record and record["rel"] else "UNKNOWN"
                shared_events = record["shared_events"] if record and record["shared_events"] else []

                description = "" if rel_type != "UNKNOWN" else "共同经历的事件数量" if shared_events else "未知"
                if rel_type == "UNKNOWN" and shared_events:
                    description = f"共同参与 {len(shared_events)} 个事件"

                return {"type": rel_type, "description": description}
            except Exception as e:
                print(f"获取角色关系失败: {e}")
                return {"type": "UNKNOWN", "description": "查询失败"}

    def get_places_for_character(self, character_id: str) -> List[Dict[str, str]]:
        """返回角色经历过的地点列表（Place 节点）。"""
        with self.driver.session(database=self.database) as session:
            try:
                result = session.run(
                    """
                    MATCH (c:Character {app_id: $char_id})-[:PROTAGONIST_EVENT|ASSOCIATED_EVENT]->(e:Event)-[:EVENT_LOCATION]->(p:Place)
                    RETURN DISTINCT p.app_id AS id, p.name AS name
                    """,
                    char_id=character_id
                )
                return [{"id": rec["id"], "name": rec["name"]} for rec in result]
            except Exception as e:
                print(f"获取地点失败: {e}")
                return []

    def vector_search(self, label: str, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        config = self.vector_index_map.get(label)
        if not config:
            log_warning(f"未配置 {label} 的向量索引")
            return []

        try:
            self._ensure_vector_index(
                index_name=config["index"],
                label=label,
                vector_prop=config["vector_prop"],
                dimension=1536,
            )
            vector_store = Neo4jVector.from_existing_index(
                embedding=self.embeddings,
                url=self.uri,
                username=self.user,
                password=self.password,
                index_name=config["index"],
                text_node_property=config["text_prop"],
            )
            docs = vector_store.similarity_search(query, k=top_k)
            results = []
            for d in docs:
                meta = d.metadata
                results.append({
                    "app_id": meta.get("app_id") or meta.get("id"),
                    "content": d.page_content,
                    "score": meta.get("score", 70),
                    "label": label,
                })
            return results
        except Exception as e:
            log_warning(f"{label} 向量搜索失败: {e}")
            return []


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
                "node_id:ID", "label:LABEL", "name", "role", "age", "gender", "occupation", "past_experience", "background",
                "topic", "context", "dialogue_content", "time_at_occurrence", "participants"
            ]
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames, quoting=csv.QUOTE_ALL, quotechar='"')
            writer.writeheader()

            def _write_node(row: Dict[str, Any]):
                writer.writerow(row)

            # 主角与关联角色节点
            for is_main, char_data in [(True, main_character)] + [(False, rc) for rc in related_characters]:
                _write_node({
                    "node_id:ID": char_data.get("id"),
                    "label:LABEL": "Character",
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

            # 事件节点与衍生节点
            for memory in sanitized_memories:
                event_id = memory.get("id")
                participants = memory.get("participants", []) or []
                raw_dialogue = memory.get("dialogue_content", [])
                normalized_dialogues = self._normalize_dialogues(raw_dialogue)
                place_id = f"place_{hash(memory.get('scene'))}" if memory.get("scene") else None

                _write_node({
                    "node_id:ID": event_id,
                    "label:LABEL": "Event",
                    "name": memory.get("topic", ""),
                    "role": "event",
                    "age": "",
                    "gender": "",
                    "occupation": "",
                    "past_experience": "",
                    "background": "",
                    "topic": memory.get("topic", ""),
                    "context": memory.get("context", ""),
                    "dialogue_content": json.dumps(normalized_dialogues, ensure_ascii=False),
                    "time_at_occurrence": memory.get("time_at_occurrence", ""),
                    "participants": ";".join(participants),
                })

                if memory.get("time_at_occurrence"):
                    _write_node({
                        "node_id:ID": f"{event_id}_time",
                        "label:LABEL": "Time",
                        "name": memory.get("time_at_occurrence"),
                        "role": "time",
                        "age": "",
                        "gender": "",
                        "occupation": "",
                        "past_experience": "",
                        "background": "",
                        "topic": "",
                        "context": "",
                        "dialogue_content": "",
                        "time_at_occurrence": memory.get("time_at_occurrence", ""),
                        "participants": ""
                    })

                if memory.get("scene"):
                    _write_node({
                        "node_id:ID": place_id,
                        "label:LABEL": "Place",
                        "name": memory.get("scene"),
                        "role": "location",
                        "age": "",
                        "gender": "",
                        "occupation": "",
                        "past_experience": "",
                        "background": "",
                        "topic": "",
                        "context": memory.get("context", ""),
                        "dialogue_content": "",
                        "time_at_occurrence": memory.get("time_at_occurrence", ""),
                        "participants": ""
                    })

                if memory.get("topic"):
                    _write_node({
                        "node_id:ID": f"{event_id}_topic",
                        "label:LABEL": "Topic",
                        "name": memory.get("topic"),
                        "role": "topic",
                        "age": "",
                        "gender": "",
                        "occupation": "",
                        "past_experience": "",
                        "background": "",
                        "topic": memory.get("topic", ""),
                        "context": "",
                        "dialogue_content": "",
                        "time_at_occurrence": memory.get("time_at_occurrence", ""),
                        "participants": ""
                    })

                dialogue_list = normalized_dialogues

                for idx, dialogue in enumerate(dialogue_list):
                    _write_node({
                        "node_id:ID": f"{event_id}_dialogue_{idx}",
                        "label:LABEL": "Dialogue",
                        "name": f"{dialogue.get('speaker') or ''}: {dialogue.get('content', '')[:120]}".strip(': ').strip(),
                        "role": "dialogue",
                        "age": "",
                        "gender": "",
                        "occupation": "",
                        "past_experience": "",
                        "background": "",
                        "topic": memory.get("topic", ""),
                        "context": memory.get("context", ""),
                        "dialogue_content": dialogue.get("content", ""),
                        "time_at_occurrence": memory.get("time_at_occurrence", ""),
                        "participants": dialogue.get("speaker", "") or ""
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
            fieldnames = ["start_id:START_ID", "end_id:END_ID", "type:TYPE", "description"]
            writer = csv.DictWriter(rel_csv, fieldnames=fieldnames, quoting=csv.QUOTE_ALL, quotechar='"')
            writer.writeheader()

            def _write_rel(row: Dict[str, Any]):
                writer.writerow(row)

            for memory in sanitized_memories:
                event_id = memory.get("id")
                _write_rel({
                    "start_id:START_ID": main_character.get("id"),
                    "end_id:END_ID": event_id,
                    "type:TYPE": "PROTAGONIST_EVENT",
                    "description": "主角参与事件"
                })

                for participant in memory.get("participants", []):
                    participant_id = name_to_id.get(participant)
                    if participant_id and participant_id != main_character.get("id"):
                        _write_rel({
                            "start_id:START_ID": participant_id,
                            "end_id:END_ID": event_id,
                            "type:TYPE": "ASSOCIATED_EVENT",
                            "description": f"{participant} 参与事件"
                        })

                if memory.get("time_at_occurrence"):
                    _write_rel({
                        "start_id:START_ID": event_id,
                        "end_id:END_ID": f"{event_id}_time",
                        "type:TYPE": "EVENT_TIME",
                        "description": "事件发生时间"
                    })

                if memory.get("scene"):
                    _write_rel({
                        "start_id:START_ID": event_id,
                        "end_id:END_ID": place_id,
                        "type:TYPE": "EVENT_LOCATION",
                        "description": "事件发生地点"
                    })

                if memory.get("topic"):
                    _write_rel({
                        "start_id:START_ID": event_id,
                        "end_id:END_ID": f"{event_id}_topic",
                        "type:TYPE": "EVENT_TOPIC",
                        "description": "事件主题"
                    })

                raw_dialogue = memory.get("dialogue_content", [])
                dialogue_list = self._normalize_dialogues(raw_dialogue)

                for idx, dialogue in enumerate(dialogue_list):
                    dialogue_id = f"{event_id}_dialogue_{idx}"
                    _write_rel({
                        "start_id:START_ID": event_id,
                        "end_id:END_ID": dialogue_id,
                        "type:TYPE": "EVENT_DIALOGUE",
                        "description": "事件相关对话"
                    })

                    speaker_name = dialogue.get("speaker")
                    speaker_id = name_to_id.get(speaker_name) if speaker_name else None
                    if speaker_id:
                        _write_rel({
                            "start_id:START_ID": dialogue_id,
                            "end_id:END_ID": speaker_id,
                            "type:TYPE": "DIALOGUE_SPOKEN_BY",
                            "description": "对话发言者"
                        })

            ordered_memories = sorted(sanitized_memories, key=lambda m: _parse_age(m.get("time_at_occurrence", "")))
            for idx in range(len(ordered_memories) - 1):
                _write_rel({
                    "start_id:START_ID": ordered_memories[idx].get("id"),
                    "end_id:END_ID": ordered_memories[idx + 1].get("id"),
                    "type:TYPE": "NEXT_EVENT",
                    "description": "时间顺序"
                })

        print("--- CSV 文件已生成 (角色/事件/时间链) ---", flush=True)
        return {
            "nodes_file": os.path.basename(nodes_filename),
            "relationships_file": os.path.basename(relationships_filename),
        }

    def _run_admin_import(self, nodes_csv: str, relationships_csv: str, database: Optional[str] = None) -> bool:
        """使用 neo4j-admin 离线导入 CSV，不直接书写 Cypher。"""
        db_name = database or self.database
        neo4j_home = os.environ.get("NEO4J_HOME")
        admin_bin = os.environ.get("NEO4J_ADMIN_BIN")

        if admin_bin:
            neo4j_admin = admin_bin
        elif neo4j_home:
            neo4j_admin = os.path.join(neo4j_home, "bin", "neo4j-admin")
        else:
            neo4j_admin = "neo4j-admin"

        nodes_path = os.path.abspath(nodes_csv)
        rels_path = os.path.abspath(relationships_csv)

        for path in [nodes_path, rels_path]:
            if not os.path.exists(path):
                print(f"❌ 未找到 CSV 文件: {path}")
                return False

        cmd = [
            neo4j_admin,
            "database", "import", "full",
            "--overwrite",
            f"--nodes={nodes_path}",
            f"--relationships={rels_path}",
            db_name
        ]

        print(f"执行 neo4j-admin 导入: {' '.join(cmd)}")
        try:
            result = subprocess.run(cmd, check=True, capture_output=True, text=True)
            print(result.stdout)
            if result.stderr:
                print(result.stderr)
            print("✅ CSV 已通过 neo4j-admin 导入（需确保数据库处于离线状态）。")
            return True
        except FileNotFoundError:
            print("❌ 未找到 neo4j-admin，可通过设置 NEO4J_HOME 或 NEO4J_ADMIN_BIN 指定路径。")
            return False
        except subprocess.CalledProcessError as exc:
            print(f"❌ 导入失败: {exc.stderr or exc.stdout}")
            return False

    def import_graph_from_csv_online(self, nodes_csv: str, relationships_csv: str, batch_size: int = 500) -> bool:
        """
        在线读取 CSV 并通过驱动逐条合并节点和关系，避免大批量 Cypher/LOAD CSV 导致卡死。
        """
        def _resolve_path(path: str) -> str:
            return path if os.path.isabs(path) else os.path.join(self.temp_csv_dir, path)

        nodes_path = _resolve_path(nodes_csv)
        rels_path = _resolve_path(relationships_csv)

        if not os.path.exists(nodes_path) or not os.path.exists(rels_path):
            print(f"❌ 找不到节点或关系 CSV: {nodes_path}, {rels_path}")
            return False

        def merge_node(tx, label_list, app_id, props):
            label_clause = ":" + ":".join(label_list) if label_list else ""
            tx.run(
                f"MERGE (n{label_clause} {{app_id: $app_id}}) SET n += $props",
                app_id=app_id,
                props=props,
            )

        def merge_rel(tx, start_id, end_id, rel_type, props):
            tx.run(
                f"MATCH (s {{app_id: $start_id}}) MATCH (e {{app_id: $end_id}}) MERGE (s)-[r:{rel_type}]->(e) SET r += $props",
                start_id=start_id,
                end_id=end_id,
                props=props,
            )

        try:
            with self.driver.session(database=self.database) as session:
                with open(nodes_path, newline='', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        app_id = row.get("node_id:ID")
                        if not app_id:
                            continue
                        labels = [lbl.strip() for lbl in (row.get("label:LABEL") or "").split(";") if lbl.strip()]
                        props = {k: v for k, v in row.items() if k not in {"node_id:ID", "label:LABEL"} and v not in ("", None)}
                        session.execute_write(merge_node, labels, app_id, props)

                with open(rels_path, newline='', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    buffer = []
                    for row in reader:
                        start_id = row.get("start_id:START_ID")
                        end_id = row.get("end_id:END_ID")
                        rel_type = (row.get("type:TYPE") or "").replace("`", "")
                        if not all([start_id, end_id, rel_type]):
                            continue
                        props = {k: v for k, v in row.items() if k not in {"start_id:START_ID", "end_id:END_ID", "type:TYPE"} and v not in ("", None)}
                        buffer.append((start_id, end_id, rel_type, props))
                        if len(buffer) >= batch_size:
                            for sid, eid, rtype, rprops in buffer:
                                session.execute_write(merge_rel, sid, eid, rtype, rprops)
                            buffer.clear()

                    for sid, eid, rtype, rprops in buffer:
                        session.execute_write(merge_rel, sid, eid, rtype, rprops)

            print("✅ 已通过在线模式将 CSV 写入 Neo4j（逐条 MERGE，避免大批量导入堵塞）。")
            return True
        except Exception as e:
            print(f"❌ 在线导入 CSV 失败: {e}")
            traceback.print_exc()
            return False

    def import_nodes_from_csv(self, csv_filename: str) -> bool:
        print("⚠️ 已切换为 neo4j-admin 离线导入流程，确保数据库处于停止状态。")
        rels = os.path.join(os.path.dirname(csv_filename), f"timeline_graph_relationships_{os.path.basename(csv_filename).split('_')[-1]}")
        return self._run_admin_import(csv_filename, rels)

    def import_entity_event_relationships_from_csv(self, csv_filename: str) -> bool:
        print("⚠️ 已切换为 neo4j-admin 离线导入流程，确保数据库处于停止状态。")
        return self._run_admin_import(csv_filename, csv_filename)

    def import_temporal_chain_from_csv(self, csv_filename: str) -> bool:
        print("⚠️ 已切换为 neo4j-admin 离线导入流程，确保数据库处于停止状态。")
        return self._run_admin_import(csv_filename, csv_filename)

    def import_character_to_character_relationships_from_csv(self, csv_filename: str) -> bool:
        print("⚠️ 已切换为 neo4j-admin 离线导入流程，确保数据库处于停止状态。")
        return self._run_admin_import(csv_filename, csv_filename)

