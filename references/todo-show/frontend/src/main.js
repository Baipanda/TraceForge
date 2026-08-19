import { createApp } from "vue";
import { createRouter, createWebHistory } from "vue-router";
import App from "./App.vue";

import "bootstrap/dist/css/bootstrap.min.css";
import "bootstrap-icons/font/bootstrap-icons.css";
import "bootstrap/dist/js/bootstrap.bundle.min.js";

import TodoList from "./views/TodoList.vue";
import TodoDetail from "./views/TodoDetail.vue";
import TodoCreate from "./views/TodoCreate.vue";
import TreeView from "./views/TreeView.vue";
import NotFound from "./views/NotFound.vue";
import LogsView from "./views/LogsView.vue";

const routes = [
  { path: "/", name: "list", component: TodoList },
  { path: "/todos/:id", name: "detail", component: TodoDetail, props: true },
  { path: "/create", name: "create", component: TodoCreate },
  { path: "/tree", name: "tree", component: TreeView },
  { path: "/logs", name: "logs", component: LogsView },
  { path: "/:pathMatch(.*)*", name: "notfound", component: NotFound },
];

const router = createRouter({
  history: createWebHistory(),
  routes,
});

const app = createApp(App);
app.use(router);
app.mount("#app");
