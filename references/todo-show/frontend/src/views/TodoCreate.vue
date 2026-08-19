<template>
  <div>
    <h4 class="mb-3"><i class="bi bi-plus-circle me-2"></i>新建 Todo</h4>
    <TodoForm @saved="onSaved" @cancel="$router.push('/')" />
  </div>
</template>

<script>
import TodoForm from "../components/TodoForm.vue";
export default {
  name: "TodoCreate",
  components: { TodoForm },
  methods: {
    onSaved(todo) {
      this.$router.push(`/todos/${todo.id}`);
    },
  },
};
</script>
