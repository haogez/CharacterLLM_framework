"""
OpenAI API客户端封装模块

提供与OpenAI API交互的封装类，支持角色生成、记忆生成和对话生成等功能。
支持智增增平台API代理。
"""

import os
import json
from typing import Dict, List, Any, Optional, Union

from openai import OpenAI
from langchain.chat_models import ChatOpenAI
from langchain.schema import HumanMessage, SystemMessage, AIMessage

class OpenAIClient:
    """
    OpenAI API客户端封装类
    
    提供对OpenAI API的封装，支持直接调用和通过LangChain调用两种方式
    支持智增增平台API代理
    """
    
    def __init__(self, 
                api_key: Optional[str] = None, 
                model: str = "gpt-4.1-mini", 
                base_url: Optional[str] = None):
        """
        初始化OpenAI客户端
        
        Args:
            api_key: OpenAI API密钥，如果为None则从环境变量获取
            model: 使用的模型名称，默认为gpt-4.1-mini（智增增平台）
            base_url: API基础URL，用于支持智增增等代理平台，如果为None则从环境变量获取
        """
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self.base_url = base_url or os.environ.get("OPENAI_BASE_URL")
        self.model = os.environ.get("OPENAI_MODEL", model)
        
        # 直接客户端
        client_kwargs = {"api_key": self.api_key}
        if self.base_url:
            client_kwargs["base_url"] = self.base_url
        
        self.client = OpenAI(**client_kwargs)
        
        # LangChain客户端
        langchain_kwargs = {
            "model": model,
            "temperature": 0.7,
            "openai_api_key": self.api_key
        }
        if self.base_url:
            langchain_kwargs["openai_api_base"] = self.base_url
        
        self.chat_model = ChatOpenAI(**langchain_kwargs)
    
    def generate_response(self, system_prompt: str, user_prompt: str) -> str:
        """
        生成响应（使用直接客户端）
        
        Args:
            system_prompt: 系统提示
            user_prompt: 用户提示
            
        Returns:
            生成的响应文本
        """
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.7
            )
            
            # 检查响应是否有效
            if not response or not response.choices:
                raise ValueError("API返回了空响应")
            
            if not response.choices[0].message or not response.choices[0].message.content:
                raise ValueError("API返回的消息内容为空")
            
            return response.choices[0].message.content
            
        except Exception as e:
            print(f"OpenAI API调用失败: {e}")
            print(f"Model: {self.model}")
            print(f"Base URL: {self.base_url}")
            raise
    
    def generate_structured_response(self, system_prompt: str, user_prompt: str) -> Dict[str, Any]:
        """
        生成结构化JSON响应
        
        Args:
            system_prompt: 系统提示
            user_prompt: 用户提示
            
        Returns:
            解析后的JSON对象
        """
        # 添加JSON格式要求
        enhanced_system_prompt = f"{system_prompt}\n\nYou must respond in valid JSON format."
        
        response_text = self.generate_response(enhanced_system_prompt, user_prompt)
        
        # 调试日志
        print(f"=== LLM 原始响应 ===")
        print(response_text[:500] if len(response_text) > 500 else response_text)
        print(f"=== 响应长度: {len(response_text)} ===")
        
        try:
            # 尝试解析JSON
            parsed = json.loads(response_text)
            print(f"✓ JSON 解析成功")
            return parsed
        except json.JSONDecodeError as e:
            print(f"✗ JSON 解析失败: {e}")
            # 如果解析失败，尝试提取JSON部分
            try:
                # 查找可能的JSON部分（在```json和```之间）
                import re
                json_match = re.search(r'```json\n(.*?)\n```', response_text, re.DOTALL)
                if json_match:
                    print(f"✓ 从 ```json``` 块中提取 JSON")
                    return json.loads(json_match.group(1))
                
                # 尝试查找{开头和}结尾的部分
                json_match = re.search(r'(\{.*\})', response_text, re.DOTALL)
                if json_match:
                    print(f"✓ 从文本中提取 JSON")
                    return json.loads(json_match.group(1))
                
                # 返回文本作为备选
                print(f"✗ 无法提取有效的 JSON")
                return {"text": response_text, "error": "Failed to parse JSON"}
            except Exception as e:
                print(f"✗ JSON 提取失败: {e}")
                return {"text": response_text, "error": str(e)}
    
    def langchain_generate(self, messages: List[Union[SystemMessage, HumanMessage, AIMessage]]) -> str:
        """
        使用LangChain生成响应
        
        Args:
            messages: LangChain消息列表
            
        Returns:
            生成的响应文本
        """
        response = self.chat_model.generate([messages])
        return response.generations[0][0].text
    
    def create_embeddings(self, texts: List[str]) -> List[List[float]]:
        """
        创建文本嵌入向量
        
        Args:
            texts: 要嵌入的文本列表
            
        Returns:
            嵌入向量列表
        """
        response = self.client.embeddings.create(
            model="text-embedding-3-large",
            input=texts
        )
        return [item.embedding for item in response.data]


