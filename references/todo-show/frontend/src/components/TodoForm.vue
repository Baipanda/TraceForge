<template>
  <div class="card">
    <div class="card-body">
      <div class="row g-3">
        <div class="col-12">
          <label class="form-label">标题 <span class="text-danger">*</span></label>
          <input class="form-control" v-model="form.title" placeholder="请输入标题" maxlength="2000" />
        </div>
        <div class="col-12">
          <div class="form-check form-switch mb-0">
            <input id="todo-is-bug" class="form-check-input" type="checkbox" v-model="form.is_bug" />
            <label class="form-check-label" for="todo-is-bug">标记为 Bug</label>
          </div>
        </div>
        <div class="col-12">
          <label class="form-label">描述</label>
          <textarea class="form-control" v-model="form.description" rows="4" placeholder="可选描述"></textarea>
        </div>
        <div class="col-md-4">
          <label class="form-label">优先级</label>
          <select class="form-select" v-model="form.priority">
            <option value="high">High</option>
            <option value="normal">Normal</option>
            <option value="low">Low</option>
          </select>
        </div>
        <div class="col-md-4">
          <label class="form-label">状态</label>
          <select class="form-select" v-model="form.status" :disabled="!editing">
            <option value="pending">Pending</option>
            <option value="completed">Completed</option>
            <option value="cancelled">Cancelled</option>
          </select>
        </div>
        <div class="col-md-4">
          <label class="form-label">分类 <span class="text-danger">*</span></label>
          <select class="form-select" v-model="form.subtree_id">
            <option value="">请选择</option>
            <option v-for="s in subtrees" :key="s.id" :value="s.id">
              {{ "—".repeat(Math.max(0, s.level - 1)) }} {{ s.name }}
            </option>
          </select>
        </div>
        <div class="col-md-6">
          <label class="form-label">项目</label>
          <select class="form-select" v-model="form.project_id">
            <option :value="null">无</option>
            <option v-for="p in projects" :key="p.id" :value="p.id">{{ p.name }}</option>
          </select>
        </div>
        <div class="col-md-6">
          <label class="form-label">同步频率</label>
          <select class="form-select" v-model="form.track_frequency">
            <option :value="null">不设置</option>
            <option value="daily">每天</option>
            <option value="every_3_days">每 3 天</option>
            <option value="weekly">每周</option>
            <option value="biweekly">每两周</option>
            <option value="monthly">每月</option>
          </select>
        </div>
        <div class="col-12">
          <label class="form-label">同步进展填写提示 <span class="text-danger">*</span></label>
          <textarea
            class="form-control"
            v-model="form.progress_prompt"
            rows="2"
            maxlength="2000"
            placeholder="打开同步进展弹框时展示给填写人的提示"
          ></textarea>
          <small class="text-muted">{{ form.progress_prompt.length }}/2000</small>
        </div>

        <!-- 父 Todo: 搜索 + 下拉 -->
        <div class="col-md-8">
          <label class="form-label">父 Todo</label>
          <input class="form-control form-control-sm mb-1" v-model="parentSearch" placeholder="输入关键词搜索..." />
          <select class="form-select" v-model="form.parent_id" size="5">
            <option :value="null">— 无（顶级 Todo）—</option>
            <option v-for="t in filteredParentOptions" :key="t.id" :value="t.id">
              {{ truncate(t.title, 80) }}
            </option>
          </select>
          <small class="text-muted">
            <span v-if="parentLoading">搜索中...</span>
            <span v-else>{{ filteredParentOptions.length }} 条匹配</span>
          </small>
        </div>

        <!-- 依赖项: 搜索 + 多选 -->
        <div class="col-12">
          <label class="form-label">依赖项 (depends_on)</label>
          <input class="form-control form-control-sm mb-1" v-model="dependsSearch" placeholder="输入关键词搜索..." />
          <select class="form-select" v-model="form.depends_on_ids" multiple size="5">
            <option v-for="t in filteredDependsOptions" :key="t.id" :value="t.id">
              {{ truncate(t.title, 80) }}
            </option>
          </select>
          <small class="text-muted">
            按住 Ctrl/Cmd 多选 ·
            <span v-if="dependsLoading">搜索中...</span>
            <span v-else>{{ filteredDependsOptions.length }} 条匹配</span>
          </small>
        </div>

        <!-- 关注人: 搜索 + 多选 -->
        <div class="col-md-6">
          <label class="form-label">关注人</label>
          <input class="form-control form-control-sm mb-1" v-model="watcherSearch" placeholder="搜索人员..." />
          <select class="form-select" v-model="form.watcher_ids" multiple size="5">
            <option v-for="p in filteredWatchers" :key="p.id" :value="p.id">{{ p.canonical_name }}</option>
          </select>
          <small class="text-muted">按住 Ctrl/Cmd 多选</small>
        </div>

        <!-- 主力: 搜索 + 多选 -->
        <div class="col-md-6">
          <label class="form-label">主力</label>
          <input class="form-control form-control-sm mb-1" v-model="mainForceSearch" placeholder="搜索人员..." />
          <select class="form-select" v-model="form.main_force_ids" multiple size="5">
            <option v-for="p in filteredMainForce" :key="p.id" :value="p.id">{{ p.canonical_name }}</option>
          </select>
          <small class="text-muted">按住 Ctrl/Cmd 多选</small>
        </div>

        <!-- 流程管理 -->
        <div class="col-md-6">
          <label class="form-label">流程管理</label>
          <input class="form-control form-control-sm mb-1" v-model="pmSearch" placeholder="搜索人员..." />
          <select class="form-select" v-model="form.process_manager_ids" multiple size="4">
            <option v-for="p in filteredPM" :key="p.id" :value="p.id">{{ p.canonical_name }}</option>
          </select>
          <small class="text-muted">按住 Ctrl/Cmd 多选</small>
        </div>

        <!-- 技术顾问 -->
        <div class="col-md-6">
          <label class="form-label">技术顾问</label>
          <input class="form-control form-control-sm mb-1" v-model="taSearch" placeholder="搜索人员..." />
          <select class="form-select" v-model="form.technical_advisor_ids" multiple size="4">
            <option v-for="p in filteredTA" :key="p.id" :value="p.id">{{ p.canonical_name }}</option>
          </select>
          <small class="text-muted">按住 Ctrl/Cmd 多选</small>
        </div>

        <!-- 后备力量 -->
        <div class="col-md-6">
          <label class="form-label">后备力量</label>
          <input class="form-control form-control-sm mb-1" v-model="bfSearch" placeholder="搜索人员..." />
          <select class="form-select" v-model="form.backup_force_ids" multiple size="4">
            <option v-for="p in filteredBF" :key="p.id" :value="p.id">{{ p.canonical_name }}</option>
          </select>
          <small class="text-muted">按住 Ctrl/Cmd 多选</small>
        </div>

        <div class="col-md-6">
          <label class="form-label">Zulip Stream</label>
          <input class="form-control" v-model="form.zulip_stream" />
        </div>
        <div class="col-md-6">
          <label class="form-label">Zulip Topic</label>
          <input class="form-control" v-model="form.zulip_topic" />
        </div>
      </div>
      <div class="mt-3 d-flex gap-2">
        <button class="btn btn-primary" @click="save" :disabled="saving">
          <span v-if="saving" class="spinner-border spinner-border-sm me-1"></span>
          {{ editing ? "保存修改" : "创建" }}
        </button>
        <button class="btn btn-outline-secondary" @click="$emit('cancel')">取消</button>
      </div>
      <div v-if="error" class="alert alert-danger mt-2 mb-0 py-1">{{ error }}</div>
    </div>
  </div>
