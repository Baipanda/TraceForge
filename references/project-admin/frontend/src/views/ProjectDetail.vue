<template>
  <div v-if="error" class="error">{{ error }}</div>
  <div v-else-if="!project" class="empty">加载中…</div>
  <div v-else class="split">
    <div class="panel">
      <div class="panel-hd">
        <div>
          <h2>{{ project.display_name }}</h2>
          <div class="mono">{{ project.project_id }}</div>
        </div>
        <div style="display: flex; gap: 8px; align-items: center">
          <span class="badge" :class="`badge-${project.status}`">{{ project.status }}</span>
          <router-link class="btn btn-ghost" :to="`/projects/${project.project_id}/edit`">编辑</router-link>
          <button
            v-if="project.status !== 'archived'"
            class="btn btn-danger"
            @click="archive"
          >
            归档
          </button>
        </div>
      </div>
      <div class="panel-bd">
        <p class="meta" style="margin-top: 0">{{ project.description || "暂无描述" }}</p>
        <div class="kv">
          <div class="kv-row"><span>Zulip</span><span>{{ project.zulip_stream || "—" }} / {{ project.zulip_topic || "—" }}</span></div>
          <div class="kv-row"><span>Docs</span><span class="mono">{{ project.docs_root || "—" }}</span></div>
          <div class="kv-row"><span>PRD / TECH</span><span>{{ project.prd_path || "—" }} · {{ project.tech_path || "—" }}</span></div>
          <div class="kv-row"><span>Gitea</span><span>{{ project.gitea_owner && project.gitea_repo ? `${project.gitea_owner}/${project.gitea_repo}@${project.default_branch}` : "—" }}</span></div>
          <div class="kv-row"><span>Subtree</span><span class="mono">{{ project.subtree_code || "—" }}</span></div>
          <div class="kv-row"><span>Todo-show</span><span>{{ project.todo_show_project_id || "—" }}</span></div>
          <div class="kv-row"><span>窗口</span><span>{{ project.window_days }} 天</span></div>
          <div class="kv-row"><span>更新</span><span>{{ project.updated_by }} · {{ project.updated_at }}</span></div>
        </div>

        <div class="section-title">成员</div>
        <div class="member-list">
          <div v-for="m in project.members" :key="m.id" class="member-item">
            <div>
              <strong>{{ m.person_name }}</strong>
              <span class="mono"> · {{ m.role }}</span>
            </div>
            <button class="btn btn-ghost" style="padding: 6px 10px" @click="removeMember(m.id)">移除</button>
          </div>
          <div v-if="!project.members.length" class="meta">暂无成员</div>
        </div>
        <div class="toolbar" style="margin-top: 12px">
          <input v-model="member.person_name" class="input" style="max-width: 180px" placeholder="姓名" />
          <select v-model="member.role" class="select" style="max-width: 140px">
            <option value="owner">owner</option>
            <option value="pm">pm</option>
            <option value="dev">dev</option>
            <option value="reviewer">reviewer</option>
            <option value="mentor">mentor</option>
          </select>
          <button class="btn btn-primary" @click="addMember">添加成员</button>
        </div>
      </div>
    </div>

    <div class="panel">
      <div class="panel-hd">
        <h2>SOP 报告</h2>
        <button class="btn btn-ghost" @click="seedDemoReport">写入演示报告</button>
      </div>
      <div class="panel-bd">
        <p class="meta" style="margin-top: 0">
          进度 SOP 产出的 Markdown 会落在这里，方便 Mentor 回看。TraceForge 后续可 POST `/api/reports`。
        </p>
        <div v-if="!reports.length" class="empty">还没有报告</div>
        <div v-else class="report-list">
          <router-link
            v-for="r in reports"
            :key="r.id"
            class="report-item"
            :to="`/reports/${r.id}`"
          >
            <div>
              <strong>{{ r.title }}</strong>
              <div class="mono">{{ r.pipeline }} · {{ r.created_at }}</div>
            </div>
            <span class="meta">查看</span>
          </router-link>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { api } from "../api/index.js";

export default {
  name: "ProjectDetail",
  props: { id: String },
  data() {
    return {
      project: null,
      reports: [],
      error: "",
      member: { person_name: "", role: "dev", person_id: "" },
    };
  },
  async mounted() {
    await this.reload();
  },
  methods: {
    async reload() {
      this.error = "";
      try {
        this.project = await api.getProject(this.id);
        this.reports = await api.listReports(this.id);
      } catch (e) {
        this.error = e.message;
      }
    },
    async archive() {
      if (!confirm(`归档项目 ${this.id}？`)) return;
      try {
        await api.archiveProject(this.id);
        await this.reload();
      } catch (e) {
        this.error = e.message;
      }
    },
    async addMember() {
      try {
        await api.addMember(this.id, this.member);
        this.member = { person_name: "", role: "dev", person_id: "" };
        await this.reload();
      } catch (e) {
        this.error = e.message;
      }
    },
    async removeMember(memberId) {
      try {
        await api.removeMember(this.id, memberId);
        await this.reload();
      } catch (e) {
        this.error = e.message;
      }
    },
    async seedDemoReport() {
      const md = `## 项目进度体检：${this.project.display_name}
- 范围：#${this.project.zulip_stream || "?"} / ${this.project.zulip_topic || "?"}
- 编排版本：progress-sop-v1（演示）

### 1. 文档侧
- docs_root: \`${this.project.docs_root || "未配置"}\`

### 2. 讨论侧
- （SOP 接入后由 topic.summarize 填充）

### 3. 任务侧
- subtree: \`${this.project.subtree_code || "未配置"}\`

### 4. 代码侧
- repo: \`${this.project.gitea_owner}/${this.project.gitea_repo}\`

### 5. 综合判断
- 总体：🟡 演示数据
- 一句话：项目名片已就绪，等待 TraceForge SOP 写入真实报告。
`;
      try {
        await api.createReport({
          project_id: this.id,
          title: `演示报告 · ${new Date().toISOString().slice(0, 16)}`,
          pipeline: "progress-sop-v1",
          markdown_body: md,
          meta_json: { demo: true },
          created_by: "project-admin-ui",
        });
        await this.reload();
      } catch (e) {
        this.error = e.message;
      }
    },
  },
};
</script>
