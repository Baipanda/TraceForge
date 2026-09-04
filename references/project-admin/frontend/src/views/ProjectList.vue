<template>
  <div>
    <div class="toolbar">
      <input v-model="q" class="input" style="max-width: 280px" placeholder="搜索 id / 名称 / topic" @keyup.enter="load" />
      <select v-model="status" class="select" style="max-width: 160px" @change="load">
        <option value="">全部状态</option>
        <option value="active">active</option>
        <option value="paused">paused</option>
        <option value="done">done</option>
      </select>
      <label class="meta" style="display: flex; align-items: center; gap: 6px">
        <input v-model="includeArchived" type="checkbox" @change="load" />
        含归档
      </label>
      <button class="btn btn-ghost" @click="load">刷新</button>
      <router-link class="btn btn-primary" to="/projects/new">新建项目</router-link>
    </div>

    <div v-if="error" class="error">{{ error }}</div>
    <div v-else-if="loading" class="empty">加载中…</div>
    <div v-else-if="!projects.length" class="empty">还没有项目。先创建一张项目名片供 SOP 使用。</div>
    <div v-else class="grid-cards">
      <router-link
        v-for="p in projects"
        :key="p.project_id"
        class="card"
        :to="`/projects/${p.project_id}`"
      >
        <div class="card-top">
          <div>
            <h3>{{ p.display_name }}</h3>
            <div class="mono">{{ p.project_id }}</div>
          </div>
          <span class="badge" :class="`badge-${p.status}`">{{ p.status }}</span>
        </div>
        <div class="meta">
          <div v-if="p.zulip_stream || p.zulip_topic">
            Zulip · {{ p.zulip_stream || "—" }} / {{ p.zulip_topic || "—" }}
          </div>
          <div v-if="p.gitea_owner && p.gitea_repo">
            Gitea · {{ p.gitea_owner }}/{{ p.gitea_repo }}
          </div>
          <div v-if="p.docs_root">Docs · {{ p.docs_root }}</div>
          <div v-if="!p.zulip_topic && !p.gitea_repo && !p.docs_root">绑定尚未完善</div>
        </div>
      </router-link>
    </div>
  </div>
</template>

<script>
import { api } from "../api/index.js";

export default {
  name: "ProjectList",
  data() {
    return {
      projects: [],
      q: "",
      status: "",
      includeArchived: false,
      loading: false,
      error: "",
    };
  },
  mounted() {
    this.load();
  },
  methods: {
    async load() {
      this.loading = true;
      this.error = "";
      try {
        this.projects = await api.listProjects({
          q: this.q,
          status: this.status,
          include_archived: this.includeArchived,
        });
      } catch (e) {
        this.error = e.message;
      } finally {
        this.loading = false;
      }
    },
  },
};
</script>
