# 角色化大语言模型知识库管理系统 - 完整版

一个支持角色建模、记忆管理和智能对话的AI框架，基于大语言模型和向量数据库实现。

## 系统架构

系统由四个核心模块组成：

1. **角色建模模块**：从自然语言描述自动生成结构化的角色人设，包括基本信息、OCEAN五维人格特征量化、语言风格和价值观建模。
2. **记忆管理模块**：为每个角色构建专属的知识库，支持多类型记忆事件的自动生成和检索。
3. **任务调度模块**：实现三阶段响应流程（下意识响应、记忆检索、补充响应），模拟人类思维的层次性。
4. **交互层模块**：提供RESTful API接口和Web前端界面，支持角色管理和实时对话交互。

## 技术栈

- **后端**：FastAPI + Python 3.11
- **大语言模型**：OpenAI GPT-4
- **向量数据库**：ChromaDB
- **前端**：React + TypeScript
- **数据集**：PersonaHub（角色数据集）

## 功能特点

- **自动角色生成**：从简单描述自动生成丰富的角色人设
- **记忆向量化存储**：使用向量数据库高效存储和检索角色记忆
- **三阶段响应流程**：模拟人类思维的层次性，提供更自然的对话体验
- **实时对话交互**：支持与角色进行实时对话，角色会基于人设和记忆做出反应

## 安装与使用

### 环境要求

- Python 3.11+
- Node.js 18+
- OpenAI API密钥

### 安装步骤

1. 克隆仓库

```bash
git clone https://github.com/yourusername/character-llm-framework.git
cd character-llm-framework
```

2. 安装后端依赖

```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

3. 设置环境变量

```bash
export OPENAI_API_KEY=your_api_key  # Windows: set OPENAI_API_KEY=your_api_key
```

4. 下载数据集（可选）

```bash
python scripts/download_datasets.py
```

5. 启动后端服务

```bash
python run_full.py
```

6. 安装并启动前端（可选）

```bash
cd frontend/character-llm-frontend
npm install
npm run dev
```

7. 访问系统

- API文档：http://localhost:8000/docs
- 前端界面：http://localhost:5173

## 系统演示

### 角色生成

通过简单的自然语言描述，系统可以自动生成丰富的角色人设：

```
输入: "一位生活在90年代上海的退休语文教师，性格温和，喜欢读书写字"

输出: {
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
```

### 记忆生成

系统会自动为角色生成多种类型的记忆：

```
[教育经历] 大学毕业
1965年从北京师范大学中文系毕业，成为一名光荣的人民教师。

[工作经历] 教学成就
1980年被评为市级优秀教师，获得表彰。

[家庭生活] 女儿出生
1970年女儿出生，取名丽华，全家欢喜。
```

### 对话示例

用户与角色的对话示例：

```
用户: 您好，苏老师！请问您在教学生涯中最难忘的一件事是什么？

[下意识响应]:
您好！很高兴与您交流。在我四十年的教学生涯中，难忘的事情实在太多了。不过要说最难忘的，应该是我在1985年带的那届高三毕业班。那是一个特别调皮但又非常有潜力的班级。开学第一天，我就发现班上有几个男生总是不守纪律，上课讲小话，作业也不认真完成。

[补充响应]:
您好！很高兴与您交流。在我四十年的教学生涯中，难忘的事情实在太多了。不过要说最难忘的，那应该是1980年我指导的学生李明在全国中学生作文比赛中获得一等奖的经历。

那个孩子原本并不起眼，在班上成绩中等，但他有着敏锐的观察力和独特的思考方式。我发现了他的潜力，便特别关注他的写作，经常利用课余时间指导他。记得他获奖那天，他抱着奖状跑来找我，眼睛里闪烁着泪光，说："苏老师，这是我们共同的荣誉。"那一刻，我感到作为一名教师的所有辛苦都是值得的。

这件事让我明白，教育不仅是传授知识，更重要的是发现每个学生的闪光点，帮助他们绽放自己的光彩。这也是我一直以来坚持的教育理念。
```

## API文档

系统提供了完整的RESTful API，详细文档可通过访问 `/docs` 路径获取。

主要API端点：

- `POST /api/v1/characters/generate`：生成角色
- `GET /api/v1/characters`：获取所有角色
- `GET /api/v1/characters/{character_id}`：获取特定角色
- `GET /api/v1/characters/{character_id}/memories`：获取角色记忆
- `POST /api/v1/chat`：与角色对话

## 项目结构

```
character_llm_framework/
├── app/
│   ├── api/
│   │   └── endpoints/
│   │       ├── chat.py           # 对话API端点
│   │       └── character.py      # 角色管理API端点
│   ├── core/
│   │   ├── llm/
│   │   │   ├── openai_client.py  # OpenAI API客户端
│   │   │   └── prompts.py        # 提示模板管理
│   │   ├── character/
│   │   │   ├── generator.py      # 角色生成器
│   │   │   └── parser.py         # 角色解析器
│   │   ├── memory/
│   │   │   ├── vector_store.py   # 向量存储管理
│   │   │   ├── embeddings.py     # 文本嵌入处理
│   │   │   └── retriever.py      # 记忆检索器
│   │   └── response/
│   │       ├── flow.py           # 三阶段响应流程
│   │       └── generator.py      # 响应生成器
│   ├── db/
│   │   ├── chroma_client.py      # ChromaDB客户端
│   │   └── models.py             # 数据库模型
│   ├── schemas/
│   │   ├── character.py          # 角色模式
│   │   └── memory.py             # 记忆模式
│   └── main_full.py              # 完整版主应用
├── data/
│   ├── personas/                 # 角色数据集
│   └── memories/                 # 记忆数据集
├── scripts/
│   ├── download_datasets.py      # 数据集下载脚本
│   └── preprocess_data.py        # 数据预处理脚本
├── tests/
│   ├── test_character.py         # 角色模块测试
│   ├── test_memory.py            # 记忆模块测试
│   └── test_response.py          # 响应模块测试
├── frontend/                     # 前端应用
├── .env.example                  # 环境变量示例
├── requirements.txt              # 项目依赖
└── README.md                     # 项目文档
```

## 与演示版的区别

本完整版与演示版的主要区别：

1. **真实LLM集成**：使用OpenAI GPT-4替代模板化的角色生成和对话生成
2. **向量数据库集成**：使用ChromaDB实现高效的向量检索和记忆管理
3. **数据集支持**：集成PersonaHub等数据集用于角色人设和事件生成
4. **完整的三阶段响应**：实现真实的下意识响应、异步记忆检索和补充响应流程
5. **高级记忆检索**：基于语义相似度的记忆检索，而非简单关键词匹配

## 扩展与定制

系统设计为模块化架构，可以轻松扩展和定制：

1. **替换LLM**：可以替换为其他大语言模型，如Claude、Llama等
2. **替换向量数据库**：可以使用其他向量数据库，如Pinecone、Milvus等
3. **添加新的记忆类型**：可以扩展记忆类型，如技能、知识等
4. **自定义前端**：可以根据需要定制前端界面

## 许可证

MIT

## 联系方式

如有问题或建议，请联系：your-email@example.com
