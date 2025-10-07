from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

class CharacterBase(BaseModel):
    """角色基础模式"""
    name: str = Field(..., description="角色姓名")
    age: Optional[int] = Field(None, description="年龄")
    occupation: Optional[str] = Field(None, description="职业")
    region: Optional[str] = Field(None, description="地域")
    
    # OCEAN五维人格模型
    ocean_openness: float = Field(0.5, ge=0, le=1, description="开放性")
    ocean_conscientiousness: float = Field(0.5, ge=0, le=1, description="尽责性")
    ocean_extraversion: float = Field(0.5, ge=0, le=1, description="外向性")
    ocean_agreeableness: float = Field(0.5, ge=0, le=1, description="宜人性")
    ocean_neuroticism: float = Field(0.5, ge=0, le=1, description="神经质")
    
    # 角色特征
    language_style: Optional[str] = Field(None, description="语言风格")
    values_and_taboos: Optional[str] = Field(None, description="价值观与禁忌")
    behavioral_boundaries: Optional[str] = Field(None, description="行为边界")

class CharacterCreate(CharacterBase):
    """创建角色的请求模式"""
    pass

class CharacterUpdate(BaseModel):
    """更新角色的请求模式"""
    name: Optional[str] = None
    age: Optional[int] = None
    occupation: Optional[str] = None
    region: Optional[str] = None
    ocean_openness: Optional[float] = Field(None, ge=0, le=1)
    ocean_conscientiousness: Optional[float] = Field(None, ge=0, le=1)
    ocean_extraversion: Optional[float] = Field(None, ge=0, le=1)
    ocean_agreeableness: Optional[float] = Field(None, ge=0, le=1)
    ocean_neuroticism: Optional[float] = Field(None, ge=0, le=1)
    language_style: Optional[str] = None
    values_and_taboos: Optional[str] = None
    behavioral_boundaries: Optional[str] = None

class Character(CharacterBase):
    """角色响应模式"""
    id: int
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True

class CharacterGenerationRequest(BaseModel):
    """角色生成请求模式"""
    description: str = Field(..., description="角色描述")

class ChatRequest(BaseModel):
    """对话请求模式"""
    character_id: str = Field(..., description="角色ID（UUID字符串）")
    message: str = Field(..., description="用户消息")
    conversation_history: Optional[list] = Field(default=[], description="对话历史")

class ChatResponse(BaseModel):
    """对话响应模式"""
    message: str = Field(..., description="角色回复")
    type: str = Field(..., description="响应类型: immediate, supplementary")
    memories: Optional[list] = Field(None, description="使用的记忆")
