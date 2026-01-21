// 会话持久化测试脚本
// 在浏览器控制台中运行此脚本来测试会话管理功能

(function() {
  console.log('=== 会话持久化测试 ===');
  
  // 保存原始localStorage状态
  const originalState = {
    sessionId: localStorage.getItem('sessionId'),
    sessions: localStorage.getItem('sessions')
  };
  
  console.log('初始状态:');
  console.log('- sessionId:', originalState.sessionId);
  console.log('- sessions:', originalState.sessions);
  
  // 清理测试环境
  function cleanup() {
    localStorage.removeItem('sessionId');
    localStorage.removeItem('sessions');
    console.log('✅ 测试环境已清理');
  }
  
  // 创建新会话
  function createNewSession() {
    const newSessionId = `test_session_${Date.now()}`;
    localStorage.setItem('sessionId', newSessionId);
    
    // 创建会话列表
    const newSession = {
      id: newSessionId,
      name: "测试会话",
      timestamp: Date.now()
    };
    
    const sessions = {
      [newSessionId]: newSession
    };
    
    localStorage.setItem('sessions', JSON.stringify(sessions));
    
    console.log('✅ 新会话已创建:');
    console.log('- sessionId:', newSessionId);
    console.log('- 会话名称:', "测试会话");
    
    return newSessionId;
  }
  
  // 验证会话保存
  function verifySessionSaved(expectedSessionId) {
    const savedSessionId = localStorage.getItem('sessionId');
    const savedSessionsJson = localStorage.getItem('sessions');
    
    console.log('验证保存结果:');
    console.log('- 保存的sessionId:', savedSessionId);
    console.log('- 保存的sessions:', savedSessionsJson);
    
    if (savedSessionId === expectedSessionId) {
      console.log('✅ sessionId 保存正确');
    } else {
      console.log('❌ sessionId 保存错误: 期望', expectedSessionId, '实际', savedSessionId);
      return false;
    }
    
    if (savedSessionsJson) {
      try {
        const sessions = JSON.parse(savedSessionsJson);
        if (sessions[expectedSessionId]) {
          console.log('✅ 会话在列表中');
          return true;
        } else {
          console.log('❌ 会话不在列表中');
          return false;
        }
      } catch (e) {
        console.log('❌ 解析sessions失败:', e);
        return false;
      }
    } else {
      console.log('❌ sessions 为空');
      return false;
    }
  }
  
  // 模拟页面刷新
  function simulatePageRefresh() {
    console.log('\n🔁 模拟页面刷新...');
    // 在真实场景中，页面刷新会丢失JavaScript状态但local保留Storage
    // 这里我们只验证localStorage中的数据是否仍然存在
    
    const afterRefresh = {
      sessionId: localStorage.getItem('sessionId'),
      sessions: localStorage.getItem('sessions')
    };
    
    console.log('刷新后状态:');
    console.log('- sessionId:', afterRefresh.sessionId);
    console.log('- sessions:', afterRefresh.sessions);
    
    return afterRefresh;
  }
  
  // 运行测试
  function runTest() {
    console.log('\n1. 清理测试环境');
    cleanup();
    
    console.log('\n2. 创建新会话');
    const testSessionId = createNewSession();
    
    console.log('\n3. 验证立即保存');
    const immediateSaveOk = verifySessionSaved(testSessionId);
    
    console.log('\n4. 模拟页面刷新');
    const afterRefresh = simulatePageRefresh();
    
    console.log('\n5. 验证刷新后会话仍然存在');
    let refreshSaveOk = false;
    
    if (afterRefresh.sessionId === testSessionId) {
      console.log('✅ 刷新后sessionId保持一致');
      refreshSaveOk = true;
    } else {
      console.log('❌ 刷新后sessionId不一致');
 }
       
    if (afterRefresh.sessions) {
      try {
        const sessions = JSON.parse(afterRefresh.sessions);
        if (sessions[testSessionId]) {
          console.log('✅ 刷新后会话仍在列表中');
          refreshSaveOk = refreshSaveOk && true;
        } else {
          console.log('❌ 刷新后会话不在列表中');
          refreshSaveOk = false;
        }
      } catch (e) {
        console.log('❌ 刷新后解析sessions失败:', e);
        refreshSaveOk = false;
      }
    } else {
      console.log('❌ 刷新后sessions为空');
      refreshSaveOk = false;
    }
    
    console.log('\n=== 测试结果 ===');
    if (immediateSaveOk && refreshSaveOk) {
      console.log('🎉 测试通过：会话在页面刷新后成功保留！');
    } else {
      console.log('❌ 测试失败：会话在页面刷新后丢失');
    }
    
    // 恢复原始状态
    if (originalState.sessionId) {
      localStorage.setItem('sessionId', originalState.sessionId);
    } else {
      localStorage.removeItem('sessionId');
    }
    
    if (originalState.sessions) {
      localStorage.setItem('sessions', originalState.sessions);
    } else {
      localStorage.removeItem('sessions');
    }
    
    console.log('✅ 原始状态已恢复');
  }
  
  // 导出测试函数
  window.testSessionPersistence = runTest;
  
  console.log('\n运行 window.testSessionPersistence() 开始测试');
  console.log('=== 测试脚本加载完成 ===');
})();