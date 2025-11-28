import { useState, useEffect, useRef } from 'react';
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
  const [isProcessing, setIsProcessing] = useState(false); // 新增：处理状态
  const chatContainerRef = useRef(null); // 新增：滚动引用
  const [selectedUserCharacter, setSelectedUserCharacter] = useState(''); // 新增：用户扮演的角色ID
  const [sceneOptions, setSceneOptions] = useState([]);
  const [selectedScene, setSelectedScene] = useState('');
  const [customScene, setCustomScene] = useState('');
  const [dialogueType, setDialogueType] = useState('闲聊');
  const [customDialogueType, setCustomDialogueType] = useState('');

  useEffect(() => {
    loadCharacters();
  }, []);

  // 滚动到底部
  useEffect(() => {
    if (chatContainerRef.current) {
      chatContainerRef.current.scrollTop = chatContainerRef.current.scrollHeight;
    }
  }, [chatHistory]);

  // 加载角色经历过的场景列表
  useEffect(() => {
    if (!selectedCharacter) {
      setSceneOptions([]);
      setSelectedScene('');
      setCustomScene('');
      setCustomDialogueType('');
      return;
    }

    const loadPlaces = async () => {
      try {
        const resp = await fetch(`${API_BASE_URL}/characters/${selectedCharacter}/places`);
        if (!resp.ok) return;
        const data = await resp.json();
        setSceneOptions(data.places || []);
      } catch (err) {
        console.error('加载场景失败', err);
      }
    };

    loadPlaces();
  }, [selectedCharacter]);

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
    setMessage({ type: '', text: '正在生成角色...' });

    try {
      const response = await fetch(`${API_BASE_URL}/characters/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ description }),
      });

      if (!response.ok) throw new Error(`HTTP错误：${response.status}`);

      const data = await response.json();
      
      // 显示生成进度和时间
      const genInfo = data.generation_info;
      let messageText = `角色生成成功！\n`;
      if (genInfo) {
        messageText += `角色生成耗时: ${genInfo.role_gen_time}秒\n`;
        if (genInfo.memory_gen_time) {
          messageText += `记忆生成耗时: ${genInfo.memory_gen_time}秒\n`;
          messageText += `总耗时: ${genInfo.total_time}秒`;
        }
      }
      
      setMessage({ type: 'success', text: messageText });
      setDescription('');
      loadCharacters();
    } catch (error) {
      console.error("角色生成失败原因：", error);
      setMessage({ type: 'error', text: `生成失败: ${error.message}` });
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
    
    // 添加用户消息
    setChatHistory(prev => [...prev, { role: 'user', content: userMessage }]);
    setChatMessage('');
    setIsProcessing(true); // 开始处理

    try {
      // 构造对话历史
      const cleanHistory = chatHistory
        .filter(msg => msg.role === 'user' || msg.role === 'assistant')
        .map(msg => ({ role: msg.role, content: msg.content }));

      // 使用 fetch 发送请求并接收 SSE 响应
      const response = await fetch(`${API_BASE_URL}/chat`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'text/event-stream' // 明确指定接受SSE
        },
        body: JSON.stringify({
          character_id: selectedCharacter,
          message: userMessage,
          conversation_history: cleanHistory,
          user_character_id: selectedUserCharacter || null,
          scene: (selectedScene === 'custom' ? customScene : selectedScene) || null,
          dialogue_type: dialogueType === '自定义' ? customDialogueType : dialogueType || null
        })
      });

      if (!response.ok) throw new Error(`HTTP错误：${response.status}`);

      // 检查 Content-Type 是否为 text/event-stream
      const contentType = response.headers.get('Content-Type');
      if (!contentType || !contentType.includes('text/event-stream')) {
        throw new Error('服务器未返回SSE响应');
      }

      // 创建读取器
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      // 读取 SSE 数据
      try {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          // 解码并添加到缓冲区
          buffer += decoder.decode(value, { stream: true });

          // 按双换行符分割，处理每个事件
          const lines = buffer.split('\n\n');
          buffer = lines.pop(); // 保留不完整的行

          for (const line of lines) {
            if (line.trim() === '') continue;
            
            // 移除 "data: " 前缀（如果存在）
            let eventLine = line.trim();
            if (eventLine.startsWith('data: ')) {
              eventLine = eventLine.substring(6);
            } else if (eventLine.startsWith(' ')) {
              // 如果以空格开头，移除它
              eventLine = eventLine.substring(1);
            }

            try {
              const data = JSON.parse(eventLine);
              
              // 检查是否是错误消息
              if (data.error) {
                throw new Error(data.error);
              }

              // 添加到聊天历史
              const newMessage = {
                role: 'assistant',
                content: data.message,
                type: data.type,
                hasMemories: data.memories?.length > 0,
                timestamp: data.timestamp,
                memories: data.memories
              };

              setChatHistory(prev => [...prev, newMessage]);
            } catch (e) {
              console.error('解析SSE数据失败:', e, '原始数据:', eventLine);
            }
          }
        }
      } finally {
        reader.releaseLock();
      }

    } catch (error) {
      console.error('对话请求失败：', error);
      setChatHistory(prev => [
        ...prev,
        {
          role: 'error',
          content: `对话失败：${error.message}`
        }
      ]);
    } finally {
      setIsProcessing(false); // 结束处理
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
                        <label>选择主角色</label>
                        <select
                          value={selectedCharacter}
                          onChange={(e) => {
                            setSelectedCharacter(e.target.value);
                            setChatHistory([]);
                            // 当主角色改变时，清空用户角色选择
                            setSelectedUserCharacter('');
                          }}
                        >
                          <option value="">请选择一个主角色</option>
                          {characters.map((char) => (
                            <option key={char.id} value={char.id}>
                              {char.name} - {char.occupation}
                            </option>
                          ))}
                        </select>
                      </div>

                      {/* 新增：选择用户扮演的角色 */}
                      <div className="form-group">
                        <label>选择用户扮演的角色 (可选)</label>
                        <select
                          value={selectedUserCharacter}
                          onChange={(e) => setSelectedUserCharacter(e.target.value)}
                          disabled={!selectedCharacter} // 只有选了主角色才能选用户角色
                        >
                          <option value="">以默认用户身份对话</option>
                          {/* 只显示与当前主角色相关的角色 */}
                          {selectedCharacter &&
                            characters
                              .filter(char => char.id !== selectedCharacter) // 排除主角色自己
                              .map((char) => (
                                <option key={char.id} value={char.id}>
                                  {char.name} - {char.occupation}
                                </option>
                              ))}
                        </select>
                      </div>

                      <div className="form-group">
                        <label>选择对话场景</label>
                        <select
                          value={selectedScene}
                          onChange={(e) => setSelectedScene(e.target.value)}
                          disabled={!selectedCharacter}
                        >
                          <option value="">不指定场景</option>
                          {sceneOptions.map((place) => (
                            <option key={place.id} value={place.name}>{place.name}</option>
                          ))}
                          <option value="custom">自定义场景</option>
                        </select>
                        {selectedScene === 'custom' && (
                          <input
                            type="text"
                            placeholder="填写自定义场景"
                            value={customScene}
                            onChange={(e) => setCustomScene(e.target.value)}
                          />
                        )}
                      </div>

                      <div className="form-group">
                        <label>对话类型</label>
                        <select
                          value={dialogueType}
                          onChange={(e) => setDialogueType(e.target.value)}
                        >
                          <option value="闲聊">闲聊</option>
                          <option value="回忆询问">回忆询问</option>
                          <option value="情感安慰">情感安慰</option>
                          <option value="求助建议">求助建议</option>
                          <option value="自定义">自定义</option>
                        </select>
                        {dialogueType === '自定义' && (
                          <input
                            type="text"
                            placeholder="自定义对话类型"
                            value={customDialogueType}
                            onChange={(e) => setCustomDialogueType(e.target.value)}
                          />
                        )}
                      </div>
                      {/* --- */}

                <div className="chat-container">
                  <div className="chat-history" ref={chatContainerRef}>
                    {chatHistory.length === 0 ? (
                      <div className="chat-empty">
                        <div className="chat-empty-icon">💭</div>
                        <p>开始与角色对话吧！</p>
                      </div>
                    ) : (
                      chatHistory.map((msg, index) => {
                        const isUser = msg.role === 'user';
                        const isAssistant = msg.role === 'assistant';
                        const isMemorySearching = msg.role === 'memory-searching';
                        const isError = msg.role === 'error';

                        return (
                          <div 
                            key={index} 
                            className={`chat-message ${isUser ? 'user' : isAssistant ? 'assistant' : isMemorySearching ? 'memory-searching' : isError ? 'error' : 'system'}`}
                          >
                            <div className="message-content">
                              {msg.content}
                              {/* 显示响应时间 */}
                              {isAssistant && msg.timestamp && (
                                <span className="response-time">
                                  （耗时: {msg.timestamp.toFixed(2)}秒）
                                </span>
                              )}
                              {/* 显示关联记忆 */}
                              {isAssistant && msg.memories && msg.memories.length > 0 && (
                                <div className="memory-info">
                                  <details>
                                    <summary>关联记忆 ({msg.memories.length})</summary>
                                    <ul>
                                      {msg.memories.map((mem, idx) => (
                                        <li key={idx}>
                                          <strong>{mem.title}</strong> - {mem.content.substring(0, 50)}...
                                        </li>
                                      ))}
                                    </ul>
                                  </details>
                                </div>
                              )}
                            </div>
                          </div>
                        );
                      })
                    )}
                  </div>

                  <div className="chat-input-container">
                    <input
                      type="text"
                      value={chatMessage}
                      onChange={(e) => setChatMessage(e.target.value)}
                      onKeyPress={(e) => e.key === 'Enter' && !isProcessing && sendMessage()}
                      placeholder="输入消息..."
                      disabled={!selectedCharacter || isProcessing}
                    />
                    <button
                      className="btn btn-primary"
                      onClick={sendMessage}
                      disabled={!selectedCharacter || !chatMessage.trim() || isProcessing}
                    >
                      {isProcessing ? '发送中...' : '发送'}
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