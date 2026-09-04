<template>
  <div v-if="!mentor" class="gate">
    <div class="gate-card">
      <h1>Project Ledger</h1>
      <p>Mentor 登录后维护项目名片：Zulip Topic、文档目录、Gitea 仓库与成员绑定。Agent / SOP 只读这些数据。</p>
      <div class="field" style="margin-bottom: 14px">
        <label>选择 Mentor</label>
        <select v-model="selected" class="select">
          <option disabled value="">— 请选择 —</option>
          <option v-for="m in mentors" :key="m" :value="m">{{ m }}</option>
        </select>
      </div>
      <button class="btn btn-primary" style="width: 100%" :disabled="!selected" @click="enter">
        进入管理台
      </button>
      <div v-if="error" class="error" style="margin-top: 10px">{{ error }}</div>
    </div>
  </div>

  <div v-else class="shell">
    <header class="topbar">
      <router-link class="brand" to="/">
        <strong>Project Ledger</strong>
        <span>TraceForge · 项目注册中心</span>
      </router-link>
      <div class="mentor-chip">
        <span>{{ mentor }}</span>
        <button type="button" @click="logout">切换</button>
      </div>
    </header>
    <router-view />
  </div>
</template>

<script>
import { api, clearMentor, getMentor, setMentor } from "./api/index.js";

export default {
  name: "App",
  data() {
    return {
      mentor: getMentor(),
      mentors: [],
      selected: "",
      error: "",
    };
  },
  async mounted() {
    try {
      const data = await api.mentors();
      this.mentors = data.mentors || [];
      if (!this.selected && this.mentors.length) this.selected = this.mentors[0];
    } catch (e) {
      this.error = e.message;
    }
  },
  methods: {
    enter() {
      if (!this.selected) return;
      setMentor(this.selected);
      this.mentor = this.selected;
    },
    logout() {
      clearMentor();
      this.mentor = "";
    },
  },
};
</script>
