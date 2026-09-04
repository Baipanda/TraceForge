import { createRouter, createWebHistory } from "vue-router";
import ProjectList from "./views/ProjectList.vue";
import ProjectEditor from "./views/ProjectEditor.vue";
import ProjectDetail from "./views/ProjectDetail.vue";
import ReportView from "./views/ReportView.vue";

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/", name: "list", component: ProjectList },
    { path: "/projects/new", name: "create", component: ProjectEditor },
    { path: "/projects/:id", name: "detail", component: ProjectDetail, props: true },
    { path: "/projects/:id/edit", name: "edit", component: ProjectEditor, props: true },
    { path: "/reports/:reportId", name: "report", component: ReportView, props: true },
  ],
});

export default router;
