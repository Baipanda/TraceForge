<template>
  <div class="text-center py-5">
    <h1 class="display-1 text-muted">404</h1>
    <p class="lead">页面未找到</p>
    <router-link to="/" class="btn btn-primary">
      <i class="bi bi-house me-1"></i>返回首页
    </router-link>
  </div>
</template>

<script>
export default { name: "NotFound" };
</script>
