<template>
  <div>
    <div class="d-flex align-items-center py-1 border-bottom" :style="{ paddingLeft: (node.level - 1) * 24 + 'px' }">
      <button class="btn btn-sm btn-link text-decoration-none p-0 me-1" @click="expanded = !expanded"
        v-if="node.children && node.children.length">
        <i class="bi" :class="expanded ? 'bi-chevron-down' : 'bi-chevron-right'"></i>
      </button>
      <span v-else class="me-2" style="width:14px"></span>
      <i class="bi bi-folder2 me-2 text-warning"></i>
      <span class="flex-grow-1">{{ node.name }}</span>
      <router-link :to="`/?subtree_id=${node.id}`" class="badge bg-primary text-decoration-none me-2">
        {{ node.todo_count }} 项
      </router-link>
      <small class="text-muted" v-if="node.description" :title="node.description">
        <i class="bi bi-info-circle"></i>
      </small>
    </div>
    <div v-if="expanded && node.children && node.children.length">
      <TreeNode v-for="child in node.children" :key="child.id" :node="child" />
    </div>
  </div>
</template>

<script>
export default {
  name: "TreeNode",
  props: { node: { type: Object, required: true } },
  data() {
    return { expanded: this.node.level <= 2 };
  },
};
</script>