</template>

<script>
import api from "../api/index.js";

export default {
  name: "TodoForm",
  props: {
    todo: { type: Object, default: null },
    editing: { type: Boolean, default: false },
  },
  emits: ["saved", "cancel"],
  data() {
    return {
      form: {
        title: "",
        is_bug: false,
        description: "",
        priority: "normal",
        status: "pending",
        subtree_id: "",
        project_id: null,
        track_frequency: null,
        progress_prompt: "请说明本次完成了什么、当前问题或风险，以及下一步计划和预计时间。",
        parent_id: null,
        depends_on_ids: [],
        watcher_ids: [],
        process_manager_ids: [],
        technical_advisor_ids: [],
        main_force_ids: [],
        backup_force_ids: [],
        zulip_stream: "",
        zulip_topic: "",
      },
      people: [],
      projects: [],
      subtrees: [],
      parentOptions: [],
      dependsOptions: [],
      saving: false,
      error: "",
      parentLoading: false,
      dependsLoading: false,
      parentSearchTimer: null,
      dependsSearchTimer: null,
      // Search filters
      parentSearch: "",
      dependsSearch: "",
      watcherSearch: "",
      mainForceSearch: "",
      pmSearch: "",
      taSearch: "",
      bfSearch: "",
    };
  },
  computed: {
    filteredParentOptions() {
      return this.parentOptions;
    },
    filteredDependsOptions() {
      return this.dependsOptions;
    },
    filteredWatchers() {
      return this.filterPeople(this.watcherSearch);
    },
    filteredMainForce() {
      return this.filterPeople(this.mainForceSearch);
    },
    filteredPM() {
      return this.filterPeople(this.pmSearch);
    },
    filteredTA() {
      return this.filterPeople(this.taSearch);
    },
    filteredBF() {
      return this.filterPeople(this.bfSearch);
    },
  },
  async mounted() {
    await Promise.all([
      this.loadPeople(),
      this.loadProjects(),
      this.loadSubtrees(),
      this.loadParentOptions(),
      this.loadDependsOptions(),
    ]);
    if (this.todo) {
      this.form.title = this.todo.title;
      this.form.is_bug = Boolean(this.todo.is_bug);
      this.form.description = this.todo.description || "";
      this.form.priority = this.todo.priority;
      this.form.status = this.todo.status;
      this.form.subtree_id = this.todo.subtree_id;
      this.form.project_id = this.todo.project_id;
      this.form.track_frequency = this.todo.track_frequency || null;
      this.form.progress_prompt = this.todo.progress_prompt || this.form.progress_prompt;
      this.form.parent_id = this.todo.parent_id || null;
      this.form.depends_on_ids = this.todo.depends_on_ids || [];
      this.form.watcher_ids = this.todo.watcher_ids || [];
      this.form.process_manager_ids = this.todo.process_manager_ids || [];
      this.form.technical_advisor_ids = this.todo.technical_advisor_ids || [];
      this.form.main_force_ids = this.todo.main_force_ids || [];
      this.form.backup_force_ids = this.todo.backup_force_ids || [];
      this.form.zulip_stream = this.todo.zulip_stream || "";
      this.form.zulip_topic = this.todo.zulip_topic || "";
      this.ensureSelectedTodoOptions();
    }
  },
  watch: {
    parentSearch() {
      clearTimeout(this.parentSearchTimer);
      this.parentSearchTimer = setTimeout(() => this.loadParentOptions(), 300);
    },
    dependsSearch() {
      clearTimeout(this.dependsSearchTimer);
      this.dependsSearchTimer = setTimeout(() => this.loadDependsOptions(), 300);
    },
  },
  beforeUnmount() {
    clearTimeout(this.parentSearchTimer);
    clearTimeout(this.dependsSearchTimer);
  },
  methods: {
    filterPeople(search) {
      if (!search) return this.people;
      const q = search.toLowerCase();
      return this.people.filter(p => p.canonical_name.toLowerCase().includes(q));
    },
    truncate(text, max) {
      if (!text) return "";
      return text.length > max ? text.slice(0, max) + "..." : text;
    },
    async loadPeople() {
      try {
        this.people = (await api.getPeople()).data;
      } catch (e) { console.error(e); }
    },
    async loadProjects() {
      try { this.projects = (await api.getProjects()).data; } catch (e) { console.error(e); }
    },
    async loadSubtrees() {
      try {
        const res = await api.getSubtrees();
        this.flatten(res.data);
      } catch (e) { console.error(e); }
    },
    async loadParentOptions() {
      this.parentLoading = true;
      try {
        const res = await api.getTodos({
          size: 200,
          sort: "updated_at_desc",
          q: this.parentSearch || undefined,
        });
        this.parentOptions = this.excludeCurrentTodo(res.data.items);
        this.ensureSelectedTodoOptions();
      } catch (e) { console.error(e); }
      this.parentLoading = false;
    },
    async loadDependsOptions() {
      this.dependsLoading = true;
      try {
        const res = await api.getTodos({
          size: 200,
          sort: "updated_at_desc",
          q: this.dependsSearch || undefined,
        });
        this.dependsOptions = this.excludeCurrentTodo(res.data.items);
        this.ensureSelectedTodoOptions();
      } catch (e) { console.error(e); }
      this.dependsLoading = false;
    },
    excludeCurrentTodo(items) {
      if (!this.todo?.id) return items;
      return items.filter(t => t.id !== this.todo.id);
    },
    upsertTodoOption(listName, item) {
      if (!item?.id) return;
      const list = this[listName];
      if (!list.some(t => t.id === item.id)) {
        list.unshift(item);
      }
    },
    ensureSelectedTodoOptions() {
      if (!this.todo) return;
      if (this.todo.parent_id && this.todo.parent_title) {
        this.upsertTodoOption("parentOptions", {
          id: this.todo.parent_id,
          title: this.todo.parent_title,
        });
      }
      for (const dep of this.todo.depends_on_details || []) {
        this.upsertTodoOption("dependsOptions", dep);
      }
    },
    flatten(nodes) {
      for (const n of nodes) {
        this.subtrees.push(n);
        if (n.children?.length) this.flatten(n.children);
      }
    },
    async save() {
      if (!this.form.title.trim()) { this.error = "标题不能为空"; return; }
      if (!this.form.subtree_id) { this.error = "请选择分类"; return; }
      if (!this.form.progress_prompt.trim()) { this.error = "请填写同步进展提示"; return; }
      this.error = "";
      this.saving = true;
      try {
        const payload = { ...this.form };
        if (!payload.parent_id) payload.parent_id = null;
        if (!payload.project_id) payload.project_id = null;
        payload.track_frequency = payload.track_frequency || null;
        payload.progress_prompt = payload.progress_prompt.trim();
        let res;
        if (this.editing && this.todo) {
          res = await api.updateTodo(this.todo.id, payload);
        } else {
          res = await api.createTodo(payload);
        }
        this.$emit("saved", res.data);
      } catch (e) {
        this.error = e.response?.data?.detail || e.message || "保存失败";
      }
      this.saving = false;
    },
  },
};
</script>
