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

const API_BASE_URL = 'http://localhost:8000/api/v1'

function App() {
  const [characters, setCharacters] = useState([])
  const [selectedCharacter, setSelectedCharacter] = useState(null)
  const [chatMessages, setChatMessages] = useState([])
  const [newMessage, setNewMessage] = useState('')
  const [characterDescription, setCharacterDescription] = useState('')
  const [isGenerating, setIsGenerating] = useState(false)
  const [isChatting, setIsChatting] = useState(false)

  // 获取角色列表
  const fetchCharacters = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/characters`)
      if (response.ok) {
        const data = await response.json()
        setCharacters(data)
      }
    } catch (error) {
      console.error('获取角色列表失败:', error)
    }
  }

  // 生成新角色
  const generateCharacter = async () => {
    if (!characterDescription.trim()) return
    
    setIsGenerating(true)
    try {
      const response = await fetch(`${API_BASE_URL}/characters/generate`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          description: characterDescription
        })
      })
      
      if (response.ok) {
        const newCharacter = await response.json()
        setCharacters(prev => [...prev, newCharacter])
        setCharacterDescription('')
        setSelectedCharacter(newCharacter)
      }
    } catch (error) {
      console.error('生成角色失败:', error)
    } finally {
      setIsGenerating(false)
    }
  }

  // 发送消息
  const sendMessage = async () => {
    if (!newMessage.trim() || !selectedCharacter) return
    
    const userMessage = { role: 'user', content: newMessage, timestamp: new Date() }
    setChatMessages(prev => [...prev, userMessage])
    setNewMessage('')
    setIsChatting(true)

    try {
      const response = await fetch(`${API_BASE_URL}/chat`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          character_id: selectedCharacter.id,
          message: newMessage
        })
      })
      
      if (response.ok) {
        const chatResponse = await response.json()
        const botMessage = {
          role: 'assistant',
          content: chatResponse.response,
          timestamp: new Date(chatResponse.timestamp),
          responseType: chatResponse.response_type
        }
        setChatMessages(prev => [...prev, botMessage])
      }
    } catch (error) {
      console.error('发送消息失败:', error)
    } finally {
      setIsChatting(false)
    }
  }

  // 选择角色时清空聊天记录
  const selectCharacter = (character) => {
    setSelectedCharacter(character)
    setChatMessages([])
  }

  useEffect(() => {
    fetchCharacters()
  }, [])

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100 dark:from-gray-900 dark:to-gray-800">
      <div className="container mx-auto p-6">
        <div className="text-center mb-8">
          <h1 className="text-4xl font-bold text-gray-900 dark:text-white mb-2">
            角色化大语言模型知识库管理系统
          </h1>
          <p className="text-lg text-gray-600 dark:text-gray-300">
            智能角色建模 • 记忆管理 • 自然对话
          </p>
        </div>

        <Tabs defaultValue="chat" className="w-full">
          <TabsList className="grid w-full grid-cols-3">
            <TabsTrigger value="chat" className="flex items-center gap-2">
              <MessageCircle className="w-4 h-4" />
              智能对话
            </TabsTrigger>
            <TabsTrigger value="characters" className="flex items-center gap-2">
              <User className="w-4 h-4" />
              角色管理
            </TabsTrigger>
            <TabsTrigger value="create" className="flex items-center gap-2">
              <Plus className="w-4 h-4" />
              创建角色
            </TabsTrigger>
          </TabsList>

          <TabsContent value="chat" className="space-y-4">
            <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
              {/* 角色选择面板 */}
              <Card className="lg:col-span-1">
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <User className="w-5 h-5" />
                    选择角色
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <ScrollArea className="h-64">
                    <div className="space-y-2">
                      {characters.map((character) => (
                        <Button
                          key={character.id}
                          variant={selectedCharacter?.id === character.id ? "default" : "outline"}
                          className="w-full justify-start"
                          onClick={() => selectCharacter(character)}
                        >
                          <div className="text-left">
                            <div className="font-medium">{character.name}</div>
                            <div className="text-xs text-muted-foreground">
                              {character.occupation} • {character.region}
                            </div>
                          </div>
                        </Button>
                      ))}
                    </div>
                  </ScrollArea>
                </CardContent>
              </Card>

              {/* 聊天界面 */}
              <Card className="lg:col-span-3">
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <Bot className="w-5 h-5" />
                    {selectedCharacter ? `与 ${selectedCharacter.name} 对话` : '请选择一个角色开始对话'}
                  </CardTitle>
                  {selectedCharacter && (
                    <CardDescription>
                      {selectedCharacter.age}岁 • {selectedCharacter.occupation} • {selectedCharacter.region}
                    </CardDescription>
                  )}
                </CardHeader>
                <CardContent>
                  {selectedCharacter ? (
                    <div className="space-y-4">
                      {/* 聊天消息区域 */}
                      <ScrollArea className="h-96 border rounded-lg p-4">
                        <div className="space-y-4">
                          {chatMessages.map((message, index) => (
                            <div
                              key={index}
                              className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}
                            >
                              <div
                                className={`max-w-[80%] rounded-lg p-3 ${
                                  message.role === 'user'
                                    ? 'bg-blue-500 text-white'
                                    : 'bg-gray-100 dark:bg-gray-700 text-gray-900 dark:text-white'
                                }`}
                              >
                                <div className="text-sm">{message.content}</div>
                                {message.responseType && (
                                  <Badge variant="secondary" className="mt-1 text-xs">
                                    {message.responseType === 'immediate' ? '即时响应' : '补充响应'}
                                  </Badge>
                                )}
                              </div>
                            </div>
                          ))}
                          {isChatting && (
                            <div className="flex justify-start">
                              <div className="bg-gray-100 dark:bg-gray-700 rounded-lg p-3">
                                <div className="text-sm text-gray-500">正在思考...</div>
                              </div>
                            </div>
                          )}
                        </div>
                      </ScrollArea>

                      {/* 消息输入区域 */}
                      <div className="flex gap-2">
                        <Input
                          placeholder="输入您的消息..."
                          value={newMessage}
                          onChange={(e) => setNewMessage(e.target.value)}
                          onKeyPress={(e) => e.key === 'Enter' && sendMessage()}
                          disabled={isChatting}
                        />
                        <Button onClick={sendMessage} disabled={isChatting || !newMessage.trim()}>
                          发送
                        </Button>
                      </div>
                    </div>
                  ) : (
                    <div className="text-center text-gray-500 py-12">
                      <Bot className="w-12 h-12 mx-auto mb-4 opacity-50" />
                      <p>请从左侧选择一个角色开始对话</p>
                    </div>
                  )}
                </CardContent>
              </Card>
            </div>
          </TabsContent>

          <TabsContent value="characters" className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
              {characters.map((character) => (
                <Card key={character.id} className="hover:shadow-lg transition-shadow">
                  <CardHeader>
                    <CardTitle className="flex items-center justify-between">
                      <span>{character.name}</span>
                      <Badge variant="outline">{character.occupation}</Badge>
                    </CardTitle>
                    <CardDescription>
                      {character.age}岁 • {character.region}
                    </CardDescription>
                  </CardHeader>
                  <CardContent>
                    <div className="space-y-3">
                      <div>
                        <h4 className="font-medium mb-1">性格特征 (OCEAN)</h4>
                        <div className="grid grid-cols-2 gap-2 text-sm">
                          <div>开放性: {(character.ocean_openness * 100).toFixed(0)}%</div>
                          <div>尽责性: {(character.ocean_conscientiousness * 100).toFixed(0)}%</div>
                          <div>外向性: {(character.ocean_extraversion * 100).toFixed(0)}%</div>
                          <div>宜人性: {(character.ocean_agreeableness * 100).toFixed(0)}%</div>
                          <div className="col-span-2">神经质: {(character.ocean_neuroticism * 100).toFixed(0)}%</div>
                        </div>
                      </div>
                      
                      <Separator />
                      
                      <div>
                        <h4 className="font-medium mb-1">语言风格</h4>
                        <p className="text-sm text-gray-600 dark:text-gray-300">
                          {character.language_style || '暂无描述'}
                        </p>
                      </div>
                      
                      <Button 
                        className="w-full" 
                        onClick={() => selectCharacter(character)}
                      >
                        开始对话
                      </Button>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          </TabsContent>

          <TabsContent value="create" className="space-y-4">
            <Card className="max-w-2xl mx-auto">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Brain className="w-5 h-5" />
                  创建新角色
                </CardTitle>
                <CardDescription>
                  输入角色描述，系统将自动生成详细的人设和记忆
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div>
                  <label className="text-sm font-medium mb-2 block">角色描述</label>
                  <Textarea
                    placeholder="例如：一位生活在90年代上海的退休语文教师，性格温和，喜欢读书写字..."
                    value={characterDescription}
                    onChange={(e) => setCharacterDescription(e.target.value)}
                    rows={4}
                  />
                </div>
                
                <Button 
                  onClick={generateCharacter} 
                  disabled={isGenerating || !characterDescription.trim()}
                  className="w-full"
                >
                  {isGenerating ? '正在生成角色...' : '生成角色'}
                </Button>
                
                <div className="text-sm text-gray-500 space-y-2">
                  <p><strong>提示：</strong>系统将自动为您的角色生成：</p>
                  <ul className="list-disc list-inside space-y-1 ml-4">
                    <li>基础信息（姓名、年龄、职业等）</li>
                    <li>OCEAN五维人格特征</li>
                    <li>语言风格和行为特点</li>
                    <li>丰富的个人记忆和经历</li>
                  </ul>
                </div>
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>
      </div>
    </div>
  )
}

export default App
