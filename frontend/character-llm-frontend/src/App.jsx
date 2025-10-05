import React, { useState, useEffect } from 'react';
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

    try {
      const response = await fetch(`${API_BASE_URL}/characters/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ description })
      });

      if (!response.ok) throw new Error('生成失败');

      const data = await response.json();
      setMessage({ type: 'success', text: '角色生成成功！' });
      setDescription('');
      loadCharacters();
    } catch (error) {
      setMessage({ type: 'error', text: `生成失败: ${error.message}` });
    } finally {
      setLoading(false);
    }
  };

  const sendMessage = async () => {
    if (!selectedCharacter) {
      alert('请先选择角色');
      return;
    }
    if (!chatMessage.trim()) return;

    const userMessage = chatMessage;
    setChatHistory([...chatHistory, { role: 'user', content: userMessage }]);
    setChatMessage('');

    try {
      const response = await fetch(`${API_BASE_URL}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          character_id: selectedCharacter,
          message: userMessage
        })
      });

      if (!response.ok) throw new Error('对话失败');

      const data = await response.json();
      setChatHistory(prev => [...prev, { role: 'assistant', content: data.response }]);
    } catch (error) {
      setChatHistory(prev => [...prev, { role: 'error', content: `错误: ${error.message}` }]);
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
            <span className="tab-icon">✨</span>
            创建角色
          </button>
          <button
            className={`tab ${activeTab === 'list' ? 'active' : ''}`}
            onClick={() => { setActiveTab('list'); loadCharacters(); }}
          >
            <span className="tab-icon">📚</span>
            角色列表
          </button>
          <button
            className={`tab ${activeTab === 'chat' ? 'active' : ''}`}
            onClick={() => setActiveTab('chat')}
          >
            <span className="tab-icon">💬</span>
            智能对话
          </button>
        </div>

        <div className="content">
          {activeTab === 'create' && (
            <div className="tab-content">
              <div className="card">
                <h2 className="card-title">创建新角色</h2>
                <p className="card-description">
                  输入角色描述，AI将自动生成完整的角色档案，包括性格特征、背景故事等
                </p>
                
                <div className="form-group">
                  <label>角色描述</label>
                  <textarea
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                    placeholder="例如：一位35岁的女医生，温柔善良，喜欢帮助他人，有丰富的临床经验..."
                    rows="5"
                    disabled={loading}
                  />
                </div>

                {message.text && (
                  <div className={`message ${message.type}`}>
                    {message.text}
                  </div>
                )}

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
                          <span className="character-badge">{char.occupation}</span>
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
                        <div className="character-background">
                          <p><strong>背景：</strong>{char.background}</p>
                        </div>
                        {char.speech_style && (
                          <div className="character-style">
                            <p><strong>语言风格：</strong>{char.speech_style}</p>
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
                        <p>选择角色后开始对话</p>
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
                      className="chat-input"
                      value={chatMessage}
                      onChange={(e) => setChatMessage(e.target.value)}
                      onKeyPress={(e) => e.key === 'Enter' && sendMessage()}
                      placeholder="输入消息..."
                      disabled={!selectedCharacter}
                    />
                    <button
                      className="btn btn-primary btn-send"
                      onClick={sendMessage}
                      disabled={!selectedCharacter || !chatMessage.trim()}
                    >
                      发送 📤
                    </button>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>

        <footer className="footer">
          <p>角色化大语言模型知识库管理系统 © 2025</p>
        </footer>
      </div>
    </div>
  );
}

export default App;
