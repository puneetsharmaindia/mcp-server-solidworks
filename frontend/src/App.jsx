import React, { useState, useEffect, useRef } from 'react';
import axios from 'axios';
import { Send, Bot, User, Hammer } from 'lucide-react';
import './index.css';

function App() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const messagesEndRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const handleSend = async () => {
    if (!input.trim()) return;

    const newMessages = [...messages, { role: 'user', content: input }];
    setMessages(newMessages);
    setInput('');
    setIsLoading(true);

    try {
      const response = await axios.post('http://localhost:8000/api/chat', {
        messages: newMessages
      });
      setMessages(response.data.messages);
    } catch (error) {
      console.error('Error sending message:', error);
      setMessages(prev => [...prev, { 
        role: 'assistant', 
        content: 'Sorry, I encountered an error. Make sure Ollama and the backend are running.' 
      }]);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="app-container">
      <header className="header">
        <div className="status-indicator">
          <div className="status-dot"></div>
          Connected to SolidPilot
        </div>
        <h1>SolidWorks AI</h1>
      </header>

      <div className="chat-container">
        {messages.length === 0 && (
          <div className="message-wrapper assistant">
            <div className="message assistant">
              Hello! I'm your SolidWorks AI assistant powered by Ollama. You can ask me to create sketches, extrude features, or modify your current model. What would you like to design today?
            </div>
          </div>
        )}

        {messages.map((msg, idx) => (
          <div key={idx} className={`message-wrapper ${msg.role}`}>
            {msg.role === 'tool' ? (
              <div className="message tool">
                <Hammer size={16} />
                Executed: {msg.name}
              </div>
            ) : (
              <div className={`message ${msg.role}`}>
                {msg.content}
              </div>
            )}
          </div>
        ))}
        
        {isLoading && (
          <div className="message-wrapper assistant">
            <div className="message assistant">
              <div className="typing-indicator">
                <div className="typing-dot"></div>
                <div className="typing-dot"></div>
                <div className="typing-dot"></div>
              </div>
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      <div className="input-container">
        <div className="input-box">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyPress={(e) => e.key === 'Enter' && handleSend()}
            placeholder="Type a command (e.g. 'Create a 50x50 cube')..."
            disabled={isLoading}
          />
          <button 
            className="send-button"
            onClick={handleSend}
            disabled={isLoading || !input.trim()}
          >
            <Send size={20} />
          </button>
        </div>
      </div>
    </div>
  );
}

export default App;
