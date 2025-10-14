import { useState, useEffect } from 'react';
import './App.css';

const API_BASE_URL = '/api/v1';

function App() {
  const [activeTab, setActiveTab] = useState('create');
  const [characters, setCharacters] = useState([]);
  const [description, setDescription] = useState('');
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState({ type: '', text: '' });
  const [selectedCharacter, setSelectedCharacter] = useState('');
  const [chatMessage, setChatMessage] = useState('');
  const [chatHistory, setChatHistory] = useState([]);

  useEffect(() => {
    loadCharacters();
  }, []);

  const loadCharacters = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/characters`);
      const data = await response.json();
      setCharacters(data);
    } catch (error) {
      console.error('加载角色失败:', error);
    }
  };

  const generateCharacter = async () => {
    if (!description.trim()) {
    setMessage({ type: 'error', text: '请输入角色描述' });
    return;
    }

    setLoading(true);
    setMessage({ type: '', text: '' });

    // // 1. 创建超时控制器（30秒超时）
    // const controller = new AbortController();
    // const timeoutId = setTimeout(() => controller.abort(), 30000); // 30秒后取消请求

    try {
      const response = await fetch(`${API_BASE_URL}/characters/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ description }),
        // signal: controller.signal, // 关联超时控制器
      });

      // clearTimeout(timeoutId); // 清除超时定时器（如果请求提前完成）

      if (!response.ok) throw new Error(`HTTP错误：${response.status}`);

      const data = await response.json();
      setMessage({ type: 'success', text: '角色生成成功！' });
      setDescription('');
      loadCharacters();
    } catch (error) {
      console.error("角色生成失败原因：", error); // 新增：打印错误详情
      // 区分“超时错误”和“其他错误”
      if (error.name === 'AbortError') {
        setMessage({ type: 'error', text: '角色生成超时，请稍后重试' });
      } else {
        setMessage({ type: 'error', text: `生成失败: ${error.message}` });
      }
    } finally {
      setLoading(false);
    }
  };

  const deleteCharacter = async (characterId) => {
    if (!confirm('确定要删除这个角色吗？')) {
      return;
    }

    try {
      const response = await fetch(`${API_BASE_URL}/characters/${characterId}`, {
        method: 'DELETE'
      });

      if (!response.ok) throw new Error('删除失败');

      setMessage({ type: 'success', text: '角色删除成功！' });
      loadCharacters();
      
      // 如果删除的是当前选中的角色，清空选择
      if (selectedCharacter === characterId) {
        setSelectedCharacter('');
        setChatHistory([]);
      }
    } catch (error) {
      setMessage({ type: 'error', text: `删除失败: ${error.message}` });
    }
  };

  const sendMessage = async () => {
    if (!selectedCharacter) {
      alert('请先选择角色');
      return;
    }
    if (!chatMessage.trim()) return;

    const userMessage = chatMessage;
    // 1. 记录当前聊天记录长度（用于“思考中”占位的索引）
    const thinkingIndex = chatHistory.length;
    // 2. 添加用户消息和“思考中”占位
    setChatHistory([
      ...chatHistory,
      { role: 'user', content: userMessage },
      { role: 'thinking', content: '正在思考...' }
    ]);
    setChatMessage('');

    try {
      // 3. 构造对话历史（过滤并格式化）
      const cleanHistory = chatHistory
        .filter(msg => msg.role === 'user' || msg.role === 'assistant')
        .map(msg => ({ role: msg.role, content: msg.content }));

      // 4. 发起对话请求
      const response = await fetch(`${API_BASE_URL}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          character_id: selectedCharacter,
          message: userMessage,
          conversation_history: cleanHistory
        })
      });

      if (!response.ok) throw new Error(`HTTP错误：${response.status}`);
      const chatResponses = await response.json(); // 后端返回的响应数组

      // 5. 处理所有响应
      let updatedHistory = [...chatHistory, { role: 'user', content: userMessage }]; // 基于用户消息初始化
      for (const resp of chatResponses) {
        switch (resp.type) {
          case 'immediate':
            updatedHistory.push({
              role: 'assistant',
              content: resp.message,
              type: resp.type,
              hasMemories: resp.memories?.length > 0
            });
            updatedHistory.push({
              role: 'memory-searching',
              content: '🔍 正在检索相关记忆，准备补充回答...'
            });
            break;
          case 'supplementary':
            updatedHistory = updatedHistory.map((msg, idx) => 
              idx === thinkingIndex + 1 // 替换“思考中”后的“记忆检索中”提示
                ? {
                    role: 'assistant',
                    content: resp.message + (resp.memories ? `\n\n（关联记忆：${resp.memories[0].title}）` : ''),
                    type: resp.type,
                    hasMemories: resp.memories?.length > 0
                  }
                : msg
            );
            break;
          case 'direct':
          case 'no_memory':
            updatedHistory.push({
              role: 'assistant',
              content: resp.message,
              type: resp.type,
              hasMemories: resp.memories?.length > 0
            });
            break;
          default:
            updatedHistory.push({
              role: 'assistant',
              content: `[未知类型] ${resp.message}`,
              type: 'unknown'
            });
        }
      }

      // 6. 移除“思考中”占位，更新最终聊天记录
      setChatHistory(
        updatedHistory.filter(msg => msg.role !== 'thinking')
      );

    } catch (error) {
      console.error('对话请求失败：', error);
      setChatHistory(prev => 
        prev.filter(msg => msg.role !== 'thinking').concat({
          role: 'error',
          content: `对话失败：${error.message}`
        })
      );
    }
  };

  return (
    <div className="app">
      <div className="container">
        <header className="header">
          <div className="header-content">
            <div className="logo">
              <span className="logo-icon">🤖</span>
              <h1>角色化大语言模型知识库管理系统</h1>
            </div>
            <p className="subtitle">基于大语言模型的智能角色生成与对话系统</p>
          </div>
        </header>

        <div className="tabs">
          <button
            className={`tab ${activeTab === 'create' ? 'active' : ''}`}
            onClick={() => setActiveTab('create')}
          >
            <span>✨</span>
            创建角色
          </button>
          <button
            className={`tab ${activeTab === 'list' ? 'active' : ''}`}
            onClick={() => setActiveTab('list')}
          >
            <span>📋</span>
            角色列表
          </button>
          <button
            className={`tab ${activeTab === 'chat' ? 'active' : ''}`}
            onClick={() => setActiveTab('chat')}
          >
            <span>💬</span>
            智能对话
          </button>
        </div>

        <main className="main-content">
          {message.text && (
            <div className={`message ${message.type}`}>
              {message.text}
            </div>
          )}

          {activeTab === 'create' && (
            <div className="tab-content">
              <div className="card">
                <h2 className="card-title">创建新角色</h2>
                <p className="card-description">
                  输入角色描述，系统将自动生成详细的角色档案，

包括性格、背景、语言风格等。
                </p>

                <div className="form-group">
                  <label htmlFor="description">角色描述</label>
                  <textarea
                    id="description"
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                    placeholder="例如：一位35岁的女医生，温柔体贴，有丰富的临床经验..."
                    rows="5"
                  />
                </div>

                <button
                  className="btn btn-primary"
                  onClick={generateCharacter}
                  disabled={loading}
                >
                  {loading ? (
                    <>
                      <span className="spinner"></span>
                      生成中...
                    </>
                  ) : (
                    <>
                      <span>✨</span>
                      生成角色
                    </>
                  )}
                </button>
              </div>
            </div>
          )}

          {activeTab === 'list' && (
            <div className="tab-content">
              <div className="card">
                <div className="card-header">
                  <h2 className="card-title">角色列表</h2>
                  <button className="btn btn-secondary" onClick={loadCharacters}>
                    🔄 刷新
                  </button>
                </div>

                {characters.length === 0 ? (
                  <div className="empty-state">
                    <div className="empty-icon">📭</div>
                    <h3>还没有创建角色</h3>
                    <p>点击"创建角色"标签页开始创建您的第一个角色吧！</p>
                  </div>
                ) : (
                  <div className="character-grid">
                    {characters.map((char) => (
                      <div key={char.id} className="character-card">
                        <div className="character-header">
                          <h3>{char.name}</h3>
                          <div className="character-header-actions">
                            <span className="character-badge">{char.occupation}</span>
                            <button
                              className="btn-delete"
                              onClick={() => deleteCharacter(char.id)}
                              title="删除角色"
                            >
                              🗑️
                            </button>
                          </div>
                        </div>
                        
                        <div className="character-info">
                          <div className="info-item">
                            <span className="info-label">年龄</span>
                            <span className="info-value">{char.age}岁</span>
                          </div>
                          <div className="info-item">
                            <span className="info-label">性别</span>
                            <span className="info-value">{char.gender}</span>
                          </div>
                        </div>
                        
                        <div className="character-section">
                          <h4>背景故事</h4>
                          <p>{char.background}</p>
                        </div>
                        
                        {char.speech_style && (
                          <div className="character-section">
                            <h4>语言风格</h4>
                            <p>{char.speech_style}</p>
                          </div>
                        )}
                        
                        {char.personality && (
                          <div className="character-section">
                            <h4>性格特征 (OCEAN模型)</h4>
                            <div className="personality-traits">
                              <div className="trait-item">
                                <span className="trait-label">开放性</span>
                                <div className="trait-bar">
                                  <div 
                                    className="trait-fill" 
                                    style={{width: `${char.personality.openness}%`}}
                                  ></div>
                                </div>
                                <span className="trait-value">{char.personality.openness}</span>
                              </div>
                              <div className="trait-item">
                                <span className="trait-label">尽责性</span>
                                <div className="trait-bar">
                                  <div 
                                    className="trait-fill" 
                                    style={{width: `${char.personality.conscientiousness}%`}}
                                  ></div>
                                </div>
                                <span className="trait-value">{char.personality.conscientiousness}</span>
                              </div>
                              <div className="trait-item">
                                <span className="trait-label">外向性</span>
                                <div className="trait-bar">
                                  <div 
                                    className="trait-fill" 
                                    style={{width: `${char.personality.extraversion}%`}}
                                  ></div>
                                </div>
                                <span className="trait-value">{char.personality.extraversion}</span>
                              </div>
                              <div className="trait-item">
                                <span className="trait-label">宜人性</span>
                                <div className="trait-bar">
                                  <div 
                                    className="trait-fill" 
                                    style={{width: `${char.personality.agreeableness}%`}}
                                  ></div>
                                </div>
                                <span className="trait-value">{char.personality.agreeableness}</span>
                              </div>
                              <div className="trait-item">
                                <span className="trait-label">神经质</span>
                                <div className="trait-bar">
                                  <div 
                                    className="trait-fill" 
                                    style={{width: `${char.personality.neuroticism}%`}}
                                  ></div>
                                </div>
                                <span className="trait-value">{char.personality.neuroticism}</span>
                              </div>
                            </div>
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}

          {activeTab === 'chat' && (
            <div className="tab-content">
              <div className="card">
                <h2 className="card-title">智能对话</h2>
                
                <div className="form-group">
                  <label>选择角色</label>
                  <select
                    value={selectedCharacter}
                    onChange={(e) => {
                      setSelectedCharacter(e.target.value);
                      setChatHistory([]);
                    }}
                  >
                    <option value="">请选择一个角色</option>
                    {characters.map((char) => (
                      <option key={char.id} value={char.id}>
                        {char.name} - {char.occupation}
                      </option>
                    ))}
                  </select>
                </div>

                <div className="chat-container">
                  <div className="chat-history">
                    {chatHistory.length === 0 ? (
                      <div className="chat-empty">
                        <div className="chat-empty-icon">💭</div>
                        <p>开始与角色对话吧！</p>
                      </div>
                    ) : (
                      chatHistory.map((msg, index) => (
                        <div key={index} className={`chat-message ${msg.role}`}>
                          <div className="message-content">{msg.content}</div>
                        </div>
                      ))
                    )}
                  </div>

                  <div className="chat-input-container">
                    <input
                      type="text"
                      value={chatMessage}
                      onChange={(e) => setChatMessage(e.target.value)}
                      onKeyPress={(e) => e.key === 'Enter' && sendMessage()}
                      placeholder="输入消息..."
                      disabled={!selectedCharacter}
                    />
                    <button
                      className="btn btn-primary"
                      onClick={sendMessage}
                      disabled={!selectedCharacter || !chatMessage.trim()}
                    >
                      发送
                    </button>
                  </div>
                </div>
              </div>
            </div>
          )}
        </main>

        <footer className="footer">
          <p>© 2024 角色化大语言模型知识库管理系统 | 基于 FastAPI + React</p>
        </footer>
      </div>
    </div>
  );
}

export default App;
