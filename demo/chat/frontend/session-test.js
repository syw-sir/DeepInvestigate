// 自动化测试程序：测试会话管理功能
// 运行方式：在浏览器控制台中执行

class SessionTest {
  constructor() {
    this.testResults = [];
  }

  // 记录测试结果
  logResult(testName, success, message) {
    const result = {
      testName,
      success,
      message,
      timestamp: new Date().toISOString()
    };
    this.testResults.push(result);
    console.log(`${success ? '✅' : '❌'} ${testName}: ${message}`);
  }

  // 清理 localStorage
  clearLocalStorage() {
    localStorage.removeItem('sessions');
    localStorage.removeItem('sessionId');
    // 保留其他不相关的 keys
    const keysToKeep = ['theme', 'autoCollapseEnabled'];
    Object.keys(localStorage).forEach(key => {
      if (!keysToKeep.includes(key) && key.startsWith('chat_messages_v1_')) {
        localStorage.removeItem(key);
      }
    });
    console.log('LocalStorage cleared for testing');
  }

  // 获取当前会话列表
  getSessions() {
    try {
      const sessions = localStorage.getItem('sessions');
      return sessions ? JSON.parse(sessions) : {};
    } catch (e) {
      console.error('Error getting sessions:', e);
      return {};
    }
  }

  // 获取当前 sessionId
  getSessionId() {
    return localStorage.getItem('sessionId');
  }

  // 模拟创建新会话
  async createNewSession() {
    // 找到 New Session 按钮
    const newSessionButton = document.querySelector('.w-full.justify-start');
    if (!newSessionButton) {
      this.logResult('Create New Session', false, 'New Session button not found');
      return null;
    }

    // 点击按钮创建新会话
    newSessionButton.click();
    
    // 等待会话创建完成
    await new Promise(resolve => setTimeout(resolve, 1000));
    
    const sessionId = this.getSessionId();
    const sessions = this.getSessions();
    
    return { sessionId, sessions };
  }

  // 模拟页面刷新
  async simulatePageRefresh() {
    // 保存当前会话信息
    const beforeRefresh = {
      sessionId: this.getSessionId(),
      sessions: this.getSessions()
    };
    
    console.log('Before refresh:', beforeRefresh);
    
    // 刷新页面
    window.location.reload();
    
    // 页面刷新后，测试将在新页面中继续
    // 我们需要在页面加载完成后重新执行测试
  }

  // 页面加载完成后执行的测试
  async runAfterPageLoad() {
    // 等待页面完全加载
    await new Promise(resolve => {
      if (document.readyState === 'complete') {
        resolve();
      } else {
        window.addEventListener('load', resolve);
      }
    });
    
    // 获取刷新后的会话信息
    const afterRefresh = {
      sessionId: this.getSessionId(),
      sessions: this.getSessions()
    };
    
    console.log('After refresh:', afterRefresh);
    
    // 检查会话是否存在
    if (afterRefresh.sessionId && afterRefresh.sessions[afterRefresh.sessionId]) {
      this.logResult('Session Persistence After Refresh', true, 'Session persisted successfully after page refresh');
      this.logResult('Session List Integrity', true, `Session list contains ${Object.keys(afterRefresh.sessions).length} sessions`);
    } else {
      this.logResult('Session Persistence After Refresh', false, 'Session lost after page refresh');
      this.logResult('Session List Integrity', false, 'Session not found in session list');
    }
    
    // 打印测试总结
    this.printSummary();
  }

  // 打印测试总结
  printSummary() {
    const total = this.testResults.length;
    const passed = this.testResults.filter(r => r.success).length;
    const failed = total - passed;
    
    console.log('\n=== Test Summary ===');
    console.log(`Total Tests: ${total}`);
    console.log(`Passed: ${passed}`);
    console.log(`Failed: ${failed}`);
    
    if (failed === 0) {
      console.log('🎉 All tests passed! Session management is working correctly.');
    } else {
      console.log('⚠️  Some tests failed. Please check the session management implementation.');
    }
    
    // 详细结果
    console.log('\nDetailed Results:');
    this.testResults.forEach(result => {
      console.log(`- ${result.testName}: ${result.success ? 'PASS' : 'FAIL'} - ${result.message}`);
    });
  }

  // 主测试流程
  async runTests() {
    console.log('=== Starting Session Management Tests ===');
    
    // 检查是否在页面刷新后运行
    const urlParams = new URLSearchParams(window.location.search);
    if (urlParams.get('test_session') === 'true') {
      // 页面刷新后继续测试
      await this.runAfterPageLoad();
      return;
    }
    
    // 1. 清理测试环境
    this.clearLocalStorage();
    this.logResult('Clear LocalStorage', true, 'Test environment cleared');
    
    // 2. 初始状态检查
    const initialSessions = this.getSessions();
    const initialSessionId = this.getSessionId();
    this.logResult('Initial State', true, `Sessions: ${Object.keys(initialSessions).length}, SessionId: ${initialSessionId || 'none'}`);
    
    // 3. 创建新会话
    const { sessionId, sessions } = await this.createNewSession();
    if (sessionId && sessions[sessionId]) {
      this.logResult('Create New Session', true, `Session ${sessionId} created successfully`);
      this.logResult('Session List Update', true, `Session list now contains ${Object.keys(sessions).length} sessions`);
    } else {
      this.logResult('Create New Session', false, 'Failed to create new session');
      this.printSummary();
      return;
    }
    
    // 4. 验证会话立即保存
    const savedSessions = this.getSessions();
    if (savedSessions[sessionId]) {
      this.logResult('Session Immediate Save', true, 'Session saved to localStorage immediately');
    } else {
      this.logResult('Session Immediate Save', false, 'Session not saved to localStorage immediately');
    }
    
    // 5. 模拟页面刷新
    console.log('\n=== Simulating Page Refresh ===');
    // 在 URL 中添加测试参数，以便页面刷新后继续测试
    window.location.search = '?test_session=true';
  }
}

// 创建测试实例并运行测试
const sessionTest = new SessionTest();

// 等待页面加载完成后运行测试
if (document.readyState === 'complete') {
  sessionTest.runTests();
} else {
  window.addEventListener('load', () => {
    sessionTest.runTests();
  });
}

// 导出测试类供手动测试
window.SessionTest = SessionTest;