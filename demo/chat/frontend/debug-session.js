// 调试会话管理：直接在浏览器控制台中运行
// 步骤：
// 1. 打开浏览器，访问 http://localhost:4000
// 2. 按F12打开控制台
// 3. 复制并粘贴此脚本，按Enter执行

console.log('=== 开始调试会话管理 ===');

// 清理 localStorage
function clearLocalStorage() {
  console.log('1. 清理localStorage...');
  localStorage.removeItem('sessions');
  localStorage.removeItem('sessionId');
  // 清理会话消息
  Object.keys(localStorage).forEach(key => {
    if (key.startsWith('chat_messages_v1_')) {
      localStorage.removeItem(key);
    }
  });
  console.log('✓ 清理完成');
}

// 检查当前状态
function checkCurrentState() {
  console.log('\n=== 当前状态 ===');
  console.log('sessionId:', localStorage.getItem('sessionId'));
  
  const sessionsJson = localStorage.getItem('sessions');
  console.log('sessions (raw):', sessionsJson);
  
  let sessions = {};
  if (sessionsJson) {
    try {
      sessions = JSON.parse(sessionsJson);
      console.log('sessions (parsed):', sessions);
      console.log('会话数量:', Object.keys(sessions).length);
    } catch (e) {
      console.error('解析sessions失败:', e);
    }
  }
  
  console.log('localStorage所有键:', Object.keys(localStorage));
  return { sessions };
}

// 模拟点击New Session按钮
function simulateNewSession() {
  console.log('\n2. 模拟点击New Session按钮...');
  
  // 生成新会话ID
  const newSessionId = `session_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
  console.log('生成的newSessionId:', newSessionId);
  
  // 更新sessionId
  localStorage.setItem('sessionId', newSessionId);
  console.log('✓ sessionId已保存:', localStorage.getItem('sessionId'));
  
  // 更新会话列表
  const currentSessionsJson = localStorage.getItem('sessions');
  const currentSessions = currentSessionsJson ? JSON.parse(currentSessionsJson) : {};
  
  const updatedSessions = {
    ...currentSessions,
    [newSessionId]: {id: newSessionId, name: "new session", timestamp: Date.now()}
  };
  
  // 保存到localStorage
  localStorage.setItem('sessions', JSON.stringify(updatedSessions));
  console.log('✓ 会话列表已保存到localStorage');
  
  // 验证保存是否成功
  const savedSessionsJson = localStorage.getItem('sessions');
  let savedSessions = {};
  if (savedSessionsJson) {
    try {
      savedSessions = JSON.parse(savedSessionsJson);
      if (savedSessions[newSessionId]) {
        console.log('✓ 验证成功：新会话存在于会话列表中');
      } else {
        console.error('✗ 验证失败：新会话不在会话列表中');
      }
    } catch (e) {
      console.error('✗ 验证失败：解析会话列表失败', e);
    }
  } else {
    console.error('✗ 验证失败：无法获取会话列表');
  }
  
  // 创建欢迎消息
  const welcome = {
    id: `welcome-${Date.now()}`,
    content: "你好，我是自主分析智能体DeepInvestigate,",
    sender: "ai",
    timestamp: new Date(),
    localOnly: true,
  };
  
  localStorage.setItem(`chat_messages_v1_${newSessionId}`, JSON.stringify([welcome]));
  console.log('✓ 欢迎消息已保存');
  
  return { newSessionId, updatedSessions };
}

// 模拟页面刷新
function simulatePageRefresh() {
  console.log('\n3. 模拟页面刷新...');
  
  // 保存刷新前的状态
  const beforeRefresh = {
    sessionId: localStorage.getItem('sessionId'),
    sessions: localStorage.getItem('sessions')
  };
  
  console.log('刷新前的sessionId:', beforeRefresh.sessionId);
  console.log('刷新前的sessions:', beforeRefresh.sessions);
  
  // 模拟页面重新加载（清除所有JavaScript状态）
  console.log('模拟页面重新加载...');
  
  // 模拟组件重新挂载
  setTimeout(() => {
    console.log('\n4. 模拟组件重新挂载...');
    
    // 初始化或获取sessionId
    let sid = localStorage.getItem('sessionId');
    if (!sid) {
      sid = `session_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
      localStorage.setItem('sessionId', sid);
      console.log('生成新的sessionId:', sid);
    }
    
    console.log('获取的sessionId:', sid);
    
    // 加载会话列表
    let loadedSessions = {};
    const savedSessions = localStorage.getItem('sessions');
    if (savedSessions) {
      try {
        loadedSessions = JSON.parse(savedSessions);
        console.log('解析的会话列表:', loadedSessions);
        
        // 确保加载的是对象
        if (typeof loadedSessions !== 'object' || loadedSessions === null || Array.isArray(loadedSessions)) {
          console.error('会话列表格式错误，使用空对象');
          loadedSessions = {};
        }
      } catch (e) {
        console.error('解析会话列表失败:', e);
        loadedSessions = {};
      }
    }
    
    // 检查会话是否在列表中
    if (!loadedSessions[sid]) {
      console.log(`会话 ${sid} 不在列表中，添加到列表`);
      loadedSessions[sid] = {id: sid, name: "new session", timestamp: Date.now()};
      localStorage.setItem('sessions', JSON.stringify(loadedSessions));
      console.log('✓ 会话已添加到列表');
    } else {
      console.log(`会话 ${sid} 已存在于列表中`);
    }
    
    // 最终检查
    console.log('\n=== 最终检查 ===');
    console.log('当前sessionId:', localStorage.getItem('sessionId'));
    
    const finalSessionsJson = localStorage.getItem('sessions');
    console.log('最终sessions:', finalSessionsJson);
    
    let finalSessions = {};
    if (finalSessionsJson) {
      try {
        finalSessions = JSON.parse(finalSessionsJson);
        console.log('会话数量:', Object.keys(finalSessions).length);
        console.log('所有会话:', finalSessions);
      } catch (e) {
        console.error('解析最终会话列表失败:', e);
      }
    }
    
    // 验证会话是否保留
    const originalSessionId = beforeRefresh.sessionId;
    if (originalSessionId && finalSessions[originalSessionId]) {
      console.log('\n🎉 测试成功！会话在页面刷新后保留了');
    } else {
      console.log('\n❌ 测试失败！会话在页面刷新后丢失了');
    }
    
  }, 500);
}

// 运行完整测试流程
function runTest() {
  clearLocalStorage();
  checkCurrentState();
  
  const newSessionData = simulateNewSession();
  checkCurrentState();
  
  simulatePageRefresh();
}

// 启动测试
runTest();

console.log('\n=== 调试脚本执行完成 ===');
console.log('请查看控制台输出，分析会话管理流程');
console.log('===');
