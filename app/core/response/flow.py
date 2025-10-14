"""
三阶段响应流程模块

实现角色对话的三阶段响应流程：下意识响应、记忆检索、补充响应。
"""

import asyncio
import time
from typing import Dict, List, Any, Optional, AsyncGenerator, Tuple

from app.core.llm.openai_client import CharacterLLM
from app.core.memory.vector_store import ChromaMemoryStore

class ResponseFlow:
    """
    三阶段响应流程类
    
    实现角色对话的三阶段响应流程：下意识响应、记忆检索、补充响应
    """
    
    def __init__(self, 
                character_llm: Optional[CharacterLLM] = None,
                memory_store: Optional[ChromaMemoryStore] = None):
        """
        初始化响应流程
        
        Args:
            character_llm: 角色LLM客户端，如果为None则创建新实例
            memory_store: 记忆存储，如果为None则创建新实例
        """
        self.character_llm = character_llm or CharacterLLM()
        self.memory_store = memory_store or ChromaMemoryStore()
    
    async def process(self, 
                     character_id: str,
                     character_data: Dict[str, Any],
                     user_input: str,
                     conversation_history: List[Dict[str, str]] = None) -> AsyncGenerator[Dict[str, Any], None]:
        """
        处理用户输入，生成三阶段响应
        
        Args:
            character_id: 角色ID
            character_data: 角色数据
            user_input: 用户输入
            conversation_history: 对话历史
            
        Yields:
            响应数据，包含类型和内容
        """
        # 阶段1: 下意识响应
        immediate_response = await self._generate_immediate_response(
            character_data, user_input, conversation_history
        )
        
        # 阶段2: 异步记忆检索
        memory_task = asyncio.create_task(
            self._retrieve_relevant_memories(character_id, user_input)
        )
        
        # 返回初始响应
        yield {
            "type": "immediate",
            "content": immediate_response,
            "timestamp": time.time()
        }
        
        # 等待记忆检索完成
        memories = await memory_task
        
        # 如果没有找到相关记忆，直接结束
        if not memories:
            return
        
        # 阶段3: 补充响应
        supplementary_response = await self._generate_supplementary_response(
            character_data, user_input, immediate_response, memories, conversation_history
        )
        
        # 返回补充响应
        yield {
            "type": "supplementary",
            "content": supplementary_response,
            "timestamp": time.time(),
            "memories": memories
        }
    
    async def _generate_immediate_response(self,
                                         character_data: Dict[str, Any],
                                         user_input: str,
                                         conversation_history: List[Dict[str, str]] = None) -> str:
        """
        生成下意识快速响应（极速版）
        
        只基于角色人设和最近1轮对话，确保响应速度极快
        
        Args:
            character_data: 角色数据
            user_input: 用户输入
            conversation_history: 对话历史
            
        Returns:
            生成的响应文本
        """
        # 只使用最近1轮对话，确保极快响应
        recent_history = None
        if conversation_history:
            recent_history = conversation_history[-2:]  # 只取最近1轮（用户+AI各1条）
        
        # 使用简化的 prompt 生成快速响应
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: self.character_llm.generate_quick_response(
                character_data=character_data,
                user_input=user_input,
                conversation_history=recent_history
            )
        )
        
        return response
    
    async def _retrieve_relevant_memories(self, 
                                        character_id: str,
                                        query_text: str,
                                        n_results: int = 5) -> List[Dict[str, Any]]:
        """
        检索相关记忆
        
        Args:
            character_id: 角色ID
            query_text: 查询文本
            n_results: 返回结果数量
            
        Returns:
            记忆列表
        """
        print(f"\n{'='*50}")
        print(f"开始记忆检索")
        print(f"角色ID: {character_id}")
        print(f"查询文本: {query_text}")
        print(f"请求数量: {n_results}")
        print(f"{'='*50}\n")
        
        start_time = time.time()
        
        # 使用记忆存储检索记忆
        loop = asyncio.get_event_loop()
        memories = await loop.run_in_executor(
            None,
            lambda: self.memory_store.query_memories(
                character_id=character_id,
                query_text=query_text,
                n_results=n_results
            )
        )
        
        elapsed_time = time.time() - start_time
        
        print(f"\n{'='*50}")
        print(f"记忆检索完成")
        print(f"耗时: {elapsed_time:.2f} 秒")
        print(f"检索到 {len(memories)} 条记忆")
        print(f"{'='*50}\n")
        
        # 过滤掉相关性较低的记忆
        relevant_memories = [m for m in memories if m.get("relevance", 0) > 0.3]
        
        print(f"过滤后保留 {len(relevant_memories)} 条高相关性记忆 (relevance > 0.3)")
        
        return relevant_memories
    
    async def _generate_supplementary_response(self,
                                             character_data: Dict[str, Any],
                                             user_input: str,
                                             immediate_response: str,
                                             memories: List[Dict[str, Any]],
                                             conversation_history: List[Dict[str, str]] = None) -> str:
        """
        基于检索到的记忆生成补充响应
        
        Args:
            character_data: 角色数据
            user_input: 用户输入
            immediate_response: 下意识响应
            memories: 检索到的记忆
            conversation_history: 对话历史
            
        Returns:
            生成的补充响应文本
        """
        print(f"\n{'='*50}")
        print(f"开始生成补充响应")
        print(f"检索到 {len(memories)} 条相关记忆")
        print(f"{'='*50}\n")
        
        # 构建记忆文本
        memories_list = []
        for i, m in enumerate(memories, 1):
            memory_text = f"""
记忆 {i}:
标题: {m.get('title', '无标题')}
内容: {m.get('content', '')}
时间: {m.get('time', '未知')}
情感: {m.get('emotion', '中性')}
重要性: {m.get('importance', 5)}/10
相关性: {m.get('relevance', 0):.2f}
"""
            memories_list.append(memory_text)
            print(memory_text)
        
        memories_text = "\n".join(memories_list)
        
        # 构建系统提示（中文）
        system_prompt = f"""
你正在扮演以下角色进行对话。用户问了一个问题，你已经给出了初步回答。
现在你检索到了一些相关的个人记忆，可以帮助你提供更详细、更真实的回答。

角色信息：
姓名：{character_data.get('name', '')}
年龄：{character_data.get('age', '')}
职业：{character_data.get('occupation', '')}
背景：{character_data.get('background', '')}
说话风格：{character_data.get('speech_style', '')}

你的任务是基于这些记忆生成一个补充响应，要求：
1. 完全重写你的回答，不要简单地在初步回答后面添加内容
2. 深入展开记忆中的细节，让回答更加生动、具体、真实
3. 自然地融入记忆内容，就像在回忆往事一样
4. 保持角色的性格和说话风格
5. 回答要比初步回答更详细、更有深度（至少200字）
6. 不要提及"记忆"、"补充"等元信息
7. 如果记忆与问题高度相关，就详细讲述这段经历

重要：这是一个完整的新回答，不是对初步回答的补充！
"""
        
        # 构建用户提示
        user_prompt = f"""
用户问题：
{user_input}

你的初步回答：
{immediate_response}

检索到的相关记忆：
{memories_text}

现在，请基于这些记忆，重新生成一个更详细、更深入的完整回答：
"""
        
        print(f"\n{'='*50}")
        print(f"正在调用 LLM 生成补充响应...")
        print(f"{'='*50}\n")
        
        # 使用角色LLM生成补充响应
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: self.character_llm.client.generate_response(
                system_prompt=system_prompt,
                user_prompt=user_prompt
            )
        )
        
        print(f"\n{'='*50}")
        print(f"补充响应生成完成")
        print(f"响应长度: {len(response)} 字符")
        print(f"{'='*50}\n")
        
        # 如果响应太短或为空，返回空字符串
        if not response or len(response.strip()) < 50:
            print("补充响应太短，跳过")
            return ""
        
        return response


