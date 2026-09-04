<template>
  <div class="panel">
    <div class="panel-hd">
      <h2>{{ isEdit ? `编辑 · ${form.project_id}` : "新建项目名片" }}</h2>
      <div style="display: flex; gap: 8px">
        <router-link class="btn btn-ghost" :to="isEdit ? `/projects/${id}` : '/'">取消</router-link>
        <button class="btn btn-primary" :disabled="saving" @click="save">
          {{ saving ? "保存中…" : "保存" }}
        </button>
      </div>
    </div>
    <div class="panel-bd">
      <div v-if="error" class="error" style="margin-bottom: 12px">{{ error }}</div>

      <div class="section-title">身份</div>
      <div class="form-grid">
        <div class="field">
          <label>project_id（创建后不可改）</label>
          <input v-model="form.project_id" class="input" :disabled="isEdit" placeholder="agent-dev" />
        </div>
        <div class="field">
          <label>状态</label>
          <select v-model="form.status" class="select">
            <option value="active">active</option>
            <option value="paused">paused</option>
            <option value="done">done</option>
            <option value="archived">archived</option>
          </select>
        </div>
        <div class="field full">
          <label>显示名称</label>
          <input v-model="form.display_name" class="input" placeholder="TraceForge Agent 开发" />
        </div>
        <div class="field full">
          <label>描述</label>
          <textarea v-model="form.description" class="textarea" />
        </div>
      </div>

      <div class="section-title">Zulip</div>
      <div class="form-grid">
        <div class="field">
          <label>stream</label>
          <input v-model="form.zulip_stream" class="input" placeholder="dev" />
        </div>
        <div class="field">
          <label>stream_id</label>
          <input v-model="form.zulip_stream_id" class="input" placeholder="可选" />
        </div>
        <div class="field">
          <label>topic</label>
          <input v-model="form.zulip_topic" class="input" placeholder="agent开发" />
        </div>
        <div class="field">
          <label>notify_topic</label>
          <input v-model="form.notify_topic" class="input" placeholder="可选，默认同 topic" />
        </div>
      </div>

      <div class="section-title">文档</div>
      <div class="form-grid">
        <div class="field full">
          <label>docs_root</label>
          <input v-model="form.docs_root" class="input" placeholder="workspace_shared/docs/agent-dev" />
        </div>
        <div class="field">
          <label>prd_path</label>
          <input v-model="form.prd_path" class="input" placeholder="PRD.md" />
        </div>
        <div class="field">
          <label>tech_path</label>
          <input v-model="form.tech_path" class="input" placeholder="TECH.md" />
        </div>
      </div>

      <div class="section-title">Gitea</div>
      <div class="form-grid">
        <div class="field">
          <label>owner</label>
          <input v-model="form.gitea_owner" class="input" />
        </div>
        <div class="field">
          <label>repo</label>
          <input v-model="form.gitea_repo" class="input" />
        </div>
        <div class="field">
          <label>default_branch</label>
          <input v-model="form.default_branch" class="input" />
        </div>
        <div class="field">
          <label>path_filters（逗号分隔）</label>
          <input v-model="pathFiltersText" class="input" placeholder="src/traceforge/,docs/" />
        </div>
      </div>

      <div class="section-title">Todo / 组织</div>
      <div class="form-grid">
        <div class="field">
          <label>subtree_code</label>
          <input v-model="form.subtree_code" class="input" placeholder="software.cloud.agent" />
        </div>
        <div class="field">
          <label>todo_show_project_id</label>
          <input v-model="form.todo_show_project_id" class="input" placeholder="对齐 todo-show 可选" />
        </div>
        <div class="field">
          <label>window_days</label>
          <input v-model.number="form.window_days" class="input" type="number" min="1" max="365" />
        </div>
        <div class="field">
          <label>target_at</label>
          <input v-model="form.target_at" class="input" placeholder="2026-09-30" />
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { api } from "../api/index.js";

const empty = () => ({
  project_id: "",
  display_name: "",
  description: "",
  status: "active",
  zulip_stream: "",
  zulip_stream_id: "",
  zulip_topic: "",
  notify_topic: "",
  docs_root: "",
  prd_path: "",
  tech_path: "",
  gitea_owner: "",
  gitea_repo: "",
  default_branch: "main",
  path_filters: [],
  subtree_code: "",
  todo_show_project_id: "",
  window_days: 7,
  start_at: null,
  target_at: null,
});

export default {
  name: "ProjectEditor",
  props: { id: String },
  data() {
    return {
      form: empty(),
      pathFiltersText: "",
      saving: false,
      error: "",
    };
  },
  computed: {
    isEdit() {
      return Boolean(this.id);
    },
  },
  async mounted() {
    if (!this.isEdit) return;
    try {
      const p = await api.getProject(this.id);
      this.form = { ...empty(), ...p };
      this.pathFiltersText = (p.path_filters || []).join(", ");
    } catch (e) {
      this.error = e.message;
    }
  },
  methods: {
    payload() {
      const path_filters = this.pathFiltersText
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean);
      const body = { ...this.form, path_filters };
      delete body.members;
      delete body.created_at;
      delete body.updated_at;
      delete body.created_by;
      delete body.updated_by;
      return body;
    },
    async save() {
      this.saving = true;
      this.error = "";
      try {
        const body = this.payload();
        if (this.isEdit) {
          await api.updateProject(this.id, body);
          this.$router.push(`/projects/${this.id}`);
        } else {
          if (!body.project_id || !body.display_name) {
            throw new Error("project_id 与 display_name 必填");
          }
          await api.createProject(body);
          this.$router.push(`/projects/${body.project_id}`);
        }
      } catch (e) {
        this.error = e.message;
      } finally {
        this.saving = false;
      }
    },
  },
};
</script>
