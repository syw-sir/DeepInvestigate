// 综合测试：模拟真实应用的会话管理流程
// 运行方式：在浏览器控制台中执行

/**
 * 会话管理测试套件
 * 模拟真实应用的会话创建、保存和恢复流程
 */
class SessionManagementTest {
  constructor() {
    this.testSteps = [];
    this.currentStep = 0;
    this.testData = {
      originalSessions: {},
      createdSessionId: null,
      sessionListAfterCreation: {},
      sessionListAfterRefresh: {}
    };
  }

  /**
   * 记录测试步骤
   */
  logStep(step, message, data = null) {
    const stepInfo = {
      step,
      message,
      data,
      timestamp: new Date().toISOString(),
      stepNumber: ++this.currentStep
    };
    this.testSteps.push(stepInfo);
    console.log(`${step} ${stepNumber}: ${message}`, data || '');
  }

  /**
   * 清理测试环境
   */
  async cleanup() {
    this.logStep('INFO', '清理测试环境');
    
    // 保存原始数据（如果有）
    const originalSessions = localStorage.getItem('sessions');
    const originalSessionId = localStorage.getItem('sessionId');
    
    if (originalSessions) {
      this.testData.originalSessions = JSON.parse(originalSessions);
    }
    
    // 清理与会话相关的 localStorage
    localStorage.removeItem('sessions');
    localStorage.removeItem('sessionId');
    
    // 清理会话消息
    Object.keys(localStorage).forEach(key => {
      if (key.startsWith('chat_messages_v1_')) {
        localStorage.removeItem(key);
      }
    });
    
    this.logStep('INFO', '测试环境清理完成');
    return true;
  }

  /**
   * 初始化应用状态
   */
  async initializeApp() {
    this.logStep('INFO', '初始化应用状态');
    
    // 模拟组件挂载时的初始化
    await this.simulateComponentMount();
    
    return true;
  }

