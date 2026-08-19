<template>
  <div>
    <h4 class="mb-3"><i class="bi bi-diagram-3 me-2"></i>分类树</h4>
    <div class="card">
      <div class="card-body">
        <div v-if="loading" class="text-center text-muted py-3">
          <div class="spinner-border spinner-border-sm me-2"></div>加载中...
        </div>
        <div v-else-if="error" class="alert alert-danger m-3">
          <i class="bi bi-exclamation-triangle me-2"></i>{{ error }}
          <button class="btn btn-sm btn-outline-danger ms-2" @click="load">重试</button>
        </div>
        <div v-else-if="roots.length === 0" class="text-center text-muted py-3">暂无分类</div>
        <TreeNode v-for="node in roots" :key="node.id" :node="node" />
      </div>
    </div>
  </div>
</template>

<script>
import api from "../api/index.js";
import TreeNode from "../components/TreeNode.vue";

export default {
  name: "TreeView",
  components: { TreeNode },
  data() {
    return { roots: [], loading: true, error: "" };
  },
  async mounted() {
    await this.load();
  },
  methods: {
    async load() {
      this.loading = true;
      this.error = "";
      try {
        const res = await api.getSubtrees();
        this.roots = res.data;
      } catch (e) {
        this.error = "加载分类树失败: " + (e.response?.data?.detail || e.message);
      }
      this.loading = false;
    },
  },
};
</script>
