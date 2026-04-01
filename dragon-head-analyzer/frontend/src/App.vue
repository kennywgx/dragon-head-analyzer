<template>
  <div id="app">
    <nav class="sidebar">
      <div class="logo">
        <span class="logo-icon">🐉</span>
        <span class="logo-text">龙头战法</span>
      </div>
      <ul class="nav-list">
        <li><router-link to="/" exact-active-class="active">📊 看板</router-link></li>
        <li><router-link to="/zt-pool" active-class="active">🔥 涨停池</router-link></li>
        <li><router-link to="/boards" active-class="active">📂 板块</router-link></li>
        <li><router-link to="/logs" active-class="active">📝 日志</router-link></li>
      </ul>
      <div class="nav-footer">
        <span class="version">v0.2.0</span>
      </div>
    </nav>
    <main class="content">
      <router-view />
    </main>
  </div>
</template>

<style scoped>
#app {
  display: flex;
  min-height: 100vh;
}
.sidebar {
  width: 200px;
  background: #1a1a2e;
  color: #eee;
  display: flex;
  flex-direction: column;
  padding: 0;
  position: fixed;
  top: 0;
  left: 0;
  bottom: 0;
  z-index: 100;
}
.logo {
  padding: 20px;
  display: flex;
  align-items: center;
  gap: 10px;
  border-bottom: 1px solid #2a2a4a;
}
.logo-icon {
  font-size: 28px;
}
.logo-text {
  font-size: 18px;
  font-weight: bold;
  color: #ff6b6b;
}
.nav-list {
  list-style: none;
  padding: 10px 0;
  margin: 0;
  flex: 1;
}
.nav-list li a {
  display: block;
  padding: 12px 20px;
  color: #aaa;
  text-decoration: none;
  transition: all 0.2s;
  border-left: 3px solid transparent;
}
.nav-list li a:hover {
  color: #fff;
  background: #2a2a4a;
}
.nav-list li a.active {
  color: #ff6b6b;
  background: #2a2a4a;
  border-left-color: #ff6b6b;
}
.nav-footer {
  padding: 15px 20px;
  border-top: 1px solid #2a2a4a;
}
.version {
  color: #555;
  font-size: 12px;
}
.content {
  flex: 1;
  margin-left: 200px;
  padding: 24px;
  background: #f5f6fa;
  min-height: 100vh;
}
</style>
