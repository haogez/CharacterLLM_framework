import { useState, useEffect } from 'react'
import { Button } from '@/components/ui/button.jsx'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card.jsx'
import { Input } from '@/components/ui/input.jsx'
import { Textarea } from '@/components/ui/textarea.jsx'
import { Badge } from '@/components/ui/badge.jsx'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs.jsx'
import { ScrollArea } from '@/components/ui/scroll-area.jsx'
import { Separator } from '@/components/ui/separator.jsx'
import { User, Bot, Plus, MessageCircle, Brain, Database } from 'lucide-react'
import './App.css'

// 使用相对路径，这样前端会自动向当前域名发送API请求
const API_BASE_URL = '/api/v1'

function App() {
  const [characters, setCharacters] = useState([])
  const [selectedCharacter, setSelectedCharacter] = useState(null)
  const [chatMessages, setChatMessages] = useState([])
  const [newMessage, setNewMessage] = useState('')
  const [characterDescription, setCharacterDescription] = useState('')
  const [isGenerating, setIsGenerating] = useState(false)
  const [isSending, setIsSending] = useState(false)
  const [activeTab, setActiveTab] = useState('create')

  // 获取所有角色
  const fetchCharacters = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/characters`)
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`)
      }
      const data = await response.json()
      setCharacters(data)
    } catch (error) {
      console.error('获取角色列表失败:', error)
    }
  }

  // 生成角色
  const generateCharacter = async () => {
    if (!characterDescription.trim()) return
    
    setIsGenerating(true)
    try {
      const response = await fetch(`${API_BASE_URL}/characters/generate`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ description: characterDescription }),
      })
      
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`)
      }
      
      const data = await response.json()
      setCharacters(prev => [...prev, data])
      setCharacterDescription('')
      setActiveTab('manage')
    } catch (error) {
      console.error('生成角色失败:', error)
    } finally {
      setIsGenerating(false)
    }
  }

  // 发送消息
  const sendMessage = async () => {
    if (!newMessage.trim() || !selectedCharacter) return
    
    const userMessage = {
      role: 'user',
      content: newMessage,
    }
    
    setChatMessages(prev => [...prev, userMessage])
    setNewMessage('')
    setIsSending(true)
    
    try {
      const response = await fetch(`${API_BASE_URL}/chat`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          character_id: selectedCharacter.id,
          message: userMessage.content,
          conversation_history: chatMessages,
        }),
      })
      
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`)
      }
      
      const data = await response.json()
      
      // 添加下意识响应
      if (data.instinctive_response) {
        setChatMessages(prev => [...prev, {
          role: 'assistant',
          content: data.instinctive_response,
          type: 'instinctive'
        }])
      }
      
      // 如果有补充响应，等待一段时间后添加
      if (data.supplementary_response) {
        setTimeout(() => {
          setChatMessages(prev => [...prev, {
            role: 'assistant',
            content: data.supplementary_response,
            type: 'supplementary'
          }])
        }, 2000)
      }
    } catch (error) {
      console.error('发送消息失败:', error)
      setChatMessages(prev => [...prev, {
        role: 'system',
        content: '消息发送失败，请重试。',
      }])
    } finally {
      setIsSending(false)
    }
  }

  // 选择角色
  const selectCharacter = (character) => {
    setSelectedCharacter(character)
    setChatMessages([])
    setActiveTab('chat')
  }

  // 初始加载
  useEffect(() => {
    fetchCharacters()
  }, [])

  return (
    <div className="container">
      <header className="header">
        <h1>角色化大语言模型知识库管理系统</h1>
      </header>
      
      <main className="main">
        <Tabs value={activeTab} onValueChange={setActiveTab} className="tabs">
          <TabsList className="tabs-list">
            <TabsTrigger value="create">
              <Plus className="icon" />
              创建角色
            </TabsTrigger>
            <TabsTrigger value="manage">
              <Database className="icon" />
              角色管理
            </TabsTrigger>
            <TabsTrigger value="chat" disabled={!selectedCharacter}>
              <MessageCircle className="icon" />
              智能对话
            </TabsTrigger>
          </TabsList>
          
          <TabsContent value="create" className="tab-content">
            <Card>
              <CardHeader>
                <CardTitle>创建新角色</CardTitle>
                <CardDescription>
                  输入角色描述，系统将自动生成角色人设和记忆
                </CardDescription>
              </CardHeader>
              <CardContent>
                <div className="form-group">
                  <label htmlFor="character-description">角色描述</label>
                  <Textarea
                    id="character-description"
                    placeholder="例如：一位生活在90年代上海的退休语文教师，性格温和，喜欢读书写字"
                    value={characterDescription}
                    onChange={(e) => setCharacterDescription(e.target.value)}
                    rows={5}
                  />
                </div>
                <Button 
                  onClick={generateCharacter} 
                  disabled={isGenerating || !characterDescription.trim()}
                  className="submit-button"
                >
                  {isGenerating ? '生成中...' : '生成角色'}
                </Button>
              </CardContent>
            </Card>
          </TabsContent>
          
          <TabsContent value="manage" className="tab-content">
            <Card>
              <CardHeader>
                <CardTitle>角色管理</CardTitle>
                <CardDescription>
                  查看和管理已创建的角色
                </CardDescription>
              </CardHeader>
              <CardContent>
                {characters.length === 0 ? (
                  <div className="empty-state">
                    <p>暂无角色，请先创建角色</p>
                    <Button onClick={() => setActiveTab('create')}>创建角色</Button>
                  </div>
                ) : (
                  <div className="character-list">
                    {characters.map((character) => (
                      <div key={character.id} className="character-item">
                        <div className="character-info">
                          <h3>{character.name}</h3>
                          <p>{character.occupation}, {character.age}岁</p>
                          <div className="personality">
                            <Badge>开放性: {character.personality?.openness || 0}</Badge>
                            <Badge>尽责性: {character.personality?.conscientiousness || 0}</Badge>
                            <Badge>外向性: {character.personality?.extraversion || 0}</Badge>
                            <Badge>宜人性: {character.personality?.agreeableness || 0}</Badge>
                            <Badge>神经质: {character.personality?.neuroticism || 0}</Badge>
                          </div>
                        </div>
                        <Button onClick={() => selectCharacter(character)}>开始对话</Button>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          </TabsContent>
          
          <TabsContent value="chat" className="tab-content">
            {selectedCharacter && (
              <div className="chat-container">
                <div className="chat-header">
                  <div className="character-brief">
                    <h2>{selectedCharacter.name}</h2>
                    <p>{selectedCharacter.occupation}, {selectedCharacter.age}岁</p>
                  </div>
                </div>
                
                <ScrollArea className="chat-messages">
                  {chatMessages.length === 0 ? (
                    <div className="chat-empty">
                      <Brain size={48} />
                      <p>开始与{selectedCharacter.name}对话吧！</p>
                    </div>
                  ) : (
                    chatMessages.map((msg, index) => (
                      <div 
                        key={index} 
                        className={`message ${msg.role === 'user' ? 'user-message' : 'assistant-message'}`}
                      >
                        <div className="message-avatar">
                          {msg.role === 'user' ? <User /> : <Bot />}
                        </div>
                        <div className="message-content">
                          {msg.type === 'supplementary' && (
                            <Badge variant="outline" className="message-badge">
                              补充回复
                            </Badge>
                          )}
                          {msg.type === 'instinctive' && (
                            <Badge variant="outline" className="message-badge">
                              即时回复
                            </Badge>
                          )}
                          <p>{msg.content}</p>
                        </div>
                      </div>
                    ))
                  )}
                </ScrollArea>
                
                <div className="chat-input">
                  <Input
                    placeholder={`向${selectedCharacter.name}发送消息...`}
                    value={newMessage}
                    onChange={(e) => setNewMessage(e.target.value)}
                    onKeyPress={(e) => e.key === 'Enter' && !e.shiftKey && sendMessage()}
                    disabled={isSending}
                  />
                  <Button 
                    onClick={sendMessage} 
                    disabled={isSending || !newMessage.trim()}
                  >
                    {isSending ? '发送中...' : '发送'}
                  </Button>
                </div>
              </div>
            )}
          </TabsContent>
        </Tabs>
      </main>
      
      <footer className="footer">
        <p>角色化大语言模型知识库管理系统 &copy; 2025</p>
      </footer>
    </div>
  )
}

export default App
