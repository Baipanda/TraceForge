<template>
  <div>
    <!-- User selection overlay -->
    <div v-if="!username" class="position-fixed top-0 start-0 w-100 h-100 d-flex align-items-center justify-content-center"
      style="background:rgba(0,0,0,0.6); z-index:9999">
      <div class="card shadow-lg" style="width:380px">
        <div class="card-body text-center p-4">
          <i class="bi bi-person-circle display-3 text-primary mb-3"></i>
          <h5 class="mb-1">选择操作身份</h5>
          <p class="text-muted small mb-3">请选择你的用户名以记录操作日志</p>

          <div v-if="loading" class="text-muted small py-2">
            <div class="spinner-border spinner-border-sm me-1"></div>加载人员列表...
          </div>

          <div v-else-if="loadError" class="mb-3">
            <div class="text-danger small mb-2">{{ loadError }}</div>
            <button class="btn btn-sm btn-outline-secondary" @click="loadPeople">重试</button>
          </div>

          <template v-else>
            <select class="form-select mb-3" v-model="selectedUser">
              <option value="" disabled>— 请选择 —</option>
              <option v-for="p in people" :key="p.id" :value="p.canonical_name">{{ p.canonical_name }}</option>
            </select>
            <button class="btn btn-primary w-100" @click="confirmUser">
              <i class="bi bi-box-arrow-in-right me-1"></i>进入系统
            </button>
            <div v-if="error" class="text-danger small mt-2">{{ error }}</div>
          </template>
        </div>
      </div>
    </div>

    <!-- Main app -->
    <template v-if="username">
      <nav class="navbar navbar-expand-lg navbar-dark bg-primary mb-4">
        <div class="container">
          <router-link class="navbar-brand fw-bold" to="/">
            <i class="bi bi-check2-square me-2"></i>Todo Show
          </router-link>
          <button class="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#navbarNav">
            <span class="navbar-toggler-icon"></span>
          </button>
          <div class="collapse navbar-collapse" id="navbarNav">
            <ul class="navbar-nav">
              <li class="nav-item">
                <router-link class="nav-link" to="/"><i class="bi bi-list-ul me-1"></i>列表</router-link>
              </li>
              <li class="nav-item">
                <router-link class="nav-link" to="/tree"><i class="bi bi-diagram-3 me-1"></i>分类树</router-link>
              </li>
              <li class="nav-item">
                <router-link class="nav-link" to="/create"><i class="bi bi-plus-circle me-1"></i>新建</router-link>
              </li>
              <li class="nav-item">
                <router-link class="nav-link" to="/logs"><i class="bi bi-journal-text me-1"></i>日志</router-link>
              </li>
            </ul>
            <div class="ms-auto d-flex align-items-center">
              <span class="text-light small me-2">{{ username }}</span>
              <button class="btn btn-sm btn-outline-light" title="切换用户" @click="switchUser">
                <i class="bi bi-box-arrow-right"></i>
              </button>
            </div>
          </div>
        </div>
      </nav>
      <div class="container mb-5">
        <router-view :key="$route.path" />
      </div>
    </template>
  </div>
</template>

<script>
import api, { getCurrentUsername, setCurrentUsername } from "./api/index.js";

export default {
  name: "App",
  data() {
    return {
      username: "",
      selectedUser: "",
      people: [],
      error: "",
      loading: false,
      loadError: "",
    };
  },
  mounted() {
    const saved = getCurrentUsername();
    if (saved) {
      this.username = saved;
      return;
    }
    this.loadPeople();
  },
  methods: {
    async loadPeople() {
      this.loading = true;
      this.loadError = "";
      this.people = [];
      try {
        const res = await api.getPeople();
        if (Array.isArray(res.data)) {
          this.people = res.data;
        } else {
          this.loadError = "返回数据格式异常";
        }
      } catch (e) {
        this.loadError = "加载失败: " + (e.message || "网络错误");
      }
      this.loading = false;
    },
    confirmUser() {
      if (!this.selectedUser) {
        this.error = "请先选择一个用户";
        return;
      }
      this.error = "";
      this.username = this.selectedUser;
      setCurrentUsername(this.selectedUser);
      this.$router.replace({ path: "/", query: {} });
    },
    switchUser() {
      this.username = "";
      this.selectedUser = "";
      setCurrentUsername("");
      this.loadPeople();
    },
  },
};
</script>