class CharacterLLM:
    """
    角色化大语言模型客户端
    
    提供针对角色生成、记忆生成和对话生成的专用方法
    """
    
    def __init__(self, openai_client: Optional[OpenAIClient] = None):
        """
        初始化角色化LLM客户端
        
        Args:
            openai_client: OpenAI客户端实例，如果为None则创建新实例
        """
        self.client = openai_client or OpenAIClient()
    
    def generate_character(self, description: str) -> Dict[str, Any]:
        """
        生成角色
        
        Args:
            description: 角色描述
            
        Returns:
            角色数据字典
        """
        system_prompt = """
        You are a character creation assistant. Your task is to create a detailed character profile based on the given description.
        
        Respond with a JSON object in EXACTLY this format (no nested objects):
        {
          "name": "character's name",
          "age": 35,
          "gender": "male/female/other",
          "occupation": "character's occupation",
          "background": "detailed background story",
          "speech_style": "description of how the character speaks",
          "personality": {
            "openness": 65,
            "conscientiousness": 75,
            "extraversion": 55,
            "agreeableness": 80,
            "neuroticism": 40
          }
        }
        
        IMPORTANT: 
        - Use the exact field names shown above
        - personality scores should be integers from 0-100
        - Do not use nested objects except for "personality"
        - Respond ONLY with the JSON, no additional text
        """
        
        user_prompt = f"Create a character based on this description: {description}"
        
        return self.client.generate_structured_response(system_prompt, user_prompt)
    
    def generate_memory(self, character_data: Dict[str, Any], memory_type: str) -> Dict[str, Any]:
        """
        生成角色记忆
        
        Args:
            character_data: 角色数据
            memory_type: 记忆类型（education, work, family, hobby, trauma, achievement）
            
        Returns:
            记忆数据字典
        """
        system_prompt = f"""
        You are a memory generation assistant. Your task is to create a detailed {memory_type} memory for the character.
        The memory should be consistent with the character's background, personality, and values.
        
        Respond with a JSON object containing:
        1. title: A short title for the memory
        2. content: Detailed description of the memory
        3. time: When this memory occurred (year or age)
        4. emotion: The emotional impact of this memory (positive, negative, neutral)
        5. importance: How important this memory is to the character (1-10)
        """
        
        # 构建角色信息提示
        character_info = json.dumps(character_data, ensure_ascii=False, indent=2)
        user_prompt = f"Generate a {memory_type} memory for this character:\n\n{character_info}"
        
        return self.client.generate_structured_response(system_prompt, user_prompt)
    
    def generate_dialogue_response(self, 
                                  character_data: Dict[str, Any], 
                                  user_input: str, 
                                  conversation_history: List[Dict[str, str]] = None,
                                  relevant_memories: List[Dict[str, Any]] = None) -> str:
        """
        生成对话响应
        
        Args:
            character_data: 角色数据
            user_input: 用户输入
            conversation_history: 对话历史
            relevant_memories: 相关记忆
            
        Returns:
            生成的响应文本
        """
        # 构建系统提示
        character_info = json.dumps(character_data, ensure_ascii=False, indent=2)
        system_prompt = f"""
        You are roleplaying as the character described below. Respond to the user's input in a way that is consistent with this character's personality, background, values, and speech patterns.
        
        Character information:
        {character_info}
        """
        
        # 添加对话历史
        history_text = ""
        if conversation_history:
            history_text = "Conversation history:\n"
            for msg in conversation_history:
                if msg["role"] == "user":
                    history_text += f"User: {msg['content']}\n"
                else:
                    history_text += f"Character: {msg['content']}\n"
        
        # 添加相关记忆
        memories_text = ""
        if relevant_memories:
            memories_text = "Relevant memories (use these to inform your response):\n"
            for memory in relevant_memories:
                memories_text += f"- {memory.get('title', '')}: {memory.get('content', '')}\n"
        
        # 构建用户提示
        user_prompt = f"{history_text}\n{memories_text}\nUser: {user_input}\n\nRespond as the character:"
        
        return self.client.generate_response(system_prompt, user_prompt)


# 测试代码
if __name__ == "__main__":
    # 设置API密钥和基础URL
    api_key = os.environ.get("OPENAI_API_KEY")
    base_url = os.environ.get("OPENAI_BASE_URL")
    
    if not api_key:
        print("请设置OPENAI_API_KEY环境变量")
        exit(1)
    
    # 创建客户端
    character_llm = CharacterLLM(OpenAIClient(api_key=api_key, base_url=base_url))
    
    # 测试角色生成
    character = character_llm.generate_character("一位生活在90年代上海的退休语文教师，性格温和，喜欢读书写字")
    print("生成的角色:")
    print(json.dumps(character, ensure_ascii=False, indent=2))
    
    # 测试记忆生成
    memory = character_llm.generate_memory(character, "education")
    print("\n生成的记忆:")
    print(json.dumps(memory, ensure_ascii=False, indent=2))
    
    # 测试对话生成
    response = character_llm.generate_dialogue_response(
        character, 
        "您好，请问您在教学生涯中最难忘的一件事是什么？",
        relevant_memories=[memory]
    )
    print("\n生成的对话响应:")
    print(response)
