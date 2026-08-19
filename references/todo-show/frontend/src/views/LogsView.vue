<template>
  <div>
    <h4 class="mb-3"><i class="bi bi-journal-text me-2"></i>操作日志</h4>

    <div class="row g-2 mb-3 align-items-end">
      <div class="col-auto">
        <label class="form-label small mb-0">操作</label>
        <select class="form-select form-select-sm" v-model="actionFilter" @change="search">
          <option value="">全部</option>
          <option value="created">创建</option>
          <option value="updated">更新</option>
          <option value="completed">完成</option>
          <option value="cancelled">取消</option>
          <option value="deleted">删除</option>
          <option value="progress_filled">填写进展</option>
          <option value="progress_confirmed">确认同步</option>
          <option value="auto_completed">父项自动完成</option>
          <option value="auto_reopened">父项自动恢复</option>
          <option value="sync_auto_confirmed">父项自动同步</option>
          <option value="sync_rollup_revoked">同步汇总失效</option>
          <option value="weights_updated">调整子项占比</option>
          <option value="progress_synced">同步进展（旧记录）</option>
        </select>
      </div>
      <div class="col-auto">
        <label class="form-label small mb-0">用户</label>
        <input class="form-control form-control-sm" v-model="userFilter" placeholder="用户名" @keyup.enter="search" />
      </div>
      <div class="col-auto">
        <button class="btn btn-sm btn-outline-secondary mt-3" @click="search">搜索</button>
      </div>
    </div>

    <div class="card">
      <div class="table-responsive">
        <table class="table table-hover table-sm mb-0">
          <thead class="table-light">
            <tr>
              <th>时间</th>
              <th>用户</th>
              <th>操作</th>
              <th>目标</th>
              <th>详情</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="l in logs" :key="l.id">
              <td><small>{{ formatDate(l.created_at) }}</small></td>
              <td><span class="badge bg-secondary">{{ l.username }}</span></td>
              <td><span class="badge" :class="actionClass(l.action)">{{ actionLabel(l.action) }}</span></td>
              <td>
                <router-link v-if="l.target_type === 'todo' && l.target_id" :to="`/todos/${l.target_id}`">
                  <small class="text-muted">{{ l.target_id.slice(0, 8) }}...</small>
                </router-link>
                <small v-else class="text-muted">{{ l.target_type }}</small>
              </td>
              <td>
                <small
                  class="text-muted text-truncate d-inline-block"
                  style="max-width:520px"
                  :title="l.detail || ''"
                >
                  {{ l.detail || "—" }}
                </small>
              </td>
            </tr>
            <tr v-if="logs.length === 0 && !loading">
              <td colspan="5" class="text-center text-muted py-4">暂无日志</td>
            </tr>
            <tr v-if="loading">
              <td colspan="5" class="text-center py-4">
                <div class="spinner-border spinner-border-sm"></div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <nav class="mt-3" v-if="pages > 1">
      <ul class="pagination justify-content-center">
        <li class="page-item" :class="{ disabled: page <= 1 }">
          <a class="page-link" href="#" @click.prevent="goPage(page - 1)">&laquo;</a>
        </li>
        <li class="page-item" v-for="p in visiblePages" :key="p" :class="{ active: p === page }">
          <a class="page-link" href="#" @click.prevent="goPage(p)">{{ p }}</a>
        </li>
        <li class="page-item" :class="{ disabled: page >= pages }">
          <a class="page-link" href="#" @click.prevent="goPage(page + 1)">&raquo;</a>
        </li>
      </ul>
    </nav>
  </div>
</template>

<script>
import api, { http } from "../api/index.js";

export default {
  name: "LogsView",
  data() {
    return {
      logs: [],
      loading: false,
      page: 1,
      size: 50,
      pages: 0,
      actionFilter: "",
      userFilter: "",
    };
  },
  computed: {
    visiblePages() {
      const pages = [];
      const start = Math.max(1, this.page - 2);
      const end = Math.min(this.pages, this.page + 2);
      for (let i = start; i <= end; i++) pages.push(i);
      return pages;
    },
  },
  mounted() {
    this.fetchLogs();
  },
  methods: {
    async fetchLogs() {
      this.loading = true;
      try {
        const res = await http.get("/logs", {
          params: {
            action: this.actionFilter || undefined,
            username: this.userFilter || undefined,
            page: this.page,
            size: this.size,
          },
        });
        this.logs = res.data.items;
        this.pages = res.data.pages;
      } catch (e) {
        console.error(e);
      }
      this.loading = false;
    },
    search() {
      this.page = 1;
      this.fetchLogs();
    },
    goPage(p) {
      if (p < 1 || p > this.pages) return;
      this.page = p;
      this.fetchLogs();
    },
    actionClass(a) {
      return {
        created: "bg-info", updated: "bg-primary", completed: "bg-success",
        cancelled: "bg-warning text-dark", deleted: "bg-danger",
        progress_filled: "bg-info text-dark", progress_confirmed: "bg-success",
        auto_completed: "bg-success", auto_reopened: "bg-warning text-dark",
        sync_auto_confirmed: "bg-info text-dark", sync_rollup_revoked: "bg-secondary",
        weights_updated: "bg-primary",
        progress_synced: "bg-secondary",
      }[a] || "bg-secondary";
    },
    actionLabel(a) {
      return {
        created: "创建", updated: "更新", completed: "完成",
        cancelled: "取消", deleted: "删除",
        progress_filled: "填写进展", progress_confirmed: "确认同步",
        auto_completed: "父项自动完成", auto_reopened: "父项自动恢复",
        sync_auto_confirmed: "父项自动同步", sync_rollup_revoked: "同步汇总失效",
        weights_updated: "调整子项占比",
        progress_synced: "同步进展（旧）",
      }[a] || a;
    },
    formatDate(d) {
      return d ? new Date(d).toLocaleString("zh-CN") : "";
    },
  },
};
</script>