  /**
   * 模拟组件挂载
   */
  async simulateComponentMount() {
    this.logStep('INFO', '模拟组件挂载');
    
    // 检查 localStorage 状态
    const storageUsage = this.getLocalStorageUsage();
    this.logStep('INFO', 'LocalStorage 使用情况', storageUsage);
    
    // 模拟从 localStorage 加载会话列表
    let loadedSessions = {};
    const savedSessions = localStorage.getItem('sessions');
    
    if (savedSessions) {
      try {
        loadedSessions = JSON.parse(savedSessions);
        // 确保加载的是对象
        if (typeof loadedSessions !== 'object' || loadedSessions === null || Array.isArray(loadedSessions)) {
          loadedSessions = {};
        }
      } catch (e) {
        this.logStep('ERROR', '解析会话列表失败', e);
        loadedSessions = {};
      }
    }
    
    // 初始化或获取 sessionId
    let sid = localStorage.getItem('sessionId');
    if (!sid) {
      sid = `session_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
      localStorage.setItem('sessionId', sid);
      
      // 添加新会话到列表
      loadedSessions[sid] = {id: sid, name: "new session", timestamp: Date.now()};
      
      // 保存更新后的会话列表
      localStorage.setItem('sessions', JSON.stringify(loadedSessions));
    } else {
      // 检查会话是否在列表中
      if (!loadedSessions[sid]) {
        loadedSessions[sid] = {id: sid, name: "new session", timestamp: Date.now()};
        // 保存更新后的会话列表
        localStorage.setItem('sessions', JSON.stringify(loadedSessions));
      }
    }
    
    this.logStep('INFO', '组件挂载完成', { sessionId: sid, sessionCount: Object.keys(loadedSessions).length });
  }

  /**
   * 获取 localStorage 使用情况
   */
  getLocalStorageUsage() {
    let total = 0;
    const keys = [];
    
    for (let key in localStorage) {
      if (localStorage.hasOwnProperty(key)) {
        total += localStorage[key].length + key.length;
        keys.push(key);
      }
    }
    
    return { totalBytes: total, keys };
  }

  /**
   * 创建新会话
   */
  async createNewSession() {
    this.logStep('INFO', '开始创建新会话');
    
    // 模拟点击 "New Session" 按钮
    const newSessionId = `session_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    
    // 更新 sessionId
    localStorage.setItem('sessionId', newSessionId);
    
    // 使用 functional update 模式更新会话列表
    const currentSessionsJson = localStorage.getItem('sessions');
    const currentSessions = currentSessionsJson ? JSON.parse(currentSessionsJson) : {};
    
    const updatedSessions = {
      ...currentSessions,
      [newSessionId]: {id: newSessionId, name: "new session", timestamp: Date.now()}
    };
    
    // 保存到 localStorage
    localStorage.setItem('sessions', JSON.stringify(updatedSessions));
    
    // 验证保存是否成功
    const savedSessionsJson = localStorage.getItem('sessions');
    let verificationSuccess = false;
    
    if (savedSessionsJson) {
      const savedSessions = JSON.parse(savedSessionsJson);
      verificationSuccess = !!savedSessions[newSessionId];
      
      if (verificationSuccess) {
        this.testData.createdSessionId = newSessionId;
        this.testData.sessionListAfterCreation = savedSessions;
        this.logStep('SUCCESS', '新会话创建成功', { sessionId: newSessionId, sessionCount: Object.keys(savedSessions).length });
      } else {
        this.logStep('ERROR', '会话创建失败：验证失败', { expected: newSessionId, actual: savedSessions });
      }
    } else {
      this.logStep('ERROR', '会话创建失败：无法保存到 localStorage');
    }
    
    return verificationSuccess;
  }

  /**
   * 模拟页面刷新
   */
  async simulatePageRefresh() {
    this.logStep('INFO', '开始模拟页面刷新');
    
    // 保存当前状态
    const beforeRefresh = {
      sessionId: localStorage.getItem('sessionId'),
      sessions: localStorage.getItem('sessions'),
      localStorageUsage: this.getLocalStorageUsage()
    };
    
    this.logStep('INFO', '刷新前状态', beforeRefresh);
    
    // 清除内存状态（模拟页面刷新）
    // 在真实应用中，页面刷新会导致所有 JavaScript 状态丢失
    // 这里我们只模拟 localStorage 的状态保留
    
    // 模拟页面重新加载
    await new Promise(resolve => setTimeout(resolve, 500));
    
    // 模拟组件重新挂载
    await this.simulateComponentMount();
    
    // 获取刷新后的状态
    const afterRefresh = {
      sessionId: localStorage.getItem('sessionId'),
      sessions: localStorage.getItem('sessions'),
      localStorageUsage: this.getLocalStorageUsage()
    };
    
    this.logStep('INFO', '刷新后状态', afterRefresh);
    
    // 解析会话列表
    let sessionsAfterRefresh = {};
    if (afterRefresh.sessions) {
      try {
        sessionsAfterRefresh = JSON.parse(afterRefresh.sessions);
        this.testData.sessionListAfterRefresh = sessionsAfterRefresh;
      } catch (e) {
        this.logStep('ERROR', '解析刷新后的会话列表失败', e);
        return false;
      }
    }
    
    // 验证会话是否保留
    const sessionExistsAfterRefresh = 
      this.testData.createdSessionId && 
      sessionsAfterRefresh[this.testData.createdSessionId];
    
    if (sessionExistsAfterRefresh) {
      this.logStep('SUCCESS', '会话在页面刷新后成功保留');
      return true;
    } else {
      this.logStep('ERROR', '会话在页面刷新后丢失');
      return false;
    }
  }

  /**
   * 验证会话管理功能
   */
  async verifySessionManagement() {
    this.logStep('INFO', '开始验证会话管理功能');
    
    // 检查会话创建
    const sessionCreated = await this.createNewSession();
    if (!sessionCreated) {
      return false;
    }
    
    // 模拟页面刷新
    const sessionSurvivedRefresh = await this.simulatePageRefresh();
    if (!sessionSurvivedRefresh) {
      return false;
    }
    
    // 最终验证
    const finalVerification = this.finalVerification();
    
    return finalVerification;
  }

  /**
   * 最终验证
   */
  finalVerification() {
    this.logStep('INFO', '执行最终验证');
    
    const { 
      createdSessionId, 
      sessionListAfterCreation, 
      sessionListAfterRefresh 
    } = this.testData;
    
    const checks = [
      {
        name: '会话ID创建成功',
        result: !!createdSessionId
      },
      {
        name: '会话添加到列表',
        result: createdSessionId && sessionListAfterCreation[createdSessionId]
      },
      {
        name: '会话列表非空',
        result: Object.keys(sessionListAfterCreation).length > 0
      },
      {
        name: '刷新后会话列表非空',
        result: Object.keys(sessionListAfterRefresh).length > 0
      },
      {
        name: '会话在刷新后保留',
        result: createdSessionId && sessionListAfterRefresh[createdSessionId]
      },
      {
        name: '会话数量一致',
        result: Object.keys(sessionListAfterCreation).length === Object.keys(sessionListAfterRefresh).length
      }
    ];
    
    let allPassed = true;
    checks.forEach(check => {
      if (check.result) {
        this.logStep('PASS', check.name);
      } else {
        this.logStep('FAIL', check.name);
        allPassed = false;
      }
    });
    
    return allPassed;
  }

  /**
   * 恢复原始数据
   */
  async restoreOriginalData() {
    this.logStep('INFO', '恢复原始数据');
    
    // 恢复原始会话数据
    if (Object.keys(this.testData.originalSessions).length > 0) {
      localStorage.setItem('sessions', JSON.stringify(this.testData.originalSessions));
    }
    
    this.logStep('INFO', '原始数据恢复完成');
  }

  /**
   * 运行完整测试套件
   */
  async runTestSuite() {
    console.log('====================================');
    console.log('会话管理测试套件开始运行');
    console.log('====================================');
    
    try {
      // 1. 清理测试环境
      const cleanupSuccess = await this.cleanup();
      if (!cleanupSuccess) {
        throw new Error('测试环境清理失败');
      }
      
      // 2. 初始化应用
      const initSuccess = await this.initializeApp();
      if (!initSuccess) {
        throw new Error('应用初始化失败');
      }
      
      // 3. 验证会话管理
      const verificationSuccess = await this.verifySessionManagement();
      
      // 4. 恢复原始数据
      await this.restoreOriginalData();
      
      // 5. 输出测试结果
      this.printTestResults(verificationSuccess);
      
      return verificationSuccess;
      
    } catch (error) {
      this.logStep('ERROR', '测试套件运行失败', error);
      await this.restoreOriginalData();
      this.printTestResults(false, error);
      return false;
    }
  }

  /**
   * 打印测试结果
   */
  printTestResults(success, error = null) {
    console.log('\n====================================');
    console.log('测试结果汇总');
    console.log('====================================');
    
    if (success) {
      console.log('🎉 所有测试通过！会话管理功能正常工作');
    } else {
      console.log('❌ 测试失败！会话管理存在问题');
      if (error) {
        console.log('错误详情:', error);
      }
    }
    
    console.log('\n测试步骤详情:');
    this.testSteps.forEach((step, index) => {
      const prefix = step.step === 'ERROR' ? '❌' : step.step === 'SUCCESS' ? '✅' : 'ℹ️';
      console.log(`${prefix} ${step.stepNumber}. ${step.message}`);
    });
    
    console.log('\n测试数据:');
    console.log(JSON.stringify(this.testData, null, 2));
    
    console.log('\n====================================');
  }
}

// 创建测试实例并运行测试
console.log('准备运行会话管理测试...');
console.log('请按F12打开控制台查看详细测试结果');
console.log('测试将模拟真实应用的会话创建和恢复流程');

// 延迟执行，确保控制台已打开
setTimeout(async () => {
  const testSuite = new SessionManagementTest();
  await testSuite.runTestSuite();
}, 1000);

// 导出测试类供手动测试
window.SessionManagementTest = SessionManagementTest;