# 测试代码
if __name__ == "__main__":
    import os
    import json
    
    async def test_response_flow():
        # 设置API密钥
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            print("请设置OPENAI_API_KEY环境变量")
            exit(1)
        
        # 创建角色LLM和记忆存储
        character_llm = CharacterLLM()
        memory_store = ChromaMemoryStore(
            persist_directory="./test_chroma_db",
            openai_api_key=api_key
        )
        
        # 创建响应流程
        response_flow = ResponseFlow(
            character_llm=character_llm,
            memory_store=memory_store
        )
        
        # 测试角色ID和数据
        character_id = "test_character_002"
        character_data = {
            "name": "苏雅",
            "age": 68,
            "gender": "女",
            "occupation": "退休语文教师",
            "personality": {
                "openness": 75,
                "conscientiousness": 85,
                "extraversion": 60,
                "agreeableness": 90,
                "neuroticism": 40
            },
            "background": "苏雅是一位退休的语文教师，在上海一所重点中学教书40年。她性格温和，做事认真负责，深受学生爱戴。退休后，她喜欢读书、写字和园艺。",
            "speech_style": "语言优美规范，常引用古诗文，语速适中，语气温和但坚定，偶尔使用教师式的启发性问句。"
        }
        
        # 添加测试记忆
        memory_store.add_memories(
            character_id=character_id,
            memories=[
                {
                    "type": "education",
                    "title": "大学经历",
                    "content": "1955年考入北京师范大学中文系，师从著名语言学家吕叔湘教授，打下了扎实的语言文学功底。",
                    "time": "1955年-1959年",
                    "emotion": "positive",
                    "importance": 9
                },
                {
                    "type": "work",
                    "title": "教学成就",
                    "content": "1980年指导的学生李明在全国中学生作文比赛中获得一等奖，这是她教学生涯中最自豪的成就之一。",
                    "time": "1980年",
                    "emotion": "positive",
                    "importance": 10
                },
                {
                    "type": "family",
                    "title": "丈夫去世",
                    "content": "2010年，结婚50年的丈夫因病去世，这是她人生中最大的打击，但她坚强地走了过来。",
                    "time": "2010年",
                    "emotion": "negative",
                    "importance": 10
                }
            ]
        )
        
        # 测试对话
        user_input = "您好，苏老师！请问您在教学生涯中最难忘的一件事是什么？"
        print(f"用户: {user_input}")
        
        # 处理响应
        async for response in response_flow.process(
            character_id=character_id,
            character_data=character_data,
            user_input=user_input
        ):
            if response["type"] == "immediate":
                print(f"\n[下意识响应]:\n{response['content']}")
            elif response["type"] == "supplementary":
                print(f"\n[补充响应]:\n{response['content']}")
                print("\n使用的记忆:")
                for memory in response["memories"]:
                    print(f"- {memory['title']}: {memory['content']} (相关性: {memory['relevance']:.2f})")
        
        # 清理测试数据
        print("\n清理测试数据...")
        memory_store.delete_all_memories(character_id)
        print("测试完成")
    
    # 运行测试
    asyncio.run(test_response_flow())
