// localStorage变化监控脚本
// 运行方式：在浏览器控制台中执行，然后正常使用应用

console.log('=== localStorage实时监控已启动 ===');

// 监控localStorage变化
const originalSetItem = localStorage.setItem;
const originalGetItem = localStorage.getItem;
const originalRemoveItem = localStorage.removeItem;

// 记录操作日志
function logOperation(operation, key, value = null) {
  const timestamp = new Date().toLocaleTimeString();
  const caller = (new Error()).stack.split('\n')[3].trim();
  
  console.log(`[${timestamp}] ${operation} - ${key}`);
  
  if (value !== null) {
    // 限制日志长度
    const displayValue = typeof value === 'string' && value.length > 200 
      ? value.substring(0, 200) + '...'
      : value;
    
    console.log('  值:', displayValue);
  }
  
  console.log('  调用位置:', caller);
  
  // 检查sessions数据的完整性
  if (key === 'sessions') {
    try {
      const sessions = JSON.parse(value);
      console.log('  会话数量:', Object.keys(sessions).length);
      console.log('  所有会话ID:', Object.keys(sessions));
    } catch (e) {
      console.error('  ❌ 解析会话列表失败:', e);
    }
  }
  
  console.log('---');
}

// 重写localStorage方法
localStorage.setItem = function(key, value) {
  logOperation('SET', key, value);
  return originalSetItem.apply(this, arguments);
};

localStorage.getItem = function(key) {
  const result = originalGetItem.apply(this, arguments);
  logOperation('GET', key, result);
  return result;
};

localStorage.removeItem = function(key) {
  logOperation('REMOVE', key);
  return originalRemoveItem.apply(this, arguments);
};

// 定期检查localStorage状态
setInterval(() => {
  const sessionId = localStorage.getItem('sessionId');
  const sessionsJson = localStorage.getItem('sessions');
  
  if (sessionId && sessionsJson) {
    try {
      const sessions = JSON.parse(sessionsJson);
      
      if (!sessions[sessionId]) {
        console.warn('⚠️  警告：当前sessionId不在会话列表中！');
        console.log('当前sessionId:', sessionId);
        console.log('会话列表:', sessions);
      }
    } catch (e) {
      console.error('⚠️  警告：解析会话列表失败！', e);
    }
  }
}, 2000);

console.log('✅ 监控已启动：');
console.log('1. 将记录所有localStorage操作');
console.log('2. 定期检查会话完整性');
console.log('3. 检测会话列表解析错误');
console.log('\n现在请正常使用应用，点击New Session按钮，然后刷新页面。');
console.log('监控将记录所有localStorage操作，帮助找出会话丢失的原因。');
console.log('===');
