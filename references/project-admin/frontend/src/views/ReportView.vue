<template>
  <div>
    <div class="toolbar">
      <router-link v-if="report" class="btn btn-ghost" :to="`/projects/${report.project_id}`">
        ← 返回项目
      </router-link>
    </div>
    <div v-if="error" class="error">{{ error }}</div>
    <div v-else-if="!report" class="empty">加载中…</div>
    <div v-else class="panel">
      <div class="panel-hd">
        <div>
          <h2>{{ report.title }}</h2>
          <div class="mono">{{ report.pipeline }} · {{ report.created_at }} · {{ report.created_by }}</div>
        </div>
      </div>
      <div class="panel-bd">
        <article class="md-body" v-html="html"></article>
      </div>
    </div>
  </div>
</template>

<script>
import { marked } from "marked";
import { api } from "../api/index.js";

export default {
  name: "ReportView",
  props: { reportId: String },
  data() {
    return { report: null, html: "", error: "" };
  },
  async mounted() {
    try {
      this.report = await api.getReport(this.reportId);
      this.html = marked.parse(this.report.markdown_body || "");
    } catch (e) {
      this.error = e.message;
    }
  },
};
</script>
